from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketPriority
from app.models.ticket_period import TicketClosedPeriod, TicketPendingPeriod

# Documented in docs/decisions.md.
TARGET_RESPONSE_TIME: dict[TicketPriority, timedelta] = {
    TicketPriority.URGENT: timedelta(hours=4),
    TicketPriority.HIGH: timedelta(hours=8),
    TicketPriority.NORMAL: timedelta(hours=24),
    TicketPriority.LOW: timedelta(hours=72),
}


def _excluded_duration(started_at: datetime, ended_at: datetime | None, as_of: datetime) -> timedelta:
    """Length of a period, clipped to `as_of` if it's still open (or if `as_of`
    falls inside it) so an ongoing Pending/Closed span is never over-excluded."""
    end = ended_at if ended_at is not None and ended_at < as_of else as_of
    if end <= started_at:
        return timedelta(0)
    return end - started_at


def elapsed_response_time(
    created_at: datetime,
    pending_periods: list[tuple[datetime, datetime | None]],
    closed_periods: list[tuple[datetime, datetime | None]],
    as_of: datetime,
) -> timedelta:
    """Time actually counted against the response-time SLA: wall-clock time
    since creation, minus every stretch spent in Pending (waiting on the
    customer) or Closed (done, then reopened) -- both excluded the same way,
    from a log of periods rather than a paused-in-memory timer."""
    total = as_of - created_at

    for started_at, ended_at in pending_periods:
        total -= _excluded_duration(started_at, ended_at, as_of)

    for closed_at, reopened_at in closed_periods:
        total -= _excluded_duration(closed_at, reopened_at, as_of)

    return max(total, timedelta(0))


def elapsed_response_time_for_ticket(
    db: Session, ticket: Ticket, *, as_of: datetime | None = None
) -> timedelta:
    as_of = as_of or datetime.now(timezone.utc)

    pending_periods = [
        (period.started_at, period.ended_at)
        for period in db.scalars(
            select(TicketPendingPeriod).where(TicketPendingPeriod.ticket_id == ticket.id)
        )
    ]
    closed_periods = [
        (period.closed_at, period.reopened_at)
        for period in db.scalars(
            select(TicketClosedPeriod).where(TicketClosedPeriod.ticket_id == ticket.id)
        )
    ]

    return elapsed_response_time(ticket.created_at, pending_periods, closed_periods, as_of)
