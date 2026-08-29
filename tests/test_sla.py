from datetime import datetime, timedelta, timezone

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.services import lifecycle_service, sla_service
from app.services.sla_service import elapsed_response_time

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_ticket(db_session, assignee, created_at=T0):
    ticket = Ticket(
        subject="Test ticket",
        description="desc",
        requester="req@example.com",
        priority=TicketPriority.NORMAL,
        category=TicketCategory.BUG,
        status=TicketStatus.NEW,
        primary_assignee_id=assignee.id,
        created_at=created_at,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def test_elapsed_with_no_periods_equals_wall_clock_time():
    as_of = T0 + timedelta(hours=5)

    elapsed = elapsed_response_time(T0, [], [], as_of)

    assert elapsed == timedelta(hours=5)


def test_elapsed_excludes_time_spent_pending():
    """The specific requirement: elapsed time must exclude Pending spans."""
    as_of = T0 + timedelta(hours=5)
    pending_periods = [(T0 + timedelta(hours=1), T0 + timedelta(hours=3))]

    elapsed = elapsed_response_time(T0, pending_periods, [], as_of)

    assert elapsed == timedelta(hours=3)  # 5h wall clock minus 2h pending


def test_elapsed_excludes_ongoing_pending_period_up_to_as_of():
    as_of = T0 + timedelta(hours=2)
    pending_periods = [(T0 + timedelta(hours=1), None)]  # still pending at as_of

    elapsed = elapsed_response_time(T0, pending_periods, [], as_of)

    assert elapsed == timedelta(hours=1)


def test_elapsed_excludes_time_spent_closed_after_reopening():
    """A ticket closed for a week and then reopened should not instantly
    appear to have breached its target the moment it reopens."""
    closed_periods = [(T0 + timedelta(hours=2), T0 + timedelta(days=7, hours=2))]
    as_of = T0 + timedelta(days=7, hours=3)

    elapsed = elapsed_response_time(T0, [], closed_periods, as_of)

    assert elapsed == timedelta(hours=3)


def test_elapsed_excludes_both_pending_and_closed_periods_together():
    pending_periods = [(T0 + timedelta(hours=1), T0 + timedelta(hours=2))]  # 1h excluded
    closed_periods = [(T0 + timedelta(hours=5), T0 + timedelta(hours=10))]  # 5h excluded
    as_of = T0 + timedelta(hours=12)

    elapsed = elapsed_response_time(T0, pending_periods, closed_periods, as_of)

    assert elapsed == timedelta(hours=6)


def test_elapsed_excludes_multiple_pending_periods_summed():
    """A ticket that has been Pending more than once must have every span
    excluded, not just the first or the most recent."""
    pending_periods = [
        (T0 + timedelta(hours=1), T0 + timedelta(hours=2)),  # 1h
        (T0 + timedelta(hours=4), T0 + timedelta(hours=5)),  # 1h
        (T0 + timedelta(hours=7), T0 + timedelta(hours=8)),  # 1h
    ]
    as_of = T0 + timedelta(hours=10)

    elapsed = elapsed_response_time(T0, pending_periods, [], as_of)

    assert elapsed == timedelta(hours=7)  # 10h wall clock minus 3h total pending


def test_elapsed_excludes_multiple_closed_periods_summed():
    """A ticket closed and reopened more than once must have every closed
    span excluded, not just the first or the most recent."""
    closed_periods = [
        (T0 + timedelta(hours=2), T0 + timedelta(hours=4)),  # 2h
        (T0 + timedelta(hours=6), T0 + timedelta(hours=9)),  # 3h
    ]
    as_of = T0 + timedelta(hours=12)

    elapsed = elapsed_response_time(T0, [], closed_periods, as_of)

    assert elapsed == timedelta(hours=7)  # 12h wall clock minus 5h total closed


def test_elapsed_for_ticket_with_multiple_pending_cycles(db_session, agent_user):
    """Integration check for the multiple-Pending-cycles case, driven through
    real Open->Pending->Open->Pending->Open transitions rather than a
    hand-built period list."""
    ticket = make_ticket(db_session, agent_user)

    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.PENDING, agent_user, now=T0 + timedelta(hours=1)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, agent_user, now=T0 + timedelta(hours=3)
    )  # pending #1: 2h excluded
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.PENDING, agent_user, now=T0 + timedelta(hours=5)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, agent_user, now=T0 + timedelta(hours=8)
    )  # pending #2: 3h excluded

    as_of = T0 + timedelta(hours=10)
    elapsed = sla_service.elapsed_response_time_for_ticket(db_session, ticket, as_of=as_of)

    assert elapsed == timedelta(hours=5)  # 10h wall clock minus (2h + 3h) pending


def test_elapsed_for_ticket_with_multiple_closed_cycles(db_session, agent_user, supervisor_user):
    """Integration check for the multiple-Closed-cycles case, driven through
    real Resolved->Closed->Open transitions repeated twice."""
    ticket = make_ticket(db_session, agent_user)

    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0 + timedelta(hours=1)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=T0 + timedelta(hours=2)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, supervisor_user, now=T0 + timedelta(hours=5)
    )  # closed #1: 3h excluded
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0 + timedelta(hours=6)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=T0 + timedelta(hours=7)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, supervisor_user, now=T0 + timedelta(hours=9)
    )  # closed #2: 2h excluded

    as_of = T0 + timedelta(hours=10)
    elapsed = sla_service.elapsed_response_time_for_ticket(db_session, ticket, as_of=as_of)

    assert elapsed == timedelta(hours=5)  # 10h wall clock minus (3h + 2h) closed


def test_elapsed_for_ticket_reflects_real_lifecycle_transitions(db_session, agent_user):
    """Integration check: elapsed_response_time_for_ticket, fed by the actual
    period rows lifecycle_service.transition() creates, agrees with the pure
    calculation -- the two aren't just consistent in isolation."""
    ticket = make_ticket(db_session, agent_user)

    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.PENDING, agent_user, now=T0 + timedelta(hours=2)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, agent_user, now=T0 + timedelta(hours=6)
    )

    as_of = T0 + timedelta(hours=8)
    elapsed = sla_service.elapsed_response_time_for_ticket(db_session, ticket, as_of=as_of)

    assert elapsed == timedelta(hours=4)  # 8h wall clock minus 4h pending (2h-6h)


def test_target_response_time_covers_every_priority():
    for priority in TicketPriority:
        assert priority in sla_service.TARGET_RESPONSE_TIME
