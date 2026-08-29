from app.models.reply import Reply

TICKET_DATA = {
    "subject": "Billing question",
    "description": "Why was I charged twice?",
    "requester": "sam@example.com",
    "priority": "normal",
    "category": "billing",
}


def create_ticket(client, data=None):
    response = client.post("/tickets", data=data or TICKET_DATA, follow_redirects=False)
    return int(response.headers["location"].rstrip("/").split("/")[-1])


def test_reply_requires_authentication(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket(client)
    client.cookies.clear()

    response = client.post(f"/tickets/{ticket_id}/replies", data={"body": "no auth"})

    assert response.status_code == 403


def test_reply_attaches_to_ticket_with_author_and_timestamp(client, agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id = create_ticket(client)

    response = client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Looking into it now.", "is_internal": "on"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    reply = db_session.query(Reply).filter(Reply.ticket_id == ticket_id).one()
    assert reply.ticket_id == ticket_id
    assert reply.body == "Looking into it now."
    assert reply.author_id == agent_user.id
    assert reply.is_internal is True
    assert reply.created_at is not None


def test_reply_attaches_to_correct_ticket_when_multiple_exist(client, agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_a = create_ticket(client)
    ticket_b = create_ticket(client, data={**TICKET_DATA, "subject": "Second ticket"})

    client.post(
        f"/tickets/{ticket_b}/replies",
        data={"body": "Reply for ticket B only."},
        follow_redirects=False,
    )

    replies_a = db_session.query(Reply).filter(Reply.ticket_id == ticket_a).all()
    replies_b = db_session.query(Reply).filter(Reply.ticket_id == ticket_b).all()
    assert replies_a == []
    assert len(replies_b) == 1
    assert replies_b[0].body == "Reply for ticket B only."


def test_reply_without_is_internal_defaults_to_customer_visible(client, agent_user, login_as, db_session):
    login_as(agent_user)
    ticket_id = create_ticket(client)

    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "We refunded the duplicate charge."},
        follow_redirects=False,
    )

    reply = db_session.query(Reply).filter(Reply.ticket_id == ticket_id).one()
    assert reply.is_internal is False


def test_supervisor_can_also_reply(client, supervisor_user, login_as, db_session):
    login_as(supervisor_user)
    ticket_id = create_ticket(client)

    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Supervisor reply."},
        follow_redirects=False,
    )

    reply = db_session.query(Reply).filter(Reply.ticket_id == ticket_id).one()
    assert reply.author_id == supervisor_user.id


def test_replies_shown_in_chronological_order_and_distinguish_internal(client, agent_user, login_as):
    login_as(agent_user)
    ticket_id = create_ticket(client)

    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "First reply, customer-visible."},
        follow_redirects=False,
    )
    client.post(
        f"/tickets/{ticket_id}/replies",
        data={"body": "Second reply, internal note.", "is_internal": "on"},
        follow_redirects=False,
    )

    detail = client.get(f"/tickets/{ticket_id}")
    body = detail.text

    first_pos = body.index("First reply, customer-visible.")
    second_pos = body.index("Second reply, internal note.")
    assert first_pos < second_pos

    assert "Internal note" in body
    assert "Customer-visible" in body
