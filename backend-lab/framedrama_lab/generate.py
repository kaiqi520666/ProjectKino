import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.models import Model

from .deepseek import MODEL_SETTINGS
from .gates import log_progress, record_gate
from .schema import (
    Character, Episode, EpisodeDraft, EpisodePlan, Outline, ProjectSettings, PropCard, Record,
    SceneCard, ScriptResult, Text, World,
)
from .timing import (
    ACTION_SECONDS, CHARS_PER_SECOND, HOOK_WINDOW, MAX_LINE_CHARS,
    episode_duration_problems, episode_problems, episode_seconds, episode_warnings,
    render_script, script_length, seconds_range,
)

__all__ = [
    "Source", "condense_source", "generate_script", "regenerate_episode", "append_episode", "prompt",
    "script_length", "skill_instructions", "chunk_ranges",
]

DIGEST_THRESHOLD_CHARS = 24_000
CHUNK_CHARS = 6_000
MAX_SOURCE_LINES_PER_EPISODE = 1200

_CHAPTER_HEADING = re.compile(r"^\s*(第[〇零一二三四五六七八九十百千万0-9]+[章回节][^\n]{0,40})\s*$")


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
        "plan-episodes", "write-episode", "append-episode", "condense-source", "analyze-assets", "plan-storyboard",
    ],
) -> str:
    path = Path(__file__).with_name("skills") / name / "SKILL.md"
    return path.read_text(encoding="utf-8").split("\n---\n", 1)[1].strip()


def prompt(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def chunk_ranges(lines: list[str]) -> list[tuple[int, int]]:
    """按章节标题切块，没有章节标题时按长度切。返回 1 起算的闭区间行号。"""
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


async def condense_source(model: Model, source: Source) -> list[dict]:
    """长篇小说先分块摘要，规划阶段读摘要而不是全文。"""
    agent = Agent(
        model, output_type=PromptedOutput(ChunkDigest),
        instructions=skill_instructions("condense-source"), model_settings=MODEL_SETTINGS, retries=1,
    )
    limiter = asyncio.Semaphore(4)

    async def summarize(bounds: tuple[int, int]) -> dict:
        start, end = bounds
        async with limiter:
            result = await agent.run(prompt({"lines": [start, end], "text": source.excerpt(start, end)}))
        return {"lines": [start, end], "summary": result.output.summary, "events": result.output.events}

    return list(await asyncio.gather(*(summarize(bounds) for bounds in chunk_ranges(source.lines))))


_ERA_DYNASTY = re.compile(r"(夏|商|周|秦|汉|三国|晋|南北朝|隋|唐|五代|宋|辽|金|元|明|清|民国)")
_ERA_YEAR = re.compile(r"\d{3,4}\s*年|\d{1,2}\s*年代")
_VAGUE_ERA = {"古代", "古装", "架空", "某朝", "未来", "现代", "年代"}


def world_problems(world: World | None) -> list[str]:
    """世界基准只查“够不够具体”，不评判文学性。"""
    if world is None:
        return ["缺少世界基准 world，请给出 kind、era 和 baseline，用于统一全剧的年代、建筑、材质与器物。"]

    problems: list[str] = []
    era = world.era.strip()
    if era in _VAGUE_ERA:
        problems.append(f"era「{era}」太笼统，请写成一个具体的时空坐标。")
    elif world.kind == "historical" and not (_ERA_DYNASTY.search(era) or _ERA_YEAR.search(era)):
        problems.append("历史题材的 era 必须落在具体朝代或年份上。")
    elif world.kind == "modern" and not (
        _ERA_YEAR.search(era) or re.search(r"(现代|当代|都市|乡村|民国|学校|医院|警局|城|镇|村)", era)
    ):
        problems.append("现代题材的 era 请写明年份、当代、都市或乡村这类可画的时代锚。")
    elif world.kind == "scifi" and not (_ERA_YEAR.search(era) or re.search(r"(星|城|站|殖民地|轨道|月球|火星|赛博)", era)):
        problems.append("科幻题材的 era 必须带年份或具体地点，例如「2087 年，新九龙立体城」。")
    elif world.kind == "fantasy" and not re.search(r"(风格|架空|世界|大陆|山门|仙门|秘境|王朝)", era):
        problems.append("架空/奇幻题材的 era 请写成「某朝风格 + 自设世界」或一个具体的世界名。")

    baseline = world.baseline.strip()
    if len(baseline) < 20:
        problems.append("baseline 至少 20 字，写清建筑、材质、光源和技术基准。")
    elif not re.search(r"(无|没有|禁)", baseline):
        problems.append("baseline 必须写明这个世界没有什么（用「无/没有/禁止」列出排除项）。")
    return problems


def verify_outline(ctx: RunContext[OutlineContext], outline: Outline) -> Outline:
    count = ctx.deps.settings.episodeCount
    if len(outline.episodes) != count or any(
        episode.number != number for number, episode in enumerate(outline.episodes, 1)
    ):
        reason = f"请按顺序返回恰好 {count} 集，集号必须从 1 连续到 {count}。"
        record_gate("plan-episodes", False, [reason], {"episodeCount": count})
        raise ModelRetry(reason)

    problems: list[str] = []
    problems.extend(world_problems(outline.world))
    character_ids = [character.id for character in outline.characters]
    scene_ids = [card.id for card in outline.scenes]
    prop_ids = [prop.id for prop in outline.props]
    for label, ids in (("角色", character_ids), ("场景", scene_ids), ("道具", prop_ids)):
        if len(set(ids)) != len(ids):
            problems.append(f"{label}编号重复：{ids}。")

    for plan in outline.episodes:
        if not plan.characterIds or not plan.sceneIds:
            problems.append(f"第 {plan.number} 集必须列出本集角色 characterIds 和场景 sceneIds。")
        problems.extend(f"第 {plan.number} 集引用了不存在的角色 {value}。" for value in plan.characterIds
                        if value not in character_ids)
        problems.extend(f"第 {plan.number} 集引用了不存在的场景 {value}。" for value in plan.sceneIds
                        if value not in scene_ids)
        problems.extend(f"第 {plan.number} 集引用了不存在的道具 {value}。" for value in plan.propIds
                        if value not in prop_ids)

    source = ctx.deps.source
    if source.mode == "upload" and not any(plan.sourceLines for plan in outline.episodes):
        problems.append("请至少为有原文依据的集填写 sourceLines，供写作阶段核对原稿。")
    for plan in outline.episodes:
        if any(start > end or end > len(source.lines) or start < 1 for start, end in plan.sourceLines):
            problems.append(f"第 {plan.number} 集的原稿行号范围无效，全文共 {len(source.lines)} 行。")
        covered = sum(end - start + 1 for start, end in plan.sourceLines)
        if covered > MAX_SOURCE_LINES_PER_EPISODE:
            problems.append(
                f"第 {plan.number} 集圈了 {covered} 行原文，超过单集 {MAX_SOURCE_LINES_PER_EPISODE} 行上限，"
                "请只保留主线依据。"
            )

    if problems:
        record_gate("plan-episodes", False, problems, {"episodeCount": count})
        message = "分集大纲未通过检查：\n" + "\n".join(f"- {item}" for item in problems)
        print(f"[plan-episodes] 重试原因：\n{message}", file=sys.stderr)
        raise ModelRetry(message)
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
        print(
            f"[write-episode] 第 {ctx.deps.plan.number} 集末次重试仅剩时长偏差（{seconds} 秒），已降级放行并记入提示。",
            file=sys.stderr,
        )
        return episode

    problems = structural + duration
    if problems:
        record_gate("write-episode", False, problems, meta)
        message = (
            f"第 {ctx.deps.plan.number} 集未通过剧本质量门，请逐条修改后重新输出全集：\n"
            + "\n".join(f"- {item}" for item in problems)
        )
        print(f"[write-episode] {message}", file=sys.stderr)
        raise ModelRetry(message)
    record_gate("write-episode", True, meta=meta)
    return episode


def read_source_excerpt(ctx: RunContext[EpisodeContext], start_line: int, end_line: int) -> str:
    """Read an inclusive, 1-indexed excerpt of the submitted story (up to 120 lines)."""
    source = ctx.deps.source
    if source is None:
        raise ModelRetry("当前请求未附带原稿文本，请直接依据大纲和本集计划写作。")
    if not 1 <= start_line <= end_line <= len(source.lines) or end_line - start_line >= 120:
        raise ModelRetry(f"请在原稿 1–{len(source.lines)} 行内指定范围，每次最多 120 行。")
    return source.excerpt(start_line, end_line)


def finalize(draft: EpisodeDraft, outline: Outline, target: int) -> Episode:
    warnings = episode_warnings(draft, target)
    if warnings:
        print(f"[write-episode] 第 {draft.number} 集提示：" + "；".join(warnings), file=sys.stderr)
    return Episode(
        **draft.model_dump(),
        targetSeconds=target,
        seconds=episode_seconds(draft),
        script=render_script(draft, outline),
        warnings=warnings,
    )


def _cards(outline: Outline, plan: EpisodePlan) -> dict:
    return {
        "characters": [character.model_dump() for character in outline.characters
                       if character.id in plan.characterIds],
        "scenes": [card.model_dump() for card in outline.scenes if card.id in plan.sceneIds],
        "props": [prop.model_dump() for prop in outline.props if prop.id in plan.propIds],
    }


def _episode_budget(target: int) -> dict:
    low, high = seconds_range(target)
    return {
        "targetSeconds": target,
        "minSeconds": low,
        "maxSeconds": high,
        "rule": f"{ACTION_SECONDS} 秒 × 动作节拍数 + 台词总字数 ÷ {CHARS_PER_SECOND} 必须落在 "
                f"{low}–{high} 秒；输出前先自己算一遍",
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
        model, deps_type=EpisodeContext, output_type=PromptedOutput(EpisodeDraft),
        instructions=skill_instructions("write-episode"), model_settings=MODEL_SETTINGS,
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
        } if previous else None,
        "nextEpisode": next_plan.summary if next_plan else None,
        "source": source.excerpt(1, len(source.lines)) if source is not None and source.mode == "story" else None,
        "sourceExcerpts": [source.excerpt(start, end) for start, end in plan.sourceLines]
        if source is not None and source.mode == "upload" else [],
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
    model: Model, settings: ProjectSettings, source: Source, feedback: str = "",
) -> ScriptResult:
    target = settings.secondsPerEpisode
    digest = None
    if source.mode == "upload" and source.chars > DIGEST_THRESHOLD_CHARS:
        t0 = time.perf_counter()
        log_progress("condense-source", f"长文共 {source.chars} 字，开始分块摘要...")
        digest = await condense_source(model, source)
        log_progress("condense-source", f"分块摘要完成：共 {len(digest)} 块（{time.perf_counter() - t0:.1f}s）")

    planner = Agent(
        model, deps_type=OutlineContext, output_type=PromptedOutput(Outline),
        instructions=skill_instructions("plan-episodes"), model_settings=MODEL_SETTINGS,
        retries=2,
    )
    planner.output_validator(verify_outline)
    writer = _build_writer(model, source)

    project = settings.model_dump()
    note = feedback.strip()
    plan_payload: dict = {
        "settings": project,
        "mode": source.mode,
        "episodeSeconds": target,
        "source": source.excerpt(1, len(source.lines)) if digest is None else None,
        "digest": digest,
    }
    if note:
        plan_payload["revisionFeedback"] = note
    t_plan = time.perf_counter()
    log_progress("plan-episodes", f"开始规划全剧大纲：《{settings.name}》· {settings.episodeCount} 集...")
    draft = await planner.run(prompt(plan_payload), deps=OutlineContext(settings, source))
    outline = draft.output
    log_progress(
        "plan-episodes",
        f"大纲规划完成：角色 {len(outline.characters)} / 场景 {len(outline.scenes)} / 道具 {len(outline.props)}（{time.perf_counter() - t_plan:.1f}s）",
    )

    episodes: list[Episode] = []
    total = len(outline.episodes)
    for index, plan in enumerate(outline.episodes, 1):
        previous = episodes[-1] if episodes else None
        t_ep = time.perf_counter()
        log_progress("write-episode", f"开始撰写第 {index}/{total} 集《{plan.title}》...")
        result = await writer.run(
            prompt(_episode_payload(settings, outline, plan, source, previous, feedback=note)),
            deps=EpisodeContext(plan, outline, source, settings),
        )
        finalized = finalize(result.output, outline, target)
        episodes.append(finalized)
        log_progress(
            "write-episode",
            f"第 {index}/{total} 集《{finalized.title}》完成：估算 {finalized.seconds}s（{time.perf_counter() - t_ep:.1f}s）",
        )

    return ScriptResult(settings=settings, outline=outline, episodes=episodes)


async def regenerate_episode(
    model: Model,
    script: ScriptResult,
    episode_number: int,
    source: Source | None = None,
    feedback: str = "",
) -> Episode:
    """沿用既有大纲与编号体系，仅重写指定单集剧本。"""
    plan = next((item for item in script.outline.episodes if item.number == episode_number), None)
    if plan is None:
        raise ValueError(f"大纲里没有第 {episode_number} 集。")

    by_number = {episode.number: episode for episode in script.episodes}
    previous = by_number.get(episode_number - 1)
    current = by_number.get(episode_number)
    note = feedback.strip() or "用户对上一版不满意，请换一种更紧凑、更有戏剧张力的写法重写本集，避免照抄上一版台词。"

    writer = _build_writer(model, source)
    t_ep = time.perf_counter()
    log_progress("write-episode", f"开始重写第 {episode_number} 集《{plan.title}》...")
    result = await writer.run(
        prompt(_episode_payload(
            script.settings, script.outline, plan, source, previous,
            previous_draft=current, feedback=note,
        )),
        deps=EpisodeContext(plan, script.outline, source, script.settings),
    )
    finalized = finalize(result.output, script.outline, script.settings.secondsPerEpisode)
    log_progress(
        "write-episode",
        f"第 {episode_number} 集《{finalized.title}》重写完成：估算 {finalized.seconds}s（{time.perf_counter() - t_ep:.1f}s）",
    )
    return finalized


def _next_id(prefix: str, existing: list[str]) -> str:
    highest = max((int(item[1:]) for item in existing if item.startswith(prefix) and item[1:].isdigit()), default=0)
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
    problems.extend(f"第 {expected} 集引用了不存在的角色 {value}。" for value in ext.plan.characterIds if value not in all_chars)
    problems.extend(f"第 {expected} 集引用了不存在的场景 {value}。" for value in ext.plan.sceneIds if value not in all_scenes)
    problems.extend(f"第 {expected} 集引用了不存在的道具 {value}。" for value in ext.plan.propIds if value not in all_props)

    if problems:
        record_gate("plan-episodes", False, problems, {"appendEpisode": expected})
        message = "新增分集计划未通过检查：\n" + "\n".join(f"- {item}" for item in problems)
        print(f"[append-episode] 重试原因：\n{message}", file=sys.stderr)
        raise ModelRetry(message)
    record_gate("plan-episodes", True, meta={"appendEpisode": expected})
    return ext


async def append_episode(
    model: Model,
    script: ScriptResult,
    source: Source | None = None,
    feedback: str = "",
) -> ScriptResult:
    """在既有大纲与全剧编号基础上续写新的一集，返回更新后的 ScriptResult。"""
    outline = script.outline
    next_number = max(
        (plan.number for plan in outline.episodes),
        default=len(script.episodes),
    ) + 1
    if next_number > 99 and any(
        len(collection) >= 99 for collection in (outline.characters, outline.scenes, outline.props)
    ):
        raise ValueError("资产编号已达上限，无法继续追加。")

    previous = max(script.episodes, key=lambda ep: ep.number) if script.episodes else None
    planner = Agent(
        model, deps_type=ExtensionContext, output_type=PromptedOutput(EpisodeExtension),
        instructions=skill_instructions("append-episode"), model_settings=MODEL_SETTINGS,
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
        } if previous else None,
        "direction": direction,
    }
    t_plan = time.perf_counter()
    log_progress("append-episode", f"开始规划续写第 {next_number} 集...")
    planned = await planner.run(prompt(plan_payload), deps=ExtensionContext(outline, next_number))
    ext = planned.output
    log_progress(
        "append-episode",
        f"第 {next_number} 集规划完成《{ext.plan.title}》：新增角色 {len(ext.newCharacters)} / 场景 {len(ext.newScenes)} / 道具 {len(ext.newProps)}（{time.perf_counter() - t_plan:.1f}s）",
    )

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
    updated_settings = ProjectSettings.model_validate({
        **script.settings.model_dump(),
        "episodeCount": max(script.settings.episodeCount + 1, next_number),
    })

    writer = _build_writer(model, source)
    t_ep = time.perf_counter()
    log_progress("write-episode", f"开始撰写续写第 {next_number} 集《{ext.plan.title}》...")
    written = await writer.run(
        prompt(_episode_payload(updated_settings, updated_outline, ext.plan, source, previous, feedback=direction)),
        deps=EpisodeContext(ext.plan, updated_outline, source, updated_settings),
    )
    new_episode = finalize(written.output, updated_outline, updated_settings.secondsPerEpisode)
    log_progress(
        "write-episode",
        f"续写第 {next_number} 集《{new_episode.title}》完成：估算 {new_episode.seconds}s（{time.perf_counter() - t_ep:.1f}s）",
    )
    return ScriptResult(
        settings=updated_settings,
        outline=updated_outline,
        episodes=[*script.episodes, new_episode],
    )


def outline_seconds(outline: Outline) -> dict[str, int]:
    """角色/场景/道具的规模，供命令行汇报。"""
    return {"characters": len(outline.characters), "scenes": len(outline.scenes), "props": len(outline.props)}


def episode_line_count(episode: Episode) -> int:
    return sum(1 for scene in episode.scenes for beat in scene.flow if beat.line is not None)
