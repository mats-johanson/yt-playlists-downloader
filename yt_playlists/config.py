from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

OUTPUT_ROOT = Path(
    os.environ.get("OUTPUT_ROOT") or PROJECT_ROOT.parent / "Youtube Downloads"
)

LOGS_DIR = PROJECT_ROOT / "logs"
ARCHIVES_DIR = LOGS_DIR / "archives"

DEFAULT_PLAYLISTS_FILE = PROJECT_ROOT / "config" / "playlists.txt"
UNAVAILABLE_FILE = LOGS_DIR / "unavailable-videos.txt"
DEBUG_LOG = LOGS_DIR / "debug.log"

PARALLEL_JOBS = 10
# Fragments are the chunks yt-dlp downloads per video. With PARALLEL_JOBS=10
# playlists in flight, fragment_concurrency=5 → 50 concurrent TCP streams,
# which routinely trips YouTube's bot-block. Keep this low.
FRAGMENT_CONCURRENCY = 2

# Shared layout — used by both the live dashboard and the final summary so
# column widths line up.
PLAYLIST_NAME_COL_WIDTH = 18


def ensure_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
