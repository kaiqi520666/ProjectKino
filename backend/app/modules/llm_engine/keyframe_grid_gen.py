from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, PromptedOutput, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from app.modules.llm_engine.gates import record_gate
from app.modules.llm_engine.provider import MODEL_SETTINGS, SHARED_USAGE_LIMITS
from app.modules.llm_engine.schema import Record, Text
from app.modules.llm_engine.script_gen import prompt, skill_instructions

_GRID_POLLUTION_RE = re.compile(
    r"(?:@\[?图片\d+\]?|<Picture\s*\d+>|【镜头\s*\d*】|\[Shot\s*\d+\]|"
    r"\d+(?:\.\d+)?\s*[—–\-~～]\s*\d+(?:\.\d+)?\s*(?:秒|s\b)|第\s*\d+(?:\.\d+)?\s*秒|"
    r"\b\d{1,2}:\d{2}\b|字幕|文字标题|编号)",
    re.IGNORECASE,
)
_GRID_HEADER_LINE_RE = re.compile(r"^@\[图片\d+\]\s*=\s*分镜宫格[^\n]*\n?", re.MULTILINE)
_GRID_BLOCK_RE = re.compile(
    r"\n*【分镜宫格驱动】\n[\s\S]*?(?=\n\n【|\Z)",
    re.MULTILINE,
)

GRID_LAYOUT_LABELS: dict[str, str] = {
    "2x2": "2×2",
    "2x3": "2×3",
    "3x3": "3×3",
}


def choose_grid_layout(cut_count: int) -> tuple[int, int, str]:
    """根据镜头数选择零黑块标准网格：(rows, cols, layout_key)。"""
    if cut_count <= 4:
        return 2, 2, "2x2"
    if cut_count <= 6:
        return 2, 3, "2x3"
    return 3, 3, "3x3"


def allocate_cut_cells(
    cuts: list[dict[str, Any]],
) -> tuple[tuple[int, int, str], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    确定性地把片段镜头分配到 2x2 / 2x3 / 3x3 网格中，保证每一格都有画面（零黑块）。
    返回: ((rows, cols, layout), cell_plan, cell_mapping)
    """
    normalized_cuts: list[dict[str, Any]] = []
    for pos, raw in enumerate(cuts, 1):
        if not isinstance(raw, dict):
            continue
        cut_index = int(raw.get("index") or pos)
        seconds = max(0.5, float(raw.get("seconds") or 3.0))
        normalized_cuts.append(
            {
                "index": cut_index,
                "seconds": seconds,
                "shotSize": str(raw.get("shotSize") or "中景"),
                "camera": str(raw.get("camera") or "固定镜头"),
                "framePrompt": str(raw.get("framePrompt") or "").strip(),
            }
        )
    if not normalized_cuts:
        normalized_cuts = [
            {
                "index": 1,
                "seconds": 4.0,
                "shotSize": "中景",
                "camera": "固定镜头",
                "framePrompt": "",
            }
        ]

    rows, cols, layout = choose_grid_layout(len(normalized_cuts))
    total_cells = rows * cols

    counts: list[int] = [1] * len(normalized_cuts)
    if len(normalized_cuts) <= total_cells:
        extra = total_cells - len(normalized_cuts)
        for _ in range(extra):
            best_idx = max(
                range(len(normalized_cuts)),
                key=lambda i: (normalized_cuts[i]["seconds"] / counts[i], -i),
            )
            counts[best_idx] += 1
        selected_indices = list(range(len(normalized_cuts)))
    else:
        # 超过 9 镜时均匀抽选 9 个关键镜（必含首尾镜）
        n = len(normalized_cuts)
        selected_indices = sorted(
            {round(i * (n - 1) / (total_cells - 1)) for i in range(total_cells)}
        )
        while len(selected_indices) < total_cells:
            for cand in range(n):
                if cand not in selected_indices:
                    selected_indices.append(cand)
                    if len(selected_indices) == total_cells:
                        break
        selected_indices.sort()
        counts = [1 if i in selected_indices else 0 for i in range(n)]

    cell_plan: list[dict[str, Any]] = []
    cell_mapping: list[dict[str, Any]] = []
    cell_no = 0
    for idx, cut in enumerate(normalized_cuts):
        k = counts[idx]
        if k <= 0:
            continue
        assigned: list[int] = []
        for sub in range(k):
            cell_no += 1
            assigned.append(cell_no)
            row_num = (cell_no - 1) // cols + 1
            col_num = (cell_no - 1) % cols + 1
            if k == 1:
                phase = "主关键帧"
            elif k == 2:
                phase = "起势帧" if sub == 0 else "落幅帧"
            elif sub == 0:
                phase = "起势帧"
            elif sub == k - 1:
                phase = "落幅帧"
            else:
                phase = f"中段过渡帧{sub}"
            cell_plan.append(
                {
                    "cellIndex": cell_no,
                    "row": row_num,
                    "col": col_num,
                    "cutIndex": cut["index"],
                    "phase": phase,
                    "shotSize": cut["shotSize"],
                    "camera": cut["camera"],
                    "framePrompt": cut["framePrompt"],
                }
            )
        cell_mapping.append({"cutIndex": cut["index"], "cells": assigned})

    return (rows, cols, layout), cell_plan, cell_mapping


def format_cell_mapping_text(cell_mapping: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for entry in cell_mapping:
        cut_index = int(entry.get("cutIndex") or 0)
        cells = [int(c) for c in (entry.get("cells") or []) if int(c) > 0]
        if cut_index <= 0 or not cells:
            continue
        if len(cells) == 1:
            parts.append(f"镜头{cut_index}=格{cells[0]}")
        else:
            parts.append(f"镜头{cut_index}=格{cells[0]}–格{cells[-1]}")
    return "；".join(parts)


def remove_storyboard_grid_prompt(prompt_text: str) -> str:
    """无损剥离顶部宫格槽位声明行与【分镜宫格驱动】区块，不碰任何镜头正文。"""
    cleaned = _GRID_HEADER_LINE_RE.sub("", prompt_text or "")
    cleaned = _GRID_BLOCK_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def upsert_storyboard_grid_prompt(
    prompt_text: str,
    *,
    slot_index: int,
    grid_layout: str,
    cell_mapping: list[dict[str, Any]],
) -> str:
    """在原视频提示词上增量写入/刷新顶部宫格参考行与【分镜宫格驱动】独立区块。"""
    base = remove_storyboard_grid_prompt(prompt_text)
    layout_label = GRID_LAYOUT_LABELS.get(grid_layout, grid_layout.replace("x", "×"))
    total_cells = max(
        (max(entry.get("cells") or [0]) for entry in cell_mapping),
        default=9 if grid_layout == "3x3" else (6 if grid_layout == "2x3" else 4),
    )
    mapping_text = format_cell_mapping_text(cell_mapping)
    header_line = f"@[图片{slot_index}] = 分镜宫格（{layout_label}）"
    drive_block = (
        "【分镜宫格驱动】\n"
        f"@[图片{slot_index}] 为 {layout_label} 无字分镜宫格图，"
        f"按从左到右、从上到下（格1→格{total_cells}）依次对应本段各镜头构图：\n"
        f"{mapping_text}。\n"
        "全程仅输出单画幅全屏连续镜头，严禁出现宫格分屏、黑边或画中画。"
    )

    lines = base.splitlines() if base else []
    header_end = 0
    for idx, line in enumerate(lines):
        if re.match(r"^@\[(?:图片|视频|音频|文本)\d+\]\s*=", line.strip()):
            header_end = idx + 1
        elif header_end > 0:
            break

    if header_end > 0:
        lines.insert(header_end, header_line)
    else:
        lines = [header_line, "", *lines] if lines else [header_line]
    with_header = "\n".join(lines)

    # 优先插入在【人物关系与构图逻辑】前，其次第一个【镜头前，否则附在末尾。
    anchor_match = re.search(r"(?=\n【人物关系与构图逻辑】)", with_header)
    if anchor_match is None:
        anchor_match = re.search(r"(?=\n【镜头)", with_header)
    if anchor_match is not None:
        pos = anchor_match.start()
        before = with_header[:pos].rstrip("\n")
        after = with_header[pos:].lstrip("\n")
        merged = f"{before}\n\n{drive_block}\n\n{after}"
    else:
        merged = f"{with_header.rstrip()}\n\n{drive_block}"
    return re.sub(r"\n{3,}", "\n\n", merged).strip()


class GridCellPrompt(Record):
    cellIndex: int
    visualPrompt: Text


class KeyframeGridPlan(Record):
    cells: Annotated[list[GridCellPrompt], Field(min_length=4, max_length=9)]


@dataclass(frozen=True)
class KeyframeGridContext:
    expected_cells: tuple[int, ...]
    forbidden_names: tuple[str, ...]


def _verify_grid_plan(
    ctx: RunContext[KeyframeGridContext], plan: KeyframeGridPlan
) -> KeyframeGridPlan:
    got = [cell.cellIndex for cell in plan.cells]
    want = list(ctx.deps.expected_cells)
    if sorted(got) != want or len(set(got)) != len(got):
        msg = f"cells 的 cellIndex 必须与 cellPlan 一一对应：{want}"
        record_gate("plan-keyframe-grid", False, [msg])
        raise ModelRetry(msg)
    for cell in plan.cells:
        bad = _GRID_POLLUTION_RE.search(cell.visualPrompt)
        if bad:
            msg = f"第 {cell.cellIndex} 格画面描述里包含禁止词或协议标记「{bad.group(0)}」，请删掉。"
            record_gate("plan-keyframe-grid", False, [msg])
            raise ModelRetry(msg)
        for name in ctx.deps.forbidden_names:
            if name and name in cell.visualPrompt:
                msg = f"第 {cell.cellIndex} 格画面描述里出现了角色名「{name}」，请改成外观特征描述。"
                record_gate("plan-keyframe-grid", False, [msg])
                raise ModelRetry(msg)
    record_gate("plan-keyframe-grid", True)
    return plan


def compose_grid_image_prompt(
    *,
    ratio: str,
    visual_style: str,
    world_summary: str,
    rows: int,
    cols: int,
    cells: list[GridCellPrompt],
) -> str:
    total = rows * cols
    ordered = sorted(cells, key=lambda c: c.cellIndex)
    lines = [
        f"一张完整的 {ratio} {visual_style} 电影分镜联系表，"
        f"由 {rows} 行 × {cols} 列共 {total} 个等大画面格紧密铺满构成"
        "（格间无缝紧贴或仅保留极细 1px 自然分界，无外边框、无白边、无黑块、无任何空画格）。",
        "所有画格中的人物长相、发型、服饰与场景建筑布局严格以参考图为准，保持全图画风、色调与主光源方向统一。",
    ]
    if world_summary.strip():
        lines.append(f"世界观基准：{world_summary.strip()}。")
    lines.append("")
    for cell in ordered:
        r = (cell.cellIndex - 1) // cols + 1
        c = (cell.cellIndex - 1) % cols + 1
        lines.append(f"第{r}行第{c}格：{cell.visualPrompt.strip().rstrip('。')}。")
    lines.append("")
    lines.append(
        f"严格要求：全部 {total} 个画格均充满高质量电影画面，零黑块、零留白；"
        "画面中绝对不出现任何汉字、英文字母、数字编号、字幕、水印、箭头或分镜边框文字。"
    )
    return "\n".join(lines)


def _extract_shot_excerpts_from_prompt(clip_prompt: str) -> dict[int, str]:
    excerpts: dict[int, str] = {}
    blocks = re.split(r"【镜头(\d+)(?:｜[^】]+)?】", clip_prompt or "")
    for i in range(1, len(blocks) - 1, 2):
        cut_idx = int(blocks[i])
        body = blocks[i + 1]
        m = re.search(r"画面[：:]\s*([^\n]+)", body)
        if m:
            excerpts[cut_idx] = m.group(1).strip()
    return excerpts


@dataclass(frozen=True)
class PlannedKeyframeGrid:
    grid_layout: str
    rows: int
    cols: int
    cell_mapping: list[dict[str, Any]]
    image_prompt: str


async def plan_keyframe_grid(
    model: Model,
    *,
    cuts: list[dict[str, Any]],
    blocking: str,
    clip_prompt: str,
    ratio: str,
    visual_style: str,
    world_summary: str,
    reference_assets: list[dict[str, Any]],
    forbidden_names: tuple[str, ...],
    usage: RunUsage | None = None,
) -> PlannedKeyframeGrid:
    (rows, cols, layout), cell_plan, cell_mapping = allocate_cut_cells(cuts)
    shot_excerpts = _extract_shot_excerpts_from_prompt(clip_prompt)
    enriched_plan = [
        {
            **cell,
            **(
                {"shotExcerpt": shot_excerpts[cell["cutIndex"]]}
                if cell["cutIndex"] in shot_excerpts
                else {}
            ),
        }
        for cell in cell_plan
    ]
    payload: dict[str, Any] = {
        "ratio": ratio,
        "visualStyle": visual_style,
        "world": world_summary,
        "blocking": blocking,
        "grid": {
            "layout": layout,
            "rows": rows,
            "cols": cols,
            "totalCells": rows * cols,
        },
        "referenceAssets": reference_assets,
        "cellPlan": enriched_plan,
    }

    agent = Agent(
        model,
        deps_type=KeyframeGridContext,
        output_type=PromptedOutput(KeyframeGridPlan),
        instructions=skill_instructions("plan-keyframe-grid"),
        model_settings=MODEL_SETTINGS,
        retries=3,
    )
    agent.output_validator(_verify_grid_plan)
    result = await agent.run(
        prompt(payload),
        deps=KeyframeGridContext(
            expected_cells=tuple(range(1, rows * cols + 1)),
            forbidden_names=forbidden_names,
        ),
        usage=usage,
        usage_limits=SHARED_USAGE_LIMITS,
    )
    image_prompt = compose_grid_image_prompt(
        ratio=ratio,
        visual_style=visual_style,
        world_summary=world_summary,
        rows=rows,
        cols=cols,
        cells=result.output.cells,
    )
    return PlannedKeyframeGrid(
        grid_layout=layout,
        rows=rows,
        cols=cols,
        cell_mapping=cell_mapping,
        image_prompt=image_prompt,
    )
