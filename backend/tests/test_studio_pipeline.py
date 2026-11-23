import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai import RunUsage
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from app.modules.llm_engine.asset_gen import (
    ASSET_DESIGN_BATCH_SIZE,
    MAX_CLUES_PER_ASSET,
    InventoryItem,
    analyze_assets,
    design_kind,
    inventory,
)
from app.modules.llm_engine.schema import (
    Asset,
    AssetResult,
    Outline,
    ProjectSettings,
    ScriptResult,
)
from app.modules.llm_engine.schema import Episode as SchemaEpisode
from app.modules.llm_engine.script_gen import (
    CHUNK_CHARS,
    MAX_GROUP_SECONDS,
    MAX_SOURCE_EXCERPT_CHARS_PER_EPISODE,
    MAX_SOURCE_LINE_CHARS,
    SceneBeatPlan,
    Source,
    _bounded_source_excerpts,
    _episode_budget,
    _group_beat_plans,
    _outline_scale_guide,
    append_episode,
    chunk_ranges,
    generate_script,
)
from app.modules.llm_engine.storyboard_gen import (
    generate_new_clip_storyboard,
    regenerate_clip_storyboard,
    storyboard,
)
from app.modules.studio.models import Episode, Project, ProjectAsset, StoryboardClip
from app.modules.studio.schemas import (
    MAX_UPLOAD_TEXT_BYTES,
    GenerateProjectRequest,
    ProjectSettingsIn,
)
from app.modules.studio.service import _insert_clip_at_position, apply_regenerated_clip


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


def _last_user_json(messages) -> dict:
    parts = [p for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
    for part in reversed(parts):
        if isinstance(part.content, str) and part.content.lstrip().startswith("{"):
            return json.loads(part.content)
    return json.loads(parts[-1].content)


def _valid_beat_sheet(number: int = 1, target: int = 120) -> dict:
    per_scene = min(150, max(60, target // max(1, round(target / 150))))
    count = max(1, round(target / per_scene))
    allocated = [target // count] * count
    allocated[-1] += target - sum(allocated)
    return {
        "title": f"三短一长-{number}",
        "summary": "十一点整墙里传来三短一长敲击声。",
        "hook": "十一点整敲墙声响起。",
        "cliff": "门缝滑进一张带血字条。",
        "scenes": [
            {
                "index": idx,
                "sceneId": "S01",
                "lighting": "暖黄台灯微光",
                "characters": ["C01"],
                "props": ["P01"],
                "goal": f"第 {idx} 场：林晚追查墙内敲击声来源并发现异常线索。",
                "targetSeconds": sec,
            }
            for idx, sec in enumerate(allocated, 1)
        ],
    }


def _valid_scene_group(target: int = 120, *, include_hook: bool = True, short: bool = False) -> dict:
    if short:
        flow = [{"action": "林晚猛地睁开眼。"}]
    else:
        # 每对 (action 2.5s + 26字台词 5.8s) ≈ 8.3s
        pairs = max(4, round(target / 8.3))
        flow = []
        for idx in range(pairs):
            flow.append({"action": f"林晚第 {idx + 1} 次靠近墙面仔细听动静，手里紧握木质晾衣杆。"})
            flow.append(
                {
                    "speaker": "C01",
                    "delivery": "低声压抑",
                    "line": "十一点整三短一长，隔壁明明空了半年，到底是谁在敲墙？",
                }
            )
    body: dict = {
        "scenes": [
            {
                "sceneId": "S01",
                "lighting": "暖黄台灯微光",
                "characters": ["C01"],
                "props": ["P01"],
                "flow": flow,
            }
        ]
    }
    if include_hook:
        body["hookBeat"] = [1, 1]
    return body


async def test_generate_script_tracks_usage_and_emits_progress_steps():
    progress_events: list[tuple[int, int, str, int]] = []

    async def on_progress(step_idx: int, step_total: int, label: str, pct: int) -> None:
        progress_events.append((step_idx, step_total, label, pct))

    def respond(messages, _info):
        data = _last_user_json(messages)
        task = data.get("task")
        if task == "plan_episode_beats":
            body = _valid_beat_sheet(int(data["episode"]["number"]), int(data["episodeSeconds"]))
            usage = RequestUsage(input_tokens=500, cache_read_tokens=100, output_tokens=150)
        elif task == "write_scene_group":
            body = _valid_scene_group(
                int(data["groupTargetSeconds"]), include_hook=(data["groupIndex"] == 1)
            )
            usage = RequestUsage(input_tokens=1500, cache_read_tokens=400, output_tokens=450)
        else:
            body = _valid_outline(1)
            usage = RequestUsage(input_tokens=1000, cache_read_tokens=200, output_tokens=300)
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
        data = _last_user_json(messages)
        task = data.get("task")
        if task == "plan_episode_beats":
            body = _valid_beat_sheet(1, 120)
            usage = RequestUsage(input_tokens=400, output_tokens=100)
        elif task == "write_scene_group":
            # 故意永远返回极短剧本，触发全部重试并最终抛出 UnexpectedModelBehavior。
            body = _valid_scene_group(120, include_hook=True, short=True)
            usage = RequestUsage(input_tokens=500, output_tokens=100)
        else:
            body = _valid_outline(1)
            usage = RequestUsage(input_tokens=800, output_tokens=200)
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

    # 1 次大纲 (800) + 1 次节拍表 (400) + 4 次组尝试 (4 * 500 = 2000)
    assert usage.input_tokens >= 3200
    assert usage.output_tokens >= 700


async def test_append_assets_and_storyboard_pipeline_works_with_shared_usage():
    def script_respond(messages, _info):
        data = _last_user_json(messages)
        task = data.get("task")
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
        elif task == "plan_episode_beats":
            body = _valid_beat_sheet(int(data["episode"]["number"]), int(data["episodeSeconds"]))
        elif task == "write_scene_group":
            body = _valid_scene_group(
                int(data["groupTargetSeconds"]), include_hook=(data["groupIndex"] == 1)
            )
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
        data = _last_user_json(messages)
        task = data.get("task")
        if task == "plan_episode_beats":
            body = _valid_beat_sheet(int(data["episode"]["number"]), int(data["episodeSeconds"]))
        elif task == "write_scene_group":
            body = _valid_scene_group(
                int(data["groupTargetSeconds"]), include_hook=(data["groupIndex"] == 1)
            )
        else:
            body = _valid_outline(1)
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


def _script_responder(*, count: int = 1):
    def respond(messages, _info):
        data = _last_user_json(messages)
        task = data.get("task")
        if task == "plan_episode_beats":
            body = _valid_beat_sheet(int(data["episode"]["number"]), int(data["episodeSeconds"]))
        elif task == "write_scene_group":
            body = _valid_scene_group(
                int(data["groupTargetSeconds"]), include_hook=(data["groupIndex"] == 1)
            )
        else:
            body = _valid_outline(count)
        return ModelResponse(parts=[TextPart(json.dumps(body, ensure_ascii=False))])

    return respond


def _make_sample_assets(settings: ProjectSettings) -> AssetResult:
    return AssetResult(
        settings=settings,
        assets=[
            Asset(
                id="C01",
                kind="character",
                name="林晚",
                description="二十六岁女性",
                prompt="纯白背景角色设定图",
                voice="二十六岁女性；清冷女中音；语速稳；普通话",
                episodeNumbers=[1],
            ),
            Asset(
                id="C01_v1",
                kind="character",
                name="林晚",
                description="黑色雨衣造型",
                prompt="严格参考参考图1，保持面部与体型一致，换穿黑色长款雨衣",
                voice="",
                episodeNumbers=[1],
                parentId="C01",
                variantLabel="便装雨衣",
            ),
            Asset(
                id="S01",
                kind="scene",
                name="302室卧室",
                description="旧卧室白天",
                prompt="无人空景，旧卧室白天自然光",
                voice="",
                episodeNumbers=[1],
            ),
            Asset(
                id="S01_v1",
                kind="scene",
                name="302室卧室",
                description="深夜停电卧室",
                prompt="严格参考参考图1，切换为深夜停电冷蓝月光",
                voice="",
                episodeNumbers=[1],
                parentId="S01",
                variantLabel="深夜停电",
            ),
            Asset(
                id="P01",
                kind="prop",
                name="木质晾衣杆",
                description="旧木质晾衣杆",
                prompt="纯白背景，无手，旧木质晾衣杆",
                voice="",
                episodeNumbers=[1],
            ),
        ]
    )


@pytest.mark.asyncio
async def test_storyboard_passes_director_feedback():
    settings = ProjectSettings(
        name="搬进新家",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=15,
    )
    script = await generate_script(
        FunctionModel(_script_responder(count=1)),
        settings,
        Source.from_text("story", "半夜墙体传出诡异敲击声。"),
    )
    assets = _make_sample_assets(settings)
    captured_feedback: list[str] = []

    def sb_respond(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        captured_feedback.append(data.get("directorFeedback", ""))
        segs = [
            {
                "id": seg["id"],
                "references": ["S01", "C01"],
                "blocking": "女性面向右侧墙面站立。",
                "soundscape": "深夜钟表滴答声",
                "music": "",
                "cuts": [
                    {
                        "index": cut["index"],
                        "shotSize": "特写",
                        "camera": "缓慢推镜",
                        "lens": "85mm",
                        "cameraPosition": "平视",
                        "composition": "中心构图",
                        "shot": "穿深色家居服的年轻女性微皱眉头贴近斑驳墙面。",
                        "eyeline": "右侧墙面",
                        "focus": "女性眼神",
                        "stability": "稳定",
                        "framePrompt": "电影写实特写，深夜卧室，年轻女性侧耳听墙。",
                    }
                    for cut in seg["cuts"]
                ],
            }
            for seg in data["segments"]
        ]
        return ModelResponse(parts=[TextPart(json.dumps({"segments": segs}, ensure_ascii=False))])

    await storyboard(
        FunctionModel(sb_respond),
        script,
        assets,
        only_episode=1,
        feedback="加强悬疑压迫感，多用特写镜头",
    )
    assert captured_feedback and all(fb == "加强悬疑压迫感，多用特写镜头" for fb in captured_feedback)


@pytest.mark.asyncio
async def test_regenerate_clip_locked_refs_and_refreshed_refs():
    settings = ProjectSettings(
        name="搬进新家",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=15,
    )
    script = await generate_script(
        FunctionModel(_script_responder(count=1)),
        settings,
        Source.from_text("story", "半夜墙体传出诡异敲击声。"),
    )
    assets = _make_sample_assets(settings)
    episode = script.episodes[0]

    # 1) refresh_references=False: locks existing image + custom video slots, rewrites prompt only
    locked_payloads: list[dict] = []

    def locked_responder(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        locked_payloads.append(data)
        return ModelResponse(
            parts=[
                TextPart(
                    json.dumps(
                        {
                            "references": [],
                            "blocking": "女性立于床尾左侧，右手扶墙。",
                            "soundscape": "雨点拍打玻璃与低沉敲墙声",
                            "music": "",
                            "cuts": [
                                {
                                    "index": 1,
                                    "seconds": 4.0,
                                    "shotSize": "近景",
                                    "camera": "缓慢推镜",
                                    "lens": "50mm",
                                    "cameraPosition": "平视",
                                    "composition": "三分法",
                                    "shot": "穿深色家居服的年轻女性缓慢靠近昏暗墙面侧耳倾听。",
                                    "dialogue": "台词：{}",
                                    "eyeline": "右侧墙面",
                                    "focus": "女性侧脸",
                                    "stability": "稳定",
                                    "framePrompt": "电影写实中近景，年轻女性贴近墙面。",
                                },
                                {
                                    "index": 2,
                                    "seconds": 4.0,
                                    "shotSize": "特写",
                                    "camera": "固定镜头",
                                    "lens": "85mm",
                                    "cameraPosition": "平视",
                                    "composition": "中心构图",
                                    "shot": "斑驳墙皮微微震动，灰尘飘落。",
                                    "dialogue": "台词：{}",
                                    "eyeline": "画右",
                                    "focus": "墙面裂缝",
                                    "stability": "稳定",
                                    "framePrompt": "电影写实特写，老旧墙面裂缝微震。",
                                },
                            ],
                        },
                        ensure_ascii=False,
                    )
                )
            ]
        )

    locked_spec = await regenerate_clip_storyboard(
        FunctionModel(locked_responder),
        script=script,
        episode=episode,
        assets=assets,
        clip_index=1,
        clip_beats=(1, 3),
        duration_seconds=8,
        current_prompt="旧提示词",
        current_references=[
            {"index": 1, "assetCode": "C01", "name": "林晚", "kind": "character", "mediaKind": "image"},
            {"index": 2, "assetCode": "custom-v1", "name": "运镜参考", "kind": "video", "mediaKind": "video"},
        ],
        refresh_references=False,
        feedback="改为冷峻缓慢节奏",
    )
    assert len(locked_payloads) == 1
    assert "lockedReferenceSlots" in locked_payloads[0]
    assert "availableAssets" not in locked_payloads[0]
    assert locked_payloads[0]["directorFeedback"] == "改为冷峻缓慢节奏"
    assert locked_spec.references == []
    assert "@[图片1] = 林晚" in locked_spec.prompt
    assert "@[视频1] = 运镜参考" in locked_spec.prompt

    # 2) refresh_references=True on script-backed segment: re-binds latest variants and passes feedback
    refreshed_payloads: list[dict] = []

    def refreshed_responder(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        refreshed_payloads.append(data)
        seg = data["segments"][0]
        return ModelResponse(
            parts=[
                TextPart(
                    json.dumps(
                        {
                            "segments": [
                                {
                                    "id": seg["id"],
                                    "references": ["S01_v1", "C01_v1"],
                                    "blocking": "女性立于门侧，面向黑暗卧室。",
                                    "soundscape": "停电后的死寂与窗外风声",
                                    "music": "",
                                    "cuts": [
                                        {
                                            "index": cut["index"],
                                            "shotSize": "中景",
                                            "camera": "固定镜头",
                                            "lens": "35mm",
                                            "cameraPosition": "平视",
                                            "composition": "三分法",
                                            "shot": "穿黑色雨衣的年轻女性停步于深夜停电卧室门口。",
                                            "eyeline": "右侧床铺",
                                            "focus": "女性轮廓",
                                            "stability": "稳定",
                                            "framePrompt": "电影写实中景，深夜停电卧室。",
                                        }
                                        for cut in seg["cuts"]
                                    ],
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                )
            ]
        )

    refreshed_spec = await regenerate_clip_storyboard(
        FunctionModel(refreshed_responder),
        script=script,
        episode=episode,
        assets=assets,
        clip_index=1,
        clip_beats=(1, 1),
        duration_seconds=10,
        current_prompt="旧提示词",
        current_references=[],
        refresh_references=True,
        feedback="改用深夜停电与雨衣变体",
    )
    assert refreshed_payloads[0]["directorFeedback"] == "改用深夜停电与雨衣变体"
    assert [ref.assetId for ref in refreshed_spec.references] == ["C01_v1", "S01_v1"]
    assert "@[图片1] = 林晚（便装雨衣）" in refreshed_spec.prompt


@pytest.mark.asyncio
async def test_generate_new_clip_supports_30s_duration_pacing():
    settings = ProjectSettings(
        name="搬进新家",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=1,
        maxSegmentDuration=30,
    )
    script = await generate_script(
        FunctionModel(_script_responder(count=1)),
        settings,
        Source.from_text("story", "半夜墙体传出诡异敲击声。"),
    )
    assets = _make_sample_assets(settings)
    captured: list[dict] = []

    def new_clip_responder(messages, _info):
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        captured.append(data)
        cuts = [
            {
                "index": idx,
                "seconds": 5.0,
                "shotSize": "中景" if idx % 2 else "特写",
                "camera": "缓慢推镜",
                "lens": "50mm",
                "cameraPosition": "平视",
                "composition": "三分法",
                "shot": f"第 {idx} 镜：穿黑色雨衣的年轻女性在冷蓝月光下检查墙体裂缝。",
                "dialogue": "台词：{}",
                "eyeline": "右侧墙面",
                "focus": "女性侧脸",
                "stability": "稳定",
                "framePrompt": f"电影写实，深夜停电卧室第 {idx} 镜。",
            }
            for idx in range(1, 7)
        ]
        return ModelResponse(
            parts=[
                TextPart(
                    json.dumps(
                        {
                            "references": ["C01_v1", "S01_v1"],
                            "blocking": "女性沿右侧墙面缓慢移动至门框附近。",
                            "soundscape": "窗外细雨与墙内回响",
                            "music": "",
                            "cuts": cuts,
                        },
                        ensure_ascii=False,
                    )
                )
            ]
        )

    spec = await generate_new_clip_storyboard(
        FunctionModel(new_clip_responder),
        script=script,
        episode=script.episodes[0],
        assets=assets,
        duration_seconds=30,
        feedback="插入一段30秒深夜排查空镜与特写连贯推进",
        prev_clip={"clipIndex": 1, "durationSeconds": 15, "blocking": "女性站在床边", "prompt": "前段提示词"},
    )
    assert captured[0]["durationSeconds"] == 30
    assert captured[0]["cutCountRange"] == {"min": 6, "max": 10}
    assert spec.duration_seconds == 30
    assert len(spec.cuts) == 6
    assert [ref.assetId for ref in spec.references] == ["C01_v1", "S01_v1"]
    assert "@[图片1] = 林晚（便装雨衣）" in spec.prompt
    assert "@[图片2] = 302室卧室（深夜停电）" in spec.prompt


@pytest.mark.asyncio
async def test_apply_regenerated_clip_preserves_video_and_insert_at_position_renumbers():
    project_id = uuid4()
    episode_id = uuid4()
    project = Project(id=project_id, user_id=uuid4(), name="测试项目")
    episode = Episode(id=episode_id, project_id=project_id, number=1, title="第1集")

    asset_v1 = ProjectAsset(
        id=uuid4(),
        project_id=project_id,
        asset_code="C01_v1",
        kind="character",
        name="林晚",
        variant_label="便装雨衣",
        description="",
        prompt="",
    )
    existing_history = [
        {
            "id": "h1",
            "url": "https://oss.example.com/v1.mp4",
            "createdAt": "2026-01-01T00:00:00Z",
        }
    ]
    clip1 = StoryboardClip(
        id=uuid4(),
        project_id=project_id,
        episode_id=episode_id,
        clip_index=1,
        duration_seconds=8,
        prompt="原提示词1",
        references=[{"index": 1, "assetId": "old", "assetCode": "C01", "name": "林晚", "kind": "character"}],
        video_url="https://oss.example.com/v1.mp4",
        video_key="videos/v1.mp4",
        video_status="ready",
        video_history=list(existing_history),
    )
    clip2 = StoryboardClip(
        id=uuid4(),
        project_id=project_id,
        episode_id=episode_id,
        clip_index=2,
        duration_seconds=10,
        prompt="原提示词2",
        references=[],
    )
    clip3 = StoryboardClip(
        id=uuid4(),
        project_id=project_id,
        episode_id=episode_id,
        clip_index=3,
        duration_seconds=12,
        prompt="原提示词3",
        references=[],
    )

    class _FakeSession:
        def __init__(self) -> None:
            self.clips = [clip1, clip2, clip3]
            self.assets = [asset_v1]
            self.flush_snapshots: list[list[int]] = []

        async def scalar(self, _stmt):
            return clip1

        async def scalars(self, stmt):
            text_sql = str(stmt)
            if "project_assets" in text_sql:
                return list(self.assets)
            return sorted(self.clips, key=lambda item: item.clip_index)

        def add(self, obj) -> None:
            if isinstance(obj, StoryboardClip):
                if obj.id is None:
                    obj.id = uuid4()
                self.clips.append(obj)

        async def flush(self) -> None:
            indices = [item.clip_index for item in self.clips]
            # 每次 flush 都必须满足 (episode_id, clip_index) 唯一约束与 >= 1 约束
            assert len(indices) == len(set(indices))
            assert all(idx >= 1 for idx in indices)
            self.flush_snapshots.append(indices)

    session = _FakeSession()

    # 1) refresh_references=False 保留原有 references 与视频/历史
    updated_locked = await apply_regenerated_clip(
        session,  # type: ignore[arg-type]
        project=project,
        clip_id=clip1.id,
        prompt_text="新提示词（锁定参考）",
        blocking="新调度",
        cuts=[{"index": 1, "seconds": 8.0}],
        raw_references=[],
        refresh_references=False,
    )
    assert updated_locked.prompt == "新提示词（锁定参考）"
    assert updated_locked.references[0]["assetCode"] == "C01"
    assert updated_locked.video_url == "https://oss.example.com/v1.mp4"
    assert updated_locked.video_key == "videos/v1.mp4"
    assert updated_locked.video_status == "ready"
    assert updated_locked.video_history == existing_history

    # 2) refresh_references=True 更新 references 到新变体，依然保留视频/历史
    updated_refreshed = await apply_regenerated_clip(
        session,  # type: ignore[arg-type]
        project=project,
        clip_id=clip1.id,
        prompt_text="新提示词（刷新参考）",
        blocking="新调度2",
        cuts=[{"index": 1, "seconds": 8.0}],
        raw_references=[{"index": 1, "assetId": "C01_v1", "name": "林晚", "kind": "character"}],
        refresh_references=True,
    )
    assert updated_refreshed.references[0]["assetId"] == str(asset_v1.id)
    assert updated_refreshed.references[0]["name"] == "林晚 · 便装雨衣"
    assert updated_refreshed.video_url == "https://oss.example.com/v1.mp4"
    assert updated_refreshed.video_history == existing_history

    # 3) 在 clip1 后面插队新增片段，验证两阶段无冲突重排为 [clip1=1, new=2, clip2=3, clip3=4]
    inserted = await _insert_clip_at_position(
        session,  # type: ignore[arg-type]
        project=project,
        episode=episode,
        insert_after_clip_id=clip1.id,
        duration_seconds=20,
        prompt="AI 新插入的 20 秒镜头",
        prompt_customized=False,
        references=[],
    )
    ordered = sorted(session.clips, key=lambda item: item.clip_index)
    assert [item.id for item in ordered] == [clip1.id, inserted.id, clip2.id, clip3.id]
    assert [item.clip_index for item in ordered] == [1, 2, 3, 4]
    assert inserted.duration_seconds == 20


def test_project_settings_duration_total_cap_and_upload_limit():
    ok_30 = ProjectSettingsIn(
        name="长剧测试",
        visual_style="live-action",
        episode_count=30,
        seconds_per_episode=120,
    )
    assert ok_30.episode_count == 30

    ok_600 = ProjectSettingsIn(
        name="长单集测试",
        visual_style="live-action",
        episode_count=6,
        seconds_per_episode=600,
    )
    assert ok_600.seconds_per_episode == 600

    with pytest.raises(ValidationError):
        ProjectSettingsIn(name="过短", visual_style="live-action", episode_count=1, seconds_per_episode=119)
    with pytest.raises(ValidationError):
        ProjectSettingsIn(name="过长", visual_style="live-action", episode_count=1, seconds_per_episode=601)
    with pytest.raises(ValidationError):
        ProjectSettingsIn(
            name="超总时长", visual_style="live-action", episode_count=7, seconds_per_episode=600
        )
    with pytest.raises(ValidationError):
        ProjectSettingsIn(
            name="超总时长2", visual_style="live-action", episode_count=31, seconds_per_episode=120
        )

    req_ok = GenerateProjectRequest(settings=ok_600, mode="upload", text="a" * MAX_UPLOAD_TEXT_BYTES)
    assert len(req_ok.text) == MAX_UPLOAD_TEXT_BYTES
    with pytest.raises(ValidationError):
        GenerateProjectRequest(settings=ok_600, mode="upload", text="a" * (MAX_UPLOAD_TEXT_BYTES + 1))


def test_source_soft_wraps_long_lines_chunks_at_20k_and_bounds_excerpts():
    # 单行无换行长文自动软折行，免疫无换行 2MB txt
    one_giant_line = ("林晚推开档案室铁门，冷风顺着走廊灌进来。" * 120)
    src = Source.from_text("upload", one_giant_line)
    assert len(src.lines) > 1
    assert all(len(line) <= MAX_SOURCE_LINE_CHARS for line in src.lines)

    # 60,000 字按 CHUNK_CHARS=20,000 分块，约 3 块
    large_text = "\n".join(f"第{i}段：" + ("故事推进中。" * 16) for i in range(600))
    large_src = Source.from_text("upload", large_text)
    ranges = chunk_ranges(large_src.lines)
    assert CHUNK_CHARS == 20_000
    assert 2 <= len(ranges) <= 4

    # 单集 sourceExcerpts 按 30,000 字上限截断并附带回查提示
    excerpts = _bounded_source_excerpts(large_src, [(1, len(large_src.lines))])
    assert len(excerpts) == 1
    assert len(excerpts[0]) <= MAX_SOURCE_EXCERPT_CHARS_PER_EPISODE + 120
    assert "read_source_excerpt" in excerpts[0]

    # 动态时长配比不再硬编码 120 秒锚点
    budget_600 = _episode_budget(600)
    assert "600 秒" in budget_600["reference"]
    assert "120 秒" not in budget_600["reference"]
    assert budget_600["recommended"]["lineBeats"] > 60


def test_outline_scale_guide_tiers_and_round_robin_asset_clues():
    short_s = ProjectSettings(
        name="紧凑短剧",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=5,
        maxSegmentDuration=15,
        secondsPerEpisode=120,
    )
    mid_s = ProjectSettings(
        name="中等短剧",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=10,
        maxSegmentDuration=15,
        secondsPerEpisode=180,
    )
    long_s = ProjectSettings(
        name="长剧",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=6,
        maxSegmentDuration=30,
        secondsPerEpisode=600,
    )

    g_short = _outline_scale_guide(short_s, "story")
    g_mid = _outline_scale_guide(mid_s, "story")
    g_long = _outline_scale_guide(long_s, "story")
    assert g_short["tier"] == "compact"
    assert g_short["recommendedCounts"] == {"characters": "2–5", "scenes": "3–6", "props": "2–5"}
    assert "scenesPerEpisodeHint" not in g_short
    assert g_mid["tier"] == "medium"
    assert g_long["tier"] == "long"
    assert g_long["recommendedCounts"] == {"characters": "5–12", "scenes": "7–14", "props": "5–12"}
    assert "scenesPerEpisodeHint" in g_long

    # 验证跨集轮询采样：前 2 集各有 12 条线索，但第 5、6 集的关键换装线索依然能入选
    outline = Outline.model_validate(_valid_outline(6))
    episodes = []
    for ep_num in range(1, 7):
        if ep_num <= 2:
            flow = [{"action": f"林晚在第{ep_num}集巡查第{i}处角落。"} for i in range(1, 13)]
        elif ep_num == 5:
            flow = [{"action": "林晚换上沾雨的黑色风衣站在楼道口。"}]
        elif ep_num == 6:
            flow = [{"action": "林晚身穿米色毛衣推开天台铁门。"}]
        else:
            flow = [{"action": f"林晚在第{ep_num}集查看值班表。"}]
        episodes.append(
            SchemaEpisode.model_validate(
                {
                    **_valid_episode(ep_num, short=True),
                    "scenes": [
                        {
                            "sceneId": "S01",
                            "lighting": "深夜微光",
                            "characters": ["C01"],
                            "props": ["P01"],
                            "flow": flow,
                        }
                    ],
                    "targetSeconds": 600,
                    "seconds": 30.0,
                    "script": "正文",
                }
            )
        )
    script = ScriptResult(settings=long_s, outline=outline, episodes=episodes)
    items = {item.id: item for item in inventory(script)}
    c01_clues = items["C01"].clues
    assert len(c01_clues) <= MAX_CLUES_PER_ASSET
    assert any("第5集" in c and "黑色风衣" in c for c in c01_clues)
    assert any("第6集" in c and "米色毛衣" in c for c in c01_clues)


@pytest.mark.asyncio
async def test_unified_600s_multiturn_closed_loop_patch_and_resume():
    # 1. 验证 _group_beat_plans 统一公式：120s -> 1 组，600s -> 4 组
    plans_120 = [
        SceneBeatPlan(index=1, sceneId="S01", goal="开场钩子", targetSeconds=55),
        SceneBeatPlan(index=2, sceneId="S01", goal="反转收尾", targetSeconds=65),
    ]
    assert len(_group_beat_plans(plans_120, MAX_GROUP_SECONDS)) == 1

    plans_600 = [
        SceneBeatPlan(index=i, sceneId="S01", goal=f"第{i}场冲突", targetSeconds=150)
        for i in range(1, 5)
    ]
    assert len(_group_beat_plans(plans_600, MAX_GROUP_SECONDS)) == 4

    # 2. 验证 600s 单集多轮闭环纠偏 + 偏短时触发局部补戏 Patch（插在结尾场之前）
    seen_groups: list[dict] = []
    seen_history_lengths: list[int] = []
    patch_calls = 0

    def long_ep_responder(messages, _info):
        nonlocal patch_calls
        data = _last_user_json(messages)
        task = data.get("task")
        if task == "plan_episode_beats":
            return ModelResponse(
                parts=[TextPart(json.dumps(_valid_beat_sheet(1, 600), ensure_ascii=False))]
            )
        if task == "write_scene_group":
            seen_groups.append(data)
            seen_history_lengths.append(len(messages))
            # 故意每组都写短到 ~105s（4 组总计 ~420s < 448s 硬下界），既验证闭环自动拉高后续组目标，
            # 也验证全集拼装偏短时触发局部补戏 Patch 而非撕卷重来
            body = _valid_scene_group(105, include_hook=(data["groupIndex"] == 1))
            if data["groupIndex"] == data["groupTotal"]:
                body["scenes"][0]["lighting"] = "结尾悬念专属冷光"
            return ModelResponse(parts=[TextPart(json.dumps(body, ensure_ascii=False))])
        if task == "patch_short_episode":
            patch_calls += 1
            body = _valid_scene_group(int(data["gapSeconds"]), include_hook=False)
            body["scenes"][0]["lighting"] = "局部补戏中段灯光"
            return ModelResponse(parts=[TextPart(json.dumps(body, ensure_ascii=False))])
        return ModelResponse(parts=[TextPart(json.dumps(_valid_outline(2), ensure_ascii=False))])

    saved_outlines: list[Outline] = []
    saved_episodes: list[int] = []

    async def on_outline(o: Outline) -> None:
        saved_outlines.append(o)

    async def on_episode_ready(ep: SchemaEpisode) -> None:
        saved_episodes.append(ep.number)

    settings_600 = ProjectSettings(
        name="十钟测试",
        ratio="16:9",
        visualStyle="live-action",
        episodeCount=2,
        maxSegmentDuration=30,
        secondsPerEpisode=600,
    )
    res = await generate_script(
        FunctionModel(long_ep_responder),
        settings_600,
        Source.from_text("story", "600秒多轮闭环与补戏测试"),
        on_outline=on_outline,
        on_episode_ready=on_episode_ready,
    )
    assert len(saved_outlines) == 1
    assert saved_episodes == [1, 2]
    # 第 1 集的后续轮次应携带不断增长的多轮历史、自动调高剩余组目标，且最后触发了局部补戏
    assert len(seen_groups) >= 8  # 2 集 × 4 组
    assert seen_history_lengths[1] > seen_history_lengths[0]
    assert seen_groups[1]["groupTargetSeconds"] > seen_groups[0]["groupTargetSeconds"]
    assert patch_calls >= 1
    # 验证补戏场被插在了结尾悬念场之前，最后一场仍是结尾悬念场
    assert res.episodes[0].scenes[-1].lighting == "结尾悬念专属冷光"
    assert any(s.lighting == "局部补戏中段灯光" for s in res.episodes[0].scenes[:-1])

    # 3. 验证断点续写：传入 existing_outline + 第 1 集，且共享 RunUsage 已有 60 次请求也不触发 50 次上限报错
    resumed_saved: list[int] = []

    async def on_resumed_ep(ep: SchemaEpisode) -> None:
        resumed_saved.append(ep.number)

    high_usage = RunUsage(requests=60)
    resumed = await generate_script(
        FunctionModel(long_ep_responder),
        settings_600,
        Source.from_text("story", "600秒多轮闭环与补戏测试"),
        usage=high_usage,
        existing_outline=res.outline,
        existing_episodes=[res.episodes[0]],
        on_episode_ready=on_resumed_ep,
    )
    assert resumed_saved == [2]
    assert [ep.number for ep in resumed.episodes] == [1, 2]
    assert high_usage.requests > 60


@pytest.mark.asyncio
async def test_design_kind_batches_large_asset_lists():
    total_items = ASSET_DESIGN_BATCH_SIZE + 5
    items = [
        InventoryItem(
            id=f"S{idx:02d}",
            kind="scene",
            name=f"场景{idx}",
            profile="内景 · 夜",
            episodes=(1,),
        )
        for idx in range(1, total_items + 1)
    ]
    batch_sizes: list[int] = []

    def batch_responder(messages, _info):
        data = _last_user_json(messages)
        batch_sizes.append(len(data["assets"]))
        return ModelResponse(
            parts=[
                TextPart(
                    json.dumps(
                        {
                            "assets": [
                                {
                                    "id": entry["id"],
                                    "description": f"{entry['name']} 描述",
                                    "prompt": f"电影写实，无人空景，{entry['name']} 夜晚室内",
                                    "voice": "",
                                    "variants": [],
                                }
                                for entry in data["assets"]
                            ]
                        },
                        ensure_ascii=False,
                    )
                )
            ]
        )

    designs = await design_kind(
        FunctionModel(batch_responder),
        "scene",
        items,
        {"visualStyle": "live-action"},
        [],
    )
    assert sorted(batch_sizes) == [5, ASSET_DESIGN_BATCH_SIZE]
    assert len(designs) == total_items
