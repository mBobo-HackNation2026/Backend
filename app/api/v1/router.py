from fastapi import APIRouter

from app.api.v1.endpoints import admin, health

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(admin.router)

# Kolejne moduły API będą podpinane tutaj w miarę implementacji:
# - calculator    -> kalkulator świadczeń (rodzaje zasiłków, kwoty, okresy)
# - eligibility   -> weryfikacja uprawnień wnioskodawcy
# - documents     -> upload i analiza PDF (PyMuPDF)
# - integrations  -> symulowane integracje ZUS / mObywatel
