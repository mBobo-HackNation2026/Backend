"""Porównanie deklaracji użytkownika z symulowanymi danymi profilu MockZUSProvider.

Nigdy nie decyduje, które źródło jest "prawdziwe" - tylko zestawia obie wartości obok
siebie, żeby front mógł pokazać rozbieżność użytkownikowi (zob. docstring w
app/mock_zus/schemas.py).
"""

from app.mock_zus.schemas import (
    FieldComparison,
    MockZusCompareRequest,
    MockZusCompareResponse,
    MockZusProfileData,
)


def _compare_field(
    field: str, declared: object | None, simulated: object | None
) -> FieldComparison:
    matches = None if declared is None or simulated is None else declared == simulated
    return FieldComparison(
        field=field,
        declared_value=None if declared is None else str(declared),
        simulated_value=None if simulated is None else str(simulated),
        matches=matches,
    )


def compare_profile_with_declaration(
    profile: MockZusProfileData, declared: MockZusCompareRequest
) -> MockZusCompareResponse:
    comparisons = [
        _compare_field(
            "insurance_title", declared.insurance_title, profile.current_insurance_title
        ),
        _compare_field("insured", declared.insured_at_birth, profile.is_currently_insured),
        _compare_field("debt_amount_zl", declared.debt_amount_zl, profile.debt_amount_zl),
    ]
    has_discrepancies = any(c.matches is False for c in comparisons)

    return MockZusCompareResponse(
        profile_id=profile.profile_id,
        comparisons=comparisons,
        has_discrepancies=has_discrepancies,
    )
