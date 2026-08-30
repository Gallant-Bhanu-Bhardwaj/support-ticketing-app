"""Regression coverage for app/core/templates.py's context processor.

Before this, current_user was only in a template's context if the route
handler put it there by hand, and three routes never did: GET /alerts,
GET /tickets/archived, GET /tickets/mine. Any template referencing
current_user on those pages would hit Jinja2's UndefinedError. The
context processor makes current_user available on every render
regardless of what the route passed in, so these are now covered.
"""

from starlette.requests import Request

from app.core.templates import _inject_current_user
from app.main import app


def _request(cookie_header: str | None = None) -> Request:
    headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "app": app})


def test_inject_current_user_resolves_the_logged_in_user(client, agent_user):
    login_response = client.post(
        "/auth/login",
        data={"email": agent_user.email, "password": "secret123"},
        follow_redirects=False,
    )
    token = login_response.cookies["access_token"]

    result = _inject_current_user(_request(f"access_token={token}"))

    assert result["current_user"] is not None
    assert result["current_user"].email == agent_user.email


def test_inject_current_user_is_none_with_no_cookie():
    result = _inject_current_user(_request())

    assert result["current_user"] is None


def test_inject_current_user_is_none_with_a_garbage_cookie():
    result = _inject_current_user(_request("access_token=not-a-real-token"))

    assert result["current_user"] is None


def test_alerts_page_renders_for_a_logged_in_agent(client, agent_user, login_as):
    login_as(agent_user)

    response = client.get("/alerts")

    assert response.status_code == 200


def test_archived_tickets_page_renders_for_a_logged_in_agent(client, agent_user, login_as):
    login_as(agent_user)

    response = client.get("/tickets/archived")

    assert response.status_code == 200


def test_my_tickets_page_renders_for_a_logged_in_agent(client, agent_user, login_as):
    login_as(agent_user)

    response = client.get("/tickets/mine")

    assert response.status_code == 200


def test_alerts_archived_and_mine_all_require_login_rather_than_rendering_logged_out(client):
    """These three routes gate on the mandatory get_current_user dependency,
    not get_current_user_optional -- so "logged out" for them means a 401
    before the template ever renders, not a page with current_user=None.
    The graceful-when-logged-out path is covered by the home/login page
    tests below, the pages that are actually reachable without auth."""
    for path in ("/alerts", "/tickets/archived", "/tickets/mine"):
        response = client.get(path)
        assert response.status_code == 401, path


def test_home_page_renders_with_no_current_user_when_logged_out(client):
    response = client.get("/")

    assert response.status_code == 200


def test_login_page_renders_with_no_current_user_when_logged_out(client):
    response = client.get("/auth/login")

    assert response.status_code == 200
