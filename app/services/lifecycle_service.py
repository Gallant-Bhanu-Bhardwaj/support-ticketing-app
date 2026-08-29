from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketStatus
from app.models.ticket_period import TicketClosedPeriod, TicketPendingPeriod
from app.models.user import User
from app.services import history_service, permissions

REOPEN_WINDOW = timedelta(days=7)

# Every legal move. Anything not listed here -- including same-status
# no-ops -- is rejected. Pending -> Open is manual only: a non-internal reply
# is not reliable evidence the customer actually replied, since every reply
# in this system is authored by an agent or supervisor.
ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW: {TicketStatus.OPEN},
    TicketStatus.OPEN: {TicketStatus.PENDING, TicketStatus.RESOLVED},
    TicketStatus.PENDING: {TicketStatus.OPEN},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED},
    TicketStatus.CLOSED: {TicketStatus.OPEN},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def transition(
    db: Session,
    ticket: Ticket,
    new_status: TicketStatus,
    actor: User,
    *,
    now: datetime | None = None,
) -> Ticket:
    now = now or _utcnow()
    current = ticket.status

    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change status on tickets you're assigned to or collaborating on.",
        )

    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move a ticket from {current.value} to {new_status.value}.",
        )

    if current == TicketStatus.RESOLVED and new_status == TicketStatus.CLOSED:
        if not permissions.can_close_ticket(actor, ticket):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a supervisor can close a ticket.",
            )
        db.add(TicketClosedPeriod(ticket_id=ticket.id, closed_at=now))

    if current == TicketStatus.CLOSED and new_status == TicketStatus.OPEN:
        closed_period = db.scalars(
            select(TicketClosedPeriod)
            .where(
                TicketClosedPeriod.ticket_id == ticket.id,
                TicketClosedPeriod.reopened_at.is_(None),
            )
        ).one()
        if now - closed_period.closed_at > REOPEN_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This ticket was closed more than {REOPEN_WINDOW.days} days ago "
                    "and can no longer be reopened."
                ),
            )
        closed_period.reopened_at = now

    if current == TicketStatus.OPEN and new_status == TicketStatus.PENDING:
        db.add(TicketPendingPeriod(ticket_id=ticket.id, started_at=now))

    if current == TicketStatus.PENDING and new_status == TicketStatus.OPEN:
        pending_period = db.scalars(
            select(TicketPendingPeriod)
            .where(
                TicketPendingPeriod.ticket_id == ticket.id,
                TicketPendingPeriod.ended_at.is_(None),
            )
        ).one()
        pending_period.ended_at = now

    if new_status == TicketStatus.RESOLVED:
        # Overwritten on each re-resolution (after a Closed -> Open ->
        # ... -> Resolved cycle) so it always reflects the most recent one.
        ticket.resolved_at = now

    history_service.record_status_change(db, ticket, current, new_status, actor)

    ticket.status = new_status
    db.commit()
    db.refresh(ticket)
    return ticket
