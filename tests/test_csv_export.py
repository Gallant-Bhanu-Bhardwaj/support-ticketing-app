import csv
import io
from datetime import datetime, timedelta, timezone

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_ticket(db_session, assignee, **overrides):
    defaults = dict(
        subject="Default subject",
        description="Default description",
        requester="req@example.com",
        priority=TicketPriority.NORMAL,
        category=TicketCategory.BUG,
        status=TicketStatus.NEW,
        primary_assignee_id=assignee.id,
        created_at=T0,
    )
    defaults.update(overrides)
    ticket = Ticket(**defaults)
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def parse_csv(response):
    return list(csv.reader(io.StringIO(response.text)))


def test_csv_export_respects_active_filters(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Open one", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="New one", status=TicketStatus.NEW)
    login_as(agent_user)

    response = client.get("/tickets/export.csv?status=open")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = parse_csv(response)
    subjects = [row[1] for row in rows[1:]]
    assert "Open one" in subjects
    assert "New one" not in subjects


def test_csv_export_respects_search(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Printer jam issue")
    make_ticket(db_session, agent_user, subject="Login failure")
    login_as(agent_user)

    response = client.get("/tickets/export.csv?q=printer")

    subjects = [row[1] for row in parse_csv(response)[1:]]
    assert subjects == ["Printer jam issue"]


def test_csv_export_respects_viewer_scoping(client, agent_user, second_agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Mine")
    make_ticket(db_session, second_agent_user, subject="Not mine")
    login_as(agent_user)

    response = client.get("/tickets/export.csv")

    subjects = [row[1] for row in parse_csv(response)[1:]]
    assert "Mine" in subjects
    assert "Not mine" not in subjects


def test_supervisor_csv_export_includes_everything_matching(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Agent1 ticket")
    make_ticket(db_session, second_agent_user, subject="Agent2 ticket")
    login_as(supervisor_user)

    response = client.get("/tickets/export.csv")

    subjects = [row[1] for row in parse_csv(response)[1:]]
    assert "Agent1 ticket" in subjects
    assert "Agent2 ticket" in subjects


def test_csv_export_produces_parseable_file_with_expected_rows(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Row one", priority=TicketPriority.HIGH)
    make_ticket(db_session, agent_user, subject="Row two", priority=TicketPriority.LOW)
    login_as(agent_user)

    response = client.get("/tickets/export.csv")

    rows = parse_csv(response)
    assert rows[0] == [
        "id",
        "subject",
        "requester",
        "assignee",
        "priority",
        "category",
        "status",
        "created_at",
        "updated_at",
        "breach_status",
    ]
    assert len(rows) == 3  # header + 2 tickets
    subjects = {row[1] for row in rows[1:]}
    assert subjects == {"Row one", "Row two"}
    assignees = {row[3] for row in rows[1:]}
    assert assignees == {agent_user.email}


def test_csv_export_breach_status_reflects_elapsed_time_against_target(
    client, agent_user, login_as, db_session
):
    now = datetime.now(timezone.utc)
    make_ticket(
        db_session,
        agent_user,
        subject="Old urgent ticket",
        priority=TicketPriority.URGENT,  # 4h target
        created_at=now - timedelta(hours=10),
    )
    make_ticket(
        db_session,
        agent_user,
        subject="Fresh low ticket",
        priority=TicketPriority.LOW,  # 72h target
        created_at=now - timedelta(hours=1),
    )
    login_as(agent_user)

    response = client.get("/tickets/export.csv")

    by_subject = {row[1]: row for row in parse_csv(response)[1:]}
    assert by_subject["Old urgent ticket"][-1] == "breaching"
    assert by_subject["Fresh low ticket"][-1] == "on_track"


def test_csv_export_is_not_capped_by_page_size(client, agent_user, login_as, db_session):
    """Export must reflect the whole filtered set, not just one page."""
    for i in range(25):
        make_ticket(db_session, agent_user, subject=f"Export {i:02d}")
    login_as(agent_user)

    response = client.get("/tickets/export.csv")

    rows = parse_csv(response)
    assert len(rows) == 26  # header + 25, well past the default page_size of 20
