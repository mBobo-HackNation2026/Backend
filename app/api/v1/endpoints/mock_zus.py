from fastapi import APIRouter

from app.core.exceptions import NotFoundError
from app.mock_zus.comparator import compare_profile_with_declaration
from app.mock_zus.profiles import get_profile, list_profile_summaries
from app.mock_zus.schemas import (
    MockZusCompareRequest,
    MockZusCompareResponse,
    MockZusProfileData,
    MockZusProfileSummary,
)

router = APIRouter(prefix="/mock-zus", tags=["mock-zus"])


@router.get(
    "/profiles",
    response_model=list[MockZusProfileSummary],
    summary="Lista dostępnych profili demonstracyjnych ZUS",
)
async def list_profiles() -> list[MockZusProfileSummary]:
    return list_profile_summaries()


@router.get(
    "/profiles/{profile_id}",
    response_model=MockZusProfileData,
    summary="Symulowane dane ZUS dla wybranego profilu demonstracyjnego",
)
async def get_profile_data(profile_id: str) -> MockZusProfileData:
    profile = get_profile(profile_id)
    if profile is None:
        raise NotFoundError(f"Nieznany profil demonstracyjny: '{profile_id}'")
    return profile


@router.post(
    "/profiles/{profile_id}/compare",
    response_model=MockZusCompareResponse,
    summary="Porównaj deklaracje użytkownika z symulowanymi danymi profilu",
)
async def compare_profile(
    profile_id: str, payload: MockZusCompareRequest
) -> MockZusCompareResponse:
    profile = get_profile(profile_id)
    if profile is None:
        raise NotFoundError(f"Nieznany profil demonstracyjny: '{profile_id}'")
    return compare_profile_with_declaration(profile, payload)
