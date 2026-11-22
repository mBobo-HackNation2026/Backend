"""Testy dla eBobo Legal Intelligence, Etap 3.1: ustrukturyzowane markery
nieobsługiwanych przypadków prawnych, lepsza deduplikacja (problem_id), ochrona przed
wyścigiem żądań, rozdzielenie typów feedbacku i odporność na awarię monitoringu."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.db.models.engine_quality import (
    EngineQualityCase,
    EngineQualityCaseStatus,
    EngineQualitySignalType,
)
from app.engine_quality import service as engine_quality_service
from app.legal_advisor import service as legal_advisor_service

settings = get_settings()

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"


def _admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/admin/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    return response.json()["access_token"]


def _session_token(client: TestClient) -> str:
    return client.post("/api/v1/auth/session").json()["access_token"]


# --- Zadanie 1/2: ustrukturyzowany marker dla znanego, nieobsługiwanego przypadku ---


def test_naruszenie_prawa_wyrokiem_sadu_creates_unsupported_case_signal(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": False,
            "employment_ended_reason": "naruszenie_prawa_wyrokiem_sadu",
        },
    )

    assert response.status_code == 200
    body = response.json()
    # Zadanie 2: marker nigdy nie zmienia poprawnego wyniku oceny.
    assert body["status"] == "requires_verification"
    assert len(body["legal_limitation_markers"]) == 1
    assert body["legal_limitation_markers"][0]["rule_id"] == (
        "maternity_leave_naruszenie_prawa_wyrokiem_sadu_classification"
    )

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    matching = [
        c
        for c in cases
        if c["problem_id"] == "maternity_leave_naruszenie_prawa_wyrokiem_sadu_classification"
    ]
    assert len(matching) == 1
    assert matching[0]["benefit_code"] == MATERNITY_LEAVE_CODE


def test_ordinary_missing_field_does_not_create_a_signal(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["missing_fields"]
    assert body["legal_limitation_markers"] == []

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case&benefit_code="
        + MATERNITY_LEAVE_CODE,
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    assert not any(
        c["problem_id"] == "maternity_leave_naruszenie_prawa_wyrokiem_sadu_classification"
        for c in cases
    )


def test_correctly_handled_eligible_case_does_not_create_a_signal(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "likely_eligible"
    assert response.json()["legal_limitation_markers"] == []


# --- Zadanie 3: deduplikacja po problem_id ---


def test_identical_problem_dedupes_increments_occurrence_count(client: TestClient) -> None:
    payload = {
        "children_count": 1,
        "insured_at_birth": False,
        "employment_ended_reason": "naruszenie_prawa_wyrokiem_sadu",
    }
    client.post(f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}", json=payload)
    client.post(f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}", json=payload)

    admin_token = _admin_token(client)
    cases = client.get(
        "/api/v1/admin/engine-quality/cases?signal_type=unsupported_case",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    matching = [
        c
        for c in cases
        if c["problem_id"] == "maternity_leave_naruszenie_prawa_wyrokiem_sadu_classification"
    ]
    assert len(matching) == 1
    assert matching[0]["occurrence_count"] == 2


def test_different_problem_ids_for_same_benefit_and_rules_version_stay_separate() -> None:
    """Direct service-level test: two different problem_id values for the same
    signal_type/benefit_code/rules_version must produce two distinct cases, not merge
    into one - the exact gap Etap 3.1 closes in the group_key."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        case_a = engine_quality_service.record_signal(
            session,
            signal_type=EngineQualitySignalType.unsupported_case,
            benefit_code="kod_x",
            rules_version=1,
            problem_id="problem_a",
            reason="pierwszy problem",
        )
        case_b = engine_quality_service.record_signal(
            session,
            signal_type=EngineQualitySignalType.unsupported_case,
            benefit_code="kod_x",
            rules_version=1,
            problem_id="problem_b",
            reason="drugi problem",
        )

        assert case_a.id != case_b.id
        assert session.query(EngineQualityCase).filter_by(benefit_code="kod_x").count() == 2
    finally:
        session.close()
        engine.dispose()


# --- Zadanie 3: ochrona przed wyścigiem żądań ---


def test_concurrent_identical_signal_does_not_create_duplicate_case() -> None:
    """Simulates the race: another request already inserted a case for this group_key,
    but OUR own "does it already exist" check doesn't see it yet (stale read). The
    partial unique index must reject our INSERT, and record_signal must recover by
    updating the row the other request created, not crash or duplicate it."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        group_key = engine_quality_service._compute_group_key(
            EngineQualitySignalType.unsupported_case, "race_kod", None, None
        )
        winner = EngineQualityCase(
            signal_type=EngineQualitySignalType.unsupported_case,
            benefit_code="race_kod",
            reason="pierwsze żądanie wygrało wyścig",
            group_key=group_key,
            occurrence_count=1,
            status=EngineQualityCaseStatus.new,
        )
        session.add(winner)
        session.commit()

        real_find_open_case = engine_quality_service._find_open_case
        call_count = {"n": 0}

        def _pretend_missing_once(db, key):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return real_find_open_case(db, key)

        mp = pytest.MonkeyPatch()
        mp.setattr(engine_quality_service, "_find_open_case", _pretend_missing_once)
        try:
            result = engine_quality_service.record_signal(
                session,
                signal_type=EngineQualitySignalType.unsupported_case,
                benefit_code="race_kod",
                reason="drugie żądanie (wyścig)",
            )
        finally:
            mp.undo()

        assert result.id == winner.id
        assert result.occurrence_count == 2
        assert session.query(EngineQualityCase).filter_by(benefit_code="race_kod").count() == 1
    finally:
        session.close()
        engine.dispose()


# --- Zadanie 4: rozdzielenie typów feedbacku ---


def _explained_entry_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, token: str
) -> int:
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
    response = client.post(
        f"/api/v1/legal-advisor/explain/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response.json()["request_log_entry_id"]


@pytest.mark.parametrize(
    "feedback_type,expected_signal_type",
    [
        ("incorrect_result", "user_reported_discrepancy"),
        ("zus_discrepancy", "user_reported_discrepancy"),
        ("missing_case", "unsupported_case"),
    ],
)
def test_feedback_types_mapping_to_a_signal_create_one(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    feedback_type: str,
    expected_signal_type: str,
) -> None:
    token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, token)

    feedback_response = client.post(
        "/api/v1/legal-feedback",
        json={
            "request_log_entry_id": entry_id,
            "feedback_type": feedback_type,
            "user_comment": "Testowy komentarz.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    feedback_id = feedback_response.json()["id"]

    admin_token = _admin_token(client)
    cases = client.get(
        f"/api/v1/admin/engine-quality/cases?signal_type={expected_signal_type}",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    assert any(c["legal_feedback_id"] == feedback_id for c in cases)


@pytest.mark.parametrize("feedback_type", ["incorrect_explanation", "missing_input"])
def test_feedback_types_without_a_signal_mapping_create_no_case(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, feedback_type: str
) -> None:
    token = _session_token(client)
    entry_id = _explained_entry_id(client, monkeypatch, token)

    feedback_response = client.post(
        "/api/v1/legal-feedback",
        json={
            "request_log_entry_id": entry_id,
            "feedback_type": feedback_type,
            "user_comment": "Testowy komentarz.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    feedback_id = feedback_response.json()["id"]

    admin_token = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    for signal_type in ("user_reported_discrepancy", "unsupported_case", "missing_legal_knowledge"):
        cases = client.get(
            f"/api/v1/admin/engine-quality/cases?signal_type={signal_type}", headers=headers
        ).json()
        assert not any(c["legal_feedback_id"] == feedback_id for c in cases)


# --- Zadanie 5: odporność na awarię zapisu diagnostycznego ---


def test_eligibility_endpoint_survives_signal_recording_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("symulowana awaria monitoringu")

    monkeypatch.setattr(engine_quality_service, "record_signal", _boom)

    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": False,
            "employment_ended_reason": "naruszenie_prawa_wyrokiem_sadu",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "requires_verification"


def test_unsupported_benefit_code_still_returns_404_when_signal_recording_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("symulowana awaria monitoringu")

    monkeypatch.setattr(engine_quality_service, "record_signal", _boom)

    response = client.post(
        "/api/v1/eligibility/check/kod_awaria_monitoringu", json={"children_count": 1}
    )

    assert response.status_code == 404
