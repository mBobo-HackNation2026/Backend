"""Wspólne wyjątki domenowe aplikacji oraz ich handlery dla FastAPI.

Logika biznesowa powinna zgłaszać wyjątki z tego modułu zamiast HTTPException,
dzięki czemu pozostaje niezależna od warstwy transportowej (REST).
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Bazowy wyjątek domenowy aplikacji."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "app_error"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ValidationAppError(AppError):
    """Błąd walidacji reguł biznesowych (np. nieprawidłowe parametry świadczenia)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"


class EligibilityError(AppError):
    """Zgłaszany, gdy wnioskodawca nie spełnia warunków uprawniających do świadczenia."""

    status_code = status.HTTP_200_OK
    error_code = "not_eligible"


class IntegrationError(AppError):
    """Błąd komunikacji z (symulowanym) systemem zewnętrznym ZUS/mObywatel."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "integration_error"


def _error_response(error_code: str, message: str) -> JSONResponse:
    return JSONResponse(content={"error_code": error_code, "message": message})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        response = _error_response(exc.error_code, exc.message)
        response.status_code = exc.status_code
        return response
