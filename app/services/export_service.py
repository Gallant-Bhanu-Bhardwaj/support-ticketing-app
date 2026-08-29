import csv
import io

from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.services import sla_service

_COLUMNS = [
    "id",
    "subject",
    "requester",
    "assignee",
    "priority",
    "category",
    "status",
    "created_at",
    "updated_at",
    "breach_status",
]


def _breach_status(db: Session, ticket: Ticket) -> str:
    """Whether the ticket has breached its target response time, as of now.
    Only a yes/no breach column -- an "at-risk" warning window is goal 10's
    SLA-alert design to define, not something to pre-empt here."""
    elapsed = sla_service.elapsed_response_time_for_ticket(db, ticket)
    target = sla_service.TARGET_RESPONSE_TIME[ticket.priority]
    return "breaching" if elapsed >= target else "on_track"


def tickets_to_csv(db: Session, tickets: list[Ticket]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNS)
    for ticket in tickets:
        writer.writerow(
            [
                ticket.id,
                ticket.subject,
                ticket.requester,
                ticket.primary_assignee.email,
                ticket.priority.value,
                ticket.category.value,
                ticket.status.value,
                ticket.created_at.isoformat(),
                ticket.updated_at.isoformat(),
                _breach_status(db, ticket),
            ]
        )
    return buffer.getvalue()
