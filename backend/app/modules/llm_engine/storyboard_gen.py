import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext, RunUsage
from pydantic_ai.models import Model

from app.modules.llm_engine.gates import record_gate
from app.modules.llm_engine.provider import MODEL_SETTINGS
from app.modules.llm_engine.schema import (
    Asset,
    AssetResult,
    Beat,
    Episode,
    EpisodeStoryboard,
    Record,
    Scene,
    ScriptResult,
    ShotSize,
    StoryboardAssetRef,
    StoryboardClip,
    StoryboardCut,
    StoryboardReference,
    StoryboardResult,
    Text,
)
from app.modules.llm_engine.script_gen import ProgressCallback, _notify, prompt, skill_instructions
from app.modules.llm_engine.timing import beat_seconds

MIN_CUT_SECONDS = 2.0
MAX_CUT_SECONDS = 5.0
CUT_LENGTH_LIMIT = MAX_CUT_SECONDS + 1.0
DESIGN_BATCH_SEGMENTS = 4

CameraMove = Literal["固定镜头", "缓慢推镜", "快速推镜", "缓慢拉镜", "平稳横移", "跟拍", "摇镜", "手持跟随"]
Stability = Literal["稳定", "微晃", "晃动"]

CONSTRAINTS = (
    "保持无字幕，避免生成任何文字或字幕",
    "视频全程禁止出现外形、着装、配饰完全一致的人物",
)
_CLAUSE = re.compile(r"[；;。]")
_NEGATION = re.compile(r"(无|没有|禁)")
_SHOT_TIME_POLLUTION = re.compile(
    r"(?:\d+(?:\.\d+)?\s*[—–\-~～]\s*\d+(?:\.\d+)?\s*(?:秒|s\b)|第\s*\d+(?:\.\d+)?\s*秒|\b\d{1,2}:\d{2}(?:\.\d+)?\b)",
    re.IGNORECASE,
)
_SHOT_PROTOCOL_POLLUTION = re.compile(
    r"(?:@\[?图片\d+\]?|<Picture\s*\d+>|【镜头\s*\d*】|\[Shot\s*\d+\])",
    re.IGNORECASE,
)


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
    root_by_id: dict[str, str]
    kind_by_id: dict[str, Literal["character", "scene", "prop"]]
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


def _world_line(world) -> str:
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


def _asset_kind(
    asset_id: str, catalog: dict[str, Asset] | None = None
) -> Literal["character", "scene", "prop"]:
    if catalog and asset_id in catalog:
        return catalog[asset_id].kind
    kind = {"C": "character", "S": "scene", "P": "prop"}.get(asset_id[:1], "prop")
    return kind  # type: ignore[return-value]


def _root_id(asset_id: str, catalog: dict[str, Asset]) -> str:
    asset = catalog.get(asset_id)
    if asset and asset.parentId:
        return asset.parentId
    return asset_id


def _display_asset_name(
    asset_id: str, catalog: dict[str, Asset], outline_names: dict[str, str]
) -> str:
    asset = catalog.get(asset_id)
    root_id = _root_id(asset_id, catalog)
    base_name = outline_names.get(root_id) or (asset.name if asset else asset_id)
    label = (asset.variantLabel or "").strip() if asset else ""
    return f"{base_name}（{label}）" if label else base_name


def _reference_order(ids: list[str], catalog: dict[str, Asset] | None = None) -> list[str]:
    order = {"character": 0, "scene": 1, "prop": 2}
    return sorted(
        ids,
        key=lambda asset_id: (order.get(_asset_kind(asset_id, catalog), 3), ids.index(asset_id)),
    )


def compose_seedance(
    segment: Segment, design: SegmentDesign, script: ScriptResult, assets: AssetResult
) -> str:
    scene_names = {card.id: card.name for card in script.outline.scenes}
    character_names = {card.id: card.name for card in script.outline.characters}
    prop_names = {prop.id: prop.name for prop in script.outline.props}
    names = {**scene_names, **character_names, **prop_names}
    catalog = {asset.id: asset for asset in assets.assets}

    ordered = _reference_order(design.references, catalog)
    blocks: list[str] = [
        f"@[图片{number}] = {_display_asset_name(asset_id, catalog, names)}"
        for number, asset_id in enumerate(ordered, 1)
    ]

    voices = {asset.id: asset.voice for asset in assets.assets if asset.voice}
    ordered_slot_by_root: dict[str, tuple[int, str]] = {}
    for number, asset_id in enumerate(ordered, 1):
        ordered_slot_by_root.setdefault(_root_id(asset_id, catalog), (number, asset_id))

    speaker_ids: list[str] = []
    for cut in segment.cuts:
        for beat in cut.beats:
            if (
                beat.line is not None
                and beat.speaker
                and beat.speaker != "VO"
                and beat.speaker not in speaker_ids
            ):
                speaker_ids.append(beat.speaker)
    voiced: list[str] = []
    for speaker_id in speaker_ids:
        slot = ordered_slot_by_root.get(speaker_id)
        matched_asset_id = slot[1] if slot else speaker_id
        voice_text = voices.get(matched_asset_id) or voices.get(speaker_id)
        if not voice_text:
            continue
        name = names.get(speaker_id, speaker_id)
        prefix = f"@[图片{slot[0]}] " if slot is not None else ""
        voiced.append(f"{prefix}{name}：{voice_text}")
    if voiced:
        blocks.extend(["", "【角色音色】", *voiced])

    blocks.extend(["", "【人物关系与构图逻辑】", design.blocking])

    for cut, shot in zip(segment.cuts, sorted(design.cuts, key=lambda item: item.index), strict=False):
        blocks.extend(
            [
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
            ]
        )
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


def _retry(message: str, meta: dict | None = None) -> None:
    record_gate("plan-storyboard", False, [message], meta)
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
        roots_picked = [ctx.deps.root_by_id.get(aid, aid) for aid in segment.references]
        if len(set(roots_picked)) != len(roots_picked):
            _retry(
                f"第 {segment.id} 段的 references 同时选中了同一资产的多个版本（主图与变体），"
                "同一角色/场景/道具在单段内只能选 1 个最匹配当前状态的版本。",
                meta,
            )
        if not any(
            ctx.deps.kind_by_id.get(asset_id, _asset_kind(asset_id)) == "scene"
            for asset_id in segment.references
        ):
            _retry(f"第 {segment.id} 段的 references 必须包含场景。", meta)
        for cut in segment.cuts:
            for name in ctx.deps.forbidden_names:
                if name and name in cut.shot:
                    _retry(
                        f"第 {segment.id} 段镜头 {cut.index} 的「画面」里出现了角色名「{name}」，"
                        "请改成身份或外观描述。",
                        meta,
                    )
            bad_time = _SHOT_TIME_POLLUTION.search(cut.shot)
            if bad_time:
                _retry(
                    f"第 {segment.id} 段镜头 {cut.index} 的「画面」里出现了时间/秒数"
                    f"「{bad_time.group(0)}」，请删掉。",
                    meta,
                )
            bad_proto = _SHOT_PROTOCOL_POLLUTION.search(cut.shot)
            if bad_proto:
                _retry(
                    f"第 {segment.id} 段镜头 {cut.index} 的「画面」里出现了协议标记"
                    f"「{bad_proto.group(0)}」，请删掉。",
                    meta,
                )
    record_gate("plan-storyboard", True, meta=meta)
    return design


def split_cuts(numbered: list[tuple[Beat, int]]) -> tuple[Cut, ...]:
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
        for offset, (bucket, total) in enumerate(zip(buckets, totals, strict=True))
    )


def _segment(scene: Scene, numbered: list[tuple[Beat, int]], index: int, cap: int) -> Segment:
    cuts = split_cuts(numbered)
    precise = sum(cut.seconds for cut in cuts)
    seconds = min(cap, max(1, round(precise)))
    return Segment(
        index=index,
        scene=scene,
        cuts=cuts,
        seconds=seconds,
        beat_range=(numbered[0][1], numbered[-1][1]),
    )


def split_episode(episode: Episode, cap: int) -> list[Segment]:
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
    model: Model,
    episode: Episode,
    segments: list[Segment],
    script: ScriptResult,
    *,
    assets: AssetResult | None = None,
    feedback: str = "",
    initial_blocking: dict | None = None,
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[int, SegmentDesign]:
    names = {card.id: card.name for card in script.outline.characters}
    scene_names = {card.id: card.name for card in script.outline.scenes}
    prop_names = {prop.id: prop.name for prop in script.outline.props}
    outline_names = {**names, **scene_names, **prop_names}

    catalog: dict[str, Asset] = {asset.id: asset for asset in assets.assets} if assets else {}
    variants_by_parent: dict[str, list[Asset]] = {}
    for asset in catalog.values():
        if asset.parentId:
            variants_by_parent.setdefault(asset.parentId, []).append(asset)
    root_by_id: dict[str, str] = {aid: _root_id(aid, catalog) for aid in catalog}
    kind_by_id: dict[str, Literal["character", "scene", "prop"]] = {
        aid: _asset_kind(aid, catalog) for aid in catalog
    }

    def build_segment_asset_options(segment: Segment) -> tuple[list[dict], frozenset[str]]:
        options: list[dict] = []
        allowed: list[str] = []
        for root_id in segment_asset_ids(segment):
            root_asset = catalog.get(root_id)
            root_kind = _asset_kind(root_id, catalog)
            root_by_id.setdefault(root_id, root_id)
            kind_by_id.setdefault(root_id, root_kind)
            variants = variants_by_parent.get(root_id, [])
            entry: dict = {
                "id": root_id,
                "name": outline_names.get(root_id, root_asset.name if root_asset else root_id),
                "kind": root_kind,
            }
            if variants:
                entry["state"] = "默认主造型"
                if root_asset and root_asset.description:
                    entry["description"] = root_asset.description
            options.append(entry)
            allowed.append(root_id)
            for variant in variants:
                root_by_id[variant.id] = root_id
                kind_by_id[variant.id] = variant.kind
                options.append(
                    {
                        "id": variant.id,
                        "parentId": root_id,
                        "name": variant.name,
                        "variantLabel": variant.variantLabel,
                        "kind": variant.kind,
                        "description": variant.description,
                    }
                )
                allowed.append(variant.id)
        return options, frozenset(allowed)

    agent = Agent(
        model,
        deps_type=DesignContext,
        output_type=PromptedOutput(StoryboardDesign),
        instructions=skill_instructions("plan-storyboard"),
        model_settings=MODEL_SETTINGS,
        retries=5,
    )
    agent.output_validator(verify_designs)

    designs: dict[int, SegmentDesign] = {}
    previous_blocking: dict | None = initial_blocking
    total_batches = (len(segments) + DESIGN_BATCH_SEGMENTS - 1) // DESIGN_BATCH_SEGMENTS
    for batch_idx, start in enumerate(range(0, len(segments), DESIGN_BATCH_SEGMENTS), 1):
        batch = segments[start : start + DESIGN_BATCH_SEGMENTS]
        pct = 15 + int((batch_idx - 1) / max(1, total_batches) * 75)
        await _notify(
            on_progress,
            batch_idx,
            total_batches + 1,
            f"正在设计第 {episode.number} 集分镜第 {batch_idx}/{total_batches} 批",
            pct,
        )
        batch_segments_payload: list[dict] = []
        batch_available: dict[int, frozenset[str]] = {}
        for segment in batch:
            seg_assets, seg_allowed = build_segment_asset_options(segment)
            batch_available[segment.index] = seg_allowed
            seg_payload: dict = {
                "id": segment.index,
                "sceneId": segment.scene.sceneId,
                "durationSeconds": segment.seconds,
                "scene": scene_names.get(segment.scene.sceneId, segment.scene.sceneId),
                "characters": [names.get(c, c) for c in segment.scene.characters],
                "props": [prop_names.get(p, p) for p in segment.scene.props],
                "assets": seg_assets,
                "cuts": [
                    {
                        "index": cut.index,
                        "seconds": cut.seconds,
                        "beats": [_beat_payload(beat, names) for beat in cut.beats],
                    }
                    for cut in segment.cuts
                ],
            }
            if segment.scene.lighting and segment.scene.lighting.strip():
                seg_payload["lighting"] = segment.scene.lighting.strip()
            batch_segments_payload.append(seg_payload)

        payload: dict = {
            "episode": episode.number,
            "settings": {
                **script.settings.model_dump(),
                "world": script.outline.world.model_dump() if script.outline.world else None,
            },
            "maxSegmentDuration": script.settings.maxSegmentDuration,
            "cutSeconds": {"min": MIN_CUT_SECONDS, "max": MAX_CUT_SECONDS},
            "segments": batch_segments_payload,
        }
        if previous_blocking is not None:
            payload["previousBlocking"] = previous_blocking
        if feedback.strip():
            payload["directorFeedback"] = feedback.strip()
        result = await agent.run(
            prompt(payload),
            deps=DesignContext(
                {s.index: tuple(c.index for c in s.cuts) for s in batch},
                batch_available,
                tuple(c.name for c in script.outline.characters),
                root_by_id=root_by_id,
                kind_by_id=kind_by_id,
                episode=episode.number,
            ),
            usage=usage,
        )
        designs.update({segment.id: segment for segment in result.output.segments})
        last_segment = batch[-1]
        previous_blocking = {
            "segmentId": last_segment.index,
            "sceneId": last_segment.scene.sceneId,
            "scene": scene_names.get(last_segment.scene.sceneId, last_segment.scene.sceneId),
            "blocking": designs[last_segment.index].blocking,
        }
    return designs


async def storyboard_episode(
    model: Model,
    episode: Episode,
    script: ScriptResult,
    assets: AssetResult,
    *,
    feedback: str = "",
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> EpisodeStoryboard:
    cap = script.settings.maxSegmentDuration
    segments = split_episode(episode, cap)
    designs = await write_designs(
        model,
        episode,
        segments,
        script,
        assets=assets,
        feedback=feedback,
        usage=usage,
        on_progress=on_progress,
    )

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
    referenced_in_episode: list[str] = []
    for segment in segments:
        design = designs[segment.index]
        by_index = {cut.index: cut for cut in design.cuts}
        ordered = _reference_order(design.references, catalog)
        referenced_in_episode.extend(ordered)
        clips.append(
            StoryboardClip(
                id=segment.index,
                durationSeconds=segment.seconds,
                prompt=compose_seedance(segment, design, script, assets),
                assetIds=ordered,
                references=[
                    StoryboardReference(
                        index=position + 1,
                        assetId=asset_id,
                        name=_display_asset_name(asset_id, catalog, names),
                        kind=_asset_kind(asset_id, catalog),
                    )
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
            )
        )

    episode_asset_refs = list(dict.fromkeys([*used, *referenced_in_episode]))
    return EpisodeStoryboard(
        number=episode.number,
        assets=[
            StoryboardAssetRef(
                id=aid,
                kind=_asset_kind(aid, catalog),
                name=_display_asset_name(aid, catalog, names),
            )
            for aid in episode_asset_refs
            if aid in catalog
        ],
        clips=clips,
    )


async def storyboard(
    model: Model,
    script: ScriptResult,
    assets: AssetResult,
    only_episode: int | None = None,
    *,
    feedback: str = "",
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> StoryboardResult:
    episodes = [
        await storyboard_episode(
            model,
            ep,
            script,
            assets,
            feedback=feedback,
            usage=usage,
            on_progress=on_progress,
        )
        for ep in script.episodes
        if only_episode is None or ep.number == only_episode
    ]
    if not episodes:
        raise ValueError(f"剧本里没有第 {only_episode} 集。")
    return StoryboardResult(settings=script.settings, episodes=episodes)


@dataclass(frozen=True)
class GeneratedClipSpec:
    prompt: str
    references: list[StoryboardReference]
    blocking: str
    cuts: list[StoryboardCut]
    duration_seconds: int


class FreeformCutDesign(Record):
    index: int
    seconds: Annotated[float, Field(gt=0, le=10)]
    shotSize: ShotSize
    camera: CameraMove
    lens: Text
    cameraPosition: Text
    composition: Text
    shot: Text
    dialogue: str = ""
    eyeline: Text
    focus: Text
    stability: Stability
    framePrompt: Text
    sfx: str = ""
    lighting: str = ""


class FreeformClipDesign(Record):
    references: list[str] = Field(default_factory=list, max_length=6)
    blocking: Text
    soundscape: str = ""
    music: str = ""
    cuts: Annotated[list[FreeformCutDesign], Field(min_length=1, max_length=12)]


@dataclass(frozen=True)
class FreeformClipContext:
    allowed_refs: frozenset[str]
    require_refs: bool
    root_by_id: dict[str, str]
    forbidden_names: tuple[str, ...]
    min_cuts: int
    max_cuts: int


_FREEFORM_CLIP_INSTRUCTIONS = (
    "你是 FrameDrama 影视短剧分镜导演，负责为单集分镜重写或新增一个高质量视频片段的镜头设计。\n"
    "请严格按输入中的目标时长（durationSeconds）、推荐镜次范围（cutCountRange）、"
    "上下文片段与导演要求输出 JSON：\n"
    "- 若输入提供了 availableAssets（非空），请从中选出本片段真正出镜的 1–6 个资产/变体编号填入 references；"
    "同一角色/场景/道具严禁同时选中主设定与变体，尽量包含场景与出镜人物。\n"
    "- 若输入提供了 lockedReferenceSlots（锁定当前参考素材），则 references 留空数组 []，"
    "画面与人物调度必须严格围绕已锁定的参考素材展开。\n"
    "- cuts 数量必须在 cutCountRange 内，各镜 seconds 之和应接近 durationSeconds（每镜约 2–5 秒）。\n"
    "- shot（画面）中严禁出现角色姓名、秒数/时间范围、镜头编号或 @[图片N] 协议标记，"
    "用外观/身份描述动作细节。\n"
    "- 若本镜有对白，在 dialogue 填「台词（角色，情绪）：对白内容」；无对白则 dialogue 留空字符串。\n"
    "- 若存在 prevClip / nextClip，blocking 与画面需自然承接前后镜头的人物站位与情绪节奏。\n"
    "- 若输入有 directorFeedback，必须优先落实其中的构图、运镜、光影、节奏或服装/变体要求。"
)


def _verify_freeform_clip(
    ctx: RunContext[FreeformClipContext], design: FreeformClipDesign
) -> FreeformClipDesign:
    if ctx.deps.require_refs:
        if not design.references:
            raise ModelRetry("references 不能为空，请至少选择本段需要的场景或角色资产。")
        unknown = [aid for aid in design.references if aid not in ctx.deps.allowed_refs]
        if unknown:
            raise ModelRetry(f"references 包含不存在的资产编号：{unknown}")
        if len(set(design.references)) != len(design.references):
            raise ModelRetry("references 存在重复项，请去重。")
        roots = [ctx.deps.root_by_id.get(aid, aid) for aid in design.references]
        if len(set(roots)) != len(roots):
            raise ModelRetry("同一角色/场景/道具在单段内只能选 1 个版本（主图或其中一个变体），不能同时选。")
    if not (ctx.deps.min_cuts <= len(design.cuts) <= ctx.deps.max_cuts):
        raise ModelRetry(
            f"镜头数量（cuts）需在 {ctx.deps.min_cuts}–{ctx.deps.max_cuts} 之间以匹配目标时长，"
            f"当前为 {len(design.cuts)}。"
        )
    for cut in design.cuts:
        for name in ctx.deps.forbidden_names:
            if name and name in cut.shot:
                raise ModelRetry(f"镜头 {cut.index} 的 shot 中出现了角色名「{name}」，请改成身份或外观描述。")
        if _SHOT_TIME_POLLUTION.search(cut.shot):
            raise ModelRetry(f"镜头 {cut.index} 的 shot 中出现了时间/秒数，请删掉。")
        if _SHOT_PROTOCOL_POLLUTION.search(cut.shot):
            raise ModelRetry(f"镜头 {cut.index} 的 shot 中出现了协议标记，请删掉。")
    return design


def _cut_count_range(duration_seconds: int) -> tuple[int, int]:
    clamped = max(4, min(30, int(duration_seconds)))
    min_cuts = max(1, round(clamped / 5.0))
    max_cuts = max(min_cuts + 1, min(10, round(clamped / 2.2)))
    return min_cuts, max_cuts


def _compose_freeform_seedance(
    design: FreeformClipDesign,
    *,
    script: ScriptResult,
    assets: AssetResult,
    slot_headers: list[str],
    ordered_asset_ids: list[str],
) -> str:
    catalog = {asset.id: asset for asset in assets.assets}
    names = {
        **{card.id: card.name for card in script.outline.characters},
        **{card.id: card.name for card in script.outline.scenes},
        **{prop.id: prop.name for prop in script.outline.props},
    }
    voices = {asset.id: asset.voice for asset in assets.assets if asset.voice}

    blocks: list[str] = list(slot_headers)
    voiced: list[str] = []
    seen_voice_roots: set[str] = set()
    for idx, aid in enumerate(ordered_asset_ids, 1):
        root_id = _root_id(aid, catalog)
        if _asset_kind(aid, catalog) != "character" or root_id in seen_voice_roots:
            continue
        voice_text = voices.get(aid) or voices.get(root_id)
        if voice_text:
            seen_voice_roots.add(root_id)
            voiced.append(f"@[图片{idx}] {names.get(root_id, root_id)}：{voice_text}")
    if voiced:
        blocks.extend(["", "【角色音色】", *voiced])

    blocks.extend(["", "【人物关系与构图逻辑】", design.blocking])

    for idx, shot in enumerate(sorted(design.cuts, key=lambda item: item.index), 1):
        dialogue_line = shot.dialogue.strip() or "台词：{}"
        if dialogue_line != "台词：{}" and not dialogue_line.startswith("台词"):
            dialogue_line = f"台词：{dialogue_line}"
        blocks.extend(
            [
                "",
                f"【镜头{idx}】",
                f"焦距：{shot.lens}",
                f"机位：{shot.cameraPosition}",
                f"构图：{shot.composition}",
                f"运镜：{shot.camera}",
                f"景别：{shot.shotSize}",
                f"画面：{shot.shot}",
                dialogue_line,
                f"视线落点：{shot.eyeline}",
                f"焦点：{shot.focus}",
                f"稳定性：{shot.stability}",
            ]
        )
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
    return "\n".join(blocks).lstrip("\n")


def _build_all_asset_options(
    assets: AssetResult, script: ScriptResult
) -> tuple[list[dict], frozenset[str], dict[str, str]]:
    outline_names = {
        **{card.id: card.name for card in script.outline.characters},
        **{card.id: card.name for card in script.outline.scenes},
        **{prop.id: prop.name for prop in script.outline.props},
    }
    catalog = {a.id: a for a in assets.assets}
    root_by_id = {a.id: _root_id(a.id, catalog) for a in assets.assets}
    options: list[dict] = []
    for a in assets.assets:
        entry: dict = {
            "id": a.id,
            "name": outline_names.get(a.parentId or a.id, a.name),
            "kind": a.kind,
            "description": a.description,
        }
        if a.parentId:
            entry["parentId"] = a.parentId
            entry["variantLabel"] = a.variantLabel
        options.append(entry)
    return options, frozenset(catalog.keys()), root_by_id


async def _run_freeform_clip_agent(
    model: Model,
    *,
    script: ScriptResult,
    episode: Episode,
    assets: AssetResult,
    duration_seconds: int,
    feedback: str,
    locked_references: list[dict] | None,
    current_prompt: str = "",
    prev_clip: dict | None = None,
    next_clip: dict | None = None,
    usage: RunUsage | None = None,
) -> GeneratedClipSpec:
    catalog = {a.id: a for a in assets.assets}
    outline_names = {
        **{card.id: card.name for card in script.outline.characters},
        **{card.id: card.name for card in script.outline.scenes},
        **{prop.id: prop.name for prop in script.outline.props},
    }
    min_cuts, max_cuts = _cut_count_range(duration_seconds)
    use_locked = locked_references is not None

    if use_locked:
        available_options: list[dict] = []
        allowed_refs: frozenset[str] = frozenset()
        root_by_id: dict[str, str] = {}
        img_n = vid_n = aud_n = 0
        locked_slot_headers: list[str] = []
        locked_slot_payload: list[dict] = []
        locked_image_codes: list[str] = []
        for raw_ref in locked_references:
            if not isinstance(raw_ref, dict):
                continue
            media_kind = str(raw_ref.get("mediaKind") or "").strip().lower()
            if media_kind not in ("image", "video", "audio"):
                raw_kind = str(raw_ref.get("kind") or "").strip().lower()
                media_kind = raw_kind if raw_kind in ("video", "audio") else "image"
            ref_name = str(raw_ref.get("name") or raw_ref.get("assetCode") or "参考素材").strip()
            ref_code = str(raw_ref.get("assetCode") or raw_ref.get("assetId") or "").strip()
            if media_kind == "video":
                vid_n += 1
                slot = f"@[视频{vid_n}]"
            elif media_kind == "audio":
                aud_n += 1
                slot = f"@[音频{aud_n}]"
            else:
                img_n += 1
                slot = f"@[图片{img_n}]"
                if ref_code in catalog:
                    locked_image_codes.append(ref_code)
            locked_slot_headers.append(f"{slot} = {ref_name}")
            locked_slot_payload.append({"slot": slot, "name": ref_name, "mediaKind": media_kind})
    else:
        available_options, allowed_refs, root_by_id = _build_all_asset_options(assets, script)
        locked_slot_headers = []
        locked_slot_payload = []
        locked_image_codes = []

    payload: dict = {
        "episode": episode.number,
        "episodeTitle": episode.title,
        "episodeSummary": episode.summary,
        "durationSeconds": duration_seconds,
        "cutCountRange": {"min": min_cuts, "max": max_cuts},
        "settings": {
            **script.settings.model_dump(),
            "world": script.outline.world.model_dump() if script.outline.world else None,
        },
    }
    if use_locked:
        payload["lockedReferenceSlots"] = locked_slot_payload
    else:
        payload["availableAssets"] = available_options
    if current_prompt.strip():
        payload["currentPrompt"] = current_prompt.strip()
    if prev_clip:
        payload["prevClip"] = prev_clip
    if next_clip:
        payload["nextClip"] = next_clip
    if feedback.strip():
        payload["directorFeedback"] = feedback.strip()

    agent = Agent(
        model,
        deps_type=FreeformClipContext,
        output_type=PromptedOutput(FreeformClipDesign),
        instructions=_FREEFORM_CLIP_INSTRUCTIONS,
        model_settings=MODEL_SETTINGS,
        retries=3,
    )
    agent.output_validator(_verify_freeform_clip)
    result = await agent.run(
        prompt(payload),
        deps=FreeformClipContext(
            allowed_refs=allowed_refs,
            require_refs=not use_locked and bool(allowed_refs),
            root_by_id=root_by_id,
            forbidden_names=tuple(c.name for c in script.outline.characters),
            min_cuts=min_cuts,
            max_cuts=max_cuts,
        ),
        usage=usage,
    )
    design = result.output

    if use_locked:
        slot_headers = locked_slot_headers
        ordered_ids = locked_image_codes
        refs_out: list[StoryboardReference] = []
    else:
        ordered_ids = _reference_order(design.references, catalog)
        slot_headers = [
            f"@[图片{num}] = {_display_asset_name(aid, catalog, outline_names)}"
            for num, aid in enumerate(ordered_ids, 1)
        ]
        refs_out = [
            StoryboardReference(
                index=pos + 1,
                assetId=aid,
                name=_display_asset_name(aid, catalog, outline_names),
                kind=_asset_kind(aid, catalog),
            )
            for pos, aid in enumerate(ordered_ids)
        ]

    final_prompt = _compose_freeform_seedance(
        design,
        script=script,
        assets=assets,
        slot_headers=slot_headers,
        ordered_asset_ids=ordered_ids,
    )
    cuts_out = [
        StoryboardCut(
            index=idx,
            seconds=round(float(cut.seconds), 1),
            shotSize=cut.shotSize,
            camera=cut.camera,
            framePrompt=cut.framePrompt,
            beats=(1, 1),
        )
        for idx, cut in enumerate(sorted(design.cuts, key=lambda c: c.index), 1)
    ]
    return GeneratedClipSpec(
        prompt=final_prompt,
        references=refs_out,
        blocking=design.blocking,
        cuts=cuts_out,
        duration_seconds=duration_seconds,
    )


async def regenerate_clip_storyboard(
    model: Model,
    *,
    script: ScriptResult,
    episode: Episode,
    assets: AssetResult,
    clip_index: int,
    clip_beats: tuple[int, int] | None,
    duration_seconds: int,
    current_prompt: str,
    current_references: list[dict],
    refresh_references: bool = True,
    feedback: str = "",
    prev_clip: dict | None = None,
    next_clip: dict | None = None,
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> GeneratedClipSpec:
    await _notify(on_progress, 1, 2, f"正在重生成片段 {clip_index} 分镜设计", 35)
    cap = script.settings.maxSegmentDuration
    segments = split_episode(episode, cap)
    matched_segment: Segment | None = None
    if clip_beats is not None:
        matched_segment = next((s for s in segments if s.beat_range == clip_beats), None)
    if matched_segment is None and 1 <= clip_index <= len(segments) and clip_beats is not None:
        matched_segment = segments[clip_index - 1]

    if refresh_references and matched_segment is not None:
        catalog = {a.id: a for a in assets.assets}
        names = {
            **{card.id: card.name for card in script.outline.characters},
            **{card.id: card.name for card in script.outline.scenes},
            **{prop.id: prop.name for prop in script.outline.props},
        }
        initial_blocking = (
            {
                "segmentId": max(1, matched_segment.index - 1),
                "sceneId": matched_segment.scene.sceneId,
                "scene": names.get(matched_segment.scene.sceneId, matched_segment.scene.sceneId),
                "blocking": prev_clip.get("blocking", ""),
            }
            if prev_clip and prev_clip.get("blocking")
            else None
        )
        designs = await write_designs(
            model,
            episode,
            [matched_segment],
            script,
            assets=assets,
            feedback=feedback,
            initial_blocking=initial_blocking,
            usage=usage,
        )
        design = designs[matched_segment.index]
        by_index = {cut.index: cut for cut in design.cuts}
        ordered = _reference_order(design.references, catalog)
        await _notify(on_progress, 2, 2, f"片段 {clip_index} 分镜重生成完成", 95)
        return GeneratedClipSpec(
            prompt=compose_seedance(matched_segment, design, script, assets),
            references=[
                StoryboardReference(
                    index=pos + 1,
                    assetId=aid,
                    name=_display_asset_name(aid, catalog, names),
                    kind=_asset_kind(aid, catalog),
                )
                for pos, aid in enumerate(ordered)
            ],
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
                for cut in matched_segment.cuts
            ],
            duration_seconds=duration_seconds,
        )

    spec = await _run_freeform_clip_agent(
        model,
        script=script,
        episode=episode,
        assets=assets,
        duration_seconds=duration_seconds,
        feedback=feedback,
        locked_references=None if refresh_references else current_references,
        current_prompt=current_prompt,
        prev_clip=prev_clip,
        next_clip=next_clip,
        usage=usage,
    )
    await _notify(on_progress, 2, 2, f"片段 {clip_index} 分镜重生成完成", 95)
    return spec


async def generate_new_clip_storyboard(
    model: Model,
    *,
    script: ScriptResult,
    episode: Episode,
    assets: AssetResult,
    duration_seconds: int,
    feedback: str = "",
    prev_clip: dict | None = None,
    next_clip: dict | None = None,
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> GeneratedClipSpec:
    await _notify(on_progress, 1, 2, "正在结合上下文与资产设计新片段", 35)
    spec = await _run_freeform_clip_agent(
        model,
        script=script,
        episode=episode,
        assets=assets,
        duration_seconds=duration_seconds,
        feedback=feedback,
        locked_references=None,
        prev_clip=prev_clip,
        next_clip=next_clip,
        usage=usage,
    )
    await _notify(on_progress, 2, 2, "新片段分镜设计已完成", 95)
    return spec
