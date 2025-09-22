from datetime import date, datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..auth import get_db, get_current_user, require_role
from ..models import Patient, User

router = APIRouter(prefix="/patients")

def _doctor_choices(db: Session) -> List[str]:
    """Ambil daftar username semua user dengan role 'dokter'."""
    rows = db.query(User).filter(User.role == "dokter").order_by(User.username.asc()).all()
    # fallback: kalau kosong (mustahil di produksi), jangan bikin dropdown kosong
    return [u.username for u in rows] or []

def _render_form(
    request: Request,
    user: User,
    patient: Optional[Patient] = None,
    form: Optional[Dict[str, Any]] = None,
    errors: Optional[Dict[str, str]] = None,
    doctors: Optional[List[str]] = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render ulang form dengan nilai terakhir & pesan error per-field + daftar dokter."""
    from ..templates_engine import templates
    return templates.TemplateResponse(
        "patient_form.html",
        {
            "request": request,
            "patient": patient,
            "user": user,
            "form": form or {},
            "errors": errors or {},
            "doctors": doctors or [],
        },
        status_code=status_code,
    )

def _parse_date(s: Optional[str], field: str, errors: Dict[str, str], required: bool = False) -> Optional[date]:
    """Parse tanggal dari string 'YYYY-MM-DD'. Tulis error ke dict jika invalid."""
    if s is None or s == "":
        if required:
            errors[field] = "Wajib diisi."
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        errors[field] = "Format tanggal tidak valid (gunakan YYYY-MM-DD)."
        return None

@router.get("", response_class=HTMLResponse)
def list_patients(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from ..templates_engine import templates
    try:
        patients = db.query(Patient).order_by(Patient.tanggal_kunjungan.desc()).all()
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Gagal mengambil data pasien.")
    return templates.TemplateResponse("patients_list.html", {"request": request, "patients": patients, "user": user})

@router.get("/new", response_class=HTMLResponse)
def new_patient_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("dokter")),
):
    doctors = _doctor_choices(db)
    # jika daftar dokter kosong, set minimal ke user saat ini agar tidak kosong
    if user.username not in doctors:
        doctors = [user.username] + doctors
    return _render_form(request, user=user, patient=None, form={}, errors={}, doctors=doctors)

@router.post("/new")
def create_patient(
    request: Request,
    nama: str = Form(...),
    tanggal_lahir: Optional[str] = Form(None),        # terima string agar tidak 422
    tanggal_kunjungan: str = Form(...),               # terima string agar tidak 422
    diagnosis: Optional[str] = Form(None),
    tindakan: Optional[str] = Form(None),
    dokter: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("dokter"))
):
    doctors = _doctor_choices(db)
    if user.username not in doctors:
        doctors = [user.username] + doctors

    errors: Dict[str, str] = {}
    form_values = {
        "nama": (nama or "").strip(),
        "tanggal_lahir": (tanggal_lahir or "").strip(),
        "tanggal_kunjungan": (tanggal_kunjungan or "").strip(),
        "diagnosis": (diagnosis or "").strip(),
        "tindakan": (tindakan or "").strip(),
        "dokter": (dokter or "").strip(),
    }

    # Wajib
    if not form_values["nama"]:
        errors["nama"] = "Nama wajib diisi."
    if not form_values["diagnosis"]:
        errors["diagnosis"] = "Diagnosis wajib diisi."
    if not form_values["tindakan"]:
        errors["tindakan"] = "Tindakan wajib diisi."
    if not form_values["dokter"]:
        errors["dokter"] = "Dokter wajib dipilih."
    elif form_values["dokter"] not in doctors:
        errors["dokter"] = "Pilih dokter yang tersedia."

    # Tanggal
    tgl_lahir = _parse_date(form_values["tanggal_lahir"], "tanggal_lahir", errors, required=True)
    tgl_kunjungan = _parse_date(form_values["tanggal_kunjungan"], "tanggal_kunjungan", errors, required=True)

    if errors:
        return _render_form(request, user=user, patient=None, form=form_values, errors=errors, doctors=doctors, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        p = Patient(
            nama=form_values["nama"],
            tanggal_lahir=tgl_lahir,
            tanggal_kunjungan=tgl_kunjungan,  # type: ignore[arg-type]
            diagnosis=form_values["diagnosis"],
            tindakan=form_values["tindakan"],
            dokter=form_values["dokter"],
        )
        db.add(p)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        errors["__all__"] = "Gagal menyimpan data pasien."
        return _render_form(request, user=user, patient=None, form=form_values, errors=errors, doctors=doctors, status_code=500)

    return RedirectResponse(url="/patients", status_code=302)

@router.get("/{patient_id}/edit", response_class=HTMLResponse)
def edit_patient_form(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("dokter")),
):
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Data pasien tidak ditemukan.")
    doctors = _doctor_choices(db)
    if user.username not in doctors:
        doctors = [user.username] + doctors
    return _render_form(request, user=user, patient=p, form={}, errors={}, doctors=doctors)

@router.post("/{patient_id}/edit")
def update_patient(
    patient_id: int,
    nama: str = Form(...),
    tanggal_lahir: Optional[str] = Form(None),
    tanggal_kunjungan: str = Form(...),
    diagnosis: Optional[str] = Form(None),
    tindakan: Optional[str] = Form(None),
    dokter: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("dokter")),
):
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Data pasien tidak ditemukan.")

    doctors = _doctor_choices(db)
    if user.username not in doctors:
        doctors = [user.username] + doctors

    errors: Dict[str, str] = {}
    form_values = {
        "nama": (nama or "").strip(),
        "tanggal_lahir": (tanggal_lahir or "").strip(),
        "tanggal_kunjungan": (tanggal_kunjungan or "").strip(),
        "diagnosis": (diagnosis or "").strip(),
        "tindakan": (tindakan or "").strip(),
        "dokter": (dokter or "").strip(),
    }

    if not form_values["nama"]:
        errors["nama"] = "Nama wajib diisi."
    if not form_values["diagnosis"]:
        errors["diagnosis"] = "Diagnosis wajib diisi."
    if not form_values["tindakan"]:
        errors["tindakan"] = "Tindakan wajib diisi."
    if not form_values["dokter"]:
        errors["dokter"] = "Dokter wajib dipilih."
    elif form_values["dokter"] not in doctors:
        errors["dokter"] = "Pilih dokter yang tersedia."

    tgl_lahir = _parse_date(form_values["tanggal_lahir"], "tanggal_lahir", errors, required=True)
    tgl_kunjungan = _parse_date(form_values["tanggal_kunjungan"], "tanggal_kunjungan", errors, required=True)

    if errors:
        return _render_form(request, user=user, patient=p, form=form_values, errors=errors, doctors=doctors, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        p.nama = form_values["nama"]
        p.tanggal_lahir = tgl_lahir
        p.tanggal_kunjungan = tgl_kunjungan  # type: ignore[assignment]
        p.diagnosis = form_values["diagnosis"]
        p.tindakan = form_values["tindakan"]
        p.dokter = form_values["dokter"]
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        errors["__all__"] = "Gagal memperbarui data pasien."
        return _render_form(request, user=user, patient=p, form=form_values, errors=errors, doctors=doctors, status_code=500)

    return RedirectResponse(url="/patients", status_code=302)

@router.post("/{patient_id}/delete")
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("dokter")),
):
    p = db.get(Patient, patient_id)
    if not p:
        raise HTTPException(status_code=404, detail="Data pasien tidak ditemukan.")
    try:
        db.delete(p)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Gagal menghapus data pasien.")
    return RedirectResponse(url="/patients", status_code=302)
