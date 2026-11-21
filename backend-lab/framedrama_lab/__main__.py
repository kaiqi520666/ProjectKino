import argparse
import asyncio
import sys
from pathlib import Path

from pydantic_ai.exceptions import AgentRunError

from .deepseek import model_from_env
from .generate import Source, episode_line_count, generate_script, outline_seconds, script_length
from .schema import ProjectSettings, ScriptResult
from .timing import seconds_range


def render_markdown(result: ScriptResult) -> str:
    settings = result.settings
    lines = [
        f"# 《{settings.name}》{len(result.episodes)} 集剧本",
        "",
        f"画风 {settings.visualStyle} · 画幅 {settings.ratio} · 单集目标 {settings.secondsPerEpisode} 秒 · "
        f"单片段最长 {settings.maxSegmentDuration} 秒",
        "",
        f"角色 {len(result.outline.characters)} · 场景 {len(result.outline.scenes)} · 道具 {len(result.outline.props)}",
        "",
    ]
    for episode in result.episodes:
        low, high = seconds_range(episode.targetSeconds)
        lines.extend([
            f"## 第 {episode.number} 集 · {episode.title}",
            "",
            f"正文 {script_length(episode.script)} 字 · 预估 {episode.seconds} 秒（目标区间 {low}–{high} 秒）",
            "",
            episode.summary,
            "",
            episode.script,
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate FrameDrama episode scripts.")
    parser.add_argument("settings", type=Path, help="Project settings JSON")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--story", help="Story synopsis")
    inputs.add_argument("--source-file", type=Path, help="UTF-8 novel or script text")
    parser.add_argument("--output", type=Path, required=True, help="Result JSON")
    parser.add_argument("--markdown", type=Path, help="Optional readable Markdown rendering")
    parser.add_argument("--episode-seconds", type=int, help="Override each episode's target duration")
    args = parser.parse_args()

    try:
        inputs_paths = [args.settings]
        if args.source_file:
            inputs_paths.append(args.source_file)
        outputs = [path for path in (args.output, args.markdown) if path]
        if any(path.resolve() in {item.resolve() for item in inputs_paths} for path in outputs):
            parser.exit(2, "输出路径需要与输入文件不同。\n")
        settings = ProjectSettings.model_validate_json(args.settings.read_text(encoding="utf-8-sig"))
        if args.episode_seconds is not None:
            settings = ProjectSettings.model_validate({**settings.model_dump(), "secondsPerEpisode": args.episode_seconds})
        source = (
            Source.from_text("upload", args.source_file.read_text(encoding="utf-8-sig"))
            if args.source_file else Source.from_text("story", args.story)
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"读取创作输入失败。{exc}\n")

    try:
        model = model_from_env()
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    try:
        result = asyncio.run(generate_script(model, settings, source))
    except AgentRunError as exc:
        status = getattr(exc, "status_code", None)
        detail = f"HTTP {status}" if status else type(exc).__name__
        cause = exc.__cause__
        if cause is not None:
            detail += f"：{str(cause)[:1500]}"
        parser.exit(1, f"剧本生成失败（{detail}）。\n")

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(render_markdown(result), encoding="utf-8")
    except OSError as exc:
        parser.exit(1, f"写入结果失败。{exc}\n")

    counts = outline_seconds(result.outline)
    print(
        f"《{settings.name}》{len(result.episodes)} 集 · 角色 {counts['characters']} · "
        f"场景 {counts['scenes']} · 道具 {counts['props']}",
        file=sys.stderr,
    )
    for episode in result.episodes:
        low, high = seconds_range(episode.targetSeconds)
        note = "（超出建议范围）" if not low <= episode.seconds <= high else ""
        print(
            f"第 {episode.number} 集《{episode.title}》正文 {script_length(episode.script)} 字 · "
            f"预估 {episode.seconds} 秒（{low}–{high}）· {len(episode.scenes)} 场 · "
            f"{episode_line_count(episode)} 句台词{note}",
            file=sys.stderr,
        )
        for warning in episode.warnings:
            print(f"  提示：{warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
