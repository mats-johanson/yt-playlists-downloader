"""CLI entry point."""

from __future__ import annotations

import argparse
import contextlib
import os
import select
import signal
import sys
import termios
import threading
import tty
from pathlib import Path

from rich.console import Console

from . import config
from .auth.spotify_pkce import AuthError, logout
from .config_loader import load as load_config
from .dashboard import make_dashboard
from .discovery_dates import DiscoveryDates
from .downloader import Downloader
from .match_cache import MatchCache
from .orphan_cleaner import clean_orphans
from .overrides import Overrides
from .pipeline import Pipeline
from .summary import render_discovered, render_final_summary
from .traktor_smartlists import sync_smartlists
from .traktor_sync import sync_import_dates
from .unavailable import UnavailableTracker


class KeyWatcher:
    """Translate a bare ESC keypress into SIGINT, alongside Ctrl-C.

    Background thread polls stdin in cbreak mode. On bare ESC (0x1b not
    followed by more bytes within 50ms — that's how arrow keys and other
    escape sequences are distinguished), sends SIGINT to ourselves so the
    same clean-exit path that handles Ctrl-C also handles ESC.

    No-op when stdin isn't a TTY (cron, piped runs). Terminal state is
    restored unconditionally on `__exit__`.
    """

    def __init__(self):
        self._old_settings = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        if not sys.stdin.isatty():
            return self
        try:
            self._old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        except (termios.error, OSError):
            self._old_settings = None
            return self
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._old_settings is not None:
            with contextlib.suppress(termios.error, OSError):
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_settings)

    def _watch(self) -> None:
        while not self._stop.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not ready:
                continue
            try:
                ch = sys.stdin.read(1)
            except (OSError, ValueError):
                return
            if ch != "\x1b":
                continue
            # Bare ESC vs escape sequence (arrow keys, F-keys, alt-X, …):
            # sequences send more bytes within a few ms. Wait 50ms; if more
            # data arrived, drain it and ignore. If nothing followed, it's
            # a deliberate ESC press.
            followup, _, _ = select.select([sys.stdin], [], [], 0.05)
            if followup:
                while select.select([sys.stdin], [], [], 0)[0]:
                    try:
                        sys.stdin.read(1)
                    except (OSError, ValueError):
                        break
                continue
            os.kill(os.getpid(), signal.SIGINT)
            return


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="yt-playlists",
        description="Spotify-first music library downloader with brew-style multi-bar dashboard.",
    )
    p.add_argument("--no-dashboard", action="store_true", help="single-line live summary")
    p.add_argument("--debug", action="store_true", help="verbose yt-dlp to logs/debug.log")
    p.add_argument("--logout", action="store_true", help="delete the cached Spotify token + exit")
    p.add_argument("--clean-orphans", action="store_true", help="empty stale archives + exit")
    p.add_argument(
        "--backfill-dates",
        action="store_true",
        help="populate logs/discovery-dates.json from existing playlists "
             "and the match cache without re-downloading anything; then exit",
    )
    p.add_argument(
        "--sync-traktor-dates",
        action="store_true",
        help="overwrite Traktor IMPORT_DATE with discovery date + exit",
    )
    p.add_argument(
        "--traktor-nml",
        default="/Users/mats/Documents/Native Instruments/Traktor 3.11.1/collection.nml",
        help="path to Traktor's collection.nml",
    )
    return p.parse_args(argv)


def _pick_dashboard_mode(args, *, isatty: bool) -> str:
    if not isatty:
        return "plain"
    if args.no_dashboard:
        return "summary"
    return "bars"


def _backfill_dates(
    console: Console,
    spotify_discovered,
    cache: MatchCache,
    discovery_dates: DiscoveryDates,
) -> int:
    """Record Spotify added_at into discovery_dates for already-resolved tracks.

    Pipeline.discover() has already recorded YT-direct positions. Here we cover
    the Spotify path: look up each Spotify track's cached video_id (no network,
    no matcher, no ytsearch — just the in-memory cache hit), and persist
    (video_id, added_at, source_playlist) tuples.

    Tracks with no cached video_id are skipped — those need a real resolve to
    have a known YT target. The current --backfill-dates run is by design a
    discovery-only shortcut; the user can do a full ./download_playlists.sh
    next time to fill the rest, then re-run --backfill-dates.
    """
    items: list[tuple[str, str, str]] = []
    skipped_no_cache = 0
    skipped_no_added_at = 0
    for dpl in spotify_discovered:
        for t in dpl.tracks:
            if not t.spotify:
                continue
            added_at = t.spotify.added_at
            if not added_at:
                skipped_no_added_at += 1
                continue
            cached = cache.get(t.spotify.spotify_id)
            if cached is None:
                skipped_no_cache += 1
                continue
            items.append((cached.youtube_video_id, added_at, dpl.source_label))
    written = discovery_dates.record_many(items)

    console.print()
    console.print(f"[green]Spotify backfill:[/]      recorded {written} new/earlier dates")
    console.print(f"[dim]Spotify entries with no cached video_id: {skipped_no_cache}[/]")
    console.print(f"[dim]Spotify entries with no added_at field:  {skipped_no_added_at}[/]")
    console.print(
        "[dim]YT-direct dates were already recorded during the discover phase.[/]"
    )
    console.print()
    console.print(f"Total entries in {config.DISCOVERY_DATES.name}: "
                  f"{len(discovery_dates.all())}")
    console.print("[dim]Next step: ./download_playlists.sh --sync-traktor-dates[/]")
    return 0


def main(argv: list[str] | None = None) -> int:
    console = Console(highlight=False)
    try:
        with KeyWatcher():
            return _run(argv, console)
    except KeyboardInterrupt:
        # One-line clean exit on Ctrl-C or ESC; no traceback wall.
        # Already-downloaded MP3s, archive lines, and matcher cache are all
        # flushed durably as work happens, so re-running picks up where we
        # left off without re-downloading anything finished.
        console.print(
            "\n[yellow]Interrupted.[/] Partial progress saved — re-run to resume."
        )
        return 130  # standard SIGINT exit code


def _run(argv: list[str] | None, console: Console) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.logout:
        removed = logout()
        console.print("Spotify token removed." if removed else "No cached Spotify token.")
        return 0

    config.ensure_dirs()

    if args.clean_orphans:
        clean_orphans(console, config.ARCHIVES_DIR, config.OUTPUT_ROOT)
        return 0

    if args.sync_traktor_dates:
        discovery_dates = DiscoveryDates(config.DISCOVERY_DATES)
        rc = sync_import_dates(
            console=console,
            nml_path=Path(args.traktor_nml),
            discovery_dates=discovery_dates,
            synced_root=config.OUTPUT_ROOT,
        )
        if rc != 0:
            return rc
        return sync_smartlists(
            console=console,
            nml_path=Path(args.traktor_nml),
            synced_root=config.OUTPUT_ROOT,
        )

    cfg = load_config()
    if not config.PLAYLISTS_TOML.exists():
        console.print(
            f"[dim]No {config.PLAYLISTS_TOML.name} — using defaults "
            f"(tag {cfg.spotify_tag}, no YouTube extras). "
            f"Copy config/playlists.toml.example to customize.[/]"
        )

    cache = MatchCache(config.MATCH_CACHE)
    overrides = Overrides(config.OVERRIDES_TOML)
    discovery_dates = DiscoveryDates(config.DISCOVERY_DATES)

    unavailable = UnavailableTracker(
        config.UNAVAILABLE_FILE, dead_videos_file=config.DEAD_VIDEOS_FILE
    )
    unavailable.reset_run_state()
    config.DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.DEBUG_LOG.write_text("", encoding="utf-8")
    config.UNMATCHED_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.UNMATCHED_LOG.write_text("", encoding="utf-8")

    pipeline = Pipeline(
        console=console,
        spotify_tag=cfg.spotify_tag,
        youtube_urls=cfg.youtube_urls,
        cache=cache,
        overrides=overrides,
        unavailable=unavailable,
        discovery_dates=discovery_dates,
        resolutions_log=config.RESOLUTIONS_LOG,
        unmatched_log=config.UNMATCHED_LOG,
    )

    try:
        spotify_discovered, youtube_discovered = pipeline.discover()
    except AuthError as e:
        console.print(f"[red]Auth error:[/] {e}")
        console.print("[dim]Try ./download_playlists.sh --logout, then re-run.[/]")
        return 1

    if args.backfill_dates:
        return _backfill_dates(
            console, spotify_discovered, cache, discovery_dates
        )

    spotify_resolved = pipeline.resolve_spotify(spotify_discovered)
    folders = pipeline.plan(spotify_resolved, youtube_discovered)
    render_discovered(console, folders)

    if not folders:
        return 0

    mode = _pick_dashboard_mode(args, isatty=sys.stdout.isatty())
    with make_dashboard(console, mode=mode) as dashboard:
        downloader = Downloader(
            archives_dir=config.ARCHIVES_DIR,
            output_root=config.OUTPUT_ROOT,
            dashboard=dashboard,
            unavailable=unavailable,
            cache=cache,
            debug_log=config.DEBUG_LOG,
            debug=args.debug,
        )
        outcomes = pipeline.download(folders, downloader=downloader)

    render_final_summary(
        console,
        outcomes,
        folders,
        archives_dir=config.ARCHIVES_DIR,
        unavailable=unavailable,
        output_root=config.OUTPUT_ROOT,
        debug_log=config.DEBUG_LOG,
        unmatched_log=config.UNMATCHED_LOG,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
