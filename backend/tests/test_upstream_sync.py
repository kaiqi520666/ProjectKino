from decimal import Decimal

import httpx
import pytest

from app.modules.catalog.models import AiModel, AiModelSyncLog, AiProvider, VideoModelPrice
from app.modules.catalog.service import list_enabled_catalog
from app.modules.catalog.upstream_sync import sync_provider_models_in_session


class _ScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)


class _InMemoryCatalogSession:
    def __init__(self, provider: AiProvider, models: list[AiModel], prices: list[VideoModelPrice]) -> None:
        self.provider = provider
        self.models = models
        self.prices = prices
        self.logs: list[AiModelSyncLog] = []
        self.committed = 0

    def add(self, obj) -> None:
        if isinstance(obj, AiModelSyncLog):
            self.logs.append(obj)

    async def commit(self) -> None:
        self.committed += 1

    async def scalar(self, stmt):
        sql = str(stmt)
        if "FROM ai_providers" in sql:
            return self.provider
        return None

    async def scalars(self, stmt):
        sql = str(stmt)
        if "FROM ai_models" in sql:
            if "upstream_available IS true" in sql or "upstream_available = true" in sql:
                return _ScalarResult(
                    [m for m in self.models if m.enabled and m.upstream_available and self.provider.enabled]
                )
            return _ScalarResult(self.models)
        if "FROM video_model_prices" in sql:
            return _ScalarResult(self.prices)
        return _ScalarResult([])


def _mock_client(status_code: int, payload: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/models")
        assert request.headers.get("Authorization") == "Bearer test-cc-key"
        return httpx.Response(status_code, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_upstream_sync_tracks_only_configured_models_and_logs_only_changes():
    provider = AiProvider(
        id=1,
        key="cc",
        display_name="CC",
        base_url="https://api.meaicc.com/v1",
        api_key="test-cc-key",
        adapter="ccVideoV1",
        enabled=True,
    )
    m1 = AiModel(
        id="cc-sd2-fast-720",
        provider_id=1,
        media_type="video",
        category="Seedance 2.0",
        display_name="Seedance 2.0 极速 720p",
        upstream_model_id="cc-sd2-fast-720",
        enabled=True,
        upstream_available=True,
        is_default=True,
        sort=10,
        capabilities={"resolutions": ["720p"], "minDuration": 4, "maxDuration": 15},
        defaults={"resolution": "720p"},
    )
    m2 = AiModel(
        id="sd-2-c4",
        provider_id=1,
        media_type="video",
        category="Seedance 2.0",
        display_name="Seedance 2.0 C4",
        upstream_model_id="sd-2-c4",
        enabled=True,
        upstream_available=True,
        is_default=False,
        sort=20,
        capabilities={"resolutions": ["720p"], "minDuration": 4, "maxDuration": 15},
        defaults={"resolution": "720p"},
    )
    prices = [
        VideoModelPrice(model_id=m1.id, rule_key="default", unit="call", credit_price=Decimal("15")),
        VideoModelPrice(model_id=m2.id, rule_key="default", unit="call", credit_price=Decimal("18")),
    ]
    session = _InMemoryCatalogSession(provider, [m1, m2], prices)

    # 1. Steady state + unknown upstream model -> 0 logs, no auto-create
    async with _mock_client(
        200,
        {"data": [{"id": "cc-sd2-fast-720"}, {"id": "sd-2-c4"}, {"id": "new-untracked-model"}]},
    ) as client:
        res1 = await sync_provider_models_in_session(session, provider_key="cc", http_client=client)  # type: ignore[arg-type]
        assert res1["offline"] == 0
        assert res1["restored"] == 0
        assert len(session.logs) == 0
        assert len(session.models) == 2

    # 2. Default model disappears upstream -> offline, 1 log, user catalog hides it & promotes m2
    async with _mock_client(200, {"data": [{"id": "sd-2-c4"}]}) as client:
        res2 = await sync_provider_models_in_session(session, provider_key="cc", http_client=client)  # type: ignore[arg-type]
        assert res2["offline"] == 1
        assert res2["restored"] == 0
        assert m1.upstream_available is False
        assert m1.enabled is True
        assert len(session.logs) == 1
        assert session.logs[0].event_type == "offline"
        assert session.logs[0].model_id == "cc-sd2-fast-720"

        catalog = await list_enabled_catalog(session)  # type: ignore[arg-type]
        assert [item.id for item in catalog.video] == ["sd-2-c4"]
        assert catalog.video[0].is_default is True

    # 3. Circuit breaker: upstream returns 500 or empty -> does NOT mark sd-2-c4 offline
    async with _mock_client(500, {"error": "down"}) as client:
        res3 = await sync_provider_models_in_session(session, provider_key="cc", http_client=client)  # type: ignore[arg-type]
        assert res3["skipped"] is True
        assert m2.upstream_available is True

    async with _mock_client(200, {"data": []}) as client:
        res4 = await sync_provider_models_in_session(session, provider_key="cc", http_client=client)  # type: ignore[arg-type]
        assert res4["skipped"] is True
        assert m2.upstream_available is True

    # 4. Model comes back upstream -> restored, 1 new log (total 2)
    async with _mock_client(200, {"data": [{"id": "cc-sd2-fast-720"}, {"id": "sd-2-c4"}]}) as client:
        res5 = await sync_provider_models_in_session(session, provider_key="cc", http_client=client)  # type: ignore[arg-type]
        assert res5["restored"] == 1
        assert m1.upstream_available is True
        assert len(session.logs) == 2
        assert session.logs[1].event_type == "restored"

        catalog = await list_enabled_catalog(session)  # type: ignore[arg-type]
        assert [item.id for item in catalog.video] == ["cc-sd2-fast-720", "sd-2-c4"]
        assert catalog.video[0].is_default is True
