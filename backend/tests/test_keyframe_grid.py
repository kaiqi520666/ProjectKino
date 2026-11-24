import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from app.modules.llm_engine.keyframe_grid_gen import (
    allocate_cut_cells,
    plan_keyframe_grid,
    remove_storyboard_grid_prompt,
    upsert_storyboard_grid_prompt,
)
from app.modules.llm_engine.storyboard_gen import _cut_time_ranges


def test_cut_time_ranges_produces_contiguous_integer_intervals():
    ranges = _cut_time_ranges([5.0, 5.0, 5.1, 2.5, 3.6, 2.5, 4.4], total_seconds=28)
    assert len(ranges) == 7
    assert ranges[0][0] == 0
    assert ranges[-1][1] == 28
    for idx in range(len(ranges)):
        start, end = ranges[idx]
        assert end > start
        if idx > 0:
            assert start == ranges[idx - 1][1]
    assert ranges[4] == (18, 21)


def test_allocate_cut_cells_fills_grid_with_zero_black_cells():
    # 2 cuts -> 2x2 (4 cells)
    (r2, c2, l2), plan2, map2 = allocate_cut_cells(
        [{"index": 1, "seconds": 5.0}, {"index": 2, "seconds": 3.0}]
    )
    assert (r2, c2, l2) == (2, 2, "2x2")
    assert len(plan2) == 4
    assert sum(len(m["cells"]) for m in map2) == 4

    # 5 cuts -> 2x3 (6 cells)
    (r5, c5, l5), plan5, map5 = allocate_cut_cells(
        [{"index": i, "seconds": 5.0 if i == 2 else 3.0} for i in range(1, 6)]
    )
    assert (r5, c5, l5) == (2, 3, "2x3")
    assert len(plan5) == 6
    assert map5[1]["cells"] == [2, 3]

    # 7 cuts -> 3x3 (9 cells, zero black cells)
    (r7, c7, l7), plan7, map7 = allocate_cut_cells(
        [
            {"index": 1, "seconds": 5.0},
            {"index": 2, "seconds": 5.0},
            {"index": 3, "seconds": 5.1},
            {"index": 4, "seconds": 2.5},
            {"index": 5, "seconds": 3.6},
            {"index": 6, "seconds": 2.5},
            {"index": 7, "seconds": 4.4},
        ]
    )
    assert (r7, c7, l7) == (3, 3, "3x3")
    assert len(plan7) == 9
    assert [c["cellIndex"] for c in plan7] == list(range(1, 10))
    assert sum(len(m["cells"]) for m in map7) == 9

    # 11 cuts -> 3x3 (9 representative cells including first & last)
    (r11, c11, l11), plan11, map11 = allocate_cut_cells(
        [{"index": i, "seconds": 2.5} for i in range(1, 12)]
    )
    assert (r11, c11, l11) == (3, 3, "3x3")
    assert len(plan11) == 9
    assert map11[0]["cutIndex"] == 1
    assert map11[-1]["cutIndex"] == 11


def test_upsert_and_remove_storyboard_grid_prompt_preserves_cuts_cleanly():
    original = (
        "@[图片1] = 林晚\n"
        "@[图片2] = 美术教室\n\n"
        "【人物关系与构图逻辑】\n"
        "美术教室，大窗在左侧晨光斜入。林晚：站在讲台左侧，面朝学生席。\n\n"
        "【镜头1｜0-5s】\n"
        "画面：穿针织开衫的女教师翻动教案。\n\n"
        "【镜头2｜5-10s】\n"
        "画面：教室坐满学生。"
    )
    mapping = [{"cutIndex": 1, "cells": [1, 2]}, {"cutIndex": 2, "cells": [3, 4]}]

    with_grid = upsert_storyboard_grid_prompt(
        original,
        slot_index=3,
        grid_layout="2x2",
        cell_mapping=mapping,
    )
    assert "@[图片3] = 分镜宫格（2×2）" in with_grid
    assert "【分镜宫格驱动】\n@[图片3] 为 2×2 无字分镜宫格图" in with_grid
    assert "镜头1=格1–格2；镜头2=格3–格4。" in with_grid
    assert "【镜头1｜0-5s】" in with_grid
    assert with_grid.index("【分镜宫格驱动】") < with_grid.index("【人物关系与构图逻辑】")

    # Re-upserting (e.g. redraw) replaces cleanly without duplicating block or header
    redrawn = upsert_storyboard_grid_prompt(
        with_grid,
        slot_index=3,
        grid_layout="2x2",
        cell_mapping=mapping,
    )
    assert redrawn.count("【分镜宫格驱动】") == 1
    assert redrawn.count("分镜宫格（2×2）") == 1

    # Removing restores original cleanly
    restored = remove_storyboard_grid_prompt(redrawn)
    assert restored == original


@pytest.mark.asyncio
async def test_plan_keyframe_grid_validates_pollution_and_builds_borderless_prompt():
    attempts = 0

    def respond(messages, _info):
        nonlocal attempts
        attempts += 1
        user = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        data = json.loads(user.content)
        cells = []
        for item in data["cellPlan"]:
            idx = item["cellIndex"]
            if attempts == 1 and idx == 1:
                text = "【镜头1】林晚站在教室讲台前翻开教案"
            else:
                text = f"中景，小学美术教室讲台前，穿米白针织开衫的女教师神情温和，第{idx}格动作清晰自然"
            cells.append({"cellIndex": idx, "visualPrompt": text})
        return ModelResponse(parts=[TextPart(json.dumps({"cells": cells}, ensure_ascii=False))])

    planned = await plan_keyframe_grid(
        FunctionModel(respond),
        cuts=[
            {"index": 1, "seconds": 5.0, "shotSize": "中景", "camera": "缓慢推镜", "framePrompt": "讲台前"},
            {"index": 2, "seconds": 5.0, "shotSize": "全景", "camera": "固定镜头", "framePrompt": "教室全景"},
        ],
        blocking="美术教室，大窗在左侧晨光斜入。",
        clip_prompt="【镜头1｜0-5s】\n画面：女教师站在讲台前翻开教案。",
        ratio="16:9",
        visual_style="电影写实",
        world_summary="现代中国校园；自然日光",
        reference_assets=[{"slot": 1, "kind": "character", "name": "林晚", "appearance": "米白针织开衫"}],
        forbidden_names=("林晚",),
    )
    assert attempts == 2
    assert planned.grid_layout == "2x2"
    assert len(planned.cell_mapping) == 2
    assert "零黑块、零留白" in planned.image_prompt
    assert "林晚" not in planned.image_prompt
