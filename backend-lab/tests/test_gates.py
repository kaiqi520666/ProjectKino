import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from framedrama_lab.gates import (
    DEFAULT_GATES_LOG, classify_reason, format_summary, gates_log_path,
    record_gate, running_under_tests, summarize_gates,
)
from framedrama_lab.schema import AssetResult, ScriptResult
from framedrama_lab.storyboard import storyboard

from test_storyboard import asset_doc, reply_for, script_doc


class GateStatsTests(TestCase):
    def test_records_and_summarizes_pass_and_retry_buckets(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / ".gates.jsonl"
            record_gate("write-episode", False, ["全集 70.0 秒，短于可交付区间 90.0–150.0 秒"], {"episode": 1}, path=log_file)
            record_gate("write-episode", True, meta={"episode": 1}, path=log_file)
            record_gate("plan-storyboard", False, ["第 1 段镜头 1 的「画面」里出现了时间/秒数「0-3秒」"], {"episode": 1}, path=log_file)
            record_gate("plan-storyboard", True, meta={"episode": 1}, path=log_file)

            summary = summarize_gates(log_file)
            self.assertEqual(summary["write-episode"]["checks"], 2)
            self.assertEqual(summary["write-episode"]["retries"], 1)
            self.assertEqual(summary["write-episode"]["categories"], {"duration_short": 1})
            self.assertEqual(summary["plan-storyboard"]["categories"], {"shot_pollution": 1})

            rendered = format_summary(summary)
            self.assertIn("[write-episode]", rendered)
            self.assertIn("duration_short: 1 次", rendered)
            self.assertIn("shot_pollution: 1 次", rendered)

    def test_classify_reason_covers_core_stages(self):
        self.assertEqual(classify_reason("plan-episodes", "缺少 world：请写清世界观。"), "world_missing")
        self.assertEqual(classify_reason("analyze-assets", "角色 C01 缺少 voice"), "missing_voice")
        self.assertEqual(classify_reason("plan-storyboard", "第 1 段的 references 必须包含场景。"), "missing_scene_ref")

    def test_gates_log_path_skips_in_unittest_but_enables_in_normal_runtime(self):
        self.assertTrue(running_under_tests())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FRAMEDRAMA_GATES_LOG", None)
            self.assertIsNone(gates_log_path())
            with patch("framedrama_lab.gates.running_under_tests", return_value=False):
                self.assertEqual(gates_log_path(), DEFAULT_GATES_LOG)


class GateIntegrationTests(IsolatedAsyncioTestCase):
    async def test_storyboard_validator_writes_retry_and_pass_entries_when_log_enabled(self):
        attempts = 0

        def respond(messages, _info):
            nonlocal attempts
            response = reply_for(messages)
            payload = json.loads(response.parts[0].content)
            if attempts == 0:
                payload["segments"][0]["cuts"][0]["shot"] = "@[图片1] 缓缓走近"
            attempts += 1
            return ModelResponse(parts=[TextPart(json.dumps(payload, ensure_ascii=False))])

        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / ".gates.jsonl"
            with patch.dict(os.environ, {"FRAMEDRAMA_GATES_LOG": str(log_file)}):
                script = ScriptResult.model_validate(script_doc(beats=4))
                assets = AssetResult.model_validate(asset_doc())
                await storyboard(FunctionModel(respond), script, assets)

            summary = summarize_gates(log_file)
            self.assertEqual(summary["plan-storyboard"]["checks"], 2)
            self.assertEqual(summary["plan-storyboard"]["passed"], 1)
            self.assertEqual(summary["plan-storyboard"]["retries"], 1)
            self.assertEqual(summary["plan-storyboard"]["categories"], {"shot_pollution": 1})
