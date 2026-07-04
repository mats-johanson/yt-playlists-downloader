"""yt-dlp's `ytsearchN:` extractor wrapped to return matcher-ready candidates.

Uses `extract_flat="in_playlist"` so we get flat metadata (id, title, duration,
uploader) per candidate without a full info fetch each. Detail fetch only on
the eventual winner during the download phase.

A shared `UnavailableTracker` short-circuits the search if a global YouTube
bot-block has already been observed. Without that hook, the download phase's
circuit-breaker would still let 487 ytsearch calls fan out during resolve and
each one would burn through 5 candidates worth of failing extraction, badly
polluting the match cache with `Unmatched` rows.
"""

from __future__ import annotations

from yt_dlp import YoutubeDL

from .matcher import YtCandidate
from .unavailable import UnavailableTracker

_SEARCH_OPTS = {
    "extract_flat": "in_playlist",
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "skip_download": True,
    "force_ipv4": True,
    "extractor_args": {"youtube": {"player_client": ["default", "web_embedded"]}},
}


def youtube_search(
    query: str,
    n: int = 5,
    *,
    unavailable: UnavailableTracker | None = None,
) -> list[YtCandidate]:
    """Return up to `n` candidate YouTube videos for `query`.

    If `unavailable` is provided and any prior search/download in this run
    tripped YouTube's bot-check, returns `[]` without contacting YouTube.
    """
    if unavailable is not None and unavailable.any_bot_blocked():
        return []
    url = f"ytsearch{n}:{query}"
    try:
        with YoutubeDL(_SEARCH_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return []
    if not info:
        return []
    out: list[YtCandidate] = []
    for entry in info.get("entries") or []:
        if not entry or not entry.get("id"):
            continue
        out.append(
            YtCandidate(
                video_id=entry["id"],
                title=entry.get("title") or "",
                uploader=entry.get("uploader") or entry.get("channel"),
                duration_s=(
                    float(entry["duration"]) if entry.get("duration") is not None else None
                ),
            )
        )
    return out
