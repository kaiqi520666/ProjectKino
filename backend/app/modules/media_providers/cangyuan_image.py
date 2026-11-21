import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class MediaProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        rejected: bool = False,
        uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.rejected = rejected
        self.uncertain = uncertain


@dataclass(frozen=True)
class ImageProviderResult:
    task_id: str | None = None
    url: str | None = None
    # pending / completed / failed / unknown
    status: str = "unknown"
    message: str = "图片生成失败"


def _extract_error(value: Any, fallback_status: int | None = None) -> str:
    if isinstance(value, dict):
        for key in ("message", "msg", "detail"):
            val = value.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:400]
        err = value.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("code")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()[:400]
        elif isinstance(err, str) and err.strip():
            return err.strip()[:400]
    if fallback_status:
        return f"图片供应商返回错误（HTTP {fallback_status}）"
    return "图片供应商生成失败"


def asset_aspect_ratio(kind: str) -> str:
    """业务约定：角色与场景统一 16:9，物品统一 1:1。"""
    return "1:1" if kind == "prop" else "16:9"


class CangyuanImageAdapter:
    """对齐 Moonflow 沧元图片协议（cangyuanImageV1）：异步提交 + 轮询查询。"""

    def build_payload(
        self,
        *,
        upstream_model_id: str,
        prompt: str,
        tier: str,
        ratio: str,
        quality: str = "high",
        series: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        payload: dict[str, Any] = {
            "model": upstream_model_id,
            "tier": tier,
            "prompt": prompt,
            "size": ratio,
            "n": 1,
            "response_format": "url",
            "async": True,
        }
        if series:
            payload["series"] = series
        if tier != "web" and quality:
            payload["quality"] = quality
        return payload, "generations"

    def parse(self, response: Any) -> ImageProviderResult:
        if not isinstance(response, dict):
            return ImageProviderResult()
        inner = response.get("data")
        data = inner if isinstance(inner, dict) else response
        task_id = (
            data.get("task_id") or data.get("id") or response.get("task_id") or response.get("id")
        )
        entries = data.get("data", response.get("data", []))
        url = (
            entries[0].get("url")
            if isinstance(entries, list) and entries and isinstance(entries[0], dict)
            else None
        )
        url = url or data.get("url")
        status = data.get("status", response.get("status"))
        raw = status if isinstance(status, str) else ""
        if raw in ("failed", "error", "cancelled", "canceled") or data.get("error"):
            normalized = "failed"
        elif url:
            normalized = "completed"
        elif raw in ("queued", "in_progress", "pending", "processing", "submitted"):
            normalized = "pending"
        else:
            normalized = "unknown"
        return ImageProviderResult(
            task_id=task_id if isinstance(task_id, str) and 0 < len(task_id) <= 512 else None,
            url=url if isinstance(url, str) and url else None,
            status=normalized,
            message=_extract_error(data),
        )

    async def _request(
        self,
        *,
        base_url: str,
        api_key: str,
        auth_type: str,
        auth_header: str | None,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> ImageProviderResult:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers[auth_header or "X-API-Key"] = api_key

        url = f"{base_url.rstrip('/')}/images/{endpoint}"
        method = "POST" if payload is not None else "GET"
        try:
            async with (
                asyncio.timeout(timeout_seconds),
                httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client,
            ):
                response = await client.request(method, url, json=payload, headers=headers)
        except (httpx.HTTPError, TimeoutError):
            raise MediaProviderError(
                "submissionUnknown" if payload is not None else "queryFailed",
                "图片供应商网络请求超时或中断，请勿重复提交",
                uncertain=payload is not None,
            ) from None

        try:
            value = response.json() if response.content else {}
        except ValueError:
            value = {}

        if not 200 <= response.status_code < 300:
            rejected = response.status_code in (400, 401, 403, 404, 405, 413, 415, 422, 429)
            raise MediaProviderError(
                "providerRejected" if rejected else "submissionUnknown",
                _extract_error(value, response.status_code),
                rejected=rejected,
                uncertain=not rejected,
            )
        return self.parse(value)

    async def submit(
        self,
        *,
        base_url: str,
        api_key: str,
        auth_type: str,
        auth_header: str | None,
        endpoint: str,
        payload: dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> ImageProviderResult:
        return await self._request(
            base_url=base_url,
            api_key=api_key,
            auth_type=auth_type,
            auth_header=auth_header,
            endpoint=endpoint,
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
        endpoint: str,
        task_id: str,
        timeout_seconds: float = 30.0,
    ) -> ImageProviderResult:
        return await self._request(
            base_url=base_url,
            api_key=api_key,
            auth_type=auth_type,
            auth_header=auth_header,
            endpoint=f"{endpoint}/{quote(task_id, safe='')}",
            payload=None,
            timeout_seconds=timeout_seconds,
        )
