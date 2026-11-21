import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext, RunUsage
from pydantic_ai.models import Model

from app.modules.llm_engine.gates import record_gate
from app.modules.llm_engine.provider import MODEL_SETTINGS
from app.modules.llm_engine.schema import (
    Character,
    Episode,
    EpisodeDraft,
    EpisodePlan,
    Outline,
    ProjectSettings,
    PropCard,
    Record,
    SceneCard,
    ScriptResult,
    Text,
    World,
)
from app.modules.llm_engine.timing import (
    ACTION_SECONDS,
    CHARS_PER_SECOND,
    HOOK_WINDOW,
    MAX_LINE_CHARS,
    episode_duration_problems,
    episode_problems,
    episode_seconds,
    episode_warnings,
    render_script,
    seconds_range,
)

ProgressCallback = Callable[[int, int, str, int], Awaitable[None]]

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
DIGEST_THRESHOLD_CHARS = 24_000
CHUNK_CHARS = 6_000
MAX_SOURCE_LINES_PER_EPISODE = 1200

_CHAPTER_HEADING = re.compile(r"^\s*(第[〇零一二三四五六七八九十百千万0-9]+[章回节][^\n]{0,40})\s*$")
_ERA_DYNASTY = re.compile(r"(夏|商|周|秦|汉|三国|晋|南北朝|隋|唐|五代|宋|辽|金|元|明|清|民国)")
_ERA_YEAR = re.compile(r"\d{3,4}\s*年|\d{1,2}\s*年代")
_VAGUE_ERA = {"古代", "古装", "架空", "某朝", "未来", "现代", "年代"}


@dataclass(frozen=True)
class Source:
    mode: Literal["story", "upload"]
    lines: list[str]

    @classmethod
    def from_text(cls, mode: Literal["story", "upload"], text: str) -> "Source":
        if not text.strip():
            raise ValueError("故事内容不能为空。")
        return cls(mode, text.splitlines())

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


class ChunkDigest(Record):
    summary: Text
    events: Annotated[list[Text], Field(min_length=1)]


class EpisodeExtension(Record):
    plan: EpisodePlan
    newCharacters: list[Character] = Field(default_factory=list)
    newScenes: list[SceneCard] = Field(default_factory=list)
    newProps: list[PropCard] = Field(default_factory=list)
    continuityUpdate: str = ""


def skill_instructions(
    name: Literal[
        "plan-episodes",
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


def read_source_excerpt(ctx: RunContext[EpisodeContext], start_line: int, end_line: int) -> str:
    source = ctx.deps.source
    if source is None:
        raise ModelRetry("当前请求未附带原稿文本，请直接依据大纲和本集计划写作。")
    if not 1 <= start_line <= end_line <= len(source.lines) or end_line - start_line >= 120:
        raise ModelRetry(f"请在原稿 1–{len(source.lines)} 行内指定范围，每次最多 120 行。")
    return source.excerpt(start_line, end_line)


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
    return {
        "targetSeconds": target,
        "minSeconds": low,
        "maxSeconds": high,
        "rule": (
            f"{ACTION_SECONDS} 秒 × 动作节拍数 + 台词总字数 ÷ {CHARS_PER_SECOND} 必须落在 "
            f"{low}–{high} 秒；输出前先自己算一遍"
        ),
        "reference": "120 秒一集通常 18–22 句台词加 8–12 个动作节拍",
        "recommended": {
            "lineBeats": max(6, round(target / 6.6)),
            "actionBeats": max(3, round(target / 15)),
        },
        "charsPerSecond": CHARS_PER_SECOND,
        "actionSeconds": ACTION_SECONDS,
        "maxLineChars": MAX_LINE_CHARS,
        "hookWindow": HOOK_WINDOW,
    }


def _build_writer(model: Model, source: Source | None) -> Agent[EpisodeContext, EpisodeDraft]:
    writer = Agent(
        model,
        deps_type=EpisodeContext,
        output_type=PromptedOutput(EpisodeDraft),
        instructions=skill_instructions("write-episode"),
        model_settings=MODEL_SETTINGS,
        retries=5,
    )
    writer.output_validator(verify_episode)
    if source is not None and source.mode == "upload":
        writer.tool(read_source_excerpt)
    return writer


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
        "settings": settings.model_dump(),
        "mode": source.mode if source is not None else "story",
        "episodeSeconds": target,
        "budget": _episode_budget(target),
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
        "sourceExcerpts": [source.excerpt(start, end) for start, end in plan.sourceLines]
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


async def generate_script(
    model: Model,
    settings: ProjectSettings,
    source: Source,
    *,
    feedback: str = "",
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScriptResult:
    target = settings.secondsPerEpisode
    total_steps = settings.episodeCount + 2
    digest = None
    if source.mode == "upload" and source.chars > DIGEST_THRESHOLD_CHARS:
        await _notify(on_progress, 0, total_steps, "正在浓缩长文原稿", 5)
        digest = await condense_source(model, source, usage=usage)

    planner = Agent(
        model,
        deps_type=OutlineContext,
        output_type=PromptedOutput(Outline),
        instructions=skill_instructions("plan-episodes"),
        model_settings=MODEL_SETTINGS,
        retries=2,
    )
    planner.output_validator(verify_outline)
    writer = _build_writer(model, source)

    note = feedback.strip()
    plan_payload: dict = {
        "settings": settings.model_dump(),
        "mode": source.mode,
        "episodeSeconds": target,
        "source": source.excerpt(1, len(source.lines)) if digest is None else None,
        "digest": digest,
    }
    if note:
        plan_payload["revisionFeedback"] = note

    await _notify(on_progress, 1, total_steps, f"正在规划全剧 {settings.episodeCount} 集大纲与世界观", 12)
    draft = await planner.run(prompt(plan_payload), deps=OutlineContext(settings, source), usage=usage)
    outline = draft.output

    episodes: list[Episode] = []
    total = len(outline.episodes)
    for idx, plan in enumerate(outline.episodes, 1):
        pct = 20 + int((idx - 1) / max(1, total) * 75)
        await _notify(on_progress, idx + 1, total_steps, f"正在撰写第 {idx}/{total} 集《{plan.title}》", pct)
        previous = episodes[-1] if episodes else None
        result = await writer.run(
            prompt(_episode_payload(settings, outline, plan, source, previous, feedback=note)),
            deps=EpisodeContext(plan, outline, source, settings),
            usage=usage,
        )
        episodes.append(finalize(result.output, outline, target))

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
    writer = _build_writer(model, source)
    result = await writer.run(
        prompt(
            _episode_payload(
                script.settings,
                script.outline,
                plan,
                source,
                previous,
                previous_draft=current,
                feedback=note,
            )
        ),
        deps=EpisodeContext(plan, script.outline, source, script.settings),
        usage=usage,
    )
    finalized = finalize(result.output, script.outline, script.settings.secondsPerEpisode)
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
        model_settings=MODEL_SETTINGS,
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
        prompt(plan_payload), deps=ExtensionContext(outline, next_number), usage=usage
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
    writer = _build_writer(model, source)
    written = await writer.run(
        prompt(
            _episode_payload(
                updated_settings, updated_outline, ext.plan, source, previous, feedback=direction
            )
        ),
        deps=EpisodeContext(ext.plan, updated_outline, source, updated_settings),
        usage=usage,
    )
    new_episode = finalize(written.output, updated_outline, updated_settings.secondsPerEpisode)
    await _notify(on_progress, 3, 3, f"第 {next_number} 集续写完成", 98)
    return ScriptResult(
        settings=updated_settings,
        outline=updated_outline,
        episodes=[*script.episodes, new_episode],
    )
