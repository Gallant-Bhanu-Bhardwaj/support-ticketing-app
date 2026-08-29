from datetime import datetime, timedelta, timezone

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.services import lifecycle_service, sla_service
from app.services.sla_service import elapsed_response_time

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


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


def test_elapsed_for_ticket_reflects_real_lifecycle_transitions(db_session, agent_user):
    """Integration check: elapsed_response_time_for_ticket, fed by the actual
    period rows lifecycle_service.transition() creates, agrees with the pure
    calculation -- the two aren't just consistent in isolation."""
    ticket = Ticket(
        subject="Test ticket",
        description="desc",
        requester="req@example.com",
        priority=TicketPriority.NORMAL,
        category=TicketCategory.BUG,
        status=TicketStatus.NEW,
        created_at=T0,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)

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
