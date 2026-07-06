"""Shared screen shell: the one input contract every screen obeys.

Universal keys (b/back, q/quit, ?/h/help), the slash palette (/save /home
/ref /quit /help), the navigation breadcrumb, and the auto-generated footer
all live here so no screen can drift from the contract. Screens declare a
breadcrumb label plus their local key table; the shell renders the chrome and
intercepts everything universal before the screen sees the input.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from interfaces.terminal import terminal


BACK_WORDS = frozenset({"b", "back"})
QUIT_WORDS = frozenset({"q", "quit"})
HELP_WORDS = frozenset({"?", "h", "help"})

# Palette commands work from any screen; /load stays Home-only because it
# discards the current career.
PALETTE_COMMANDS = {
    "/save": "save",
    "/home": "home",
    "/menu": "home",
    "/ref": "ref",
    "/load": "load",
    "/quit": "quit",
    "/help": "help",
}

UNIVERSAL_FOOTER = "[b Back]  [? Help]  [q Quit]"


class GoHome(Exception):
    """Unwinds nested screen loops straight back to the Home screen."""


@dataclass(frozen=True)
class LocalKey:
    key: str                      # short form, e.g. "w"
    label: str                    # footer label, e.g. "Apply"
    words: tuple[str, ...] = ()   # spelled-out aliases, e.g. ("write", "apply")
    description: str = ""         # one-liner for the help view

    def matches(self, low: str) -> bool:
        return low == self.key.lower() or low in self.words


@dataclass(frozen=True)
class Action:
    kind: str        # "back" | "quit" | "help" | "palette" | "local" | "text" | "empty" | "unknown_palette"
    value: str = ""  # palette command, matched local key, or the raw text


@dataclass
class Screen:
    name: str                                   # breadcrumb label
    keys: tuple[LocalKey, ...] = ()             # local key table (footer + dispatch)
    render: Callable[[], None] | None = None    # full redraw (chrome + body)
    dirty: Callable[[], bool] | None = None     # staged edits present?
    help: Callable[[], None] | None = None      # context help below the universal tables


def dispatch(raw: str, keys: tuple[LocalKey, ...] = ()) -> Action:
    """Pure input dispatcher: universal keys and the palette are un-shadowable,
    then the screen's local keys, then free text for the screen to interpret."""
    text = raw.strip()
    if not text:
        return Action("empty")
    low = text.lower()
    if low.startswith("/"):
        name = PALETTE_COMMANDS.get(low.split()[0])
        if name == "quit":
            return Action("quit")
        if name == "help":
            return Action("help")
        if name is not None:
            return Action("palette", name)
        return Action("unknown_palette", text)
    if low in BACK_WORDS:
        return Action("back")
    if low in QUIT_WORDS:
        return Action("quit")
    if low in HELP_WORDS:
        return Action("help")
    for key in keys:
        if key.matches(low):
            return Action("local", key.key)
    return Action("text", text)


def footer_line(keys: tuple[LocalKey, ...] = ()) -> str:
    """The fixed-height footer: local keys first, always ending with the trio."""
    parts = [f"[{key.key} {key.label}]" for key in keys]
    parts.append(UNIVERSAL_FOOTER)
    return "  ".join(parts)


def confirm(prompt: str) -> bool:
    raw = terminal.prompt(f"{prompt} [y/N]").strip().lower()
    return raw in {"y", "yes"}


def universal_help_tables() -> None:
    """The contract itself, shown at the top of every help view."""
    terminal.table(
        "Universal Keys (work on every screen)",
        ["Key", "Action"],
        [
            ["b / back", "Go back one level (cancel a picker, leave a detail view)"],
            ["q / quit", "Quit the game (asks to confirm)"],
            ["? / h / help", "This help"],
        ],
    )
    terminal.table(
        "Slash Palette (works from any screen)",
        ["Command", "Action"],
        [
            ["/save", "Save the career right now"],
            ["/home (or /menu)", "Jump straight to the Home menu"],
            ["/ref", "Open the compendium, then return here"],
            ["/quit  /help", "Same as q and ?"],
            ["/load", "Load a save (Home screen only)"],
        ],
    )


class Shell:
    """Owns the navigation stack and runs the universal contract for every
    prompt inside modal screens (pickers, editors, detail views)."""

    def __init__(self) -> None:
        self.stack: list[Screen] = []
        self.save_handler: Callable[[], None] | None = None   # /save
        self.ref_handler: Callable[[], None] | None = None    # /ref overlay
        self.help_handler: Callable[[], None] | None = None   # default context help
        self.quit_prompt = "Quit the game?"                    # the creator overrides this

    # -- navigation stack ----------------------------------------------------
    @contextmanager
    def screen(self, screen: Screen):
        self.stack.append(screen)
        try:
            yield screen
        finally:
            self.stack.pop()

    @property
    def active(self) -> Screen | None:
        return self.stack[-1] if self.stack else None

    def breadcrumb(self, root: str = "Home") -> str:
        return " › ".join(([root] if root else []) + [screen.name for screen in self.stack])

    def any_dirty(self) -> bool:
        return any(screen.dirty is not None and screen.dirty() for screen in self.stack)

    # -- chrome ----------------------------------------------------------------
    def render_chrome(self, root: str = "Home") -> None:
        terminal.print_plain(self.breadcrumb(root))

    def footer(self) -> str:
        keys = self.active.keys if self.active is not None else ()
        return footer_line(keys)

    # -- the one prompt every modal screen uses --------------------------------
    def prompt(self, label: str, *, empty: str = "ignore") -> Action:
        """Render the footer, read input, and intercept everything universal.

        Returns only "back", "local", or "text" actions (and "empty" as "back"
        when ``empty='back'`` — detail screens treat Enter as return). Quit,
        help, and the palette never reach the calling screen.
        """
        while True:
            terminal.print_plain(self.footer())
            while True:
                try:
                    raw = terminal.prompt(label)
                except EOFError:
                    return Action("back")
                action = dispatch(raw, self.active.keys if self.active else ())
                if action.kind == "empty":
                    if empty == "back":
                        return Action("back")
                    continue
                if action.kind == "quit":
                    if self.confirm_quit():
                        raise SystemExit
                    break  # redraw the screen after the cancelled confirm
                if action.kind == "help":
                    self.show_help()
                    break
                if action.kind == "unknown_palette":
                    terminal.print(
                        f"Unknown command {action.value}. Palette: /save /home /ref /quit /help"
                    )
                    continue
                if action.kind == "palette":
                    if action.value == "save":
                        self.do_save()
                        continue
                    if action.value == "load":
                        terminal.print("/load works from the Home screen only (it replaces the current career).")
                        continue
                    if action.value == "home":
                        if self.confirm_home():
                            raise GoHome
                        continue
                    if action.value == "ref":
                        if self.ref_handler is not None:
                            self.ref_handler()
                        break
                    continue
                return action
            self.redraw()

    def redraw(self) -> None:
        active = self.active
        if active is not None and active.render is not None:
            active.render()

    # -- universal behaviours ----------------------------------------------------
    def confirm_quit(self) -> bool:
        note = " Staged changes will be lost." if self.any_dirty() else ""
        return confirm(f"{self.quit_prompt}{note}")

    def confirm_home(self) -> bool:
        if self.any_dirty():
            return confirm("Staged changes will be discarded — jump to Home anyway?")
        return True

    def do_save(self) -> None:
        if self.save_handler is not None:
            self.save_handler()

    def show_help(self) -> None:
        universal_help_tables()
        active = self.active
        if active is not None and active.keys:
            terminal.table(
                f"{active.name} Keys",
                ["Key", "Action"],
                [[key.key, key.description or key.label] for key in active.keys],
            )
        if active is not None and active.help is not None:
            active.help()
        elif self.help_handler is not None:
            self.help_handler()
        terminal.pause()


shell = Shell()
