import asyncio
from pathlib import Path

from app.modules.storage.media import probe_video_duration


async def _run_ffmpeg(args: list[str], timeout_seconds: float = 600.0) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ValueError("FFmpeg 合成视频超时") from None

    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="ignore")[-400:]
        raise ValueError(f"FFmpeg 合成失败：{detail}")


async def compose_episode_videos(
    clip_paths: list[Path],
    output_path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    timeout_seconds: float = 600.0,
) -> float:
    """
    将本集所有片段按序归一化拼接成标准 MP4（H.264 + AAC + faststart），返回成片时长。
    先逐段统一编码参数再 concat，确保不同片段帧率/采样率存在细微差异时也能无缝拼接。
    """
    if not clip_paths:
        raise ValueError("没有可合成的片段视频")

    work_dir = output_path.parent
    normalized: list[Path] = []
    for idx, src in enumerate(clip_paths, 1):
        norm = work_dir / f"norm_{idx:03d}.mp4"
        await _run_ffmpeg(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(src),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(norm),
            ],
            timeout_seconds=timeout_seconds,
        )
        normalized.append(norm)

    list_file = work_dir / "concat.txt"
    list_lines = [f"file '{item.resolve().as_posix()}'" for item in normalized]
    list_file.write_text("\n".join(list_lines) + "\n", encoding="utf-8")

    await _run_ffmpeg(
        [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        timeout_seconds=timeout_seconds,
    )
    return await probe_video_duration(output_path, ffprobe_path=ffprobe_path)
