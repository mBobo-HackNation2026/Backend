"""Testy dla panelu administratora Etap 2 Faza B: przegląd zgłoszeń, analiza AI
(OpenRouter, zawsze mockowany), zmiana statusu z historią. Reużywa ten sam
sposób zdobycia referencyjnego request_log_entry_id co tests/test_legal_feedback_endpoint.py
(przez /legal-advisor/explain, mockując app.legal_advisor.service.request_json_completion)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.legal_advisor import service as legal_advisor_service
from app.legal_feedback import admin_service as legal_feedback_admin_service

settings = get_settings()

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/admin/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    return response.json()["access_token"]


def _explain_ai_response(**overrides) -> dict:
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


def _submit_feedback_and_get_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, *, feedback_type: str = "incorrect_result"
) -> tuple[int, str]:
    """Returns (feedback_id, session_token)."""
    monkeypatch.setattr(
        legal_advisor_service, "request_json_completion", lambda *_a, **_kw: _explain_ai_response()
    )
    user_token = _session_token(client)
    explain_response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    entry_id = explain_response.json()["request_log_entry_id"]

    feedback_response = client.post(
        "/api/v1/legal-feedback",
        json={
            "request_log_entry_id": entry_id,
            "feedback_type": feedback_type,
            "user_comment": "ZUS potwierdził moje prawo, eBobo pokazuje inaczej.",
            "expected_result": "likely_eligible",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    return feedback_response.json()["id"], user_token


def _analysis_ai_response(**overrides) -> dict:
    base = {
        "classification": "possible_rule_gap",
        "summary": "Możliwa luka w regule.",
        "potential_issue": "Reguła może nie uwzględniać tej sytuacji.",
        "required_information": ["Data porodu"],
        "cited_fragment_ids": [],
        "recommended_admin_action": "Zweryfikuj ręcznie regułę.",
    }
    base.update(overrides)
    return base


def test_list_legal_feedback_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/admin/legal-feedback")

    assert response.status_code == 401


def test_list_legal_feedback_returns_submitted_entries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    admin_token = _admin_token(client)

    response = client.get(
        "/api/v1/admin/legal-feedback", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    entries = response.json()
    assert any(e["id"] == feedback_id for e in entries)


def test_list_legal_feedback_filters_by_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    matching = client.get(
        "/api/v1/admin/legal-feedback?status_filter=new", headers=headers
    ).json()
    assert any(e["id"] == feedback_id for e in matching)

    non_matching = client.get(
        "/api/v1/admin/legal-feedback?status_filter=closed", headers=headers
    ).json()
    assert all(e["id"] != feedback_id for e in non_matching)


def test_get_legal_feedback_detail_includes_original_evaluation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    admin_token = _admin_token(client)

    response = client.get(
        f"/api/v1/admin/legal-feedback/{feedback_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["original_evaluation"]["endpoint"] == "legal_advisor_explain"
    assert body["original_evaluation"]["benefit_code"] == MATERNITY_LEAVE_CODE
    assert body["analyses"] == []
    assert body["status_history"] == []


def test_get_legal_feedback_detail_unknown_id_returns_404(client: TestClient) -> None:
    admin_token = _admin_token(client)

    response = client.get(
        "/api/v1/admin/legal-feedback/999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


def test_analyze_requires_auth(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)

    response = client.post(f"/api/v1/admin/legal-feedback/{feedback_id}/analyze")

    assert response.status_code == 401


def test_analyze_unknown_feedback_returns_404(client: TestClient) -> None:
    admin_token = _admin_token(client)

    response = client.post(
        "/api/v1/admin/legal-feedback/999999999/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


def test_analyze_completed_does_not_change_feedback_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    monkeypatch.setattr(
        legal_feedback_admin_service,
        "request_json_completion",
        lambda *_a, **_kw: _analysis_ai_response(),
    )
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.post(
        f"/api/v1/admin/legal-feedback/{feedback_id}/analyze", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "completed"
    assert body["classification"] == "possible_rule_gap"
    assert body["requires_human_review"] is True
    assert body["model_id"]

    detail = client.get(f"/api/v1/admin/legal-feedback/{feedback_id}", headers=headers).json()
    assert detail["status"] == "new"  # unchanged - only an explicit PATCH can change it
    assert len(detail["analyses"]) == 1


def test_analyze_drops_citation_to_fragment_outside_offered_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    monkeypatch.setattr(
        legal_feedback_admin_service,
        "request_json_completion",
        lambda *_a, **_kw: _analysis_ai_response(cited_fragment_ids=["zmyslony_przepis_999"]),
    )
    admin_token = _admin_token(client)

    response = client.post(
        f"/api/v1/admin/legal-feedback/{feedback_id}/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "completed"
    assert body["verified_source_ids"] == []


def test_analyze_keeps_citation_matching_a_real_fragment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    monkeypatch.setattr(
        legal_feedback_admin_service,
        "request_json_completion",
        lambda *_a, **_kw: _analysis_ai_response(cited_fragment_ids=["kp_art_180_par1"]),
    )
    admin_token = _admin_token(client)

    response = client.post(
        f"/api/v1/admin/legal-feedback/{feedback_id}/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["verified_source_ids"] == ["kp_art_180_par1"]


def test_analyze_handles_ai_provider_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai_provider.client import AIProviderUnavailableError

    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)

    def _raise(*_args, **_kwargs):
        raise AIProviderUnavailableError("brak klucza")

    monkeypatch.setattr(legal_feedback_admin_service, "request_json_completion", _raise)
    admin_token = _admin_token(client)

    response = client.post(
        f"/api/v1/admin/legal-feedback/{feedback_id}/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "failed"
    assert body["classification"] is None
    assert body["summary"] is None
    assert body["error_message"]
    assert body["requires_human_review"] is True


def test_analyze_handles_malformed_ai_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    monkeypatch.setattr(
        legal_feedback_admin_service,
        "request_json_completion",
        lambda *_a, **_kw: {"summary": "brakuje wymaganych pól"},
    )
    admin_token = _admin_token(client)

    response = client.post(
        f"/api/v1/admin/legal-feedback/{feedback_id}/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "failed"
    assert body["classification"] is None


def test_running_analysis_twice_keeps_both_in_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    monkeypatch.setattr(
        legal_feedback_admin_service,
        "request_json_completion",
        lambda *_a, **_kw: _analysis_ai_response(),
    )
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    client.post(f"/api/v1/admin/legal-feedback/{feedback_id}/analyze", headers=headers)
    client.post(f"/api/v1/admin/legal-feedback/{feedback_id}/analyze", headers=headers)

    detail = client.get(f"/api/v1/admin/legal-feedback/{feedback_id}", headers=headers).json()
    assert len(detail["analyses"]) == 2


def test_update_status_requires_auth(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)

    response = client.patch(
        f"/api/v1/admin/legal-feedback/{feedback_id}/status", json={"status": "closed"}
    )

    assert response.status_code == 401


def test_update_status_unknown_feedback_returns_404(client: TestClient) -> None:
    admin_token = _admin_token(client)

    response = client.patch(
        "/api/v1/admin/legal-feedback/999999999/status",
        json={"status": "closed"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


def test_update_status_changes_status_and_records_history(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.patch(
        f"/api/v1/admin/legal-feedback/{feedback_id}/status",
        json={"status": "confirmed_issue", "reason": "Potwierdzone po analizie ręcznej."},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed_issue"
    assert len(body["status_history"]) == 1
    history_entry = body["status_history"][0]
    assert history_entry["old_status"] == "new"
    assert history_entry["new_status"] == "confirmed_issue"
    assert history_entry["changed_by"] == settings.admin_username
    assert history_entry["reason"] == "Potwierdzone po analizie ręcznej."


def test_update_status_does_not_require_a_prior_analysis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running an AI analysis must never be a prerequisite for a human decision -
    the admin can close a case on their own judgement alone."""
    feedback_id, _ = _submit_feedback_and_get_id(client, monkeypatch)
    admin_token = _admin_token(client)

    response = client.patch(
        f"/api/v1/admin/legal-feedback/{feedback_id}/status",
        json={"status": "not_an_issue"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_an_issue"
