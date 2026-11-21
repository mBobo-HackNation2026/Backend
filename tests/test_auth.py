from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.security import require_authenticated_user
from app.core.config import get_settings
from app.db.models.user import AuthStatus, User


def _expired_token_for(user_id: str, status_: AuthStatus, token_version: int = 0) -> str:
    """Build a token identical in shape to create_user_token's, but already expired -
    used to test the /auth/refresh path, which must accept exactly this case."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "status": status_.value,
        "exp": datetime.now(UTC) - timedelta(minutes=1),
        "type": "user",
        "tv": token_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


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


def test_refresh_issues_new_token_with_same_user_id(client: TestClient) -> None:
    session = client.post("/api/v1/auth/session").json()

    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == session["user_id"]
    assert body["status"] == "anonymous"

    settings = get_settings()
    decoded = jwt.decode(body["access_token"], settings.secret_key, algorithms=["HS256"])
    assert decoded["sub"] == session["user_id"]
    assert decoded["tv"] == 0


def test_refresh_preserves_authenticated_status(client: TestClient) -> None:
    session = client.post("/api/v1/auth/session").json()
    login = client.post(
        "/api/v1/auth/mobywatel/login",
        json={},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    ).json()

    refreshed = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    ).json()

    assert refreshed["status"] == "authenticated"
    assert refreshed["user_id"] == session["user_id"]

    me_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refreshed['access_token']}"}
    )
    assert me_response.json()["first_name"] == "Jan"


def test_refresh_works_even_with_already_expired_token(client: TestClient) -> None:
    session = client.post("/api/v1/auth/session").json()
    expired_token = _expired_token_for(session["user_id"], AuthStatus.anonymous)

    # The expired token is rejected by the ordinary auth dependency...
    me_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert me_response.status_code == 401

    # ...but /auth/refresh accepts it specifically because it's expired, not despite it.
    refresh_response = client.post(
        "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["user_id"] == session["user_id"]


def test_logout_invalidates_old_token_and_returns_new_anonymous_session(
    client: TestClient,
) -> None:
    session = client.post("/api/v1/auth/session").json()
    login = client.post(
        "/api/v1/auth/mobywatel/login",
        json={},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    ).json()

    logout_response = client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {login['access_token']}"}
    )

    assert logout_response.status_code == 200
    new_session = logout_response.json()
    assert new_session["status"] == "anonymous"
    assert new_session["user_id"] != session["user_id"]

    old_token_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"}
    )
    assert old_token_response.status_code == 401

    new_token_response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_session['access_token']}"}
    )
    assert new_token_response.status_code == 200
    assert new_token_response.json()["user_id"] == new_session["user_id"]


def test_refresh_rejects_token_after_logout(client: TestClient) -> None:
    session = client.post("/api/v1/auth/session").json()
    client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {session['access_token']}"}
    )

    response = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )

    assert response.status_code == 401


def test_logout_without_token_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 401
