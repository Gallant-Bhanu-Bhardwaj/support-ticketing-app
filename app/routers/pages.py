from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_current_user, require_role
from app.core.templates import templates
from app.models.user import User, UserRole

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "protected.html",
        {"current_user": current_user, "heading": "Dashboard"},
    )


@router.get("/admin")
def admin_area(request: Request, current_user: User = Depends(require_role(UserRole.SUPERVISOR))):
    return templates.TemplateResponse(
        request,
        "protected.html",
        {"current_user": current_user, "heading": "Supervisor area"},
    )
