"""Optional modern CLI presentation layer with safe plain fallback."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Iterable, List, Sequence

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
    from rich.table import Table
    _RICH_AVAILABLE = True
except Exception:  # pragma: no cover - fallback path
    _RICH_AVAILABLE = False
    box = None
    Console = None
    Panel = None
    Progress = None
    TextColumn = None
    BarColumn = None
    TimeElapsedColumn = None
    Table = None


class _NullPhaseTracker:
    """No-op phase tracker used in plain mode."""

    def advance(self, _label: str) -> None:
        return None

    def fail(self, _label: str) -> None:
        return None


class _NullChapterTracker:
    """No-op chapter tracker used in plain mode."""

    def set_total(self, _total: int) -> None:
        return None

    def start(self, _chapter_id: str, _index: int | None = None, _total: int | None = None) -> None:
        return None

    def complete(self, _chapter_id: str) -> None:
        return None

    def fail(self, _chapter_id: str) -> None:
        return None

    def skip(self, _chapter_id: str) -> None:
        return None


class _RichPhaseTracker:
    """Rich-backed phase tracker for visual pipeline progress."""

    def __init__(self, progress: Progress, task_id: int, title: str):
        self._progress = progress
        self._task_id = task_id
        self._title = title

    def advance(self, label: str) -> None:
        self._progress.update(
            self._task_id,
            advance=1,
            description=f"{self._title} • {label}",
        )

    def fail(self, label: str) -> None:
        self._progress.update(
            self._task_id,
            description=f"{self._title} • FAILED ({label})",
        )


class _RichChapterTracker:
    """Rich-backed tracker for per-chapter phase 2 progress."""

    def __init__(self, progress: Progress, task_id: int, title: str):
        self._progress = progress
        self._task_id = task_id
        self._title = title

    def set_total(self, total: int) -> None:
        safe_total = max(int(total), 1)
        self._progress.update(self._task_id, total=safe_total)

    def start(self, chapter_id: str, index: int | None = None, total: int | None = None) -> None:
        if index is not None and total is not None:
            self._progress.update(
                self._task_id,
                description=f"{self._title} • {chapter_id} [{index}/{total}]",
            )
        else:
            self._progress.update(
                self._task_id,
                description=f"{self._title} • {chapter_id}",
            )

    def complete(self, chapter_id: str) -> None:
        self._progress.update(
            self._task_id,
            advance=1,
            description=f"{self._title} • done {chapter_id}",
        )

    def fail(self, chapter_id: str) -> None:
        self._progress.update(
            self._task_id,
            advance=1,
            description=f"{self._title} • fail {chapter_id}",
        )

    def skip(self, chapter_id: str) -> None:
        self._progress.update(
            self._task_id,
            advance=1,
            description=f"{self._title} • skip {chapter_id}",
        )


class ModernCLIUI:
    """Modern UI helpers that degrade gracefully to plain text."""

    def __init__(self, mode: str = "auto", no_color: bool = False):
        self.mode = mode
        self.no_color = no_color
        self.rich_enabled = False
        self.console = None

        if not _RICH_AVAILABLE:
            return

        if mode == "plain":
            return

        if mode == "rich":
            self.rich_enabled = True
        elif mode == "auto":
            self.rich_enabled = sys.stdout.isatty()

        if self.rich_enabled:
            self.console = Console(
                no_color=no_color,
                force_terminal=(mode == "rich"),
                highlight=False,
                soft_wrap=True,
            )

    def format_badge(self, badge: str) -> str:
        """Return a styled badge when rich is enabled."""
        if not self.rich_enabled:
            return badge

        value = (badge or "").upper()
        if value.startswith("DONE"):
            color = "green"
        elif value.startswith("RUN"):
            color = "cyan"
        elif value.startswith("FAIL"):
            color = "red"
        elif value.startswith("WARN"):
            color = "yellow"
        elif value.startswith("PART"):
            color = "magenta"
        else:
            color = "yellow"
        return f"[bold {color}]{badge}[/bold {color}]"

    def format_compact_badge(self, badge: str) -> str:
        """Return compact one-letter status badges for narrow tables."""
        value = (badge or "").upper()
        if value.startswith("DONE"):
            token, color = "D", "green"
        elif value.startswith("RUN"):
            token, color = "R", "cyan"
        elif value.startswith("FAIL"):
            token, color = "F", "red"
        elif value.startswith("WARN"):
            token, color = "W", "yellow"
        elif value.startswith("PART"):
            token, color = "P", "magenta"
        else:
            token, color = "T", "yellow"

        if not self.rich_enabled:
            return token
        return f"[bold {color}]{token}[/bold {color}]"

    def print_header(self, title: str, subtitle: str = "") -> bool:
        """Render a panel header in modern mode. Returns True when rendered."""
        if not self.rich_enabled:
            return False

        content = f"[bold]{title}[/bold]"
        if subtitle:
            content += f"\n[dim]{subtitle}[/dim]"
        panel = Panel(content, title="MTL Studio 5.1", border_style="cyan", padding=(0, 1))
        self.console.print(panel)
        return True

    def print_success(self, message: str) -> None:
        if self.rich_enabled:
            self.console.print(f"[green][bold]OK[/bold][/green] {message}")

    def print_error(self, message: str) -> None:
        if self.rich_enabled:
            self.console.print(f"[red][bold]FAIL[/bold][/red] {message}")

    @contextmanager
    def command_status(self, description: str):
        """Render a live status spinner for long-running commands."""
        if not self.rich_enabled:
            yield
            return

        with self.console.status(f"[bold cyan]{description}[/bold cyan]", spinner="dots"):
            yield

    @contextmanager
    def phase_progress(self, total: int, title: str):
        """Render a phase progress bar for full pipeline runs."""
        if not self.rich_enabled:
            yield _NullPhaseTracker()
            return

        progress = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
        )
        with progress:
            task_id = progress.add_task(title, total=total)
            yield _RichPhaseTracker(progress, task_id, title)

    @contextmanager
    def chapter_progress(self, title: str = "Phase 2 Chapters", total: int = 1):
        """Render a live chapter progress bar for translator execution."""
        if not self.rich_enabled:
            yield _NullChapterTracker()
            return

        safe_total = max(int(total), 1)
        progress = Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=32),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
        )
        with progress:
            task_id = progress.add_task(title, total=safe_total)
            yield _RichChapterTracker(progress, task_id, title)

    def render_table(
        self,
        title: str,
        columns: Sequence[dict],
        rows: Iterable[Sequence[str]],
        caption: str = "",
    ) -> bool:
        """Render a table in modern mode. Returns True when rendered."""
        if not self.rich_enabled:
            return False

        table = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=False)
        for column in columns:
            table.add_column(
                column["header"],
                justify=column.get("justify", "left"),
                style=column.get("style"),
                no_wrap=column.get("no_wrap", False),
                overflow=column.get("overflow", "fold"),
                max_width=column.get("max_width"),
            )

        for row in rows:
            table.add_row(*[str(cell) for cell in row])

        self.console.print(table)
        if caption:
            self.console.print(f"[dim]{caption}[/dim]")
        return True

    def render_status_bar(self, label: str, completed: int, total: int, width: int = 28) -> bool:
        """Render a simple static status bar."""
        if not self.rich_enabled:
            return False

        total = max(total, 1)
        ratio = max(0.0, min(float(completed) / float(total), 1.0))
        filled = int(width * ratio)
        bar = ("█" * filled) + ("░" * (width - filled))
        color = "green" if ratio >= 1.0 else ("cyan" if ratio >= 0.5 else "yellow")
        self.console.print(
            f"[bold cyan]{label}[/bold cyan] [{color}]{bar}[/{color}] {completed}/{total}"
        )
        return True
