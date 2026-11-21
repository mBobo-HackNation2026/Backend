from fastapi.testclient import TestClient

from app.core.config import get_settings

settings = get_settings()


def test_login_with_invalid_credentials_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/admin/login",
        json={"username": "wrong", "password": "wrong"},
    )

    assert response.status_code == 401


def test_login_with_valid_credentials_returns_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/admin/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_dashboard_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/admin/dashboard")

    assert response.status_code == 401


def test_dashboard_with_valid_token_returns_modules(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/admin/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "modules" in body
