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
    )  # closed #1: 3h excluded (T0+2h -> T0+5h); resolved #1: 1h excluded (T0+1h -> T0+2h)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0 + timedelta(hours=6)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=T0 + timedelta(hours=7)
    )
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.OPEN, supervisor_user, now=T0 + timedelta(hours=9)
    )  # closed #2: 2h excluded (T0+7h -> T0+9h); resolved #2: 1h excluded (T0+6h -> T0+7h)

    as_of = T0 + timedelta(hours=10)
    elapsed = sla_service.elapsed_response_time_for_ticket(db_session, ticket, as_of=as_of)

    # 10h wall clock minus (3h + 2h) closed minus (1h + 1h) resolved-but-not-yet-closed
    assert elapsed == timedelta(hours=3)


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


def test_elapsed_excludes_time_spent_resolved_but_not_yet_closed():
    """A ticket resolved quickly but left sitting in Resolved for a long
    stretch before anyone gets around to closing it must not show inflated
    elapsed time -- the customer already had a fast response the moment it
    was resolved; sitting unclosed is an administrative delay, not the
    customer still waiting."""
    resolved_periods = [(T0 + timedelta(minutes=30), T0 + timedelta(days=10))]
    as_of = T0 + timedelta(days=10)  # right when it's closed, ending the resolved period

    elapsed = elapsed_response_time(T0, [], [], as_of, resolved_periods)

    assert elapsed == timedelta(minutes=30)


def test_elapsed_freezes_while_still_sitting_in_resolved_unclosed():
    """The open-ended case: never closed at all. Elapsed must stay frozen
    at the moment of resolution, not keep growing while it sits there."""
    resolved_periods = [(T0 + timedelta(minutes=30), None)]
    as_of = T0 + timedelta(days=30)  # long after resolution, still unclosed

    elapsed = elapsed_response_time(T0, [], [], as_of, resolved_periods)

    assert elapsed == timedelta(minutes=30)


def test_elapsed_for_ticket_resolved_quickly_then_left_unclosed_a_long_time(
    db_session, agent_user
):
    """Integration version of the same scenario, driven through a real
    OPEN -> RESOLVED transition rather than a hand-built period list."""
    ticket = make_ticket(db_session, agent_user)

    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0 + timedelta(minutes=30)
    )

    as_of = T0 + timedelta(days=10)  # sat in Resolved, unclosed, for 10 days
    elapsed = sla_service.elapsed_response_time_for_ticket(db_session, ticket, as_of=as_of)

    assert elapsed == timedelta(minutes=30)


def test_elapsed_for_ticket_resolved_fast_sits_a_while_then_closed_then_reopened(
    db_session, agent_user, supervisor_user
):
    """The exact scenario from the review: fast resolution, a long
    unclosed stretch, then closed, then reopened. Elapsed on reopen must
    reflect only the real active time (30 minutes), not the 10-day wait to
    be closed nor the closed period itself."""
    ticket = make_ticket(db_session, agent_user)

    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, agent_user, now=T0)
    lifecycle_service.transition(
        db_session, ticket, TicketStatus.RESOLVED, agent_user, now=T0 + timedelta(minutes=30)
    )
    close_time = T0 + timedelta(days=10)  # sat unclosed for 10 days
    lifecycle_service.transition(db_session, ticket, TicketStatus.CLOSED, supervisor_user, now=close_time)
    reopen_time = close_time + timedelta(hours=2)  # closed for 2 hours
    lifecycle_service.transition(db_session, ticket, TicketStatus.OPEN, supervisor_user, now=reopen_time)

    as_of = reopen_time + timedelta(minutes=5)
    elapsed = sla_service.elapsed_response_time_for_ticket(db_session, ticket, as_of=as_of)

    assert elapsed == timedelta(minutes=35)  # 30 min (real work) + 5 min since reopening
