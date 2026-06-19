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
)


@dataclass(frozen=True)
class UnavailableVideo:
    """One video that failed in the current run. Identified by playlist + URL only."""
    playlist: str
    url: str


class UnavailableTracker:
    """Thread-safe collector of unavailable videos and bot-block detections.

    Persistence: appends to `log_path`. Caller is responsible for clearing the
    file at run start via `reset()` if a fresh log per run is desired.
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._lock = threading.Lock()
        self._entries: list[UnavailableVideo] = []
        self._bot_blocked: set[str] = set()

    def reset(self) -> None:
        """Truncate the persistent log and clear in-memory state."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._entries.clear()
            self._bot_blocked.clear()
            self.log_path.write_text("", encoding="utf-8")

    def record_error(self, playlist: str, message: str) -> None:
        if any(phrase in message for phrase in _BOT_BLOCK_PHRASES):
            with self._lock:
                self._bot_blocked.add(playlist)

        if not any(phrase in message for phrase in _UNAVAILABLE_PHRASES):
            return

        match = _VIDEO_ID_RE.search(message)
        if not match:
            return

        entry = UnavailableVideo(
            playlist=playlist,
            url=f"https://www.youtube.com/watch?v={match.group(1)}",
        )
        with self._lock:
            self._entries.append(entry)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"{entry.playlist}|{entry.url}\n")

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
