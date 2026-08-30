from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.services import dashboard_service, permissions

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    headlines = dashboard_service.headline_counts(db, current_user)
    status_breakdown = dashboard_service.breakdown_by_status(db, current_user)
    agent_breakdown = (
        dashboard_service.breakdown_by_agent(db)
        if permissions.can_view_full_queue(current_user)
        else None
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "headlines": headlines,
            "status_breakdown": status_breakdown,
            "agent_breakdown": agent_breakdown,
        },
    )


@router.get("/chart-data")
def chart_data(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return dashboard_service.resolved_per_week(db, current_user)
