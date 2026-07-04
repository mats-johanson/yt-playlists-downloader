"""Provider-agnostic downloader.

Eats `PlannedFolder` instances: a list of `ResolvedTrack`s that already point
at concrete YouTube video IDs, plus a pre-built per-video info_dict override
map (`folder.info_overrides()`). The downloader doesn't know what source the
overrides came from — Spotify, MusicBrainz, hand-written, whatever.

Reused largely from v1; the changes are:
- accepts `PlannedFolder` instead of `ScanResult`
- attaches a unified `MetadataPP` at pre_process, fed by `info_overrides()`
  (the PP merges the dict into info_dict, falling back to "Artist - Title"
  regex when no override exists for a video)
- archive filename includes the stable playlist id (rename-safe)
"""

from __future__ import annotations

import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from . import config
from .archive import archive_path, filter_new, read_archive
from .dashboard import Dashboard, PlaylistTaskHandle
from .match_cache import MatchCache
from .outcomes import OutcomeReason, PlaylistOutcome
from .postprocessors.spotify_metadata import MetadataPP
from .tracks import PlannedFolder
from .unavailable import UnavailableTracker
from .ydl_logger import YDLLogger


class SongCounter:
    __slots__ = ("_seen", "_count")

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def record(self, video_id: str | None) -> bool:
        if not video_id or video_id in self._seen:
            return False
        self._seen.add(video_id)
        self._count += 1
        return True


class ProgressForwarder:
    __slots__ = ("_handle", "_counter", "_current_title")

    def __init__(self, handle: PlaylistTaskHandle):
        self._handle = handle
        self._counter = SongCounter()
        self._current_title = "starting…"

    @property
    def songs_done(self) -> int:
        return self._counter.count

    def __call__(self, d: dict) -> None:
        status = d.get("status")
        info = d.get("info_dict") or {}

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            pct = (downloaded / total * 100) if total > 0 else 0.0
            self._current_title = info.get("title") or self._current_title
            self._handle.update_song(title=self._current_title, pct=pct)
            return

        if status == "finished":
            video_id = info.get("id") or self._current_title
            if self._counter.record(video_id):
                self._handle.song_completed(
                    song_title=self._current_title,
                    songs_done=self._counter.count,
                )


def _build_ydl_opts(
    *,
    archive: Path,
    out_tmpl: str,
    logger: YDLLogger,
    progress_hook,
    match_filter,
    debug: bool,
) -> dict:
    return {
        "format": "bestaudio/best",
        "extractor_args": {"youtube": {"player_client": ["default", "web_embedded"]}},
        # EJS = External JS challenge solver. yt-dlp's internal JS interpreter
        # can't handle YouTube's newest signature variants; without this opt,
        # those videos fail with HTTP 403 even when deno is installed.
        # `ejs:github` fetches the solver script from yt-dlp's repo and runs it
        # under our local deno; cached after first fetch.
        "remote_components": ["ejs:github"],
        "writethumbnail": True,
        # ZERO retries on any HTTP error. yt-dlp's defaults (10/10/3) spin on
        # 403'd videos for ~5 minutes each via exponential backoff — those
        # retries are wasted (the video isn't suddenly going to un-403) AND
        # actively hostile, each one counts against YouTube's per-IP request
        # budget. Spinning on a 403 storm is exactly how a soft rate-limit
        # becomes a hard IP block. Skip fast; the next run picks up anything
        # that was a genuinely transient blip — and persistent dead videos
        # land in logs/dead-videos.txt so we never attempt them again.
        "retries": 0,
        "fragment_retries": 0,
        "extractor_retries": 0,
        # Stay polite — these three keep our request rate well under YouTube's
        # per-IP ceiling so we don't earn a soft block (which then escalates
        # into the 403 storm we just diagnosed in logs/debug.log on 14:11).
        # sleep_interval_requests: per-HTTP-call jitter (page fetch, player
        #   script fetch, fragment).
        # sleep_interval / max_sleep_interval: random 1–3 s between videos
        #   within a single playlist. With 10× parallel playlists, that
        #   smooths the aggregate hit rate to YouTube nicely.
        "sleep_interval_requests": 0.2,
        "sleep_interval": 1,
        "max_sleep_interval": 3,
        # MetadataPP attached separately via add_post_processor at pre_process —
        # it handles BOTH Spotify-canonical writes and the "Artist - Title"
        # fallback regex for YouTube-only tracks. Removing the legacy
        # MetadataFromField here eliminates a post_process re-stomp that was
        # overwriting Spotify-canonical artist tags on multi-artist tracks.
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"},
            {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": False},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
        "download_archive": str(archive),
        "concurrent_fragment_downloads": config.FRAGMENT_CONCURRENCY,
        "force_ipv4": True,
        "outtmpl": out_tmpl,
        "ignoreerrors": "only_download",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": logger,
        "progress_hooks": [progress_hook],
        "match_filter": match_filter,
        "verbose": debug,
    }


def _next_available_name(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    parent = dest.parent
    i = 2
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _move_downloads(temp_dir: Path, dest_dir: Path) -> None:
    if not temp_dir.is_dir():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for path in temp_dir.rglob("*.mp3"):
        shutil.move(str(path), str(_next_available_name(dest_dir / path.name)))


@dataclass
class _Workspace:
    archive: Path
    temp_root: Path
    out_tmpl: str


class Downloader:
    def __init__(
        self,
        *,
        archives_dir: Path,
        output_root: Path,
        dashboard: Dashboard,
        unavailable: UnavailableTracker,
        cache: MatchCache,
        debug_log: Path,
        debug: bool = False,
    ):
        self._archives_dir = archives_dir
        self._output_root = output_root
        self._dashboard = dashboard
        self._unavailable = unavailable
        self._cache = cache
        self._debug_log = debug_log
        self._debug = debug

    def _make_bot_block_filter(self):
        unavailable = self._unavailable

        def filt(info_dict, *, incomplete=False):
            if unavailable.any_bot_blocked():
                return "skipping — bot-block already triggered in this run"
            return None

        return filt

    def _archive_for(self, folder: PlannedFolder) -> Path:
        return archive_path(self._archives_dir, folder.folder_name, folder.archive_id)

    def _prepare_workspace(self, folder: PlannedFolder) -> _Workspace:
        temp_root = Path(tempfile.mkdtemp(prefix="ytdl-"))
        out_tmpl = str(
            temp_root / "%(artist&{} - |)s%(title).100s.%(ext)s"
        )
        return _Workspace(
            archive=self._archive_for(folder), temp_root=temp_root, out_tmpl=out_tmpl
        )

    def _run_ydl(
        self,
        folder: PlannedFolder,
        workspace: _Workspace,
        forwarder: ProgressForwarder,
        video_ids: list[str],
    ) -> OutcomeReason | None:
        logger = YDLLogger(folder.folder_name, self._debug_log, self._unavailable.record_error)

        # Generic info_dict overrides — the planning layer already translated
        # whatever the upstream source had (Spotify, MusicBrainz, hand pin) into
        # yt-dlp's info_dict shape. Downloader stays provider-agnostic.
        info_overrides = folder.info_overrides()

        opts = _build_ydl_opts(
            archive=workspace.archive,
            out_tmpl=workspace.out_tmpl,
            logger=logger,
            progress_hook=forwarder,
            match_filter=self._make_bot_block_filter(),
            debug=self._debug,
        )

        urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]

        try:
            with YoutubeDL(opts) as ydl:
                # MetadataPP at pre_process — applies per-video info_dict
                # overrides (when present) AND falls back to "Artist - Title"
                # regex parse for videos without overrides. Attach
                # unconditionally; an empty overrides map still gets the
                # fallback parse for YT-only folders.
                ydl.add_post_processor(
                    MetadataPP(ydl, overrides=info_overrides),
                    when="pre_process",
                )
                ydl.download(urls)
        except DownloadError:
            return OutcomeReason.ERROR
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unexpected: {e}")
            return OutcomeReason.ERROR
        return None

    def _finalize(self, workspace: _Workspace, folder: PlannedFolder) -> None:
        dest_dir = self._output_root / folder.folder_name
        try:
            _move_downloads(workspace.temp_root, dest_dir)
        finally:
            shutil.rmtree(workspace.temp_root, ignore_errors=True)

    def _classify(self, folder: PlannedFolder, songs_done: int, fatal) -> OutcomeReason:
        if fatal is not None:
            return fatal
        if songs_done > 0:
            return OutcomeReason.DONE
        if (
            self._unavailable.is_bot_blocked(folder.folder_name)
            or self._unavailable.any_bot_blocked()
        ):
            return OutcomeReason.BOT_BLOCKED
        return OutcomeReason.EMPTY

    def _download_one(self, folder: PlannedFolder) -> PlaylistOutcome:
        # Pre-filter via the archive: keep only video IDs not already on disk.
        # yt-dlp also does this internally via download_archive, but pre-filtering
        # lets us short-circuit the entire ydl invocation when nothing is new.
        archived = read_archive(self._archive_for(folder))
        all_video_ids = [r.youtube_video_id for r in folder.resolved if r.youtube_video_id]
        new_video_ids = [
            v for v in filter_new(all_video_ids, archived)
            if not self._unavailable.is_known_dead(v)
        ]

        handle = self._dashboard.add_playlist(folder.folder_name, len(new_video_ids))

        if not new_video_ids:
            handle.playlist_completed(songs_done=0, reason=OutcomeReason.DONE)
            return PlaylistOutcome(name=folder.folder_name, songs_done=0, reason=OutcomeReason.DONE)

        if self._unavailable.any_bot_blocked():
            handle.playlist_completed(songs_done=0, reason=OutcomeReason.BOT_BLOCKED)
            return PlaylistOutcome(
                name=folder.folder_name, songs_done=0, reason=OutcomeReason.BOT_BLOCKED
            )

        workspace = self._prepare_workspace(folder)
        forwarder = ProgressForwarder(handle)
        fatal = self._run_ydl(folder, workspace, forwarder, new_video_ids)
        self._finalize(workspace, folder)
        self._evict_dead_from_cache(folder)

        reason = self._classify(folder, forwarder.songs_done, fatal)
        handle.playlist_completed(songs_done=forwarder.songs_done, reason=reason)
        return PlaylistOutcome(
            name=folder.folder_name, songs_done=forwarder.songs_done, reason=reason
        )

    def _evict_dead_from_cache(self, folder: PlannedFolder) -> None:
        """Drop any cache entry whose video died at download time.

        Without this, a next run would cache-hit the dead `video_id`, fail
        again, and never re-resolve to a working candidate. Eviction lets the
        next run go back through the matcher for a fresh winner.
        """
        attempted = {r.youtube_video_id for r in folder.resolved if r.youtube_video_id}
        if not attempted:
            return
        dead_urls = {
            e.url.rsplit("v=", 1)[-1]
            for e in self._unavailable.entries()
            if e.playlist == folder.folder_name
        }
        for video_id in attempted & dead_urls:
            self._cache.evict_by_video_id(video_id)

    def download_all(self, folders: list[PlannedFolder]) -> list[PlaylistOutcome]:
        ex = ThreadPoolExecutor(max_workers=config.PARALLEL_JOBS)
        futures: list = []
        outcomes: list[PlaylistOutcome] = []
        try:
            for i, f in enumerate(folders):
                if i > 0:
                    time.sleep(config.DOWNLOAD_STAGGER_SECONDS)
                futures.append(ex.submit(self._download_one, f))
            for fut in futures:
                outcomes.append(fut.result())
        except KeyboardInterrupt:
            # Don't let ThreadPoolExecutor.__exit__ block on shutdown(wait=True).
            # cancel_futures drops anything that hasn't started; running yt-dlp
            # workers will see SIGINT shortly and exit on their own. Already-
            # written MP3s and archive lines are durable, so re-running picks
            # up exactly where we left off.
            ex.shutdown(wait=False, cancel_futures=True)
            raise
        ex.shutdown(wait=True)
        return outcomes
