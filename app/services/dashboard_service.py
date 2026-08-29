from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole
from app.services import sla_service
from app.services.ticket_service import matching_ticket_ids


def _week_start(moment: datetime) -> datetime:
    """Monday 00:00 UTC of the calendar week containing `moment`. Used for
    both "resolved this week" and the chart's weekly buckets, so the two
    numbers agree on what a week means."""
    day = moment.date() - timedelta(days=moment.weekday())
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _scope(viewer: User):
    """The same viewer-scoped id subquery used by the queue/search/export --
    supervisors see everything, agents see only their own assigned or
    collaborated tickets. No other filters applied."""
    return matching_ticket_ids(
        viewer,
        archived=False,
        search=None,
        status_filter=None,
        priority_filter=None,
        category_filter=None,
        assignee_id=None,
    )


def _count(db: Session, *conditions) -> int:
    return db.scalar(select(func.count()).where(*conditions)) or 0


def headline_counts(db: Session, viewer: User, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    week_start = _week_start(now)
    scope = _scope(viewer)

    open_count = _count(db, Ticket.id.in_(scope), Ticket.status == TicketStatus.OPEN)
    pending_count = _count(db, Ticket.id.in_(scope), Ticket.status == TicketStatus.PENDING)
    resolved_this_week = _count(
        db, Ticket.id.in_(scope), Ticket.resolved_at.is_not(None), Ticket.resolved_at >= week_start
    )

    active_tickets = list(
        db.scalars(
            select(Ticket).where(Ticket.id.in_(scope), Ticket.status.in_(sla_service.ACTIVE_STATUSES))
        )
    )
    breaching_count = sum(
        1
        for ticket in active_tickets
        if sla_service.elapsed_response_time_for_ticket(db, ticket, as_of=now)
        >= sla_service.TARGET_RESPONSE_TIME[ticket.priority]
    )

    return {
        "open": open_count,
        "pending": pending_count,
        "resolved_this_week": resolved_this_week,
        "breaching": breaching_count,
    }


def breakdown_by_status(db: Session, viewer: User) -> list[dict]:
    scope = _scope(viewer)
    stmt = (
        select(Ticket.status, func.count())
        .where(Ticket.id.in_(scope))
        .group_by(Ticket.status)
        .order_by(Ticket.status)
    )
    return [{"status": status, "count": count} for status, count in db.execute(stmt)]


def breakdown_by_agent(db: Session) -> list[dict]:
    """Every agent, including those with zero tickets right now -- a
    complete workload picture, not just the agents who happen to have one.
    Deliberately not viewer-scoped: this is the supervisor-only view."""
    stmt = (
        select(User.email, func.count(Ticket.id))
        .select_from(User)
        .outerjoin(
            Ticket,
            (Ticket.primary_assignee_id == User.id) & (Ticket.is_archived.is_(False)),
        )
        .where(User.role == UserRole.AGENT)
        .group_by(User.id, User.email)
        .order_by(User.email)
    )
    return [{"agent": email, "count": count} for email, count in db.execute(stmt)]


def resolved_per_week(db: Session, viewer: User, *, weeks: int = 8, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    current_week_start = _week_start(now)
    scope = _scope(viewer)

    buckets = []
    for offset in range(weeks - 1, -1, -1):
        start = current_week_start - timedelta(weeks=offset)
        end = start + timedelta(weeks=1)
        count = _count(
            db, Ticket.id.in_(scope), Ticket.resolved_at >= start, Ticket.resolved_at < end
        )
        buckets.append({"week_start": start.date().isoformat(), "count": count})
    return buckets
