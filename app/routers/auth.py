from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import ACCESS_TOKEN_COOKIE
from app.core.security import create_access_token, verify_password
from app.core.templates import templates
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password"},
            status_code=401,
        )

    token = create_access_token(subject=user.email)
    redirect = RedirectResponse(url="/dashboard", status_code=303)
    redirect.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return redirect


@router.post("/logout")
def logout():
    redirect = RedirectResponse(url="/auth/login", status_code=303)
    redirect.delete_cookie(ACCESS_TOKEN_COOKIE)
    return redirect
