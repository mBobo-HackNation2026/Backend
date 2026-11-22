import httpx
import pytest

from app.ai_provider import client as ai_client
from app.ai_provider.client import (
    AIProviderInvalidResponseError,
    AIProviderUnavailableError,
    request_json_completion,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_request_json_completion_raises_when_no_api_key_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    with pytest.raises(AIProviderUnavailableError):
        request_json_completion("system", "user")


def test_request_json_completion_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")

    def _raise(*_args, **_kwargs):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(ai_client.httpx, "post", _raise)

    with pytest.raises(AIProviderUnavailableError):
        request_json_completion("system", "user")


def test_request_json_completion_raises_on_malformed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "not valid json"}}]}

    monkeypatch.setattr(ai_client.httpx, "post", lambda *a, **kw: _FakeResponse())

    with pytest.raises(AIProviderInvalidResponseError):
        request_json_completion("system", "user")


def test_request_json_completion_returns_parsed_json_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"explanation": "ok"}'}}]}

    monkeypatch.setattr(ai_client.httpx, "post", lambda *a, **kw: _FakeResponse())

    result = request_json_completion("system", "user")

    assert result == {"explanation": "ok"}
