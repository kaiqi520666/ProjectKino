import argparse
import asyncio
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model

from .deepseek import MODEL_SETTINGS, model_from_env
from .gates import log_progress, record_gate
from .generate import prompt, skill_instructions
from .schema import (
    AssetResult, Beat, Episode, EpisodeStoryboard, Record, Scene, ScriptResult, ShotSize,
    StoryboardAssetRef, StoryboardClip, StoryboardCut, StoryboardReference, StoryboardResult, Text,
)
from .timing import beat_seconds

MIN_CUT_SECONDS = 2.0
MAX_CUT_SECONDS = 5.0
# 并入不足 2 秒的尾差时允许略微超出上限；质量门按这个上限检查。
CUT_LENGTH_LIMIT = MAX_CUT_SECONDS + 1.0
# 一段设计包含镜头字段，整集一次请求会撞输出上限；按段分批。
DESIGN_BATCH_SEGMENTS = 4

CameraMove = Literal[
    "固定镜头", "缓慢推镜", "快速推镜", "缓慢拉镜", "平稳横移", "跟拍", "摇镜", "手持跟随",
]
Stability = Literal["稳定", "微晃", "晃动"]


@dataclass(frozen=True)
class Cut:
    index: int
    beats: tuple[Beat, ...]
    seconds: float
    beat_range: tuple[int, int]


@dataclass(frozen=True)
class Segment:
    index: int
    scene: Scene
    cuts: tuple[Cut, ...]
    seconds: float
    beat_range: tuple[int, int]


@dataclass(frozen=True)
class DesignContext:
    expected: dict[int, tuple[int, ...]]
    available: dict[int, frozenset[str]]
    forbidden_names: tuple[str, ...]
    episode: int = 0


class CutDesign(Record):
    index: int
    shotSize: ShotSize
    camera: CameraMove
    lens: Text
    cameraPosition: Text
    composition: Text
    shot: Text
    eyeline: Text
    focus: Text
    stability: Stability
    framePrompt: Text
    sfx: str = ""
    lighting: str = ""


class SegmentDesign(Record):
    id: int
    references: Annotated[list[str], Field(min_length=1, max_length=6)]
    blocking: Text
    soundscape: str = ""
    music: str = ""
    cuts: list[CutDesign]


class StoryboardDesign(Record):
    segments: list[SegmentDesign]


CONSTRAINTS = (
    "保持无字幕，避免生成任何文字或字幕",
    "视频全程禁止出现外形、着装、配饰完全一致的人物",
)
_CLAUSE = re.compile(r"[；;。]")
_NEGATION = re.compile(r"(无|没有|禁)")
_MODERN_STYLE = re.compile(r"古装|古风|唐|宋|元|明|清|民国")
_SCIFI_STYLE = re.compile(r"赛博|cyberpunk|未来|科幻")


def _world_line(world) -> str:
    """世界基准压缩成一行：时代 + 少量正向材质，排除项另行放进约束。"""
    positive: list[str] = []
    total = 0
    for clause in _CLAUSE.split(world.baseline):
        clause = clause.strip()
        if not clause or _NEGATION.search(clause):
            continue
        if total + len(clause) > 60:
            if not positive:
                positive.append(clause[:60])
            break
        positive.append(clause)
        total += len(clause)
    detail = "；".join(positive) or world.baseline.strip()[:60]
    return f"世界观：{world.era}；{detail}"


def _world_exclusions(world) -> list[str]:
    return [
        clause.strip().rstrip("。；;")
        for clause in _CLAUSE.split(world.baseline)
        if clause.strip() and _NEGATION.search(clause)
    ]


def world_style_warnings(script: ScriptResult) -> list[str]:
    world = script.outline.world
    if world is None:
        return []
    label = script.settings.visualStyleLabel or script.settings.visualStyle
    style = f"{label} {script.settings.visualStyle}".lower()
    if world.kind in ("modern", "scifi") and _MODERN_STYLE.search(style):
        return [f"画风「{label}」看起来是古装向，与世界观「{world.era}」不一致，请确认哪一层优先。"]
    if world.kind == "historical" and _SCIFI_STYLE.search(style):
        return [f"画风「{label}」看起来是科幻向，与世界观「{world.era}」不一致，请确认哪一层优先。"]
    return []


def _first_clause(text: str) -> str:
    return text.split("，")[0].split("。")[0].strip()


def _dialogue(cut: Cut, names: dict[str, str]) -> str:
    parts: list[str] = []
    for beat in cut.beats:
        if beat.line is None:
            continue
        emotion = _first_clause(beat.delivery or "")
        if beat.speaker == "VO":
            tag = f"画外音，{emotion}" if emotion else "画外音"
        else:
            name = names.get(beat.speaker or "", beat.speaker or "")
            tag = f"{name}，{emotion}" if emotion else name
        parts.append(f"台词（{tag}）：{{{beat.line}}}")
    return "；".join(parts) if parts else "台词：{}"


def _asset_kind(asset_id: str) -> str:
    return {"C": "character", "S": "scene", "P": "prop"}.get(asset_id[:1], "prop")


def _reference_order(ids: list[str]) -> list[str]:
    # 与前端分镜页的资产分组顺序一致：角色 → 场景 → 道具。
    # @[图片N] 按这个顺序编号，附件也必须按同样顺序上传。
    order = {"C": 0, "S": 1, "P": 2}
    return sorted(ids, key=lambda asset_id: (order.get(asset_id[:1], 3), ids.index(asset_id)))


def compose_seedance(
    segment: Segment, design: SegmentDesign, script: ScriptResult, assets: AssetResult,
) -> str:
    """按 Seedance 规范把镜头设计拼成一段可直接下给视频模型的提示词。"""
    scene_names = {card.id: card.name for card in script.outline.scenes}
    character_names = {card.id: card.name for card in script.outline.characters}
    prop_names = {prop.id: prop.name for prop in script.outline.props}
    names = {**scene_names, **character_names, **prop_names}

    ordered = _reference_order(design.references)
    blocks: list[str] = []
    for number, asset_id in enumerate(ordered, 1):
        blocks.append(f"@[图片{number}] = {names.get(asset_id, asset_id)}")

    voices = {asset.id: asset.voice for asset in assets.assets if asset.voice}
    speaker_ids: list[str] = []
    for cut in segment.cuts:
        for beat in cut.beats:
            if beat.line is not None and beat.speaker and beat.speaker != "VO" and beat.speaker not in speaker_ids:
                speaker_ids.append(beat.speaker)
    voiced: list[str] = []
    for asset_id in speaker_ids:
        if asset_id not in voices:
            continue
        name = names.get(asset_id, asset_id)
        prefix = f"@[图片{ordered.index(asset_id) + 1}] " if asset_id in ordered else ""
        voiced.append(f"{prefix}{name}：{voices[asset_id]}")
    if voiced:
        blocks.append("")
        blocks.append("【角色音色】")
        blocks.extend(voiced)

    blocks.append("")
    blocks.append("【人物关系与构图逻辑】")
    blocks.append(design.blocking)

    for cut, shot in zip(segment.cuts, sorted(design.cuts, key=lambda item: item.index)):
        blocks.extend([
            "",
            f"【镜头{cut.index}】",
            f"焦距：{shot.lens}",
            f"机位：{shot.cameraPosition}",
            f"构图：{shot.composition}",
            f"运镜：{shot.camera}",
            f"景别：{shot.shotSize}",
            f"画面：{shot.shot}",
            _dialogue(cut, character_names),
            f"视线落点：{shot.eyeline}",
            f"焦点：{shot.focus}",
            f"稳定性：{shot.stability}",
        ])
        if shot.sfx:
            blocks.append(f"音效：{shot.sfx}")
        if shot.lighting:
            blocks.append(f"光影：{shot.lighting}")

    if design.soundscape:
        blocks.extend(["", f"<{design.soundscape}>"])
    if design.music and script.settings.backgroundMusic:
        blocks.extend(["", f"（{design.music}）"])
    world = script.outline.world
    constraints = list(CONSTRAINTS)
    if not script.settings.backgroundMusic:
        constraints.append("不生成背景音乐；只保留对白、环境音与动作音效")
    if world:
        blocks.extend(["", _world_line(world)])
        constraints.extend(_world_exclusions(world))
    style = script.settings.visualStyleLabel or script.settings.visualStyle
    blocks.extend(["", f"视觉风格：{style}", "", "【约束】"])
    blocks.extend(f"{number}. {line}" for number, line in enumerate(dict.fromkeys(constraints), 1))
    return "\n".join(blocks)


_SHOT_TIME_POLLUTION = re.compile(
    r"(?:\d+(?:\.\d+)?\s*[—–\-~～]\s*\d+(?:\.\d+)?\s*(?:秒|s\b)|第\s*\d+(?:\.\d+)?\s*秒|\b\d{1,2}:\d{2}(?:\.\d+)?\b)",
    re.IGNORECASE,
)
_SHOT_PROTOCOL_POLLUTION = re.compile(
    r"(?:@\[?图片\d+\]?|<Picture\s*\d+>|【镜头\s*\d*】|\[Shot\s*\d+\])",
    re.IGNORECASE,
)


def _retry(message: str, meta: dict | None = None) -> None:
    record_gate("plan-storyboard", False, [message], meta)
    print(f"[plan-storyboard] 重试原因：{message}", file=sys.stderr)
    raise ModelRetry(message)


def verify_designs(ctx: RunContext[DesignContext], design: StoryboardDesign) -> StoryboardDesign:
    expected = ctx.deps.expected
    meta = {"episode": ctx.deps.episode, "segments": sorted(expected)}
    got_ids = [segment.id for segment in design.segments]
    if sorted(got_ids) != sorted(expected) or len(set(got_ids)) != len(got_ids):
        _retry(f"请为且只为这些段各写一份设计，不多不少：{sorted(expected)}", meta)
    for segment in design.segments:
        got = [cut.index for cut in segment.cuts]
        want = list(expected[segment.id])
        if sorted(got) != sorted(want) or len(set(got)) != len(got):
            _retry(f"第 {segment.id} 段的镜头编号必须与输入一致：{want}", meta)
        available = ctx.deps.available[segment.id]
        unknown = [asset_id for asset_id in segment.references if asset_id not in available]
        if unknown:
            _retry(f"第 {segment.id} 段引用了本段没有的资产：{unknown}，可选：{sorted(available)}", meta)
        if len(set(segment.references)) != len(segment.references):
            _retry(f"第 {segment.id} 段的 references 有重复。", meta)
        if not any(asset_id.startswith("S") for asset_id in segment.references):
            _retry(f"第 {segment.id} 段的 references 必须包含场景。", meta)
        for cut in segment.cuts:
            for name in ctx.deps.forbidden_names:
                if name and name in cut.shot:
                    _retry(f"第 {segment.id} 段镜头 {cut.index} 的「画面」里出现了角色名「{name}」，请改成身份或外观描述。", meta)
            bad_time = _SHOT_TIME_POLLUTION.search(cut.shot)
            if bad_time:
                _retry(f"第 {segment.id} 段镜头 {cut.index} 的「画面」里出现了时间/秒数「{bad_time.group(0)}」，请删掉（时长由程序控制）。", meta)
            bad_proto = _SHOT_PROTOCOL_POLLUTION.search(cut.shot)
            if bad_proto:
                _retry(f"第 {segment.id} 段镜头 {cut.index} 的「画面」里出现了协议/参考图标记「{bad_proto.group(0)}」，请删掉（由程序自动拼装）。", meta)
    record_gate("plan-storyboard", True, meta=meta)
    return design


def split_cuts(numbered: list[tuple[Beat, int]]) -> tuple[Cut, ...]:
    """把一段里的节拍切成 2–5 秒的镜头；结尾不足 2 秒时并回上一镜。"""
    buckets: list[list[tuple[Beat, int]]] = []
    totals: list[float] = []
    for beat, number in numbered:
        seconds = beat_seconds(beat)
        if not buckets or totals[-1] + seconds > MAX_CUT_SECONDS:
            buckets.append([])
            totals.append(0.0)
        buckets[-1].append((beat, number))
        totals[-1] += seconds

    if len(buckets) > 1 and totals[-1] < MIN_CUT_SECONDS and totals[-2] + totals[-1] <= CUT_LENGTH_LIMIT:
        buckets[-2].extend(buckets[-1])
        totals[-2] += totals[-1]
        buckets.pop()
        totals.pop()

    return tuple(
        Cut(
            index=offset + 1,
            beats=tuple(beat for beat, _ in bucket),
            seconds=round(total, 1),
            beat_range=(bucket[0][1], bucket[-1][1]),
        )
        for offset, (bucket, total) in enumerate(zip(buckets, totals))
    )


def _segment(scene: Scene, numbered: list[tuple[Beat, int]], index: int, cap: int) -> Segment:
    cuts = split_cuts(numbered)
    precise = sum(cut.seconds for cut in cuts)
    # 对外用整数秒；四舍五入后不得超过单段上限。
    seconds = min(cap, max(1, round(precise)))
    return Segment(
        index=index,
        scene=scene,
        cuts=cuts,
        seconds=seconds,
        beat_range=(numbered[0][1], numbered[-1][1]),
    )


def split_episode(episode: Episode, cap: int) -> list[Segment]:
    """按单段生成上限切段，段内再切 2–5 秒的镜头；段不跨场。"""
    segments: list[Segment] = []
    number = 0
    for scene in episode.scenes:
        current: list[tuple[Beat, int]] = []
        total = 0.0
        for beat in scene.flow:
            number += 1
            seconds = beat_seconds(beat)
            if current and total + seconds > cap:
                segments.append(_segment(scene, current, len(segments) + 1, cap))
                current, total = [], 0.0
            current.append((beat, number))
            total += seconds
        if current:
            segments.append(_segment(scene, current, len(segments) + 1, cap))
    return segments


def segment_asset_ids(segment: Segment) -> list[str]:
    return list(dict.fromkeys([segment.scene.sceneId, *segment.scene.characters, *segment.scene.props]))


def episode_asset_ids(episode: Episode) -> list[str]:
    ids: list[str] = []
    for scene in episode.scenes:
        ids.extend([scene.sceneId, *scene.characters, *scene.props])
    return list(dict.fromkeys(ids))


def _beat_payload(beat: Beat, names: dict[str, str]) -> dict:
    if beat.action is not None:
        return {"action": beat.action}
    return {
        "speaker": "画外音" if beat.speaker == "VO" else names.get(beat.speaker or "", beat.speaker),
        "line": beat.line,
        **({"delivery": beat.delivery} if beat.delivery else {}),
    }


async def write_designs(
    model: Model, episode: Episode, segments: list[Segment], script: ScriptResult,
) -> dict[int, SegmentDesign]:
    names = {card.id: card.name for card in script.outline.characters}
    scene_names = {card.id: card.name for card in script.outline.scenes}
    prop_names = {prop.id: prop.name for prop in script.outline.props}
    agent = Agent(
        model, deps_type=DesignContext, output_type=PromptedOutput(StoryboardDesign),
        instructions=skill_instructions("plan-storyboard"), model_settings=MODEL_SETTINGS, retries=5,
    )
    agent.output_validator(verify_designs)

    designs: dict[int, SegmentDesign] = {}
    previous_blocking: dict | None = None
    total_batches = (len(segments) + DESIGN_BATCH_SEGMENTS - 1) // DESIGN_BATCH_SEGMENTS
    for batch_idx, start in enumerate(range(0, len(segments), DESIGN_BATCH_SEGMENTS), 1):
        batch = segments[start:start + DESIGN_BATCH_SEGMENTS]
        t_batch = time.perf_counter()
        span = f"{batch[0].index}" if len(batch) == 1 else f"{batch[0].index}–{batch[-1].index}"
        log_progress("storyboard", f"第 {episode.number} 集 第 {batch_idx}/{total_batches} 批（第 {span} 段）开始生成...")
        payload: dict = {
            "episode": episode.number,
            "settings": {
                **script.settings.model_dump(),
                "world": script.outline.world.model_dump() if script.outline.world else None,
            },
            "maxSegmentDuration": script.settings.maxSegmentDuration,
            "cutSeconds": {"min": MIN_CUT_SECONDS, "max": MAX_CUT_SECONDS},
            "segments": [
                {
                    "id": segment.index,
                    "sceneId": segment.scene.sceneId,
                    "durationSeconds": segment.seconds,
                    "scene": scene_names.get(segment.scene.sceneId, segment.scene.sceneId),
                    "characters": [names.get(character, character) for character in segment.scene.characters],
                    "props": [prop_names.get(prop, prop) for prop in segment.scene.props],
                    "assets": [
                        {"id": asset_id, "name": names.get(asset_id, asset_id), "kind": _asset_kind(asset_id)}
                        for asset_id in segment_asset_ids(segment)
                    ],
                    "cuts": [
                        {
                            "index": cut.index,
                            "seconds": cut.seconds,
                            "beats": [_beat_payload(beat, names) for beat in cut.beats],
                        }
                        for cut in segment.cuts
                    ],
                }
                for segment in batch
            ],
        }
        if previous_blocking is not None:
            payload["previousBlocking"] = previous_blocking
        result = await agent.run(prompt(payload), deps=DesignContext(
            {segment.index: tuple(cut.index for cut in segment.cuts) for segment in batch},
            {segment.index: frozenset(segment_asset_ids(segment)) for segment in batch},
            tuple(character.name for character in script.outline.characters),
            episode=episode.number,
        ))
        designs.update({segment.id: segment for segment in result.output.segments})
        log_progress(
            "storyboard",
            f"第 {episode.number} 集 第 {batch_idx}/{total_batches} 批（第 {span} 段）完成（{time.perf_counter() - t_batch:.1f}s）",
        )
        last_segment = batch[-1]
        previous_blocking = {
            "segmentId": last_segment.index,
            "sceneId": last_segment.scene.sceneId,
            "scene": scene_names.get(last_segment.scene.sceneId, last_segment.scene.sceneId),
            "blocking": designs[last_segment.index].blocking,
        }
    return designs


async def storyboard_episode(
    model: Model, episode: Episode, script: ScriptResult, assets: AssetResult,
) -> EpisodeStoryboard:
    started = time.perf_counter()
    cap = script.settings.maxSegmentDuration
    segments = split_episode(episode, cap)
    log_progress("storyboard", f"第 {episode.number} 集《{episode.title}》切分完成：共 {len(segments)} 段（上限 {cap}s/段）")
    designs = await write_designs(model, episode, segments, script)

    catalog = {asset.id: asset for asset in assets.assets}
    used = episode_asset_ids(episode)
    missing = [asset_id for asset_id in used if asset_id not in catalog]
    if missing:
        raise ValueError(f"第 {episode.number} 集引用了资产表里没有的编号：{missing}")

    clips: list[StoryboardClip] = []
    names = {
        **{card.id: card.name for card in script.outline.characters},
        **{card.id: card.name for card in script.outline.scenes},
        **{prop.id: prop.name for prop in script.outline.props},
    }
    for segment in segments:
        design = designs[segment.index]
        by_index = {cut.index: cut for cut in design.cuts}
        ordered = _reference_order(design.references)
        clips.append(StoryboardClip(
            id=segment.index,
            durationSeconds=segment.seconds,
            prompt=compose_seedance(segment, design, script, assets),
            assetIds=ordered,
            references=[
                StoryboardReference(index=position + 1, assetId=asset_id,
                                    name=names.get(asset_id, asset_id), kind=_asset_kind(asset_id))
                for position, asset_id in enumerate(ordered)
            ],
            beats=segment.beat_range,
            blocking=design.blocking,
            cuts=[
                StoryboardCut(
                    index=cut.index,
                    seconds=cut.seconds,
                    shotSize=by_index[cut.index].shotSize,
                    camera=by_index[cut.index].camera,
                    framePrompt=by_index[cut.index].framePrompt,
                    beats=cut.beat_range,
                )
                for cut in segment.cuts
            ],
        ))

    board = EpisodeStoryboard(
        number=episode.number,
        assets=[
            StoryboardAssetRef(id=asset_id, kind=catalog[asset_id].kind, name=catalog[asset_id].name)
            for asset_id in used
        ],
        clips=clips,
    )
    log_progress("storyboard", f"第 {episode.number} 集分镜完成：共 {len(clips)} 段（{time.perf_counter() - started:.1f}s）")
    return board


async def storyboard(
    model: Model, script: ScriptResult, assets: AssetResult, only_episode: int | None = None,
) -> StoryboardResult:
    for warning in world_style_warnings(script):
        print(f"[storyboard] 注意：{warning}", file=sys.stderr)
    episodes = [
        await storyboard_episode(model, episode, script, assets)
        for episode in script.episodes
        if only_episode is None or episode.number == only_episode
    ]
    if not episodes:
        raise ValueError(f"剧本里没有第 {only_episode} 集。")
    return StoryboardResult(settings=script.settings, episodes=episodes)


def storyboard_problems(result: StoryboardResult, script: ScriptResult) -> list[str]:
    """段/切/节拍覆盖的确定性检查，给测试和命令行复用。"""
    problems: list[str] = []
    cap = script.settings.maxSegmentDuration
    by_number = {episode.number: episode for episode in script.episodes}
    for board in result.episodes:
        episode = by_number.get(board.number)
        if episode is None:
            problems.append(f"分镜里的第 {board.number} 集不在剧本里。")
            continue
        if not board.clips:
            problems.append(f"第 {board.number} 集没有片段。")
            continue

        total_beats = sum(len(scene.flow) for scene in episode.scenes)
        for clip in board.clips:
            if clip.durationSeconds > cap:
                problems.append(f"第 {board.number} 集片段 {clip.id} 时长 {clip.durationSeconds} 秒，超过上限 {cap} 秒。")
            problems.extend(_cut_problems(board.number, clip))
        total = round(sum(clip.durationSeconds for clip in board.clips), 1)
        if abs(total - episode.seconds) > max(2.0, episode.seconds * 0.05):
            problems.append(f"第 {board.number} 集片段合计 {total} 秒，与剧本预估 {episode.seconds} 秒不一致。")
        problems.extend(_coverage_problems(board.number, board.clips, total_beats))

        known = {asset.id for asset in board.assets}
        for clip in board.clips:
            unknown = [asset_id for asset_id in clip.assetIds if asset_id not in known]
            if unknown:
                problems.append(f"第 {board.number} 集片段 {clip.id} 引用了本集资产表里没有的编号：{unknown}。")
    return problems


def _cut_problems(number: int, clip: StoryboardClip) -> list[str]:
    problems: list[str] = []
    if not clip.cuts:
        return problems
    total = round(sum(cut.seconds for cut in clip.cuts), 1)
    if abs(total - clip.durationSeconds) > 0.6:
        problems.append(f"第 {number} 集片段 {clip.id} 的镜头合计 {total} 秒，与段时长 {clip.durationSeconds} 秒不一致。")
    for cut in clip.cuts:
        single_beat = cut.beats[0] == cut.beats[1]
        if clip.durationSeconds < MIN_CUT_SECONDS or single_beat:
            continue
        if cut.seconds < MIN_CUT_SECONDS or cut.seconds > CUT_LENGTH_LIMIT:
            problems.append(
                f"第 {number} 集片段 {clip.id} 的镜头 {cut.index} 是 {cut.seconds} 秒，"
                f"应落在 {MIN_CUT_SECONDS}–{MAX_CUT_SECONDS} 秒（并入尾差最多到 {CUT_LENGTH_LIMIT} 秒）。"
            )
    return problems


def _coverage_problems(number: int, clips: list[StoryboardClip], total_beats: int) -> list[str]:
    if any(clip.beats is None or not clip.cuts for clip in clips):
        return []
    problems: list[str] = []
    expected = 1
    for clip in clips:
        start, end = clip.beats or (0, 0)
        if start != expected:
            problems.append(f"第 {number} 集片段 {clip.id} 的节拍从 {start} 开始，应为 {expected}。")
        expected = end + 1
        cut_start = start
        for cut in clip.cuts:
            if cut.beats[0] != cut_start:
                problems.append(f"第 {number} 集片段 {clip.id} 镜头 {cut.index} 的节拍不连续。")
            cut_start = cut.beats[1] + 1
        if cut_start != end + 1:
            problems.append(f"第 {number} 集片段 {clip.id} 的镜头没有覆盖到第 {end} 拍。")
    if expected != total_beats + 1:
        problems.append(f"第 {number} 集有 {total_beats} 拍，分镜只覆盖到第 {expected - 1} 拍。")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split a confirmed FrameDrama script into storyboard segments and cuts.")
    parser.add_argument("script", type=Path, help="Confirmed script JSON")
    parser.add_argument("--assets", type=Path, required=True, help="Asset JSON from analyze-assets")
    parser.add_argument("--output", type=Path, required=True, help="Storyboard JSON")
    parser.add_argument("--episode", type=int, help="Only build this episode")
    args = parser.parse_args(argv)

    try:
        if args.output.resolve() in {args.script.resolve(), args.assets.resolve()}:
            parser.exit(2, "输出路径需要与输入文件不同。\n")
        script = ScriptResult.model_validate_json(args.script.read_text(encoding="utf-8-sig"))
        assets = AssetResult.model_validate_json(args.assets.read_text(encoding="utf-8-sig"))
        result = asyncio.run(storyboard(model_from_env(), script, assets, args.episode))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"分镜输入错误。{exc}\n")
    except AgentRunError as exc:
        status = getattr(exc, "status_code", None)
        detail = f"HTTP {status}" if status else type(exc).__name__
        cause = exc.__cause__
        if cause is not None:
            detail += f"：{str(cause)[:1200]}"
        parser.exit(1, f"分镜生成失败（{detail}）。\n")

    problems = storyboard_problems(result, script)
    if problems:
        parser.exit(1, "分镜未通过检查：\n" + "\n".join(f"- {item}" for item in problems) + "\n")

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        parser.exit(1, f"写入分镜结果失败。{exc}\n")

    for board in result.episodes:
        cuts = sum(len(clip.cuts) for clip in board.clips)
        print(f"第 {board.number} 集：{len(board.clips)} 段 / {cuts} 切 · "
              f"合计 {round(sum(clip.durationSeconds for clip in board.clips), 1)} 秒 · "
              f"{len(board.assets)} 项资产")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
