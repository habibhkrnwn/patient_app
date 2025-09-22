from datetime import date, datetime
from typing import Optional, List, Union, Tuple
from fastapi import APIRouter, Depends, Request, Query, Body, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from sqlalchemy.exc import SQLAlchemyError
import io
import json
import pandas as pd

from ..auth import get_db, get_current_user
from ..models import Patient, User

router = APIRouter()

def _parse_date_q(s: Optional[str]) -> Optional[date]:
    """Parse tanggal dari query (string). Kosong/invalid → None (supaya tidak 422)."""
    if not s:
        return None
    try:
        # format aman dari <input type="date">
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

@router.get("/", include_in_schema=False)
def root(request: Request, db: Session = Depends(get_db)):
    """Jika belum login → /login, jika sudah → /dashboard"""
    from jose import JWTError, jwt
    from ..auth import SECRET_KEY, ALGORITHM
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        return RedirectResponse(url="/login", status_code=302)
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    q: Optional[str] = Query(None, description="Filter by patient name"),
    start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Aturan filter:
    - Boleh isi salah satu dari q / start / end (atau kombinasi).
    - Jika hanya start diisi → end otomatis = hari ini.
    - Jika start > end → otomatis ditukar.
    - String kosong pada start/end diabaikan (tidak 422).
    """
    from ..templates_engine import templates

    # Parse string → date (invalid/"" → None)
    s_start = _parse_date_q(start)
    s_end = _parse_date_q(end)

    # Normalisasi
    eff_start = s_start
    eff_end = s_end
    if eff_start and not eff_end:
        eff_end = date.today()
    if eff_start and eff_end and eff_start > eff_end:
        eff_start, eff_end = eff_end, eff_start

    # Base query + filter
    try:
        query = db.query(Patient)
        if q:
            query = query.filter(Patient.nama.ilike(f"%{q}%"))
        if eff_start:
            query = query.filter(Patient.tanggal_kunjungan >= eff_start)
        if eff_end:
            query = query.filter(Patient.tanggal_kunjungan <= eff_end)

        patients = query.order_by(Patient.tanggal_kunjungan.desc()).all()
        total = db.query(func.count(Patient.id)).scalar()
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Gagal memuat dashboard.")

    # ---------- Aggregations untuk Chart ----------
    def _apply_filters(qry):
        if q:
            qry = qry.filter(Patient.nama.ilike(f"%{q}%"))
        if eff_start:
            qry = qry.filter(Patient.tanggal_kunjungan >= eff_start)
        if eff_end:
            qry = qry.filter(Patient.tanggal_kunjungan <= eff_end)
        return qry

    # 1) Jumlah pasien per hari
    try:
        rows: List[Tuple[date, int]] = (
            _apply_filters(db.query(Patient.tanggal_kunjungan, func.count(Patient.id)))
            .group_by(Patient.tanggal_kunjungan)
            .order_by(Patient.tanggal_kunjungan.asc())
            .all()
        )
        visits_labels = [r[0].isoformat() for r in rows]
        visits_values = [int(r[1]) for r in rows]
    except SQLAlchemyError:
        visits_labels, visits_values = [], []

    # 2) Top Diagnosis
    try:
        diag_rows: List[Tuple[Optional[str], int]] = (
            _apply_filters(
                db.query(Patient.diagnosis, func.count(Patient.id))
                .filter(and_(Patient.diagnosis.isnot(None), Patient.diagnosis != ""))
            )
            .group_by(Patient.diagnosis)
            .order_by(func.count(Patient.id).desc())
            .all()
        )
        # Ambil top 8, gabungkan sisanya ke "Lainnya"
        top_n = 8
        diag_labels = [d or "-" for d, _ in diag_rows[:top_n]]
        diag_values = [int(c) for _, c in diag_rows[:top_n]]
        others_sum = sum(int(c) for _, c in diag_rows[top_n:])
        if others_sum:
            diag_labels.append("Lainnya")
            diag_values.append(others_sum)
    except SQLAlchemyError:
        diag_labels, diag_values = [], []

    # 3) Top Tindakan
    try:
        tind_rows: List[Tuple[Optional[str], int]] = (
            _apply_filters(
                db.query(Patient.tindakan, func.count(Patient.id))
                .filter(and_(Patient.tindakan.isnot(None), Patient.tindakan != ""))
            )
            .group_by(Patient.tindakan)
            .order_by(func.count(Patient.id).desc())
            .all()
        )
        top_n = 8
        tind_labels = [t or "-" for t, _ in tind_rows[:top_n]]
        tind_values = [int(c) for _, c in tind_rows[:top_n]]
        others_sum = sum(int(c) for _, c in tind_rows[top_n:])
        if others_sum:
            tind_labels.append("Lainnya")
            tind_values.append(others_sum)
    except SQLAlchemyError:
        tind_labels, tind_values = [], []

    # Kirim data chart sebagai JSON string agar aman di JS
    ctx = {
        "request": request,
        "patients": patients,
        "total": total,
        "user": user,
        "q": q or "",
        "start": eff_start.isoformat() if eff_start else "",
        "end": eff_end.isoformat() if eff_end else "",
        "visits_labels": json.dumps(visits_labels),
        "visits_values": json.dumps(visits_values),
        "diag_labels": json.dumps(diag_labels),
        "diag_values": json.dumps(diag_values),
        "tind_labels": json.dumps(tind_labels),
        "tind_values": json.dumps(tind_values),
    }

    return templates.TemplateResponse("dashboard.html", ctx)

@router.get("/export.xlsx")
def export_excel(
    q: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Export mengikuti aturan filter yang sama:
    - Hanya start → end = hari ini
    - Start > end → ditukar
    - Nama / tanggal bisa salah satu saja
    - String kosong diabaikan (tidak 422)
    """
    s_start = _parse_date_q(start)
    s_end = _parse_date_q(end)

    eff_start = s_start
    eff_end = s_end
    if eff_start and not eff_end:
        eff_end = date.today()
    if eff_start and eff_end and eff_start > eff_end:
        eff_start, eff_end = eff_end, eff_start

    try:
        query = db.query(Patient)
        if q:
            query = query.filter(Patient.nama.ilike(f"%{q}%"))
        if eff_start:
            query = query.filter(Patient.tanggal_kunjungan >= eff_start)
        if eff_end:
            query = query.filter(Patient.tanggal_kunjungan <= eff_end)
        rows = query.all()
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Gagal mengambil data untuk export.")

    data = [{
        "ID": r.id,
        "Nama": r.nama,
        "Tanggal Lahir": r.tanggal_lahir.isoformat() if r.tanggal_lahir else None,
        "Tanggal Kunjungan": r.tanggal_kunjungan.isoformat() if r.tanggal_kunjungan else None,
        "Diagnosis": r.diagnosis,
        "Tindakan": r.tindakan,
        "Dokter": r.dokter,
    } for r in rows]

    output = io.BytesIO()
    try:
        df = pd.DataFrame(data)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Pasien")
        output.seek(0)
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal membuat file Excel.")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=laporan_pasien.xlsx"}
    )

@router.post("/import")
def import_patients(
    payload: Union[List[dict], dict] = Body(..., description="List pasien JSON, atau single dict"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Import dummy data pasien dari JSON via POST.
    - Terima list[dict] atau dict tunggal.
    - Minimal field: nama + tanggal_kunjungan (alias: name + visit_date).
    - Batasi maksimum 500 item agar tidak overload.
    - Hasil: ringkasan sukses & error per indeks.
    """
    items = payload if isinstance(payload, list) else [payload]

    MAX_ITEMS = 500
    if len(items) > MAX_ITEMS:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": f"Maksimal {MAX_ITEMS} item per import."},
        )

    created = 0
    errors: list[dict] = []

    def to_date(val):
        if val is None or val == "":
            return None
        try:
            return pd.to_datetime(val, errors="raise").date()
        except Exception:
            raise ValueError(f"Format tanggal tidak valid: {val}")

    try:
        for idx, item in enumerate(items):
            try:
                nama = (item.get("nama") or item.get("name") or "").strip()
                tgl_raw = item.get("tanggal_kunjungan") or item.get("visit_date")
                if not nama or not tgl_raw:
                    raise ValueError("Field minimal 'nama' dan 'tanggal_kunjungan/visit_date' wajib.")

                p = Patient(
                    nama=nama,
                    tanggal_kunjungan=to_date(tgl_raw),
                    tanggal_lahir=to_date(item.get("tanggal_lahir")),
                    diagnosis=(item.get("diagnosis") or None),
                    tindakan=(item.get("tindakan") or None),
                    dokter=(item.get("dokter") or None),
                )
                db.add(p)
                created += 1
            except Exception as e:
                errors.append({"index": idx, "error": str(e), "item": item})
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Gagal menyimpan data import ke database.")

    status_code = 200 if created and not errors else 207
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok", "created": created, "failed": len(errors), "errors": errors},
    )
