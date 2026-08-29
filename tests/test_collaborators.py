from app.models.reply import Reply
from app.models.ticket import Ticket

TICKET_DATA = {
    "subject": "Needs a second pair of eyes",
    "description": "desc",
    "requester": "req@example.com",
    "priority": "normal",
    "category": "bug",
}


def create_ticket(client, data=None):
    response = client.post("/tickets", data=data or TICKET_DATA, follow_redirects=False)
    return int(response.headers["location"].rstrip("/").split("/")[-1])


def test_add_collaborator(client, agent_user, second_agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id = create_ticket(client)

    response = client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    ticket = db_session.get(Ticket, ticket_id)
    assert second_agent_user.id in ticket.collaborator_ids


def test_remove_collaborator(client, agent_user, second_agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id = create_ticket(client)
    client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
        follow_redirects=False,
    )

    response = client.post(
        f"/tickets/{ticket_id}/collaborators/{second_agent_user.id}/remove",
        follow_redirects=False,
    )

    assert response.status_code == 303
    ticket = db_session.get(Ticket, ticket_id)
    assert second_agent_user.id not in ticket.collaborator_ids


def test_cannot_add_primary_assignee_as_collaborator(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket(client)

    response = client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(agent_user.id)},
    )

    assert response.status_code == 409


def test_cannot_add_same_collaborator_twice(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket(client)
    client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
        follow_redirects=False,
    )

    response = client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
    )

    assert response.status_code == 409


def test_unrelated_agent_cannot_manage_collaborators(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket(client)

    login_as(second_agent_user)
    response = client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
    )

    assert response.status_code == 403


def test_collaborator_can_reply(client, agent_user, second_agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id = create_ticket(client)
    client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
        follow_redirects=False,
    )

    login_as(second_agent_user)
    response = client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Collaborator chiming in."},
        follow_redirects=False,
    )

    assert response.status_code == 303
    reply = db_session.query(Reply).filter(Reply.ticket_id == ticket_id).one()
    assert reply.author_id == second_agent_user.id


def test_collaborator_can_edit_and_archive(client, agent_user, second_agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket(client)
    client.post(
        f"/tickets/{ticket_id}/collaborators",
        data={"user_id": str(second_agent_user.id)},
        follow_redirects=False,
    )

    login_as(second_agent_user)
    updated = {**TICKET_DATA, "primary_assignee_id": str(agent_user.id)}
    response = client.post(f"/tickets/{ticket_id}", data=updated, follow_redirects=False)
    assert response.status_code == 303

    response = client.post(f"/tickets/{ticket_id}/archive", follow_redirects=False)
    assert response.status_code == 303


def test_my_tickets_includes_assigned_and_collaborated_and_nothing_else(
    client, agent_user, second_agent_user, login_as
):
    login_as(agent_user)
    create_ticket(client, data={**TICKET_DATA, "subject": "Assigned to me"})

    # this ticket must be assigned to the *other* agent so it only shows up
    # for agent_user via the collaborator path, not the assignee path
    login_as(second_agent_user)
    collaborating_on = create_ticket(client, data={**TICKET_DATA, "subject": "Collaborating on this one"})
    client.post(
        f"/tickets/{collaborating_on}/collaborators",
        data={"user_id": str(agent_user.id)},
        follow_redirects=False,
    )
    create_ticket(client, data={**TICKET_DATA, "subject": "Not mine at all"})

    login_as(agent_user)
    response = client.get("/tickets/mine")

    assert "Assigned to me" in response.text
    assert "Collaborating on this one" in response.text
    assert "Not mine at all" not in response.text
