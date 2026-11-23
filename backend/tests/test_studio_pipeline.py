import json

import pytest
from pydantic_ai import RunUsage
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from app.modules.llm_engine.asset_gen import analyze_assets
from app.modules.llm_engine.schema import Asset, ProjectSettings
from app.modules.llm_engine.script_gen import Source, append_episode, generate_script
from app.modules.llm_engine.storyboard_gen import storyboard


def _valid_outline(count: int = 1) -> dict:
    return {
        "continuity": "主线连续。",
        "world": {
            "kind": "modern",
            "era": "2025 年，南方二线城市老小区",
            "baseline": "老式砖混楼房、木门、铁窗、暖黄台灯；无未来科幻设施。",
        },
        "characters": [
            {"id": "C01", "name": "林晚", "role": "主角", "voice": "冷静短句"},
        ],
        "scenes": [
            {"id": "S01", "name": "302室卧室", "kind": "内景", "time": "夜", "note": "旧卧室"},
        ],
        "props": [
            {"id": "P01", "name": "木质晾衣杆", "role": "敲墙试探工具"},
        ],
        "episodes": [
            {
                "number": idx,
                "title": f"第{idx}集",
                "summary": "半夜敲墙声响起。",
                "hook": "十一点整敲墙声准时响起。",
                "suspense": "隔壁是空房。",
                "ending": "门缝塞进一张纸条。",
                "characterIds": ["C01"],
                "sceneIds": ["S01"],
                "propIds": ["P01"],
            }
            for idx in range(1, count + 1)
        ],
    }


def _valid_episode(number: int = 1, *, short: bool = False) -> dict:
    if short:
        flow = [{"action": "林晚猛地睁开眼。"}]
    else:
        flow = []
        for idx in range(14):
            flow.append({"action": f"林晚第 {idx + 1} 次靠近墙面仔细听动静，手里紧握木质晾衣杆。"})
            flow.append(
                {
                    "speaker": "C01",
                    "delivery": "低声压抑",
                    "line": "十一点整三短一长，隔壁明明空了半年，到底是谁在敲墙？",
                }
            )
    return {
        "number": number,
        "title": f"三短一长-{number}",
        "summary": "十一点整墙里传来三短一长敲击声。",
        "hook": "十一点整敲墙声响起。",
        "cliff": "门缝滑进一张带血字条。",
        "hookBeat": [1, 1],
        "scenes": [
            {
                "sceneId": "S01",
                "lighting": "暖黄台灯微光",
                "characters": ["C01"],
                "props": ["P01"],
                "flow": flow,
            }
        ],
    }


async def test_generate_script_tracks_usage_and_emits_progress_steps():
    progress_events: list[tuple[int, int, str, int]] = []

    async def on_progress(step_idx: int, step_total: int, label: str, pct: int) -> None:
        progress_events.append((step_idx, step_total, label, pct))

    def respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        if "episode" not in data:
            body = _valid_outline(1)
            usage = RequestUsage(input_tokens=1000, cache_read_tokens=200, output_tokens=300)
        else:
            body = _valid_episode(1)
            usage = RequestUsage(input_tokens=2000, cache_read_tokens=500, output_tokens=600)
        return ModelResponse(parts=[TextPart(json.dumps(body, ensure_ascii=False))], usage=usage)

    usage = RunUsage()
    settings = ProjectSettings(
        name="搬进新家",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=15,
    )
    result = await generate_script(
        FunctionModel(respond),
        settings,
        Source.from_text("story", "十一点整隔壁空房准时响起三短一长敲墙声。"),
        usage=usage,
        on_progress=on_progress,
    )
    assert len(result.episodes) == 1
    assert usage.input_tokens == 3000
    assert usage.cache_read_tokens == 700
    assert usage.output_tokens == 900
    assert len(progress_events) >= 3
    assert progress_events[-1][3] == 98


async def test_failed_episode_still_accumulates_consumed_tokens_in_shared_usage():
    """验证零垫资原则：即便第 1 集校验失败抛出异常，已消耗的大纲 + 重试 token 依然保留在 RunUsage 中。"""

    def respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        if "episode" not in data:
            body = _valid_outline(1)
            usage = RequestUsage(input_tokens=800, output_tokens=200)
        else:
            # 故意永远返回极短剧本，触发全部重试并最终抛出 UnexpectedModelBehavior。
            body = _valid_episode(1, short=True)
            usage = RequestUsage(input_tokens=500, output_tokens=100)
        return ModelResponse(parts=[TextPart(json.dumps(body, ensure_ascii=False))], usage=usage)

    usage = RunUsage()
    settings = ProjectSettings(
        name="搬进新家",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=15,
    )
    with pytest.raises(UnexpectedModelBehavior):
        await generate_script(
            FunctionModel(respond),
            settings,
            Source.from_text("story", "短故事测试"),
            usage=usage,
        )

    # 1 次大纲 (800 in, 200 out) + 6 次分集尝试 (6 * 500 = 3000 in, 600 out)
    assert usage.input_tokens >= 3800
    assert usage.output_tokens >= 800


async def test_append_assets_and_storyboard_pipeline_works_with_shared_usage():
    def script_respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        if "nextEpisodeNumber" in data:
            body = {
                "plan": {
                    "number": 2,
                    "title": "纸条背后",
                    "summary": "林晚拆开纸条。",
                    "hook": "门缝纸条写着别回头。",
                    "suspense": "字迹像她自己。",
                    "ending": "走廊灯全灭。",
                    "characterIds": ["C01"],
                    "sceneIds": ["S01"],
                    "propIds": ["P01"],
                },
                "newCharacters": [],
                "newScenes": [],
                "newProps": [],
                "continuityUpdate": "林晚拿到纸条。",
            }
        elif "episode" in data:
            body = _valid_episode(int(data["episode"]["number"]))
        else:
            body = _valid_outline(1)
        return ModelResponse(
            parts=[TextPart(json.dumps(body, ensure_ascii=False))],
            usage=RequestUsage(input_tokens=400, output_tokens=150),
        )

    usage = RunUsage()
    settings = ProjectSettings(
        name="搬进新家",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=15,
    )
    script = await generate_script(
        FunctionModel(script_respond),
        settings,
        Source.from_text("story", "敲墙声故事"),
        usage=usage,
    )
    appended = await append_episode(FunctionModel(script_respond), script, usage=usage)
    assert len(appended.episodes) == 2

    def asset_respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        kind = data["kind"]
        designs = []
        for entry in data["assets"]:
            if kind == "scene":
                p = "现代写实，无人空景，旧卧室"
            elif kind == "prop":
                p = "现代写实，纯白背景，无手，手持级尺度，木质晾衣杆"
            else:
                p = "二十六岁女性，黑发，家居服"
            designs.append(
                {
                    "id": entry["id"],
                    "description": f"{entry['id']} 描述",
                    "prompt": p,
                    "voice": "二十六岁女性；清冷女中音；语速稳；普通话" if kind == "character" else "",
                }
            )
        return ModelResponse(
            parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))],
            usage=RequestUsage(input_tokens=300, output_tokens=120),
        )

    existing_c01 = Asset(
        id="C01",
        kind="character",
        name="林晚（定妆）",
        description="保留描述",
        prompt="保留提示词",
        episodeNumbers=[1],
        voice="保留音色",
    )
    assets = await analyze_assets(
        FunctionModel(asset_respond),
        appended,
        existing=[existing_c01],
        usage=usage,
    )
    assert next(a for a in assets.assets if a.id == "C01").prompt == "保留提示词"
    assert next(a for a in assets.assets if a.id == "C01").episodeNumbers == [1, 2]

    def sb_respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        segs = []
        for seg in data["segments"]:
            segs.append(
                {
                    "id": seg["id"],
                    "references": [seg["sceneId"], "C01"],
                    "blocking": "女性站在床边偏左，面向墙壁。",
                    "soundscape": "深夜老楼微弱回声",
                    "music": "低频悬疑铺底",
                    "cuts": [
                        {
                            "index": cut["index"],
                            "shotSize": "中景",
                            "camera": "固定镜头",
                            "lens": "35mm",
                            "cameraPosition": "平视",
                            "composition": "三分法",
                            "shot": "年轻女性紧握木杆贴近老旧白墙细听动静。",
                            "eyeline": "看向右侧墙面",
                            "focus": "对焦女性侧脸",
                            "stability": "稳定",
                            "framePrompt": "电影写实中景，昏暗卧室，年轻女性侧身贴墙细听。",
                        }
                        for cut in seg["cuts"]
                    ],
                }
            )
        return ModelResponse(
            parts=[TextPart(json.dumps({"segments": segs}, ensure_ascii=False))],
            usage=RequestUsage(input_tokens=500, output_tokens=200),
        )

    board = await storyboard(
        FunctionModel(sb_respond),
        appended,
        assets,
        only_episode=1,
        usage=usage,
    )
    assert len(board.episodes) == 1
    assert len(board.episodes[0].clips) > 0
    assert usage.input_tokens > 1500


async def test_analyze_assets_auto_variants_and_storyboard_variant_binding():
    settings = ProjectSettings(
        name="雨夜调查",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=15,
    )

    def script_respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        body = _valid_episode(int(data["episode"]["number"])) if "episode" in data else _valid_outline(1)
        return ModelResponse(parts=[TextPart(json.dumps(body, ensure_ascii=False))])

    script = await generate_script(
        FunctionModel(script_respond),
        settings,
        Source.from_text("story", "雨夜变装测试"),
    )

    def asset_respond_with_variants(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        kind = data["kind"]
        designs = []
        for entry in data["assets"]:
            if kind == "character":
                designs.append(
                    {
                        "id": entry["id"],
                        "description": "白天默认造型",
                        "prompt": "二十六岁女性，黑发低马尾，浅蓝色家居服，电影写实",
                        "voice": "二十六岁女性；清冷女中音；语速稳；普通话",
                        "variants": [
                            {
                                "label": "便装雨衣",
                                "description": "深夜外出调查穿黑色风衣",
                                "prompt": "黑色长款防水风衣，湿发微乱，电影写实",
                                "episodes": [1],
                            },
                            {
                                "label": "战损",
                                "description": "肩头微破带尘土",
                                "prompt": "深灰夹克肩部微破，脸颊带轻微尘土，电影写实",
                                "episodes": [1],
                            },
                        ],
                    }
                )
            elif kind == "scene":
                designs.append(
                    {
                        "id": entry["id"],
                        "description": "旧卧室白天",
                        "prompt": "现代写实，无人空景，旧卧室白天自然光",
                        "voice": "",
                        "variants": [
                            {
                                "label": "深夜停电",
                                "description": "深夜无灯光，月光斜照",
                                "prompt": "现代写实，无人空景，深夜停电卧室，冷蓝月光斜照地面",
                                "episodes": [1],
                            }
                        ],
                    }
                )
            else:
                designs.append(
                    {
                        "id": entry["id"],
                        "description": "木质晾衣杆",
                        "prompt": "现代写实，纯白背景，无手，手持级尺度，旧木质晾衣杆",
                        "voice": "",
                        "variants": [],
                    }
                )
        return ModelResponse(parts=[TextPart(json.dumps({"assets": designs}, ensure_ascii=False))])

    assets = await analyze_assets(FunctionModel(asset_respond_with_variants), script)
    by_id = {a.id: a for a in assets.assets}
    assert "C01_v1" in by_id and by_id["C01_v1"].parentId == "C01"
    assert by_id["C01_v1"].variantLabel == "便装雨衣"
    assert "严格参考参考图1" in by_id["C01_v1"].prompt
    assert "C01_v2" in by_id and by_id["C01_v2"].variantLabel == "战损"
    assert "S01_v1" in by_id and by_id["S01_v1"].parentId == "S01"
    assert "严格参考参考图1" in by_id["S01_v1"].prompt

    # 1b: Storyboard receives variant options, rejects root+variant conflict on 1st attempt,
    # then binds C01_v1 + S01_v1 cleanly and inherits parent C01's voice.
    batch1_calls = 0

    def sb_respond_variants(messages, _info):
        nonlocal batch1_calls
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        is_first_batch = data["segments"][0]["id"] == 1
        if is_first_batch:
            batch1_calls += 1
        # Verify variant options were passed to the storyboard LLM
        first_seg_asset_ids = {item["id"] for item in data["segments"][0]["assets"]}
        assert "C01_v1" in first_seg_asset_ids
        assert "S01_v1" in first_seg_asset_ids

        segs = []
        for seg in data["segments"]:
            refs = (
                ["S01_v1", "C01", "C01_v1"]
                if is_first_batch and batch1_calls == 1
                else ["S01_v1", "C01_v1"]
            )
            segs.append(
                {
                    "id": seg["id"],
                    "references": refs,
                    "blocking": "女性站在床边偏左，面向墙壁。",
                    "soundscape": "雨夜风声",
                    "music": "",
                    "cuts": [
                        {
                            "index": cut["index"],
                            "shotSize": "中景",
                            "camera": "固定镜头",
                            "lens": "35mm",
                            "cameraPosition": "平视",
                            "composition": "三分法",
                            "shot": "穿黑色风衣的年轻女性侧耳贴近昏暗墙面。",
                            "eyeline": "右侧墙面",
                            "focus": "女性侧脸",
                            "stability": "稳定",
                            "framePrompt": "电影写实中景，深夜卧室，穿黑风衣女性贴墙倾听。",
                        }
                        for cut in seg["cuts"]
                    ],
                }
            )
        return ModelResponse(parts=[TextPart(json.dumps({"segments": segs}, ensure_ascii=False))])

    board = await storyboard(FunctionModel(sb_respond_variants), script, assets, only_episode=1)
    assert batch1_calls == 2  # 1st attempt rejected for root+variant conflict, 2nd succeeded
    clip0 = board.episodes[0].clips[0]
    assert clip0.assetIds == ["C01_v1", "S01_v1"]
    assert "@[图片1] = 林晚（便装雨衣）" in clip0.prompt
    assert "@[图片2] = 302室卧室（深夜停电）" in clip0.prompt
    assert "@[图片1] 林晚：二十六岁女性；清冷女中音；语速稳；普通话" in clip0.prompt
