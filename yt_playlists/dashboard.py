"""Brew-style multi-progress dashboard.

Three implementations share one interface (`PlaylistTaskHandle` for per-playlist
control). Pick at runtime via `make_dashboard(mode=…)`. Mode selection lives in
`__main__._pick_dashboard_mode` — this module does not auto-detect.

    Bar       — rich Progress with one animated bar per playlist (default).
    Summary   — single live line summarising overall throughput (--no-dashboard).
    Plain     — one stdout line per song-completion event (no TTY).
"""

from __future__ import annotations

import threading
from abc import abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.progress import BarColumn, Progress, ProgressColumn, SpinnerColumn
from rich.text import Text

from .config import PLAYLIST_NAME_COL_WIDTH
from .outcomes import OutcomeReason

BAR_WIDTH = 22
TITLE_WIDTH = 40


_OUTCOME_LABEL: dict[OutcomeReason, str] = {
    OutcomeReason.DONE: "done",
    # EMPTY only reaches the dashboard for playlists where scan saw new videos
    # (has_work filter in __main__). Getting 0 downloads means yt-dlp tried all
    # N and every one failed — typically unavailable/private/age-restricted.
    OutcomeReason.EMPTY: "skipped (all failed)",
    OutcomeReason.BOT_BLOCKED: "bot-blocked",
    OutcomeReason.ERROR: "error",
}


class PlaylistTaskHandle(Protocol):
    def update_song(self, *, title: str, pct: float) -> None: ...
    def song_completed(self, *, song_title: str, songs_done: int) -> None: ...
    def playlist_completed(self, *, songs_done: int, reason: OutcomeReason) -> None: ...


class Dashboard(AbstractContextManager):
    """Common dashboard interface — start on __enter__, stop on __exit__."""

    def __enter__(self) -> Dashboard:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def add_playlist(self, name: str, total_new: int) -> PlaylistTaskHandle: ...


# --- Bar dashboard (rich Progress, brew-style) -----------------------------


class _StatusColumn(ProgressColumn):
    def render(self, task) -> Text:
        reason: OutcomeReason | None = task.fields.get("outcome_reason")
        if reason is OutcomeReason.DONE:
            return Text("✓", style="bold green")
        if reason is OutcomeReason.EMPTY:
            return Text("•", style="dim")
        if reason in (OutcomeReason.BOT_BLOCKED, OutcomeReason.ERROR):
            return Text("✗", style="bold red")
        pct = int(task.percentage or 0)
        return Text(f"{pct:>3}%", style="cyan")


class _SongTitleColumn(ProgressColumn):
    def render(self, task) -> Text:
        reason: OutcomeReason | None = task.fields.get("outcome_reason")
        if reason is not None:
            return Text(_OUTCOME_LABEL.get(reason, ""), style="dim")
        title = task.fields.get("song_title") or "—"
        if len(title) > TITLE_WIDTH:
            title = title[: TITLE_WIDTH - 1] + "…"
        return Text(title)


class _SongCountColumn(ProgressColumn):
    def render(self, task) -> Text:
        done = task.fields.get("songs_done", 0)
        total = task.fields.get("songs_total", 0)
        return Text(f"({done}/{total})", style="dim")


class _PlaylistNameColumn(ProgressColumn):
    def render(self, task) -> Text:
        name = task.fields.get("playlist_name") or "?"
        if len(name) > PLAYLIST_NAME_COL_WIDTH:
            name = name[: PLAYLIST_NAME_COL_WIDTH - 1] + "…"
        return Text(f"{name:<{PLAYLIST_NAME_COL_WIDTH}}", style="bold")


@dataclass
class _BarHandle:
    task_id: int
    progress: Progress
    console: Console
    name: str

    def update_song(self, *, title: str, pct: float) -> None:
        self.progress.update(
            self.task_id,
            completed=max(0.0, min(100.0, pct)),
            song_title=title,
        )

    def song_completed(self, *, song_title: str, songs_done: int) -> None:
        self.progress.update(self.task_id, songs_done=songs_done)
        self.console.print(
            f"  [dim green]✓[/] [bold]{escape(self.name)}:[/] {escape(song_title)}"
        )

    def playlist_completed(self, *, songs_done: int, reason: OutcomeReason) -> None:
        self.progress.update(
            self.task_id,
            completed=100,
            songs_done=songs_done,
            outcome_reason=reason,
        )


class BarDashboard(Dashboard):
    def __init__(self, console: Console):
        self._console = console
        self._progress = Progress(
            SpinnerColumn(style="cyan"),
            _PlaylistNameColumn(),
            BarColumn(bar_width=BAR_WIDTH, complete_style="green", finished_style="green"),
            _StatusColumn(),
            _SongTitleColumn(),
            _SongCountColumn(),
            console=console,
            refresh_per_second=12,
            transient=False,
            expand=False,
        )

    def start(self) -> None:
        self._progress.start()

    def stop(self) -> None:
        self._progress.stop()

    def add_playlist(self, name: str, total_new: int) -> _BarHandle:
        task_id = self._progress.add_task(
            "playlist",
            total=100,
            playlist_name=name,
            song_title="starting…",
            songs_done=0,
            songs_total=total_new,
            outcome_reason=None,
            start=True,
        )
        return _BarHandle(task_id, self._progress, self._console, name)


# --- Summary dashboard (single live line) ---------------------------------


@dataclass
class _SummaryState:
    name: str
    songs_total: int
    songs_done: int = 0
    current_title: str = "starting…"
    pct: float = 0.0
    reason: OutcomeReason | None = None


class _SummaryHandle:
    def __init__(self, dashboard: SummaryDashboard, state: _SummaryState):
        self._dashboard = dashboard
        self._state = state

    def update_song(self, *, title: str, pct: float) -> None:
        self._state.current_title = title
        self._state.pct = pct
        self._dashboard.notify()

    def song_completed(self, *, song_title: str, songs_done: int) -> None:
        self._state.songs_done = songs_done
        self._dashboard.notify(event=f"{self._state.name}: {song_title}")

    def playlist_completed(self, *, songs_done: int, reason: OutcomeReason) -> None:
        self._state.songs_done = songs_done
        self._state.reason = reason
        self._dashboard.notify()


class SummaryDashboard(Dashboard):
    """One live line, refreshed in place: `N active · M/T done · now: Title`."""

    def __init__(self, console: Console):
        self._console = console
        self._states: list[_SummaryState] = []
        self._lock = threading.Lock()
        self._live = Live(
            self._render(),
            console=console,
            refresh_per_second=8,
            transient=False,
        )

    def start(self) -> None:
        self._live.start()

    def stop(self) -> None:
        self._live.update(self._render(), refresh=True)
        self._live.stop()

    def add_playlist(self, name: str, total_new: int) -> _SummaryHandle:
        state = _SummaryState(name=name, songs_total=total_new)
        with self._lock:
            self._states.append(state)
        self.notify()
        return _SummaryHandle(self, state)

    def notify(self, event: str | None = None) -> None:
        if event:
            self._console.print(f"  [dim green]✓[/] {escape(event)}")
        self._live.update(self._render())

    def _render(self) -> Text:
        with self._lock:
            active = sum(1 for s in self._states if s.reason is None)
            done = sum(s.songs_done for s in self._states)
            total = sum(s.songs_total for s in self._states)
            current = next(
                (s for s in self._states if s.reason is None and s.current_title),
                None,
            )
            now = current.current_title if current else "—"
        return Text.from_markup(
            f"  [bold]{active}[/] active · [bold]{done}/{total}[/] done · now: [dim]{escape(now)}[/]"
        )


# --- Plain dashboard (no TTY: one line per event) -------------------------


class _PlainHandle:
    def __init__(self, console: Console, name: str, total: int):
        self._console = console
        self._name = name
        self._total = total

    def update_song(self, *, title: str, pct: float) -> None:
        # Plain mode skips byte-level updates to keep log volume sane.
        pass

    def song_completed(self, *, song_title: str, songs_done: int) -> None:
        self._console.print(
            f"  {songs_done}/{self._total}  {self._name}: {song_title}",
            markup=False,
        )

    def playlist_completed(self, *, songs_done: int, reason: OutcomeReason) -> None:
        marker = {
            OutcomeReason.DONE: "✓",
            OutcomeReason.EMPTY: "•",
        }.get(reason, "✗")
        label = _OUTCOME_LABEL.get(reason, "")
        self._console.print(
            f"  {marker} {self._name} — {label} ({songs_done} songs)",
            markup=False,
        )


class PlainDashboard(Dashboard):
    def __init__(self, console: Console):
        self._console = console

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def add_playlist(self, name: str, total_new: int) -> _PlainHandle:
        return _PlainHandle(self._console, name, total_new)


# --- Factory --------------------------------------------------------------


def make_dashboard(console: Console, *, mode: str) -> Dashboard:
    """Build a dashboard for an explicit mode. No auto-detection — that's the
    orchestrator's job (see `__main__._pick_dashboard_mode`).

    mode: "bars" | "summary" | "plain"
    """
    if mode == "bars":
        return BarDashboard(console)
    if mode == "summary":
        return SummaryDashboard(console)
    if mode == "plain":
        return PlainDashboard(console)
    raise ValueError(f"unknown dashboard mode: {mode!r}")
