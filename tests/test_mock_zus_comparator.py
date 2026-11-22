from decimal import Decimal

from app.mock_zus.comparator import compare_profile_with_declaration
from app.mock_zus.profiles import MOCK_ZUS_PROFILES
from app.mock_zus.schemas import MockZusCompareRequest


def test_compare_profile_with_declaration_all_match() -> None:
    profile = MOCK_ZUS_PROFILES["matka_umowa_o_prace_standard"]
    declared = MockZusCompareRequest(
        insurance_title=profile.current_insurance_title,
        insured_at_birth=profile.is_currently_insured,
        debt_amount_zl=profile.debt_amount_zl,
    )

    result = compare_profile_with_declaration(profile, declared)

    assert result.has_discrepancies is False
    assert all(c.matches is True for c in result.comparisons)


def test_compare_profile_with_declaration_flags_mismatch() -> None:
    profile = MOCK_ZUS_PROFILES["dzialalnosc_z_zadluzeniem"]
    declared = MockZusCompareRequest(debt_amount_zl=Decimal("0.00"))

    result = compare_profile_with_declaration(profile, declared)

    assert result.has_discrepancies is True
    debt_comparison = next(c for c in result.comparisons if c.field == "debt_amount_zl")
    assert debt_comparison.matches is False
