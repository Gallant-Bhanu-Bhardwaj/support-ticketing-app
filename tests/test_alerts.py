from datetime import datetime, timedelta, timezone

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.services import alerts_service, lifecycle_service

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_ticket(db_session, assignee, **overrides):
    defaults = dict(
        subject="Default subject",
        description="Default description",
        requester="req@example.com",
        priority=TicketPriority.URGENT,  # 4h target -- easy to breach with small offsets
        category=TicketCategory.BUG,
        status=TicketStatus.OPEN,
        primary_assignee_id=assignee.id,
        created_at=T0,
    )
    defaults.update(overrides)
    ticket = Ticket(**defaults)
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def alert_ticket_ids(alerts):
    return {alert["ticket"].id for alert in alerts}


def test_breaching_ticket_appears_in_alerts(client, agent_user, login_as, db_session):
    ticket = make_ticket(db_session, agent_user, created_at=T0)
    as_of = T0 + timedelta(hours=5)  # past the 4h urgent target

    alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)

    assert ticket.id in alert_ticket_ids(alerts)
    assert next(a for a in alerts if a["ticket"].id == ticket.id)["status"] == "breaching"


def test_at_risk_ticket_appears_in_alerts(client, agent_user, login_as, db_session):
    ticket = make_ticket(db_session, agent_user, created_at=T0)
    as_of = T0 + timedelta(hours=3, minutes=40)  # 92% of the 4h target: within the 90% warning window

    alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)

    assert ticket.id in alert_ticket_ids(alerts)
    assert next(a for a in alerts if a["ticket"].id == ticket.id)["status"] == "at_risk"


def test_ticket_well_within_target_does_not_appear(client, agent_user, login_as, db_session):
    ticket = make_ticket(db_session, agent_user, created_at=T0)
    as_of = T0 + timedelta(minutes=30)  # well under 90% of 4h

    alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)

    assert ticket.id not in alert_ticket_ids(alerts)


def test_resolved_ticket_that_would_otherwise_breach_does_not_appear(
    client, agent_user, login_as, db_session
):
    ticket = make_ticket(db_session, agent_user, created_at=T0, status=TicketStatus.RESOLVED, resolved_at=T0)
    as_of = T0 + timedelta(hours=10)  # would be massively breaching if still active

    alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)

    assert ticket.id not in alert_ticket_ids(alerts)


def test_closed_ticket_that_would_otherwise_breach_does_not_appear(
    client, agent_user, login_as, db_session
):
    ticket = make_ticket(db_session, agent_user, created_at=T0, status=TicketStatus.CLOSED)
    as_of = T0 + timedelta(hours=10)

    alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)

    assert ticket.id not in alert_ticket_ids(alerts)


def test_agent_alert_list_excludes_tickets_outside_their_scope(
    client, agent_user, second_agent_user, login_as, db_session
):
    make_ticket(db_session, second_agent_user, created_at=T0)
    as_of = T0 + timedelta(hours=5)

    alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)

    assert alerts == []


def test_supervisor_alert_list_includes_every_agents_breaching_ticket(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    ticket_a = make_ticket(db_session, agent_user, created_at=T0)
    ticket_b = make_ticket(db_session, second_agent_user, created_at=T0)
    as_of = T0 + timedelta(hours=5)

    alerts = alerts_service.list_alerts(db_session, supervisor_user, now=as_of)

    assert {ticket_a.id, ticket_b.id} <= alert_ticket_ids(alerts)


def test_collaborator_can_acknowledge_same_as_primary_assignee(
    client, agent_user, second_agent_user, login_as, db_session
):
    ticket = make_ticket(db_session, agent_user, created_at=T0)
    ticket.collaborators.append(second_agent_user)
    db_session.commit()
    as_of = T0 + timedelta(hours=5)

    alerts_service.acknowledge_alert(db_session, ticket, second_agent_user)

    alerts = alerts_service.list_alerts(db_session, second_agent_user, now=as_of)
    assert ticket.id not in alert_ticket_ids(alerts)


def test_unrelated_agent_cannot_acknowledge(client, agent_user, second_agent_user, login_as, db_session):
    from fastapi import HTTPException

    ticket = make_ticket(db_session, agent_user, created_at=T0)

    try:
        alerts_service.acknowledge_alert(db_session, ticket, second_agent_user)
        assert False, "expected an HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_acknowledging_clears_it_from_the_acknowledging_users_list_only(
    client, agent_user, supervisor_user, login_as, db_session
):
    ticket = make_ticket(db_session, agent_user, created_at=T0)
    as_of = T0 + timedelta(hours=5)

    alerts_service.acknowledge_alert(db_session, ticket, agent_user)

    agent_alerts = alerts_service.list_alerts(db_session, agent_user, now=as_of)
    assert ticket.id not in alert_ticket_ids(agent_alerts)

    # a different viewer (supervisor) hasn't acknowledged it -- still theirs to see
    supervisor_alerts = alerts_service.list_alerts(db_session, supervisor_user, now=as_of)
    assert ticket.id in alert_ticket_ids(supervisor_alerts)


def test_reopening_and_rebreaching_brings_the_alert_back(
    client, agent_user, supervisor_user, login_as, db_session
):
    """The one most likely to be silently wrong: acknowledging must not be
    a permanent flag. Take a ticket through breach -> ack -> Closed ->
    reopen, and confirm the SAME acknowledging user sees it again, then
    repeat a second full cycle to make sure it isn't a one-time fluke."""
    ticket = make_ticket(db_session, agent_user, created_at=T0, status=TicketStatus.OPEN)

    breach_time = T0 + timedelta(hours=10)  # already breaching before it's ever closed
    assert ticket.id in alert_ticket_ids(
        alerts_service.list_alerts(db_session, agent_user, now=breach_time)
    )

    alerts_service.acknowledge_alert(db_session, ticket, agent_user)
    assert ticket.id not in alert_ticket_ids(
        alerts_service.list_alerts(db_session, agent_user, now=breach_time)
    )

    # Resolve, then close -- ticket must vanish from alerts entirely while Closed
    lifecycle_service.transition(db_session, ticket, TicketStatus.RESOLVED, agent_user, now=breach_time)
    lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=breach_time)
    assert ticket.id not in alert_ticket_ids(
        alerts_service.list_alerts(db_session, agent_user, now=breach_time)
    )

    # Reopen -- a new breach epoch. The old ack must NOT suppress this.
    reopen_time = breach_time + timedelta(hours=1)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=reopen_time)
    as_of_after_reopen = reopen_time + timedelta(minutes=1)

    alerts_after_reopen = alerts_service.list_alerts(db_session, agent_user, now=as_of_after_reopen)
    assert ticket.id in alert_ticket_ids(alerts_after_reopen), (
        "alert must reappear after reopening + re-breaching, despite the earlier acknowledgment"
    )

    # Acknowledge again, then run a SECOND close/reopen cycle to confirm
    # this isn't a one-off: it must keep reappearing on every new epoch.
    alerts_service.acknowledge_alert(db_session, ticket, agent_user)
    assert ticket.id not in alert_ticket_ids(
        alerts_service.list_alerts(db_session, agent_user, now=as_of_after_reopen)
    )

    lifecycle_service.transition(db_session, ticket, TicketStatus.RESOLVED, agent_user, now=as_of_after_reopen)
    lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=as_of_after_reopen)
    reopen_time_2 = as_of_after_reopen + timedelta(hours=1)
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=reopen_time_2)
    as_of_after_second_reopen = reopen_time_2 + timedelta(minutes=1)

    alerts_after_second_reopen = alerts_service.list_alerts(
        db_session, agent_user, now=as_of_after_second_reopen
    )
    assert ticket.id in alert_ticket_ids(alerts_after_second_reopen)


def test_breach_epoch_increments_only_on_reopen_not_on_pending_cycles(
    client, agent_user, login_as, db_session
):
    """A Pending cycle isn't a reopen -- acknowledging must survive it."""
    ticket = make_ticket(db_session, agent_user, created_at=T0, status=TicketStatus.OPEN)
    breach_time = T0 + timedelta(hours=10)

    alerts_service.acknowledge_alert(db_session, ticket, agent_user)

    lifecycle_service.transition(db_session, ticket, TicketStatus.PENDING, agent_user, now=breach_time)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, agent_user, now=breach_time + timedelta(hours=1)
    )

    as_of = breach_time + timedelta(hours=2)
    assert ticket.id not in alert_ticket_ids(
        alerts_service.list_alerts(db_session, agent_user, now=as_of)
    )
