"""yt-dlp's `ytsearchN:` extractor wrapped to return matcher-ready candidates.

Uses `extract_flat="in_playlist"` so we get flat metadata (id, title, duration,
uploader) per candidate without a full info fetch each. Detail fetch only on
the eventual winner during the download phase.
"""

from __future__ import annotations

from yt_dlp import YoutubeDL

from .matcher import YtCandidate

_SEARCH_OPTS = {
    "extract_flat": "in_playlist",
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "skip_download": True,
    "force_ipv4": True,
    "extractor_args": {"youtube": {"player_client": ["default", "web_embedded"]}},
}


def youtube_search(query: str, n: int = 5) -> list[YtCandidate]:
    """Return up to `n` candidate YouTube videos for `query`."""
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
