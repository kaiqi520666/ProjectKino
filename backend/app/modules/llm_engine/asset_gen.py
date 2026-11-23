import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext, RunUsage
from pydantic_ai.models import Model

from app.modules.llm_engine.gates import record_gate
from app.modules.llm_engine.provider import MODEL_SETTINGS
from app.modules.llm_engine.schema import Asset, AssetKind, AssetResult, Record, ScriptResult, Text
from app.modules.llm_engine.script_gen import ProgressCallback, _notify, prompt, skill_instructions

MAX_CLUES_PER_ASSET = 16
MAX_CLUE_CHARS = 80
MAX_VARIANTS_PER_ASSET = 3
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

CHARACTER_VARIANT_SHEET_TEMPLATE = (
    "严格参考参考图1中的同一人物（保持五官、脸型、年龄、肤色与面部识别锚点完全一致），"
    "生成该人物的新造型角色三视图设定图，横版构图，纯白无缝背景，影棚柔光均匀照明。"
    "画面左侧约五分之二宽度是该角色的大头照：正面平视，从头顶到肩膀，脸部清晰占满这一块，表情自然放松。"
    "画面右侧约五分之三宽度是同一角色的三个身体视图，从左到右依次为正面、侧面（身体朝向画面左侧）、背面；"
    "三个视图都只画脖子以下、头部不入画（类似服装展示的裁切构图），大小一致，肩线与脚底各自对齐，间距均匀，"
    "脚完整入画，统一标准站姿：身体正直，双手自然下垂放在身体两侧，手里不拿任何东西，不做任何动作或手势，"
    "脚下只有很淡的落地阴影。新造型设定：{subject}。"
    "大头照和三个身体视图与参考图1是同一个人，仅按新造型设定替换服装、发型状态或表面痕迹；"
    "人物描述里写到的动作、姿势和手持物品都不画出来，身体视图一律用上面的标准站姿。"
    "画面里只有这一个角色，右侧三个身体视图都不画头部，不要任何文字、标注、姓名、编号、边框、分隔线、色块面板和水印，"
    "不要场景和道具。"
)


def _format_variant_prompt(kind: AssetKind, raw_prompt: str) -> str:
    cleaned = raw_prompt.strip().rstrip("。；;.")
    if kind == "character":
        return CHARACTER_VARIANT_SHEET_TEMPLATE.replace("{subject}", cleaned)
    if "参考图" in cleaned:
        return raw_prompt.strip()
    if kind == "scene":
        return (
            "严格参考参考图1中的同一场景（保持建筑结构、空间布局、主要陈设与镜头视角一致），"
            f"仅按以下状态调整时间、光影或表面变化：{raw_prompt.strip()}"
        )
    return (
        "严格参考参考图1中的同一道具（保持主体造型、材质与比例一致），"
        f"仅按以下状态调整外观或结构变化：{raw_prompt.strip()}"
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


class VariantDesign(Record):
    label: Text
    description: Text
    prompt: Text
    episodes: list[int] = Field(default_factory=list)


class AssetDesign(Record):
    id: Text
    description: Text
    prompt: Text
    voice: str = ""
    variants: list[VariantDesign] = Field(default_factory=list)


class DesignBatch(Record):
    assets: list[AssetDesign]


def _clip_clue(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= MAX_CLUE_CHARS else cleaned[: MAX_CLUE_CHARS - 1] + "…"


def _add_clue_for_ep(by_ep: dict[int, list[str]], ep_number: int, clue: str) -> None:
    text = _clip_clue(clue)
    if not text:
        return
    bucket = by_ep.setdefault(ep_number, [])
    if text not in bucket and len(bucket) < MAX_CLUES_PER_ASSET:
        bucket.append(text)


def _sample_clues_round_robin(by_ep: dict[int, list[str]], limit: int = MAX_CLUES_PER_ASSET) -> list[str]:
    """跨集轮询抽取线索，避免长剧中前 1–2 集占满名额而漏掉后半程换装/场景状态变化。"""
    if not by_ep:
        return []
    ordered_eps = sorted(by_ep.keys())
    sampled: list[str] = []
    seen: set[str] = set()
    round_idx = 0
    while len(sampled) < limit:
        added_this_round = False
        for ep_num in ordered_eps:
            ep_clues = by_ep[ep_num]
            if round_idx >= len(ep_clues):
                continue
            added_this_round = True
            clue = ep_clues[round_idx]
            if clue not in seen:
                seen.add(clue)
                sampled.append(clue)
                if len(sampled) >= limit:
                    break
        if not added_this_round:
            break
        round_idx += 1
    return sampled


def inventory(script: ScriptResult) -> list[InventoryItem]:
    characters = {card.id: card for card in script.outline.characters}
    scenes = {card.id: card for card in script.outline.scenes}
    props = {prop.id: prop for prop in script.outline.props}
    used: dict[str, set[int]] = {}
    order: dict[str, int] = {}
    clues: dict[str, dict[int, list[str]]] = {}
    prop_fallback_clues: dict[str, dict[int, list[str]]] = {}

    def touch(asset_id: str, number: int) -> None:
        order.setdefault(asset_id, len(order))
        used.setdefault(asset_id, set()).add(number)
        clues.setdefault(asset_id, {})

    for episode in script.episodes:
        ep_num = episode.number
        ep_prefix = f"第{ep_num}集"
        for scene in episode.scenes:
            touch(scene.sceneId, ep_num)
            for character in scene.characters:
                touch(character, ep_num)
            for prop in scene.props:
                touch(prop, ep_num)

            if scene.lighting and scene.lighting.strip():
                _add_clue_for_ep(clues[scene.sceneId], ep_num, f"{ep_prefix}·光线：{scene.lighting.strip()}")
            actions = [beat.action.strip() for beat in scene.flow if beat.action and beat.action.strip()]
            if actions:
                _add_clue_for_ep(clues[scene.sceneId], ep_num, f"{ep_prefix}：{actions[0]}")
            for action in actions:
                for character in scene.characters:
                    card = characters.get(character)
                    if card and card.name in action:
                        _add_clue_for_ep(clues[character], ep_num, f"{ep_prefix}：{action}")
                for prop in scene.props:
                    card = props.get(prop)
                    if card and card.name in action:
                        _add_clue_for_ep(clues[prop], ep_num, f"{ep_prefix}：{action}")
                    else:
                        _add_clue_for_ep(
                            prop_fallback_clues.setdefault(prop, {}), ep_num, f"{ep_prefix}：{action}"
                        )

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
        asset_clues = _sample_clues_round_robin(clues.get(asset_id, {}))
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
        prop_clues = asset_clues or _sample_clues_round_robin(
            prop_fallback_clues.get(asset_id, {}), limit=4
        )
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
        if len(design.variants) > MAX_VARIANTS_PER_ASSET:
            fail(
                f"资产 {design.id} 的变体数量超过了上限（最多 {MAX_VARIANTS_PER_ASSET} 个），"
                "请只保留最核心的外观状态变化。"
            )
        seen_labels: set[str] = set()
        for variant in design.variants:
            label_key = variant.label.strip().lower()
            if label_key in seen_labels:
                fail(f"资产 {design.id} 的变体标签「{variant.label}」重复，请去重。")
            seen_labels.add(label_key)
            for name in ctx.deps.forbidden:
                if name and name in variant.prompt:
                    fail(
                        f"资产 {design.id} 变体「{variant.label}」的生图提示词里出现了"
                        f"角色名「{name}」，请删掉。"
                    )
            if ctx.deps.kind == "scene" and not _SCENE_EMPTY.search(variant.prompt):
                fail(f"场景 {design.id} 变体「{variant.label}」的生图提示词必须明确写出无人空景。")
            if ctx.deps.kind == "prop":
                if not _PROP_WHITE_BG.search(variant.prompt):
                    fail(
                        f"道具 {design.id} 变体「{variant.label}」的生图提示词必须明确写出"
                        "纯白背景或白底。"
                    )
                if not _PROP_NO_HANDS.search(variant.prompt):
                    fail(f"道具 {design.id} 变体「{variant.label}」的生图提示词必须明确写出无手。")
                if not _PROP_SCALE.search(variant.prompt):
                    fail(
                        f"道具 {design.id} 变体「{variant.label}」的生图提示词必须写明尺度"
                        "（手持级/桌面级/家具级尺度）。"
                    )
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


class VariantPromptSuggestion(Record):
    description: Text
    prompt: Text


_VARIANT_SUGGEST_INSTRUCTIONS = (
    "你是 FrameDrama 影视短剧美术设定师。用户已有一个主资产（角色/场景/道具）设定，"
    "现在需要为它创建一个特定状态的新变体（将在主图作为参考图1的基础上改图生成）。"
    "请基于主资产设定、项目画风与用户指定的状态标签/补充说明，返回 JSON：\n"
    "- description：1–2 句中文，说明该变体与主资产的外观差异及适用情景；\n"
    "- prompt：高质量中文生图提示词，要求：\n"
    "  * 若为角色：只写人物的新造型描述（服装、发型状态、表面痕迹与结尾画风句），"
    "不写角色名，不写三视图/白底/站姿等版式词（程序会自动套模板并锁脸）；\n"
    "  * 若为场景：必须包含「无人空景，画面中没有任何人物或剪影」，"
    "重点写清变化后的时间、光影、气候或陈设状态，不写角色名；\n"
    "  * 若为道具：必须包含「纯白背景」「无手」和尺度短语"
    "（手持级尺度/桌面级尺度/家具级尺度），重点写清状态变化，不写角色名。"
)


async def suggest_variant_prompt(
    model: Model,
    *,
    kind: AssetKind,
    name: str,
    parent_description: str,
    parent_prompt: str,
    variant_label: str,
    note: str = "",
    settings_payload: dict | None = None,
    usage: RunUsage | None = None,
) -> VariantPromptSuggestion:
    agent = Agent(
        model,
        output_type=PromptedOutput(VariantPromptSuggestion),
        instructions=_VARIANT_SUGGEST_INSTRUCTIONS,
        model_settings=MODEL_SETTINGS,
        retries=1,
    )
    payload: dict = {
        "kind": kind,
        "name": name,
        "parentDescription": parent_description,
        "parentPrompt": parent_prompt,
        "variantLabel": variant_label.strip(),
    }
    if note.strip():
        payload["note"] = note.strip()
    if settings_payload:
        payload["settings"] = settings_payload
    result = await agent.run(prompt(payload), usage=usage)
    return VariantPromptSuggestion(
        description=result.output.description.strip(),
        prompt=_format_variant_prompt(kind, result.output.prompt),
    )


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
    existing_roots = [asset for asset in existing if not asset.parentId]
    existing_by_id = {asset.id: asset for asset in existing_roots}
    existing_variants_by_parent: dict[str, list[Asset]] = {}
    for asset in existing:
        if asset.parentId:
            existing_variants_by_parent.setdefault(asset.parentId, []).append(asset)
    reused_ids = {
        item.id for item in items if item.id in existing_by_id and existing_by_id[item.id].kind == item.kind
    }
    to_design = [item for item in items if item.id not in reused_ids]

    designs: dict[str, AssetDesign] = {}
    if to_design:
        label = (
            f"正在并发增量设计 {len(to_design)} 项新资产（保留已有 {len(reused_ids)} 项）"
            if reused_ids
            else f"正在并发设计 {len(to_design)} 项角色、场景与道具设定（含自动变体识别）"
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
            for prev_variant in existing_variants_by_parent.get(item.id, ()):
                assets.append(
                    Asset(
                        id=prev_variant.id,
                        kind=item.kind,
                        name=prev_variant.name,
                        description=prev_variant.description,
                        prompt=prev_variant.prompt,
                        episodeNumbers=list(prev_variant.episodeNumbers) or list(item.episodes),
                        voice="",
                        parentId=item.id,
                        variantLabel=prev_variant.variantLabel,
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
        allowed_eps = set(item.episodes)
        seen_variant_labels: set[str] = set()
        variant_idx = 0
        for variant in design.variants:
            if variant_idx >= MAX_VARIANTS_PER_ASSET:
                break
            v_label = variant.label.strip()[:60]
            if not v_label or v_label.lower() in seen_variant_labels:
                continue
            seen_variant_labels.add(v_label.lower())
            variant_idx += 1
            v_eps = sorted({ep for ep in variant.episodes if ep in allowed_eps}) or list(item.episodes)
            assets.append(
                Asset(
                    id=f"{item.id}_v{variant_idx}",
                    kind=item.kind,
                    name=item.name,
                    description=variant.description,
                    prompt=_format_variant_prompt(item.kind, variant.prompt),
                    episodeNumbers=v_eps,
                    voice="",
                    parentId=item.id,
                    variantLabel=v_label,
                )
            )
    root_count = sum(1 for a in assets if not a.parentId)
    variant_count = len(assets) - root_count
    done_label = (
        f"已完成 {root_count} 项主资产与 {variant_count} 项自动变体识别"
        if variant_count > 0
        else f"已完成 {root_count} 项资产识别"
    )
    await _notify(on_progress, 3, 3, done_label, 98)
    return AssetResult(settings=script.settings, assets=assets)
