"""Testy dla POST /api/v1/legal-feedback (eBobo Legal Intelligence, Etap 2, Faza A).

Obecnie jedyny endpoint zwracający request_log_entry_id w odpowiedzi to
/legal-advisor/explain/{benefit_code} - dlatego testy zdobywają referencyjny id
przez tę ścieżkę (zgodnie z zamierzonym przepływem: wyjaśnienie -> użytkownik się
nie zgadza -> zgłoszenie). Dostawca AI jest zawsze mockowany."""

import pytest
from fastapi.testclient import TestClient

from app.legal_advisor import service as legal_advisor_service

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"


def _ai_response(**overrides) -> dict:
    base = {
        "explanation": "Wyjaśnienie testowe.",
        "missing_data_explained": [],
        "suggested_next_steps": [],
        "other_benefits_to_check": [],
        "cited_fragment_ids": [],
        "requires_additional_verification": False,
    }
    base.update(overrides)
    return base


def _session_token(client: TestClient) -> str:
    response = client.post("/api/v1/auth/session")
    return response.json()["access_token"]


def _explained_entry_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, token: str | None
) -> int:
    monkeypatch.setattr(
        legal_advisor_service, "request_json_completion", lambda *_a, **_kw: _ai_response()
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
        headers=headers,
    )
    return response.json()["request_log_entry_id"]


def _feedback_payload(request_log_entry_id: int, **overrides) -> dict:
    base = {
        "request_log_entry_id": request_log_entry_id,
        "feedback_type": "incorrect_result",
        "user_comment": "ZUS potwierdził moje prawo, eBobo pokazuje inaczej.",
        "expected_result": "likely_eligible",
    }
    base.update(overrides)
    return base


def test_create_feedback_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/legal-feedback", json=_feedback_payload(1))

    assert response.status_code == 401


def test_create_feedback_for_own_evaluation_succeeds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, token)

    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(entry_id),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["request_log_entry_id"] == entry_id
    assert body["benefit_code"] == MATERNITY_LEAVE_CODE
    assert body["feedback_type"] == "incorrect_result"
    assert body["expected_result"] == "likely_eligible"
    assert body["status"] == "new"
    assert body["rules_version"] is not None


def test_create_feedback_rejects_entry_belonging_to_another_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, owner_token)

    other_token = _session_token(client)
    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(entry_id),
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404


def test_create_feedback_rejects_entry_with_no_owner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evaluation made anonymously (no token sent) has user_id=None and must
    never be claimable by feedback, even by a real, later-authenticated session."""
    anonymous_entry_id = _explained_entry_id(client, monkeypatch, token=None)

    token = _session_token(client)
    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(anonymous_entry_id),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_create_feedback_rejects_unknown_entry_id(client: TestClient) -> None:
    token = _session_token(client)

    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(999999999),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_create_feedback_rejects_invalid_feedback_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, token)

    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(entry_id, feedback_type="something_made_up"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_feedback_rejects_empty_comment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, token)

    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(entry_id, user_comment=""),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_feedback_rejects_overly_long_comment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, token)

    response = client.post(
        "/api/v1/legal-feedback",
        json=_feedback_payload(entry_id, user_comment="x" * 2001),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_feedback_rate_limited_after_threshold(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _session_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(10):
        entry_id = _explained_entry_id(client, monkeypatch, token)
        response = client.post(
            "/api/v1/legal-feedback", json=_feedback_payload(entry_id), headers=headers
        )
        assert response.status_code == 201

    entry_id = _explained_entry_id(client, monkeypatch, token)
    response = client.post(
        "/api/v1/legal-feedback", json=_feedback_payload(entry_id), headers=headers
    )

    assert response.status_code == 429


def test_existing_eligibility_endpoint_still_works_without_auth(client: TestClient) -> None:
    """Regression: eligibility/check must remain fully callable anonymously - the new
    optional-auth wiring must never require a token here."""
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200


def test_existing_calculate_endpoint_still_works_without_auth(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/benefits/calculate/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "average_monthly_income_zl": "6000.00"},
    )

    assert response.status_code == 200


def test_eligibility_endpoint_treats_garbage_bearer_token_as_anonymous(
    client: TestClient,
) -> None:
    """get_current_user_optional must swallow a bad/expired/garbage token as
    'anonymous', never surface it as a 401 - these endpoints are not auth-gated."""
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 200
