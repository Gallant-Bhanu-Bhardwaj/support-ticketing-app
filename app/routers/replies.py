from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.reply import ReplyCreate
from app.services import reply_service, ticket_service

router = APIRouter(prefix="/tickets/{ticket_id}/replies", tags=["replies"])


@router.post("")
def create_reply(
    ticket_id: int,
    reply_in: Annotated[ReplyCreate, Form()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    reply_service.add_reply(db, ticket, current_user, reply_in)
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)
