from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.sla_acknowledgement import SlaAcknowledgement
from app.models.ticket import Ticket
from app.models.ticket_period import TicketClosedPeriod
from app.models.user import User
from app.services import permissions, sla_service
from app.services.ticket_service import matching_ticket_ids

# "Within a short window" of breaching -- documented in docs/decisions.md.
# A percentage of the target rather than a fixed duration, since targets
# range from 4h (urgent) to 72h (low) and a single fixed window wouldn't
# mean the same thing across priorities.
AT_RISK_THRESHOLD = 0.9


def _scope(viewer: User):
    return matching_ticket_ids(
        viewer,
        archived=False,
        search=None,
        status_filter=None,
        priority_filter=None,
        category_filter=None,
        assignee_id=None,
    )


def _alert_status(elapsed: timedelta, target: timedelta) -> str | None:
    if elapsed >= target:
        return "breaching"
    if elapsed >= target * AT_RISK_THRESHOLD:
        return "at_risk"
    return None


def current_breach_epoch(db: Session, ticket: Ticket) -> int:
    """How many times this ticket has been reopened from Closed so far.
    Derived from the existing TicketClosedPeriod log (goal 4), not a
    separately maintained counter that could drift out of sync with it."""
    return (
        db.scalar(
            select(func.count()).where(
                TicketClosedPeriod.ticket_id == ticket.id,
                TicketClosedPeriod.reopened_at.is_not(None),
            )
        )
        or 0
    )


def list_alerts(db: Session, viewer: User, *, now: datetime | None = None) -> list[dict]:
    """Per goal 1/5's viewer scoping: supervisors see every breaching/
    at-risk ticket, agents only their own assigned-or-collaborated ones.
    Reuses sla_service.ACTIVE_STATUSES and elapsed_response_time_for_ticket
    directly -- a Resolved/Closed ticket never appears here."""
    now = now or datetime.now(timezone.utc)
    scope = _scope(viewer)

    candidates = list(
        db.scalars(
            select(Ticket).where(Ticket.id.in_(scope), Ticket.status.in_(sla_service.ACTIVE_STATUSES))
        )
    )

    alerts = []
    for ticket in candidates:
        elapsed = sla_service.elapsed_response_time_for_ticket(db, ticket, as_of=now)
        target = sla_service.TARGET_RESPONSE_TIME[ticket.priority]
        alert_status = _alert_status(elapsed, target)
        if alert_status is None:
            continue

        epoch = current_breach_epoch(db, ticket)
        acknowledged = db.scalar(
            select(SlaAcknowledgement).where(
                SlaAcknowledgement.ticket_id == ticket.id,
                SlaAcknowledgement.user_id == viewer.id,
                SlaAcknowledgement.breach_epoch == epoch,
            )
        )
        if acknowledged is not None:
            continue

        alerts.append({"ticket": ticket, "status": alert_status, "elapsed": elapsed, "target": target})

    return alerts


def acknowledge_alert(db: Session, ticket: Ticket, actor: User) -> None:
    """Same rights as the primary assignee: assignee, collaborator, or
    supervisor -- reusing can_act_on_ticket rather than a parallel check."""
    if not permissions.can_act_on_ticket(actor, ticket):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only acknowledge alerts for tickets you're assigned to or collaborating on.",
        )

    epoch = current_breach_epoch(db, ticket)
    existing = db.scalar(
        select(SlaAcknowledgement).where(
            SlaAcknowledgement.ticket_id == ticket.id,
            SlaAcknowledgement.user_id == actor.id,
            SlaAcknowledgement.breach_epoch == epoch,
        )
    )
    if existing is not None:
        return

    db.add(SlaAcknowledgement(ticket_id=ticket.id, user_id=actor.id, breach_epoch=epoch))
    db.commit()
