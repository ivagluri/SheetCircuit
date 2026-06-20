"""Race length lives on the event, resolved against the track.

Tracks are geometry-only (no lap count). An event specifies exactly one of laps /
distance_km / duration_s; resolve_race turns that into a concrete RaceFormat. Duration
is parsed and represented but the race loop does not run it yet.
"""

from __future__ import annotations

import unittest

from game.loader import DataLoadError, event_from_dict, load_tracks, resolve_race
from game.models import Event, Track


def _event(**kwargs) -> Event:
    base = dict(
        id="e", name="E", track_id="t", car_class_limit="A", entry_fee=0,
        prize_money=[0], opponent_count=3, restrictions={},
    )
    base.update(kwargs)
    return Event(**base)


class RaceFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracks = {t.id: t for t in load_tracks()}
        self.track = self.tracks["maple_short"]  # 2.1 km/lap

    def test_no_track_carries_laps(self) -> None:
        self.assertFalse(hasattr(self.track, "laps"))

    def test_laps_format(self) -> None:
        fmt = resolve_race(_event(laps=5), self.track)
        self.assertEqual((fmt.mode, fmt.laps), ("laps", 5))

    def test_distance_resolves_to_lap_count(self) -> None:
        fmt = resolve_race(_event(distance_km=21.0), self.track)
        self.assertEqual(fmt.mode, "distance")
        self.assertEqual(fmt.laps, round(21.0 / self.track.length_km))  # 10

    def test_distance_rounds_up_to_at_least_one_lap(self) -> None:
        fmt = resolve_race(_event(distance_km=0.1), self.track)
        self.assertEqual(fmt.laps, 1)

    def test_duration_is_open_ended(self) -> None:
        fmt = resolve_race(_event(duration_s=86400), self.track)
        self.assertEqual(fmt.mode, "duration")
        self.assertIsNone(fmt.laps)
        self.assertEqual(fmt.duration_s, 86400)

    def test_event_requires_exactly_one_race_length(self) -> None:
        payload = dict(
            id="bad", name="Bad", track_id="t", car_class_limit="A", entry_fee=0,
            prize_money=[0], opponent_count=1, restrictions={},
        )
        with self.assertRaises(DataLoadError):
            event_from_dict(dict(payload))  # none specified
        with self.assertRaises(DataLoadError):
            event_from_dict(dict(payload, laps=5, distance_km=10))  # two specified

    def test_seed_events_are_all_resolvable(self) -> None:
        from game.loader import load_events

        for event in load_events():
            fmt = resolve_race(event, self.tracks[event.track_id])
            self.assertIn(fmt.mode, ("laps", "distance", "duration"))


if __name__ == "__main__":
    unittest.main()
