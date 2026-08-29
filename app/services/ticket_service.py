from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.schemas.ticket import TicketWrite


def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


def list_tickets(db: Session, *, archived: bool) -> list[Ticket]:
    stmt = (
        select(Ticket)
        .where(Ticket.is_archived == archived)
        .order_by(Ticket.created_at.desc())
    )
    return list(db.scalars(stmt))


def create_ticket(db: Session, data: TicketWrite) -> Ticket:
    ticket = Ticket(**data.model_dump())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket(db: Session, ticket: Ticket, data: TicketWrite) -> Ticket:
    for field, value in data.model_dump().items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return ticket


def archive_ticket(db: Session, ticket: Ticket) -> Ticket:
    ticket.is_archived = True
    db.commit()
    db.refresh(ticket)
    return ticket


def restore_ticket(db: Session, ticket: Ticket) -> Ticket:
    ticket.is_archived = False
    db.commit()
    db.refresh(ticket)
    return ticket
