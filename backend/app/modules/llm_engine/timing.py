import re
from math import ceil

from app.modules.llm_engine.schema import Beat, EpisodeDraft, EpisodePlan, Outline

CHARS_PER_SECOND = 4.5
ACTION_SECONDS = 2.5
TOLERANCE = 0.15
HARD_TOLERANCE = 0.25
DURATION_SLACK = 2.0
MAX_LINE_CHARS = 35
HOOK_WINDOW = 3

_QUOTES = re.compile(r"[「」『』“”\"]")
_CN_DIGITS = "零一二三四五六七八九"


def chinese_number(value: int) -> str:
    if value < 10:
        return _CN_DIGITS[value]
    if value < 20:
        return "十" + (_CN_DIGITS[value % 10] if value % 10 else "")
    if value < 100:
        return _CN_DIGITS[value // 10] + "十" + (_CN_DIGITS[value % 10] if value % 10 else "")
    return str(value)


def line_chars(line: str) -> int:
    return sum(not character.isspace() for character in line)


def script_length(script: str) -> int:
    return line_chars(script)


def beat_seconds(beat: Beat) -> float:
    return line_chars(beat.line) / CHARS_PER_SECOND if beat.line is not None else ACTION_SECONDS


def episode_seconds(episode: EpisodeDraft) -> float:
    return round(sum(beat_seconds(beat) for scene in episode.scenes for beat in scene.flow), 1)


def seconds_range(target: int, tolerance: float = TOLERANCE) -> tuple[float, float]:
    return round(target * (1 - tolerance), 1), round(target * (1 + tolerance), 1)


def _hook_position(episode: EpisodeDraft) -> int | None:
    scene_index, beat_index = episode.hookBeat
    if scene_index > len(episode.scenes) or beat_index > len(episode.scenes[scene_index - 1].flow):
        return None
    return sum(len(scene.flow) for scene in episode.scenes[: scene_index - 1]) + beat_index


def episode_duration_problems(episode: EpisodeDraft, target: int) -> list[str]:
    seconds = episode_seconds(episode)
    low, high = seconds_range(target, HARD_TOLERANCE)
    actions = sum(1 for scene in episode.scenes for beat in scene.flow if beat.action is not None)
    characters = sum(line_chars(beat.line or "") for scene in episode.scenes for beat in scene.flow)
    if seconds < low - DURATION_SLACK:
        gap_target = target - seconds
        min_gap = low - seconds
        return [
            f"全集 {seconds} 秒，短于可交付区间 {low}–{high} 秒（目标 {target} 秒）："
            f"距离目标还差约 {gap_target:.1f} 秒（至少需补 {min_gap:.1f} 秒）。"
            f"请直接多展开 1–2 个戏剧冲突回合，一次性补足约 {ceil(gap_target * CHARS_PER_SECOND)} 字台词"
            f"（或补 {ceil(gap_target / 2 / ACTION_SECONDS)} 个动作节拍 + "
            f"{ceil(gap_target / 2 * CHARS_PER_SECOND)} 字台词），"
            f"不要只补一两句。（当前 {actions} 个动作节拍、{characters} 字台词）"
        ]
    if seconds > high + DURATION_SLACK:
        excess_target = seconds - target
        min_excess = seconds - high
        return [
            f"全集 {seconds} 秒，超出可交付区间 {low}–{high} 秒（目标 {target} 秒）："
            f"比目标多出约 {excess_target:.1f} 秒（至少需压 {min_excess:.1f} 秒），"
            f"请精简过场或合并冗余寒暄，一次压掉约 {ceil(excess_target / 2 / ACTION_SECONDS)} 个动作节拍"
            f" + {ceil(excess_target / 2 * CHARS_PER_SECOND)} 字台词。"
            f"（当前 {actions} 个动作节拍、{characters} 字台词）"
        ]
    return []


def episode_problems(
    episode: EpisodeDraft,
    plan: EpisodePlan,
    outline: Outline,
    target: int,
    *,
    check_duration: bool = True,
) -> list[str]:
    problems: list[str] = []
    if episode.number != plan.number:
        problems.append(f"集号必须是第 {plan.number} 集，实际是第 {episode.number} 集。")

    cards = {card.id: card for card in outline.scenes}
    cast = {character.id for character in outline.characters}
    planned_cast = set(plan.characterIds)
    planned_scenes = set(plan.sceneIds)
    used_planned_scene = False

    for index, scene in enumerate(episode.scenes, 1):
        card = cards.get(scene.sceneId)
        if card is None:
            problems.append(f"第 {index} 场的 sceneId「{scene.sceneId}」不在大纲场景里。")
        elif scene.sceneId not in planned_scenes:
            problems.append(
                f"第 {index} 场用了大纲没给本集安排的场景「{scene.sceneId}」，"
                f"本集场景是 {sorted(planned_scenes)}。"
            )
        else:
            used_planned_scene = True

        unknown = [character for character in scene.characters if character not in cast]
        if unknown:
            problems.append(f"第 {index} 场的角色 {unknown} 不在大纲角色表里。")
        unplanned = [character for character in scene.characters if character not in planned_cast]
        if unplanned:
            problems.append(f"第 {index} 场的角色 {unplanned} 没列进本集 characterIds。")

        actions = [beat for beat in scene.flow if beat.action is not None]
        if not actions:
            problems.append(f"第 {index} 场没有动作节拍：纯对白的场在生成时没有画面可拍。")

        for beat_number, beat in enumerate(scene.flow, 1):
            where = f"第 {index} 场第 {beat_number} 拍"
            if beat.action is not None:
                if _QUOTES.search(beat.action):
                    problems.append(f"{where}的动作描写里出现了引号台词，请拆成独立台词节拍。")
                continue
            if beat.speaker != "VO" and beat.speaker not in scene.characters:
                problems.append(
                    f"{where}的说话人「{beat.speaker}」不在本场 characters {scene.characters} 里。"
                )
            if line_chars(beat.line or "") > MAX_LINE_CHARS:
                problems.append(
                    f"{where}的台词 {line_chars(beat.line or '')} 字，超过单句 {MAX_LINE_CHARS} 字上限。"
                )

    if not used_planned_scene:
        problems.append(f"一场戏都没用到大纲给本集安排的场景 {sorted(planned_scenes)}。")

    position = _hook_position(episode)
    if position is None:
        problems.append(f"hookBeat {list(episode.hookBeat)} 指向不存在的场次或节拍。")
    elif position > HOOK_WINDOW:
        problems.append(f"钩子认领落在全集第 {position} 拍，必须在前 {HOOK_WINDOW} 拍内兑现（冷开场）。")

    if check_duration:
        problems.extend(episode_duration_problems(episode, target))
    return problems


def episode_warnings(episode: EpisodeDraft, target: int) -> list[str]:
    seconds = episode_seconds(episode)
    low, high = seconds_range(target)
    if seconds < low:
        return [f"全集 {seconds} 秒，短于建议区间 {low}–{high} 秒，建议补戏"]
    if seconds > high:
        return [f"全集 {seconds} 秒，超出建议区间 {low}–{high} 秒，建议压缩"]
    return []


def render_script(episode: EpisodeDraft, outline: Outline) -> str:
    scenes = {card.id: card for card in outline.scenes}
    names = {character.id: character.name for character in outline.characters}
    blocks: list[str] = []
    for index, scene in enumerate(episode.scenes, 1):
        lines = [f"第{chinese_number(index)}场"]
        card = scenes.get(scene.sceneId)
        if card is not None:
            lines.append(f"{card.kind} · {card.name} · {card.time}")
        for beat in scene.flow:
            if beat.action is not None:
                lines.append(beat.action)
            else:
                speaker = names.get(
                    beat.speaker or "", "画外音" if beat.speaker == "VO" else (beat.speaker or "")
                )
                lines.append(f"{speaker}：{beat.line}")
        blocks.append("\n\n".join(lines))
    return "\n\n".join(blocks)
