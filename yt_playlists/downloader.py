from __future__ import annotations

import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from . import config
from .archive import archive_path
from .dashboard import Dashboard, PlaylistTaskHandle
from .outcomes import OutcomeReason, PlaylistOutcome
from .scanner import ScanResult
from .unavailable import UnavailableTracker
from .ydl_logger import YDLLogger

# ---------------------------------------------------------------------------
# Per-playlist state — split into three single-responsibility pieces.
# ---------------------------------------------------------------------------


class SongCounter:
    """Counts unique songs completed in this playlist run. Dedupes by video id."""

    __slots__ = ("_seen", "_count")

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    def record(self, video_id: str | None) -> bool:
        """Returns True if this id was new (and counted), False if duplicate."""
        if not video_id or video_id in self._seen:
            return False
        self._seen.add(video_id)
        self._count += 1
        return True


class ProgressForwarder:
    """Adapts yt-dlp's progress_hook dict to a PlaylistTaskHandle.

    Holds the only mutable state needed during a playlist's download:
    current song title (so completion events can name it) and the song counter.
    """

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


# ---------------------------------------------------------------------------
# Helpers — yt-dlp options + filesystem moves
# ---------------------------------------------------------------------------


def _ydl_opts(
    *,
    archive: Path,
    out_tmpl: str,
    logger: YDLLogger,
    progress_hook,
    debug: bool,
) -> dict:
    return {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
        "download_archive": str(archive),
        "concurrent_fragment_downloads": config.FRAGMENT_CONCURRENCY,
        "force_ipv4": True,
        "outtmpl": out_tmpl,
        # "only_download" lets playlist-level errors (auth/geo/deleted) raise
        # while still skipping over per-video failures within a playlist.
        "ignoreerrors": "only_download",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": logger,
        "progress_hooks": [progress_hook],
        "verbose": debug,
    }


def _next_available_name(dest: Path) -> Path:
    """If `dest` already exists, return `dest` with a numeric suffix that doesn't.

    Two playlists containing the same song name would otherwise silently
    overwrite each other on move.
    """
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


def _move_downloads(temp_dir: Path, output_root: Path) -> None:
    """Move mp3s from `temp_dir/<playlist>/...` to `output_root/<playlist>/`."""
    if not temp_dir.is_dir():
        return
    for playlist_dir in temp_dir.iterdir():
        if not playlist_dir.is_dir():
            continue
        dest_dir = output_root / playlist_dir.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        for mp3 in playlist_dir.glob("*.mp3"):
            shutil.move(str(mp3), str(_next_available_name(dest_dir / mp3.name)))


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------


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
        debug_log: Path,
        debug: bool = False,
    ):
        self._archives_dir = archives_dir
        self._output_root = output_root
        self._dashboard = dashboard
        self._unavailable = unavailable
        self._debug_log = debug_log
        self._debug = debug

    def _prepare_workspace(self, scan: ScanResult) -> _Workspace:
        archive = archive_path(self._archives_dir, scan.name)
        temp_root = Path(tempfile.mkdtemp(prefix="ytdl-"))
        out_tmpl = str(
            temp_root
            / "%(playlist_title)s"
            / "%(artist&{} - |)s%(title).100s.%(ext)s"
        )
        return _Workspace(archive=archive, temp_root=temp_root, out_tmpl=out_tmpl)

    def _run_ydl(
        self,
        scan: ScanResult,
        workspace: _Workspace,
        forwarder: ProgressForwarder,
    ) -> OutcomeReason | None:
        """Run yt-dlp for one playlist. Returns a fatal-error reason, or None on success."""
        logger = YDLLogger(scan.name, self._debug_log, self._unavailable.record_error)
        opts = _ydl_opts(
            archive=workspace.archive,
            out_tmpl=workspace.out_tmpl,
            logger=logger,
            progress_hook=forwarder,
            debug=self._debug,
        )
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([scan.url])
        except DownloadError:
            # Playlist-level failure (auth, geo-block, deleted playlist URL).
            # The logger already wrote the message to debug.log via on_error;
            # we don't re-route through unavailable.record_error here to avoid
            # double-funnelling.
            return OutcomeReason.ERROR
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unexpected: {e}")
            return OutcomeReason.ERROR
        return None

    def _finalize(self, workspace: _Workspace) -> None:
        try:
            _move_downloads(workspace.temp_root, self._output_root)
        finally:
            shutil.rmtree(workspace.temp_root, ignore_errors=True)

    def _classify(self, scan: ScanResult, songs_done: int, fatal: OutcomeReason | None) -> OutcomeReason:
        if fatal is not None:
            return fatal
        if songs_done > 0:
            return OutcomeReason.DONE
        if self._unavailable.is_bot_blocked(scan.name):
            return OutcomeReason.BOT_BLOCKED
        return OutcomeReason.EMPTY

    def _download_one(self, scan: ScanResult) -> PlaylistOutcome:
        handle = self._dashboard.add_playlist(scan.name, scan.new_count)
        workspace = self._prepare_workspace(scan)
        forwarder = ProgressForwarder(handle)

        fatal = self._run_ydl(scan, workspace, forwarder)
        self._finalize(workspace)

        reason = self._classify(scan, forwarder.songs_done, fatal)
        handle.playlist_completed(songs_done=forwarder.songs_done, reason=reason)
        return PlaylistOutcome(name=scan.name, songs_done=forwarder.songs_done, reason=reason)

    def download_all(
        self, scans: list[ScanResult], parallel: int
    ) -> list[PlaylistOutcome]:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            futures = [ex.submit(self._download_one, s) for s in scans]
            return [f.result() for f in futures]
