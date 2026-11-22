from fastapi.testclient import TestClient

from app.mock_zus.profiles import MOCK_ZUS_PROFILES


def test_list_profiles_returns_all_registered_profiles(client: TestClient) -> None:
    response = client.get("/api/v1/mock-zus/profiles")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(MOCK_ZUS_PROFILES)
    returned_ids = {entry["profile_id"] for entry in body}
    assert returned_ids == set(MOCK_ZUS_PROFILES.keys())
    for entry in body:
        assert entry["label"]
        assert entry["description"]


def test_get_profile_data_marks_source_as_simulated(client: TestClient) -> None:
    response = client.get("/api/v1/mock-zus/profiles/matka_umowa_o_prace_standard")

    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "mock_zus_simulated"
    assert body["is_currently_insured"] is True
    assert body["current_insurance_title"] == "umowa_o_prace"
    assert any("symulowane" in w for w in body["warnings"])


def test_get_profile_data_unknown_profile_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/mock-zus/profiles/nieistniejacy_profil")

    assert response.status_code == 404


def test_get_profile_data_debt_profile_has_nonzero_debt(client: TestClient) -> None:
    response = client.get("/api/v1/mock-zus/profiles/dzialalnosc_z_zadluzeniem")

    assert response.status_code == 200
    body = response.json()
    assert body["debt_amount_zl"] == "100.00"
    assert body["current_insurance_title"] == "dzialalnosc_gospodarcza"


def test_compare_profile_unknown_profile_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mock-zus/profiles/nieistniejacy_profil/compare",
        json={"debt_amount_zl": "0.00"},
    )

    assert response.status_code == 404


def test_compare_profile_detects_discrepancy(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mock-zus/profiles/dzialalnosc_z_zadluzeniem/compare",
        json={"debt_amount_zl": "0.00", "insurance_title": "umowa_o_prace"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_discrepancies"] is True
    debt_comparison = next(c for c in body["comparisons"] if c["field"] == "debt_amount_zl")
    assert debt_comparison["matches"] is False
    assert debt_comparison["declared_value"] == "0.00"
    assert debt_comparison["simulated_value"] == "100.00"


def test_compare_profile_matches_when_declaration_agrees(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mock-zus/profiles/dzialalnosc_z_zadluzeniem/compare",
        json={"debt_amount_zl": "100.00", "insurance_title": "dzialalnosc_gospodarcza"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_discrepancies"] is False
    for comparison in body["comparisons"]:
        if comparison["field"] in {"debt_amount_zl", "insurance_title"}:
            assert comparison["matches"] is True


def test_compare_profile_missing_declared_field_has_null_match(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mock-zus/profiles/matka_umowa_o_prace_standard/compare",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_discrepancies"] is False
    for comparison in body["comparisons"]:
        assert comparison["matches"] is None
        assert comparison["declared_value"] is None
