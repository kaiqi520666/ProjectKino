import asyncio
import json
import math
from pathlib import Path

import httpx


def detect_image_format(body: bytes) -> tuple[str, str]:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise ValueError("无法识别的图片格式，仅支持 PNG / JPEG / WebP")


async def download_public_media(
    url: str,
    *,
    max_bytes: int = 200 * 1024 * 1024,
    timeout_seconds: float = 120.0,
) -> bytes:
    async with (
        asyncio.timeout(timeout_seconds),
        httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client,
    ):
        async with client.stream("GET", url) as response:
            if not 200 <= response.status_code < 300:
                raise ValueError(f"媒体下载失败（HTTP {response.status_code}）")
            buf = bytearray()
            async for chunk in response.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ValueError("媒体文件超出大小限制")
            if not buf:
                raise ValueError("下载到的媒体文件为空")
            return bytes(buf)


async def download_to_file(
    url: str,
    dest: Path,
    *,
    max_bytes: int = 500 * 1024 * 1024,
    timeout_seconds: float = 180.0,
) -> int:
    async with (
        asyncio.timeout(timeout_seconds),
        httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client,
    ):
        async with client.stream("GET", url) as response:
            if not 200 <= response.status_code < 300:
                raise ValueError(f"媒体下载失败（HTTP {response.status_code}）")
            total = 0
            with dest.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("媒体文件超出大小限制")
                    handle.write(chunk)
            if total == 0:
                raise ValueError("下载到的媒体文件为空")
            return total


async def probe_video_duration(path: Path, ffprobe_path: str = "ffprobe") -> float:
    proc = await asyncio.create_subprocess_exec(
        ffprobe_path,
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm",
        "-show_entries",
        "format=duration:stream=codec_type,duration",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ValueError("ffprobe 校验超时") from None

    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="ignore")[:300]
        raise ValueError(f"视频文件元数据校验失败：{detail}")

    metadata = json.loads(stdout.decode("utf-8"))
    streams = [s for s in metadata.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise ValueError("视频文件缺少有效视频轨")

    candidates = [metadata.get("format", {}).get("duration"), *(s.get("duration") for s in streams)]
    for item in candidates:
        try:
            seconds = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(seconds) and seconds > 0:
            return round(seconds, 2)
    raise ValueError("无法解析有效的视频时长")
