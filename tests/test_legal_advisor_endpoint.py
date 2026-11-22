"""Testy dla POST /api/v1/legal-advisor/explain/{benefit_code} (eBobo Legal
Intelligence, Funkcja 1). Dostawca AI jest zawsze mockowany (monkeypatch na
app.legal_advisor.service.request_json_completion) - żadne testy nie wykonują
prawdziwych, płatnych wywołań do OpenRouter."""

import pytest
from fastapi.testclient import TestClient

from app.ai_provider.client import AIProviderUnavailableError
from app.legal_advisor import service as legal_advisor_service

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
REHABILITATION_BENEFIT_CODE = "swiadczenie_rehabilitacyjne"


def _ai_response(**overrides) -> dict:
    base = {
        "explanation": "Brakuje informacji o ubezpieczeniu w dniu porodu.",
        "missing_data_explained": ["Status ubezpieczenia w dniu porodu"],
        "suggested_next_steps": ["Sprawdź status ubezpieczenia i spróbuj ponownie."],
        "other_benefits_to_check": [],
        "cited_legal_basis": [],
        "requires_additional_verification": False,
    }
    base.update(overrides)
    return base


def test_explain_unknown_benefit_code_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/legal-advisor/explain/nieistniejace_swiadczenie",
        json={"children_count": 1},
    )

    assert response.status_code == 404


def test_explain_requires_verification_uses_real_engine_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["ai_available"] is True
    assert body["source"] == "ai"
    assert body["explanation"]
    assert body["request_log_entry_id"] is not None


def test_explain_not_eligible_uses_real_engine_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(explanation="Termin na wniosek już minął."),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{REHABILITATION_BENEFIT_CODE}",
        json={
            "children_count": 1,
            "sickness_benefit_period_exhausted": True,
            "medical_prognosis_recovery_possible": True,
            "excluded_from_rehabilitation_benefit": True,
            "is_pregnant": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["source"] == "ai"


def test_explain_drops_unverified_legal_citation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A citation the AI invents (not present in the benefit's actual legal_basis)
    must never reach the user as a verified citation - it is silently dropped and
    forces requires_additional_verification=True."""
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(
            cited_legal_basis=["ustawa zasiłkowa art. 999 ust. 99 (zmyślony przepis)"],
            requires_additional_verification=False,
        ),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified_legal_basis"] == []
    assert body["requires_additional_verification"] is True


def test_explain_keeps_citation_that_matches_rule_legal_basis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules_response = client.get(f"/api/v1/formalities/{MATERNITY_LEAVE_CODE}")
    real_citation = rules_response.json()["legal_basis"][0]

    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(cited_legal_basis=[real_citation]),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified_legal_basis"] == [real_citation]
    assert body["requires_additional_verification"] is False


def test_explain_falls_back_when_ai_provider_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*_args, **_kwargs):
        raise AIProviderUnavailableError("brak klucza")

    monkeypatch.setattr(legal_advisor_service, "request_json_completion", _raise)

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_available"] is False
    assert body["source"] == "fallback"
    assert body["status"] == "requires_verification"
    assert body["explanation"]


def test_explain_falls_back_when_ai_response_fails_schema_validation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed AI response (missing the required 'explanation' field) must not
    crash the request - it is treated like a provider failure and falls back."""
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: {"missing_data_explained": ["coś"]},
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_available"] is False
    assert body["source"] == "fallback"
