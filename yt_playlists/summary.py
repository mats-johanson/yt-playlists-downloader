from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .archive import total_archived
from .config import PLAYLIST_NAME_COL_WIDTH
from .outcomes import OutcomeReason, PlaylistOutcome
from .unavailable import UnavailableTracker

_FAILED_REASON_LABEL: dict[OutcomeReason, str] = {
    OutcomeReason.BOT_BLOCKED: "bot-blocked",
    OutcomeReason.ERROR: "error",
}


def render_scan_results(console: Console, scans) -> None:
    up_to_date = 0
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left")
    table.add_column(justify="right")
    table.add_column(justify="left")

    any_rows = False
    for scan in scans:
        if scan.new_count > 0:
            table.add_row(
                f"  {escape(scan.name)}",
                f"{scan.total} videos",
                f"[bold]{scan.new_count} new[/]",
            )
            any_rows = True
        else:
            up_to_date += 1

    if any_rows:
        console.print(table)
    if up_to_date:
        console.print(f"  [dim]({up_to_date} playlists up to date)[/]")
    console.print()


def _truncate(name: str, width: int) -> str:
    if len(name) > width:
        return name[: width - 1] + "…"
    return name


def _outcome_row(outcome: PlaylistOutcome, unavailable_count: int) -> str:
    name = _truncate(outcome.name, PLAYLIST_NAME_COL_WIDTH)

    if outcome.reason is OutcomeReason.DONE:
        return f"  [green]✓[/] {name:<{PLAYLIST_NAME_COL_WIDTH}} {outcome.songs_done:>3}"

    if outcome.reason is OutcomeReason.EMPTY:
        # Not a failure: the playlist had no fetchable new content this run.
        # If we recorded individual unavailables, name the actual cause.
        label = (
            f"{unavailable_count} unavailable" if unavailable_count else "no new songs"
        )
        return f"  [dim]•[/] {name:<{PLAYLIST_NAME_COL_WIDTH}} [dim]{label}[/]"

    label = _FAILED_REASON_LABEL.get(outcome.reason, "fail")
    return f"  [red]✗[/] {name:<{PLAYLIST_NAME_COL_WIDTH}} [red]{label}[/]"


def render_final_summary(
    console: Console,
    outcomes: list[PlaylistOutcome],
    *,
    archives_dir: Path,
    unavailable: UnavailableTracker,
    output_root: Path,
    debug_log: Path,
) -> None:
    total_downloaded = sum(o.songs_done for o in outcomes)
    console.rule()
    console.print(f"Done — [bold]{total_downloaded}[/] songs downloaded\n")

    # Two-column outcome grid.
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
        console.print(f"  [dim]→ see {debug_log} for HTTP 429 / sign-in messages[/]")

    any_failed = any(o.failed for o in outcomes)
    if any_failed and not blocked:
        console.print(f"\n[dim]Details for failures: {debug_log}[/]")

    console.print(f"\n[dim]Files saved to: {output_root}[/]")
