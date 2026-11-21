import json
from unittest import TestCase

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from framedrama_lab.api import app, get_model


def line_text(chars=25):
    return ("台词内容正好凑够字数用来试跑时长" * 4)[:chars]


def settings(**overrides):
    base = {
        "name": "关外香头", "ratio": "16:9", "language": "zh-CN",
        "visualStyle": "民国写实", "episodeCount": 1, "maxSegmentDuration": 15,
    }
    return {**base, **overrides}


def outline_doc():
    return {
        "continuity": "线索依次揭晓。",
        "world": {
            "kind": "historical",
            "era": "1942 年，民国东北山村",
            "baseline": "土坯房、松木梁、纸窗、煤油灯；无电灯、无塑料。",
        },
        "characters": [{"id": "C01", "name": "陈九河", "role": "香头"}],
        "scenes": [{"id": "S01", "name": "靠山屯坟地", "kind": "外景", "time": "夜"}],
        "props": [{"id": "P01", "name": "枣木烟袋", "role": "主角标志物"}],
        "episodes": [{
            "number": 1, "title": "坟头", "summary": "档案失踪。", "hook": "灯先灭。",
            "suspense": "门外有人。", "ending": "灯灭。",
            "characterIds": ["C01"], "sceneIds": ["S01"], "propIds": ["P01"],
        }],
    }


def episode_draft(number):
    flow = [{"action": "他抬眼看向门口。"}]
    for index in range(18):
        flow.append({"speaker": "C01", "line": line_text(25), "delivery": "低声"})
        if index % 3 == 2:
            flow.append({"action": "远处传来一声闷响。"})
    flow.append({"action": "灯灭了。"})
    return {
        "number": number, "title": "坟头", "summary": "档案失踪。",
        "hook": "灯先灭。", "cliff": "门外有人。", "hookBeat": [1, 1],
        "scenes": [{"sceneId": "S01", "characters": ["C01"], "props": ["P01"], "flow": flow}],
    }


def script_doc():
    return {
        "settings": settings(),
        "outline": outline_doc(),
        "episodes": [{**episode_draft(1), "targetSeconds": 120, "seconds": 120.0, "script": "第一场"}],
    }


def assets_doc():
    return {
        "settings": settings(),
        "assets": [
            {"id": "C01", "kind": "character", "name": "陈九河", "description": "香头",
             "prompt": "参考图", "episodeNumbers": [1], "voice": "四十多岁男性；沙哑男中音；东北口音"},
            {"id": "S01", "kind": "scene", "name": "靠山屯坟地", "description": "坟地",
             "prompt": "空景图", "episodeNumbers": [1]},
            {"id": "P01", "kind": "prop", "name": "枣木烟袋", "description": "烟袋",
             "prompt": "道具图", "episodeNumbers": [1]},
        ],
    }


def respond(messages, _info):
    user = next(part for message in messages for part in message.parts if isinstance(part, UserPromptPart))
    data = json.loads(user.content)
    if "segments" in data:
        segments = [
            {
                "id": segment["id"],
                "references": [asset["id"] for asset in segment["assets"]],
                "blocking": "他站在门口。",
                "soundscape": "夜风声",
                "music": "",
                "cuts": [
                    {
                        "index": cut["index"], "shotSize": "中景", "camera": "固定镜头",
                        "lens": "35mm 广角，中景深", "cameraPosition": "他 + 平视正面",
                        "composition": "三分法", "shot": "一名中年男人站在坟前",
                        "eyeline": "坟头", "focus": "锁定人物上半身", "stability": "稳定",
                        "framePrompt": "分镜图",
                    }
                    for cut in segment["cuts"]
                ],
            }
            for segment in data["segments"]
        ]
        return ModelResponse(parts=[TextPart(json.dumps({"segments": segments}, ensure_ascii=False))])
    if "kind" in data:
        def mock_prompt(kind, asset_id):
            if kind == "scene":
                return f"无人空景，{asset_id}"
            if kind == "prop":
                return f"纯白背景，无手，手持级尺度，{asset_id}"
            return f"人物描述，{asset_id}"

        designs = [
            {
                "id": entry["id"], "description": "描述", "prompt": mock_prompt(data["kind"], entry["id"]),
                "voice": "四十多岁男性；沙哑男中音" if data["kind"] == "character" else "",
            }
            for entry in data["assets"]
        ]
        return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])
    if "nextEpisodeNumber" in data:
        next_num = data["nextEpisodeNumber"]
        return ModelResponse(parts=[TextPart(json.dumps({
            "plan": {
                "number": next_num, "title": f"续写第 {next_num} 集", "summary": "续写梗概。",
                "hook": "灯又灭。", "suspense": "有人敲门。", "ending": "门开。",
                "characterIds": ["C01"], "sceneIds": ["S01"], "propIds": ["P01"],
            },
            "newCharacters": [], "newScenes": [], "newProps": [], "continuityUpdate": "",
        }, ensure_ascii=False))])
    if "budget" in data:
        return ModelResponse(parts=[TextPart(json.dumps(episode_draft(data["episode"]["number"]), ensure_ascii=False))])
    return ModelResponse(parts=[TextPart(json.dumps(outline_doc(), ensure_ascii=False))])


class ApiTests(TestCase):
    def setUp(self):
        app.dependency_overrides[get_model] = lambda: FunctionModel(respond)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_reports_the_configured_model(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_story_returns_a_script_with_rendered_text(self):
        response = self.client.post("/api/story", json={
            "settings": settings(), "mode": "story", "text": "一份档案消失。", "feedback": "节奏更快",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["episodes"]), 1)
        self.assertTrue(body["episodes"][0]["script"].startswith("第一场"))
        self.assertEqual(body["episodes"][0]["seconds"], 120.0)
        self.assertEqual(body["settings"]["language"], "zh-CN")

    def test_story_episode_rewrites_a_single_episode(self):
        response = self.client.post("/api/story/episode", json={
            "script": script_doc(), "episode": 1, "mode": "story", "text": "一份档案消失。", "feedback": "悬念更强",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["number"], 1)
        self.assertTrue(body["script"].startswith("第一场"))

    def test_story_episode_rejects_unknown_episode(self):
        response = self.client.post("/api/story/episode", json={
            "script": script_doc(), "episode": 9,
        })
        self.assertEqual(response.status_code, 400)

    def test_story_episode_append_adds_next_structured_episode(self):
        response = self.client.post("/api/story/episode/append", json={
            "script": script_doc(), "mode": "story", "text": "一份档案消失。", "feedback": "反转升级",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["settings"]["episodeCount"], 2)
        self.assertEqual([ep["number"] for ep in body["episodes"]], [1, 2])
        self.assertEqual(len(body["outline"]["episodes"]), 2)

    def test_story_rejects_settings_the_frontend_cannot_send(self):
        response = self.client.post("/api/story", json={
            "settings": settings(language="ja"), "mode": "story", "text": "一份档案消失。",
        })
        self.assertEqual(response.status_code, 422)

    def test_assets_use_the_ids_from_the_script(self):
        response = self.client.post("/api/assets", json={"script": script_doc()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([asset["id"] for asset in response.json()["assets"]], ["C01", "S01", "P01"])

    def test_assets_reject_ids_missing_from_the_outline(self):
        doc = script_doc()
        doc["episodes"][0]["scenes"][0]["characters"] = ["C09"]
        response = self.client.post("/api/assets", json={"script": doc})
        self.assertEqual(response.status_code, 400)
        self.assertIn("C09", response.json()["detail"])

    def test_storyboard_splits_clips_within_the_segment_cap(self):
        response = self.client.post("/api/storyboard", json={"script": script_doc(), "assets": assets_doc()})
        self.assertEqual(response.status_code, 200)
        episode = response.json()["episodes"][0]
        self.assertTrue(episode["clips"])
        self.assertTrue(all(clip["durationSeconds"] <= 15 for clip in episode["clips"]))
        self.assertTrue(all(clip["cuts"] for clip in episode["clips"]))
        self.assertTrue(all(clip["prompt"].startswith("@[图片1]") for clip in episode["clips"]))
        self.assertTrue(all("【镜头1】" in clip["prompt"] for clip in episode["clips"]))
        self.assertEqual([clip["assetIds"] for clip in episode["clips"]], [["C01", "S01", "P01"]] * len(episode["clips"]))

    def test_storyboard_can_target_one_episode(self):
        response = self.client.post("/api/storyboard", json={
            "script": script_doc(), "assets": assets_doc(), "episode": 2,
        })
        self.assertEqual(response.status_code, 400)
