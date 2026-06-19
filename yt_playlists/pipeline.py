"""Phase orchestration.

DISCOVER  → fan out source.discover() for each configured source
RESOLVE   → for each Spotify track: override → cache → matcher
PLAN      → group + merge into PlannedFolders
DOWNLOAD  → existing downloader pipeline
SUMMARY   → render report

Each phase is one method on `Pipeline`. `__main__` wires them.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rich.console import Console

from . import config
from .downloader import Downloader
from .match_cache import MatchCache
from .matcher import resolve as matcher_resolve
from .outcomes import PlaylistOutcome
from .overrides import Overrides
from .playlist_plan import plan as plan_folders
from .sources import DiscoveredPlaylist, Source
from .sources.spotify_discover import SpotifySource
from .sources.youtube import YouTubeSource
from .tracks import PlannedFolder, ResolvedTrack, Unmatched
from .yt_search import youtube_search


class Pipeline:
    def __init__(
        self,
        *,
        console: Console,
        spotify_tag: str,
        youtube_urls: list[str],
        cache: MatchCache,
        overrides: Overrides,
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
        self._resolutions_log = resolutions_log
        self._unmatched_log = unmatched_log

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
        return spotify_discovered, youtube_discovered

    # --- RESOLVE ---

    def resolve_spotify(
        self, discovered: list[DiscoveredPlaylist]
    ) -> list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]]:
        # Flatten everything into work items so we can parallelize across playlists.
        all_tracks = sum((dpl.tracks for dpl in discovered), [])
        if not all_tracks:
            return [(dpl, [], []) for dpl in discovered]
        self._console.print(
            f"Resolving [bold]{len(all_tracks)}[/] Spotify track(s) → YouTube…"
        )

        # Resolve each track in parallel. Caching + overrides check happens here.
        resolved_or_unmatched: dict[str, ResolvedTrack | Unmatched] = {}

        def resolve_one(spotify_id: str, meta):
            override_video = self._overrides.get(spotify_id)
            if override_video:
                rt = ResolvedTrack(
                    youtube_video_id=override_video,
                    spotify=meta,
                    match_reason="override",
                )
                self._cache.put(rt)
                self._log_resolution(spotify_id, "override", override_video, None, "user override")
                return rt
            cached = self._cache.get(spotify_id)
            if cached is not None:
                self._log_resolution(spotify_id, "cache-hit", cached.youtube_video_id, cached.match_score, "cache")
                return cached
            result = matcher_resolve(meta, youtube_search)
            if isinstance(result, ResolvedTrack):
                self._cache.put(result)
                self._log_resolution(
                    spotify_id,
                    "matched",
                    result.youtube_video_id,
                    result.match_score,
                    result.match_reason or "",
                )
            else:
                self._log_resolution(
                    spotify_id,
                    "unmatched",
                    result.best_candidate_video_id,
                    result.best_score,
                    result.reason,
                )
                self._append_unmatched(result)
            return result

        with ThreadPoolExecutor(max_workers=config.RESOLVE_PARALLEL) as ex:
            future_to_id = {}
            for t in all_tracks:
                if not t.spotify:
                    continue
                future_to_id[ex.submit(resolve_one, t.spotify.spotify_id, t.spotify)] = (
                    t.spotify.spotify_id
                )
            for fut, sid in future_to_id.items():
                resolved_or_unmatched[sid] = fut.result()

        # Re-bucket per playlist.
        out: list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]] = []
        for dpl in discovered:
            resolved: list[ResolvedTrack] = []
            unmatched: list[Unmatched] = []
            for t in dpl.tracks:
                if not t.spotify:
                    continue
                r = resolved_or_unmatched.get(t.spotify.spotify_id)
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

    # --- logging helpers ---

    def _log_resolution(
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
        with self._resolutions_log.open("a", encoding="utf-8") as f:
            f.write(line)

    def _append_unmatched(self, u: Unmatched) -> None:
        self._unmatched_log.parent.mkdir(parents=True, exist_ok=True)
        suggestion = u.best_candidate_video_id or "—"
        line = (
            f'"{u.spotify.spotify_id}" = "{suggestion}"  '
            f"# {u.spotify.artist} — {u.spotify.title}  (score {u.best_score:.1f})\n"
        )
        with self._unmatched_log.open("a", encoding="utf-8") as f:
            f.write(line)
