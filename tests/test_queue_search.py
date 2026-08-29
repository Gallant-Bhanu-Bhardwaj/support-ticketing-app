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


def test_search_matches_subject(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Printer jam issue")
    make_ticket(db_session, agent_user, subject="Login failure")
    login_as(agent_user)

    response = client.get("/tickets?q=printer")

    assert "Printer jam issue" in response.text
    assert "Login failure" not in response.text


def test_search_matches_description(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Ticket A", description="something about invoices")
    make_ticket(db_session, agent_user, subject="Ticket B", description="unrelated text")
    login_as(agent_user)

    response = client.get("/tickets?q=invoices")

    assert "Ticket A" in response.text
    assert "Ticket B" not in response.text


def test_search_is_case_insensitive(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Printer jam issue")
    login_as(agent_user)

    response = client.get("/tickets?q=PRINTER")

    assert "Printer jam issue" in response.text


def test_empty_filter_values_are_treated_as_no_filter(client, agent_user, login_as, db_session):
    """The queue form's reset options submit value="" -- that must mean 'no
    filter', not a 422 from failing to parse "" as an enum/int."""
    make_ticket(db_session, agent_user, subject="Some ticket")
    login_as(agent_user)

    response = client.get("/tickets?status=&priority=&category=&assignee_id=")

    assert response.status_code == 200
    assert "Some ticket" in response.text


def test_invalid_filter_value_is_rejected(client, agent_user, login_as):
    login_as(agent_user)

    response = client.get("/tickets?status=not-a-real-status")

    assert response.status_code == 422


def test_status_filter_narrows_results(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Open one", status=TicketStatus.OPEN)
    make_ticket(db_session, agent_user, subject="New one", status=TicketStatus.NEW)
    login_as(agent_user)

    response = client.get("/tickets?status=open")

    assert "Open one" in response.text
    assert "New one" not in response.text


def test_priority_filter_narrows_results(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Urgent one", priority=TicketPriority.URGENT)
    make_ticket(db_session, agent_user, subject="Low one", priority=TicketPriority.LOW)
    login_as(agent_user)

    response = client.get("/tickets?priority=urgent")

    assert "Urgent one" in response.text
    assert "Low one" not in response.text


def test_category_filter_narrows_results(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="Bug one", category=TicketCategory.BUG)
    make_ticket(db_session, agent_user, subject="Billing one", category=TicketCategory.BILLING)
    login_as(agent_user)

    response = client.get("/tickets?category=billing")

    assert "Billing one" in response.text
    assert "Bug one" not in response.text


def test_assignee_filter_narrows_results(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Agent1 ticket")
    make_ticket(db_session, second_agent_user, subject="Agent2 ticket")
    login_as(supervisor_user)

    response = client.get(f"/tickets?assignee_id={agent_user.id}")

    assert "Agent1 ticket" in response.text
    assert "Agent2 ticket" not in response.text


def test_sort_by_created_date_ascending(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="First", created_at=T0)
    make_ticket(db_session, agent_user, subject="Second", created_at=T0 + timedelta(hours=1))
    login_as(agent_user)

    response = client.get("/tickets?sort=created&direction=asc")

    assert response.text.index("First") < response.text.index("Second")


def test_sort_by_created_date_descending(client, agent_user, login_as, db_session):
    make_ticket(db_session, agent_user, subject="First", created_at=T0)
    make_ticket(db_session, agent_user, subject="Second", created_at=T0 + timedelta(hours=1))
    login_as(agent_user)

    response = client.get("/tickets?sort=created&direction=desc")

    assert response.text.index("Second") < response.text.index("First")


def test_sort_by_priority_ascending_uses_severity_order_not_alphabetical(
    client, agent_user, login_as, db_session
):
    """low/normal/high/urgent are stored as strings -- alphabetically that's
    high, low, normal, urgent, which is not the real severity order."""
    make_ticket(db_session, agent_user, subject="LowOne", priority=TicketPriority.LOW)
    make_ticket(db_session, agent_user, subject="UrgentOne", priority=TicketPriority.URGENT)
    make_ticket(db_session, agent_user, subject="NormalOne", priority=TicketPriority.NORMAL)
    make_ticket(db_session, agent_user, subject="HighOne", priority=TicketPriority.HIGH)
    login_as(agent_user)

    response = client.get("/tickets?sort=priority&direction=asc")

    positions = {name: response.text.index(name) for name in ["LowOne", "NormalOne", "HighOne", "UrgentOne"]}
    assert positions["LowOne"] < positions["NormalOne"] < positions["HighOne"] < positions["UrgentOne"]


def test_sort_by_priority_descending_uses_severity_order_not_alphabetical(
    client, agent_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="LowOne", priority=TicketPriority.LOW)
    make_ticket(db_session, agent_user, subject="UrgentOne", priority=TicketPriority.URGENT)
    make_ticket(db_session, agent_user, subject="NormalOne", priority=TicketPriority.NORMAL)
    make_ticket(db_session, agent_user, subject="HighOne", priority=TicketPriority.HIGH)
    login_as(agent_user)

    response = client.get("/tickets?sort=priority&direction=desc")

    positions = {name: response.text.index(name) for name in ["LowOne", "NormalOne", "HighOne", "UrgentOne"]}
    assert positions["UrgentOne"] < positions["HighOne"] < positions["NormalOne"] < positions["LowOne"]


def test_sort_by_updated_at_ascending(client, agent_user, login_as, db_session):
    older = make_ticket(db_session, agent_user, subject="Updated older")
    newer = make_ticket(db_session, agent_user, subject="Updated newer")
    older.updated_at = T0
    newer.updated_at = T0 + timedelta(hours=2)
    db_session.commit()
    login_as(agent_user)

    response = client.get("/tickets?sort=updated&direction=asc")

    assert response.text.index("Updated older") < response.text.index("Updated newer")


def test_sort_by_updated_at_descending(client, agent_user, login_as, db_session):
    older = make_ticket(db_session, agent_user, subject="Updated older")
    newer = make_ticket(db_session, agent_user, subject="Updated newer")
    older.updated_at = T0
    newer.updated_at = T0 + timedelta(hours=2)
    db_session.commit()
    login_as(agent_user)

    response = client.get("/tickets?sort=updated&direction=desc")

    assert response.text.index("Updated newer") < response.text.index("Updated older")


def test_combined_filters_apply_as_and_not_or(client, agent_user, login_as, db_session):
    """status=open&priority=high must only match tickets satisfying BOTH --
    if the filters were OR'd instead, the other two tickets would also show."""
    make_ticket(db_session, agent_user, subject="Open high", status=TicketStatus.OPEN, priority=TicketPriority.HIGH)
    make_ticket(db_session, agent_user, subject="Open low", status=TicketStatus.OPEN, priority=TicketPriority.LOW)
    make_ticket(db_session, agent_user, subject="New high", status=TicketStatus.NEW, priority=TicketPriority.HIGH)
    login_as(agent_user)

    response = client.get("/tickets?status=open&priority=high")

    assert "Open high" in response.text
    assert "Open low" not in response.text
    assert "New high" not in response.text
    assert "1 matching ticket" in response.text


def test_pagination_and_total_count(client, agent_user, login_as, db_session):
    for i in range(12):
        make_ticket(db_session, agent_user, subject=f"Ticket {i:02d}", created_at=T0 + timedelta(minutes=i))
    login_as(agent_user)

    page1 = client.get("/tickets?page=1&page_size=5&sort=created&direction=asc")
    assert "12 matching" in page1.text
    for i in range(5):
        assert f"Ticket {i:02d}" in page1.text
    for i in range(5, 12):
        assert f"Ticket {i:02d}" not in page1.text

    page2 = client.get("/tickets?page=2&page_size=5&sort=created&direction=asc")
    for i in range(5, 10):
        assert f"Ticket {i:02d}" in page2.text
    assert "Ticket 00" not in page2.text
    assert "Ticket 10" not in page2.text

    page3 = client.get("/tickets?page=3&page_size=5&sort=created&direction=asc")
    assert "Ticket 10" in page3.text
    assert "Ticket 11" in page3.text
    assert "Ticket 09" not in page3.text


def test_agent_search_never_includes_unrelated_ticket_even_if_matching(
    client, agent_user, second_agent_user, login_as, db_session
):
    make_ticket(db_session, second_agent_user, subject="Printer jam issue for someone else")
    login_as(agent_user)

    response = client.get("/tickets?q=printer")

    assert "Printer jam issue for someone else" not in response.text
    assert "0 matching" in response.text


def test_agent_filter_never_includes_unrelated_ticket(
    client, agent_user, second_agent_user, login_as, db_session
):
    make_ticket(db_session, second_agent_user, subject="Not mine", status=TicketStatus.NEW)
    login_as(agent_user)

    response = client.get("/tickets?status=new")

    assert "Not mine" not in response.text


def test_supervisor_search_includes_every_matching_ticket(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Printer jam issue")
    make_ticket(db_session, second_agent_user, subject="Printer jam issue too")
    login_as(supervisor_user)

    response = client.get("/tickets?q=printer")

    assert "Printer jam issue" in response.text
    assert "Printer jam issue too" in response.text


def test_total_count_reflects_filtered_query_not_the_unfiltered_queue(
    client, agent_user, login_as, db_session
):
    make_ticket(db_session, agent_user, subject="Match", status=TicketStatus.OPEN)
    for i in range(3):
        make_ticket(db_session, agent_user, subject=f"NoMatch {i}", status=TicketStatus.NEW)
    login_as(agent_user)

    response = client.get("/tickets?status=open")

    assert "1 matching ticket" in response.text
    assert "Match" in response.text


def test_total_count_and_page_count_stay_consistent_under_a_filter(
    client, agent_user, login_as, db_session
):
    """Regression guard: total must come from the same scoped+filtered query
    as the page of results, not a separately computed count that could
    drift out of sync with what's actually being paginated."""
    for i in range(7):
        make_ticket(
            db_session,
            agent_user,
            subject=f"Filtered {i:02d}",
            status=TicketStatus.OPEN,
            created_at=T0 + timedelta(minutes=i),
        )
    make_ticket(db_session, agent_user, subject="Excluded", status=TicketStatus.NEW)
    login_as(agent_user)

    response = client.get("/tickets?status=open&page=1&page_size=3&sort=created&direction=asc")

    assert "7 matching" in response.text
    assert "Page 1 of 3" in response.text
    assert "Excluded" not in response.text
    for i in range(3):
        assert f"Filtered {i:02d}" in response.text
    for i in range(3, 7):
        assert f"Filtered {i:02d}" not in response.text
