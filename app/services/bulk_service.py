from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.services import lifecycle_service, ticket_service


@dataclass
class BulkResult:
    ticket_id: int
    subject: str
    success: bool
    detail: str


def bulk_reassign(db: Session, ticket_ids: list[int], new_assignee_id: int, actor: User) -> list[BulkResult]:
    """Per-ticket outcome for a bulk reassignment. Each ticket goes through
    ticket_service.reassign_ticket -- the exact same can_act_on_ticket and
    can_reassign_ticket checks as the single-ticket edit path, not a
    separate bulk-specific rule. A failure on one ticket never rolls back
    or blocks the others: each is committed independently as it succeeds."""
    ticket_service.ensure_valid_assignee(db, new_assignee_id)

    results = []
    for ticket_id in ticket_ids:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            results.append(BulkResult(ticket_id, "(not found)", False, "Ticket not found."))
            continue

        try:
            ticket_service.reassign_ticket(db, ticket, new_assignee_id, actor)
        except HTTPException as exc:
            db.rollback()
            results.append(BulkResult(ticket_id, ticket.subject, False, exc.detail))
            continue

        results.append(BulkResult(ticket_id, ticket.subject, True, "Reassigned."))
    return results


def bulk_close(db: Session, ticket_ids: list[int], actor: User) -> list[BulkResult]:
    """Per-ticket outcome for a bulk close. Each ticket goes through
    lifecycle_service.transition to CLOSED -- the same can_act_on_ticket,
    can_close_ticket, and state-machine legality checks as closing one
    ticket at a time, so an already-closed (or not-yet-Resolved) ticket is
    refused with the same message a single-ticket attempt would get."""
    results = []
    for ticket_id in ticket_ids:
        ticket = db.get(Ticket, ticket_id)
        if ticket is None:
            results.append(BulkResult(ticket_id, "(not found)", False, "Ticket not found."))
            continue

        try:
            lifecycle_service.transition(db, ticket, TicketStatus.CLOSED, actor)
        except HTTPException as exc:
            db.rollback()
            results.append(BulkResult(ticket_id, ticket.subject, False, exc.detail))
            continue

        results.append(BulkResult(ticket_id, ticket.subject, True, "Closed."))
    return results
