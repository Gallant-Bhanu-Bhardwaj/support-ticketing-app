from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_user_optional
from app.core.templates import templates
from app.models.user import User
from app.services import alerts_service, ticket_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    alerts = alerts_service.list_alerts(db, current_user)
    return templates.TemplateResponse(request, "alerts.html", {"alerts": alerts})


@router.get("/count")
def alerts_count(
    db: Session = Depends(get_db), current_user: User | None = Depends(get_current_user_optional)
):
    if current_user is None:
        return HTMLResponse("")
    count = len(alerts_service.list_alerts(db, current_user))
    if not count:
        return HTMLResponse("")
    return HTMLResponse(f'<span class="badge text-bg-danger">{count}</span>')


@router.post("/{ticket_id}/acknowledge")
def acknowledge(
    ticket_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    alerts_service.acknowledge_alert(db, ticket, current_user)
    return RedirectResponse(url="/alerts", status_code=303)
