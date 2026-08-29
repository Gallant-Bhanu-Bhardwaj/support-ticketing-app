from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.models.ticket_period import TicketClosedPeriod, TicketPendingPeriod
from app.services import lifecycle_service

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)

VALID_TICKET = {
    "subject": "Route test ticket",
    "description": "desc",
    "requester": "req@example.com",
    "priority": "normal",
    "category": "bug",
}


def make_ticket(db_session, priority=TicketPriority.NORMAL, created_at=T0):
    ticket = Ticket(
        subject="Test ticket",
        description="desc",
        requester="req@example.com",
        priority=priority,
        category=TicketCategory.BUG,
        status=TicketStatus.NEW,
        created_at=created_at,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def create_ticket_via_route(client):
    response = client.post("/tickets", data=VALID_TICKET, follow_redirects=False)
    return int(response.headers["location"].rstrip("/").split("/")[-1])


# -- legal transitions --------------------------------------------------


def test_new_to_open_succeeds(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    assert ticket.status == TicketStatus.OPEN


def test_open_to_pending_succeeds_and_records_period(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.PENDING, agent_user, now=T0 + timedelta(hours=1)
    )

    assert ticket.status == TicketStatus.PENDING
    period = db_session.query(TicketPendingPeriod).filter_by(ticket_id=ticket.id).one()
    assert period.started_at == T0 + timedelta(hours=1)
    assert period.ended_at is None


def test_pending_to_open_succeeds_and_closes_period(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.PENDING, agent_user, now=T0 + timedelta(hours=1)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, agent_user, now=T0 + timedelta(hours=3)
    )

    assert ticket.status == TicketStatus.OPEN
    period = db_session.query(TicketPendingPeriod).filter_by(ticket_id=ticket.id).one()
    assert period.ended_at == T0 + timedelta(hours=3)


def test_open_to_resolved_succeeds(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0 + timedelta(hours=1)
    )
    assert ticket.status == TicketStatus.RESOLVED


def test_resolved_to_closed_succeeds_for_supervisor(db_session, supervisor_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, supervisor_user, now=T0 + timedelta(hours=1)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=T0 + timedelta(hours=2)
    )

    assert ticket.status == TicketStatus.CLOSED
    period = db_session.query(TicketClosedPeriod).filter_by(ticket_id=ticket.id).one()
    assert period.closed_at == T0 + timedelta(hours=2)
    assert period.reopened_at is None


def test_closed_to_open_succeeds_within_window(db_session, supervisor_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, supervisor_user, now=T0 + timedelta(hours=1)
    )
    closed_time = T0 + timedelta(hours=2)
    lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=closed_time)

    reopen_time = closed_time + timedelta(days=6)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=reopen_time)

    assert ticket.status == TicketStatus.OPEN
    period = db_session.query(TicketClosedPeriod).filter_by(ticket_id=ticket.id).one()
    assert period.reopened_at == reopen_time


# -- illegal transitions --------------------------------------------------


@pytest.mark.parametrize(
    "to_status",
    [TicketStatus.PENDING, TicketStatus.RESOLVED, TicketStatus.CLOSED],
)
def test_illegal_transitions_from_new_are_rejected(db_session, agent_user, to_status):
    ticket = make_ticket(db_session)

    with pytest.raises(HTTPException) as exc_info:
        lifecycle_service.transition(db_session, ticket, to_status, agent_user, now=T0)

    assert exc_info.value.status_code == 409
    assert "cannot move a ticket" in exc_info.value.detail.lower()
    assert ticket.status == TicketStatus.NEW


def test_illegal_transition_open_to_closed_skipping_resolved(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)

    with pytest.raises(HTTPException) as exc_info:
        lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, agent_user, now=T0)

    assert exc_info.value.status_code == 409
    assert "open to closed" in exc_info.value.detail.lower()
    assert ticket.status == TicketStatus.OPEN


def test_illegal_transition_resolved_to_open_rejected(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0)

    with pytest.raises(HTTPException) as exc_info:
        lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)

    assert exc_info.value.status_code == 409
    assert ticket.status == TicketStatus.RESOLVED


def test_same_status_transition_rejected(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)

    with pytest.raises(HTTPException) as exc_info:
        lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)

    assert exc_info.value.status_code == 409


def test_closed_to_open_rejected_past_window(db_session, supervisor_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, supervisor_user, now=T0 + timedelta(hours=1)
    )
    closed_time = T0 + timedelta(hours=2)
    lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=closed_time)

    too_late = closed_time + timedelta(days=8)
    with pytest.raises(HTTPException) as exc_info:
        lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=too_late)

    assert exc_info.value.status_code == 409
    assert "closed more than 7 days ago" in exc_info.value.detail
    assert ticket.status == TicketStatus.CLOSED


def test_agent_cannot_close_ticket(db_session, agent_user):
    ticket = make_ticket(db_session)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0)

    with pytest.raises(HTTPException) as exc_info:
        lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, agent_user, now=T0)

    assert exc_info.value.status_code == 403
    assert "supervisor" in exc_info.value.detail.lower()
    assert ticket.status == TicketStatus.RESOLVED


# -- server-level enforcement (via the actual route) ------------------------


def test_illegal_transition_rejected_by_server_with_message(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket_via_route(client)

    response = client.post(f"/tickets/{ticket_id}/status", data={"new_status": "closed"})

    assert response.status_code == 409
    assert "cannot move a ticket from new to closed" in response.text.lower()


def test_agent_cannot_close_ticket_via_route(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket_via_route(client)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "resolved"}, follow_redirects=False)

    response = client.post(f"/tickets/{ticket_id}/status", data={"new_status": "closed"})

    assert response.status_code == 403
    assert "supervisor" in response.text.lower()


def test_reply_while_pending_does_not_auto_transition_to_open(client, agent_user, login_as, db_session):
    """Regression test: a non-internal reply must NOT resume the clock on its
    own -- every reply is authored by an agent/supervisor, not the customer,
    so it's not reliable evidence the customer actually replied."""
    login_as(agent_user)
    ticket_id = create_ticket_via_route(client)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "pending"}, follow_redirects=False)

    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Following up while we wait on the customer."},
        follow_redirects=False,
    )

    ticket = db_session.query(Ticket).filter_by(id=ticket_id).one()
    assert ticket.status == TicketStatus.PENDING
