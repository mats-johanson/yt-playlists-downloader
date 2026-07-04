"""Phase orchestration.

DISCOVER  → fan out source.discover() for each configured source
RESOLVE   → for each Spotify track: override → cache → matcher
PLAN      → group + merge into PlannedFolders
DOWNLOAD  → existing downloader pipeline
SUMMARY   → render report

Each phase is one method on `Pipeline`. `__main__` wires them.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console

from . import config
from .discovery_dates import DiscoveryDates
from .downloader import Downloader
from .match_cache import MatchCache
from .matcher import resolve as matcher_resolve
from .outcomes import PlaylistOutcome
from .overrides import Overrides
from .playlist_plan import plan as plan_folders
from .sources import DiscoveredPlaylist, Source
from .sources.spotify_discover import SpotifySource
from .sources.youtube import YouTubeSource
from .tracks import (
    PlannedFolder,
    ResolvedTrack,
    SpotifyTrackMeta,
    Unmatched,
)
from .unavailable import UnavailableTracker
from .yt_search import youtube_search


# Resolution-log status values. Single source of truth for diagnostics tools
# that grep for status; if a value changes here, diagnose_resolve.py and the
# resolutions.log consumer break in lockstep rather than silently drifting.
class MatchStatus:
    OVERRIDE = "override"
    CACHE_HIT = "cache-hit"
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    WORKER_ERROR = "worker-error"


class _ResolutionLog:
    """Concurrent-safe writer for resolutions.log and unmatched.txt."""

    def __init__(self, resolutions_log: Path, unmatched_log: Path):
        self._resolutions_log = resolutions_log
        self._unmatched_log = unmatched_log
        self._resolutions_lock = threading.Lock()
        self._unmatched_lock = threading.Lock()

    def record(
        self,
        spotify_id: str,
        status: str,
        video_id: str | None,
        score: float | None,
        reason: str,
    ) -> None:
        self._resolutions_log.parent.mkdir(parents=True, exist_ok=True)
        line = (
            f"{spotify_id}\t{status}\t{video_id or '-'}\t"
            f"{f'{score:.1f}' if score is not None else '-'}\t{reason}\n"
        )
        with self._resolutions_lock, self._resolutions_log.open("a", encoding="utf-8") as f:
            f.write(line)

    def record_unmatched(self, u: Unmatched) -> None:
        self._unmatched_log.parent.mkdir(parents=True, exist_ok=True)
        suggestion = u.best_candidate_video_id or "—"
        line = (
            f'"{u.spotify.spotify_id}" = "{suggestion}"  '
            f"# {u.spotify.artist} — {u.spotify.title}  (score {u.best_score:.1f})\n"
        )
        with self._unmatched_lock, self._unmatched_log.open("a", encoding="utf-8") as f:
            f.write(line)


class _TrackResolver:
    """Override → cache → matcher chain for a single Spotify track.

    Lifted out of Pipeline so the orchestrator doesn't mix flatten/dispatch/log/parse
    levels and so callers don't have to reach into Pipeline private methods.
    """

    def __init__(
        self,
        *,
        cache: MatchCache,
        overrides: Overrides,
        log: _ResolutionLog,
        unavailable: UnavailableTracker,
    ):
        self._cache = cache
        self._overrides = overrides
        self._log = log
        self._unavailable = unavailable

    def resolve_one(self, meta: SpotifyTrackMeta) -> ResolvedTrack | Unmatched:
        spotify_id = meta.spotify_id

        override_video = self._overrides.get(spotify_id)
        if override_video:
            rt = ResolvedTrack(
                youtube_video_id=override_video,
                spotify=meta,
                match_reason="override",
            )
            self._cache.put(rt)
            self._log.record(
                spotify_id, MatchStatus.OVERRIDE, override_video, None, "user override"
            )
            return rt

        cached = self._cache.get(spotify_id)
        if cached is not None:
            self._log.record(
                spotify_id, MatchStatus.CACHE_HIT, cached.youtube_video_id,
                cached.match_score, "cache",
            )
            return cached

        result = matcher_resolve(
            meta,
            lambda query, n=5: youtube_search(query, n, unavailable=self._unavailable),
        )
        if isinstance(result, ResolvedTrack):
            self._cache.put(result)
            self._log.record(
                spotify_id, MatchStatus.MATCHED, result.youtube_video_id,
                result.match_score, result.match_reason or "",
            )
        else:
            self._log.record(
                spotify_id, MatchStatus.UNMATCHED, result.best_candidate_video_id,
                result.best_score, result.reason,
            )
            self._log.record_unmatched(result)
        return result


class Pipeline:
    def __init__(
        self,
        *,
        console: Console,
        spotify_tag: str,
        youtube_urls: list[str],
        cache: MatchCache,
        overrides: Overrides,
        unavailable: UnavailableTracker,
        discovery_dates: DiscoveryDates,
        resolutions_log: Path,
        unmatched_log: Path,
    ):
        self._console = console
        self._spotify_source: Source | None = (
            SpotifySource(tag=spotify_tag) if spotify_tag else None
        )
        self._youtube_source: Source | None = (
            YouTubeSource(urls=youtube_urls) if youtube_urls else None
        )
        self._cache = cache
        self._overrides = overrides
        self._unavailable = unavailable
        self._discovery_dates = discovery_dates
        self._log = _ResolutionLog(resolutions_log, unmatched_log)
        self._resolver = _TrackResolver(
            cache=cache, overrides=overrides, log=self._log, unavailable=unavailable,
        )

    # --- DISCOVER ---

    def discover(self) -> tuple[list[DiscoveredPlaylist], list[DiscoveredPlaylist]]:
        spotify_discovered: list[DiscoveredPlaylist] = []
        youtube_discovered: list[DiscoveredPlaylist] = []
        if self._spotify_source is not None:
            with self._console.status("Scanning Spotify playlists…"):
                spotify_discovered = self._spotify_source.discover()
            self._console.print(
                f"[dim]Spotify: {len(spotify_discovered)} playlist(s) matched tag[/]"
            )
        else:
            self._console.print("[dim]Spotify source disabled (no tag set)[/]")
        if self._youtube_source is not None:
            with self._console.status("Scanning YouTube playlists…"):
                youtube_discovered = self._youtube_source.discover()
            self._console.print(
                f"[dim]YouTube: {len(youtube_discovered)} playlist(s) scanned[/]"
            )
        # YT-direct tracks have video_id at discovery time; record their
        # synthesized added_at now. Spotify tracks get recorded post-resolve
        # (we don't know video_id until matcher picks one).
        self._record_youtube_dates(youtube_discovered)
        return spotify_discovered, youtube_discovered

    def _record_youtube_dates(
        self, youtube_discovered: list[DiscoveredPlaylist]
    ) -> None:
        items: list[tuple[str, str, str]] = []
        for dpl in youtube_discovered:
            for t in dpl.tracks:
                if t.youtube_video_id and t.added_at:
                    items.append((t.youtube_video_id, t.added_at, dpl.source_label))
        if items:
            self._discovery_dates.record_many(items)

    # --- RESOLVE ---

    def resolve_spotify(
        self, discovered: list[DiscoveredPlaylist]
    ) -> list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]]:
        all_tracks = [t for dpl in discovered for t in dpl.tracks if t.spotify]
        if not all_tracks:
            return [(dpl, [], []) for dpl in discovered]
        self._console.print(
            f"Resolving [bold]{len(all_tracks)}[/] Spotify track(s) → YouTube…"
        )

        resolved_by_id: dict[str, ResolvedTrack | Unmatched] = {}
        ex = ThreadPoolExecutor(max_workers=config.RESOLVE_PARALLEL)
        future_to_id = {
            ex.submit(self._resolve_safely, t.spotify): t.spotify.spotify_id
            for t in all_tracks
        }
        try:
            # as_completed → first-done order, not submission order; slow ytsearches
            # don't gate fast ones for the consumer.
            for fut in as_completed(future_to_id):
                spotify_id = future_to_id[fut]
                resolved_by_id[spotify_id] = fut.result()
        except KeyboardInterrupt:
            # Same pattern as Downloader.download_all — don't let __exit__
            # block on wait=True; cancel pending so Ctrl-C is responsive.
            ex.shutdown(wait=False, cancel_futures=True)
            raise
        ex.shutdown(wait=True)

        out = self._rebucket(discovered, resolved_by_id)
        self._record_spotify_dates(out)
        return out

    def _record_spotify_dates(
        self,
        rebuckets: list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]],
    ) -> None:
        items: list[tuple[str, str, str]] = []
        for dpl, resolved, _ in rebuckets:
            for r in resolved:
                if r.youtube_video_id and r.spotify and r.spotify.added_at:
                    items.append((r.youtube_video_id, r.spotify.added_at, dpl.source_label))
        if items:
            self._discovery_dates.record_many(items)

    def _resolve_safely(self, meta: SpotifyTrackMeta) -> ResolvedTrack | Unmatched:
        """Wraps `_TrackResolver.resolve_one` so one bad track doesn't abort the
        whole resolve phase. A bug in matcher / cache deserialization / spotipy
        crash currently re-raises, killing all 487 resolves at once.
        """
        try:
            return self._resolver.resolve_one(meta)
        except Exception as e:  # noqa: BLE001 — last-line defense for the whole phase
            self._log.record(
                meta.spotify_id, MatchStatus.WORKER_ERROR, None, None, f"worker error: {e}"
            )
            return Unmatched(
                spotify=meta,
                reason=f"worker error: {e}",
                best_candidate_video_id=None,
                best_score=0.0,
            )

    @staticmethod
    def _rebucket(
        discovered: list[DiscoveredPlaylist],
        resolved_by_id: dict[str, ResolvedTrack | Unmatched],
    ) -> list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]]:
        out: list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]] = []
        for dpl in discovered:
            resolved: list[ResolvedTrack] = []
            unmatched: list[Unmatched] = []
            for t in dpl.tracks:
                if not t.spotify:
                    continue
                r = resolved_by_id.get(t.spotify.spotify_id)
                if isinstance(r, ResolvedTrack):
                    resolved.append(r)
                elif isinstance(r, Unmatched):
                    unmatched.append(r)
            out.append((dpl, resolved, unmatched))
        return out

    # --- PLAN ---

    @staticmethod
    def plan(
        spotify_resolved: list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]],
        youtube_discovered: list[DiscoveredPlaylist],
    ) -> list[PlannedFolder]:
        return plan_folders(spotify_resolved, youtube_discovered)

    # --- DOWNLOAD ---

    @staticmethod
    def download(
        folders: list[PlannedFolder],
        *,
        downloader: Downloader,
    ) -> list[PlaylistOutcome]:
        if not folders:
            return []
        return downloader.download_all(folders)
