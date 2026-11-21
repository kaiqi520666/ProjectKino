from typing import Any

import pytest
from pydantic_ai.models.openrouter import OpenRouterModel

from app.core.errors import AppError
from app.modules.catalog.models import AiModel, AiProvider
from app.modules.llm_engine.provider import MODEL_SETTINGS, resolve_text_model


class _FakeExecuteResult:
    def __init__(self, row: Any) -> None:
        self._row = row

    def first(self) -> Any:
        return self._row


class _FakeSession:
    def __init__(self, row: Any) -> None:
        self._row = row

    async def execute(self, _stmt: Any) -> _FakeExecuteResult:
        return _FakeExecuteResult(self._row)


def _make_openrouter_row(api_key: str) -> tuple[AiModel, AiProvider]:
    provider = AiProvider(
        id=4,
        key="openrouter",
        display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        adapter="openrouter",
        auth_type="bearer",
        api_key=api_key,
        enabled=True,
        configuration={"appTitle": "FrameDrama"},
    )
    model = AiModel(
        id="or-ds-baidu",
        provider_id=4,
        media_type="text",
        category="OpenRouter",
        display_name="DeepSeek V4.1 Flash (OpenRouter)",
        upstream_model_id="@preset/ds-baidu",
        enabled=True,
        upstream_available=True,
        is_default=True,
        sort=10,
        capabilities={},
        defaults={},
        configuration={},
    )
    return model, provider


@pytest.mark.asyncio
async def test_resolve_text_model_uses_openrouter_preset_and_disables_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    session = _FakeSession(_make_openrouter_row(api_key="sk-or-v1-test-key"))

    model, model_id = await resolve_text_model(session)  # type: ignore[arg-type]

    assert isinstance(model, OpenRouterModel)
    assert model_id == "or-ds-baidu"
    assert model.model_name == "@preset/ds-baidu"
    assert MODEL_SETTINGS.get("max_tokens") == 16384
    assert MODEL_SETTINGS.get("openrouter_reasoning") == {"enabled": False}
    assert MODEL_SETTINGS.get("openrouter_usage") == {"include": True}


@pytest.mark.asyncio
async def test_resolve_text_model_never_falls_back_to_deepseek_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-should-not-leak")
    session = _FakeSession(_make_openrouter_row(api_key=""))

    with pytest.raises(AppError) as exc_info:
        await resolve_text_model(session)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "llm_api_key_missing"
