from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.collaborator import CollaboratorAdd
from app.services import collaborator_service, ticket_service

router = APIRouter(prefix="/tickets/{ticket_id}/collaborators", tags=["collaborators"])


@router.post("")
def add_collaborator(
    ticket_id: int,
    data: Annotated[CollaboratorAdd, Form()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    collaborator_service.add_collaborator(db, ticket, data.user_id, current_user)
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@router.post("/{user_id}/remove")
def remove_collaborator(
    ticket_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = ticket_service.get_ticket_or_404(db, ticket_id)
    collaborator_service.remove_collaborator(db, ticket, user_id, current_user)
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)
