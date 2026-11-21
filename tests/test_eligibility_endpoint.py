from fastapi.testclient import TestClient

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
ALTERNATIVE_BENEFIT_CODE = "zasilek_w_wysokosci_zasilku_macierzynskiego"


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
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] is None
    assert body["plan"]["duration_description"] == "do dnia porodu"
    assert body["benefit_code"] == ALTERNATIVE_BENEFIT_CODE
