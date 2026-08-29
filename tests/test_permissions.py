from dataclasses import dataclass, field
from typing import Iterable

from app.models.user import User, UserRole
from app.services import permissions


@dataclass
class FakeTicket:
    primary_assignee_id: int
    collaborator_ids: Iterable[int] = field(default_factory=list)


def make_user(user_id: int, role: UserRole) -> User:
    return User(id=user_id, email=f"user{user_id}@example.com", hashed_password="x", role=role)


def test_supervisor_can_view_any_ticket():
    supervisor = make_user(1, UserRole.SUPERVISOR)
    ticket = FakeTicket(primary_assignee_id=99)

    assert permissions.can_view_ticket(supervisor, ticket)


def test_agent_can_view_own_ticket():
    agent = make_user(2, UserRole.AGENT)
    ticket = FakeTicket(primary_assignee_id=2)

    assert permissions.can_view_ticket(agent, ticket)


def test_agent_can_view_ticket_as_collaborator():
    agent = make_user(3, UserRole.AGENT)
    ticket = FakeTicket(primary_assignee_id=99, collaborator_ids=[3])

    assert permissions.can_view_ticket(agent, ticket)


def test_agent_cannot_view_unrelated_ticket():
    agent = make_user(4, UserRole.AGENT)
    ticket = FakeTicket(primary_assignee_id=99, collaborator_ids=[100])

    assert not permissions.can_view_ticket(agent, ticket)


def test_agent_cannot_reassign_even_their_own_ticket():
    agent = make_user(5, UserRole.AGENT)
    ticket = FakeTicket(primary_assignee_id=5)

    assert not permissions.can_reassign_ticket(agent, ticket, new_assignee_id=6)


def test_supervisor_can_reassign_any_ticket():
    supervisor = make_user(1, UserRole.SUPERVISOR)
    ticket = FakeTicket(primary_assignee_id=99)

    assert permissions.can_reassign_ticket(supervisor, ticket, new_assignee_id=6)


def test_only_supervisor_can_close_ticket():
    supervisor = make_user(1, UserRole.SUPERVISOR)
    agent = make_user(2, UserRole.AGENT)
    ticket = FakeTicket(primary_assignee_id=2)

    assert permissions.can_close_ticket(supervisor, ticket)
    assert not permissions.can_close_ticket(agent, ticket)


def test_only_supervisor_can_view_full_queue():
    supervisor = make_user(1, UserRole.SUPERVISOR)
    agent = make_user(2, UserRole.AGENT)

    assert permissions.can_view_full_queue(supervisor)
    assert not permissions.can_view_full_queue(agent)
