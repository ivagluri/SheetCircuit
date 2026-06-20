"""Interactive, text-mode car & track creator (rich-only).

Run with ``python3 creator.py``. The editor groups every schema knob into
sections so nothing is hidden but nothing is overwhelming, validates against the
real game loader before saving, and surfaces a live PR / lap-profile readout so
you can sculpt a car or track toward a target as you go.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from game.effective_stats import class_rating, performance_type, compute_effective_stats
from game.loader import (
    DATA_ROOT,
    DataLoadError,
    car_from_dict,
    derive_weights,
    event_from_dict,
    load_tracks,
    resolve_race,
    track_from_dict,
)
from game.models import TrackSegment
from interfaces.terminal import terminal

from editor.fields import (
    CAR_SCHEMA,
    EVENT_SCHEMA,
    SEGMENT_FIELDS,
    SEGMENT_TEMPLATE,
    SEGMENT_TAGS,
    Schema,
    Section,
    FieldSpec,
    TRACK_SCHEMA,
    TRACK_SECTIONS,
)


def event_draft_to_json(draft: dict) -> dict:
    """Translate the editor's flattened event draft into real event JSON.

    The draft carries race_mode + race_value and flattened restriction knobs for the
    generic field engine; the stored event has exactly one race-length field and a
    restrictions dict (the shape the loader validates).
    """
    event: dict[str, Any] = {
        "id": draft["id"],
        "name": draft["name"],
        "track_id": draft["track_id"],
        "car_class_limit": draft["car_class_limit"],
        "entry_fee": int(draft["entry_fee"]),
        "prize_money": list(draft["prize_money"]),
        "opponent_count": int(draft["opponent_count"]),
    }
    if int(draft.get("rival_skill", 0)) > 0:
        event["rival_skill"] = int(draft["rival_skill"])
    mode = draft["race_mode"]
    value = draft["race_value"]
    event[mode] = int(value) if mode == "laps" else float(value)
    restrictions: dict[str, Any] = {}
    if int(draft.get("restr_max_power_hp", 0)) > 0:
        restrictions["max_power_hp"] = int(draft["restr_max_power_hp"])
    if int(draft.get("restr_max_class_rating", 0)) > 0:
        restrictions["max_class_rating"] = int(draft["restr_max_class_rating"])
    if draft.get("restr_allowed_tires"):
        restrictions["allowed_tires"] = list(draft["restr_allowed_tires"])
    event["restrictions"] = restrictions
    return event


def event_json_to_draft(event: dict) -> dict:
    """Inverse of event_draft_to_json: load a stored event into the flattened draft."""
    draft = copy.deepcopy(EVENT_SCHEMA.template)
    for key in ("id", "name", "track_id", "car_class_limit", "entry_fee", "prize_money", "opponent_count"):
        if key in event:
            draft[key] = event[key]
    draft["rival_skill"] = event.get("rival_skill") or 0
    for mode in ("laps", "distance_km", "duration_s"):
        if event.get(mode) is not None:
            draft["race_mode"] = mode
            draft["race_value"] = event[mode]
            break
    restrictions = event.get("restrictions") or {}
    draft["restr_max_power_hp"] = restrictions.get("max_power_hp", 0)
    draft["restr_max_class_rating"] = restrictions.get("max_class_rating", 0)
    draft["restr_allowed_tires"] = list(restrictions.get("allowed_tires", []))
    return draft


# --- draft helpers ----------------------------------------------------------
def _get(draft: dict, path: tuple[str, ...]) -> Any:
    node: Any = draft
    for key in path:
        node = node[key]
    return node


def _set(draft: dict, path: tuple[str, ...], value: Any) -> None:
    node = draft
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def _deep_merge(base: dict, override: dict) -> dict:
    """Template-shaped copy of ``base`` with values from ``override`` laid on top."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


# --- coercion / validation --------------------------------------------------
def coerce(spec: FieldSpec, raw: str, current: Any) -> Any:
    """Turn typed input into a stored value, raising ValueError with a hint."""
    raw = raw.strip()
    if spec.kind == "int":
        value: Any = int(round(float(raw)))
    elif spec.kind == "float":
        value = float(raw)
    elif spec.kind in ("str",):
        value = raw
    elif spec.kind == "enum":
        value = _resolve_choice(spec, raw)
        return value
    elif spec.kind == "tags":
        return _resolve_tags(spec, raw, current)
    elif spec.kind == "ints":
        try:
            return [int(tok) for tok in raw.replace(",", " ").split()]
        except ValueError as exc:
            raise ValueError("enter whole numbers, comma/space separated") from exc
    else:
        raise ValueError(f"unknown field kind {spec.kind}")

    if spec.kind in ("int", "float"):
        if spec.minimum is not None and value < spec.minimum:
            raise ValueError(f"must be >= {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            raise ValueError(f"must be <= {spec.maximum}")
    return value


def _resolve_choice(spec: FieldSpec, raw: str) -> str:
    choices = list(spec.choices)
    if raw.isdigit() and choices:
        idx = int(raw) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
        raise ValueError(f"pick 1..{len(choices)}")
    for choice in choices:
        if raw.lower() == choice.lower():
            return choice
    if spec.free_choices:
        return raw
    raise ValueError(f"one of: {', '.join(choices)}")


def _resolve_tags(spec: FieldSpec, raw: str, current: Any) -> list[str]:
    if raw.lower() in ("none", "-", "clear"):
        return []
    choices = list(spec.choices)
    tokens = [t for t in raw.replace(",", " ").split() if t]
    result: list[str] = []
    for token in tokens:
        if token.isdigit() and choices:
            idx = int(token) - 1
            if not (0 <= idx < len(choices)):
                raise ValueError(f"index {token} out of range 1..{len(choices)}")
            tag = choices[idx]
        else:
            match = next((c for c in choices if c.lower() == token.lower()), None)
            if match is None and not spec.free_choices:
                raise ValueError(f"unknown tag '{token}'")
            tag = match or token
        if tag not in result:
            result.append(tag)
    return result


_SUBDIR = {"car": "cars", "track": "tracks", "event": "events"}


def _payload(schema: Schema, draft: dict) -> dict:
    """The dict that actually gets written/validated (events are translated first)."""
    return event_draft_to_json(draft) if schema.kind == "event" else draft


def validate(schema: Schema, draft: dict) -> tuple[bool, str]:
    if not str(_get(draft, schema.id_path)).strip():
        return False, "id is required before saving"
    try:
        if schema.kind == "car":
            car_from_dict(copy.deepcopy(draft))
        elif schema.kind == "track":
            track_from_dict(copy.deepcopy(draft))
        else:
            payload = event_draft_to_json(draft)
            event = event_from_dict(payload)
            tracks = {t.id: t for t in load_tracks()}
            if event.track_id not in tracks:
                return False, f"unknown track_id '{event.track_id}'"
            resolve_race(event, tracks[event.track_id])
    except (DataLoadError, KeyError, TypeError, ValueError) as exc:
        return False, str(exc)
    return True, "valid"


def save_draft(schema: Schema, draft: dict) -> Path:
    ok, message = validate(schema, draft)
    if not ok:
        raise ValueError(message)
    path = DATA_ROOT / _SUBDIR[schema.kind] / f"{_get(draft, schema.id_path)}.json"
    path.write_text(json.dumps(_payload(schema, draft), indent=2) + "\n", encoding="utf-8")
    return path


# --- live previews ----------------------------------------------------------
def car_preview(draft: dict) -> list[str]:
    try:
        car = car_from_dict(copy.deepcopy(draft))
    except (DataLoadError, KeyError, TypeError, ValueError) as exc:
        return [f"[red]incomplete:[/red] {exc}"]
    eff = compute_effective_stats(car)
    return [
        f"[bold]PR {class_rating(car)}[/bold]  class [cyan]{car.identity.car_class}[/cyan]"
        f"  ({performance_type(car)})",
        f"power {eff.power:.0f}  accel {eff.acceleration:.0f}  top {eff.top_speed:.0f}"
        f"  grip {eff.grip:.0f}  brake {eff.braking:.0f}  handling {eff.handling:.0f}",
        f"aero {eff.aero_grip:.0f}  drag {eff.drag:.0f}  reliability {eff.reliability:.0f}"
        f"  weight {eff.weight:.0f}kg  drivetrain {eff.drivetrain}",
    ]


def track_preview(draft: dict) -> list[str]:
    segments = draft.get("segments", [])
    total = sum(float(s.get("length_pct", 0.0)) for s in segments)
    flag = "[green]OK[/green]" if abs(total - 1.0) <= 0.001 else "[red]must total 1.000[/red]"
    lines = [f"segments: {len(segments)}   length sum: {total:.3f} {flag}"]
    try:
        length_km = float(draft.get("length_km", 0.0))
        base = float(draft.get("base_lap_time", 0.0))
        lines.append(
            f"one lap: {length_km:g} km @ base_lap_time {base:g}s"
            "   (race length is set per-event; attrition scales with distance)"
        )
        if length_km > 0:
            # base_lap_time is just distance/speed — suggest values for common avg paces.
            suggest = "  ".join(f"{kmh}km/h→{length_km / kmh * 3600:.0f}s" for kmh in (90, 130, 170))
            lines.append(f"suggested base_lap_time: {suggest}")
    except (TypeError, ValueError):
        pass
    try:
        seg_objs = [TrackSegment(**s) for s in segments]
        weights = derive_weights(seg_objs)
        emphasis = ", ".join(
            f"{dim} {val:.0%}" for dim, val in sorted(weights.items(), key=lambda kv: -kv[1]) if val > 0.0
        )
        lines.append(f"emphasis: {emphasis or '—'}")
    except (TypeError, DataLoadError) as exc:
        lines.append(f"[yellow]profile pending:[/yellow] {exc}")
    return lines


def event_preview(draft: dict) -> list[str]:
    try:
        payload = event_draft_to_json(draft)
        event = event_from_dict(payload)
        tracks = {t.id: t for t in load_tracks()}
    except (DataLoadError, KeyError, TypeError, ValueError) as exc:
        return [f"[red]incomplete:[/red] {exc}"]
    if event.track_id not in tracks:
        return [f"[red]unknown track_id '{event.track_id}'[/red] — pick an existing track"]
    track = tracks[event.track_id]
    fmt = resolve_race(event, track)
    if fmt.laps is not None:
        race = f"{fmt.mode}: {fmt.laps} laps × {track.length_km:g} km = {fmt.laps * track.length_km:.0f} km"
    else:
        race = f"duration: {fmt.duration_s / 3600:.1f} h (not raceable yet)"
    restr = ", ".join(f"{k}={v}" for k, v in (payload.get("restrictions") or {}).items()) or "none"
    return [
        f"[bold]{event.name or '(unnamed)'}[/bold] on [cyan]{track.name}[/cyan]",
        race,
        f"class ≤ {event.car_class_limit}   field {event.opponent_count}   fee ${event.entry_fee}   restrictions: {restr}",
    ]


# ===========================================================================
class CreatorApp:
    def __init__(self) -> None:
        self.term = terminal

    # -- low-level prompts --------------------------------------------------
    def ask(self, label: str) -> str:
        try:
            return input(f"{label}: ").strip()
        except EOFError:
            return "q"

    def note(self, text: str) -> None:
        self.term.print(text)

    def pause(self) -> None:
        self.term.pause()

    # -- entry --------------------------------------------------------------
    def run(self) -> None:
        if not sys.stdin.isatty():
            self.note("The creator is interactive; run it from a terminal (TTY).")
            return
        while True:
            self.term.clear()
            self.term.header(
                "SheetCircuit Creator",
                "Interactive track & car editor — plugs straight into the game data",
            )
            self.term.menu(
                "[C] New car    [T] New track    [V] New event\n"
                "[E] Edit car   [K] Edit track    [F] Edit event\n"
                "[Q] Quit"
            )
            choice = self.ask("Choice").lower()
            if choice in ("q", "quit", ""):
                return
            if choice == "c":
                self.edit(CAR_SCHEMA, copy.deepcopy(CAR_SCHEMA.template))
            elif choice == "t":
                self.edit(TRACK_SCHEMA, copy.deepcopy(TRACK_SCHEMA.template))
            elif choice == "v":
                self.edit(EVENT_SCHEMA, copy.deepcopy(EVENT_SCHEMA.template))
            elif choice == "e":
                self.open_existing(CAR_SCHEMA, "cars")
            elif choice == "k":
                self.open_existing(TRACK_SCHEMA, "tracks")
            elif choice == "f":
                self.open_existing(EVENT_SCHEMA, "events")

    def open_existing(self, schema: Schema, subdir: str) -> None:
        files = sorted((DATA_ROOT / subdir).glob("*.json"))
        if not files:
            self.note("No files to edit.")
            self.pause()
            return
        self.term.table(
            f"Existing {subdir}",
            ["#", "file"],
            [[i + 1, p.name] for i, p in enumerate(files)],
        )
        raw = self.ask("Open # (Enter to cancel)")
        if not raw.isdigit():
            return
        idx = int(raw) - 1
        if not (0 <= idx < len(files)):
            return
        loaded = json.loads(files[idx].read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            self.note("That file bundles multiple records; the creator edits one-per-file.")
            self.pause()
            return
        if schema.kind == "event":
            loaded = event_json_to_draft(loaded)
        draft = _deep_merge(schema.template, loaded)
        self.edit(schema, draft)

    # -- main editor loop ---------------------------------------------------
    def edit(self, schema: Schema, draft: dict) -> None:
        sections = list(schema.sections)
        is_track = schema.kind == "track"
        while True:
            self.term.clear()
            label = _get(draft, schema.id_path) or "(unnamed)"
            self.term.header(
                f"Editing {schema.kind}: {label}",
                "Pick a section to edit. Save validates against the game loader.",
            )
            rows = [[str(i + 1), s.title] for i, s in enumerate(sections)]
            if is_track:
                seg_count = len(draft.get("segments", []))
                rows.append(["S", f"Segments  ({seg_count})"])
            self.term.table("Sections", ["#", "section"], rows)
            preview = {"track": track_preview, "event": event_preview}.get(schema.kind, car_preview)(draft)
            for line in preview:
                self.note(line)
            self.term.menu("number = edit section   [W] write/save   [B] back")
            raw = self.ask("Choice").strip()
            low = raw.lower()
            if low in ("b", "q", ""):
                return
            if low == "w":
                self._save(schema, draft)
                continue
            if is_track and low == "s":
                self.edit_segments(draft)
                continue
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(sections):
                    self.edit_section(schema, draft, sections[idx])

    def _save(self, schema: Schema, draft: dict) -> None:
        ok, message = validate(schema, draft)
        if not ok:
            self.note(f"[red]Cannot save:[/red] {message}")
            self.pause()
            return
        target = DATA_ROOT / _SUBDIR[schema.kind] / f"{_get(draft, schema.id_path)}.json"
        if target.exists():
            if self.ask(f"{target.name} exists — overwrite? (y/N)").lower() != "y":
                return
        path = save_draft(schema, draft)
        self.note(f"[green]Saved[/green] {path}")
        self.pause()

    # -- section field loop -------------------------------------------------
    def edit_section(self, schema: Schema, draft: dict, section: Section) -> None:
        while True:
            self.term.clear()
            self.term.header(f"{schema.kind} · {section.title}")
            rows = []
            for i, spec in enumerate(section.fields):
                value = _get(draft, spec.path)
                rows.append([
                    str(i + 1),
                    spec.label,
                    self._fmt(value),
                    self._domain(spec),
                    spec.help,
                ])
            self.term.table(section.title, ["#", "field", "value", "domain", "help"], rows)
            self.term.menu("number = edit field   [B] back")
            raw = self.ask("Field").strip()
            if raw.lower() in ("b", "q", ""):
                return
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(section.fields):
                    self.edit_field(draft, section.fields[idx])

    def edit_field(self, draft: dict, spec: FieldSpec) -> None:
        current = _get(draft, spec.path)
        self.note(f"\n[bold]{spec.label}[/bold]  current: {self._fmt(current)}")
        if spec.help:
            self.note(f"  {spec.help}")
        if spec.choices:
            for i, choice in enumerate(spec.choices):
                self.note(f"  [{i + 1}] {choice}")
            if spec.free_choices:
                self.note("  (or type any value)")
        if spec.kind == "tags":
            self.note("  enter tags by number/name, space or comma separated; 'none' clears")
        raw = self.ask("New value (Enter to keep)")
        if raw == "":
            return
        try:
            value = coerce(spec, raw, current)
        except ValueError as exc:
            self.note(f"[red]Rejected:[/red] {exc}")
            self.pause()
            return
        _set(draft, spec.path, value)

    # -- segment list editor ------------------------------------------------
    def edit_segments(self, draft: dict) -> None:
        segments: list[dict] = draft.setdefault("segments", [])
        while True:
            self.term.clear()
            self.term.header(
                "Track Segments",
                "Order matters; length_pct must total 1.000. Tags shape each segment's demands.",
            )
            rows = []
            for i, seg in enumerate(segments):
                rows.append([
                    str(i + 1),
                    seg.get("name", ""),
                    f"{float(seg.get('length_pct', 0)):.3f}",
                    ", ".join(seg.get("tags", [])),
                    seg.get("surface", ""),
                    seg.get("condition", ""),
                ])
            self.term.table(
                "Segments", ["#", "name", "len", "tags", "surface", "cond"], rows
            )
            for line in track_preview(draft):
                self.note(line)
            self.term.menu(
                "number = edit   [A] add   [D <n>] delete   [N] normalize lengths   [B] back"
            )
            raw = self.ask("Choice").strip()
            low = raw.lower()
            if low in ("b", "q", ""):
                return
            if low == "a":
                segments.append(copy.deepcopy(SEGMENT_TEMPLATE))
                self.edit_segment(segments[-1])
            elif low == "n":
                self._normalize(segments)
            elif low.startswith("d"):
                rest = raw[1:].strip()
                if rest.isdigit():
                    idx = int(rest) - 1
                    if 0 <= idx < len(segments):
                        segments.pop(idx)
            elif raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(segments):
                    self.edit_segment(segments[idx])

    def _normalize(self, segments: list[dict]) -> None:
        total = sum(float(s.get("length_pct", 0.0)) for s in segments)
        if total <= 0:
            return
        for seg in segments:
            seg["length_pct"] = round(float(seg.get("length_pct", 0.0)) / total, 4)
        # Nudge the largest segment so rounding still sums to exactly 1.0.
        drift = round(1.0 - sum(s["length_pct"] for s in segments), 4)
        if drift and segments:
            biggest = max(segments, key=lambda s: s["length_pct"])
            biggest["length_pct"] = round(biggest["length_pct"] + drift, 4)

    def edit_segment(self, seg: dict) -> None:
        while True:
            self.term.clear()
            self.term.header(f"Segment · {seg.get('name', '')}")
            rows = []
            for i, spec in enumerate(SEGMENT_FIELDS):
                rows.append([
                    str(i + 1), spec.label, self._fmt(seg.get(spec.key)),
                    self._domain(spec), spec.help,
                ])
            self.term.table("Segment", ["#", "field", "value", "domain", "help"], rows)
            self.term.menu("number = edit field   [B] back")
            raw = self.ask("Field").strip()
            if raw.lower() in ("b", "q", ""):
                return
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(SEGMENT_FIELDS):
                    spec = SEGMENT_FIELDS[idx]
                    current = seg.get(spec.key)
                    self.note(f"\n[bold]{spec.label}[/bold]  current: {self._fmt(current)}")
                    if spec.help:
                        self.note(f"  {spec.help}")
                    if spec.choices:
                        for j, choice in enumerate(spec.choices):
                            self.note(f"  [{j + 1}] {choice}")
                    if spec.kind == "tags":
                        self.note("  space/comma separated numbers or names; 'none' clears")
                    val = self.ask("New value (Enter to keep)")
                    if val == "":
                        continue
                    try:
                        seg[spec.key] = coerce(spec, val, current)
                    except ValueError as exc:
                        self.note(f"[red]Rejected:[/red] {exc}")
                        self.pause()

    # -- formatting helpers -------------------------------------------------
    @staticmethod
    def _fmt(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(map(str, value)) or "—"
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    @staticmethod
    def _domain(spec: FieldSpec) -> str:
        if spec.choices:
            shown = list(spec.choices)
            text = "/".join(shown if len(shown) <= 4 else shown[:4] + ["…"])
            return text + (" (+free)" if spec.free_choices else "")
        if spec.minimum is not None or spec.maximum is not None:
            lo = "" if spec.minimum is None else f"{spec.minimum:g}"
            hi = "" if spec.maximum is None else f"{spec.maximum:g}"
            return f"{lo}..{hi}"
        return spec.kind


def main() -> None:
    CreatorApp().run()
