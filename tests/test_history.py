from app.main import app
from app.models.reply import Reply
from app.models.ticket import TicketStatus
from app.models.ticket_history import TicketHistoryEvent, TicketHistoryEventType

VALID_TICKET = {
    "subject": "History test ticket",
    "description": "desc",
    "requester": "req@example.com",
    "priority": "normal",
    "category": "bug",
}


def create_ticket(client, login_as, user, data=None):
    login_as(user)
    response = client.post("/tickets", data=data or VALID_TICKET, follow_redirects=False)
    return int(response.headers["location"].rstrip("/").split("/")[-1])


# -- each action creates the correct timeline row --------------------------


def test_status_change_creates_correct_history_row(client, agent_user, login_as, db_session):
    ticket_id = create_ticket(client, login_as, agent_user)

    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)

    event = db_session.query(TicketHistoryEvent).filter_by(
        ticket_id=ticket_id, event_type=TicketHistoryEventType.STATUS_CHANGE
    ).one()
    assert event.old_status == TicketStatus.NEW
    assert event.new_status == TicketStatus.OPEN
    assert event.actor_id == agent_user.id
    assert event.created_at is not None


def test_each_status_change_creates_its_own_row(client, agent_user, login_as, db_session):
    ticket_id = create_ticket(client, login_as, agent_user)

    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "pending"}, follow_redirects=False)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)

    events = (
        db_session.query(TicketHistoryEvent)
        .filter_by(ticket_id=ticket_id, event_type=TicketHistoryEventType.STATUS_CHANGE)
        .order_by(TicketHistoryEvent.id)
        .all()
    )
    transitions = [(e.old_status, e.new_status) for e in events]
    assert transitions == [
        (TicketStatus.NEW, TicketStatus.OPEN),
        (TicketStatus.OPEN, TicketStatus.PENDING),
        (TicketStatus.PENDING, TicketStatus.OPEN),
    ]


def test_illegal_transition_does_not_create_a_history_row(client, agent_user, login_as, db_session):
    ticket_id = create_ticket(client, login_as, agent_user)

    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "closed"})  # illegal from New

    count = (
        db_session.query(TicketHistoryEvent)
        .filter_by(ticket_id=ticket_id, event_type=TicketHistoryEventType.STATUS_CHANGE)
        .count()
    )
    assert count == 0


def test_reassignment_via_edit_creates_correct_history_row(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    ticket_id = create_ticket(
        client, login_as, supervisor_user, data={**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    )

    login_as(supervisor_user)
    updated = {**VALID_TICKET, "primary_assignee_id": str(second_agent_user.id)}
    client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)

    event = db_session.query(TicketHistoryEvent).filter_by(
        ticket_id=ticket_id, event_type=TicketHistoryEventType.REASSIGNMENT
    ).one()
    assert event.old_assignee_id == agent_user.id
    assert event.new_assignee_id == second_agent_user.id
    assert event.actor_id == supervisor_user.id


def test_reassignment_via_bulk_creates_correct_history_row(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    ticket_id = create_ticket(client, login_as, agent_user)

    login_as(supervisor_user)
    client.post(
        "/tickets/bulk/reassign",
        data={"ticket_ids": [str(ticket_id)], "new_assignee_id": str(second_agent_user.id)},
    )

    event = db_session.query(TicketHistoryEvent).filter_by(
        ticket_id=ticket_id, event_type=TicketHistoryEventType.REASSIGNMENT
    ).one()
    assert event.old_assignee_id == agent_user.id
    assert event.new_assignee_id == second_agent_user.id
    assert event.actor_id == supervisor_user.id


def test_editing_without_changing_assignee_creates_no_reassignment_row(
    client, agent_user, login_as, db_session
):
    ticket_id = create_ticket(client, login_as, agent_user)

    updated = {**VALID_TICKET, "subject": "Edited subject", "primary_assignee_id": str(agent_user.id)}
    client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)

    count = (
        db_session.query(TicketHistoryEvent)
        .filter_by(ticket_id=ticket_id, event_type=TicketHistoryEventType.REASSIGNMENT)
        .count()
    )
    assert count == 0


def test_reply_creates_correct_history_row_referencing_the_reply(
    client, agent_user, login_as, db_session
):
    ticket_id = create_ticket(client, login_as, agent_user)

    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Looking into this.", "is_internal": "on"},
        follow_redirects=False,
    )

    reply = db_session.query(Reply).filter_by(ticket_id=ticket_id).one()

    event = db_session.query(TicketHistoryEvent).filter_by(
        ticket_id=ticket_id, event_type=TicketHistoryEventType.REPLY
    ).one()
    assert event.actor_id == agent_user.id
    # the FK itself, not just the relationship traversal -- a wrong
    # reply_id pointing at some other row could still satisfy
    # event.reply.body/.is_internal checks by coincidence if the test data
    # were less careful, but not this direct comparison against the
    # independently-queried Reply row's own id.
    assert event.reply_id == reply.id
    assert event.reply.body == "Looking into this."
    assert event.reply.is_internal is True


def test_each_reply_history_row_links_to_its_own_reply_not_another(
    client, agent_user, login_as, db_session
):
    """With only one reply on the ticket, a history row could point at
    the wrong reply_id (e.g. always the first one ever created) and still
    pass by coincidence. Two replies rule that out."""
    ticket_id = create_ticket(client, login_as, agent_user)

    client.post(f"/tickets/{ticket_id}/replies", data={"body": "First reply."}, follow_redirects=False)
    client.post(f"/tickets/{ticket_id}/replies", data={"body": "Second reply."}, follow_redirects=False)

    first_reply = db_session.query(Reply).filter_by(body="First reply.").one()
    second_reply = db_session.query(Reply).filter_by(body="Second reply.").one()

    events = (
        db_session.query(TicketHistoryEvent)
        .filter_by(ticket_id=ticket_id, event_type=TicketHistoryEventType.REPLY)
        .order_by(TicketHistoryEvent.id)
        .all()
    )
    assert len(events) == 2
    assert events[0].reply_id == first_reply.id
    assert events[1].reply_id == second_reply.id
    assert events[0].reply_id != events[1].reply_id


# -- unified timeline rendering --------------------------------------------


def test_timeline_interleaves_all_event_types_in_order_without_duplicating_replies(
    client, agent_user, supervisor_user, second_agent_user, login_as, db_session
):
    ticket_id = create_ticket(client, login_as, agent_user)
    login_as(agent_user)
    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "First: customer-visible reply."},  # unchecked checkbox: field omitted entirely
        follow_redirects=False,
    )
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)
    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Second: an internal note.", "is_internal": "on"},
        follow_redirects=False,
    )

    login_as(supervisor_user)
    updated = {**VALID_TICKET, "primary_assignee_id": str(second_agent_user.id)}
    client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)

    detail = client.get(f"/tickets/{ticket_id}")
    body = detail.text

    assert "First: customer-visible reply." in body
    assert "Second: an internal note." in body
    assert "changed status from" in body
    assert "reassigned this ticket from" in body
    assert "Customer-visible" in body
    assert "Internal note" in body

    # chronological, and each reply appears exactly once
    first_pos = body.index("First: customer-visible reply.")
    status_pos = body.index("changed status from")
    second_pos = body.index("Second: an internal note.")
    reassign_pos = body.index("reassigned this ticket from")
    assert first_pos < status_pos < second_pos < reassign_pos
    assert body.count("First: customer-visible reply.") == 1
    assert body.count("Second: an internal note.") == 1

    # no separate, redundant "Replies" section
    assert "<h2>Replies</h2>" not in body


# -- immutability: no route can mutate a timeline row -----------------------


def test_no_registered_route_accepts_a_mutating_method_on_a_history_path():
    mutating_methods = {"PUT", "PATCH", "DELETE"}
    offending = [
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set()) & mutating_methods
        if "history" in route.path.lower() or "timeline" in route.path.lower()
    ]
    assert offending == []


def test_history_service_exposes_no_update_or_delete_function():
    from app.services import history_service

    public_names = [name for name in dir(history_service) if not name.startswith("_")]
    mutating_names = [
        name for name in public_names if any(word in name.lower() for word in ("update", "delete", "edit", "remove"))
    ]
    assert mutating_names == []


def test_guessed_history_mutation_endpoints_do_not_exist(client, agent_user, login_as, db_session):
    ticket_id = create_ticket(client, login_as, agent_user)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)
    event = db_session.query(TicketHistoryEvent).filter_by(ticket_id=ticket_id).one()

    before = (event.old_status, event.new_status, event.actor_id, event.created_at)

    guessed_urls = [
        f"/tickets/{ticket_id}/history/{event.id}",
        f"/tickets/{ticket_id}/timeline/{event.id}",
        f"/history/{event.id}",
        f"/timeline/{event.id}",
    ]
    for url in guessed_urls:
        assert client.put(url, data={}).status_code in (404, 405)
        assert client.patch(url, data={}).status_code in (404, 405)
        assert client.delete(url).status_code in (404, 405)

    db_session.refresh(event)
    after = (event.old_status, event.new_status, event.actor_id, event.created_at)
    assert before == after
