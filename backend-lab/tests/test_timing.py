from unittest import TestCase

from framedrama_lab.generate import Source, chunk_ranges
from framedrama_lab.schema import Beat, EpisodeDraft, Outline
from framedrama_lab.timing import (
    beat_seconds, episode_problems, episode_seconds, episode_warnings, render_script, seconds_range,
)


def outline_dict():
    return {
        "continuity": "线索依次揭晓。",
        "characters": [{"id": "C01", "name": "陈九河", "role": "香头"}, {"id": "C02", "name": "栓子", "role": "徒弟"}],
        "scenes": [
            {"id": "S01", "name": "档案室", "kind": "内景", "time": "夜"},
            {"id": "S02", "name": "土路", "kind": "外景", "time": "夜"},
        ],
        "props": [{"id": "P01", "name": "旧马灯"}],
        "episodes": [{
            "number": 1, "title": "问路", "summary": "档案失踪。", "hook": "灯先灭。",
            "suspense": "门外有人。", "ending": "灯灭。",
            "characterIds": ["C01"], "sceneIds": ["S01"], "propIds": ["P01"],
        }],
    }


def balanced_flow():
    """5 个动作（12.5 秒）+ 18 句 25 字台词（100 秒）= 112.5 秒。"""
    flow = [{"action": "他抬眼看向门口。"}]
    for index in range(18):
        flow.append({"speaker": "C01", "line": ("台词内容正好凑够字数用来试跑时长" * 2)[:25]})
        if index % 6 == 5:
            flow.append({"action": "远处传来一声闷响。"})
    flow.append({"action": "灯灭了。"})
    return flow


def draft_dict(flow=None, hook_beat=(1, 1)):
    return {
        "number": 1, "title": "问路", "summary": "档案失踪。",
        "hook": "灯先灭。", "cliff": "门外有人。", "hookBeat": list(hook_beat),
        "scenes": [{
            "sceneId": "S01", "lighting": "台灯", "characters": ["C01"], "props": ["P01"],
            "flow": flow if flow is not None else balanced_flow(),
        }],
    }


def check(flow=None, target=120, hook_beat=(1, 1)):
    outline = Outline.model_validate(outline_dict())
    episode = EpisodeDraft.model_validate(draft_dict(flow, hook_beat))
    return outline, episode, episode_problems(episode, outline.episodes[0], outline, target)


class TimingTests(TestCase):
    def test_seconds_use_chars_per_second_and_action_cost(self):
        outline, episode, problems = check()
        self.assertEqual(beat_seconds(episode.scenes[0].flow[0]), 2.5)
        self.assertEqual(episode_seconds(episode), 112.5)
        self.assertEqual(problems, [])

    def test_beat_requires_exactly_one_kind(self):
        with self.assertRaises(ValueError):
            Beat.model_validate({"action": "灯灭。", "speaker": "C01", "line": "走。"})
        with self.assertRaises(ValueError):
            Beat.model_validate({"speaker": "C01"})

    def test_seconds_range_is_the_documented_budget(self):
        self.assertEqual(seconds_range(120), (102.0, 138.0))

    def test_valid_draft_passes_every_gate(self):
        outline, episode, problems = check(target=112)
        self.assertEqual(problems, [])

    def test_missing_action_beat_is_reported(self):
        _, _, problems = check([{"speaker": "C01", "line": "只有台词。"}])
        self.assertTrue(any("没有动作节拍" in item for item in problems))

    def test_line_over_limit_and_foreign_speaker_are_reported(self):
        _, _, problems = check([
            {"action": "他抬眼。"},
            {"speaker": "C02", "line": "这是一句超长台词" + "字" * 30},
        ])
        self.assertTrue(any("超过单句 35 字上限" in item for item in problems))
        self.assertTrue(any("说话人「C02」不在本场" in item for item in problems))

    def test_quotes_inside_action_are_reported(self):
        _, _, problems = check([
            {"action": "他说「快走」。"},
            {"speaker": "C01", "line": "快走。"},
        ])
        self.assertTrue(any("引号台词" in item for item in problems))

    def test_hook_must_land_in_the_first_three_beats(self):
        flow = [
            {"action": "一。"}, {"action": "二。"}, {"action": "三。"}, {"action": "四。"},
            {"speaker": "C01", "line": "钩子在这。"},
        ]
        _, _, problems = check(flow, hook_beat=(1, 5))
        self.assertTrue(any("冷开场" in item for item in problems))

    def test_hook_beat_out_of_range_is_reported(self):
        _, _, problems = check(hook_beat=(2, 1))
        self.assertTrue(any("指向不存在的场次" in item for item in problems))

    def test_duration_outside_tolerance_is_reported_in_both_directions(self):
        short = [{"action": "他抬眼。"}, {"speaker": "C01", "line": "太短了。"}]
        _, _, problems = check(short, target=120)
        self.assertTrue(any("短于可交付区间" in item and "距离目标还差约" in item for item in problems))
        _, _, problems = check(balanced_flow() * 3, target=60)
        self.assertTrue(any("超出可交付区间" in item and "比目标多出约" in item for item in problems))

    def test_a_short_episode_within_two_seconds_of_the_floor_is_delivered(self):
        flow = [{"speaker": "C01", "line": ("二十三字台词用于取整测试" * 2)[:23]} for _ in range(14)]
        flow += [{"action": "动作。"} for _ in range(7)]
        _, episode, problems = check(flow, target=120)
        seconds = episode_seconds(episode)
        self.assertGreaterEqual(seconds, 88.0)
        self.assertLess(seconds, 90.0)
        self.assertEqual([item for item in problems if "可交付区间" in item], [])

    def test_slightly_over_the_hard_cap_is_accepted(self):
        flow = [{"speaker": "C01", "line": ("二十五字台词用于取整测试" * 3)[:25]} for _ in range(18)]
        flow += [{"action": "动作。"} for _ in range(20)]
        flow.append({"speaker": "C01", "line": "嗯"})
        _, episode, problems = check(flow, target=120)
        self.assertEqual(episode_seconds(episode), 150.2)
        self.assertEqual([item for item in problems if "可交付区间" in item], [])

    def test_small_drift_is_delivered_with_a_warning(self):
        flow = [{"speaker": "C01", "line": ("三十字台词" * 6)[:30]} for _ in range(18)]
        flow += [{"action": "动作。"} for _ in range(10)]
        _, episode, problems = check(flow, target=120)
        self.assertEqual([item for item in problems if "区间" in item], [])
        self.assertEqual(episode_seconds(episode), 145.0)
        self.assertTrue(any("建议区间" in item for item in episode_warnings(episode, 120)))

    def test_unplanned_scene_and_cast_are_reported(self):
        data = draft_dict()
        data["scenes"][0]["sceneId"] = "S02"
        data["scenes"][0]["characters"] = ["C02"]
        outline = Outline.model_validate(outline_dict())
        episode = EpisodeDraft.model_validate(data)
        problems = episode_problems(episode, outline.episodes[0], outline, 120)
        self.assertTrue(any("没列进本集 characterIds" in item for item in problems))
        self.assertTrue(any("大纲没给本集安排" in item for item in problems))

    def test_render_script_writes_scene_heads_and_names(self):
        outline = Outline.model_validate(outline_dict())
        episode = EpisodeDraft.model_validate(draft_dict([
            {"action": "他抬眼看向门口。"},
            {"speaker": "C01", "line": "坐着说。"},
            {"speaker": "VO", "line": "风声压过一切。"},
        ]))
        text = render_script(episode, outline)
        self.assertTrue(text.startswith("第一场\n\n内景 · 档案室 · 夜\n\n他抬眼看向门口。"))
        self.assertIn("陈九河：坐着说。", text)
        self.assertIn("画外音：风声压过一切。", text)


class ChunkTests(TestCase):
    def test_prefers_chapter_headings(self):
        lines = ["第一章 纸灯", "档案不见了。", "第二章 夜访", "门开了。"]
        self.assertEqual(chunk_ranges(lines), [(1, 4)])

    def test_splits_long_text_without_headings(self):
        source = Source.from_text("upload", "\n".join(["字" * 100] * 200))
        ranges = chunk_ranges(source.lines)
        self.assertGreater(len(ranges), 1)
        self.assertEqual(ranges[0][0], 1)
        self.assertEqual(ranges[-1][1], 200)
        self.assertTrue(all(start <= end for start, end in ranges))

    def test_every_line_belongs_to_exactly_one_chunk(self):
        source = Source.from_text("upload", "\n".join(["字" * 80] * 90))
        ranges = chunk_ranges(source.lines)
        covered = [number for start, end in ranges for number in range(start, end + 1)]
        self.assertEqual(covered, list(range(1, 91)))
