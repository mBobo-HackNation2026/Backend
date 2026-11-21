from fastapi.testclient import TestClient

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
ALTERNATIVE_BENEFIT_CODE = "zasilek_w_wysokosci_zasilku_macierzynskiego"
PATERNITY_LEAVE_CODE = "urlop_ojcowski"
STUB_BENEFIT_CODES = [
    "zasilek_chorobowy_w_ciazy",
    "uzupelniajacy_urlop_macierzynski",
    "urlop_rodzicielski",
    "urlop_na_warunkach_urlopu_macierzynskiego",
    "zasilek_pogrzebowy_martwe_urodzenie",
]


def test_check_eligibility_returns_likely_eligible_for_insured_mother(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 20
    assert body["benefit_code"] == MATERNITY_LEAVE_CODE


def test_check_eligibility_requires_verification_when_insurance_status_missing(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}", json={"children_count": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["missing_data"]


def test_check_eligibility_rejects_zero_children_count(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{MATERNITY_LEAVE_CODE}", json={"children_count": 0}
    )

    assert response.status_code == 422


def test_check_eligibility_unknown_benefit_code_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/eligibility/check/nieistniejace_swiadczenie",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 404


def test_check_eligibility_alternative_benefit_for_employer_liquidation(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{ALTERNATIVE_BENEFIT_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": False,
            "employment_ended_reason": "upadlosc_likwidacja_smierc_pracodawcy",
            "other_employment_secured": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] is None
    assert body["plan"]["duration_description"] == "do dnia porodu"
    assert body["benefit_code"] == ALTERNATIVE_BENEFIT_CODE


def test_check_eligibility_alternative_benefit_requires_verification_without_employment_field(
    client: TestClient,
) -> None:
    """Without other_employment_secured, the API must not guess likely_eligible - it
    must ask for that missing fact explicitly instead."""
    response = client.post(
        f"/api/v1/eligibility/check/{ALTERNATIVE_BENEFIT_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": False,
            "employment_ended_reason": "upadlosc_likwidacja_smierc_pracodawcy",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["plan"] is None
    assert any("inne zatrudnienie" in m for m in body["missing_data"])


def test_check_eligibility_paternity_leave_likely_eligible(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "father_insured": True, "child_age_months": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 2
    assert body["benefit_code"] == PATERNITY_LEAVE_CODE


def test_check_eligibility_paternity_leave_not_eligible_after_deadline(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{PATERNITY_LEAVE_CODE}",
        json={"children_count": 1, "father_insured": True, "child_age_months": 14},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["plan"] is None


def test_stub_benefits_are_registered_and_return_requires_verification(
    client: TestClient,
) -> None:
    """Each Phase 2 stub benefit must be reachable and honest about being a
    placeholder (requires_verification, never likely_eligible, with an explicit
    warning) - never a silent fake 'yes'."""
    for code in STUB_BENEFIT_CODES:
        response = client.post(
            f"/api/v1/eligibility/check/{code}",
            json={"children_count": 1, "insured_at_birth": True},
        )

        assert response.status_code == 200, code
        body = response.json()
        assert body["status"] == "requires_verification", code
        assert body["plan"] is None, code
        assert body["benefit_code"] == code
        assert any("TYMCZASOWA ODPOWIEDŹ ZASTĘPCZA" in w for w in body["warnings"]), code
