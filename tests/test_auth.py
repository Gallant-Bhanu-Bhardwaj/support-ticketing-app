def test_login_success_sets_cookie(client, agent_user):
    response = client.post(
        "/auth/login",
        data={"email": agent_user.email, "password": "secret123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "access_token" in response.cookies


def test_login_failure_wrong_password(client, agent_user):
    response = client.post(
        "/auth/login",
        data={"email": agent_user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "access_token" not in response.cookies


def test_login_failure_unknown_email(client):
    response = client.post(
        "/auth/login",
        data={"email": "nobody@example.com", "password": "whatever"},
    )

    assert response.status_code == 401


def test_protected_route_without_token_is_unauthorized(client):
    response = client.get("/dashboard")

    assert response.status_code == 401


def test_protected_route_with_valid_token_succeeds(client, agent_user):
    login_response = client.post(
        "/auth/login",
        data={"email": agent_user.email, "password": "secret123"},
        follow_redirects=False,
    )
    client.cookies.set("access_token", login_response.cookies["access_token"])

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert agent_user.email in response.text


def test_role_dependency_blocks_agent_from_supervisor_route(client, agent_user):
    login_response = client.post(
        "/auth/login",
        data={"email": agent_user.email, "password": "secret123"},
        follow_redirects=False,
    )
    client.cookies.set("access_token", login_response.cookies["access_token"])

    response = client.get("/admin")

    assert response.status_code == 403


def test_role_dependency_allows_supervisor_on_supervisor_route(client, supervisor_user):
    login_response = client.post(
        "/auth/login",
        data={"email": supervisor_user.email, "password": "secret123"},
        follow_redirects=False,
    )
    client.cookies.set("access_token", login_response.cookies["access_token"])

    response = client.get("/admin")

    assert response.status_code == 200
