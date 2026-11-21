from fastapi.testclient import TestClient


def test_check_eligibility_returns_likely_eligible_for_insured_mother(client: TestClient) -> None:
    response = client.post(
        "/api/v1/eligibility/check",
        json={"children_count": 1, "insured_at_birth": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 20
    assert body["benefit_code"] == "zasilek_macierzynski_urlop_macierzynski"


def test_check_eligibility_requires_verification_when_insurance_status_missing(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/eligibility/check", json={"children_count": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_verification"
    assert body["missing_data"]


def test_check_eligibility_rejects_zero_children_count(client: TestClient) -> None:
    response = client.post("/api/v1/eligibility/check", json={"children_count": 0})

    assert response.status_code == 422
