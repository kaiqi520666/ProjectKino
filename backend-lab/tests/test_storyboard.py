import json
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from framedrama_lab.schema import AssetResult, Beat, ScriptResult
from framedrama_lab.storyboard import (
    CutDesign, SegmentDesign, compose_seedance, episode_asset_ids, segment_asset_ids,
    split_cuts, split_episode, storyboard, storyboard_problems, world_style_warnings,
)


def script_doc(cap=15, beats=10):
    return {
        "settings": {
            "name": "关外香头", "ratio": "16:9", "language": "zh-CN",
            "visualStyle": "民国东北民俗悬疑，写实", "episodeCount": 1, "maxSegmentDuration": cap,
        },
        "outline": {
            "continuity": "线索依次揭晓。",
            "world": {
                "kind": "historical",
                "era": "1942 年，民国东北山村",
                "baseline": "土坯房、松木梁、纸窗、煤油灯；无电灯、无塑料。",
            },
            "characters": [{"id": "C01", "name": "陈九河", "role": "香头"}],
            "scenes": [{"id": "S01", "name": "靠山屯坟地", "kind": "外景", "time": "夜"}],
            "props": [{"id": "P01", "name": "枣木烟袋", "role": "主角标志物"}],
            "episodes": [{"number": 1, "title": "坟头", "summary": "s", "hook": "h", "suspense": "s",
                          "ending": "e", "characterIds": ["C01"], "sceneIds": ["S01"], "propIds": ["P01"]}],
        },
        "episodes": [{
            "number": 1, "title": "坟头", "summary": "s", "targetSeconds": 120,
            "seconds": round(beats * 2.5, 1), "hook": "灯灭。", "cliff": "门外有人。", "hookBeat": [1, 1],
            "scenes": [{"sceneId": "S01", "characters": ["C01"], "props": ["P01"],
                        "flow": [{"action": f"第 {index} 个动作。"} for index in range(beats)]}],
            "script": "第一场",
        }],
    }


def asset_doc():
    return {
        "settings": {
            "name": "关外香头", "ratio": "16:9", "language": "zh-CN",
            "visualStyle": "民国东北民俗悬疑，写实", "episodeCount": 1, "maxSegmentDuration": 15,
        },
        "assets": [
            {"id": "C01", "kind": "character", "name": "陈九河", "description": "香头", "prompt": "p",
             "episodeNumbers": [1], "voice": "四十多岁男性；沙哑低沉的男中低音；语速慢；东北口音"},
            {"id": "S01", "kind": "scene", "name": "靠山屯坟地", "description": "坟地", "prompt": "p", "episodeNumbers": [1]},
            {"id": "P01", "kind": "prop", "name": "枣木烟袋", "description": "烟袋", "prompt": "p", "episodeNumbers": [1]},
        ],
    }


def reply_for(messages):
    user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
    data = json.loads(user.content)
    assert data["settings"]["language"] == "zh-CN"
    segments = [
        {
            "id": segment["id"],
            "references": [asset["id"] for asset in segment["assets"]],
            "blocking": "他站在门口，面朝北。",
            "soundscape": "夜风声",
            "music": "低沉的弦乐持续音",
            "cuts": [
                {
                    "index": cut["index"], "shotSize": "中景", "camera": "固定镜头",
                    "lens": "35mm 广角，中景深", "cameraPosition": "他 + 平视正面",
                    "composition": "三分法", "shot": "一名中年男人站在坟前",
                    "eyeline": "坟头", "focus": "锁定人物上半身", "stability": "稳定",
                    "framePrompt": f"第 {segment['id']} 段第 {cut['index']} 切的分镜图",
                }
                for cut in segment["cuts"]
            ],
        }
        for segment in data["segments"]
    ]
    return ModelResponse(parts=[TextPart(json.dumps({"segments": segments}, ensure_ascii=False))])


class SplitTests(TestCase):
    def episode(self, cap=15, beats=10):
        return ScriptResult.model_validate(script_doc(cap, beats)).episodes[0]

    def test_segments_split_on_the_cap_and_never_cross_scenes(self):
        segments = split_episode(self.episode(), 15)
        self.assertEqual([segment.seconds for segment in segments], [15.0, 10.0])
        self.assertEqual([segment.beat_range for segment in segments], [(1, 6), (7, 10)])

    def test_cuts_stay_within_five_seconds(self):
        segments = split_episode(self.episode(), 15)
        self.assertEqual([[cut.seconds for cut in segment.cuts] for segment in segments],
                         [[5.0, 5.0, 5.0], [5.0, 5.0]])
        self.assertEqual([cut.beat_range for cut in segments[0].cuts], [(1, 2), (3, 4), (5, 6)])

    def test_segment_seconds_are_integers_and_never_exceed_the_cap(self):
        for cap in (15, 30):
            with self.subTest(cap=cap):
                segments = split_episode(self.episode(cap=cap, beats=14), cap)
                self.assertTrue(all(isinstance(segment.seconds, int) for segment in segments))
                self.assertTrue(all(segment.seconds <= cap for segment in segments))

    def test_short_tail_is_merged_into_the_previous_cut(self):
        numbered = [
            (Beat(action="一。"), 1),
            (Beat(action="二。"), 2),
            (Beat(speaker="C01", line="短。"), 3),
        ]
        cuts = split_cuts(numbered)
        self.assertEqual(len(cuts), 1)
        self.assertEqual(cuts[0].seconds, 5.4)
        self.assertEqual(cuts[0].beat_range, (1, 3))

    def test_a_single_short_line_may_form_its_own_cut(self):
        script = ScriptResult.model_validate(script_doc(beats=1))
        script.episodes[0].scenes[0].flow = [Beat(speaker="C01", line="短。")]
        script.episodes[0].seconds = 0.4
        segments = split_episode(script.episodes[0], 15)
        self.assertEqual(segments[0].cuts[0].seconds, 0.4)

    def test_segment_assets_are_scene_plus_cast_and_props(self):
        segment = split_episode(self.episode(), 15)[0]
        self.assertEqual(segment_asset_ids(segment), ["S01", "C01", "P01"])
        self.assertEqual(episode_asset_ids(self.episode()), ["S01", "C01", "P01"])


class WorldStyleTests(TestCase):
    def script_with(self, kind, label):
        doc = script_doc()
        doc["settings"]["visualStyle"] = "x"
        doc["settings"]["visualStyleLabel"] = label
        doc["outline"]["world"]["kind"] = kind
        return ScriptResult.model_validate(doc)

    def test_period_style_against_a_modern_world_warns(self):
        self.assertTrue(world_style_warnings(self.script_with("modern", "古装写实")))

    def test_scifi_style_against_a_historical_world_warns(self):
        self.assertTrue(world_style_warnings(self.script_with("historical", "3D赛博朋克")))

    def test_matching_style_and_world_stay_quiet(self):
        self.assertEqual(world_style_warnings(self.script_with("historical", "民国复古写实")), [])


class StoryboardTests(IsolatedAsyncioTestCase):
    async def test_designs_every_segment_and_cut_with_deterministic_timing(self):
        script = ScriptResult.model_validate(script_doc())
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, assets)

        board = result.episodes[0]
        self.assertEqual([clip.durationSeconds for clip in board.clips], [15.0, 10.0])
        self.assertEqual([len(clip.cuts) for clip in board.clips], [3, 2])
        self.assertEqual([[cut.seconds for cut in clip.cuts] for clip in board.clips],
                         [[5.0, 5.0, 5.0], [5.0, 5.0]])
        self.assertEqual(board.clips[0].beats, (1, 6))
        self.assertEqual(board.clips[0].cuts[0].beats, (1, 2))
        self.assertEqual(board.clips[0].blocking, "他站在门口，面朝北。")
        self.assertEqual(board.clips[0].assetIds, ["C01", "S01", "P01"])
        self.assertEqual([ref.index for ref in board.clips[0].references], [1, 2, 3])
        self.assertEqual([ref.assetId for ref in board.clips[0].references], ["C01", "S01", "P01"])
        self.assertEqual(board.clips[0].references[0].name, "陈九河")
        self.assertEqual(storyboard_problems(result, script), [])

    async def test_composed_prompt_follows_the_seedance_shape(self):
        script = ScriptResult.model_validate(script_doc())
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, assets)
        prompt = result.episodes[0].clips[0].prompt

        self.assertTrue(prompt.startswith("@[图片1] = 陈九河\n@[图片2] = 靠山屯坟地\n@[图片3] = 枣木烟袋"))
        self.assertIn("【人物关系与构图逻辑】", prompt)
        self.assertIn("【镜头1】", prompt)
        for field in ("焦距：35mm 广角，中景深", "机位：", "构图：三分法", "运镜：固定镜头", "景别：中景",
                      "画面：一名中年男人站在坟前", "台词：{}", "视线落点：坟头", "焦点：", "稳定性：稳定"):
            self.assertIn(field, prompt)
        self.assertIn("<夜风声>", prompt)
        self.assertIn("（低沉的弦乐持续音）", prompt)
        self.assertNotIn("不生成背景音乐", prompt)
        self.assertIn("世界观：1942 年，民国东北山村；土坯房", prompt)
        self.assertNotIn("无电灯", prompt.split("【约束】")[0])
        self.assertIn("3. 无电灯、无塑料", prompt)
        self.assertIn("视觉风格：民国东北民俗悬疑，写实", prompt)
        self.assertIn("【约束】", prompt)
        self.assertIn("保持无字幕", prompt)

    def test_composer_only_declares_the_references_it_was_given(self):
        script = ScriptResult.model_validate(script_doc(beats=3))
        segment = split_episode(script.episodes[0], 15)[0]
        design = SegmentDesign(
            id=1, references=["S01", "C01"], blocking="他站在坟前。",
            cuts=[CutDesign(
                index=1, shotSize="中景", camera="固定镜头", lens="35mm 广角，中景深",
                cameraPosition="他 + 平视正面", composition="三分法", shot="一名中年男人站在坟前",
                eyeline="坟头", focus="锁定人物上半身", stability="稳定", framePrompt="分镜图",
            )],
        )
        text = compose_seedance(segment, design, script, AssetResult.model_validate(asset_doc()))
        self.assertIn("@[图片1] = 陈九河", text)
        self.assertIn("@[图片2] = 靠山屯坟地", text)
        self.assertNotIn("@[图片3]", text)

    async def test_dialogue_is_copied_verbatim_into_braces(self):
        doc = script_doc(beats=3)
        doc["episodes"][0]["scenes"][0]["flow"] = [
            {"action": "他抬眼。"},
            {"speaker": "C01", "line": "坐着说。", "delivery": "低声"},
            {"action": "灯灭了。"},
        ]
        doc["episodes"][0]["seconds"] = 5.9
        script = ScriptResult.model_validate(doc)
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, assets)
        prompt = result.episodes[0].clips[0].prompt
        self.assertIn("台词（陈九河，低声）：{坐着说。}", prompt)
        self.assertIn("【角色音色】", prompt)
        self.assertIn("@[图片1] 陈九河：四十多岁男性", prompt)

    async def test_background_music_can_be_switched_off(self):
        doc = script_doc()
        doc["settings"]["backgroundMusic"] = False
        script = ScriptResult.model_validate(doc)
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, assets)
        prompt = result.episodes[0].clips[0].prompt
        self.assertNotIn("（低沉的弦乐持续音）", prompt)
        self.assertIn("<夜风声>", prompt)
        self.assertIn("不生成背景音乐；只保留对白、环境音与动作音效", prompt)

    async def test_design_requests_are_split_into_small_batches(self):
        sizes: list[int] = []

        def respond(messages, info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            if "segments" in data:
                sizes.append(len(data["segments"]))
            return reply_for(messages)

        script = ScriptResult.model_validate(script_doc(beats=60))
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(respond), script, assets)
        self.assertEqual(len(result.episodes[0].clips), 10)
        self.assertEqual(sum(sizes), 10)
        self.assertTrue(all(size <= 4 for size in sizes))
        self.assertGreater(len(sizes), 1)

    async def test_missing_asset_catalog_entry_fails_loudly(self):
        script = ScriptResult.model_validate(script_doc())
        doc = asset_doc()
        doc["assets"] = [asset for asset in doc["assets"] if asset["id"] != "P01"]
        with self.assertRaises(ValueError):
            await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, AssetResult.model_validate(doc))

    async def test_problems_flag_a_cut_outside_the_length_rule(self):
        script = ScriptResult.model_validate(script_doc(cap=30))
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, assets)
        result.episodes[0].clips[0].cuts[0].seconds = 12
        self.assertTrue(any("镜头 1" in item for item in storyboard_problems(result, script)))

    async def test_problems_flag_a_beat_gap(self):
        script = ScriptResult.model_validate(script_doc())
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(lambda messages, _info: reply_for(messages)), script, assets)
        result.episodes[0].clips[1].beats = (8, 10)
        self.assertTrue(any("节拍从" in item or "覆盖到" in item for item in storyboard_problems(result, script)))

    async def test_retries_when_references_miss_scene_duplicate_or_use_unknown_asset(self):
        attempts = 0
        bad_refs = [["C01"], ["S01", "C01", "C01"], ["S01", "C99"]]

        def respond(messages, _info):
            nonlocal attempts
            response = reply_for(messages)
            payload = json.loads(response.parts[0].content)
            if attempts < len(bad_refs):
                payload["segments"][0]["references"] = bad_refs[attempts]
            attempts += 1
            return ModelResponse(parts=[TextPart(json.dumps(payload, ensure_ascii=False))])

        script = ScriptResult.model_validate(script_doc(beats=4))
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(respond), script, assets)
        self.assertEqual(attempts, len(bad_refs) + 1)
        self.assertEqual(result.episodes[0].clips[0].assetIds, ["C01", "S01", "P01"])

    async def test_retries_when_cut_shot_contains_character_name(self):
        attempts = 0

        def respond(messages, _info):
            nonlocal attempts
            response = reply_for(messages)
            payload = json.loads(response.parts[0].content)
            if attempts == 0:
                payload["segments"][0]["cuts"][0]["shot"] = "陈九河站在坟前点烟"
            attempts += 1
            return ModelResponse(parts=[TextPart(json.dumps(payload, ensure_ascii=False))])

        script = ScriptResult.model_validate(script_doc(beats=4))
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(respond), script, assets)
        self.assertEqual(attempts, 2)
        self.assertNotIn("画面：陈九河", result.episodes[0].clips[0].prompt)

    async def test_retries_when_cut_shot_contains_timing_or_protocol_pollution(self):
        attempts = 0
        bad_shots = [
            "0-3秒，一名中年男人抬头看向坟头",
            "第3秒时一名中年男人转身",
            "00:02 画面切近，一名中年男人坐下",
            "@[图片1] 缓缓走近坟头",
            "【镜头1】一名中年男人蹲下点烟",
        ]

        def respond(messages, _info):
            nonlocal attempts
            response = reply_for(messages)
            payload = json.loads(response.parts[0].content)
            if attempts < len(bad_shots):
                payload["segments"][0]["cuts"][0]["shot"] = bad_shots[attempts]
            attempts += 1
            return ModelResponse(parts=[TextPart(json.dumps(payload, ensure_ascii=False))])

        script = ScriptResult.model_validate(script_doc(beats=4))
        assets = AssetResult.model_validate(asset_doc())
        result = await storyboard(FunctionModel(respond), script, assets)
        self.assertEqual(attempts, len(bad_shots) + 1)
        self.assertIn("画面：一名中年男人站在坟前", result.episodes[0].clips[0].prompt)

    async def test_subsequent_batches_receive_previous_blocking(self):
        seen_previous: list[dict | None] = []

        def respond(messages, _info):
            user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
            data = json.loads(user.content)
            seen_previous.append(data.get("previousBlocking"))
            response = reply_for(messages)
            payload = json.loads(response.parts[0].content)
            for seg in payload["segments"]:
                seg["blocking"] = f"第 {seg['id']} 段走位"
            return ModelResponse(parts=[TextPart(json.dumps(payload, ensure_ascii=False))])

        script = ScriptResult.model_validate(script_doc(beats=60))
        assets = AssetResult.model_validate(asset_doc())
        await storyboard(FunctionModel(respond), script, assets)

        self.assertEqual(len(seen_previous), 3)
        self.assertIsNone(seen_previous[0])
        self.assertEqual(seen_previous[1], {
            "segmentId": 4, "sceneId": "S01", "scene": "靠山屯坟地", "blocking": "第 4 段走位",
        })
        self.assertEqual(seen_previous[2], {
            "segmentId": 8, "sceneId": "S01", "scene": "靠山屯坟地", "blocking": "第 8 段走位",
        })
