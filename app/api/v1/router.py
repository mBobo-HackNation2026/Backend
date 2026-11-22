from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    calculator,
    eligibility,
    formalities,
    health,
    mock_zus,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(admin.router)
api_router.include_router(auth.router)
api_router.include_router(eligibility.router)
api_router.include_router(calculator.router)
api_router.include_router(mock_zus.router)
api_router.include_router(formalities.router)

# Kolejne moduły API będą podpinane tutaj w miarę implementacji:
# - documents     -> upload i analiza PDF (PyMuPDF)
# - integrations  -> symulowana integracja mObywatel (osobna od MockZUSProvider)
