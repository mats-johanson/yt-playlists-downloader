from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from . import config
from .dashboard import make_dashboard
from .downloader import Downloader
from .orphan_cleaner import clean_orphans
from .scanner import scan_all
from .summary import render_final_summary, render_scan_results
from .unavailable import UnavailableTracker


def _read_playlist_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yt-playlists",
        description="Download YouTube playlists as MP3 with a brew-style multi-bar dashboard.",
    )
    parser.add_argument(
        "playlists_file",
        nargs="?",
        type=Path,
        default=config.DEFAULT_PLAYLISTS_FILE,
        help=f"playlist URLs, one per line (default: {config.DEFAULT_PLAYLISTS_FILE})",
    )
    parser.add_argument(
        "--clean-orphans",
        action="store_true",
        help="empty archive files whose output folder is missing/empty, then exit",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="use a single-line summary instead of the multi-bar dashboard",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable verbose yt-dlp output to logs/debug.log",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=config.PARALLEL_JOBS,
        help=f"parallel downloads (default: {config.PARALLEL_JOBS})",
    )
    return parser.parse_args(argv)


def _pick_dashboard_mode(args: argparse.Namespace, *, isatty: bool) -> str:
    """Single source of truth for which dashboard implementation to use.

    Pure function of args + TTY state — easy to unit test.
    """
    if not isatty:
        return "plain"
    if args.no_dashboard:
        return "summary"
    return "bars"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    console = Console(highlight=False)

    config.ensure_dirs()

    if args.clean_orphans:
        clean_orphans(console, config.ARCHIVES_DIR, config.OUTPUT_ROOT)
        return 0

    if not args.playlists_file.exists():
        console.print(f"[red]Playlists file not found:[/] {args.playlists_file}")
        return 1

    urls = _read_playlist_urls(args.playlists_file)
    if not urls:
        console.print("[yellow]No playlist URLs found.[/]")
        return 0

    # --- Scan phase ---
    with console.status(f"Scanning {len(urls)} playlists..."):
        scans = scan_all(urls, config.ARCHIVES_DIR, args.parallel)

    render_scan_results(console, scans)

    todo = [s for s in scans if s.has_work]
    if not todo:
        console.print("All playlists up to date — nothing to download")
        return 0

    total_new = sum(s.new_count for s in todo)
    console.print(f"[bold]{total_new}[/] new songs to download\n")
    for s in todo:
        console.print(f"  [dim]→ {s.name}[/]")
    console.print()

    # --- Download phase ---
    unavailable = UnavailableTracker(config.UNAVAILABLE_FILE)
    unavailable.reset()
    config.DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.DEBUG_LOG.write_text("", encoding="utf-8")

    mode = _pick_dashboard_mode(args, isatty=sys.stdout.isatty())
    with make_dashboard(console, mode=mode) as dashboard:
        downloader = Downloader(
            archives_dir=config.ARCHIVES_DIR,
            output_root=config.OUTPUT_ROOT,
            dashboard=dashboard,
            unavailable=unavailable,
            debug_log=config.DEBUG_LOG,
            debug=args.debug,
        )
        outcomes = downloader.download_all(todo, args.parallel)

    # --- Summary ---
    render_final_summary(
        console,
        outcomes,
        archives_dir=config.ARCHIVES_DIR,
        unavailable=unavailable,
        output_root=config.OUTPUT_ROOT,
        debug_log=config.DEBUG_LOG,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
