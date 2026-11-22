"""Testy dla eBobo Legal Intelligence, Etap 3: wykrywanie sygnałów jakościowych,
deduplikacja/grupowanie, wewnętrzna kolejka i analiza AI (OpenRouter zawsze mockowany).
Reużywa helpery sesji/admin tokenu z test_legal_feedback_endpoint.py/
test_admin_legal_feedback.py."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.engine_quality import service as engine_quality_service
from app.legal_advisor import service as legal_advisor_service

settings = get_settings()

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
PATERNITY_LEAVE_CODE = "urlop_ojcowski"


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/admin/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    return response.json()["access_token"]


def _session_token(client: TestClient) -> str:
    return client.post("/api/v1/auth/session").json()["access_token"]


def _case_analysis_ai_response(**overrides) -> dict:
    base = {
        "classification": "possible_rule_gap",
        "summary": "Możliwa luka.",
        "potential_issue": "Opis potencjalnego problemu.",
        "required_information": [],
        "cited_fragment_ids": [],
        "recommended_admin_action": "Zweryfikuj ręcznie.",
    }
    base.update(overrides)
    return base


# --- unsupported_case: wired on unknown benefit_code in /eligibility/check ---


def test_unknown_benefit_code_creates_unsupported_case_signal(client: TestClient) -> None:
    response = client.post(
        "/api/v1/eligibility/check/nieistniejace_swiadczenie_xyz",
        json={"children_count": 1},
    )
    assert response.status_code == 404

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    assert any(c["benefit_code"] == "nieistniejace_swiadczenie_xyz" for c in cases)


def test_repeated_unknown_benefit_code_dedupes_into_one_case_with_incrementing_count(
    client: TestClient,
) -> None:
    for _ in range(2):
        client.post(
            "/api/v1/eligibility/check/kolejny_nieznany_kod",
            json={"children_count": 1},
        )

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    matching = [c for c in cases if c["benefit_code"] == "kolejny_nieznany_kod"]
    assert len(matching) == 1
    assert matching[0]["occurrence_count"] == 2


def test_different_unsupported_benefit_codes_create_separate_cases(client: TestClient) -> None:
    client.post("/api/v1/eligibility/check/nieznany_a", json={"children_count": 1})
    client.post("/api/v1/eligibility/check/nieznany_b", json={"children_count": 1})

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    codes = {c["benefit_code"] for c in cases}
    assert "nieznany_a" in codes
    assert "nieznany_b" in codes


def test_occurrence_count_reaching_threshold_escalates_priority_to_high(
    client: TestClient,
) -> None:
    for _ in range(3):
        client.post(
            "/api/v1/eligibility/check/eskalowany_kod_testowy",
            json={"children_count": 1},
        )

    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case", headers=headers
    ).json()
    case = next(c for c in cases if c["benefit_code"] == "eskalowany_kod_testowy")

    assert case["occurrence_count"] == 3
    assert case["priority"] == "high"

    detail = client.get(
        f"/api/v1/admin/engine-quality/cases/{case['id']}", headers=headers
    ).json()
    assert any(
        h["field_changed"] == "priority" and h["changed_by"] == "system"
        for h in detail["history"]
    )


# --- missing_legal_knowledge: wired in /legal-advisor/explain when no fragments ---


def test_legal_advisor_without_fragments_creates_missing_legal_knowledge_signal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service, "_collect_candidate_fragments", lambda *_a, **_k: []
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "father_insured": True, "child_age_months": 2},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "fallback"

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=missing_legal_knowledge",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    assert any(c["benefit_code"] == PATERNITY_LEAVE_CODE for c in cases)


# --- user_reported_discrepancy: wired in POST /legal-feedback ---


def test_legal_feedback_submission_creates_user_reported_discrepancy_signal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_a, **_kw: {
            "explanation": "x",
            "missing_data_explained": [],
            "suggested_next_steps": [],
            "other_benefits_to_check": [],
            "cited_fragment_ids": [],
            "requires_additional_verification": False,
        },
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
            "feedback_type": "zus_discrepancy",
            "user_comment": "ZUS powiedział co innego.",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert feedback_response.status_code == 201
    feedback_id = feedback_response.json()["id"]

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=user_reported_discrepancy",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    matching = next(c for c in cases if c["legal_feedback_id"] == feedback_id)
    assert matching["request_log_entry_id"] == entry_id
    assert matching["benefit_code"] == MATERNITY_LEAVE_CODE


# --- Admin API: auth, list/filter, detail, status/priority, analyze ---


def test_list_engine_quality_cases_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/admin/engine-quality/cases")
    assert response.status_code == 401


def test_get_case_detail_unknown_id_returns_404(client: TestClient) -> None:
    admin_token = _admin_token(client)
    response = client.get(
        "/api/v1/admin/engine-quality/cases/999999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


def _create_a_case_and_get_id(client: TestClient) -> int:
    client.post("/api/v1/eligibility/check/kod_do_statusu_testowego", json={"children_count": 1})
    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    return next(c for c in cases if c["benefit_code"] == "kod_do_statusu_testowego")["id"]


def test_update_status_requires_auth(client: TestClient) -> None:
    case_id = _create_a_case_and_get_id(client)
    response = client.patch(
        f"/api/v1/admin/engine-quality/cases/{case_id}/status", json={"status": "closed"}
    )
    assert response.status_code == 401


def test_update_status_changes_status_and_records_history(client: TestClient) -> None:
    case_id = _create_a_case_and_get_id(client)
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.patch(
        f"/api/v1/admin/engine-quality/cases/{case_id}/status",
        json={"status": "under_review", "reason": "Przyjęte do przeglądu."},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "under_review"
    history_entry = next(h for h in body["history"] if h["field_changed"] == "status")
    assert history_entry["old_value"] == "new"
    assert history_entry["new_value"] == "under_review"
    assert history_entry["changed_by"] == settings.admin_username
    assert history_entry["reason"] == "Przyjęte do przeglądu."


def test_update_priority_changes_priority_and_records_history(client: TestClient) -> None:
    case_id = _create_a_case_and_get_id(client)
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.patch(
        f"/api/v1/admin/engine-quality/cases/{case_id}/priority",
        json={"priority": "high", "reason": "Dotyczy wielu spraw."},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == "high"
    history_entry = next(h for h in body["history"] if h["field_changed"] == "priority")
    assert history_entry["old_value"] == "medium"
    assert history_entry["new_value"] == "high"
    assert history_entry["changed_by"] == settings.admin_username


def test_analyze_case_requires_auth(client: TestClient) -> None:
    case_id = _create_a_case_and_get_id(client)
    response = client.post(f"/api/v1/admin/engine-quality/cases/{case_id}/analyze")
    assert response.status_code == 401


def test_analyze_case_unknown_id_returns_404(client: TestClient) -> None:
    admin_token = _admin_token(client)
    response = client.post(
        "/api/v1/admin/engine-quality/cases/999999999/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


def test_analyze_case_completed_does_not_change_case_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = _create_a_case_and_get_id(client)
    monkeypatch.setattr(
        engine_quality_service,
        "request_json_completion",
        lambda *_a, **_kw: _case_analysis_ai_response(),
    )
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = client.post(
        f"/api/v1/admin/engine-quality/cases/{case_id}/analyze", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "completed"
    assert body["classification"] == "possible_rule_gap"
    assert body["requires_human_review"] is True

    detail = client.get(
        f"/api/v1/admin/engine-quality/cases/{case_id}", headers=headers
    ).json()
    assert detail["status"] == "new"  # analysis alone never changes status
    assert len(detail["analyses"]) == 1


def test_analyze_case_drops_citation_outside_offered_fragments(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = _create_a_case_and_get_id(client)
    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    monkeypatch.setattr(
        engine_quality_service,
        "request_json_completion",
        lambda *_a, **_kw: _case_analysis_ai_response(cited_fragment_ids=["zmyslony_999"]),
    )

    response = client.post(
        f"/api/v1/admin/engine-quality/cases/{case_id}/analyze", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["verified_source_ids"] == []


def test_analyze_case_handles_ai_provider_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai_provider.client import AIProviderUnavailableError

    case_id = _create_a_case_and_get_id(client)

    def _raise(*_args, **_kwargs):
        raise AIProviderUnavailableError("brak klucza")

    monkeypatch.setattr(engine_quality_service, "request_json_completion", _raise)
    admin_token = _admin_token(client)

    response = client.post(
        f"/api/v1/admin/engine-quality/cases/{case_id}/analyze",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_status"] == "failed"
    assert body["classification"] is None
    assert body["error_message"]
