from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.models.ticket_collaborator import TicketCollaborator
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.services import history_service, permissions

# low/normal/high/urgent are stored as strings; sorting by the column
# directly would order them alphabetically (high, low, normal, urgent),
# not by actual severity. This maps each to a rank for real severity order.
_PRIORITY_RANK = case(
    (Ticket.priority == TicketPriority.LOW, 1),
    (Ticket.priority == TicketPriority.NORMAL, 2),
    (Ticket.priority == TicketPriority.HIGH, 3),
    (Ticket.priority == TicketPriority.URGENT, 4),
)

_SORT_COLUMNS = {
    "created": Ticket.created_at,
    "updated": Ticket.updated_at,
    "priority": _PRIORITY_RANK,
}

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


def get_editable_ticket_or_404(db: Session, ticket_id: int, actor: User) -> Ticket:
    """For GET /tickets/{id}/edit: no reason to hand back a pre-filled form
    for a ticket the actor couldn't actually submit changes to anyway."""
    ticket = get_ticket_or_404(db, ticket_id)
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)
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


def matching_ticket_ids(
    viewer: User,
    *,
    archived: bool,
    search: str | None,
    status_filter: TicketStatus | None,
    priority_filter: TicketPriority | None,
    category_filter: TicketCategory | None,
    assignee_id: int | None,
):
    """The scoped+filtered id subquery shared by search_tickets (paginated,
    for the queue page), all_matching_tickets (unpaginated, for CSV export),
    and dashboard_service's aggregates -- one place filter/scope logic
    lives, not several."""
    conditions = [Ticket.is_archived == archived]

    if not permissions.can_view_full_queue(viewer):
        conditions.append(
            or_(
                Ticket.primary_assignee_id == viewer.id,
                TicketCollaborator.user_id == viewer.id,
            )
        )

    if search:
        pattern = f"%{search}%"
        conditions.append(or_(Ticket.subject.ilike(pattern), Ticket.description.ilike(pattern)))

    if status_filter is not None:
        conditions.append(Ticket.status == status_filter)
    if priority_filter is not None:
        conditions.append(Ticket.priority == priority_filter)
    if category_filter is not None:
        conditions.append(Ticket.category == category_filter)
    if assignee_id is not None:
        conditions.append(Ticket.primary_assignee_id == assignee_id)

    return (
        select(Ticket.id)
        .outerjoin(TicketCollaborator, TicketCollaborator.ticket_id == Ticket.id)
        .where(*conditions)
        .distinct()
    )


def search_tickets(
    db: Session,
    viewer: User,
    *,
    archived: bool = False,
    search: str | None = None,
    status_filter: TicketStatus | None = None,
    priority_filter: TicketPriority | None = None,
    category_filter: TicketCategory | None = None,
    assignee_id: int | None = None,
    sort: Literal["created", "priority", "updated"] = "created",
    direction: Literal["asc", "desc"] = "desc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Ticket], int]:
    """The queue with search/filter/sort/pagination, narrowed within the same
    viewer scope as list_tickets/list_my_tickets -- supervisors search
    everything, agents only ever search their own assigned/collaborated
    tickets, even when a search term would otherwise match someone else's."""
    matching_ids = matching_ticket_ids(
        viewer,
        archived=archived,
        search=search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        category_filter=category_filter,
        assignee_id=assignee_id,
    )

    total = db.scalar(select(func.count()).select_from(matching_ids.subquery())) or 0

    sort_column = _SORT_COLUMNS[sort]
    order = sort_column.asc() if direction == "asc" else sort_column.desc()

    page_stmt = (
        select(Ticket)
        .where(Ticket.id.in_(matching_ids))
        .order_by(order, Ticket.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    tickets = list(db.scalars(page_stmt))
    return tickets, total


def all_matching_tickets(
    db: Session,
    viewer: User,
    *,
    archived: bool = False,
    search: str | None = None,
    status_filter: TicketStatus | None = None,
    priority_filter: TicketPriority | None = None,
    category_filter: TicketCategory | None = None,
    assignee_id: int | None = None,
    sort: Literal["created", "priority", "updated"] = "created",
    direction: Literal["asc", "desc"] = "desc",
) -> list[Ticket]:
    """Every ticket matching the same scope+filters as search_tickets, with
    no pagination -- for CSV export of the current filtered view, which
    must reflect the whole filtered set, not just the visible page."""
    matching_ids = matching_ticket_ids(
        viewer,
        archived=archived,
        search=search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        category_filter=category_filter,
        assignee_id=assignee_id,
    )

    sort_column = _SORT_COLUMNS[sort]
    order = sort_column.asc() if direction == "asc" else sort_column.desc()

    stmt = select(Ticket).where(Ticket.id.in_(matching_ids)).order_by(order, Ticket.id.desc())
    return list(db.scalars(stmt))


def ensure_valid_assignee(db: Session, assignee_id: int) -> None:
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

    ensure_valid_assignee(db, assignee_id)

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


def _apply_reassignment(db: Session, ticket: Ticket, new_assignee_id: int, actor: User) -> None:
    """Mutates ticket.primary_assignee_id in place if permitted; does not
    commit. Shared by update_ticket and reassign_ticket (bulk's per-ticket
    path) so both go through the exact same check, not two copies of it."""
    if new_assignee_id == ticket.primary_assignee_id:
        return
    if not permissions.can_reassign_ticket(actor, ticket, new_assignee_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a supervisor can reassign a ticket.",
        )
    ensure_valid_assignee(db, new_assignee_id)
    history_service.record_reassignment(db, ticket, ticket.primary_assignee_id, new_assignee_id, actor)
    ticket.primary_assignee_id = new_assignee_id


def update_ticket(db: Session, ticket: Ticket, data: TicketUpdate, actor: User) -> Ticket:
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    _apply_reassignment(db, ticket, data.primary_assignee_id, actor)

    ticket.subject = data.subject
    ticket.description = data.description
    ticket.requester = data.requester
    ticket.priority = data.priority
    ticket.category = data.category
    db.commit()
    db.refresh(ticket)
    return ticket


def reassign_ticket(db: Session, ticket: Ticket, new_assignee_id: int, actor: User) -> Ticket:
    """Used by bulk reassign: the exact same per-ticket authorization checks
    as update_ticket's reassignment path (can_act_on_ticket, then
    can_reassign_ticket), just without the rest of TicketUpdate's fields."""
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED_DETAIL)

    _apply_reassignment(db, ticket, new_assignee_id, actor)
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
