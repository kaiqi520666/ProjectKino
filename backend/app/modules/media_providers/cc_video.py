import asyncio
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.modules.media_providers.cangyuan_image import (
    MediaProviderError,
    _extract_error,
    build_provider_http_error,
)


@dataclass(frozen=True)
class VideoProviderResult:
    task_id: str | None = None
    url: str | None = None
    # pending / completed / failed / unknown
    status: str = "unknown"
    progress: int = 0
    message: str | None = None


class CcVideoAdapter:
    """对齐 Moonflow CC 视频协议（ccVideoV1）：Seedance 2.0 / 2.5 提交与 20 秒轮询。"""

    minimum_poll_interval = 20

    def build_payload(
        self,
        *,
        upstream_model_id: str,
        prompt: str,
        reference_urls: list[str],
        reference_video_urls: list[str] | None = None,
        reference_audio_urls: list[str] | None = None,
        ratio: str,
        resolution: str,
        duration: int,
        parameter_bindings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bindings = parameter_bindings or {}
        raw_params = {"ratio": ratio, "resolution": resolution, "duration": duration}
        mapped: dict[str, Any] = {}
        for name, val in raw_params.items():
            binding = bindings.get(name, {})
            field = binding.get("field", name)
            key = str(val)
            mapped[field] = binding.get("values", {}).get(key, val)

        media: list[dict[str, str]] = [
            {"type": "reference_image", "url": url} for url in reference_urls
        ]
        for url in reference_video_urls or []:
            media.append({"type": "reference_video", "url": url})
        for url in reference_audio_urls or []:
            media.append({"type": "reference_audio", "url": url})
        return {
            "model": upstream_model_id,
            "input": {"prompt": prompt, **({"media": media} if media else {})},
            "parameters": mapped,
        }

    def parse(self, value: Any) -> VideoProviderResult:
        if not isinstance(value, dict):
            return VideoProviderResult()
        task_id = next(
            (
                value[key]
                for key in ("task_id", "id")
                if isinstance(value.get(key), str) and 0 < len(value[key]) <= 1024
            ),
            None,
        )
        raw = value.get("status")
        state = raw if isinstance(raw, str) else ""
        if state == "SUCCEEDED":
            status = "completed"
        elif state == "FAILED" or state.startswith("FAILED:"):
            status = "failed"
        elif state in {"RUNNING", "PENDING", "QUEUED", "PROCESSING"}:
            status = "pending"
        else:
            status = "unknown"

        url = value.get("object")
        try:
            parsed = urlsplit(url) if isinstance(url, str) and len(url) <= 8192 else None
            if (
                status != "completed"
                or parsed is None
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
            ):
                url = None
        except ValueError:
            url = None

        raw_prog = value.get("progress")
        is_valid_prog = (
            isinstance(raw_prog, (int, float))
            and not isinstance(raw_prog, bool)
            and math.isfinite(raw_prog)
        )
        progress = int(max(0, min(100, raw_prog))) if is_valid_prog else 0
        return VideoProviderResult(
            task_id=task_id,
            url=url,
            status=status,
            progress=progress,
            message=_extract_error(value) if status == "failed" else None,
        )

    async def _request(
        self,
        *,
        base_url: str,
        api_key: str,
        auth_type: str,
        auth_header: str | None,
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> VideoProviderResult:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers[auth_header or "X-API-Key"] = api_key

        endpoint = f"{base_url.rstrip('/')}/videos"
        if task_id:
            endpoint += f"/{quote(task_id, safe='')}"
        method = "POST" if payload is not None else "GET"

        try:
            async with (
                asyncio.timeout(timeout_seconds),
                httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client,
            ):
                response = await client.request(method, endpoint, json=payload, headers=headers)
        except (httpx.HTTPError, TimeoutError):
            raise MediaProviderError(
                "submissionUnknown" if payload is not None else "queryFailed",
                "视频供应商网络请求超时或中断，请勿重复提交",
                uncertain=payload is not None,
            ) from None

        try:
            value = response.json() if response.content else {}
        except ValueError:
            value = {}

        if not 200 <= response.status_code < 300:
            raise build_provider_http_error(
                value,
                response.status_code,
                is_submit=payload is not None,
                provider_label="视频供应商",
            )
        return self.parse(value)

    async def submit(
        self,
        *,
        base_url: str,
        api_key: str,
        auth_type: str,
        auth_header: str | None,
        payload: dict[str, Any],
        timeout_seconds: float = 120.0,
    ) -> VideoProviderResult:
        return await self._request(
            base_url=base_url,
            api_key=api_key,
            auth_type=auth_type,
            auth_header=auth_header,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    async def query(
        self,
        *,
        base_url: str,
        api_key: str,
        auth_type: str,
        auth_header: str | None,
        task_id: str,
        timeout_seconds: float = 30.0,
    ) -> VideoProviderResult:
        return await self._request(
            base_url=base_url,
            api_key=api_key,
            auth_type=auth_type,
            auth_header=auth_header,
            task_id=task_id,
            timeout_seconds=timeout_seconds,
        )
