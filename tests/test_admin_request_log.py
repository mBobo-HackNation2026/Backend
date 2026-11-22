from fastapi.testclient import TestClient

from app.core.config import get_settings

settings = get_settings()

PATERNITY_LEAVE_CODE = "urlop_ojcowski"


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/admin/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    return response.json()["access_token"]


def test_eligibility_check_is_logged_and_visible_in_request_log(client: TestClient) -> None:
    client.post(
        f"/api/v1/eligibility/check/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "father_insured": True, "child_age_months": 2},
    )

    token = _admin_token(client)
    response = client.get(
        f"/api/v1/admin/request-log?benefit_code={PATERNITY_LEAVE_CODE}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) >= 1
    assert all(entry["benefit_code"] == PATERNITY_LEAVE_CODE for entry in entries)
    assert all(entry["endpoint"] == "eligibility_check" for entry in entries)
    assert all(entry["status_code"] == 200 for entry in entries)


def test_calculate_is_logged_with_calculate_endpoint_label(client: TestClient) -> None:
    client.post(
        f"/api/v1/benefits/calculate/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "average_monthly_income_zl": "6000.00"},
    )

    token = _admin_token(client)
    response = client.get(
        f"/api/v1/admin/request-log?benefit_code={PATERNITY_LEAVE_CODE}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    entries = response.json()
    assert any(entry["endpoint"] == "calculate" for entry in entries)


def test_request_log_detail_includes_full_payloads(client: TestClient) -> None:
    client.post(
        f"/api/v1/eligibility/check/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "father_insured": True, "child_age_months": 2},
    )
    token = _admin_token(client)
    list_response = client.get(
        f"/api/v1/admin/request-log?benefit_code={PATERNITY_LEAVE_CODE}",
        headers={"Authorization": f"Bearer {token}"},
    )
    entry_id = list_response.json()[0]["id"]

    response = client.get(
        f"/api/v1/admin/request-log/{entry_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_payload"]["children_count"] == 1
    assert "status" in body["response_payload"]


def test_request_log_detail_unknown_id_returns_404(client: TestClient) -> None:
    token = _admin_token(client)
    response = client.get(
        "/api/v1/admin/request-log/999999999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_request_log_requires_admin_auth(client: TestClient) -> None:
    response = client.get("/api/v1/admin/request-log")

    assert response.status_code == 401
