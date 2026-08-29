from app.models.ticket import Ticket, TicketStatus

TICKET_DATA = {
    "subject": "Bulk test ticket",
    "description": "desc",
    "requester": "req@example.com",
    "priority": "normal",
    "category": "bug",
}


def create_ticket_as(client, login_as, user, subject, **overrides):
    login_as(user)
    data = {**TICKET_DATA, "subject": subject, **overrides}
    response = client.post("/tickets", data=data, follow_redirects=False)
    return int(response.headers["location"].rstrip("/").split("/")[-1])


def resolve_ticket(client, login_as, agent, ticket_id):
    login_as(agent)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "open"}, follow_redirects=False)
    client.post(f"/tickets/{ticket_id}/status", data={"new_status": "resolved"}, follow_redirects=False)


# -- bulk reassign -----------------------------------------------------


def test_mixed_eligibility_bulk_reassign_reports_per_ticket_outcome(
    client, agent_user, second_agent_user, login_as, db_session
):
    """Genuinely mixed batch: a ticket the actor is assigned to (fails the
    reassign-specific check), a ticket the actor isn't authorized on at all
    (fails the access check first, before reassignment is even considered),
    and a ticket id that doesn't exist. Three tickets, three distinct
    outcomes, none swallowed into a single batch-level failure."""
    own_ticket_id = create_ticket_as(client, login_as, agent_user, "My own ticket")
    other_ticket_id = create_ticket_as(client, login_as, second_agent_user, "Someone elses ticket")
    nonexistent_id = other_ticket_id + 1000

    login_as(agent_user)
    response = client.post(
        "/tickets/bulk/reassign",
        data={
            "ticket_ids": [str(own_ticket_id), str(other_ticket_id), str(nonexistent_id)],
            "new_assignee_id": str(second_agent_user.id),
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "My own ticket" in body
    assert "Someone elses ticket" in body
    assert "Only a supervisor can reassign a ticket." in body
    assert "assigned to or collaborating on." in body  # the "not authorized on this ticket" case
    assert "Ticket not found." in body
    assert "0 succeeded, 3 refused" in body

    # confirm nothing was actually mutated by the refused attempts
    own_ticket = db_session.get(Ticket, own_ticket_id)
    other_ticket = db_session.get(Ticket, other_ticket_id)
    assert own_ticket.primary_assignee_id == agent_user.id
    assert other_ticket.primary_assignee_id == second_agent_user.id


def test_supervisor_bulk_reassign_succeeds_with_mixed_not_found(
    client, agent_user, second_agent_user, supervisor_user, login_as, db_session
):
    ticket_id = create_ticket_as(client, login_as, agent_user, "Reassign me")
    fake_id = ticket_id + 5000

    login_as(supervisor_user)
    response = client.post(
        "/tickets/bulk/reassign",
        data={"ticket_ids": [str(ticket_id), str(fake_id)], "new_assignee_id": str(second_agent_user.id)},
    )

    assert response.status_code == 200
    assert "1 succeeded, 1 refused" in response.text
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == second_agent_user.id


def test_bulk_reassign_requires_at_least_one_ticket(client, supervisor_user, agent_user, login_as):
    login_as(supervisor_user)

    response = client.post("/tickets/bulk/reassign", data={"ticket_ids": [], "new_assignee_id": str(agent_user.id)})

    assert response.status_code == 400


def test_bulk_reassign_rejects_invalid_assignee_before_touching_any_ticket(
    client, agent_user, supervisor_user, login_as, db_session
):
    ticket_id = create_ticket_as(client, login_as, agent_user, "Should stay put")

    login_as(supervisor_user)
    response = client.post(
        "/tickets/bulk/reassign",
        data={"ticket_ids": [str(ticket_id)], "new_assignee_id": str(supervisor_user.id)},  # a supervisor, not an agent
    )

    assert response.status_code == 422
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.primary_assignee_id == agent_user.id


# -- bulk close -----------------------------------------------------


def test_bulk_close_mixed_eligibility(client, agent_user, supervisor_user, login_as, db_session):
    resolved_id = create_ticket_as(client, login_as, agent_user, "Ready to close")
    resolve_ticket(client, login_as, agent_user, resolved_id)
    new_id = create_ticket_as(client, login_as, agent_user, "Still new")

    login_as(supervisor_user)
    response = client.post("/tickets/bulk/close", data={"ticket_ids": [str(resolved_id), str(new_id)]})

    assert response.status_code == 200
    body = response.text
    assert "Ready to close" in body
    assert "Still new" in body
    assert "1 succeeded, 1 refused" in body
    assert "cannot move a ticket from new to closed" in body.lower()

    resolved_ticket = db_session.get(Ticket, resolved_id)
    new_ticket = db_session.get(Ticket, new_id)
    assert resolved_ticket.status == TicketStatus.CLOSED
    assert new_ticket.status == TicketStatus.NEW


def test_bulk_close_refuses_an_already_closed_ticket(client, agent_user, supervisor_user, login_as, db_session):
    """Per the goal: an already-closed ticket can't be bulk-closed again."""
    ticket_id = create_ticket_as(client, login_as, agent_user, "Close twice")
    resolve_ticket(client, login_as, agent_user, ticket_id)

    login_as(supervisor_user)
    client.post("/tickets/bulk/close", data={"ticket_ids": [str(ticket_id)]})

    response = client.post("/tickets/bulk/close", data={"ticket_ids": [str(ticket_id)]})

    assert "0 succeeded, 1 refused" in response.text
    assert "cannot move a ticket from closed to closed" in response.text.lower()


def test_bulk_close_mixed_batch_with_valid_and_already_closed_ticket(
    client, agent_user, supervisor_user, login_as, db_session
):
    """One batch, both outcomes a supervisor can actually produce: a valid
    Resolved ticket succeeds, an already-Closed one is refused by the
    state-machine check -- not two separate requests."""
    valid_id = create_ticket_as(client, login_as, agent_user, "Valid resolved ticket")
    resolve_ticket(client, login_as, agent_user, valid_id)

    already_closed_id = create_ticket_as(client, login_as, agent_user, "Already closed ticket")
    resolve_ticket(client, login_as, agent_user, already_closed_id)
    login_as(supervisor_user)
    client.post("/tickets/bulk/close", data={"ticket_ids": [str(already_closed_id)]})

    response = client.post(
        "/tickets/bulk/close", data={"ticket_ids": [str(valid_id), str(already_closed_id)]}
    )

    assert response.status_code == 200
    body = response.text
    assert "Valid resolved ticket" in body
    assert "Already closed ticket" in body
    assert "1 succeeded, 1 refused" in body
    assert "cannot move a ticket from closed to closed" in body.lower()

    valid_ticket = db_session.get(Ticket, valid_id)
    assert valid_ticket.status == TicketStatus.CLOSED


def test_bulk_close_refuses_ticket_outside_actor_scope_via_access_check(
    client, agent_user, second_agent_user, login_as, db_session
):
    """Distinct from the supervisor-only refusal: a ticket the actor has no
    relationship to at all is refused by can_act_on_ticket before the
    close-specific check is ever reached."""
    unrelated_id = create_ticket_as(client, login_as, second_agent_user, "Not my ticket at all")
    resolve_ticket(client, login_as, second_agent_user, unrelated_id)

    login_as(agent_user)
    response = client.post("/tickets/bulk/close", data={"ticket_ids": [str(unrelated_id)]})

    assert response.status_code == 200
    assert "0 succeeded, 1 refused" in response.text
    assert "assigned to or collaborating on" in response.text
    assert "supervisor" not in response.text.lower()


def test_agent_bulk_close_gets_all_refused_report_not_a_blanket_403(client, agent_user, login_as, db_session):
    """No bulk-specific role gate at the route level -- the per-ticket check
    inside lifecycle_service.transition is what does the rejecting."""
    ticket_id = create_ticket_as(client, login_as, agent_user, "Cannot close as agent")
    resolve_ticket(client, login_as, agent_user, ticket_id)

    login_as(agent_user)
    response = client.post("/tickets/bulk/close", data={"ticket_ids": [str(ticket_id)]})

    assert response.status_code == 200
    assert "0 succeeded, 1 refused" in response.text
    assert "supervisor" in response.text.lower()

    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.status == TicketStatus.RESOLVED


def test_bulk_close_requires_at_least_one_ticket(client, supervisor_user, login_as):
    login_as(supervisor_user)

    response = client.post("/tickets/bulk/close", data={"ticket_ids": []})

    assert response.status_code == 400
