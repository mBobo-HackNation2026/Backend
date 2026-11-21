from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.eligibility.schemas import (
    BenefitPlan,
    DataSource,
    EligibilityResult,
    EligibilityStatus,
    InsuranceTitle,
    MaternityLeaveEligibilityRequest,
    PossibleSolution,
    RequiredDocument,
    SolutionType,
)


def test_children_count_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError):
        MaternityLeaveEligibilityRequest(children_count=0)


def test_minimal_valid_request_defaults_optional_fields_to_none() -> None:
    request = MaternityLeaveEligibilityRequest(children_count=1)

    assert request.insured_at_birth is None
    assert request.insurance_title is None
    assert request.debt_amount_zl is None
    assert request.employment_ended_reason is None


def test_insurance_title_accepts_known_values() -> None:
    request = MaternityLeaveEligibilityRequest(
        children_count=1, insurance_title=InsuranceTitle.dzialalnosc_gospodarcza
    )

    assert request.insurance_title == InsuranceTitle.dzialalnosc_gospodarcza


def test_eligibility_result_round_trips_through_json() -> None:
    result = EligibilityResult(
        benefit_code="maternity_leave",
        benefit_name="Zasiłek macierzyński",
        status=EligibilityStatus.requires_verification,
        met_conditions=["Ubezpieczenie chorobowe w dniu porodu"],
        unmet_conditions=[],
        missing_data=["Tytuł ubezpieczenia"],
        possible_solutions=[
            PossibleSolution(
                type=SolutionType.corrective_action,
                description="Zgłosić zadłużenie składkowe do umorzenia.",
                legal_basis="art. 1 ustawy przykładowej",
            )
        ],
        plan=BenefitPlan(
            weeks=20,
            rate_percentage=Decimal("100"),
            institution="ZUS",
            required_documents=[
                RequiredDocument(
                    code="ZUS_ZLA",
                    name="Zaświadczenie lekarskie",
                    when="przy składaniu wniosku",
                )
            ],
            deadlines=["Wniosek w ciągu 12 miesięcy od porodu"],
            legal_basis=["ustawa o świadczeniach"],
        ),
        rules_version=3,
    )

    payload = result.model_dump_json()
    restored = EligibilityResult.model_validate_json(payload)

    assert restored == result
    assert restored.status == EligibilityStatus.requires_verification
    assert restored.data_source == DataSource.user
    assert restored.plan is not None
    assert restored.plan.required_documents[0].code == "ZUS_ZLA"
    assert restored.possible_solutions[0].type == SolutionType.corrective_action
    assert '"status":"requires_verification"' in payload
    assert '"data_source":"user"' in payload


def test_benefit_plan_supports_duration_description_instead_of_weeks() -> None:
    plan = BenefitPlan(
        weeks=None,
        duration_description="do dnia porodu",
        rate_percentage=Decimal("100"),
        institution="ZUS",
        required_documents=[],
        deadlines=["Niezwłocznie po ustaniu ubezpieczenia"],
        legal_basis=["ustawa zasiłkowa art. 30"],
    )

    payload = plan.model_dump_json()
    restored = BenefitPlan.model_validate_json(payload)

    assert restored.weeks is None
    assert restored.duration_description == "do dnia porodu"


def test_possible_solution_supports_related_benefit_code() -> None:
    solution = PossibleSolution(
        type=SolutionType.alternative_benefit,
        description="Sprawdź świadczenie X.",
        related_benefit_code="swiadczenie_x",
    )

    assert solution.related_benefit_code == "swiadczenie_x"


def test_possible_solution_related_benefit_code_defaults_to_none() -> None:
    solution = PossibleSolution(
        type=SolutionType.limitation,
        description="Brak podstawy.",
    )

    assert solution.related_benefit_code is None


def test_data_source_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        EligibilityResult.model_validate(
            {
                "benefit_code": "maternity_leave",
                "benefit_name": "Zasiłek macierzyński",
                "status": "not_eligible",
                "met_conditions": [],
                "unmet_conditions": [],
                "missing_data": [],
                "possible_solutions": [],
                "plan": None,
                "rules_version": 1,
                "data_source": "zus_api",
            }
        )
