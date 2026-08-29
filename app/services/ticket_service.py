from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.models.ticket_collaborator import TicketCollaborator
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services import permissions

_ACCESS_DENIED_DETAIL = "You can only act on tickets you're assigned to or collaborating on."
_VIEW_DENIED_DETAIL = "You can only view tickets you're assigned to or collaborating on."


def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


def get_viewable_ticket_or_404(db: Session, ticket_id: int, viewer: User) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id)
    if not permissions.can_view_ticket(viewer, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_VIEW_DENIED_DETAIL)
    return ticket


def list_tickets(db: Session, *, archived: bool, viewer: User) -> list[Ticket]:
    """The base queue. Per goal 1: supervisors see everything, agents see
    only tickets where they're primary assignee or a collaborator."""
    if not permissions.can_view_full_queue(viewer):
        return list_my_tickets(db, viewer.id, archived=archived)

    stmt = (
        select(Ticket)
        .where(Ticket.is_archived == archived)
        .order_by(Ticket.created_at.desc())
    )
    return list(db.scalars(stmt))


def list_my_tickets(db: Session, user_id: int, *, archived: bool = False) -> list[Ticket]:
    """Every ticket where the user is primary assignee OR a collaborator."""
    stmt = (
        select(Ticket)
        .outerjoin(TicketCollaborator, TicketCollaborator.ticket_id == Ticket.id)
        .where(
            Ticket.is_archived == archived,
            or_(
                Ticket.primary_assignee_id == user_id,
                TicketCollaborator.user_id == user_id,
            ),
        )
        .distinct()
        .order_by(Ticket.created_at.desc())
    )
    return list(db.scalars(stmt))


def _ensure_valid_assignee(db: Session, assignee_id: int) -> None:
    assignee = db.get(User, assignee_id)
    if assignee is None or assignee.role != UserRole.AGENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A ticket's primary assignee must be an existing agent.",
        )


def create_ticket(db: Session, data: TicketCreate, actor: User) -> Ticket:
    if permissions.is_supervisor(actor):
        if data.primary_assignee_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Choose an agent to assign this ticket to.",
            )
        assignee_id = data.primary_assignee_id
    elif data.primary_assignee_id is not None and data.primary_assignee_id != actor.id:
        # Agents can never assign a ticket to anyone but themselves, even at
        # creation. Per goal 1, this must be rejected with a clear error,
        # not silently overridden to self.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents can only create tickets assigned to themselves.",
        )
    else:
        assignee_id = actor.id

    _ensure_valid_assignee(db, assignee_id)

    ticket = Ticket(
        subject=data.subject,
        description=data.description,
        requester=data.requester,
        priority=data.priority,
        category=data.category,
        primary_assignee_id=assignee_id,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket(db: Session, ticket: Ticket, data: TicketUpdate, actor: User) -> Ticket:
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    if data.primary_assignee_id != ticket.primary_assignee_id:
        if not permissions.can_reassign_ticket(actor, ticket, data.primary_assignee_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a supervisor can reassign a ticket.",
            )
        _ensure_valid_assignee(db, data.primary_assignee_id)
        ticket.primary_assignee_id = data.primary_assignee_id

    ticket.subject = data.subject
    ticket.description = data.description
    ticket.requester = data.requester
    ticket.priority = data.priority
    ticket.category = data.category
    db.commit()
    db.refresh(ticket)
    return ticket


def archive_ticket(db: Session, ticket: Ticket, actor: User) -> Ticket:
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    ticket.is_archived = True
    db.commit()
    db.refresh(ticket)
    return ticket


def restore_ticket(db: Session, ticket: Ticket, actor: User) -> Ticket:
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    ticket.is_archived = False
    db.commit()
    db.refresh(ticket)
    return ticket
