import base64
import hashlib
import hmac
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

import oss2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.settings.models import SystemSetting


@dataclass(frozen=True)
class OssConfig:
    endpoint: str
    bucket: str
    access_key_id: str
    access_key_secret: str
    public_domain: str
    prefix: str = "framedrama"
    timeout_seconds: int = 30


def parse_oss_config(raw: dict[str, Any] | None) -> OssConfig:
    if not isinstance(raw, dict):
        raise AppError(503, "oss_not_configured", "尚未配置阿里云 OSS")
    endpoint = str(raw.get("endpoint") or "").strip().rstrip("/")
    bucket = str(raw.get("bucket") or "").strip()
    key_id = str(raw.get("access_key_id") or raw.get("accessKeyId") or "").strip()
    key_secret = str(raw.get("access_key_secret") or raw.get("accessKeySecret") or "").strip()
    public_domain = str(
        raw.get("public_base_url")
        or raw.get("publicBaseUrl")
        or raw.get("public_domain")
        or raw.get("publicDomain")
        or ""
    ).strip().rstrip("/")
    prefix = str(raw.get("prefix") or "framedrama").strip().strip("/") or "framedrama"
    timeout_seconds = int(raw.get("timeout_seconds") or raw.get("timeoutSeconds") or 30)

    if not endpoint or not bucket or not key_id or not key_secret:
        raise AppError(503, "oss_not_configured", "阿里云 OSS 配置不完整，请先配置 Endpoint、Bucket 与密钥")

    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    parsed = urlsplit(endpoint)
    hostname = parsed.hostname or ""
    if hostname.startswith(f"{bucket}."):
        hostname = hostname[len(bucket) + 1 :]
    if not hostname:
        raise AppError(503, "oss_invalid", "阿里云 OSS Endpoint 格式无效")

    normalized_endpoint = f"https://{hostname}"
    if not public_domain:
        public_domain = f"https://{bucket}.{hostname}"
    elif "://" not in public_domain:
        public_domain = f"https://{public_domain}"

    return OssConfig(
        endpoint=normalized_endpoint,
        bucket=bucket,
        access_key_id=key_id,
        access_key_secret=key_secret,
        public_domain=public_domain.rstrip("/"),
        prefix=prefix,
        timeout_seconds=max(5, min(timeout_seconds, 120)),
    )


class OssStorage:
    def __init__(self, config: OssConfig) -> None:
        self.config = config
        hostname = urlsplit(config.endpoint).hostname or ""
        self.host = f"https://{config.bucket}.{hostname}"

    def make_key(self, user_id: int, category: str, filename: str) -> str:
        clean_cat = category.strip("/")
        return f"{self.config.prefix}/{user_id}/{clean_cat}/{filename}"

    def make_system_key(self, category: str, filename: str) -> str:
        clean_cat = category.strip("/")
        return f"{self.config.prefix}/system/{clean_cat}/{filename}"

    def public_url(self, key: str) -> str:
        return f"{self.config.public_domain}/{quote(key, safe='/')}"

    def _build_post_policy(self, *, key: str, mime_type: str, size: int) -> dict[str, Any]:
        expires = datetime.now(UTC) + timedelta(minutes=5)
        fields = {
            "key": key,
            "Content-Type": mime_type,
            "x-oss-content-type": mime_type,
            "success_action_status": "200",
            "x-oss-forbid-overwrite": "true",
            "x-oss-object-acl": "default",
        }
        policy = {
            "expiration": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "conditions": [
                {"bucket": self.config.bucket},
                *[{k: v} for k, v in fields.items()],
                ["content-length-range", size, size],
            ],
        }
        encoded = base64.b64encode(json.dumps(policy, separators=(",", ":")).encode("utf-8")).decode("utf-8")
        signature = base64.b64encode(
            hmac.new(
                self.config.access_key_secret.encode("utf-8"),
                encoded.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        fields.update(
            {
                "OSSAccessKeyId": self.config.access_key_id,
                "policy": encoded,
                "Signature": signature,
            }
        )
        return {
            "host": self.host,
            "key": key,
            "url": self.public_url(key),
            "fields": fields,
            "expiresAt": expires.isoformat(),
        }

    def upload_policy(
        self,
        *,
        user_id: int,
        kind: str,
        file_name: str,
        mime_type: str,
        size: int,
    ) -> dict[str, Any]:
        match = re.search(r"\.[a-z0-9]{1,10}$", file_name, re.IGNORECASE)
        suffix = match.group().lower() if match else ""
        directory = {"image": "images", "video": "videos", "audio": "audios"}.get(kind, "files")
        key = self.make_key(user_id, directory, f"{uuid4().hex}{suffix}")
        return self._build_post_policy(key=key, mime_type=mime_type, size=size)

    def system_upload_policy(
        self,
        *,
        category: str,
        file_name: str,
        mime_type: str,
        size: int,
        slug: str | None = None,
    ) -> dict[str, Any]:
        match = re.search(r"\.[a-z0-9]{1,10}$", file_name, re.IGNORECASE)
        suffix = match.group().lower() if match else ".webp"
        clean_slug = re.sub(r"[^a-z0-9-]+", "-", (slug or "").strip().lower()).strip("-")
        stem = f"{clean_slug}-{uuid4().hex[:10]}" if clean_slug else uuid4().hex
        key = self.make_system_key(category, f"{stem}{suffix}")
        return self._build_post_policy(key=key, mime_type=mime_type, size=size)

    @contextmanager
    def client(self):
        transport = oss2.Session()
        try:
            auth = oss2.Auth(self.config.access_key_id, self.config.access_key_secret)
            yield oss2.Bucket(
                auth,
                self.config.endpoint,
                self.config.bucket,
                session=transport,
                connect_timeout=min(self.config.timeout_seconds, 60),
            )
        finally:
            transport.session.close()

    def put_bytes(self, key: str, body: bytes, mime_type: str) -> None:
        with self.client() as bucket:
            bucket.put_object(key, body, headers={"Content-Type": mime_type})

    def put_file(self, key: str, path: str, mime_type: str) -> None:
        with self.client() as bucket:
            bucket.put_object_from_file(key, path, headers={"Content-Type": mime_type})

    def download_file(self, key: str, path: str, max_bytes: int = 500 * 1024 * 1024) -> int:
        with self.client() as bucket:
            result = bucket.get_object(key)
            try:
                total = 0
                with open(path, "wb") as handle:
                    while True:
                        chunk = result.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("OSS 对象超出大小限制")
                        handle.write(chunk)
                if total == 0:
                    raise ValueError("OSS 对象为空")
                return total
            finally:
                result.close()

    def delete_objects(self, keys: list[str], *, required_prefix: str | None = None) -> int:
        prefix = (required_prefix or f"{self.config.prefix}/").lstrip("/")
        valid = [k for k in dict.fromkeys(keys) if isinstance(k, str) and k.startswith(prefix)]
        if not valid:
            return 0
        deleted = 0
        with self.client() as bucket:
            for start in range(0, len(valid), 1000):
                batch = valid[start : start + 1000]
                bucket.batch_delete_objects(batch)
                deleted += len(batch)
        return deleted


async def load_storage(session: AsyncSession) -> OssStorage:
    raw = await session.scalar(select(SystemSetting.value).where(SystemSetting.key == "storage.oss"))
    return OssStorage(parse_oss_config(raw))


async def try_load_storage(session: AsyncSession) -> OssStorage | None:
    raw = await session.scalar(select(SystemSetting.value).where(SystemSetting.key == "storage.oss"))
    try:
        return OssStorage(parse_oss_config(raw))
    except AppError:
        return None
