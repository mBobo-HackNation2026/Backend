from fastapi.testclient import TestClient

PATERNITY_LEAVE_CODE = "urlop_ojcowski"
STILLBIRTH_FUNERAL_CODE = "zasilek_pogrzebowy_martwe_urodzenie"


def test_general_guide_includes_risks_and_charitable_note(client: TestClient) -> None:
    response = client.get("/api/v1/formalities/general")

    assert response.status_code == 200
    body = response.json()
    assert len(body["general_risks"]) == 3
    assert body["employment_protection_note"]
    assert body["charitable_support_note"]
    assert body["difficult_situation_benefit_codes"] == [STILLBIRTH_FUNERAL_CODE]


def test_general_guide_does_not_fabricate_charity_names(client: TestClient) -> None:
    """The brief requires pointing to charitable organizations for difficult
    situations, but the project has no verified data for this - the note must say
    so explicitly rather than inventing organization names."""
    response = client.get("/api/v1/formalities/general")

    assert response.status_code == 200
    body = response.json()
    assert "nie dysponuje" in body["charitable_support_note"]


def test_benefit_guide_returns_documents_and_next_steps(client: TestClient) -> None:
    response = client.get(f"/api/v1/formalities/{PATERNITY_LEAVE_CODE}")

    assert response.status_code == 200
    body = response.json()
    assert body["benefit_code"] == PATERNITY_LEAVE_CODE
    assert body["institution"]
    assert len(body["required_documents"]) >= 1
    assert len(body["general_risks"]) == 3
    assert any(PATERNITY_LEAVE_CODE in step for step in body["next_steps"])
    assert any("calculate" in step for step in body["next_steps"])


def test_benefit_guide_unknown_code_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/formalities/nieistniejace_swiadczenie")

    assert response.status_code == 404


def test_general_route_is_not_shadowed_by_benefit_code_route(client: TestClient) -> None:
    """'/general' must resolve to the general guide, not be treated as an unknown
    benefit_code - route registration order matters here."""
    response = client.get("/api/v1/formalities/general")

    assert response.status_code == 200
    assert "how_benefits_are_paid" in response.json()
