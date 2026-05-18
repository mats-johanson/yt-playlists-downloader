"""Per-playlist outcome types.

Lives in its own module to break a would-be cycle between downloader (which
constructs outcomes) and dashboard (which renders them).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OutcomeReason(StrEnum):
    """Why a playlist's run ended the way it did. Drives summary + dashboard labels."""

    DONE = "done"
    EMPTY = "empty"          # ran, but yt-dlp produced zero songs (every one was archived or filtered)
    BOT_BLOCKED = "blocked"  # at least one 429 / "confirm you're not a bot" detected
    ERROR = "error"          # playlist-level failure (auth, geo-block, deleted, network)


@dataclass(frozen=True)
class PlaylistOutcome:
    name: str
    songs_done: int
    reason: OutcomeReason

    @property
    def failed(self) -> bool:
        # EMPTY means "nothing downloaded but no error" — usually the playlist's
        # new entries are now unavailable. Not a script failure; rendered as
        # informational, not alarming.
        return self.reason in (OutcomeReason.BOT_BLOCKED, OutcomeReason.ERROR)
