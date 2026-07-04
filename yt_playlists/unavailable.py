from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

# Parses yt-dlp error log lines like "[youtube] dQw4w9WgXcQ: Video unavailable".
# This is yt-dlp's user-facing log format and has been stable through the
# 202x.x line — but it IS a log string, not an API. If yt-dlp ever changes
# the bracket/colon convention, unavailable videos silently stop being captured.
_VIDEO_ID_RE = re.compile(r"\[youtube\]\s+([A-Za-z0-9_-]{6,}):")
_UNAVAILABLE_PHRASES = (
    "Video unavailable",
    "Private video",
    "has been removed",
)
_BOT_BLOCK_PHRASES = (
    "Sign in to confirm",
    "confirm you're not a bot",
    "HTTP Error 429",
    # Treat bare HTTP 403 on a video data fetch as bot-detection too. This is
    # NOT "the video is dead" — the video might be perfectly fine on YT — it's
    # YouTube telling our client "you've made too many requests, slow down."
    # Continuing to attempt downloads just deepens the rate-limit; circuit-
    # break the run instead and let the user re-run later.
    "HTTP Error 403",
)
# Strict subset of _UNAVAILABLE_PHRASES + extras: failure modes we treat as
# PERMANENT, not transient. The whole point of the persistent ledger is to never
# retry these; mis-tagging a transient failure as permanent is the regression
# to watch for. Add phrases here only if a re-attempt cannot help.
_PERMANENT_DEATH_PHRASES = (
    "account associated with this video has been terminated",
    "removed for violating",                # ToS violation
    "removed by the user",
    "Private video",                        # without cookies — treat as permanent
    "copyright",                            # any phrasing of copyright takedown
    "no longer available",                  # generic but always permanent in practice
)


@dataclass(frozen=True)
class UnavailableVideo:
    """One video that failed in the current run. Identified by playlist + URL only."""
    playlist: str
    url: str


class UnavailableTracker:
    """Thread-safe collector of unavailable videos and bot-block detections.

    Two layers of state:
      - **Per-run** (`_entries`, `_bot_blocked`): cleared by `reset_run_state()`
        at the start of each run; drives the summary report.
      - **Persistent** (`_dead_ids` + `dead_videos_file`): survives across runs.
        Once a video lands here, `is_known_dead()` returns True forever, and the
        downloader refuses to attempt re-downloading it. Cleared only by the
        user editing the file.
    """

    def __init__(
        self,
        log_path: Path,
        dead_videos_file: Path | None = None,
    ):
        self.log_path = log_path
        self.dead_videos_file = dead_videos_file
        self._lock = threading.Lock()
        self._entries: list[UnavailableVideo] = []
        self._bot_blocked: set[str] = set()
        self._dead_ids: set[str] = self._load_dead_ids()

    def _load_dead_ids(self) -> set[str]:
        if not self.dead_videos_file or not self.dead_videos_file.exists():
            return set()
        try:
            return {
                line.strip()
                for line in self.dead_videos_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            }
        except OSError:
            return set()

    def reset_run_state(self) -> None:
        """Truncate the per-run log + clear per-run in-memory state.

        Does NOT touch the persistent dead-video ledger.
        """
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._entries.clear()
            self._bot_blocked.clear()
            self.log_path.write_text("", encoding="utf-8")

    # Kept for backwards compat with existing callers.
    reset = reset_run_state

    def is_known_dead(self, video_id: str) -> bool:
        with self._lock:
            return video_id in self._dead_ids

    def record_error(self, playlist: str, message: str) -> None:
        if any(phrase in message for phrase in _BOT_BLOCK_PHRASES):
            with self._lock:
                self._bot_blocked.add(playlist)

        if not any(phrase in message for phrase in _UNAVAILABLE_PHRASES):
            return

        match = _VIDEO_ID_RE.search(message)
        if not match:
            return
        video_id = match.group(1)

        entry = UnavailableVideo(
            playlist=playlist,
            url=f"https://www.youtube.com/watch?v={video_id}",
        )
        with self._lock:
            self._entries.append(entry)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"{entry.playlist}|{entry.url}\n")

        if self._is_permanent(message):
            self._mark_dead(video_id)

    def _mark_dead(self, video_id: str) -> None:
        """Add to persistent ledger so the next run skips this video entirely."""
        with self._lock:
            if video_id in self._dead_ids:
                return
            self._dead_ids.add(video_id)
            if self.dead_videos_file is not None:
                self.dead_videos_file.parent.mkdir(parents=True, exist_ok=True)
                with self.dead_videos_file.open("a", encoding="utf-8") as f:
                    f.write(f"{video_id}\n")

    @staticmethod
    def _is_permanent(message: str) -> bool:
        lowered = message.lower()
        return any(phrase.lower() in lowered for phrase in _PERMANENT_DEATH_PHRASES)

    def is_bot_blocked(self, playlist: str) -> bool:
        with self._lock:
            return playlist in self._bot_blocked

    def bot_blocked_playlists(self) -> set[str]:
        with self._lock:
            return set(self._bot_blocked)

    def any_bot_blocked(self) -> bool:
        """True if any playlist in this run has tripped YouTube's bot-check.

        Used as a global circuit-breaker: once the IP is flagged, further
        requests just fail the same way and may extend the block, so the
        downloader stops issuing them.
        """
        with self._lock:
            return bool(self._bot_blocked)

    def count_for(self, playlist: str) -> int:
        with self._lock:
            return sum(1 for e in self._entries if e.playlist == playlist)

    def entries(self) -> list[UnavailableVideo]:
        with self._lock:
            return list(self._entries)
