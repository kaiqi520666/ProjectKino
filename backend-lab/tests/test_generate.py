import json
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx2
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider

from framedrama_lab import generate
from framedrama_lab.generate import Source, append_episode, generate_script, regenerate_episode, script_length, world_problems
from framedrama_lab.schema import ProjectSettings, ScriptResult, World


def settings(count):
    return ProjectSettings(name="纸灯", ratio="16:9", visualStyle="写实", episodeCount=count, maxSegmentDuration=30)


def episode_plan(number, source_lines=None):
    return {
        "number": number, "title": f"线索 {number}", "summary": "档案失踪。",
        "hook": "灯先灭，人后到。", "suspense": "走廊尽头有人没走。", "ending": "灯灭。",
        "characterIds": ["C01"], "sceneIds": ["S01"], "propIds": ["P01"],
        "sourceLines": source_lines or [],
    }


def outline(count):
    return {
        "continuity": "线索依次揭晓。",
        "world": {
            "kind": "historical",
            "era": "1942 年，民国东北山村",
            "baseline": "土坯房、松木梁、纸窗、煤油灯；无电灯、无塑料。",
        },
        "characters": [{"id": "C01", "name": "陈九河", "role": "香头", "voice": "短句，带旧腔"}],
        "scenes": [{"id": "S01", "name": "档案室", "kind": "内景", "time": "夜", "note": "铁柜与一盏台灯"}],
        "props": [{"id": "P01", "name": "旧马灯"}],
        "episodes": [episode_plan(number) for number in range(1, count + 1)],
    }


def line_text(chars=25):
    return ("台词内容正好凑够字数用来试跑时长" * 4)[:chars]


def episode_draft(number):
    flow = [{"action": "他抬眼看向门口。"}]
    for index in range(18):
        flow.append({"speaker": "C01", "line": line_text(25), "delivery": "低声"})
        if index % 3 == 2:
            flow.append({"action": "远处传来一声闷响。"})
    flow.append({"action": "灯灭了。"})
    scene = {"sceneId": "S01", "lighting": "台灯", "characters": ["C01"], "props": ["P01"], "flow": flow}
    return {
        "number": number, "title": f"线索 {number}", "summary": "档案失踪。",
        "hook": "灯先灭，人后到。", "cliff": "走廊尽头有人没走。",
        "hookBeat": [1, 1], "scenes": [scene],
    }


def reply(output=None, *, arguments=None):
    message = {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)}
    finish_reason = "stop"
    if arguments is not None:
        message.update(content=None, tool_calls=[{
            "id": "call_source", "type": "function",
            "function": {"name": "read_source_excerpt", "arguments": json.dumps(arguments)},
        }])
        finish_reason = "tool_calls"
    return httpx2.Response(200, json={
        "id": "mock", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    })


class WorldTests(TestCase):
    def test_missing_world_is_a_problem(self):
        self.assertTrue(world_problems(None))

    def test_vague_era_is_rejected(self):
        for era in ("古代", "古装", "架空", "未来", "现代", "某朝"):
            with self.subTest(era=era):
                self.assertTrue(world_problems(World(kind="historical", era=era, baseline="土坯房、煤油灯；无电灯、无塑料。")))

    def test_kind_specific_era_rules(self):
        good_baseline = "土坯房、松木梁、煤油灯；无电灯、无塑料。"
        self.assertTrue(world_problems(World(kind="historical", era="很久以前", baseline=good_baseline)))
        self.assertTrue(world_problems(World(kind="scifi", era="未来世界", baseline=good_baseline)))
        self.assertTrue(world_problems(World(kind="fantasy", era="随便哪里", baseline=good_baseline)))
        self.assertEqual(world_problems(World(kind="historical", era="1942 年，民国东北山村", baseline=good_baseline)), [])
        self.assertEqual(world_problems(World(kind="modern", era="2024 年，东北小城", baseline=good_baseline)), [])
        self.assertEqual(world_problems(World(kind="scifi", era="2087 年，新九龙立体城", baseline=good_baseline)), [])
        self.assertEqual(world_problems(World(kind="fantasy", era="唐代风格架空，青云山", baseline=good_baseline)), [])

    def test_baseline_must_state_what_is_absent(self):
        problems = world_problems(World(kind="modern", era="当代都市", baseline="高楼、地铁、霓虹灯、写字楼和整片玻璃幕墙。"))
        self.assertTrue(any("没有什么" in item for item in problems))


class GenerateTests(IsolatedAsyncioTestCase):
    def test_settings_accept_the_languages_the_frontend_offers(self):
        for language in ("zh-CN", "zh-TW", "en"):
            with self.subTest(language=language):
                self.assertEqual(
                    ProjectSettings(name="纸灯", ratio="16:9", visualStyle="写实", episodeCount=1,
                                   maxSegmentDuration=15, language=language).language,
                    language,
                )
        with self.assertRaises(ValueError):
            ProjectSettings(name="纸灯", ratio="16:9", visualStyle="写实", episodeCount=1,
                            maxSegmentDuration=15, language="ja")

    def test_settings_carry_a_readable_style_label(self):
        settings = ProjectSettings(
            name="纸灯", ratio="16:9", visualStyle="historical-realism",
            visualStyleLabel="古风写实", episodeCount=1, maxSegmentDuration=15,
        )
        self.assertEqual(settings.visualStyle, "historical-realism")
        self.assertEqual(settings.visualStyleLabel, "古风写实")
        self.assertTrue(settings.backgroundMusic)
        self.assertFalse(ProjectSettings(
            name="纸灯", ratio="16:9", visualStyle="写实", episodeCount=1,
            maxSegmentDuration=15, backgroundMusic=False,
        ).backgroundMusic)

    async def run_with_mock(self, project, source, respond):
        async def handler(request):
            self.assertEqual(request.url.path, "/chat/completions")
            payload = json.loads(request.content)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            self.assertEqual(payload["thinking"], {"type": "disabled"})
            return respond(payload)

        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            provider = DeepSeekProvider(api_key="offline-test", http_client=client)
            model = OpenAIChatModel("deepseek-flash", provider=provider)
            return await generate_script(model, project, source)

    async def test_story_plans_then_writes_each_episode_in_order(self):
        for count in (1, 5):
            with self.subTest(count=count):
                requests = []

                def respond(payload):
                    messages = payload["messages"]
                    user_data = json.loads(next(item["content"] for item in messages if item["role"] == "user"))
                    requests.append(user_data)
                    if "episode" not in user_data:
                        self.assertIn("规划分集", str(messages))
                        self.assertEqual(user_data["mode"], "story")
                        self.assertEqual(user_data["episodeSeconds"], 120)
                        return reply(outline(count))
                    number = user_data["episode"]["number"]
                    self.assertIn("写一集剧本", str(messages))
                    self.assertEqual(user_data["continuity"], "线索依次揭晓。")
                    self.assertEqual(user_data["characters"][0]["name"], "陈九河")
                    self.assertEqual(user_data["scenes"][0]["id"], "S01")
                    self.assertEqual(user_data["budget"]["targetSeconds"], 120)
                    self.assertIn("一份档案消失。", user_data["source"])
                    if number > 1:
                        self.assertIn("灯灭了。", user_data["previousEpisode"]["endingExcerpt"])
                    return reply(episode_draft(number))

                result = await self.run_with_mock(settings(count), Source.from_text("story", "一份档案消失。"), respond)
                self.assertEqual(len(requests), count + 1)
                self.assertEqual([episode.number for episode in result.episodes], list(range(1, count + 1)))
                self.assertEqual([episode.seconds for episode in result.episodes], [120.0] * count)
                self.assertEqual(len(result.outline.characters), 1)
                self.assertEqual(result.settings.maxSegmentDuration, 30)

    async def test_upload_retries_outline_and_episode_then_reads_original_text(self):
        step = 0

        def respond(payload):
            nonlocal step
            step += 1
            messages = payload["messages"]
            user_data = json.loads(next(item["content"] for item in messages if item["role"] == "user"))
            if step == 1:
                bad = outline(1)
                bad["episodes"] = []
                return reply(bad)
            if step == 2:
                self.assertIn("恰好 1 集", str(messages))
                bad = outline(1)
                bad["episodes"][0]["sourceLines"] = [[2, 8]]
                return reply(bad)
            if step == 3:
                self.assertIn("原稿行号范围无效", str(messages))
                good = outline(1)
                good["episodes"][0]["sourceLines"] = [[2, 2]]
                return reply(good)
            if step == 4:
                self.assertEqual(user_data["sourceExcerpts"], ["2: 档案不见了。"])
                broken = episode_draft(1)
                broken["scenes"][0]["flow"] = [{"speaker": "C01", "line": "只有台词。"}]
                return reply(broken)
            if step == 5:
                self.assertIn("剧本质量门", str(messages))
                self.assertIn("没有动作节拍", str(messages))
                self.assertEqual(payload["tools"][0]["function"]["name"], "read_source_excerpt")
                return reply(arguments={"start_line": 1, "end_line": 1})
            if step == 6:
                self.assertTrue(any(message["role"] == "tool" and message["content"] == "1: 第一章 纸灯"
                                    for message in messages))
                return reply(episode_draft(1))
            self.fail(f"多余的请求：第 {step} 次")

        source = Source.from_text("upload", "第一章 纸灯\n档案不见了。")
        result = await self.run_with_mock(settings(1), source, respond)
        self.assertEqual(step, 6)
        self.assertEqual(result.episodes[0].title, "线索 1")
        self.assertIn("陈九河：", result.episodes[0].script)
        self.assertEqual(script_length(" 内景\n灯灭。　"), 5)

    async def test_long_novel_is_digested_before_planning(self):
        original = generate.DIGEST_THRESHOLD_CHARS
        generate.DIGEST_THRESHOLD_CHARS = 10
        stages = []

        def respond(payload):
            user_data = json.loads(next(item["content"] for item in payload["messages"] if item["role"] == "user"))
            if "episode" in user_data:
                stages.append("write")
                return reply(episode_draft(1))
            if "digest" in user_data and user_data["digest"] is not None:
                stages.append("plan")
                self.assertIsNone(user_data["source"])
                self.assertTrue(all(entry["summary"] for entry in user_data["digest"]))
                planned = outline(1)
                planned["episodes"][0]["sourceLines"] = [[1, 4]]
                return reply(planned)
            stages.append("digest")
            self.assertEqual(user_data["lines"], [1, 4])
            return reply({"summary": "档案不见了。", "events": ["灯灭。"]})

        try:
            source = Source.from_text("upload", "第一章 纸灯\n档案不见了。\n第二章 夜访\n门开了。")
            await self.run_with_mock(settings(1), source, respond)
        finally:
            generate.DIGEST_THRESHOLD_CHARS = original
        self.assertEqual(stages[0], "digest")
        self.assertEqual(stages[-1], "write")
        self.assertIn("plan", stages)

    async def test_final_retry_soft_passes_duration_only_drift_with_warning(self):
        attempts = 0

        def short_but_valid_episode():
            # 12 动作（30s）+ 10 句 22 字台词（48.9s）≈ 78.9s，无结构硬伤，但短于 90s 硬底线。
            flow = [{"action": "他推门走进来。"}]
            for index in range(10):
                flow.append({"speaker": "C01", "line": line_text(22), "delivery": "低声"})
                flow.append({"action": f"第 {index + 1} 个动作停顿。"})
            flow.append({"action": "灯灭了。"})
            draft = episode_draft(1)
            draft["scenes"][0]["flow"] = flow
            return draft

        def respond(payload):
            nonlocal attempts
            user_data = json.loads(next(item["content"] for item in payload["messages"] if item["role"] == "user"))
            if "episode" not in user_data:
                return reply(outline(1))
            attempts += 1
            return reply(short_but_valid_episode())

        result = await self.run_with_mock(settings(1), Source.from_text("story", "一份档案消失。"), respond)
        # 首写 1 次 + 重试 5 次后，末次仅剩时长偏差应降级放行，不抛 502。
        self.assertEqual(attempts, 6)
        self.assertEqual(len(result.episodes), 1)
        self.assertLess(result.episodes[0].seconds, 90.0)
        self.assertTrue(any("短于建议区间" in item for item in result.episodes[0].warnings))

    async def test_regenerate_episode_reuses_outline_and_forwards_feedback(self):
        seen_payloads = []

        async def handler(request):
            payload = json.loads(request.content)
            user_data = json.loads(next(item["content"] for item in payload["messages"] if item["role"] == "user"))
            seen_payloads.append(user_data)
            draft = episode_draft(2)
            draft["title"] = "重写后的线索 2"
            return reply(draft)

        base = ScriptResult.model_validate({
            "settings": settings(2).model_dump(),
            "outline": outline(2),
            "episodes": [
                {**episode_draft(1), "targetSeconds": 120, "seconds": 120.0, "script": "第一集结尾。"},
                {**episode_draft(2), "targetSeconds": 120, "seconds": 120.0, "script": "旧第二集正文。"},
            ],
        })
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            model = OpenAIChatModel("deepseek-flash", provider=DeepSeekProvider(api_key="offline-test", http_client=client))
            rewritten = await regenerate_episode(
                model, base, 2, source=Source.from_text("story", "一份档案消失。"), feedback="冲突提前到开场",
            )

        self.assertEqual(len(seen_payloads), 1)
        self.assertEqual(seen_payloads[0]["revisionFeedback"], "冲突提前到开场")
        self.assertEqual(seen_payloads[0]["previousDraft"]["script"], "旧第二集正文。")
        self.assertEqual(seen_payloads[0]["previousEpisode"]["endingExcerpt"], "第一集结尾。")
        self.assertEqual(rewritten.number, 2)
        self.assertEqual(rewritten.title, "重写后的线索 2")

    async def test_append_episode_extends_outline_and_writes_next_episode(self):
        seen_payloads = []

        async def handler(request):
            payload = json.loads(request.content)
            user_data = json.loads(next(item["content"] for item in payload["messages"] if item["role"] == "user"))
            seen_payloads.append(user_data)
            if "nextEpisodeNumber" in user_data:
                self.assertEqual(user_data["nextEpisodeNumber"], 2)
                self.assertEqual(user_data["nextIds"], {"character": "C02", "scene": "S02", "prop": "P02"})
                self.assertEqual(user_data["direction"], "引入老物业管理员")
                return reply({
                    "plan": {
                        "number": 2, "title": "旧钥匙", "summary": "老物业现身交出旧钥匙。",
                        "hook": "走廊灯忽灭。", "suspense": "钥匙沾着铁锈与红漆。", "ending": "门开了。",
                        "characterIds": ["C01", "C02"], "sceneIds": ["S01"], "propIds": ["P01"],
                    },
                    "newCharacters": [{"id": "C02", "name": "老周", "role": "老物业管理员", "voice": "低哑慢速"}],
                    "newScenes": [],
                    "newProps": [],
                    "continuityUpdate": "老周保管着备用钥匙。",
                })
            draft = episode_draft(2)
            draft["title"] = "旧钥匙"
            return reply(draft)

        base = ScriptResult.model_validate({
            "settings": settings(1).model_dump(),
            "outline": outline(1),
            "episodes": [{**episode_draft(1), "targetSeconds": 120, "seconds": 120.0, "script": "第一集结尾。"}],
        })
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            model = OpenAIChatModel("deepseek-flash", provider=DeepSeekProvider(api_key="offline-test", http_client=client))
            updated = await append_episode(model, base, source=Source.from_text("story", "一份档案消失。"), feedback="引入老物业管理员")

        self.assertEqual(len(seen_payloads), 2)
        self.assertEqual(updated.settings.episodeCount, 2)
        self.assertEqual([ep.number for ep in updated.episodes], [1, 2])
        self.assertEqual([c.id for c in updated.outline.characters], ["C01", "C02"])
        self.assertIn("老周保管着备用钥匙", updated.outline.continuity)
        self.assertEqual(updated.episodes[1].title, "旧钥匙")
