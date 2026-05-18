from __future__ import annotations

from pathlib import Path

# yt-dlp writes archive lines as "<extractor> <video_id>", e.g. "youtube dQw4w9WgXcQ".
# We diff against this exact prefix; if yt-dlp ever changes the extractor name
# we will silently re-download everything, so this constant is load-bearing.
_YTDLP_ARCHIVE_PREFIX = "youtube "


def sanitize_name(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_")


def archive_path(archives_dir: Path, playlist_name: str) -> Path:
    return archives_dir / f"{sanitize_name(playlist_name)}.txt"


def read_archive(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def filter_new(video_ids: list[str], archived: set[str]) -> list[str]:
    return [vid for vid in video_ids if f"{_YTDLP_ARCHIVE_PREFIX}{vid}" not in archived]


def count_archived(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def total_archived(archives_dir: Path) -> int:
    if not archives_dir.is_dir():
        return 0
    return sum(count_archived(p) for p in archives_dir.glob("*.txt"))
