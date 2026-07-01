"""Dev event probe: is a race result the sim being honest or the sim being broken?

Usage (from repo root):
  python3 tools/probe_event.py <event_id> [--car <car_id>] [--driver <driver_id>] [-n N]

  <event_id>          event to probe, e.g. ridge_grand_prix
  --car <car_id>      your entry: adds the matchmaking view (anchor, band, peer pool)
  --driver <driver_id>  driver for outcome sims (default: first catalog driver)
  -n N                simulate N full races over seeds 1..N (default 30; 0 skips sims)

Three sections, using the exact same math as the game (game.opponents / game.simulation):
  1. Field   — every catalog car's natural lap on this event's track, PR/class, eligibility,
               and the event's pace-floor lap.
  2. Matching — given --car: the anchor lap, the +/- band, and the peer pool rivals are drawn
               from, each with its per-lap delta and projected margin over the race distance.
  3. Outcomes — given --car: N instant races; win rate, position spread, margin behind the
               winner, which models win, and how often each model appears on the grid.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState
from game.loader import load_cars, load_drivers, load_events, load_parts, load_tracks, resolve_race
from game.effective_stats import derived_class, derived_rating
from game.opponents import (
    _effective_rival_skill,
    _event_floor_lap,
    _event_peer_pool,
    _is_eligible,
    _natural_lap,
)
from game.simulation import simulate_race


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("event_id")
    parser.add_argument("--car", dest="car_id")
    parser.add_argument("--driver", dest="driver_id")
    parser.add_argument("-n", type=int, default=30, help="number of simulated races (0 = skip)")
    args = parser.parse_args()

    events = {event.id: event for event in load_events()}
    if args.event_id not in events:
        parser.error(f"unknown event: {args.event_id} (have: {', '.join(sorted(events))})")
    event = events[args.event_id]
    track = next(t for t in load_tracks() if t.id == event.track_id)
    parts = load_parts()
    cars = load_cars()
    race_format = resolve_race(event, track)

    length = f"{race_format.laps} laps" if race_format.laps else f"{race_format.duration_s:.0f}s duration"
    restrictions = ", ".join(f"{k}={v}" for k, v in (event.restrictions or {}).items()) or "none"
    print(f"== {event.name} ({event.id}) — {track.name}, {length}")
    print(
        f"   class limit {event.car_class_limit} | rival skill {_effective_rival_skill(event)}"
        f" | opponents {event.opponent_count} | fee ${event.entry_fee} | restrictions: {restrictions}"
    )

    profiles = sorted(
        ((_natural_lap(car, parts, track), car, _is_eligible(car, event, parts)) for car in cars),
        key=lambda item: item[0],
    )
    eligible_laps = [lap for lap, _car, ok in profiles if ok]
    floor_lap = _event_floor_lap(eligible_laps, event.car_class_limit)

    print(f"\n== Field: natural lap on {track.id} (no driver, no wear — the matchmaking metric)")
    print(f"   {'lap':>9}  {'car':26} {'cls':3} {'PR':>4}  eligible")
    for lap, car, ok in profiles:
        marker = " <- you" if car.identity.id == args.car_id else ""
        print(
            f"   {lap:9.3f}  {car.identity.id:26} {derived_class(car, parts):3}"
            f" {derived_rating(car, parts):4}  {'yes' if ok else '-'}{marker}"
        )
    print(f"   pace floor for class {event.car_class_limit}: {floor_lap:.3f}")

    if not args.car_id:
        return
    player_car = next((car for car in cars if car.identity.id == args.car_id), None)
    if player_car is None:
        parser.error(f"unknown car: {args.car_id}")
    if not _is_eligible(player_car, event, parts):
        print(f"\n!! {args.car_id} is not eligible for this event; matchmaking view is hypothetical.")

    player_lap = _natural_lap(player_car, parts, track)
    anchor = min(player_lap, floor_lap)
    # Mirror build_opponent_grid: rivals come from the eligible field minus the player's car.
    field = [deepcopy(car) for car in cars if car.identity.id != player_car.identity.id and _is_eligible(car, event, parts)]
    pool = _event_peer_pool(player_car, field, parts, track, event)
    race_laps = race_format.laps or (race_format.duration_s / anchor if race_format.duration_s else 0.0)

    from constants import RIVAL_MATCH_LAP_BAND_FRAC

    print(f"\n== Matchmaking for {args.car_id} (natural lap {player_lap:.3f})")
    anchor_src = "player pace" if player_lap <= floor_lap else f"event floor (player is slower)"
    print(
        f"   anchor {anchor:.3f} ({anchor_src}) | band ±{anchor * RIVAL_MATCH_LAP_BAND_FRAC:.3f}s/lap"
        f" | race ≈ {race_laps:.1f} laps"
    )
    print("   peer pool (negative delta = rival faster than you):")
    for rival in pool:
        delta = _natural_lap(rival, parts, track) - player_lap
        print(f"     {rival.identity.id:26} {delta:+7.3f}s/lap  {delta * race_laps:+8.1f}s over race")

    if args.n <= 0:
        return
    drivers = load_drivers()
    driver = next((d for d in drivers if d.id == args.driver_id), None) if args.driver_id else drivers[0]
    if driver is None:
        parser.error(f"unknown driver: {args.driver_id}")

    positions: Counter[int] = Counter()
    winners: Counter[str] = Counter()
    appearances: Counter[str] = Counter()
    margins: list[float] = []
    dnfs = 0
    for seed in range(1, args.n + 1):
        state = GameState(garage=[deepcopy(player_car)], money=10**9)
        result = simulate_race(state, event.id, player_car.identity.id, driver.id, seed=seed)
        for model in {s.label.split(" #")[0] for s in result.standings if not s.is_player}:
            appearances[model] += 1
        player = next(s for s in result.standings if s.is_player)
        if player.is_dnf:
            dnfs += 1
            continue
        winner = result.standings[0]
        winners["YOU" if winner.is_player else winner.label.split(" #")[0]] += 1
        positions[player.position] += 1
        margins.append(player.total_time - winner.total_time)

    finished = args.n - dnfs
    print(
        f"\n== Outcomes: {player_car.identity.id} + {driver.id}"
        f" (pace {driver.pace}, wet {driver.wet_skill}, cons {driver.consistency}), {args.n} sims"
    )
    if not finished:
        print("   every sim ended in a DNF")
        return
    wins = positions.get(1, 0)
    podiums = sum(count for pos, count in positions.items() if pos <= 3)
    avg_pos = sum(pos * count for pos, count in positions.items()) / finished
    print(
        f"   wins {wins}/{finished} ({wins / finished:.0%}) | podiums {podiums}/{finished}"
        f" | avg pos {avg_pos:.1f}" + (f" | DNF {dnfs}" if dnfs else "")
    )
    print("   positions: " + "  ".join(f"P{pos}×{positions[pos]}" for pos in sorted(positions)))
    print(
        f"   behind winner: avg {sum(margins) / len(margins):.1f}s"
        f" / min {min(margins):.1f}s / max {max(margins):.1f}s"
    )
    print("   race winner: " + "  ".join(f"{name}×{count}" for name, count in winners.most_common()))
    print("   on the grid: " + "  ".join(f"{name} {count}/{args.n}" for name, count in appearances.most_common()))


if __name__ == "__main__":
    main()
