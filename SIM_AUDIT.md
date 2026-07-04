# Simulation Audit Plan

Findings from a full engine audit (simulation.py, race_session.py, effective_stats.py,
telemetry.py, opponents.py, loader.py, constants.py, plus the economy/actions layers),
each verified against the running game. Ordered by severity within each section.
Status legend: **fixed** = landed, **planned** = agreed work, **decide** = needs a design
call before any code is written.

## 1. Verified bugs

### 1.1 Event detail screen crashes whenever the garage is non-empty — fixed

`game/actions.py` (`_estimate_entry`) called `class_rating(compute_effective_stats(car, parts))`
at two sites, but `class_rating` takes a `Car` (it computes effective stats itself). Any
career state (the starter car is always present) → events screen → open an event detail →
`AttributeError: 'EffectiveCarStats' object has no attribute 'installed_parts'`.
Fix: pass the `Car` straight through (`class_rating(car, parts)`). Regression test:
`event_detail_screen(event_id, state)` with a garage car must return an "Est. Time" row.

### 1.2 Race log re-emits stale events every lap — fixed

`race_session.simulate_tick` published `state.event_log[-3:]` at every lap end, but
`event_log` is cumulative and never cleared, so a one-time event (a rival's lap-3
mechanical issue) was re-logged on every later lap and warnings snowballed into multiple
copies per lap. A second defect in the same code: a car that crashed out mid-lap was
skipped on all later ticks, so its "crashed out" message never reached the race log at all
unless the crash tick happened to be a lap end.
Fix: track a published-count watermark per car (`RaceCarState.event_log_published`) and
publish only unpublished entries — at lap end for running cars, immediately on DNF.
Regression test: no message may appear in the session race log more often than it appears
in the cars' own event logs.

## 2. Design holes (attrition has no endgame and the AI can't play it) — fixed

These three were one theme and landed together; they define the long-race strategy layer.

- **Empty fuel tank has no consequence — fixed.** A dry tank now adds
  `FUEL_EMPTY_PACE_FRACTION` (0.35) of base_lap_time per lap: the car limps (a ~90s lap
  becomes ~120s) but can still crawl to the pits and refuel — devastating for the
  result, recoverable as strategy. Wired through `_state_penalty`, so the instant sim
  shows the same crawl honestly.
- **Tire temperature only ever rises — fixed.** Heat is now a *balance*: an always-on
  passive cooling (linear in seconds, preserving the exact segment↔aggregate
  integration invariant, which rules out temperature-dependent Newtonian cooling) fights
  the gain. Passive rates sit near a mid car's normal-pace gain: gentle cars drift back
  to the operating floor (`TIRE_OPTIMAL_C` / `INITIAL_ENGINE_TEMP_C` — both previously
  dead constants, now wired), thermally demanding cars (Detroit V8, Blackpool V12) creep
  and must lift — thermal character. Cooling commands multiply the passive rate
  (`TIRE_COOLING_BOOST` 3.0 / `ENGINE_COOLING_BOOST` 3.5). The pre-fix enduro ended with
  the whole field at 122–144°C; it now ends 90–108°C with hot cars held just under
  overheat by the AI.
- **The AI has no survival tools — fixed.** `_ai_command` is now a rule-based pit boss:
  pit when tyres/fuel cross `AI_PIT_TIRE_PCT`/`AI_PIT_FUEL_PCT`, lift to the matching
  cooling command past an overheat threshold, push only in a close battle when healthy.
  Mechanical failures can now be terminal for anyone (`telemetry.failure_dnf_chance`:
  `FAILURE_DNF_PROB` base, rising steeply with engine temp past overheat), so attrition
  racing exists on both sides. Pit stops are logged ("X pitted (+Ns)").
  Future refinement: race-remaining awareness (don't pit from P2 on the final lap for
  29% tyres) and fuel-to-finish arithmetic instead of a flat threshold.

## 3. Half-wired systems — fixed (all five wired, not cut)

- **Mid-race damage — fixed.** A medium mistake dings `condition_pct`
  (`CONDITION_HIT_MISTAKE`), a non-terminal mechanical issue damages it harder
  (`CONDITION_HIT_FAILURE`); damage feeds `failure_chance` (issues beget issues) and a
  share carries into post-race garage wear (`RACE_DAMAGE_WEAR_FACTOR`). `driver_energy`
  is live: fatigue adds mistake risk (`MISTAKE_FATIGUE_SCALE`, zero when fresh so
  baselines don't shift) and an exhausted driver leaks pace below
  `DRIVER_ENERGY_LOW_PCT` (up to `DRIVER_ENERGY_PACE_FRACTION` of the lap).
- **Post-race wear — fixed.** Overall wear now scales with real race distance
  (`WEAR_PER_RACE_BASE` x race_km / `WEAR_REFERENCE_RACE_KM`, clamped), sub-systems wear
  alongside at per-system rates (`SUBCONDITION_WEAR_FACTORS` — engines age faster than
  bodywork), and resale depreciates with condition and mileage
  (`economy._resale_factor`), so racing has a real cost on the way out of the garage.
- **Overtaking — fixed.** Live races contest passes: `_contest_overtakes` walks the road
  ahead nearest-first; a move sticks on a roll against `_pass_chance` (per-lap base x
  (1 − `track.overtake_difficulty`) x racecraft edge, slice-scaled so it is
  resolution-invariant), a failed move holds the car in dirty air at the follow gap
  (stacking into trains), and sweeping past a crippled car (pitted/crawling) is free.
  `overtake_difficulty` and `racecraft` are both live. Instant sim carries none of it,
  same as jitter/reactive push. *Regression fix (post-`d936448`)*: the first cut froze
  every field — cars tied at the start (no established position) were contested, so the
  whole grid trained up behind whichever car was processed first (the player, on
  stable-sorted ties) at exactly the follow gap, and a won roll never reordered the
  road because ranking is by `total_time`. Now a defender must have been strictly ahead
  at tick start (a dead heat spreads on pace alone) and a won contest completes the
  pass by exchanging the pair's race clocks (time-conserving), logged to the race log.
- **Race-day weather — fixed.** One forecast roll per race (`loader.roll_race_condition`,
  isolated rng stream so pace/mistake draws are untouched): `weather_variability` is the
  chance the race doesn't run in the default condition, usually damp, sometimes wet
  (`WEATHER_WET_SHARE`). Applied by escalating the session track's segment profiles
  (`apply_race_condition`; never dries an authored-wet segment; aggregate re-derived so
  the integration invariant holds). Both engines roll it; the balance baseline's seed 7
  is now a wet race and was re-pinned. Shown in the race screen; mid-race weather
  changes remain a future step.
- **Calendar — fixed.** Each race consumes a week (both engines). Weekly salaries are
  implemented behind `SALARY_WEEKLY_ENABLED` (each hired driver costs
  `SALARY_WEEKLY_FRACTION` of their hire fee per week raced); the flag stays off until
  the economy is balanced for it.

## 4. Redundancies / dead code — fixed

- **`FUEL_WEIGHT_PENALTY_PER_L` — wired.** Fuel load is lap time: a full tank is the
  reference and every burned litre buys `FUEL_WEIGHT_PENALTY_PER_L` seconds per lap
  (in `_state_penalty`, so both engines carry it). Brimming the tank at a stop now
  costs pace until it burns off — the last piece of the pit-strategy loop.
  `RACE_DISTANCE_LAP_PROGRESS` deleted; `SALARY_WEEKLY_ENABLED` was wired by Section 3;
  `TIRE_OPTIMAL_C` by Section 2.
- ~~`_initial_state` hardcodes 85.0/90.0~~ — fixed with the Section-2 work; it now uses
  `INITIAL_TIRE_TEMP_C` / `INITIAL_ENGINE_TEMP_C`.
- **Effective-stats cache — fixed.** `RaceSession.effective_stats` is computed once per
  entry in `enter_event` (ticks read the cache; a fallback recompute covers sessions
  built without it), and `simulate_race` caches per entry before its loop. Live ticks
  dropped to ~0.06ms (the per-tick recompute alone was ~0.4ms with 8 cars).
- **Double sort — fixed.** `simulate_tick` now filters actives and lets `_rank` do the
  single sort; `_active_standings` remains for the early-return path.
- **`class_rating` alias — kept deliberately.** It is the established public name at
  ~30 call sites across game/interfaces/editor/tests; `derived_rating` is the
  implementation name. Removing either is churn with no behavior gain.

## 5. Minor / latent — fixed

- **Tick RNG stride — fixed.** Seeds now stride by `MAX_TICKS_PER_LAP + 1` per lap, so
  (lap, sub_tick) pairs can never collide at any tick density (the old stride of 100
  collided on realtime laps or any lap over ~665s canonical).
- **`simulate_to_end_action` pit loop — fixed.** The run-to-flag loop drops the command
  to `normal` after the stop completes, mirroring the pit one-shot (the CLI resumes the
  prior command; the action layer defaults to normal). `advance_to_lap_end_action`
  stops at the first lap end, so one call was already one pit.
- **`simulate_race` entry fee — fixed.** The batch summary charges the fee like the
  live engine (without the funds gate — it runs on throwaway states in tools).
- **Player DNF doesn't finish the session — confirmed intended.** The field races on;
  the player spectates or types `end` to skip to the flag. The DNF row stays pinned in
  the standings.
- `wet_grip` skips the camber factor that dry grip gets — noted, left as is (camber is
  tuned against dry contact-patch behaviour; wet pace is dominated by the wet_weight
  blend).
