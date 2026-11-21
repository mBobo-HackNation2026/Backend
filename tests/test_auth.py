import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.security import require_authenticated_user
from app.db.models.user import AuthStatus, User


def test_create_session_returns_anonymous_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "anonymous"
    assert body["access_token"]
    assert body["user_id"]


def test_me_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_with_anonymous_token_returns_profile(client: TestClient) -> None:
    session = client.post("/api/v1/auth/session").json()

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == session["user_id"]
    assert body["status"] == "anonymous"
    assert body["first_name"] is None


def test_mobywatel_login_upgrades_session_to_authenticated(client: TestClient) -> None:
    session = client.post("/api/v1/auth/session").json()
    anon_token = session["access_token"]

    login_response = client.post(
        "/api/v1/auth/mobywatel/login",
        json={},
        headers={"Authorization": f"Bearer {anon_token}"},
    )

    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["status"] == "authenticated"
    assert login_body["user_id"] == session["user_id"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )
    me_body = me_response.json()
    assert me_body["status"] == "authenticated"
    assert me_body["first_name"] == "Jan"
    assert me_body["pesel"]


def test_require_authenticated_user_rejects_anonymous() -> None:
    anon_user = User(id="anon-1", status=AuthStatus.anonymous)

    with pytest.raises(HTTPException) as exc_info:
        require_authenticated_user(anon_user)

    assert exc_info.value.status_code == 403


def test_require_authenticated_user_accepts_authenticated() -> None:
    auth_user = User(id="auth-1", status=AuthStatus.authenticated)

    assert require_authenticated_user(auth_user) is auth_user
