from datetime import datetime, timedelta, timezone

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.services import dashboard_service

NOW = datetime.now(timezone.utc)


def _week_start(moment: datetime) -> datetime:
    """Mirrors dashboard_service._week_start, kept independent so fixtures
    are anchored to real week boundaries rather than an offset from `NOW`
    that could accidentally cross a boundary depending on what day tests
    happen to run."""
    day = moment.date() - timedelta(days=moment.weekday())
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


THIS_WEEK = _week_start(NOW)


def make_ticket(db_session, assignee, **overrides):
    defaults = dict(
        subject="Default subject",
        description="Default description",
        requester="req@example.com",
        priority=TicketPriority.NORMAL,
        category=TicketCategory.BUG,
        status=TicketStatus.NEW,
        primary_assignee_id=assignee.id,
        created_at=NOW - timedelta(hours=1),
    )
    defaults.update(overrides)
    ticket = Ticket(**defaults)
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def test_headline_counts_correct_against_seeded_data(
    client, agent_user, second_agent_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Open 1", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="Open 2", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="Pending 1", status=TicketStatus.PENDING)
    make_ticket(db_session, agent_user, subject="New 1", status=TicketStatus.NEW)

    make_ticket(
        db_session,
        agent_user,
        subject="Resolved this week",
        status=TicketStatus.RESOLVED,
        created_at=THIS_WEEK - timedelta(days=20),
        resolved_at=THIS_WEEK + timedelta(hours=2),
    )
    make_ticket(
        db_session,
        agent_user,
        subject="Resolved last week",
        status=TicketStatus.RESOLVED,
        created_at=THIS_WEEK - timedelta(days=20),
        resolved_at=THIS_WEEK - timedelta(days=3),
    )

    make_ticket(
        db_session,
        agent_user,
        subject="Breaching urgent",
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,  # 4h target
        created_at=NOW - timedelta(hours=10),
    )
    make_ticket(
        db_session,
        agent_user,
        subject="Fresh low",
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,  # 72h target
        created_at=NOW - timedelta(hours=1),
    )

    # unrelated to agent_user -- must not affect their headline numbers
    make_ticket(db_session, second_agent_user, subject="Other agent open", status=TicketStatus.OPEN)
    make_ticket(
        db_session,
        second_agent_user,
        subject="Other agent resolved this week",
        status=TicketStatus.RESOLVED,
        resolved_at=THIS_WEEK + timedelta(hours=1),
    )

    headlines = dashboard_service.headline_counts(db_session, agent_user, now=NOW)

    assert headlines["open"] == 4  # Open 1, Open 2, Breaching urgent, Fresh low
    assert headlines["pending"] == 1
    assert headlines["resolved_this_week"] == 1
    assert headlines["breaching"] == 1


def test_supervisor_headline_counts_include_every_agent(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Agent1 open", status=TicketStatus.OPEN)
    make_ticket(db_session, second_agent_user, subject="Agent2 open", status=TicketStatus.OPEN)

    headlines = dashboard_service.headline_counts(db_session, supervisor_user, now=NOW)

    assert headlines["open"] == 2


def test_breakdown_by_status_correct_against_seeded_data(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="N1", status=TicketStatus.NEW)
    make_ticket(db_session, agent_user, subject="O1", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="O2", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="P1", status=TicketStatus.PENDING)
    make_ticket(db_session, agent_user, subject="R1", status=TicketStatus.RESOLVED)
    make_ticket(db_session, agent_user, subject="R2", status=TicketStatus.RESOLVED)
    make_ticket(db_session, agent_user, subject="R3", status=TicketStatus.RESOLVED)

    breakdown = {row["status"]: row["count"] for row in dashboard_service.breakdown_by_status(db_session, agent_user)}

    assert breakdown[TicketStatus.NEW] == 1
    assert breakdown[TicketStatus.OPEN] == 2
    assert breakdown[TicketStatus.PENDING] == 1
    assert breakdown[TicketStatus.RESOLVED] == 3
    assert TicketStatus.CLOSED not in breakdown


def test_breakdown_by_status_excludes_archived_tickets(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Active", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="Archived", status=TicketStatus.OPEN, is_archived=True)

    breakdown = {row["status"]: row["count"] for row in dashboard_service.breakdown_by_status(db_session, agent_user)}

    assert breakdown[TicketStatus.OPEN] == 1


def test_agent_breakdown_by_status_only_reflects_their_own_tickets(
    client, agent_user, second_agent_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Mine", status=TicketStatus.OPEN)
    make_ticket(db_session, second_agent_user, subject="Not mine", status=TicketStatus.OPEN)

    breakdown = {row["status"]: row["count"] for row in dashboard_service.breakdown_by_status(db_session, agent_user)}

    assert breakdown[TicketStatus.OPEN] == 1


def test_breakdown_by_agent_includes_agents_with_zero_tickets(
    client, agent_user, second_agent_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="T1", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="T2", status=TicketStatus.OPEN)

    breakdown = {row["agent"]: row["count"] for row in dashboard_service.breakdown_by_agent(db_session)}

    assert breakdown[agent_user.email] == 2
    assert breakdown[second_agent_user.email] == 0


def test_dashboard_page_shows_agent_breakdown_only_for_supervisor(
    client, agent_user, supervisor_user, login_as
):
    login_as(agent_user)
    agent_response = client.get("/dashboard")
    assert "By agent" not in agent_response.text

    login_as(supervisor_user)
    supervisor_response = client.get("/dashboard")
    assert "By agent" in supervisor_response.text


def test_resolved_per_week_buckets_correctly_and_excludes_outside_window(
    client, agent_user, login_as, db_session
):
    make_ticket(
        db_session, agent_user, subject="This week",
        status=TicketStatus.RESOLVED, resolved_at=THIS_WEEK + timedelta(hours=1),
    )
    make_ticket(
        db_session, agent_user, subject="One week ago",
        status=TicketStatus.RESOLVED, resolved_at=THIS_WEEK - timedelta(weeks=1, hours=-1),
    )
    make_ticket(
        db_session, agent_user, subject="Three weeks ago x2 (a)",
        status=TicketStatus.RESOLVED, resolved_at=THIS_WEEK - timedelta(weeks=3, hours=-1),
    )
    make_ticket(
        db_session, agent_user, subject="Three weeks ago x2 (b)",
        status=TicketStatus.RESOLVED, resolved_at=THIS_WEEK - timedelta(weeks=3, hours=-2),
    )
    make_ticket(
        db_session, agent_user, subject="Nine weeks ago (outside window)",
        status=TicketStatus.RESOLVED, resolved_at=THIS_WEEK - timedelta(weeks=9, hours=-1),
    )

    buckets = dashboard_service.resolved_per_week(db_session, agent_user, weeks=8, now=NOW)

    assert len(buckets) == 8
    assert buckets[-1]["week_start"] == THIS_WEEK.date().isoformat()
    assert buckets[-1]["count"] == 1  # this week
    assert buckets[-2]["count"] == 1  # one week ago
    assert buckets[-4]["count"] == 2  # three weeks ago
    total_bucketed = sum(bucket["count"] for bucket in buckets)
    assert total_bucketed == 4  # the nine-weeks-ago ticket must not appear anywhere


def test_chart_data_endpoint_returns_json_matching_resolved_per_week(client, agent_user, login_as, db_session):
    make_ticket(
        db_session, agent_user, subject="Resolved", status=TicketStatus.RESOLVED,
        resolved_at=THIS_WEEK + timedelta(hours=1),
    )
    login_as(agent_user)

    response = client.get("/dashboard/chart-data")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    assert data[-1]["count"] == 1
