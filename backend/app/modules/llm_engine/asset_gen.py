import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext, RunUsage
from pydantic_ai.models import Model

from app.modules.llm_engine.gates import record_gate
from app.modules.llm_engine.provider import MODEL_SETTINGS
from app.modules.llm_engine.schema import Asset, AssetKind, AssetResult, Record, ScriptResult, Text
from app.modules.llm_engine.script_gen import ProgressCallback, _notify, prompt, skill_instructions

MAX_CLUES_PER_ASSET = 4
MAX_CLUE_CHARS = 80
_SCENE_EMPTY = re.compile(
    r"(无人|空景|空无一人|没有人物|无人物|无任何人物|empty scene|no people)", re.IGNORECASE
)
_PROP_WHITE_BG = re.compile(r"(纯白|白底|白色背景|白色无缝|pure white|white background)", re.IGNORECASE)
_PROP_NO_HANDS = re.compile(r"(无手|没有手|无人手|不出现手|不带手|no hands|without hands)", re.IGNORECASE)
_PROP_SCALE = re.compile(
    r"(手持级|桌面级|家具级|尺度|掌心|单手可握|手掌大小|桌面大小|handheld|tabletop|furniture scale)",
    re.IGNORECASE,
)

CHARACTER_SHEET_TEMPLATE = (
    "角色三视图设定图，横版构图，纯白无缝背景，影棚柔光均匀照明。"
    "画面左侧约五分之二宽度是该角色的大头照：正面平视，从头顶到肩膀，脸部清晰占满这一块，表情自然放松。"
    "画面右侧约五分之三宽度是同一角色的三个身体视图，从左到右依次为正面、侧面（身体朝向画面左侧）、背面；"
    "三个视图都只画脖子以下、头部不入画（类似服装展示的裁切构图），大小一致，肩线与脚底各自对齐，间距均匀，"
    "脚完整入画，统一标准站姿：身体正直，双手自然下垂放在身体两侧，手里不拿任何东西，不做任何动作或手势，"
    "脚下只有很淡的落地阴影。角色：{subject}。"
    "大头照和三个身体视图是同一个人：肤色、体型、服装、鞋子和配饰完全一致；"
    "人物描述里写到的动作、姿势和手持物品都不画出来，性格只体现在大头照的神态上，身体视图一律用上面的标准站姿。"
    "画面里只有这一个角色，右侧三个身体视图都不画头部，不要任何文字、标注、姓名、编号、边框、分隔线、色块面板和水印，"
    "不要场景和道具。"
)


@dataclass(frozen=True)
class InventoryItem:
    id: str
    kind: AssetKind
    name: str
    profile: str
    episodes: tuple[int, ...]
    clues: tuple[str, ...] = ()


@dataclass(frozen=True)
class DesignContext:
    kind: AssetKind
    expected: tuple[str, ...]
    forbidden: tuple[str, ...]


class AssetDesign(Record):
    id: Text
    description: Text
    prompt: Text
    voice: str = ""


class DesignBatch(Record):
    assets: list[AssetDesign]


def _clip_clue(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= MAX_CLUE_CHARS else cleaned[: MAX_CLUE_CHARS - 1] + "…"


def _add_clue(bucket: list[str], clue: str) -> None:
    text = _clip_clue(clue)
    if text and text not in bucket and len(bucket) < MAX_CLUES_PER_ASSET:
        bucket.append(text)


def inventory(script: ScriptResult) -> list[InventoryItem]:
    characters = {card.id: card for card in script.outline.characters}
    scenes = {card.id: card for card in script.outline.scenes}
    props = {prop.id: prop for prop in script.outline.props}
    used: dict[str, set[int]] = {}
    order: dict[str, int] = {}
    clues: dict[str, list[str]] = {}
    prop_fallback_clues: dict[str, list[str]] = {}

    def touch(asset_id: str, number: int) -> None:
        order.setdefault(asset_id, len(order))
        used.setdefault(asset_id, set()).add(number)
        clues.setdefault(asset_id, [])

    for episode in script.episodes:
        for scene in episode.scenes:
            touch(scene.sceneId, episode.number)
            for character in scene.characters:
                touch(character, episode.number)
            for prop in scene.props:
                touch(prop, episode.number)

            if scene.lighting and scene.lighting.strip():
                _add_clue(clues[scene.sceneId], f"光线：{scene.lighting.strip()}")
            actions = [beat.action.strip() for beat in scene.flow if beat.action and beat.action.strip()]
            if actions:
                _add_clue(clues[scene.sceneId], actions[0])
            for action in actions:
                for character in scene.characters:
                    card = characters.get(character)
                    if card and card.name in action:
                        _add_clue(clues[character], action)
                for prop in scene.props:
                    card = props.get(prop)
                    if card and card.name in action:
                        _add_clue(clues[prop], action)
                    else:
                        _add_clue(prop_fallback_clues.setdefault(prop, []), action)

    missing = [
        asset_id
        for asset_id in used
        if (asset_id.startswith("C") and asset_id not in characters)
        or (asset_id.startswith("S") and asset_id not in scenes)
        or (asset_id.startswith("P") and asset_id not in props)
    ]
    if missing:
        raise ValueError(f"剧本引用了大纲里没有的资产编号：{sorted(missing)}")

    def build_item(asset_id: str) -> InventoryItem:
        numbers = tuple(sorted(used[asset_id]))
        asset_clues = clues.get(asset_id, [])
        if asset_id.startswith("C"):
            card = characters[asset_id]
            profile = f"{card.role}；说话方式：{card.voice}" if card.voice else card.role
            return InventoryItem(card.id, "character", card.name, profile, numbers, tuple(asset_clues))
        if asset_id.startswith("S"):
            card = scenes[asset_id]
            head = f"{card.kind} · {card.time}"
            profile = f"{head}；{card.note}" if card.note else head
            return InventoryItem(card.id, "scene", card.name, profile, numbers, tuple(asset_clues))
        card = props[asset_id]
        prop_clues = asset_clues or prop_fallback_clues.get(asset_id, [])[:2]
        return InventoryItem(card.id, "prop", card.name, card.role, numbers, tuple(prop_clues))

    items = [build_item(asset_id) for asset_id in used]
    return sorted(
        items, key=lambda entry: (("character", "scene", "prop").index(entry.kind), order[entry.id])
    )


def verify_designs(ctx: RunContext[DesignContext], batch: DesignBatch) -> DesignBatch:
    meta = {"kind": ctx.deps.kind}

    def fail(reason: str) -> None:
        record_gate("analyze-assets", False, [reason], meta)
        raise ModelRetry(reason)

    got = [design.id for design in batch.assets]
    expected = list(ctx.deps.expected)
    if sorted(got) != sorted(expected) or len(set(got)) != len(got):
        fail(f"请为且只为这些资产各写一条设计，不多不少：{expected}")
    for design in batch.assets:
        for name in ctx.deps.forbidden:
            if name and name in design.prompt:
                fail(f"资产 {design.id} 的生图提示词里出现了角色名「{name}」，请删掉。")
        voice = design.voice.strip()
        if ctx.deps.kind == "character":
            if not voice:
                fail(f"角色 {design.id} 缺少 voice：请写一条静态音色，描述这把嗓子本身。")
            if len(voice) > 160:
                fail(f"角色 {design.id} 的 voice 超过 160 字，请压缩成参数串。")
        elif voice:
            fail(f"只有角色需要 voice，{design.id} 是 {ctx.deps.kind}，请把 voice 留空。")
        if ctx.deps.kind == "scene" and not _SCENE_EMPTY.search(design.prompt):
            fail(f"场景 {design.id} 的生图提示词必须明确写出无人空景（如「空无一人」「无人空景」）。")
        if ctx.deps.kind == "prop":
            if not _PROP_WHITE_BG.search(design.prompt):
                fail(f"道具 {design.id} 的生图提示词必须明确写出纯白背景或白底。")
            if not _PROP_NO_HANDS.search(design.prompt):
                fail(f"道具 {design.id} 的生图提示词必须明确写出无手。")
            if not _PROP_SCALE.search(design.prompt):
                fail(f"道具 {design.id} 的生图提示词必须写明尺度（手持级/桌面级/家具级尺度）。")
    record_gate("analyze-assets", True, meta=meta)
    return batch


async def design_kind(
    model: Model,
    kind: AssetKind,
    items: list[InventoryItem],
    settings_payload: dict,
    forbidden: list[str],
    *,
    usage: RunUsage | None = None,
) -> dict[str, AssetDesign]:
    if not items:
        return {}
    agent = Agent(
        model,
        deps_type=DesignContext,
        output_type=PromptedOutput(DesignBatch),
        instructions=skill_instructions("analyze-assets"),
        model_settings=MODEL_SETTINGS,
        retries=2,
    )
    agent.output_validator(verify_designs)
    result = await agent.run(
        prompt(
            {
                "kind": kind,
                "settings": settings_payload,
                "assets": [
                    {
                        "id": item.id,
                        "name": item.name,
                        "episodes": list(item.episodes),
                        "profile": item.profile,
                        **({"scriptClues": list(item.clues)} if item.clues else {}),
                    }
                    for item in items
                ],
            }
        ),
        deps=DesignContext(kind, tuple(item.id for item in items), tuple(n for n in forbidden if n)),
        usage=usage,
    )
    return {design.id: design for design in result.output.assets}


async def analyze_assets(
    model: Model,
    script: ScriptResult,
    *,
    existing: Sequence[Asset] = (),
    usage: RunUsage | None = None,
    on_progress: ProgressCallback | None = None,
) -> AssetResult:
    await _notify(on_progress, 1, 3, "正在汇总全剧出场的角色、场景与道具", 15)
    items = inventory(script)
    names = [card.name for card in script.outline.characters]
    world = script.outline.world
    settings_payload = {**script.settings.model_dump(), "world": world.model_dump() if world else None}
    existing_by_id = {asset.id: asset for asset in existing}
    reused_ids = {
        item.id for item in items if item.id in existing_by_id and existing_by_id[item.id].kind == item.kind
    }
    to_design = [item for item in items if item.id not in reused_ids]

    designs: dict[str, AssetDesign] = {}
    if to_design:
        label = (
            f"正在并发增量设计 {len(to_design)} 项新资产（保留已有 {len(reused_ids)} 项）"
            if reused_ids
            else f"正在并发设计 {len(to_design)} 项角色、场景与道具设定"
        )
        await _notify(on_progress, 2, 3, label, 45)
        batches = await asyncio.gather(
            *(
                design_kind(
                    model,
                    kind,
                    [item for item in to_design if item.kind == kind],
                    settings_payload,
                    names,
                    usage=usage,
                )
                for kind in ("character", "scene", "prop")
            )
        )
        for batch in batches:
            designs.update(batch)

    assets: list[Asset] = []
    for item in items:
        if item.id in reused_ids:
            prev = existing_by_id[item.id]
            assets.append(
                Asset(
                    id=item.id,
                    kind=item.kind,
                    name=prev.name,
                    description=prev.description,
                    prompt=prev.prompt,
                    episodeNumbers=list(item.episodes),
                    voice=prev.voice if item.kind == "character" else "",
                )
            )
            continue
        design = designs[item.id]
        assets.append(
            Asset(
                id=item.id,
                kind=item.kind,
                name=item.name,
                description=design.description,
                prompt=(
                    CHARACTER_SHEET_TEMPLATE.replace("{subject}", design.prompt.strip().rstrip("。；;."))
                    if item.kind == "character"
                    else design.prompt
                ),
                episodeNumbers=list(item.episodes),
                voice=design.voice.strip() if item.kind == "character" else "",
            )
        )
    await _notify(on_progress, 3, 3, f"已完成 {len(assets)} 项资产识别", 98)
    return AssetResult(settings=script.settings, assets=assets)
