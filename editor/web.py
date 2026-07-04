"""Event-driven adapter that drives the creator for the browser (Pyodide) build.

The terminal creator blocks on ``input()`` (every prompt funnels through
``CreatorApp.ask``); a browser cannot. ``WebCreator`` re-expresses those nested
menu loops as an input-mode state machine with a string-in / string-out surface,
reusing the editor's pure value layer (schemas, coerce, validate, save_draft,
previews) untouched.

Unlike interfaces/web.py this adapter assembles output strings directly instead
of capturing stdout: every editor building block is already list-of-lines shaped,
and bypassing the ``terminal`` singleton keeps CPython test output byte-identical
to the browser even when rich is installed locally.

Saving cannot write to a repo from a static page, so a save writes into the
(in-browser) data dir — keeping open/clone pickers and validation live — and
hands the JSON to the JS shell via ``js_request`` to download and to stash in
localStorage.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from compendium import registry
from editor import app as editor_app
from editor.app import (
    CreatorApp,
    SIM_MODE_NAMES,
    _deep_merge,
    _get,
    _set,
    car_preview,
    coerce,
    event_json_to_draft,
    event_preview,
    track_preview,
    validate,
)
from editor.fields import (
    CAR_ARCHETYPES,
    CAR_SCHEMA,
    CAR_TEMPLATE,
    EVENT_SCHEMA,
    SEGMENT_FIELDS,
    SEGMENT_TEMPLATE,
    FieldSpec,
    Schema,
    Section,
    TRACK_SCHEMA,
)
from interfaces.terminal import Terminal

MODE_MENU = "menu"
MODE_NEW_CAR = "new_car"
MODE_CLONE = "clone"
MODE_OPEN = "open"
MODE_EDIT = "edit"
MODE_GUARD = "guard"
MODE_OVERWRITE = "overwrite"
MODE_SAVE_AS = "save_as"
MODE_SECTION = "section"
MODE_FIELD = "field"
MODE_SEGMENTS = "segments"
MODE_SEGMENT = "segment"
MODE_SEG_FIELD = "seg_field"
MODE_SIM_TRACK = "sim_track"

_CANCEL_WORDS = ("b", "q", "")

_PROMPT_LABELS = {
    MODE_MENU: "Choice",
    MODE_NEW_CAR: "Template # (Enter to cancel)",
    MODE_CLONE: "Clone # (Enter to cancel)",
    MODE_OPEN: "Open # (Enter to cancel)",
    MODE_EDIT: "Choice",
    MODE_GUARD: "Unsaved — [s] save  [d] discard  [any] keep editing",
    MODE_OVERWRITE: "[y] overwrite  [d] save as new id  [N] cancel",
    MODE_SAVE_AS: "New id (Enter to cancel)",
    MODE_SECTION: "Field",
    MODE_FIELD: "New value (Enter to keep)",
    MODE_SEGMENTS: "Choice",
    MODE_SEGMENT: "Field",
    MODE_SEG_FIELD: "New value (Enter to keep)",
    MODE_SIM_TRACK: "Track # (Enter to keep)",
}

# Allowlist of rich tags the previews/sim lines embed. A generic \[.*?\] would
# also eat legitimate literal text like "[M] cycle" and "[s] save".
_MARKUP = re.compile(r"\[/?(?:bold|red|green|yellow|cyan|magenta|blue|dim|italic|underline)\]")


def strip_markup(text: str) -> str:
    return _MARKUP.sub("", text)


class _PlainTerminal(Terminal):
    """Terminal locked to the plain-text path regardless of rich availability."""

    def __init__(self) -> None:
        self._console = None


_PLAIN = _PlainTerminal()


def _table(title: str, headers: list[str], rows: list[list[Any]]) -> list[str]:
    return _PLAIN._plain_table_lines(title, headers, rows)


class WebCreator:
    def __init__(self) -> None:
        self.app = CreatorApp()  # hosts sim state + _sim_lines; run() is never called
        self.mode = MODE_MENU
        self.schema: Schema | None = None
        self.draft: dict | None = None
        self.saved: dict | None = None
        self.section: Section | None = None
        self.field: FieldSpec | None = None
        self.seg_index: int | None = None
        self.seg_field: FieldSpec | None = None
        self.js_request: dict | None = None
        self._files: list[Path] = []
        self._open_schema: Schema | None = None
        self._open_subdir = ""
        self._exit_after_save = False
        self._notices: list[str] = []
        self._view = ""

    # ------------------------------------------------------------------ API

    def render(self) -> str:
        if not self._view:
            self._view = self._compose()
        return self._view

    def handle_input(self, raw: str) -> str:
        raw = (raw or "").strip()
        self._notices = []
        handler = {
            MODE_MENU: self._menu_input,
            MODE_NEW_CAR: self._new_car_input,
            MODE_CLONE: self._clone_input,
            MODE_OPEN: self._open_input,
            MODE_EDIT: self._edit_input,
            MODE_GUARD: self._guard_input,
            MODE_OVERWRITE: self._overwrite_input,
            MODE_SAVE_AS: self._save_as_input,
            MODE_SECTION: self._section_input,
            MODE_FIELD: self._field_input,
            MODE_SEGMENTS: self._segments_input,
            MODE_SEGMENT: self._segment_input,
            MODE_SEG_FIELD: self._seg_field_input,
            MODE_SIM_TRACK: self._sim_track_input,
        }[self.mode]
        handler(raw)
        self._view = self._compose()
        return self._view

    def ui_meta(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "kind": self.schema.kind if self.schema else None,
                "dirty": bool(self.draft is not None and self.draft != self.saved),
                "prompt_label": _PROMPT_LABELS[self.mode],
                "buttons": self._buttons(),
                "js_request": self.js_request,
            }
        )

    def clear_js_request(self) -> None:
        self.js_request = None

    def import_record(self, payload: str) -> str:
        """Bring an uploaded JSON record into the session's data dir."""
        self._notices = []
        try:
            data = json.loads(payload)
            if isinstance(data, list):
                raise ValueError("file bundles multiple records; the creator edits one-per-file")
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            if "segments" in data:
                schema = TRACK_SCHEMA
            elif "track_id" in data:
                schema = EVENT_SCHEMA
                data = event_json_to_draft(data)
            else:
                schema = CAR_SCHEMA
            draft = _deep_merge(schema.template, data)
            path = editor_app.save_draft(schema, draft)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            self._notices.append(f"Import failed: {exc}")
        else:
            self._set_js_request(schema, path, download=False)
            if schema.kind == "track":
                self._refresh_tracks()
            self._notices.append(f"Imported {path.name}.")
        self._view = self._compose()
        return self._view

    def delete_record(self, relpath: str) -> str:
        """Remove a session record; relpath is the stash key, e.g. data/cars/x.json."""
        self._notices = []
        root = Path(editor_app.DATA_ROOT).resolve()
        target = (root / relpath.removeprefix("data/")).resolve()
        if not (target.is_relative_to(root) and target.suffix == ".json"):
            self._notices.append(f"Refusing to remove {relpath}.")
        elif target.exists():
            target.unlink()
            if target.parent.name == "tracks":
                self._refresh_tracks()
            self._notices.append(f"Removed {target.name}.")
        else:
            self._notices.append(f"{relpath} not found.")
        self._view = self._compose()
        return self._view

    # -------------------------------------------------------------- helpers

    def _refresh_tracks(self) -> None:
        # Pass the root explicitly: load_tracks' default is bound at import time,
        # so it wouldn't follow a swapped editor_app.DATA_ROOT (tests patch it).
        self.app.sim_tracks = {t.id: t for t in editor_app.load_tracks(Path(editor_app.DATA_ROOT))}

    def _open_editor(self, schema: Schema, draft: dict) -> None:
        self.schema = schema
        self.draft = draft
        self.saved = copy.deepcopy(draft)
        self.mode = MODE_EDIT

    def _close_editor(self) -> None:
        self.schema = None
        self.draft = None
        self.saved = None
        self.mode = MODE_MENU

    def _data_dir(self, subdir: str) -> Path:
        return Path(editor_app.DATA_ROOT) / subdir

    def _load_record(self, path: Path) -> dict | None:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            self._notices.append("That file bundles multiple records; the creator edits one-per-file.")
            return None
        return loaded

    def _current_field_spec(self, spec: FieldSpec) -> FieldSpec:
        """The spec to edit with, refreshing the event track_id enum from the live
        data dir so tracks created this session are selectable (the module-level
        choices were globbed once at import)."""
        if self.schema is not None and self.schema.kind == "event" and spec.path == ("track_id",):
            track_ids = tuple(sorted(p.stem for p in self._data_dir("tracks").glob("*.json")))
            return dataclasses.replace(spec, choices=track_ids)
        return spec

    def _set_js_request(self, schema: Schema, path: Path, download: bool = True) -> None:
        text = path.read_text(encoding="utf-8")
        request: dict[str, Any] = {
            "stash": {"path": f"data/{editor_app._SUBDIR[schema.kind]}/{path.name}", "content": text}
        }
        if download:
            request["download"] = {"filename": path.name, "content": text}
        self.js_request = request

    # ------------------------------------------------------------ save flow

    def _begin_save(self, exit_after: bool) -> None:
        self._exit_after_save = exit_after
        ok, message = validate(self.schema, self.draft)
        if not ok:
            self._notices.append(f"Cannot save: {message}")
            self.mode = MODE_EDIT
            self._exit_after_save = False
            return
        if self._save_target().exists():
            self.mode = MODE_OVERWRITE
            return
        self._write()

    def _save_target(self) -> Path:
        record_id = _get(self.draft, self.schema.id_path)
        return self._data_dir(editor_app._SUBDIR[self.schema.kind]) / f"{record_id}.json"

    def _write(self) -> None:
        path = editor_app.save_draft(self.schema, self.draft)
        self._set_js_request(self.schema, path)
        self.saved = copy.deepcopy(self.draft)
        if self.schema.kind == "track":
            self._refresh_tracks()
        self._notices.append(f"Saved {path.name} — downloading a copy (drop it in data/ to contribute it).")
        if self._exit_after_save:
            self._close_editor()
        else:
            self.mode = MODE_EDIT
        self._exit_after_save = False

    def _cancel_save(self) -> None:
        self._exit_after_save = False
        self.mode = MODE_EDIT
        self._notices.append("Save cancelled.")

    # -------------------------------------------------------- input handling

    def _menu_input(self, raw: str) -> None:
        low = raw.lower()
        if low == "q":
            self._notices.append("This is a browser tool — close the tab to quit.")
        elif low == "c":
            self.mode = MODE_NEW_CAR
        elif low == "t":
            self._open_editor(TRACK_SCHEMA, copy.deepcopy(TRACK_SCHEMA.template))
        elif low == "v":
            self._open_editor(EVENT_SCHEMA, copy.deepcopy(EVENT_SCHEMA.template))
        elif low in ("e", "k", "f"):
            schema, subdir = {
                "e": (CAR_SCHEMA, "cars"),
                "k": (TRACK_SCHEMA, "tracks"),
                "f": (EVENT_SCHEMA, "events"),
            }[low]
            files = sorted(self._data_dir(subdir).glob("*.json"))
            if not files:
                self._notices.append("No files to edit.")
                return
            self._files = files
            self._open_schema = schema
            self._open_subdir = subdir
            self.mode = MODE_OPEN

    def _new_car_input(self, raw: str) -> None:
        low = raw.lower()
        if low in _CANCEL_WORDS:
            self.mode = MODE_MENU
            return
        if low == "c":
            files = sorted(self._data_dir("cars").glob("*.json"))
            if not files:
                self._notices.append("No cars to clone.")
                self.mode = MODE_MENU
                return
            self._files = files
            self.mode = MODE_CLONE
            return
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(CAR_ARCHETYPES):
                _name, _help, overrides = CAR_ARCHETYPES[idx]
                self._open_editor(CAR_SCHEMA, _deep_merge(CAR_TEMPLATE, overrides))

    def _clone_input(self, raw: str) -> None:
        if not raw.isdigit() or not (0 <= int(raw) - 1 < len(self._files)):
            self.mode = MODE_MENU
            return
        loaded = self._load_record(self._files[int(raw) - 1])
        if loaded is None:
            self.mode = MODE_MENU
            return
        draft = _deep_merge(CAR_SCHEMA.template, loaded)
        _set(draft, CAR_SCHEMA.id_path, "")  # force a new id before it can be saved
        self._open_editor(CAR_SCHEMA, draft)

    def _open_input(self, raw: str) -> None:
        if not raw.isdigit() or not (0 <= int(raw) - 1 < len(self._files)):
            self.mode = MODE_MENU
            return
        loaded = self._load_record(self._files[int(raw) - 1])
        if loaded is None:
            self.mode = MODE_MENU
            return
        schema = self._open_schema
        if schema.kind == "event":
            loaded = event_json_to_draft(loaded)
        self._open_editor(schema, _deep_merge(schema.template, loaded))

    def _edit_input(self, raw: str) -> None:
        low = raw.lower()
        is_car = self.schema.kind == "car"
        if low in _CANCEL_WORDS:
            if self.draft == self.saved:
                self._close_editor()
            else:
                self.mode = MODE_GUARD
            return
        if low == "w":
            self._begin_save(exit_after=False)
            return
        if is_car and low == "g":
            self.mode = MODE_SIM_TRACK
            return
        if is_car and low == "m":
            self.app.sim_mode = (self.app.sim_mode + 1) % len(SIM_MODE_NAMES)
            return
        if self.schema.kind == "track" and low == "s":
            self.mode = MODE_SEGMENTS
            return
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(self.schema.sections):
                self.section = self.schema.sections[idx]
                self.mode = MODE_SECTION

    def _guard_input(self, raw: str) -> None:
        low = raw.lower()
        if low == "s":
            self._begin_save(exit_after=True)
        elif low == "d":
            self._close_editor()
        else:
            self.mode = MODE_EDIT

    def _overwrite_input(self, raw: str) -> None:
        low = raw.lower()
        if low == "y":
            self._write()
        elif low == "d":
            self.mode = MODE_SAVE_AS
        else:
            self._cancel_save()

    def _save_as_input(self, raw: str) -> None:
        current = _get(self.draft, self.schema.id_path)
        if not raw or raw == str(current):
            self._cancel_save()
            return
        _set(self.draft, self.schema.id_path, raw)
        # Re-run the conflict check against the new id, mirroring _save's loop.
        if self._save_target().exists():
            self.mode = MODE_OVERWRITE
        else:
            self._write()

    def _section_input(self, raw: str) -> None:
        if raw.lower() in _CANCEL_WORDS:
            self.mode = MODE_EDIT
            return
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(self.section.fields):
                self.field = self._current_field_spec(self.section.fields[idx])
                self.mode = MODE_FIELD

    def _field_input(self, raw: str) -> None:
        if raw == "":
            self.mode = MODE_SECTION
            return
        try:
            value = coerce(self.field, raw, _get(self.draft, self.field.path))
        except ValueError as exc:
            self._notices.append(f"Rejected: {exc}")
            return  # stay in the field so the value can be retried
        _set(self.draft, self.field.path, value)
        self.mode = MODE_SECTION

    def _segments(self) -> list[dict]:
        # Alias into the draft (mirrors app.py edit_segments) so the dirty check
        # and previews see in-place edits.
        return self.draft.setdefault("segments", [])

    def _segments_input(self, raw: str) -> None:
        low = raw.lower()
        segments = self._segments()
        if low in _CANCEL_WORDS:
            self.mode = MODE_EDIT
            return
        if low == "a":
            segments.append(copy.deepcopy(SEGMENT_TEMPLATE))
            self.seg_index = len(segments) - 1
            self.mode = MODE_SEGMENT
            return
        if low == "n":
            self.app._normalize(segments)
            return
        if low.startswith("d"):
            rest = raw[1:].strip()
            if rest.isdigit() and 0 <= int(rest) - 1 < len(segments):
                segments.pop(int(rest) - 1)
            return
        if raw.isdigit() and 0 <= int(raw) - 1 < len(segments):
            self.seg_index = int(raw) - 1
            self.mode = MODE_SEGMENT

    def _segment_input(self, raw: str) -> None:
        if raw.lower() in _CANCEL_WORDS:
            self.mode = MODE_SEGMENTS
            return
        if raw.isdigit() and 0 <= int(raw) - 1 < len(SEGMENT_FIELDS):
            self.seg_field = SEGMENT_FIELDS[int(raw) - 1]
            self.mode = MODE_SEG_FIELD

    def _seg_field_input(self, raw: str) -> None:
        if raw == "":
            self.mode = MODE_SEGMENT
            return
        seg = self._segments()[self.seg_index]
        try:
            seg[self.seg_field.key] = coerce(self.seg_field, raw, seg.get(self.seg_field.key))
        except ValueError as exc:
            self._notices.append(f"Rejected: {exc}")
            return
        self.mode = MODE_SEGMENT

    def _sim_track_input(self, raw: str) -> None:
        tracks = list(self.app.sim_tracks.values())
        if raw.isdigit() and 0 <= int(raw) - 1 < len(tracks):
            self.app.sim_track_id = tracks[int(raw) - 1].id
        self.mode = MODE_EDIT

    # ------------------------------------------------------------- rendering

    def _compose(self) -> str:
        lines = {
            MODE_MENU: self._menu_view,
            MODE_NEW_CAR: self._new_car_view,
            MODE_CLONE: self._files_view,
            MODE_OPEN: self._files_view,
            MODE_EDIT: self._edit_view,
            MODE_GUARD: self._guard_view,
            MODE_OVERWRITE: self._overwrite_view,
            MODE_SAVE_AS: self._save_as_view,
            MODE_SECTION: self._section_view,
            MODE_FIELD: self._field_view,
            MODE_SEGMENTS: self._segments_view,
            MODE_SEGMENT: self._segment_view,
            MODE_SEG_FIELD: self._seg_field_view,
            MODE_SIM_TRACK: self._sim_track_view,
        }[self.mode]()
        lines.extend(self._notices)
        return "\n".join(lines)

    def _menu_view(self) -> list[str]:
        return [
            "SheetCircuit Creator",
            "Interactive track & car editor — runs entirely in your browser.",
            "Saving validates against the game loader and downloads the JSON;",
            "contribute finished files back to the repo's data/ via a PR.",
            "",
            "[C] New car    [T] New track    [V] New event",
            "[E] Edit car   [K] Edit track    [F] Edit event",
        ]

    def _new_car_view(self) -> list[str]:
        rows = [[str(i + 1), name, help] for i, (name, help, _) in enumerate(CAR_ARCHETYPES)]
        rows.append(["C", "Clone existing car", "start from a copy of a catalog car"])
        return [
            "New car",
            "Pick a starting template, then tweak the big knobs.",
            "",
            *_table("Templates", ["#", "template", "notes"], rows),
        ]

    def _files_view(self) -> list[str]:
        if self.mode == MODE_CLONE:
            title, header = "Clone which car", "Clone which car"
        else:
            title, header = f"Existing {self._open_subdir}", f"Edit {self._open_subdir}"
        rows = [[i + 1, p.name] for i, p in enumerate(self._files)]
        return [header, "", *_table(title, ["#", "file"], rows)]

    def _edit_body(self) -> list[str]:
        schema, draft = self.schema, self.draft
        label = _get(draft, schema.id_path) or "(unnamed)"
        rows = [[str(i + 1), s.title] for i, s in enumerate(schema.sections)]
        if schema.kind == "track":
            rows.append(["S", f"Segments  ({len(draft.get('segments', []))})"])
        preview = {"track": track_preview, "event": event_preview}.get(schema.kind, car_preview)(draft)
        lines = [
            f"Editing {schema.kind}: {label}",
            "Pick a section to edit. Save validates against the game loader.",
            "",
            *_table("Sections", ["#", "section"], rows),
            *(strip_markup(line) for line in preview),
        ]
        if schema.kind == "car":
            lines.extend(strip_markup(line) for line in self.app._sim_lines(draft))
        return lines

    def _edit_view(self) -> list[str]:
        menu = "number = edit section   [W] write/save   [B] back"
        if self.schema.kind == "car":
            menu += "   [G] sim track   [M] cycle view"
        return [*self._edit_body(), "", menu]

    def _guard_view(self) -> list[str]:
        return [*self._edit_body(), "", "Unsaved changes — [s] save  [d] discard & exit  [any] keep editing"]

    def _overwrite_view(self) -> list[str]:
        return [*self._edit_body(), "", f"{self._save_target().name} exists — [y] overwrite  [d] save as new id  [N] cancel"]

    def _save_as_view(self) -> list[str]:
        current = _get(self.draft, self.schema.id_path)
        return [*self._edit_body(), "", f"New id (current: {current}; Enter to cancel)"]

    def _section_view(self) -> list[str]:
        rows = []
        for i, spec in enumerate(self.section.fields):
            spec = self._current_field_spec(spec)
            value = _get(self.draft, spec.path)
            rows.append([str(i + 1), spec.label, self.app._fmt(value), self.app._domain(spec), spec.help])
        lines = [
            f"{self.schema.kind} · {self.section.title}",
            "",
            *_table(self.section.title, ["#", "field", "value", "domain", "help"], rows),
        ]
        if self.schema.kind == "car":
            lines.extend(strip_markup(line) for line in self.app._sim_lines(self.draft))
        return [*lines, "", "number = edit field   [B] back"]

    def _field_detail(self, spec: FieldSpec, current: Any) -> list[str]:
        lines = [f"{spec.label}  current: {self.app._fmt(current)}"]
        if spec.help:
            lines.append(f"  {spec.help}")
        domain = self.schema.kind if self.schema else ""
        entry = registry.entry_for(domain, spec.path) if domain else None
        if entry and entry.prose:
            lines.append(f"  {entry.prose}")
        if spec.choices:
            lines.extend(f"  [{i + 1}] {choice}" for i, choice in enumerate(spec.choices))
            if spec.free_choices:
                lines.append("  (or type any value)")
        if spec.kind == "tags":
            lines.append("  enter tags by number/name, space or comma separated; 'none' clears")
        return lines

    def _field_view(self) -> list[str]:
        return self._field_detail(self.field, _get(self.draft, self.field.path))

    def _segments_view(self) -> list[str]:
        rows = []
        for i, seg in enumerate(self._segments()):
            rows.append([
                str(i + 1),
                seg.get("name", ""),
                f"{float(seg.get('length_pct', 0)):.3f}",
                ", ".join(seg.get("tags", [])),
                seg.get("surface", ""),
                seg.get("condition", ""),
            ])
        return [
            "Track Segments",
            "Order matters; length_pct must total 1.000. Tags shape each segment's demands.",
            "",
            *_table("Segments", ["#", "name", "len", "tags", "surface", "cond"], rows),
            *(strip_markup(line) for line in track_preview(self.draft)),
            "",
            "number = edit   [A] add   [D <n>] delete   [N] normalize lengths   [B] back",
        ]

    def _segment_view(self) -> list[str]:
        seg = self._segments()[self.seg_index]
        rows = [
            [str(i + 1), spec.label, self.app._fmt(seg.get(spec.key)), self.app._domain(spec), spec.help]
            for i, spec in enumerate(SEGMENT_FIELDS)
        ]
        return [
            f"Segment · {seg.get('name', '')}",
            "",
            *_table("Segment", ["#", "field", "value", "domain", "help"], rows),
            "",
            "number = edit field   [B] back",
        ]

    def _seg_field_view(self) -> list[str]:
        seg = self._segments()[self.seg_index]
        return self._field_detail(self.seg_field, seg.get(self.seg_field.key))

    def _sim_track_view(self) -> list[str]:
        tracks = list(self.app.sim_tracks.values())
        rows = [[i + 1, t.name, t.layout_type, f"{t.length_km:g}"] for i, t in enumerate(tracks)]
        return _table("Sim anchor track", ["#", "track", "layout", "km"], rows)

    # --------------------------------------------------------------- buttons

    def _buttons(self) -> list[list[str]]:
        if self.mode == MODE_MENU:
            return [["c", "New car"], ["t", "New track"], ["v", "New event"],
                    ["e", "Edit car"], ["k", "Edit track"], ["f", "Edit event"]]
        if self.mode == MODE_NEW_CAR:
            return [["c", "Clone existing"], ["", "Cancel"]]
        if self.mode in (MODE_CLONE, MODE_OPEN):
            return [["", "Cancel"]]
        if self.mode == MODE_EDIT:
            buttons = [["w", "Save"], ["b", "Back"]]
            if self.schema.kind == "car":
                buttons += [["g", "Sim track"], ["m", "Cycle view"]]
            if self.schema.kind == "track":
                buttons += [["s", "Segments"]]
            return buttons
        if self.mode == MODE_GUARD:
            return [["s", "Save & exit"], ["d", "Discard"], ["k", "Keep editing"]]
        if self.mode == MODE_OVERWRITE:
            return [["y", "Overwrite"], ["d", "Save as new id"], ["n", "Cancel"]]
        if self.mode == MODE_SAVE_AS:
            return [["", "Cancel"]]
        if self.mode in (MODE_SECTION, MODE_SEGMENT):
            return [["b", "Back"]]
        if self.mode in (MODE_FIELD, MODE_SEG_FIELD):
            return [["", "Keep current"]]
        if self.mode == MODE_SEGMENTS:
            return [["a", "Add segment"], ["n", "Normalize"], ["b", "Back"]]
        if self.mode == MODE_SIM_TRACK:
            return [["", "Keep current"]]
        return []
