"""End-of-run summary with per-folder source breakdown + unmatched section."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .archive import total_archived
from .config import PLAYLIST_NAME_COL_WIDTH
from .outcomes import OutcomeReason, PlaylistOutcome
from .tracks import PlannedFolder
from .unavailable import UnavailableTracker

_FAILED_REASON_LABEL: dict[OutcomeReason, str] = {
    OutcomeReason.BOT_BLOCKED: "bot-blocked",
    OutcomeReason.ERROR: "error",
}


def _truncate(name: str, width: int) -> str:
    if len(name) > width:
        return name[: width - 1] + "…"
    return name


def render_discovered(console: Console, folders: list[PlannedFolder]) -> None:
    if not folders:
        console.print("[yellow]No playlists matched any source.[/]")
        return
    console.print(f"[bold]{len(folders)}[/] folder(s) planned:\n")
    for f in folders:
        spotify_n = sum(1 for r in f.resolved if r.spotify is not None)
        yt_only_n = sum(1 for r in f.resolved if r.spotify is None)
        line = f"  [bold]{escape(f.folder_name)}[/] — {len(f.resolved)} track(s)"
        if spotify_n:
            line += f" (Spotify: {spotify_n})"
        if yt_only_n:
            line += f" (YouTube: {yt_only_n})"
        if f.unmatched:
            line += f" [red]+{len(f.unmatched)} unmatched[/]"
        if f.merge_note:
            line += f" [dim]← merge: {escape(f.merge_note)}[/]"
        console.print(line)
    console.print()


def _outcome_row(outcome: PlaylistOutcome, unavailable_count: int) -> str:
    name = _truncate(outcome.name, PLAYLIST_NAME_COL_WIDTH)
    if outcome.reason is OutcomeReason.DONE:
        return f"  [green]✓[/] {name:<{PLAYLIST_NAME_COL_WIDTH}} {outcome.songs_done:>3}"
    if outcome.reason is OutcomeReason.EMPTY:
        label = (
            f"{unavailable_count} unavailable"
            if unavailable_count
            else "skipped (all failed)"
        )
        return f"  [dim]•[/] {name:<{PLAYLIST_NAME_COL_WIDTH}} [dim]{label}[/]"
    label = _FAILED_REASON_LABEL.get(outcome.reason, "fail")
    return f"  [red]✗[/] {name:<{PLAYLIST_NAME_COL_WIDTH}} [red]{label}[/]"


def render_final_summary(
    console: Console,
    outcomes: list[PlaylistOutcome],
    folders: list[PlannedFolder],
    *,
    archives_dir: Path,
    unavailable: UnavailableTracker,
    output_root: Path,
    debug_log: Path,
    unmatched_log: Path,
) -> None:
    total_downloaded = sum(o.songs_done for o in outcomes)
    console.rule()
    console.print(f"Done — [bold]{total_downloaded}[/] songs downloaded\n")

    grid = Table.grid(padding=(0, 4))
    grid.add_column()
    grid.add_column()
    rows = [
        _outcome_row(o, unavailable.count_for(o.name))
        for o in sorted(outcomes, key=lambda x: x.name.lower())
    ]
    for i in range(0, len(rows), 2):
        left = rows[i]
        right = rows[i + 1] if i + 1 < len(rows) else ""
        grid.add_row(left, right)
    console.print(grid)

    archived = total_archived(archives_dir)
    if archived:
        console.print(f"\n[dim]{archived} total songs in archive[/]")

    # Unmatched Spotify tracks: surface for manual override.
    total_unmatched = sum(len(f.unmatched) for f in folders)
    if total_unmatched:
        console.print(
            f"\n[yellow]{total_unmatched} Spotify track(s) unmatched[/] — "
            f"see {unmatched_log} to add manual overrides to "
            f"config/spotify_overrides.toml"
        )

    entries = unavailable.entries()
    if entries:
        console.print("\nUnavailable videos:")
        for e in entries:
            console.print(f"  [red]✗[/] [dim]{e.playlist}:[/] {e.url}")

    blocked = unavailable.bot_blocked_playlists()
    if blocked:
        console.print("\n[bold red]Bot-block detected[/] for:")
        for name in sorted(blocked):
            console.print(f"  [red]✗[/] {name}")
        console.print(f"  [dim]→ see {debug_log}[/]")

    any_failed = any(o.failed for o in outcomes)
    if any_failed and not blocked:
        console.print(f"\n[dim]Details: {debug_log}[/]")

    console.print(f"\n[dim]Files saved to: {output_root}[/]")
