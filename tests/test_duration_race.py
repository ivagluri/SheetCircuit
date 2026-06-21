"""Phase 4.2 — duration (Regime A) races run on the lockstep engine.

A ``duration_s`` event used to raise "Duration-based races are not yet supported". Now both
the batch engine and the interactive session run whole laps until the leader crosses the
time cap, then finish the lead lap. Because the field is lockstep, watch-live and
instant-resolve are the same code path and must produce the identical result, and a longer
cap simply runs more laps -- which, for a thirsty car, forces a real fuel/tyre stop.
"""

from __future__ import annotations

from copy import deepcopy
import unittest
from unittest import mock

from game.actions import advance_race_action, simulate_to_end_action
from game.game_state import GameState
from game.loader import load_cars, load_events
from game.models import Event
from game.race_session import enter_event
from game.simulation import simulate_race


def _duration_event(event_id: str, track_id: str, duration_s: float) -> Event:
    return Event(
        id=event_id, name=event_id, track_id=track_id, car_class_limit="S",
        entry_fee=0, prize_money=[0] * 8, opponent_count=3, restrictions={},
        rival_skill=None, laps=None, distance_km=None, duration_s=duration_s,
    )


class _Injected:
    """Patch the event catalog seen by both race engines with one extra event."""

    def __init__(self, event: Event) -> None:
        self._event = event
        self._patches = [
            mock.patch(f"game.{mod}.load_events", side_effect=lambda: [*load_events(), self._event])
            for mod in ("simulation", "race_session")
        ]

    def __enter__(self):
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in self._patches:
            patch.stop()


class DurationRaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cars = {c.identity.id: c for c in load_cars()}

    def _beater(self) -> object:
        car = deepcopy(self.cars["kanto_k660"])
        car.condition.overall_condition = 70.0  # satisfy the beater_enduro restriction
        return car

    def test_shipped_duration_event_runs_to_completion(self) -> None:
        # beater_enduro is a duration_s event in the catalog; it must resolve to a finite,
        # multi-lap race rather than raising the old "not yet supported" guard.
        gs = GameState(garage=[self._beater()])
        result = simulate_race(gs, "beater_enduro", "kanto_k660", "driver_novak", seed=3)
        self.assertGreater(result.total_laps, 1)
        player = next(s for s in result.standings if s.is_player)
        # The race ends just past the 1200 s cap on the lead lap, never before it.
        self.assertGreaterEqual(player.total_time, 1200.0)

    def test_watch_live_and_instant_resolve_match(self) -> None:
        # The interactive engine driven tick-by-tick (watch live) and all-at-once
        # (instant resolve) are the same lockstep code path => identical finish.
        def run(instant: bool):
            gs = GameState(garage=[self._beater()])
            gs.money = 10 ** 7
            session = enter_event(gs, "beater_enduro", "kanto_k660", "driver_novak", seed=3)
            if instant:
                simulate_to_end_action(session, "normal")
            else:
                while not session.is_finished:
                    advance_race_action(session, "normal")
            player = next(s for s in session.cars if s.is_player)
            return session.current_lap, round(player.total_time, 4), player.position

        self.assertEqual(run(instant=False), run(instant=True))

    def test_a_longer_cap_runs_more_laps(self) -> None:
        # Regime A: the only thing the cap changes is how many whole laps run.
        def laps_for(duration_s: float) -> int:
            event = _duration_event("dur_len", "cresta_speed_run", duration_s)
            with _Injected(event):
                gs = GameState(garage=[deepcopy(self.cars["blackpool_twelve"])])
                return simulate_race(gs, "dur_len", "blackpool_twelve", "driver_novak", seed=2).total_laps

        self.assertGreater(laps_for(1200.0), laps_for(600.0))

    def test_long_enduro_forces_a_thirsty_car_to_stop(self) -> None:
        # The thirsty escarpa_pikes finishes a short sprint with fuel in hand but is drained
        # dry over a long enduro on the same fuel-hungry track -- a real strategy difference.
        def fuel_left(duration_s: float) -> float:
            event = _duration_event("dur_thirst", "cresta_speed_run", duration_s)
            with _Injected(event):
                gs = GameState(garage=[deepcopy(self.cars["escarpa_pikes"])])
                result = simulate_race(gs, "dur_thirst", "escarpa_pikes", "driver_novak", seed=2)
                return next(s for s in result.standings if s.is_player).fuel_pct

        self.assertGreater(fuel_left(600.0), 20.0)   # short race: still has a margin
        self.assertLessEqual(fuel_left(1800.0), 5.0)  # long race: forced to refuel


if __name__ == "__main__":
    unittest.main()
