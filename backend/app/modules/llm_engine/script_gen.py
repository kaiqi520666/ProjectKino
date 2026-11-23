import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PositiveInt
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext, RunUsage
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model

from app.modules.llm_engine.gates import record_gate
from app.modules.llm_engine.provider import (
    BEAT_SHEET_MODEL_SETTINGS,
    MODEL_SETTINGS,
    PLANNING_MODEL_SETTINGS,
    SHARED_USAGE_LIMITS,
)
from app.modules.llm_engine.schema import (
    Character,
    CharacterId,
    Episode,
    EpisodeDraft,
    EpisodePlan,
    Outline,
    ProjectSettings,
    PropCard,
    PropId,
    Record,
    Scene,
    SceneCard,
    SceneId,
    ScriptResult,
    Text,
    World,
)
from app.modules.llm_engine.timing import (
    ACTION_SECONDS,
    CHARS_PER_SECOND,
    DURATION_SLACK,
    HARD_TOLERANCE,
    HOOK_WINDOW,
    MAX_LINE_CHARS,
    beat_seconds,
    episode_duration_problems,
    episode_problems,
    episode_seconds,
    episode_warnings,
    line_chars,
    render_script,
    seconds_range,
)

ProgressCallback = Callable[[int, int, str, int], Awaitable[None]]
OutlineCallback = Callable[[Outline], Awaitable[None]]
EpisodeReadyCallback = Callable[[Episode], Awaitable[None]]

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
DIGEST_THRESHOLD_CHARS = 40_000
CHUNK_CHARS = 20_000
MAX_SOURCE_LINE_CHARS = 400
MAX_SOURCE_LINES_PER_EPISODE = 4000
MAX_SOURCE_EXCERPT_CHARS_PER_EPISODE = 30_000
MAX_GROUP_SECONDS = 180
GROUP_DURATION_TOLERANCE = 0.30

_ACTION_QUOTES = re.compile(r"[「」『』“”\"]")

_CHAPTER_HEADING = re.compile(r"^\s*(第[〇零一二三四五六七八九十百千万0-9]+[章回节][^\n]{0,40})\s*$")
_SOFT_BREAK_CHARS = "。！？；!?;…\n"
_ERA_DYNASTY = re.compile(r"(夏|商|周|秦|汉|三国|晋|南北朝|隋|唐|五代|宋|辽|金|元|明|清|民国)")
_ERA_YEAR = re.compile(r"\d{3,4}\s*年|\d{1,2}\s*年代")
_VAGUE_ERA = {"古代", "古装", "架空", "某朝", "未来", "现代", "年代"}


def _wrap_long_line(line: str, limit: int = MAX_SOURCE_LINE_CHARS) -> list[str]:
    if len(line) <= limit:
        return [line]
    parts: list[str] = []
    remaining = line
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = max((window.rfind(ch) for ch in _SOFT_BREAK_CHARS), default=-1)
        if cut >= limit // 2:
            split_at = cut + 1
        else:
            split_at = limit
        parts.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        parts.append(remaining)
    return parts


@dataclass(frozen=True)
class Source:
    mode: Literal["story", "upload"]
    lines: list[str]

    @classmethod
    def from_text(cls, mode: Literal["story", "upload"], text: str) -> "Source":
        if not text.strip():
            raise ValueError("故事内容不能为空。")
        raw_lines = text.splitlines()
        normalized: list[str] = []
        for raw_line in raw_lines:
            normalized.extend(_wrap_long_line(raw_line))
        return cls(mode, normalized)

    @property
    def chars(self) -> int:
        return sum(len(line) for line in self.lines)

    def excerpt(self, start: int, end: int) -> str:
        return "\n".join(f"{i}: {self.lines[i - 1]}" for i in range(start, end + 1))


@dataclass(frozen=True)
class OutlineContext:
    settings: ProjectSettings
    source: Source


@dataclass(frozen=True)
class EpisodeContext:
    plan: EpisodePlan
    outline: Outline
    source: Source | None
    settings: ProjectSettings


@dataclass(frozen=True)
class ExtensionContext:
    outline: Outline
    next_number: int


@dataclass(frozen=True)
class BeatSheetContext:
    plan: EpisodePlan
    outline: Outline
    source: Source | None
    settings: ProjectSettings


@dataclass(frozen=True)
class SceneGroupContext:
    plan: EpisodePlan
    outline: Outline
    source: Source | None
    settings: ProjectSettings
    group_index: int
    group_total: int
    group_target: int
    is_patch: bool = False


class ChunkDigest(Record):
    summary: Text
    events: Annotated[list[Text], Field(min_length=1)]


class SceneBeatPlan(Record):
    index: PositiveInt
    sceneId: SceneId
    lighting: str = ""
    characters: list[CharacterId] = Field(default_factory=list)
    props: list[PropId] = Field(default_factory=list)
    goal: Text
    targetSeconds: Annotated[int, Field(ge=20, le=MAX_GROUP_SECONDS)]


class EpisodeBeatSheet(Record):
    title: Text
    summary: Text
    hook: Text
    cliff: Text
    scenes: Annotated[list[SceneBeatPlan], Field(min_length=1, max_length=16)]


class SceneGroupDraft(Record):
    scenes: Annotated[list[Scene], Field(min_length=1)]
    hookBeat: tuple[PositiveInt, PositiveInt] | None = None


class EpisodeExtension(Record):
    plan: EpisodePlan
    newCharacters: list[Character] = Field(default_factory=list)
    newScenes: list[SceneCard] = Field(default_factory=list)
    newProps: list[PropCard] = Field(default_factory=list)
    continuityUpdate: str = ""


def skill_instructions(
    name: Literal[
        "plan-episodes",
        "plan-episode-beats",
        "write-episode",
        "append-episode",
        "condense-source",
        "analyze-assets",
        "plan-storyboard",
    ],
) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    return path.read_text(encoding="utf-8").split("\n---\n", 1)[1].strip()


def prompt(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def chunk_ranges(lines: list[str]) -> list[tuple[int, int]]:
    total = len(lines)
    ranges: list[tuple[int, int]] = []
    start = 1
    size = 0
    for number, line in enumerate(lines, 1):
        heading = _CHAPTER_HEADING.match(line) is not None
        if number > start and size and (size >= CHUNK_CHARS or (heading and size >= CHUNK_CHARS * 0.6)):
            ranges.append((start, number - 1))
            start = number
            size = 0
        size += len(line)
        if size >= CHUNK_CHARS * 1.6:
            ranges.append((start, number))
            start = number + 1
            size = 0
    if start <= total:
        ranges.append((start, total))
    return ranges


async def _notify(
    cb: ProgressCallback | None, step_index: int, step_total: int, label: str, progress: int
) -> None:
    if cb is not None:
        await cb(step_index, step_total, label, progress)


async def condense_source(
    model: Model,
    source: Source,
    *,
    usage: RunUsage | None = None,
) -> list[dict]:
    agent = Agent(
        model,
        output_type=PromptedOutput(ChunkDigest),
        instructions=skill_instructions("condense-source"),
        model_settings=MODEL_SETTINGS,
        retries=1,
    )
    limiter = asyncio.Semaphore(4)

    async def summarize(bounds: tuple[int, int]) -> dict:
        start, end = bounds
        async with limiter:
            result = await agent.run(
                prompt({"lines": [start, end], "text": source.excerpt(start, end)}),
                usage=usage,
                usage_limits=SHARED_USAGE_LIMITS,
            )
        return {"lines": [start, end], "summary": result.output.summary, "events": result.output.events}

    return list(await asyncio.gather(*(summarize(bounds) for bounds in chunk_ranges(source.lines))))


def world_problems(world: World | None) -> list[str]:
    if world is None:
        return ["缺少世界基准 world，请给出 kind、era 和 baseline，用于统一全剧的年代、建筑、材质与器物。"]

    problems: list[str] = []
    era = world.era.strip()
    if era in _VAGUE_ERA:
        problems.append(f"era「{era}」太笼统，请写成一个具体的时空坐标。")
    elif world.kind == "historical" and not (_ERA_DYNASTY.search(era) or _ERA_YEAR.search(era)):
        problems.append(f"历史/民国题材的 era「{era}」需要具体到朝代或年份。")

    baseline = world.baseline.strip()
    if len(baseline) < 16:
        problems.append("world.baseline 太短，至少写清建筑/服饰/材质特征以及明确排除的时代外物件。")
    if world.kind == "historical" and not re.search(r"(无|没有|禁)", baseline):
        problems.append("历史/民国题材的 world.baseline 需要写清不能出现的现代物件（如无电灯、无塑料）。")
    return problems


def verify_outline(ctx: RunContext[OutlineContext], outline: Outline) -> Outline:
    count = ctx.deps.settings.episodeCount
    problems = world_problems(outline.world)
    numbers = [plan.number for plan in outline.episodes]
    if numbers != list(range(1, count + 1)):
        problems.append(f"分集数量和集号必须恰好是 1..{count}，实际是 {numbers}。")

    character_ids = {item.id for item in outline.characters}
    scene_ids = {item.id for item in outline.scenes}
    prop_ids = {item.id for item in outline.props}
    if len(character_ids) != len(outline.characters):
        problems.append("角色编号重复。")
    if len(scene_ids) != len(outline.scenes):
        problems.append("场景编号重复。")
    if len(prop_ids) != len(outline.props):
        problems.append("道具编号重复。")

    for plan in outline.episodes:
        if not plan.characterIds or not plan.sceneIds:
            problems.append(f"第 {plan.number} 集必须列出本集角色和场景。")
        problems.extend(
            f"第 {plan.number} 集引用了不存在的角色 {v}。"
            for v in plan.characterIds
            if v not in character_ids
        )
        problems.extend(
            f"第 {plan.number} 集引用了不存在的场景 {v}。" for v in plan.sceneIds if v not in scene_ids
        )
        problems.extend(
            f"第 {plan.number} 集引用了不存在的道具 {v}。" for v in plan.propIds if v not in prop_ids
        )

    source = ctx.deps.source
    if source.mode == "upload" and not any(plan.sourceLines for plan in outline.episodes):
        problems.append("请至少为有原文依据的集填写 sourceLines，供写作阶段核对原稿。")
    for plan in outline.episodes:
        if any(start > end or end > len(source.lines) or start < 1 for start, end in plan.sourceLines):
            problems.append(f"第 {plan.number} 集的原稿行号范围无效，全文共 {len(source.lines)} 行。")
        covered = sum(end - start + 1 for start, end in plan.sourceLines)
        if covered > MAX_SOURCE_LINES_PER_EPISODE:
            problems.append(
                f"第 {plan.number} 集圈了 {covered} 行原文，超过单集 {MAX_SOURCE_LINES_PER_EPISODE} 行上限。"
            )

    if problems:
        record_gate("plan-episodes", False, problems, {"episodeCount": count})
        raise ModelRetry("分集大纲未通过检查：\n" + "\n".join(f"- {item}" for item in problems))
    record_gate("plan-episodes", True, meta={"episodeCount": count})
    return outline


def verify_episode(ctx: RunContext[EpisodeContext], episode: EpisodeDraft) -> EpisodeDraft:
    target = ctx.deps.settings.secondsPerEpisode
    structural = episode_problems(episode, ctx.deps.plan, ctx.deps.outline, target, check_duration=False)
    duration = episode_duration_problems(episode, target)
    meta = {"episode": ctx.deps.plan.number, "retry": ctx.retry}

    seconds = episode_seconds(episode)
    if (
        not structural
        and duration
        and ctx.retry >= ctx.max_retries
        and target * 0.4 <= seconds <= target * 2.0
    ):
        record_gate("write-episode", True, duration, {**meta, "fallback": "duration_soft_pass"})
        return episode

    problems = structural + duration
    if problems:
        record_gate("write-episode", False, problems, meta)
        raise ModelRetry(
            f"第 {ctx.deps.plan.number} 集未通过剧本质量门，请逐条修改后重新输出全集：\n"
            + "\n".join(f"- {item}" for item in problems)
        )
    record_gate("write-episode", True, meta=meta)
    return episode


def read_source_excerpt(
    ctx: RunContext[EpisodeContext] | RunContext[BeatSheetContext] | RunContext[SceneGroupContext],
    start_line: int,
    end_line: int,
) -> str:
    source = ctx.deps.source
    if source is None:
        raise ModelRetry("当前请求未附带原稿文本，请直接依据大纲和本集计划写作。")
    if not 1 <= start_line <= end_line <= len(source.lines) or end_line - start_line >= 120:
        raise ModelRetry(f"请在原稿 1–{len(source.lines)} 行内指定范围，每次最多 120 行。")
    return source.excerpt(start_line, end_line)


def _scenes_seconds(scenes: Sequence[Scene]) -> float:
    return round(sum(beat_seconds(beat) for scene in scenes for beat in scene.flow), 1)


def _group_hook_position(scenes: Sequence[Scene], hook_beat: tuple[int, int]) -> int | None:
    scene_index, beat_index = hook_beat
    if not 1 <= scene_index <= len(scenes):
        return None
    if not 1 <= beat_index <= len(scenes[scene_index - 1].flow):
        return None
    return sum(len(scene.flow) for scene in scenes[: scene_index - 1]) + beat_index


def _scenes_structural_problems(scenes: Sequence[Scene], outline: Outline) -> list[str]:
    problems: list[str] = []
    valid_characters = {card.id for card in outline.characters}
    valid_scenes = {card.id for card in outline.scenes}
    valid_props = {prop.id for prop in outline.props}

    for scene_index, scene in enumerate(scenes, 1):
        if scene.sceneId not in valid_scenes:
            problems.append(f"第 {scene_index} 场引用了大纲里没有的场景 {scene.sceneId}。")
        for character in scene.characters:
            if character not in valid_characters:
                problems.append(f"第 {scene_index} 场引用了大纲里没有的角色 {character}。")
        for prop in scene.props:
            if prop not in valid_props:
                problems.append(f"第 {scene_index} 场引用了大纲里没有的道具 {prop}。")

        if not any(beat.action is not None for beat in scene.flow):
            problems.append(f"第 {scene_index} 场没有任何动作节拍，纯对白拍不成画面。")

        for beat_index, beat in enumerate(scene.flow, 1):
            where = f"第 {scene_index} 场第 {beat_index} 拍"
            if beat.action is not None:
                if _ACTION_QUOTES.search(beat.action):
                    problems.append(f"{where}的动作里出现了引号台词，请拆成独立台词节拍。")
                continue
            if beat.speaker != "VO" and beat.speaker not in scene.characters:
                problems.append(
                    f"{where}的说话人「{beat.speaker}」不在本场 characters {scene.characters} 里。"
                )
            if line_chars(beat.line or "") > MAX_LINE_CHARS:
                problems.append(
                    f"{where}的台词 {line_chars(beat.line or '')} 字，超过单句 {MAX_LINE_CHARS} 字上限。"
                )
    return problems


def _group_duration_problems(scenes: Sequence[Scene], target: int) -> list[str]:
    seconds = _scenes_seconds(scenes)
    low, high = seconds_range(target, GROUP_DURATION_TOLERANCE)
    actions = sum(1 for scene in scenes for beat in scene.flow if beat.action is not None)
    characters = sum(line_chars(beat.line or "") for scene in scenes for beat in scene.flow)
    if seconds < low - DURATION_SLACK:
        gap = target - seconds
        return [
            f"本组共 {seconds} 秒，短于可交付区间 {low}–{high} 秒（本组目标 {target} 秒）："
            f"约差 {gap:.1f} 秒，请补足约 {ceil(gap * CHARS_PER_SECOND)} 字台词"
            f"（或 {ceil(gap / 2 / ACTION_SECONDS)} 拍动作 + {ceil(gap / 2 * CHARS_PER_SECOND)} 字台词）。"
            f"（当前 {actions} 拍动作、{characters} 字台词）"
        ]
    if seconds > high + DURATION_SLACK:
        excess = seconds - target
        return [
            f"本组共 {seconds} 秒，超出可交付区间 {low}–{high} 秒（本组目标 {target} 秒）："
            f"约多 {excess:.1f} 秒，请压缩约 {ceil(excess / 2 / ACTION_SECONDS)} 拍动作"
            f" + {ceil(excess / 2 * CHARS_PER_SECOND)} 字台词。"
            f"（当前 {actions} 拍动作、{characters} 字台词）"
        ]
    return []


def verify_beat_sheet(ctx: RunContext[BeatSheetContext], sheet: EpisodeBeatSheet) -> EpisodeBeatSheet:
    outline = ctx.deps.outline
    plan = ctx.deps.plan
    target = ctx.deps.settings.secondsPerEpisode
    valid_characters = {card.id for card in outline.characters}
    valid_scenes = {card.id for card in outline.scenes}
    valid_props = {prop.id for prop in outline.props}
    planned_scenes = set(plan.sceneIds)

    structural: list[str] = []
    used_planned = False
    for idx, scene in enumerate(sheet.scenes, 1):
        if scene.sceneId not in valid_scenes:
            structural.append(f"节拍表第 {idx} 场引用了不存在的场景 {scene.sceneId}。")
        if scene.sceneId in planned_scenes:
            used_planned = True
        for char_id in scene.characters:
            if char_id not in valid_characters:
                structural.append(f"节拍表第 {idx} 场引用了不存在的角色 {char_id}。")
        for prop_id in scene.props:
            if prop_id not in valid_props:
                structural.append(f"节拍表第 {idx} 场引用了不存在的道具 {prop_id}。")
    if not used_planned:
        structural.append(f"节拍表未包含本集计划场景 {sorted(planned_scenes)} 中的任何一场。")

    total_planned = sum(scene.targetSeconds for scene in sheet.scenes)
    low, high = seconds_range(target, 0.15)
    duration_err: list[str] = []
    if not (low - DURATION_SLACK <= total_planned <= high + DURATION_SLACK):
        duration_err.append(
            f"各场 targetSeconds 总和为 {total_planned} 秒，偏离目标 {target} 秒（建议 {low}–{high} 秒）。"
        )

    meta = {"episode": plan.number, "retry": ctx.retry}
    if (
        not structural
        and duration_err
        and ctx.retry >= ctx.max_retries
        and target * 0.6 <= total_planned <= target * 1.4
    ):
        record_gate("plan-episode-beats", True, duration_err, {**meta, "fallback": "duration_soft_pass"})
        return sheet

    problems = structural + duration_err
    if problems:
        record_gate("plan-episode-beats", False, problems, meta)
        raise ModelRetry("单集分场节拍表未通过检查：\n" + "\n".join(f"- {item}" for item in problems))
    record_gate("plan-episode-beats", True, meta=meta)
    return sheet


def _group_beat_plans(
    plans: Sequence[SceneBeatPlan], max_group_seconds: int = MAX_GROUP_SECONDS
) -> list[list[SceneBeatPlan]]:
    """统一打包公式：按单组 <= 180s 贪心打包连续场次，120s 自动成 1 组，600s 自动成 3–4 组。"""
    groups: list[list[SceneBeatPlan]] = []
    current: list[SceneBeatPlan] = []
    current_sum = 0
    for item in plans:
        if current and current_sum + item.targetSeconds > max_group_seconds:
            groups.append(current)
            current = [item]
            current_sum = item.targetSeconds
        else:
            current.append(item)
            current_sum += item.targetSeconds
    if current:
        groups.append(current)
    return groups


def verify_scene_group(ctx: RunContext[SceneGroupContext], draft: SceneGroupDraft) -> SceneGroupDraft:
    deps = ctx.deps
    structural = _scenes_structural_problems(draft.scenes, deps.outline)
    hook_errors: list[str] = []
    hook_soft = False
    if deps.group_index == 1 and not deps.is_patch:
        if draft.hookBeat is None:
            structural.append("第 1 组必须提供 hookBeat 指向第 1 场前 3 拍内的开场钩子。")
        else:
            pos = _group_hook_position(draft.scenes, draft.hookBeat)
            if pos is None:
                structural.append(f"hookBeat {list(draft.hookBeat)} 指向不存在的场次或节拍。")
            elif pos > HOOK_WINDOW:
                hook_soft = True
                hook_errors.append(
                    f"开场钩子落在第 {pos} 拍，必须把开场钩子事件提前写进第 1 场前 {HOOK_WINDOW} 拍内，"
                    "再将 hookBeat 指向该拍（如 [1, 1]–[1, 3]，不要只改数字敷衍，"
                    "也不要填结尾悬念 cliff 的位置）。"
                )

    duration_errors = (
        [] if deps.is_patch else _group_duration_problems(draft.scenes, deps.group_target)
    )
    meta = {
        "episode": deps.plan.number,
        "group": deps.group_index,
        "groupTotal": deps.group_total,
        "isPatch": deps.is_patch,
        "retry": ctx.retry,
    }
    actual = _scenes_seconds(draft.scenes)
    if (
        not structural
        and (duration_errors or hook_soft)
        and ctx.retry >= ctx.max_retries
        and (deps.is_patch or deps.group_target * 0.4 <= actual <= deps.group_target * 2.0)
    ):
        record_gate(
            "write-episode",
            True,
            hook_errors + duration_errors,
            {**meta, "fallback": "group_soft_pass"},
        )
        return draft

    problems = structural + hook_errors + duration_errors
    if problems:
        record_gate("write-episode", False, problems, meta)
        raise ModelRetry(
            f"第 {deps.plan.number} 集第 {deps.group_index}/{deps.group_total} 组未通过检查：\n"
            + "\n".join(f"- {item}" for item in problems)
        )
    record_gate("write-episode", True, meta=meta)
    return draft


def finalize(draft: EpisodeDraft, outline: Outline, target: int) -> Episode:
    return Episode(
        **draft.model_dump(),
        targetSeconds=target,
        seconds=episode_seconds(draft),
        script=render_script(draft, outline),
        warnings=episode_warnings(draft, target),
    )


def _cards(outline: Outline, plan: EpisodePlan) -> dict:
    return {
        "characters": [c.model_dump() for c in outline.characters if c.id in plan.characterIds],
        "scenes": [c.model_dump() for c in outline.scenes if c.id in plan.sceneIds],
        "props": [p.model_dump() for p in outline.props if p.id in plan.propIds],
    }


def _episode_budget(target: int) -> dict:
    low, high = seconds_range(target)
    line_beats = max(4, round(target / 6.6))
    action_beats = max(2, round(target / 15))
    return {
        "targetSeconds": target,
        "minSeconds": low,
        "maxSeconds": high,
        "rule": (
            f"{ACTION_SECONDS} 秒 × 动作节拍数 + 台词总字数 ÷ {CHARS_PER_SECOND} 必须落在 "
            f"{low}–{high} 秒；输出前先自己算一遍"
        ),
        "reference": (
            f"{target} 秒建议约 {line_beats} 句台词（每句 20–28 字）加 {action_beats} 个动作节拍"
        ),
        "recommended": {
            "lineBeats": line_beats,
            "actionBeats": action_beats,
        },
        "charsPerSecond": CHARS_PER_SECOND,
        "actionSeconds": ACTION_SECONDS,
        "maxLineChars": MAX_LINE_CHARS,
        "hookWindow": HOOK_WINDOW,
    }


def _bounded_source_excerpts(source: Source, ranges: list[tuple[int, int]]) -> list[str]:
    excerpts: list[str] = []
    remaining = MAX_SOURCE_EXCERPT_CHARS_PER_EPISODE
    for start, end in ranges:
        if remaining <= 0:
            break
        block = source.excerpt(start, end)
        if len(block) <= remaining:
            excerpts.append(block)
            remaining -= len(block)
        else:
            excerpts.append(
                block[:remaining]
                + f"\n…（本段原文第 {start}–{end} 行已按单集字符上限截断，"
                "需要后续细节请调用 read_source_excerpt 回查）"
            )
            remaining = 0
    return excerpts


def _build_beat_planner(model: Model, source: Source | None) -> Agent[BeatSheetContext, EpisodeBeatSheet]:
    planner = Agent(
        model,
        deps_type=BeatSheetContext,
        output_type=PromptedOutput(EpisodeBeatSheet),
        instructions=skill_instructions("plan-episode-beats"),
        model_settings=BEAT_SHEET_MODEL_SETTINGS,
        retries=2,
    )
    planner.output_validator(verify_beat_sheet)
    if source is not None and source.mode == "upload":
        planner.tool(read_source_excerpt)
    return planner


def _build_group_writer(model: Model, source: Source | None) -> Agent[SceneGroupContext, SceneGroupDraft]:
    writer = Agent(
        model,
        deps_type=SceneGroupContext,
        output_type=PromptedOutput(SceneGroupDraft),
        instructions=skill_instructions("write-episode"),
        model_settings=MODEL_SETTINGS,
        retries=3,
    )
    writer.output_validator(verify_scene_group)
    if source is not None and source.mode == "upload":
        writer.tool(read_source_excerpt)
    return writer


def _recommended_scene_count(target: int) -> dict[str, int]:
    low = max(1, round(target / 130))
    high = max(low + 1, min(14, round(target / 60)))
    return {"min": low, "max": high}


def _episode_payload(
    settings: ProjectSettings,
    outline: Outline,
    plan: EpisodePlan,
    source: Source | None,
    previous: Episode | None,
    *,
    previous_draft: Episode | None = None,
    feedback: str = "",
) -> dict:
    target = settings.secondsPerEpisode
    next_plan = next((item for item in outline.episodes if item.number == plan.number + 1), None)
    payload: dict = {
        "task": "plan_episode_beats",
        "settings": settings.model_dump(),
        "mode": source.mode if source is not None else "story",
        "episodeSeconds": target,
        "recommendedSceneCount": _recommended_scene_count(target),
        "continuity": outline.continuity,
        "episode": plan.model_dump(),
        **_cards(outline, plan),
        "previousEpisode": {
            "summary": previous.summary,
            "endingExcerpt": previous.script[-500:],
        }
        if previous
        else None,
        "nextEpisode": next_plan.summary if next_plan else None,
        "source": source.excerpt(1, len(source.lines))
        if source is not None and source.mode == "story"
        else None,
        "sourceExcerpts": _bounded_source_excerpts(source, plan.sourceLines)
        if source is not None and source.mode == "upload"
        else [],
    }
    if previous_draft is not None:
        payload["previousDraft"] = {
            "title": previous_draft.title,
            "summary": previous_draft.summary,
            "script": previous_draft.script,
        }
    note = feedback.strip()
    if note:
        payload["revisionFeedback"] = note
    return payload


async def _write_episode_unified(
    model: Model,
    *,
    settings: ProjectSettings,
    outline: Outline,
    plan: EpisodePlan,
    source: Source | None,
    previous: Episode | None,
    previous_draft: Episode | None = None,
    feedback: str = "",
    usage: RunUsage | None = None,
) -> Episode:
    """
    统一单集写作公式（不区分短集/长集分支）：
    1. 规划单集分场节拍表（Beat Sheet，low 思考）
    2. 按 <=180s/组贪心分组，单集内多轮对话闭环算秒逐组扩写（复用 Prefix Cache）
    3. 全集拼装后若仍短于硬下界，执行 1 次局部补戏 Patch（插在收尾悬念场前，不撕全集）
    """
    target = settings.secondsPerEpisode
    base_payload = _episode_payload(
        settings,
        outline,
        plan,
        source,
        previous,
        previous_draft=previous_draft,
        feedback=feedback,
    )

    beat_planner = _build_beat_planner(model, source)
    beat_result = await beat_planner.run(
        prompt(base_payload),
        deps=BeatSheetContext(plan, outline, source, settings),
        usage=usage,
        usage_limits=SHARED_USAGE_LIMITS,
    )
    sheet = beat_result.output
    groups = _group_beat_plans(sheet.scenes, MAX_GROUP_SECONDS)

    group_writer = _build_group_writer(model, source)
    history: list[ModelMessage] = []
    assembled_scenes: list[Scene] = []
    completed_seconds = 0.0
    hook_beat: tuple[int, int] = (1, 1)

    for g_idx, group_plans in enumerate(groups, 1):
        planned_remaining = sum(
            item.targetSeconds for grp in groups[g_idx - 1 :] for item in grp
        )
        planned_this = sum(item.targetSeconds for item in group_plans)
        remaining_needed = max(30.0, target - completed_seconds)
        if g_idx == len(groups):
            group_target = max(30, min(MAX_GROUP_SECONDS + 60, round(remaining_needed)))
        else:
            scaled = remaining_needed * (planned_this / max(1, planned_remaining))
            group_target = max(30, min(MAX_GROUP_SECONDS + 40, round(scaled)))

        scene_plans_dump = [item.model_dump() for item in group_plans]
        if g_idx == 1:
            turn_payload: dict = {
                **{k: v for k, v in base_payload.items() if k != "task"},
                "task": "write_scene_group",
                "beatSheet": {
                    "title": sheet.title,
                    "summary": sheet.summary,
                    "hook": sheet.hook,
                    "cliff": sheet.cliff,
                },
                "groupIndex": 1,
                "groupTotal": len(groups),
                "isFinalGroup": len(groups) == 1,
                "groupTargetSeconds": group_target,
                "budget": _episode_budget(group_target),
                "scenePlans": scene_plans_dump,
            }
        else:
            turn_payload = {
                "task": "write_scene_group",
                "groupIndex": g_idx,
                "groupTotal": len(groups),
                "isFinalGroup": g_idx == len(groups),
                "completedSeconds": round(completed_seconds, 1),
                "remainingEpisodeSeconds": round(max(0.0, target - completed_seconds), 1),
                "groupTargetSeconds": group_target,
                "budget": _episode_budget(group_target),
                "scenePlans": scene_plans_dump,
                **({"cliff": sheet.cliff} if g_idx == len(groups) else {}),
            }

        turn_prompt_str = prompt(turn_payload)
        turn_result = await group_writer.run(
            turn_prompt_str,
            deps=SceneGroupContext(
                plan=plan,
                outline=outline,
                source=source,
                settings=settings,
                group_index=g_idx,
                group_total=len(groups),
                group_target=group_target,
            ),
            message_history=history or None,
            usage=usage,
            usage_limits=SHARED_USAGE_LIMITS,
        )
        new_msgs = turn_result.new_messages()
        if len(new_msgs) == 2:
            # 一次过审时原样保留完整消息历史，100% 命中 DeepSeek Prefix Cache。
            history = list(turn_result.all_messages())
        else:
            # 若本组经历过校验重试，仅保留干净的最终问答对，避免错误重试废话污染后续轮次。
            history = [
                *history,
                ModelRequest(parts=[UserPromptPart(content=turn_prompt_str)]),
                ModelResponse(parts=[TextPart(content=turn_result.output.model_dump_json())]),
            ]

        if g_idx == 1 and turn_result.output.hookBeat is not None:
            hook_beat = turn_result.output.hookBeat
        assembled_scenes.extend(turn_result.output.scenes)
        completed_seconds = _scenes_seconds(assembled_scenes)

    # 局部补戏 Patch：若全部组拼完仍短于硬下界，不撕全集，仅补 1–2 场插在收尾悬念场之前。
    low_hard, _ = seconds_range(target, HARD_TOLERANCE)
    if completed_seconds < low_hard - DURATION_SLACK:
        gap = max(45, min(MAX_GROUP_SECONDS, round(target - completed_seconds)))
        patch_payload = {
            "task": "patch_short_episode",
            "completedSeconds": round(completed_seconds, 1),
            "targetSeconds": target,
            "gapSeconds": gap,
            "budget": _episode_budget(gap),
            "instruction": (
                f"本集已写完 {completed_seconds:.1f} 秒，距目标 {target} 秒还差约 {gap} 秒。"
                "请不要重复已写场次，额外补写 1–2 场承上启下的冲突推进戏，"
                "程序会自动将其插入收尾悬念场之前。"
            ),
        }
        try:
            patch_result = await group_writer.run(
                prompt(patch_payload),
                deps=SceneGroupContext(
                    plan=plan,
                    outline=outline,
                    source=source,
                    settings=settings,
                    group_index=len(groups) + 1,
                    group_total=len(groups) + 1,
                    group_target=gap,
                    is_patch=True,
                ),
                message_history=history or None,
                usage=usage,
                usage_limits=SHARED_USAGE_LIMITS,
            )
            patch_scenes = patch_result.output.scenes
            if len(assembled_scenes) > 1:
                assembled_scenes = [*assembled_scenes[:-1], *patch_scenes, assembled_scenes[-1]]
            else:
                assembled_scenes = [*assembled_scenes, *patch_scenes]
        except Exception:
            # 局部补戏偶发失败不毁掉已成型的正片，由 finalize 写入时长 warning 透明提示用户。
            pass

    draft = EpisodeDraft(
        number=plan.number,
        title=sheet.title,
        summary=sheet.summary,
        hook=sheet.hook,
        cliff=sheet.cliff,
        hookBeat=hook_beat,
        scenes=assembled_scenes,
    )
    return finalize(draft, outline, target)


def _outline_scale_guide(settings: ProjectSettings, mode: Literal["story", "upload"]) -> dict:
    total_seconds = settings.episodeCount * settings.secondsPerEpisode
    total_minutes = round(total_seconds / 60, 1)
    if total_seconds <= 900:
        guide: dict = {
            "tier": "compact",
            "totalMinutes": total_minutes,
            "recommendedCounts": {"characters": "2–5", "scenes": "3–6", "props": "2–5"},
            "note": (
                "短体量紧凑聚焦，严禁为凑数塞入无关配角或日常杂物；"
                "但每个实际换场的独立物理空间仍须单独建场景。"
            ),
        }
    elif total_seconds <= 2100:
        guide = {
            "tier": "medium",
            "totalMinutes": total_minutes,
            "recommendedCounts": {"characters": "4–8", "scenes": "5–10", "props": "4–8"},
            "note": "中等体量适度展开支线与空间转换，确保每集有清晰的场景推进与核心线索道具。",
        }
    else:
        guide = {
            "tier": "long",
            "totalMinutes": total_minutes,
            "recommendedCounts": {"characters": "5–12", "scenes": "7–14", "props": "5–12"},
            "note": (
                "长体量需足够的人物关系网、独立拍摄空间与关键道具支撑戏量；"
                + (
                    "当前为简短梗概扩写，请围绕主线合理补足功能配角（如同事、邻里、知情人）"
                    "与不同拍摄地点，避免多集困在少数房间干聊。"
                    if mode == "story"
                    else "请忠实拆出原稿中实际出场的功能配角、独立场景与关键线索道具，不要过度合并。"
                )
            ),
        }
    if settings.secondsPerEpisode >= 300:
        guide["scenesPerEpisodeHint"] = (
            "单集达到 5 分钟以上，每集建议安排 3–6 个独立场次切换与多轮冲突递进，避免整集困在单一房间纯对话。"
        )
    return guide


async def generate_script(
    model: Model,
    settings: ProjectSettings,
    source: Source,
    *,
    feedback: str = "",
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
    on_outline: OutlineCallback | None = None,
    on_episode_ready: EpisodeReadyCallback | None = None,
    existing_outline: Outline | None = None,
    existing_episodes: Sequence[Episode] = (),
) -> ScriptResult:
    target = settings.secondsPerEpisode
    total_steps = settings.episodeCount + 2
    note = feedback.strip()

    if existing_outline is not None:
        outline = existing_outline
        await _notify(on_progress, 1, total_steps, "已复用现有大纲，继续补写剩余分集", 15)
    else:
        digest = None
        if source.mode == "upload" and source.chars > DIGEST_THRESHOLD_CHARS:
            await _notify(on_progress, 0, total_steps, "正在浓缩长文原稿", 5)
            digest = await condense_source(model, source, usage=usage)

        planner = Agent(
            model,
            deps_type=OutlineContext,
            output_type=PromptedOutput(Outline),
            instructions=skill_instructions("plan-episodes"),
            model_settings=PLANNING_MODEL_SETTINGS,
            retries=2,
        )
        planner.output_validator(verify_outline)

        plan_payload: dict = {
            "settings": settings.model_dump(),
            "mode": source.mode,
            "episodeSeconds": target,
            "scaleGuide": _outline_scale_guide(settings, source.mode),
            "source": source.excerpt(1, len(source.lines)) if digest is None else None,
            "digest": digest,
        }
        if note:
            plan_payload["revisionFeedback"] = note

        await _notify(on_progress, 1, total_steps, f"正在规划全剧 {settings.episodeCount} 集大纲与世界观", 12)
        draft = await planner.run(
            prompt(plan_payload),
            deps=OutlineContext(settings, source),
            usage=usage,
            usage_limits=SHARED_USAGE_LIMITS,
        )
        outline = draft.output
        if on_outline is not None:
            await on_outline(outline)

    done_by_number = {ep.number: ep for ep in existing_episodes}
    episodes: list[Episode] = []
    total = len(outline.episodes)
    for idx, plan in enumerate(outline.episodes, 1):
        pct = 20 + int((idx - 1) / max(1, total) * 75)
        if plan.number in done_by_number:
            episodes.append(done_by_number[plan.number])
            continue
        await _notify(on_progress, idx + 1, total_steps, f"正在撰写第 {idx}/{total} 集《{plan.title}》", pct)
        previous = episodes[-1] if episodes else None
        ep = await _write_episode_unified(
            model,
            settings=settings,
            outline=outline,
            plan=plan,
            source=source,
            previous=previous,
            feedback=note,
            usage=usage,
        )
        episodes.append(ep)
        if on_episode_ready is not None:
            await on_episode_ready(ep)

    await _notify(on_progress, total_steps, total_steps, "剧本生成完成，正在落库保存", 98)
    return ScriptResult(settings=settings, outline=outline, episodes=episodes)


async def regenerate_episode(
    model: Model,
    script: ScriptResult,
    episode_number: int,
    *,
    source: Source | None = None,
    feedback: str = "",
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> Episode:
    plan = next((item for item in script.outline.episodes if item.number == episode_number), None)
    if plan is None:
        raise ValueError(f"大纲里没有第 {episode_number} 集。")

    by_number = {episode.number: episode for episode in script.episodes}
    previous = by_number.get(episode_number - 1)
    current = by_number.get(episode_number)
    note = (
        feedback.strip()
        or "用户对上一版不满意，请换一种更紧凑、更有戏剧张力的写法重写本集，避免照抄上一版台词。"
    )

    await _notify(on_progress, 1, 2, f"正在重写第 {episode_number} 集《{plan.title}》", 30)
    finalized = await _write_episode_unified(
        model,
        settings=script.settings,
        outline=script.outline,
        plan=plan,
        source=source,
        previous=previous,
        previous_draft=current,
        feedback=note,
        usage=usage,
    )
    await _notify(on_progress, 2, 2, f"第 {episode_number} 集重写完成", 98)
    return finalized


def _next_id(prefix: str, existing: list[str]) -> str:
    highest = max(
        (int(item[1:]) for item in existing if item.startswith(prefix) and item[1:].isdigit()),
        default=0,
    )
    return f"{prefix}{highest + 1:02d}"


def verify_extension(ctx: RunContext[ExtensionContext], ext: EpisodeExtension) -> EpisodeExtension:
    outline = ctx.deps.outline
    expected = ctx.deps.next_number
    problems: list[str] = []
    if ext.plan.number != expected:
        problems.append(f"新增集号必须是第 {expected} 集，实际是第 {ext.plan.number} 集。")

    existing_chars = {item.id for item in outline.characters}
    existing_scenes = {item.id for item in outline.scenes}
    existing_props = {item.id for item in outline.props}

    for label, existing_set, items in (
        ("角色", existing_chars, ext.newCharacters),
        ("场景", existing_scenes, ext.newScenes),
        ("道具", existing_props, ext.newProps),
    ):
        new_ids = [item.id for item in items]
        if len(set(new_ids)) != len(new_ids):
            problems.append(f"新增{label}编号重复：{new_ids}。")
        overlap = [item_id for item_id in new_ids if item_id in existing_set]
        if overlap:
            problems.append(f"新增{label}编号与已有编号冲突：{overlap}。")

    all_chars = existing_chars | {item.id for item in ext.newCharacters}
    all_scenes = existing_scenes | {item.id for item in ext.newScenes}
    all_props = existing_props | {item.id for item in ext.newProps}

    if not ext.plan.characterIds or not ext.plan.sceneIds:
        problems.append(f"第 {expected} 集必须列出本集角色 characterIds 和场景 sceneIds。")
    problems.extend(
        f"第 {expected} 集引用了不存在的角色 {v}。" for v in ext.plan.characterIds if v not in all_chars
    )
    problems.extend(
        f"第 {expected} 集引用了不存在的场景 {v}。" for v in ext.plan.sceneIds if v not in all_scenes
    )
    problems.extend(
        f"第 {expected} 集引用了不存在的道具 {v}。" for v in ext.plan.propIds if v not in all_props
    )

    if problems:
        record_gate("plan-episodes", False, problems, {"appendEpisode": expected})
        raise ModelRetry("新增分集计划未通过检查：\n" + "\n".join(f"- {item}" for item in problems))
    record_gate("plan-episodes", True, meta={"appendEpisode": expected})
    return ext


async def append_episode(
    model: Model,
    script: ScriptResult,
    *,
    source: Source | None = None,
    feedback: str = "",
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScriptResult:
    outline = script.outline
    next_number = max((plan.number for plan in outline.episodes), default=len(script.episodes)) + 1
    if next_number > 99 and any(len(c) >= 99 for c in (outline.characters, outline.scenes, outline.props)):
        raise ValueError("资产编号已达上限，无法继续追加。")

    previous = max(script.episodes, key=lambda ep: ep.number) if script.episodes else None
    planner = Agent(
        model,
        deps_type=ExtensionContext,
        output_type=PromptedOutput(EpisodeExtension),
        instructions=skill_instructions("append-episode"),
        model_settings=BEAT_SHEET_MODEL_SETTINGS,
        retries=2,
    )
    planner.output_validator(verify_extension)

    direction = feedback.strip()
    plan_payload: dict = {
        "settings": script.settings.model_dump(),
        "nextEpisodeNumber": next_number,
        "nextIds": {
            "character": _next_id("C", [item.id for item in outline.characters]),
            "scene": _next_id("S", [item.id for item in outline.scenes]),
            "prop": _next_id("P", [item.id for item in outline.props]),
        },
        "outline": outline.model_dump(),
        "previousEpisode": {
            "number": previous.number,
            "title": previous.title,
            "summary": previous.summary,
            "cliff": previous.cliff,
            "endingExcerpt": previous.script[-600:],
        }
        if previous
        else None,
        "direction": direction,
    }
    await _notify(on_progress, 1, 3, f"正在规划续写第 {next_number} 集大纲", 20)
    planned = await planner.run(
        prompt(plan_payload),
        deps=ExtensionContext(outline, next_number),
        usage=usage,
        usage_limits=SHARED_USAGE_LIMITS,
    )
    ext = planned.output

    continuity = outline.continuity
    if ext.continuityUpdate.strip():
        continuity = f"{continuity}\n{ext.continuityUpdate.strip()}"

    updated_outline = Outline(
        continuity=continuity,
        world=outline.world,
        characters=[*outline.characters, *ext.newCharacters],
        scenes=[*outline.scenes, *ext.newScenes],
        props=[*outline.props, *ext.newProps],
        episodes=[*outline.episodes, ext.plan],
    )
    updated_settings = ProjectSettings.model_validate(
        {
            **script.settings.model_dump(),
            "episodeCount": max(script.settings.episodeCount + 1, next_number),
        }
    )

    await _notify(on_progress, 2, 3, f"正在撰写第 {next_number} 集《{ext.plan.title}》", 55)
    new_episode = await _write_episode_unified(
        model,
        settings=updated_settings,
        outline=updated_outline,
        plan=ext.plan,
        source=source,
        previous=previous,
        feedback=direction,
        usage=usage,
    )
    await _notify(on_progress, 3, 3, f"第 {next_number} 集续写完成", 98)
    return ScriptResult(
        settings=updated_settings,
        outline=updated_outline,
        episodes=[*script.episodes, new_episode],
    )
