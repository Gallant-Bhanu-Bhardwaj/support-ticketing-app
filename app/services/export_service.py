import csv
import io

from app.models.ticket import Ticket

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
]


def tickets_to_csv(tickets: list[Ticket]) -> str:
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
            ]
        )
    return buffer.getvalue()
