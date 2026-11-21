import pytest
from pydantic import ValidationError

from app.eligibility.schemas import InsuranceTitle, MaternityLeaveEligibilityRequest


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
