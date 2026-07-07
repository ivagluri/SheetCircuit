from __future__ import annotations

import shutil
import sys
from typing import Sequence


try:
    from rich import box
    from rich.columns import Columns
    from rich.console import Console
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    box = None
    Columns = None
    Console = None
    Group = None
    Panel = None
    Table = None
    RICH_AVAILABLE = False


class Terminal:
    def __init__(self) -> None:
        self._console = Console() if RICH_AVAILABLE and Console is not None else None

    def print(self, text: object = "") -> None:
        if self._console is not None:
            self._console.print(text)
        else:
            print(text)

    def print_plain(self, text: object = "") -> None:
        """Print without markup interpretation: chrome like "[q Quit]" must
        render its brackets literally instead of being parsed as a rich tag."""
        if self._console is not None:
            self._console.print(text, markup=False, highlight=False)
        else:
            print(text)

    def clear(self) -> None:
        if not sys.stdout.isatty():
            return
        if self._console is not None:
            self._console.clear()
        else:
            print("\033[2J\033[H", end="")

    def header(self, title: str, subtitle: str = "") -> None:
        if self._console is not None and Panel is not None:
            body = subtitle if subtitle else title
            self._console.print(Panel(body, title=title, border_style="cyan"))
        else:
            print(title)
            if subtitle:
                print(subtitle)

    def menu(self, text: str) -> None:
        if self._console is not None and Panel is not None:
            self._console.print(Panel(text, title="Menu", border_style="green"))
        else:
            print()
            print(text)

    def table(self, title: str, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
        if self._console is not None and Table is not None and box is not None:
            self._console.print(self._rich_table(title, headers, rows))
            return
        print("\n".join(self._plain_table_lines(title, headers, rows)))

    def table_columns(
        self,
        *groups: Sequence[tuple[str, Sequence[str], Sequence[Sequence[object]]]],
    ) -> None:
        """Render groups of tables side by side; each group stacks its tables vertically."""
        if (
            self._console is not None
            and Columns is not None
            and Group is not None
            and Table is not None
            and box is not None
        ):
            # no_wrap: side-by-side panels must keep a constant height, so a cell that
            # can't fit truncates with an ellipsis instead of wrapping onto extra lines.
            rendered = [
                Group(*(self._rich_table(title, headers, rows, no_wrap=True) for title, headers, rows in group))
                for group in groups
            ]
            # Left-packed (no expand): a column growing wider (e.g. a long race-log line)
            # only extends its own right edge instead of re-spacing the whole row.
            self._console.print(Columns(rendered, expand=False, equal=False))
            return

        group_lines: list[list[str]] = []
        for group in groups:
            lines: list[str] = []
            for title, headers, rows in group:
                if lines:
                    lines.append("")
                lines.extend(self._plain_table_lines(title, headers, rows))
            group_lines.append(lines)
        widths = [max((len(line) for line in lines), default=0) for lines in group_lines]
        terminal_width = shutil.get_terminal_size((120, 40)).columns
        gap = 4
        if sum(widths) + gap * (len(group_lines) - 1) > terminal_width:
            print("\n\n".join("\n".join(lines) for lines in group_lines))
            return
        height = max(len(lines) for lines in group_lines)
        combined = []
        for index in range(height):
            cells = [
                (lines[index] if index < len(lines) else "").ljust(widths[column])
                for column, lines in enumerate(group_lines)
            ]
            combined.append((" " * gap).join(cells).rstrip())
        print("\n".join(combined))

    def _rich_table(self, title: str, headers: Sequence[str], rows: Sequence[Sequence[object]], no_wrap: bool = False):
        table = Table(title=title, box=box.SIMPLE_HEAVY)
        for header in headers:
            if no_wrap:
                table.add_column(header, no_wrap=True, overflow="ellipsis")
            else:
                table.add_column(header)
        for row in rows:
            table.add_row(*(str(value) for value in row))
        return table

    def _plain_table_lines(
        self,
        title: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
    ) -> list[str]:
        lines = [title]
        if not rows:
            return lines + ["  none"]
        widths = [len(header) for header in headers]
        for row in rows:
            for index, value in enumerate(row):
                widths[index] = max(widths[index], len(str(value)))
        header_line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
        lines.append(header_line)
        lines.append("  ".join("-" * width for width in widths))
        for row in rows:
            lines.append("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
        return lines

    def prompt(self, label: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{label}{suffix}: ").strip()
        return raw if raw else (default or "")

    def pause(self, label: str = "Press Enter") -> None:
        if sys.stdin.isatty():
            input(f"{label}...")


terminal = Terminal()
