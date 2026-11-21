import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DISABLED = {"0", "off", "false", "none", "no"}
DEFAULT_GATES_LOG = Path(__file__).resolve().parents[3] / "output" / ".gates.jsonl"


def running_under_tests() -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return True
    main_mod = sys.modules.get("__main__")
    if getattr(main_mod, "__package__", None) == "unittest":
        return True
    entry = Path(sys.argv[0]).name if sys.argv else ""
    return entry.startswith("test_")


def gates_log_path() -> Path | None:
    raw = os.getenv("FRAMEDRAMA_GATES_LOG")
    if raw is not None:
        cleaned = raw.strip()
        if not cleaned or cleaned.lower() in _DISABLED:
            return None
        return Path(cleaned)
    if running_under_tests():
        return None
    return DEFAULT_GATES_LOG


def record_gate(
    stage: str,
    passed: bool,
    reasons: Sequence[str] = (),
    meta: dict | None = None,
) -> None:
    reason_list = [item.strip() for item in reasons if item and item.strip()]
    if not passed:
        logger.warning("llm_gate_retry", stage=stage, reasons=reason_list, meta=meta or {})
    target = gates_log_path()
    if target is None:
        return
    entry = {
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": stage,
        "passed": bool(passed),
        "reasons": reason_list,
        "meta": meta or {},
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return
