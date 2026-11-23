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


_SUBMIT_REJECT_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 413, 415, 422, 429})
_QUERY_REJECT_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 413, 415, 422})

_DEFINITIVE_SUBMIT_REJECT_NEEDLES = (
    "no available channel",
    "model_not_found",
    "invalid model",
    "unsupported model",
    "insufficient_quota",
    "cpu overloaded",
    "system overloaded",
    "server overloaded",
    "service unavailable",
    "too many requests",
    "rate limit",
)


def _extract_raw_error(value: Any) -> str | None:
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
    return None


def _extract_error(value: Any, fallback_status: int | None = None) -> str:
    raw = _extract_raw_error(value)
    if raw:
        return raw
    if fallback_status:
        return f"图片供应商返回错误（HTTP {fallback_status}）"
    return "图片供应商生成失败"


def _response_has_task_id(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    inner = value.get("data")
    candidates = (value, inner) if isinstance(inner, dict) else (value,)
    for obj in candidates:
        for key in ("task_id", "id"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return True
    return False


def format_provider_http_error(value: Any, status_code: int, *, provider_label: str) -> str:
    raw = _extract_raw_error(value)
    if raw:
        if f"HTTP {status_code}" in raw:
            return raw[:400]
        return f"[HTTP {status_code}] {raw}"[:400]
    return f"{provider_label}返回错误（HTTP {status_code}）"


def build_provider_http_error(
    value: Any,
    status_code: int,
    *,
    is_submit: bool,
    provider_label: str,
) -> MediaProviderError:
    err_msg = format_provider_http_error(value, status_code, provider_label=provider_label)
    if is_submit:
        has_task_id = _response_has_task_id(value)
        err_lower = err_msg.lower()
        definitive_overload_or_reject = not has_task_id and (
            status_code == 503
            or any(needle in err_lower for needle in _DEFINITIVE_SUBMIT_REJECT_NEEDLES)
        )
        rejected = status_code in _SUBMIT_REJECT_STATUS_CODES or definitive_overload_or_reject
        return MediaProviderError(
            "providerRejected" if rejected else "submissionUnknown",
            err_msg,
            rejected=rejected,
            uncertain=not rejected,
        )

    # 轮询阶段（任务已提交）收到 503/429/5xx 属于瞬时异常，交由上层重试，绝不直接拒单退费。
    rejected = status_code in _QUERY_REJECT_STATUS_CODES
    return MediaProviderError(
        "providerRejected" if rejected else "queryFailed",
        err_msg,
        rejected=rejected,
        uncertain=False,
    )


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
        reference_urls: list[str] | None = None,
    ) -> tuple[dict[str, Any], str]:
        cleaned_refs = [
            url.strip() for url in (reference_urls or []) if isinstance(url, str) and url.strip()
        ]
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
        if cleaned_refs:
            payload["images"] = cleaned_refs
            return payload, "edits"
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
            raise build_provider_http_error(
                value,
                response.status_code,
                is_submit=payload is not None,
                provider_label="图片供应商",
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
        endpoint: str = "generations",
        task_id: str,
        timeout_seconds: float = 30.0,
    ) -> ImageProviderResult:
        # 沧元官方文档约定：无论提交走 /v1/images/generations 还是 /v1/images/edits，
        # 异步轮询端点统一为 GET /v1/images/generations/{id}。
        poll_endpoint = "generations" if endpoint == "edits" else endpoint
        return await self._request(
            base_url=base_url,
            api_key=api_key,
            auth_type=auth_type,
            auth_header=auth_header,
            endpoint=f"{poll_endpoint}/{quote(task_id, safe='')}",
            payload=None,
            timeout_seconds=timeout_seconds,
        )
