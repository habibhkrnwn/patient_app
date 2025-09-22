from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..auth import get_db, verify_password, create_access_token
from ..models import User

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    from ..templates_engine import templates
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login")
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from ..templates_engine import templates
    try:
        user = db.query(User).filter(User.username == username).first()
    except SQLAlchemyError:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Gagal mengakses database. Coba lagi."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Username atau password salah."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    token = create_access_token({"sub": user.username})
    resp = RedirectResponse(url="/dashboard", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax")
    return resp

@router.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp
