import asyncio
import json
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from framedrama_lab.analyze_assets import analyze_assets, inventory
from framedrama_lab.schema import Asset, ScriptResult


def script_doc():
    return {
        "settings": {
            "name": "关外香头", "ratio": "16:9", "language": "zh-CN",
            "visualStyle": "民国东北民俗悬疑，写实", "episodeCount": 2, "maxSegmentDuration": 15,
        },
        "outline": {
            "continuity": "线索依次揭晓。",
            "world": {
                "kind": "historical",
                "era": "1942 年，民国东北山村",
                "baseline": "土坯房、松木梁、纸窗、煤油灯；无电灯、无塑料。",
            },
            "characters": [
                {"id": "C01", "name": "陈九河", "role": "香头", "voice": "短句，带旧腔"},
                {"id": "C02", "name": "栓子", "role": "徒弟"},
                {"id": "C03", "name": "未出场角色", "role": "规划了但没写进剧本"},
            ],
            "scenes": [
                {"id": "S01", "name": "靠山屯坟地", "kind": "外景", "time": "夜"},
                {"id": "S02", "name": "闲置土屋", "kind": "内景", "time": "夜"},
            ],
            "props": [{"id": "P01", "name": "枣木烟袋", "role": "主角标志物"}],
            "episodes": [
                {"number": 1, "title": "坟头", "summary": "s", "hook": "h", "suspense": "s", "ending": "e",
                 "characterIds": ["C01"], "sceneIds": ["S01"]},
                {"number": 2, "title": "夜访", "summary": "s", "hook": "h", "suspense": "s", "ending": "e",
                 "characterIds": ["C01", "C02"], "sceneIds": ["S01"]},
            ],
        },
        "episodes": [
            {
                "number": 1, "title": "坟头", "summary": "s", "targetSeconds": 120, "seconds": 10.0,
                "hook": "灯灭。", "cliff": "门外有人。", "hookBeat": [1, 1],
                "scenes": [{"sceneId": "S01", "lighting": "血红晚霞压低", "characters": ["C01"], "props": ["P01"],
                            "flow": [{"action": "陈九河蹲在荒草坟前，掏出枣木烟袋磕了磕灰。"}]}],
                "script": "第一场",
            },
            {
                "number": 2, "title": "夜访", "summary": "s", "targetSeconds": 120, "seconds": 10.0,
                "hook": "门响。", "cliff": "脚步声远去。", "hookBeat": [1, 1],
                "scenes": [{"sceneId": "S01", "characters": ["C01", "C02"],
                            "flow": [{"action": "门开了。"}]}],
                "script": "第一场",
            },
        ],
    }


class InventoryTests(TestCase):
    def test_collects_only_assets_used_by_the_final_script(self):
        items = inventory(ScriptResult.model_validate(script_doc()))
        found = {item.id: item for item in items}
        self.assertEqual(list(found), ["C01", "C02", "S01", "P01"])
        self.assertEqual(found["C01"].episodes, (1, 2))
        self.assertEqual(found["C02"].episodes, (2,))
        self.assertEqual(found["P01"].episodes, (1,))
        self.assertNotIn("C03", found)
        self.assertNotIn("S02", found)

    def test_character_profile_carries_role_and_voice(self):
        items = inventory(ScriptResult.model_validate(script_doc()))
        profile = next(item.profile for item in items if item.id == "C01")
        self.assertIn("香头", profile)
        self.assertIn("短句", profile)

    def test_inventory_extracts_script_clues_and_lighting(self):
        items = {item.id: item for item in inventory(ScriptResult.model_validate(script_doc()))}
        self.assertTrue(any("血红晚霞压低" in clue for clue in items["S01"].clues))
        self.assertTrue(any("荒草坟前" in clue for clue in items["S01"].clues))
        self.assertTrue(any("陈九河" in clue for clue in items["C01"].clues))
        self.assertTrue(any("枣木烟袋" in clue for clue in items["P01"].clues))

    def test_unknown_asset_ids_fail_loudly(self):
        data = script_doc()
        data["episodes"][0]["scenes"][0]["characters"] = ["C09"]
        with self.assertRaises(ValueError):
            inventory(ScriptResult.model_validate(data))


def _valid_prompt(kind: str, asset_id: str) -> str:
    if kind == "scene":
        return f"静态参考图，无人空景，{asset_id}"
    if kind == "prop":
        return f"静态参考图，纯白背景，无手，手持级尺度，{asset_id}"
    return f"静态参考图，{asset_id}"


class AnalyzeAssetsTests(IsolatedAsyncioTestCase):
    async def test_designs_every_asset_and_retries_a_partial_batch(self):
        attempts = {"character": 0}
        seen_clues: dict[str, list[str]] = {}

        def respond(messages, _info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            self.assertEqual(data["settings"]["language"], "zh-CN")
            self.assertIn("visualStyleLabel", data["settings"])
            for entry in data["assets"]:
                if "scriptClues" in entry:
                    seen_clues[entry["id"]] = entry["scriptClues"]
            ids = [entry["id"] for entry in data["assets"]]
            if data["kind"] == "character":
                attempts["character"] += 1
                if attempts["character"] == 1:
                    ids = ids[:1]
            designs = [
                {
                    "id": asset_id,
                    "description": f"{asset_id} 的剧情用途",
                    "prompt": _valid_prompt(data["kind"], asset_id),
                    "voice": "四十多岁男性；沙哑男中音；语速慢；东北口音" if data["kind"] == "character" else "",
                }
                for asset_id in ids
            ]
            return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])

        result = await analyze_assets(FunctionModel(respond), ScriptResult.model_validate(script_doc()))
        self.assertEqual(attempts["character"], 2)
        self.assertIn("S01", seen_clues)
        self.assertIn("P01", seen_clues)
        self.assertEqual([asset.id for asset in result.assets], ["C01", "C02", "S01", "P01"])
        self.assertEqual([asset.kind for asset in result.assets], ["character", "character", "scene", "prop"])
        self.assertEqual(next(a for a in result.assets if a.id == "C01").episodeNumbers, [1, 2])
        character = next(a for a in result.assets if a.id == "C01")
        self.assertTrue(character.voice)
        self.assertTrue(character.prompt.startswith("角色三视图设定图"))
        self.assertIn("角色：静态参考图，C01。", character.prompt)
        self.assertEqual(next(a for a in result.assets if a.id == "S01").prompt, "静态参考图，无人空景，S01")
        self.assertEqual(next(a for a in result.assets if a.id == "S01").voice, "")

    async def test_rejects_character_names_inside_image_prompts(self):
        attempts = {"character": 0}

        def respond(messages, _info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            designs = []
            for entry in data["assets"]:
                prompt = _valid_prompt(data["kind"], entry["id"])
                if data["kind"] == "character" and entry["id"] == "C01" and attempts["character"] == 0:
                    prompt = "写实参考图，陈九河站在坟前"
                designs.append({
                    "id": entry["id"], "description": "描述", "prompt": prompt,
                    "voice": "青年男性；清亮男声；语速中；标准普通话" if data["kind"] == "character" else "",
                })
            if data["kind"] == "character":
                attempts["character"] += 1
            return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])

        result = await analyze_assets(FunctionModel(respond), ScriptResult.model_validate(script_doc()))
        self.assertEqual(attempts["character"], 2)
        self.assertNotIn("陈九河", next(asset for asset in result.assets if asset.id == "C01").prompt)

    async def test_enforces_empty_scene_and_prop_constraints(self):
        attempts = {"scene": 0, "prop": 0}

        def respond(messages, _info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            kind = data["kind"]
            designs = []
            for entry in data["assets"]:
                prompt = _valid_prompt(kind, entry["id"])
                if kind == "scene" and attempts["scene"] == 0:
                    prompt = "民国写实，荒草坟地，血红晚霞"
                elif kind == "prop" and attempts["prop"] == 0:
                    prompt = "民国写实，枣木烟袋，纯白背景，无手"
                designs.append({
                    "id": entry["id"], "description": "描述", "prompt": prompt,
                    "voice": "青年男性；清亮男声；语速中；标准普通话" if kind == "character" else "",
                })
            if kind in attempts:
                attempts[kind] += 1
            return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])

        result = await analyze_assets(FunctionModel(respond), ScriptResult.model_validate(script_doc()))
        self.assertEqual(attempts["scene"], 2)
        self.assertEqual(attempts["prop"], 2)
        self.assertIn("无人空景", next(asset for asset in result.assets if asset.id == "S01").prompt)
        self.assertIn("手持级尺度", next(asset for asset in result.assets if asset.id == "P01").prompt)

    async def test_designs_all_asset_kinds_concurrently(self):
        started: set[str] = set()
        all_started = asyncio.Event()

        async def respond(messages, _info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            started.add(data["kind"])
            if len(started) == 3:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1.0)
            designs = [
                {
                    "id": entry["id"],
                    "description": f"{entry['id']} 描述",
                    "prompt": _valid_prompt(data["kind"], entry["id"]),
                    "voice": "青年男性；清亮男声；语速中；标准普通话" if data["kind"] == "character" else "",
                }
                for entry in data["assets"]
            ]
            return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])

        result = await analyze_assets(FunctionModel(respond), ScriptResult.model_validate(script_doc()))
        self.assertEqual(started, {"character", "scene", "prop"})
        self.assertEqual([asset.id for asset in result.assets], ["C01", "C02", "S01", "P01"])

    async def test_incremental_analysis_skips_existing_assets_and_preserves_edits(self):
        called_ids: list[str] = []

        def respond(messages, _info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            called_ids.extend(entry["id"] for entry in data["assets"])
            designs = [
                {
                    "id": entry["id"],
                    "description": f"新生成 {entry['id']}",
                    "prompt": _valid_prompt(data["kind"], entry["id"]),
                    "voice": "青年男性；清亮男声；语速中；标准普通话" if data["kind"] == "character" else "",
                }
                for entry in data["assets"]
            ]
            return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])

        existing = [
            Asset(
                id="C01", kind="character", name="陈九河（手改）",
                description="用户手改描述", prompt="用户手改提示词",
                episodeNumbers=[1], voice="用户手改音色",
            ),
            Asset(
                id="S01", kind="scene", name="靠山屯坟地",
                description="老场景", prompt="静态参考图，无人空景，老场景",
                episodeNumbers=[1], voice="",
            ),
            Asset(
                id="P01", kind="prop", name="枣木烟袋",
                description="老道具", prompt="静态参考图，纯白背景，无手，手持级尺度，老道具",
                episodeNumbers=[1], voice="",
            ),
        ]
        result = await analyze_assets(
            FunctionModel(respond), ScriptResult.model_validate(script_doc()), existing=existing,
        )
        # Only C02 is missing; S01 and P01 shouldn't even invoke the model.
        self.assertEqual(called_ids, ["C02"])
        self.assertEqual([asset.id for asset in result.assets], ["C01", "C02", "S01", "P01"])
        c01 = next(asset for asset in result.assets if asset.id == "C01")
        self.assertEqual(c01.name, "陈九河（手改）")
        self.assertEqual(c01.prompt, "用户手改提示词")
        self.assertEqual(c01.voice, "用户手改音色")
        # Episode appearances refreshed from the latest script.
        self.assertEqual(c01.episodeNumbers, [1, 2])
        c02 = next(asset for asset in result.assets if asset.id == "C02")
        self.assertEqual(c02.description, "新生成 C02")
