from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

from constants import EVENT_KIND_LADDER, EVENT_KIND_OPEN_INVITATIONAL
from game.progression import (
    empty_event_progress,
    is_team_level_unlocked,
    min_team_level_for_class,
    normalize_event_progress,
    team_level_for_xp,
    team_xp_award,
    team_xp_progress,
    updated_event_progress,
)


class ProgressionTests(unittest.TestCase):
    def test_team_level_is_derived_from_thresholds(self) -> None:
        self.assertEqual(team_level_for_xp(-10), 1)
        self.assertEqual(team_level_for_xp(0), 1)
        self.assertEqual(team_level_for_xp(99), 1)
        self.assertEqual(team_level_for_xp(100), 2)
        self.assertEqual(team_level_for_xp(249), 2)
        self.assertEqual(team_level_for_xp(250), 3)
        self.assertEqual(team_level_for_xp(1300), 6)
        self.assertEqual(team_level_for_xp(9999), 6)

    def test_team_xp_progress_reports_next_level_window(self) -> None:
        progress = team_xp_progress(145)

        self.assertEqual(progress.level, 2)
        self.assertEqual(progress.level_start_xp, 100)
        self.assertEqual(progress.next_level, 3)
        self.assertEqual(progress.next_level_xp, 250)
        self.assertEqual(progress.xp_into_level, 45)
        self.assertEqual(progress.xp_needed_for_next, 105)
        self.assertAlmostEqual(progress.level_fraction, 0.3)

    def test_max_level_progress_has_no_next_level(self) -> None:
        progress = team_xp_progress(1400)

        self.assertEqual(progress.level, 6)
        self.assertIsNone(progress.next_level)
        self.assertIsNone(progress.next_level_xp)
        self.assertIsNone(progress.xp_needed_for_next)
        self.assertEqual(progress.level_fraction, 1.0)

    def test_default_team_level_gate_tracks_class_ladder(self) -> None:
        self.assertEqual(min_team_level_for_class("E"), 1)
        self.assertEqual(min_team_level_for_class("S"), 6)
        self.assertFalse(is_team_level_unlocked(99, 2))
        self.assertTrue(is_team_level_unlocked(100, 2))
        with self.assertRaises(ValueError):
            min_team_level_for_class("X")

    def test_first_win_gets_result_xp_and_first_win_bonus(self) -> None:
        award = team_xp_award(
            "E",
            EVENT_KIND_LADDER,
            position=1,
            is_dnf=False,
            event_progress_before=empty_event_progress(),
        )

        self.assertTrue(award.first_win)
        self.assertEqual(award.base_xp, 25)
        self.assertEqual(award.result_xp, 25)
        self.assertEqual(award.first_win_bonus, 25)
        self.assertEqual(award.total_xp, 50)

    def test_repeat_wins_ramp_down_gradually(self) -> None:
        first_repeat = team_xp_award("E", position=1, event_progress_before={"wins": 1})
        second_repeat = team_xp_award("E", position=1, event_progress_before={"wins": 2})
        late_repeat = team_xp_award("E", position=1, event_progress_before={"wins": 99})

        self.assertEqual(first_repeat.repeat_multiplier, 0.85)
        self.assertEqual(first_repeat.total_xp, 21)
        self.assertEqual(second_repeat.repeat_multiplier, 0.70)
        self.assertEqual(second_repeat.total_xp, 18)
        self.assertEqual(late_repeat.repeat_multiplier, 0.60)
        self.assertEqual(late_repeat.total_xp, 15)

    def test_non_win_finishes_scale_with_repeat_state_after_a_win(self) -> None:
        fresh_second = team_xp_award("D", position=2, event_progress_before={"wins": 0})
        repeat_second = team_xp_award("D", position=2, event_progress_before={"wins": 2})

        self.assertEqual(fresh_second.total_xp, 29)
        self.assertEqual(repeat_second.repeat_multiplier, 0.70)
        self.assertEqual(repeat_second.total_xp, 20)

    def test_open_invitational_multiplier_reduces_result_and_bonus(self) -> None:
        award = team_xp_award(
            "D",
            EVENT_KIND_OPEN_INVITATIONAL,
            position=1,
            is_dnf=False,
            event_progress_before={"wins": 0},
        )

        self.assertEqual(award.event_kind_multiplier, 0.70)
        self.assertEqual(award.result_xp, 31)
        self.assertEqual(award.first_win_bonus, 31)
        self.assertEqual(award.total_xp, 62)

    def test_dnf_awards_no_team_xp(self) -> None:
        award = team_xp_award("C", position=1, is_dnf=True, event_progress_before={"wins": 0})

        self.assertFalse(award.first_win)
        self.assertEqual(award.result_xp, 0)
        self.assertEqual(award.first_win_bonus, 0)
        self.assertEqual(award.total_xp, 0)

    def test_event_progress_records_result_without_mutating_input(self) -> None:
        before = {"starts": 1, "best_position": 3, "wins": 0, "podiums": 1, "best_time_s": 410.0}

        after = updated_event_progress(before, position=1, is_dnf=False, total_time_s=405.2)

        self.assertEqual(before["starts"], 1)
        self.assertEqual(after["starts"], 2)
        self.assertEqual(after["best_position"], 1)
        self.assertEqual(after["wins"], 1)
        self.assertEqual(after["podiums"], 2)
        self.assertEqual(after["best_time_s"], 405.2)

    def test_dnf_progress_only_records_start(self) -> None:
        after = updated_event_progress(None, position=8, is_dnf=True, total_time_s=500.0)

        self.assertEqual(after["starts"], 1)
        self.assertIsNone(after["best_position"])
        self.assertEqual(after["wins"], 0)
        self.assertEqual(after["podiums"], 0)
        self.assertIsNone(after["best_time_s"])

    def test_normalize_event_progress_preserves_extra_future_fields(self) -> None:
        progress = normalize_event_progress({"wins": 2, "custom_note": "future"})

        self.assertEqual(progress["starts"], 0)
        self.assertIsNone(progress["best_position"])
        self.assertEqual(progress["wins"], 2)
        self.assertEqual(progress["podiums"], 0)
        self.assertIsNone(progress["best_time_s"])
        self.assertEqual(progress["custom_note"], "future")

    def test_invalid_award_inputs_raise_clear_errors(self) -> None:
        with self.assertRaises(ValueError):
            team_xp_award("X")
        with self.assertRaises(ValueError):
            team_xp_award("E", event_kind="weird")
        with self.assertRaises(ValueError):
            team_xp_award("E", position=0)

    def test_progression_probe_tool_runs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "tools/probe_progression.py"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("Team XP Awards", result.stdout)
        self.assertIn("open_invitational", result.stdout)
        self.assertIn("Simple Ladder Path", result.stdout)
        self.assertIn("Lv 6", result.stdout)


if __name__ == "__main__":
    unittest.main()
