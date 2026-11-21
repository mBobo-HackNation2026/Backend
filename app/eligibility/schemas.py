from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class InsuranceTitle(StrEnum):
    umowa_o_prace = "umowa_o_prace"
    zlecenie = "zlecenie"
    dzialalnosc_gospodarcza = "dzialalnosc_gospodarcza"
    inny = "inny"


class EmploymentEndedReason(StrEnum):
    upadlosc_likwidacja_smierc_pracodawcy = "upadlosc_likwidacja_smierc_pracodawcy"
    naruszenie_prawa_wyrokiem_sadu = "naruszenie_prawa_wyrokiem_sadu"


class MaternityLeaveEligibilityRequest(BaseModel):
    children_count: int = Field(ge=1, description="Liczba dzieci urodzonych przy jednym porodzie")
    insured_at_birth: bool | None = Field(
        default=None,
        description=(
            "Czy wnioskodawczyni była objęta ubezpieczeniem chorobowym w dniu porodu. "
            "None = nieznane."
        ),
    )
    insurance_title: InsuranceTitle | None = Field(
        default=None, description="Tytuł ubezpieczenia, jeśli znany."
    )
    debt_amount_zl: Decimal | None = Field(
        default=None,
        description="Zadłużenie składkowe na dzień powstania prawa do zasiłku, jeśli dotyczy.",
    )
    employment_ended_reason: EmploymentEndedReason | None = Field(
        default=None,
        description=(
            "Jeśli insured_at_birth=False: powód ustania ubezpieczenia w okresie ciąży, "
            "o ile wystąpił."
        ),
    )


class EligibilityStatus(StrEnum):
    likely_eligible = "likely_eligible"
    not_eligible = "not_eligible"
    requires_verification = "requires_verification"


class SolutionType(StrEnum):
    alternative_benefit = "alternative_benefit"
    corrective_action = "corrective_action"
    limitation = "limitation"


class PossibleSolution(BaseModel):
    type: SolutionType
    description: str
    legal_basis: str | None = None


class RequiredDocument(BaseModel):
    code: str
    name: str
    when: str


class BenefitPlan(BaseModel):
    weeks: int
    rate_percentage: Decimal
    institution: str
    required_documents: list[RequiredDocument]
    deadlines: list[str]
    legal_basis: list[str]


class EligibilityResult(BaseModel):
    benefit_code: str
    benefit_name: str
    status: EligibilityStatus
    met_conditions: list[str]
    unmet_conditions: list[str]
    missing_data: list[str]
    possible_solutions: list[PossibleSolution]
    plan: BenefitPlan | None
    rules_version: int
    data_source: str = "user"
    warnings: list[str] = Field(default_factory=list)
