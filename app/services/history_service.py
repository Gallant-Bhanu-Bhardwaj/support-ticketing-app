"""Append-only writes for the ticket timeline.

Deliberately creation functions only. There is no update_* or delete_*
here, and there must never be one -- every timeline row is a side effect
of a real action (a status transition, a reassignment, a reply) recorded
in the same transaction as that action, never editable afterward by
anyone, including a supervisor.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reply import Reply
from app.models.ticket import Ticket, TicketStatus
from app.models.ticket_history import TicketHistoryEvent, TicketHistoryEventType
from app.models.user import User


def record_status_change(
    db: Session, ticket: Ticket, old_status: TicketStatus, new_status: TicketStatus, actor: User
) -> TicketHistoryEvent:
    event = TicketHistoryEvent(
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type=TicketHistoryEventType.STATUS_CHANGE,
        old_status=old_status,
        new_status=new_status,
    )
    db.add(event)
    return event


def record_reassignment(
    db: Session, ticket: Ticket, old_assignee_id: int, new_assignee_id: int, actor: User
) -> TicketHistoryEvent:
    event = TicketHistoryEvent(
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type=TicketHistoryEventType.REASSIGNMENT,
        old_assignee_id=old_assignee_id,
        new_assignee_id=new_assignee_id,
    )
    db.add(event)
    return event


def record_reply(db: Session, ticket: Ticket, reply: Reply, actor: User) -> TicketHistoryEvent:
    event = TicketHistoryEvent(
        ticket_id=ticket.id,
        actor_id=actor.id,
        event_type=TicketHistoryEventType.REPLY,
        reply_id=reply.id,
    )
    db.add(event)
    return event


def list_timeline(db: Session, ticket_id: int) -> list[TicketHistoryEvent]:
    stmt = (
        select(TicketHistoryEvent)
        .where(TicketHistoryEvent.ticket_id == ticket_id)
        .order_by(TicketHistoryEvent.created_at, TicketHistoryEvent.id)
    )
    return list(db.scalars(stmt))
