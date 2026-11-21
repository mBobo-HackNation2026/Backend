from fastapi.testclient import TestClient

MATERNITY_LEAVE_CODE = "zasilek_macierzynski_urlop_macierzynski"
ALTERNATIVE_BENEFIT_CODE = "zasilek_w_wysokosci_zasilku_macierzynskiego"
PATERNITY_LEAVE_CODE = "urlop_ojcowski"
PARENTAL_LEAVE_CODE = "urlop_rodzicielski"
SICKNESS_DURING_PREGNANCY_CODE = "zasilek_chorobowy_w_ciazy"
REHABILITATION_BENEFIT_CODE = "swiadczenie_rehabilitacyjne"
SUPPLEMENTARY_MATERNITY_LEAVE_CODE = "uzupelniajacy_urlop_macierzynski"
ADOPTION_LEAVE_CODE = "urlop_na_warunkach_urlopu_macierzynskiego"
STUB_BENEFIT_CODES = [
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


def test_check_eligibility_parental_leave_likely_eligible_standard_rate(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{PARENTAL_LEAVE_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": True,
            "za_zyciem_certificate": False,
            "other_parent_used_parental_leave_weeks": 0,
            "full_dose_claimed_within_21_days": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 32
    assert body["plan"]["rate_percentage"] == "70.00"


def test_check_eligibility_parental_leave_full_dose_gets_higher_rate(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{PARENTAL_LEAVE_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": True,
            "za_zyciem_certificate": False,
            "other_parent_used_parental_leave_weeks": 0,
            "full_dose_claimed_within_21_days": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["rate_percentage"] == "81.50"


def test_check_eligibility_parental_leave_pool_exhausted_by_other_parent(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{PARENTAL_LEAVE_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": True,
            "za_zyciem_certificate": False,
            "other_parent_used_parental_leave_weeks": 41,
            "full_dose_claimed_within_21_days": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["plan"] is None


def test_check_eligibility_sickness_during_pregnancy_likely_eligible(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{SICKNESS_DURING_PREGNANCY_CODE}",
        json={
            "children_count": 1,
            "is_pregnant": True,
            "insurance_title": "umowa_o_prace",
            "insured_days_continuous": 45,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert (
        body["plan"]["duration_description"]
        == "do 270 dni niezdolności do pracy w okresie ciąży"
    )
    assert body["plan"]["rate_percentage"] == "100.00"


def test_check_eligibility_sickness_during_pregnancy_waiting_period_not_met(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{SICKNESS_DURING_PREGNANCY_CODE}",
        json={
            "children_count": 1,
            "is_pregnant": True,
            "insurance_title": "zlecenie",
            "insured_days_continuous": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["plan"] is None


def test_check_eligibility_rehabilitation_benefit_likely_eligible(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{REHABILITATION_BENEFIT_CODE}",
        json={
            "children_count": 1,
            "sickness_benefit_period_exhausted": True,
            "medical_prognosis_recovery_possible": True,
            "excluded_from_rehabilitation_benefit": False,
            "is_pregnant": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["duration_description"] == "do 12 miesięcy"
    assert body["plan"]["rate_percentage"] == "90.00"


def test_check_eligibility_rehabilitation_benefit_not_eligible_when_excluded(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{REHABILITATION_BENEFIT_CODE}",
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
    assert body["plan"] is None


def test_check_eligibility_supplementary_maternity_leave_likely_eligible(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{SUPPLEMENTARY_MATERNITY_LEAVE_CODE}",
        json={
            "children_count": 1,
            "child_hospitalization_weeks": 3,
            "gestational_week_at_birth": 30,
            "birth_weight_grams": 1800,
            "postpartum_weeks_elapsed": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 3
    assert body["plan"]["rate_percentage"] == "100.00"


def test_check_eligibility_supplementary_maternity_leave_deadline_passed(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{SUPPLEMENTARY_MATERNITY_LEAVE_CODE}",
        json={
            "children_count": 1,
            "child_hospitalization_weeks": 3,
            "gestational_week_at_birth": 30,
            "birth_weight_grams": 1800,
            "postpartum_weeks_elapsed": 9,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["plan"] is None


def test_check_eligibility_adoption_leave_likely_eligible(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{ADOPTION_LEAVE_CODE}",
        json={
            "children_count": 1,
            "is_adoption_or_foster_care": True,
            "foster_care_type": "wniosek_o_przysposobienie",
            "child_age_years": 10,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "likely_eligible"
    assert body["plan"]["weeks"] == 20
    assert body["plan"]["rate_percentage"] == "100.00"


def test_check_eligibility_adoption_leave_not_eligible_for_professional_foster_family(
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/v1/eligibility/check/{ADOPTION_LEAVE_CODE}",
        json={
            "children_count": 1,
            "is_adoption_or_foster_care": True,
            "foster_care_type": "rodzina_zastepcza_zawodowa",
            "child_age_years": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_eligible"
    assert body["plan"] is None


def test_check_eligibility_accepts_full_expanded_request_schema(client: TestClient) -> None:
    """The input schema was expanded (waiting periods, hospitalization, adoption/foster
    care, parental leave split, rehabilitation benefit, stillbirth, podstawa wymiaru) so
    the frontend survey can collect everything up front - confirm every new field is
    accepted (no 422) even though most stub evaluators don't read them yet."""
    response = client.post(
        f"/api/v1/eligibility/check/{PATERNITY_LEAVE_CODE}",
        json={
            "children_count": 1,
            "insured_at_birth": True,
            "insurance_title": "umowa_o_prace",
            "insured_days_continuous": 45,
            "child_hospitalization_weeks": 2,
            "gestational_week_at_birth": 36,
            "birth_weight_grams": 2200,
            "postpartum_weeks_elapsed": 5,
            "is_adoption_or_foster_care": False,
            "foster_care_type": None,
            "child_age_years": 3,
            "school_obligation_deferred": False,
            "za_zyciem_certificate": False,
            "full_dose_claimed_within_21_days": True,
            "other_parent_used_parental_leave_weeks": 4,
            "part_time_fraction_during_parental_leave": "0.5",
            "sickness_benefit_period_exhausted": False,
            "medical_prognosis_recovery_possible": True,
            "excluded_from_rehabilitation_benefit": False,
            "is_stillbirth_or_infant_death": False,
            "days_since_death": None,
            "average_monthly_income_zl": "5500.00",
            "employment_duration_months": 18,
            "voluntary_contribution_base_zl": None,
            "bonus_type": "kwartalna",
            "months_since_last_benefit": "0.5",
        },
    )

    assert response.status_code == 200
    assert response.json()["benefit_code"] == PATERNITY_LEAVE_CODE


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
