"""Paths, ports, thresholds, and the tag regex.

Every constant the rest of the package treats as tunable lives here.
TOML config overrides specific values at runtime; nothing else hardcodes them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# --- paths ---

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

OUTPUT_ROOT = Path(
    os.environ.get("OUTPUT_ROOT") or PROJECT_ROOT.parent / "Synced Music"
)

CONFIG_DIR = PROJECT_ROOT / "config"
PLAYLISTS_TOML = CONFIG_DIR / "playlists.toml"
OVERRIDES_TOML = CONFIG_DIR / "spotify_overrides.toml"

LOGS_DIR = PROJECT_ROOT / "logs"
ARCHIVES_DIR = LOGS_DIR / "archives"
MATCH_CACHE = LOGS_DIR / "match_cache.json"
RESOLUTIONS_LOG = LOGS_DIR / "resolutions.log"
UNMATCHED_LOG = LOGS_DIR / "unmatched.txt"
DEBUG_LOG = LOGS_DIR / "debug.log"
UNAVAILABLE_FILE = LOGS_DIR / "unavailable-videos.txt"
# Persistent video-id ledger. Resists across runs; once a video here, the
# downloader refuses to attempt it again. Prevents re-spinning on known-dead
# content (account terminated, copyright, private, geo-block).
DEAD_VIDEOS_FILE = LOGS_DIR / "dead-videos.txt"
# {video_id: {"added_at": ISO-8601, "source_playlist": "..."}}
# Populated during discover/resolve from Spotify's playlist_items.added_at
# (exact) and from YT-only playlist position (proxy). Consumed by the
# --sync-traktor-dates subcommand to overwrite Traktor's IMPORT_DATE so
# the library sorts by user discovery order, not by Traktor scan order.
DISCOVERY_DATES = LOGS_DIR / "discovery-dates.json"

USER_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "yt-playlists"
SPOTIFY_TOKEN_FILE = USER_CONFIG_DIR / "spotify-token.json"

# --- parallelism / pacing ---

PARALLEL_JOBS = 10
FRAGMENT_CONCURRENCY = 2
SCAN_STAGGER_SECONDS = 0.5
DOWNLOAD_STAGGER_SECONDS = 1.0
RESOLVE_PARALLEL = 8                    # matcher workers
RESOLVE_STAGGER_SECONDS = 0.2

# --- display ---

PLAYLIST_NAME_COL_WIDTH = 18

# --- Spotify ---

SPOTIFY_CLIENT_ID_ENV = "SPOTIFY_CLIENT_ID"
SPOTIFY_REDIRECT_PORT = int(os.environ.get("SPOTIFY_REDIRECT_PORT") or 8765)
SPOTIFY_REDIRECT_URI = f"http://127.0.0.1:{SPOTIFY_REDIRECT_PORT}/callback"
SPOTIFY_SCOPES = "playlist-read-private"

# Default tag — case-insensitive, word-bounded match. TOML can override.
# Format: a literal substring (e.g. "[DJ]"). The matcher wraps it with word
# boundaries at runtime so "seeing [DJ] play live" does NOT trigger.
DEFAULT_SPOTIFY_TAG = "[DJ]"


def spotify_tag_regex(tag: str) -> re.Pattern:
    """Word-bounded, case-insensitive match for `tag` in a description."""
    return re.compile(rf"(^|\s){re.escape(tag)}(\s|$)", re.IGNORECASE)


# --- Matcher signals (ported from spotDL signal weights) ---

# All weights apply in a 0..100-ish space; higher is better.
MATCH_DURATION_DECAY_PER_SEC = 0.05        # exp decay factor: score *= exp(-decay * delta_s)
MATCH_ARTIST_MIN_SIMILARITY = 0.4          # below this -> not a match (lowered 0.5→0.4 to catch
                                            # multi-word band names where YT credits only the
                                            # primary artist, e.g. "Joe Shirimani Na Bangoni
                                            # Bandawu" appearing in YT as just "Joe Shirimani")
MATCH_FORBIDDEN_PENALTY = 15.0
MATCH_FORBIDDEN_TOKENS = (
    "live", "cover", "karaoke", "instrumental", "remix",
    "acoustic", "concert", "tribute",
    # Note: NOT including bare "mix" — DJ music routinely has legitimate
    # "Extended Mix" / "Original Mix" / "Club Mix" canonical versions.
    # "remix" stays — that's the meaningful signal.
)
MATCH_EXPLICIT_MISMATCH_PENALTY = 5.0
MATCH_THRESHOLD = 70.0                      # below this -> unmatched.
                                            # Tried 65 but it let in two false positives:
                                            #   - Cyrillic-vs-Latin transliteration cases where
                                            #     artist + duration matched but title_sim=0 → any
                                            #     same-duration track by the artist would pass.
                                            #   - Tracks where duration_sim was ~0.05 (1-min off)
                                            #     squeaked above 65 on artist+title alone.
                                            # 70 keeps the 0.4 artist_sim relaxation while
                                            # requiring corroborating signal strength.

YT_SEARCH_CANDIDATES = 5

# --- archive prefix (generalized, parameterized) ---

# yt-dlp writes archive lines as "<extractor> <video_id>".
# Set per extractor; we currently only target YouTube via yt-dlp.
YTDLP_ARCHIVE_PREFIX = "youtube"


# --- dirs ---

def ensure_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
