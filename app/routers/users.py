# app/routers/users.py
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import Dict, Any

from ..auth import get_db, get_current_user, require_role, get_password_hash
from ..models import User

router = APIRouter(prefix="/users")

def _render_form(request: Request, user: User, form: Dict[str, Any], errors: Dict[str, str], status_code: int = 200):
    from ..templates_engine import templates
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "form": form, "errors": errors},
        status_code=status_code,
    )

@router.get("", response_class=HTMLResponse)
def list_doctors(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Daftar akun role=dokter (hanya admin)."""
    from ..templates_engine import templates
    try:
        doctors = db.query(User).filter(User.role == "dokter").order_by(User.created_at.desc()).all()
    except SQLAlchemyError:
        doctors = []
    # tampilkan banner sukses jika ?created=1
    created = request.query_params.get("created") == "1"
    return templates.TemplateResponse(
        "users_list.html",
        {"request": request, "user": admin, "doctors": doctors, "created": created},
    )

@router.get("/new", response_class=HTMLResponse)
def new_user_form(
    request: Request,
    admin: User = Depends(require_role("admin")),
):
    return _render_form(
        request,
        user=admin,
        form={"username": "", "password": "", "password2": ""},
        errors={}
    )

@router.post("/new")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Buat akun role=dokter (hanya admin)."""
    form = {
        "username": (username or "").strip(),
        "password": password or "",
        "password2": password2 or "",
    }
    errors: Dict[str, str] = {}

    # Validasi sederhana
    if not form["username"]:
        errors["username"] = "Username wajib diisi."
    elif len(form["username"]) < 3:
        errors["username"] = "Minimal 3 karakter."

    if not form["password"]:
        errors["password"] = "Password wajib diisi."
    elif len(form["password"]) < 6:
        errors["password"] = "Minimal 6 karakter."

    if form["password2"] != form["password"]:
        errors["password2"] = "Konfirmasi password tidak sama."

    # Cek duplikasi username
    if not errors:
        if db.query(User).filter(User.username == form["username"]).first():
            errors["username"] = "Username sudah dipakai."

    if errors:
        return _render_form(request, user=admin, form=form, errors=errors, status_code=status.HTTP_400_BAD_REQUEST)

    # Simpan
    try:
        u = User(
            username=form["username"],
            password_hash=get_password_hash(form["password"]),
            role="dokter",
        )
        db.add(u)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        errors["__all__"] = "Gagal membuat akun. Coba lagi."
        return _render_form(request, user=admin, form=form, errors=errors, status_code=500)

    return RedirectResponse(url="/users?created=1", status_code=302)
