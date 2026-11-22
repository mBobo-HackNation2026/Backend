"""Testy dla POST /api/v1/legal-advisor/explain/{benefit_code} (eBobo Legal
Intelligence, Funkcja 1 - w tym "minimalny RAG" z app/legal_knowledge). Dostawca AI
jest zawsze mockowany (monkeypatch na app.legal_advisor.service.request_json_completion)
- żadne testy nie wykonują prawdziwych, płatnych wywołań do OpenRouter."""

import pytest
from fastapi.testclient import TestClient

from app.ai_provider.client import AIProviderUnavailableError
from app.legal_advisor import service as legal_advisor_service
from app.legal_knowledge.repository import get_fragments_for_benefit

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
REHABILITATION_BENEFIT_CODE = "swiadczenie_rehabilitacyjne"
PATERNITY_LEAVE_CODE = "urlop_ojcowski"


def _ai_response(**overrides) -> dict:
    base = {
        "explanation": "Brakuje informacji o ubezpieczeniu w dniu porodu.",
        "missing_data_explained": ["Status ubezpieczenia w dniu porodu"],
        "suggested_next_steps": [],
        "other_benefits_to_check": [],
        "cited_fragment_ids": [],
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
        lambda *_args, **_kwargs: _ai_response(explanation="Warunki nie zostały spełnione."),
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


def test_explain_selects_fragments_matching_the_benefit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fragments offered to the AI as grounding must actually belong to the
    benefit being explained - not some unrelated benefit's legal basis."""
    captured_prompts: list[str] = []

    def _capture(_system_prompt: str, user_prompt: str) -> dict:
        captured_prompts.append(user_prompt)
        return _ai_response()

    monkeypatch.setattr(legal_advisor_service, "request_json_completion", _capture)

    client.post(
        f"/api/v1/legal-advisor/explain/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "father_insured": True, "child_age_months": 2},
    )

    expected_fragment_ids = {f.id for f in get_fragments_for_benefit(PATERNITY_LEAVE_CODE)}
    assert expected_fragment_ids
    prompt = captured_prompts[0]
    for fragment_id in expected_fragment_ids:
        assert fragment_id in prompt
    # A fragment belonging only to a different benefit must not leak in.
    assert "kp_art_1802_par1_3" not in prompt


def test_explain_sends_real_fragment_content_not_just_a_label(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_prompts: list[str] = []

    def _capture(_system_prompt: str, user_prompt: str) -> dict:
        captured_prompts.append(user_prompt)
        return _ai_response()

    monkeypatch.setattr(legal_advisor_service, "request_json_completion", _capture)

    client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    fragment = next(
        f for f in get_fragments_for_benefit(MATERNITY_LEAVE_CODE) if f.id == "kp_art_180_par1"
    )
    assert fragment.content in captured_prompts[0]


def test_explain_drops_unverified_cited_fragment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fragment id the AI invents (not among the ones actually offered) must never
    reach the user as a verified citation - it is silently dropped and forces
    requires_additional_verification=True."""
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(cited_fragment_ids=["nieistniejacy_fragment_999"]),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified_legal_basis"] == []
    assert body["requires_additional_verification"] is True


def test_explain_keeps_citation_that_matches_a_real_fragment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(cited_fragment_ids=["kp_art_180_par1"]),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["verified_legal_basis"]) == 1
    assert "wymiar urlopu macierzyńskiego" in body["verified_legal_basis"][0]
    assert body["requires_additional_verification"] is False


def test_explain_drops_unconfirmed_recommendation_citing_invalid_fragment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A suggested next step citing a fragment outside the offered set must be
    dropped entirely (never shown as if confirmed), and forces verification."""
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(
            suggested_next_steps=[
                {
                    "text": "Zrobiono by to na podstawie zmyślonego przepisu.",
                    "supporting_fragment_ids": ["zmyslony_przepis"],
                }
            ]
        ),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Zrobiono by to na podstawie zmyślonego przepisu." not in body["suggested_next_steps"]
    assert body["requires_additional_verification"] is True


def test_explain_keeps_recommendation_grounded_in_a_real_fragment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(
            suggested_next_steps=[
                {
                    "text": "Sprawdź wymiar urlopu macierzyńskiego.",
                    "supporting_fragment_ids": ["kp_art_180_par1"],
                }
            ]
        ),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert "Sprawdź wymiar urlopu macierzyńskiego." in body["suggested_next_steps"]
    assert body["requires_additional_verification"] is False


def test_explain_drops_unknown_other_benefit_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        legal_advisor_service,
        "request_json_completion",
        lambda *_args, **_kwargs: _ai_response(
            other_benefits_to_check=["urlop_ojcowski", "cos_wymyslonego"]
        ),
    )

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["other_benefits_to_check"] == ["urlop_ojcowski"]


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
    assert any("ZUS" in step for step in body["suggested_next_steps"])


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


def test_explain_handles_benefit_with_no_legal_fragments_without_calling_ai(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("AI should not be called when there are no legal fragments")

    monkeypatch.setattr(legal_advisor_service, "request_json_completion", _fail_if_called)
    monkeypatch.setattr(legal_advisor_service, "_collect_candidate_fragments", lambda *_a, **_k: [])

    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert body["requires_additional_verification"] is True
    assert body["verified_legal_basis"] == []
