from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from fastapi.responses import Response
import base64
from .database import Base, engine, SessionLocal
from .models import User
from .routers import patients as patients_router
from .routers import auth as auth_router
from .routers import dashboard as dashboard_router
from .routers import users as users_router

# --- Logging dasar ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("patients-app")

app = FastAPI(title="Patients App")
# Favicon kecil 1x1 (clear pixel) supaya browser tidak spam error
_CLEAR_ICO = base64.b64decode(
    b'AAABAAEAEBAAAAAAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAGAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    b'AAAAAAAAAAAA////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
)

@app.get("/favicon.ico")
def favicon():
    return Response(content=_CLEAR_ICO, media_type="image/x-icon")
def wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept.lower()

def render_error_page(request: Request, status_code: int, message: str) -> HTMLResponse:
    # render template error.html jika user minta HTML, else JSON
    if wants_html(request):
        from .templates_engine import templates
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": status_code, "message": message},
            status_code=status_code,
        )
    return JSONResponse(status_code=status_code, content={"detail": message})

# --- Exception Handlers ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # 401: redirect ke login untuk UX lebih baik (khusus permintaan HTML)
    if exc.status_code == 401 and wants_html(request):
        return RedirectResponse(url="/login", status_code=302)
    # lain-lain: render error page / JSON
    return render_error_page(request, exc.status_code, str(exc.detail))

@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 401: redirect ke login (HTML)
    if exc.status_code == 401 and wants_html(request):
        return RedirectResponse(url="/login", status_code=302)
    # 404/403/dst
    return render_error_page(request, exc.status_code, str(exc.detail))

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # 422 karena input user/ form salah
    log.warning("Validation error: %s", exc.errors())
    msg = "Input tidak valid. Mohon cek kembali isian/form Anda."
    return render_error_page(request, 422, msg)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Catch-all supaya tidak bocor stack trace ke user
    log.exception("Unhandled error: %s", exc)
    msg = "Terjadi kesalahan tak terduga di server."
    return render_error_page(request, 500, msg)

# --- Startup: create tables & seed user demo ---
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy.orm import Session
    from .auth import get_password_hash
    db: Session = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(username="admin", password_hash=get_password_hash("admin123"), role="admin"))
        if not db.query(User).filter(User.username == "dokter").first():
            db.add(User(username="dokter", password_hash=get_password_hash("dokter123"), role="dokter"))
        db.commit()
    finally:
        db.close()

# --- Routers ---
app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(patients_router.router)
app.include_router(users_router.router) 
