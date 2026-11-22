"""Cienki, dostawca-agnostyczny klient do OpenRouter (API zgodne z OpenAI chat
completions - działa z dowolnym modelem dostępnym przez OpenRouter, bez wiązania
logiki aplikacji na stałe z jednym dostawcą/modelem - zob. brief "eBobo Legal
Intelligence", pkt 1).

Niedostępność tego klienta (brak klucza, timeout, błąd HTTP, nieoczekiwany kształt
odpowiedzi) NIGDY nie powinna wywołać HTTP 500 u wywołującego - woła się
``AIProviderUnavailableError``/``AIProviderInvalidResponseError``, a warstwa wyżej
(``app/legal_advisor/service.py``) łapie je i zwraca deterministyczny fallback
(zob. brief pkt 6: "Niedostępność OpenRouter nie może powodować HTTP 500").
"""

import json

import httpx

from app.core.config import get_settings


class AIProviderUnavailableError(Exception):
    """Dostawca AI jest nieosiągalny (brak klucza, timeout, błąd sieci/HTTP)."""


class AIProviderInvalidResponseError(Exception):
    """Dostawca AI odpowiedział, ale treść nie ma oczekiwanego kształtu / nie jest JSON-em."""


def request_json_completion(system_prompt: str, user_prompt: str) -> dict:
    """Wysyła jedno zapytanie chat-completion i zwraca jego treść sparsowaną jako JSON.

    Wymusza odpowiedź w formacie JSON (``response_format``) - walidacja względem
    oczekiwanego schematu Pydantic należy do wywołującego (``app/legal_advisor``).
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise AIProviderUnavailableError("OPENROUTER_API_KEY nie jest skonfigurowany.")

    try:
        response = httpx.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openrouter_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=settings.openrouter_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AIProviderUnavailableError(f"Błąd komunikacji z dostawcą AI: {exc}") from exc

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIProviderInvalidResponseError(
            "Nieoczekiwany kształt odpowiedzi dostawcy AI."
        ) from exc

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIProviderInvalidResponseError(
            "Odpowiedź dostawcy AI nie jest poprawnym JSON-em."
        ) from exc
