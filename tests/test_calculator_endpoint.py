from decimal import Decimal

from fastapi.testclient import TestClient

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
PARENTAL_LEAVE_CODE = "urlop_rodzicielski"
STILLBIRTH_FUNERAL_CODE = "zasilek_pogrzebowy_martwe_urodzenie"


def test_calculate_maternity_leave_returns_total_amount(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/benefits/calculate/{MATERNITY_LEAVE_CODE}",
        json={
            "children_count": 1,
            "average_monthly_income_zl": "6000.00",
            "insurance_title": "umowa_o_prace",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_days"] == 140
    assert body["total_amount_zl"] == "24161.20"
    assert body["basis"]["monthly_basis_zl"] == "5177.40"


def test_calculate_unknown_benefit_code_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/benefits/calculate/nieistniejace_swiadczenie",
        json={"children_count": 1},
    )

    assert response.status_code == 404


def test_calculate_stillbirth_funeral_benefit_returns_lump_sum(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/benefits/calculate/{STILLBIRTH_FUNERAL_CODE}",
        json={"children_count": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lump_sum_amount_zl"] == "7000.00"
    assert body["basis"] is None


def test_compare_parental_leave_variants_household_totals(client: TestClient) -> None:
    response = client.post(
        "/api/v1/benefits/compare/urlop-rodzicielski",
        json={
            "children_count": 1,
            "za_zyciem_certificate": False,
            "full_dose_claimed_within_21_days": False,
            "parent_a": {
                "label": "Matka",
                "average_monthly_income_zl": "6000.00",
                "insurance_title": "umowa_o_prace",
            },
            "parent_b": {
                "label": "Ojciec",
                "average_monthly_income_zl": "8000.00",
                "insurance_title": "umowa_o_prace",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_pool_weeks"] == 41
    assert len(body["variants"]) == 3
    for variant in body["variants"]:
        assert variant["weeks_parent_a"] + variant["weeks_parent_b"] == 41
    # Father earns more, so the household total is higher when he takes the larger share.
    father_max_variant = next(v for v in body["variants"] if v["weeks_parent_b"] == 32)
    mother_max_variant = next(v for v in body["variants"] if v["weeks_parent_a"] == 32)
    assert Decimal(father_max_variant["total_household_amount_zl"]) > Decimal(
        mother_max_variant["total_household_amount_zl"]
    )


def test_compare_parental_leave_variants_missing_income_warns(client: TestClient) -> None:
    response = client.post(
        "/api/v1/benefits/compare/urlop-rodzicielski",
        json={
            "children_count": 1,
            "parent_a": {"label": "Matka"},
            "parent_b": {"label": "Ojciec", "average_monthly_income_zl": "8000.00"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert any("Matka" in w for w in body["warnings"])
    assert all(v["amount_parent_a_zl"] is None for v in body["variants"])
