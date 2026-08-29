"""Ticket authorization rules, shared by every route/service that touches a ticket.

Written against a structural TicketLike protocol rather than importing the
Ticket model directly; app.models.ticket.Ticket satisfies it via a real
primary_assignee_id column and a collaborator_ids property.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from app.models.user import User, UserRole


class TicketLike(Protocol):
    primary_assignee_id: int
    collaborator_ids: Iterable[int]


def is_supervisor(user: User) -> bool:
    return user.role == UserRole.SUPERVISOR


def is_assigned_to(user: User, ticket: TicketLike) -> bool:
    return ticket.primary_assignee_id == user.id or user.id in set(ticket.collaborator_ids)


def can_view_full_queue(user: User) -> bool:
    """Whether the user can see every ticket, not just their own."""
    return is_supervisor(user)


def can_view_ticket(user: User, ticket: TicketLike) -> bool:
    return is_supervisor(user) or is_assigned_to(user, ticket)


def can_act_on_ticket(user: User, ticket: TicketLike) -> bool:
    """Reply to, or change the status of, a ticket."""
    return is_supervisor(user) or is_assigned_to(user, ticket)


def can_reassign_ticket(user: User, ticket: TicketLike, new_assignee_id: int) -> bool:
    """Change the primary assignee. Only supervisors may do this -- agents may
    never reassign a ticket, including away from themselves."""
    return is_supervisor(user)


def can_close_ticket(user: User, ticket: TicketLike) -> bool:
    return is_supervisor(user)
