from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.services import permissions

_ACCESS_DENIED_DETAIL = (
    "You can only manage collaborators on tickets you're assigned to or collaborating on."
)


def available_agents_for_ticket(db: Session, ticket: Ticket) -> list[User]:
    """Agents not already the primary assignee or an existing collaborator."""
    excluded_ids = {ticket.primary_assignee_id, *ticket.collaborator_ids}
    stmt = (
        select(User)
        .where(User.role == UserRole.AGENT, User.id.notin_(excluded_ids))
        .order_by(User.email)
    )
    return list(db.scalars(stmt))


def add_collaborator(db: Session, ticket: Ticket, user_id: int, actor: User) -> Ticket:
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    if user_id == ticket.primary_assignee_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already the primary assignee.",
        )
    if user_id in ticket.collaborator_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already a collaborator on this ticket.",
        )

    user = db.get(User, user_id)
    if user is None or user.role != UserRole.AGENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Collaborators must be an existing agent.",
        )

    ticket.collaborators.append(user)
    db.commit()
    db.refresh(ticket)
    return ticket


def remove_collaborator(db: Session, ticket: Ticket, user_id: int, actor: User) -> Ticket:
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    if user_id not in ticket.collaborator_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This user is not a collaborator on this ticket.",
        )

    ticket.collaborators = [user for user in ticket.collaborators if user.id != user_id]
    db.commit()
    db.refresh(ticket)
    return ticket
