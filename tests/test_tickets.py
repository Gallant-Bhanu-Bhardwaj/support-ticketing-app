from app.models.ticket import Ticket

VALID_TICKET = {
    "subject": "Cannot log in",
    "description": "User gets a 500 error on login.",
    "requester": "jane@example.com",
    "priority": "high",
    "category": "bug",
}


def create_ticket(client, data=None):
    response = client.post("/tickets", data=data or VALID_TICKET, follow_redirects=False)
    ticket_id = int(response.headers["location"].rstrip("/").split("/")[-1])
    return ticket_id, response


def test_tickets_route_requires_authentication(client):
    response = client.get("/tickets")

    assert response.status_code == 401


def test_create_ticket(client, agent_user, login_as):
    login_as(agent_user)

    ticket_id, response = create_ticket(client)

    assert response.status_code == 303
    detail = client.get(f"/tickets/{ticket_id}")
    assert detail.status_code == 200
    assert "Cannot log in" in detail.text
    assert "new" in detail.text


def test_create_as_agent_defaults_to_self_assigned(client, agent_user, login_as, db_session):
    login_as(agent_user)

    ticket_id, response = create_ticket(client)

    assert response.status_code == 303
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == agent_user.id


def test_create_as_agent_rejects_a_different_submitted_assignee(
    client, agent_user, second_agent_user, login_as, db_session
):
    """Per goal 1: an agent's reassignment attempt must be rejected by the
    server with a clear error, not silently overridden to self."""
    login_as(agent_user)

    response = client.post(
        "/tickets", data={**VALID_TICKET, "primary_assignee_id": str(second_agent_user.id)}
    )

    assert response.status_code == 403
    assert "agents can only create tickets assigned to themselves" in response.text.lower()
    assert db_session.query(Ticket).count() == 0


def test_create_as_agent_explicitly_choosing_self_succeeds(client, agent_user, login_as, db_session):
    login_as(agent_user)

    ticket_id, response = create_ticket(
        client, data={**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    )

    assert response.status_code == 303
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == agent_user.id


def test_create_as_supervisor_requires_choosing_an_agent(client, supervisor_user, login_as):
    login_as(supervisor_user)

    response = client.post("/tickets", data=VALID_TICKET)

    assert response.status_code == 422


def test_create_as_supervisor_with_chosen_agent_succeeds(
    client, supervisor_user, agent_user, login_as, db_session
):
    login_as(supervisor_user)

    ticket_id, response = create_ticket(
        client, data={**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    )

    assert response.status_code == 303
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == agent_user.id


def test_edit_ticket(client, agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    updated = {
        **VALID_TICKET,
        "subject": "Cannot log in — updated",
        "priority": "urgent",
        "primary_assignee_id": str(agent_user.id),
    }
    response = client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)

    assert response.status_code == 303
    detail = client.get(f"/tickets/{ticket_id}")
    assert "Cannot log in — updated" in detail.text
    assert "urgent" in detail.text


def test_agent_cannot_reassign_via_edit(client, agent_user, second_agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    updated = {**VALID_TICKET, "primary_assignee_id": str(second_agent_user.id)}
    response = client.post(f"/tickets/{ticket_id}", data=updated)

    assert response.status_code == 403
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == agent_user.id


def test_supervisor_can_also_create_and_edit(client, supervisor_user, agent_user, login_as):
    login_as(supervisor_user)

    ticket_id, response = create_ticket(
        client, data={**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    )
    assert response.status_code == 303

    updated = {**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    response = client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)
    assert response.status_code == 303


def test_supervisor_can_reassign_via_edit(
    client, supervisor_user, agent_user, second_agent_user, login_as, db_session
):
    login_as(supervisor_user)
    ticket_id, _ = create_ticket(
        client, data={**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    )

    updated = {**VALID_TICKET, "primary_assignee_id": str(second_agent_user.id)}
    response = client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)

    assert response.status_code == 303
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == second_agent_user.id


def test_archive_removes_ticket_from_default_list(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    list_before = client.get("/tickets")
    assert VALID_TICKET["subject"] in list_before.text

    archive_response = client.post(f"/tickets/{ticket_id}/archive", follow_redirects=False)
    assert archive_response.status_code == 303

    list_after = client.get("/tickets")
    assert VALID_TICKET["subject"] not in list_after.text


def test_archived_ticket_appears_in_archived_list(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)
    client.post(f"/tickets/{ticket_id}/archive", follow_redirects=False)

    archived_list = client.get("/tickets/archived")
    assert VALID_TICKET["subject"] in archived_list.text


def test_restore_brings_ticket_back_to_default_list(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)
    client.post(f"/tickets/{ticket_id}/archive", follow_redirects=False)

    restore_response = client.post(f"/tickets/{ticket_id}/restore", follow_redirects=False)
    assert restore_response.status_code == 303

    list_after = client.get("/tickets")
    assert VALID_TICKET["subject"] in list_after.text

    archived_list = client.get("/tickets/archived")
    assert VALID_TICKET["subject"] not in archived_list.text


def test_row_and_data_survive_archiving(client, agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    client.post(f"/tickets/{ticket_id}/archive", follow_redirects=False)

    ticket = db_session.get(Ticket, ticket_id)
    assert ticket is not None
    assert ticket.is_archived is True
    assert ticket.subject == VALID_TICKET["subject"]
    assert ticket.description == VALID_TICKET["description"]

    # still reachable directly, not hidden entirely -- only excluded from the default queue
    detail = client.get(f"/tickets/{ticket_id}")
    assert detail.status_code == 200


def test_archive_via_htmx_returns_empty_fragment_for_list_row_removal(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    response = client.post(
        f"/tickets/{ticket_id}/archive?render=none",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text == ""


def test_archive_via_htmx_returns_actions_panel_for_detail_page(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    response = client.post(
        f"/tickets/{ticket_id}/archive",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Restore" in response.text


# -- goal 5 retrofit: agents restricted to tickets they're assigned to or
# collaborating on -------------------------------------------------------


def test_unrelated_agent_cannot_edit_ticket(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    login_as(second_agent_user)
    updated = {**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    response = client.post(f"/tickets/{ticket_id}", data=updated)

    assert response.status_code == 403


def test_unrelated_agent_cannot_archive_ticket(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    login_as(second_agent_user)
    response = client.post(f"/tickets/{ticket_id}/archive")

    assert response.status_code == 403


def test_supervisor_can_edit_any_ticket(client, agent_user, supervisor_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    login_as(supervisor_user)
    updated = {**VALID_TICKET, "primary_assignee_id": str(agent_user.id)}
    response = client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)

    assert response.status_code == 303


# -- view scoping: goal 1's queue-visibility rule, unenforced since goal 2 --


def test_unrelated_agent_cannot_view_ticket_detail(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    login_as(second_agent_user)
    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 403


def test_assigned_agent_can_view_ticket_detail(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 200


def test_collaborator_can_view_ticket_detail(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)
    client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
        follow_redirects=False,
    )

    login_as(second_agent_user)
    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 200


def test_supervisor_can_view_any_ticket_detail(client, agent_user, supervisor_user, login_as):
    login_as(agent_user)
    ticket_id, _ = create_ticket(client)

    login_as(supervisor_user)
    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 200


def test_agent_queue_only_shows_their_own_tickets(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    create_ticket(client, data={**VALID_TICKET, "subject": "Mine"})

    login_as(second_agent_user)
    create_ticket(client, data={**VALID_TICKET, "subject": "Not mine"})

    login_as(agent_user)
    response = client.get("/tickets")

    assert "Mine" in response.text
    assert "Not mine" not in response.text


def test_supervisor_queue_shows_every_ticket(client, agent_user, second_agent_user, supervisor_user, login_as):
    login_as(agent_user)
    create_ticket(client, data={**VALID_TICKET, "subject": "First agent ticket"})

    login_as(second_agent_user)
    create_ticket(client, data={**VALID_TICKET, "subject": "Second agent ticket"})

    login_as(supervisor_user)
    response = client.get("/tickets")

    assert "First agent ticket" in response.text
    assert "Second agent ticket" in response.text
