import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

_DISABLED = {"0", "off", "false", "none", "no"}
DEFAULT_GATES_LOG = Path(__file__).resolve().parent.parent / "output" / ".gates.jsonl"


def running_under_tests() -> bool:
    """True only when actually executing under unittest or pytest (not merely because a dependency imported unittest)."""
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return True
    main_mod = sys.modules.get("__main__")
    if getattr(main_mod, "__package__", None) == "unittest":
        return True
    entry = Path(sys.argv[0]).name if sys.argv else ""
    return entry.startswith("test_")


def log_progress(stage: str, message: str) -> None:
    """Emit a timestamped, immediately-flushed progress line to stderr outside unit tests."""
    if running_under_tests():
        return
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] [{stage}] {message}", file=sys.stderr, flush=True)


def gates_log_path() -> Path | None:
    """Resolve the JSONL log path. Returns None when disabled or running under a test runner without override."""
    raw = os.getenv("FRAMEDRAMA_GATES_LOG")
    if raw is not None:
        cleaned = raw.strip()
        if not cleaned or cleaned.lower() in _DISABLED:
            return None
        return Path(cleaned)
    if running_under_tests():
        return None
    return DEFAULT_GATES_LOG


def classify_reason(stage: str, reason: str) -> str:
    """Bucket a human-readable retry reason into a stable gate category for stats."""
    if stage == "plan-episodes":
        if "集号" in reason or "恰好" in reason:
            return "episode_count"
        if "缺少 world" in reason:
            return "world_missing"
        if "world.era" in reason or "年代" in reason or "朝代" in reason or "空泛" in reason:
            return "world_era"
        if "world.baseline" in reason or "没有" in reason:
            return "world_baseline"
        if "编号重复" in reason:
            return "duplicate_id"
        if "必须列出本集角色" in reason:
            return "missing_cast_or_scene"
        if "不存在的" in reason:
            return "unknown_ref"
        if "sourceLines" in reason or "原稿行号" in reason or "行上限" in reason:
            return "source_lines"
        return "other"

    if stage == "write-episode":
        if "没有动作节拍" in reason:
            return "empty_action"
        if "引号" in reason:
            return "action_quote"
        if "说话人" in reason:
            return "unknown_speaker"
        if "上限" in reason and "台词" in reason:
            return "line_length"
        if "不在大纲" in reason or "安排的场景" in reason or "一场戏都没用到" in reason:
            return "unplanned_scene"
        if "角色" in reason and ("安排" in reason or "不在" in reason):
            return "unplanned_character"
        if "hookBeat" in reason or "钩子" in reason or "冷开场" in reason:
            return "hook_position"
        if "短于" in reason:
            return "duration_short"
        if "超出" in reason:
            return "duration_long"
        return "other"

    if stage == "analyze-assets":
        if "不多不少" in reason:
            return "batch_mismatch"
        if "角色名" in reason:
            return "forbidden_name"
        if "缺少 voice" in reason:
            return "missing_voice"
        if "voice 超过" in reason:
            return "voice_too_long"
        if "把 voice 留空" in reason:
            return "unexpected_voice"
        if "无人空景" in reason:
            return "scene_not_empty"
        if "纯白背景" in reason:
            return "prop_missing_white_bg"
        if "无手" in reason:
            return "prop_missing_no_hands"
        if "尺度" in reason:
            return "prop_missing_scale"
        return "other"

    if stage == "plan-storyboard":
        if "这些段" in reason:
            return "segment_mismatch"
        if "镜头编号" in reason:
            return "cut_mismatch"
        if "没有的资产" in reason:
            return "unknown_ref"
        if "references 有重复" in reason:
            return "duplicate_ref"
        if "必须包含场景" in reason:
            return "missing_scene_ref"
        if "角色名" in reason:
            return "forbidden_name"
        if "时间" in reason or "秒数" in reason or "协议" in reason or "参考图" in reason:
            return "shot_pollution"
        return "other"

    return "other"


def record_gate(
    stage: str,
    passed: bool,
    reasons: Sequence[str] = (),
    meta: dict | None = None,
    *,
    path: Path | None = None,
) -> None:
    """Append a single quality-gate check result to the JSONL log. Never raises on I/O errors."""
    target = path if path is not None else gates_log_path()
    if target is None:
        return
    reason_list = [item.strip() for item in reasons if item and item.strip()]
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": stage,
        "passed": bool(passed),
        "reasons": reason_list,
        "categories": [classify_reason(stage, item) for item in reason_list],
        "meta": meta or {},
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return


def summarize_gates(path: Path) -> dict[str, dict]:
    """Aggregate pass/retry counts and top failure categories per stage from a JSONL log."""
    summary: dict[str, dict] = {}
    if not path.exists():
        return summary

    samples: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        stage = str(record.get("stage", "unknown"))
        bucket = summary.setdefault(stage, {"checks": 0, "passed": 0, "retries": 0, "categories": Counter(), "samples": {}})
        bucket["checks"] += 1
        if record.get("passed"):
            bucket["passed"] += 1
            continue
        bucket["retries"] += 1
        reasons = record.get("reasons") or []
        categories = record.get("categories") or [classify_reason(stage, item) for item in reasons]
        for category, reason in zip(categories, reasons):
            bucket["categories"][category] += 1
            if len(samples[stage][category]) < 3 and reason not in samples[stage][category]:
                samples[stage][category].append(reason)

    for stage, bucket in summary.items():
        bucket["categories"] = dict(bucket["categories"].most_common())
        bucket["samples"] = dict(samples[stage])
    return summary


def format_summary(summary: dict[str, dict]) -> str:
    if not summary:
        return "暂无质量门记录。"
    lines: list[str] = []
    for stage, bucket in summary.items():
        checks = bucket["checks"]
        retries = bucket["retries"]
        rate = (retries / checks * 100) if checks else 0.0
        lines.append(f"[{stage}] 校验 {checks} 次 · 通过 {bucket['passed']} · 重试 {retries}（重试率 {rate:.1f}%）")
        for category, count in bucket["categories"].items():
            lines.append(f"  - {category}: {count} 次")
            for sample in bucket["samples"].get(category, []):
                lines.append(f"      例：{sample}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect FrameDrama quality-gate retry stats.")
    parser.add_argument("--file", type=Path, default=DEFAULT_GATES_LOG, help="Path to .gates.jsonl")
    parser.add_argument("--clear", action="store_true", help="Clear the gate log file")
    args = parser.parse_args(argv)

    if args.clear:
        if args.file.exists():
            args.file.unlink()
            print(f"已清空：{args.file}")
        else:
            print(f"文件不存在：{args.file}")
        return 0

    print(format_summary(summarize_gates(args.file)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
