from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class Column:
    header: str
    values: list[str]


class Terminal:
    def __init__(self) -> None:
        self._console = Console() if RICH_AVAILABLE and Console is not None else None

    def print(self, text: object = "") -> None:
        if self._console is not None:
            self._console.print(text)
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
        left_tables: Sequence[tuple[str, Sequence[str], Sequence[Sequence[object]]]],
        right_table: tuple[str, Sequence[str], Sequence[Sequence[object]]],
    ) -> None:
        if (
            self._console is not None
            and Columns is not None
            and Group is not None
            and Table is not None
            and box is not None
        ):
            left = Group(*(self._rich_table(title, headers, rows) for title, headers, rows in left_tables))
            right = self._rich_table(*right_table)
            self._console.print(Columns([left, right], expand=True, equal=False))
            return

        left_lines: list[str] = []
        for title, headers, rows in left_tables:
            if left_lines:
                left_lines.append("")
            left_lines.extend(self._plain_table_lines(title, headers, rows))
        right_lines = self._plain_table_lines(*right_table)
        left_width = max((len(line) for line in left_lines), default=0)
        terminal_width = shutil.get_terminal_size((120, 40)).columns
        gap = 4
        if left_width + gap + max((len(line) for line in right_lines), default=0) > terminal_width:
            print("\n".join(left_lines))
            print()
            print("\n".join(right_lines))
            return
        height = max(len(left_lines), len(right_lines))
        combined = []
        for index in range(height):
            left = left_lines[index] if index < len(left_lines) else ""
            right = right_lines[index] if index < len(right_lines) else ""
            combined.append(left.ljust(left_width) + (" " * gap) + right)
        print("\n".join(combined))

    def _rich_table(self, title: str, headers: Sequence[str], rows: Sequence[Sequence[object]]):
        table = Table(title=title, box=box.SIMPLE_HEAVY)
        for header in headers:
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
