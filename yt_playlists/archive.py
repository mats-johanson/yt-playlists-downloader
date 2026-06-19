r"""Per-folder yt-dlp download archive.

Generalized from the v1 implementation:
- Extractor prefix is a parameter (currently "youtube"; pluggable for the future).
- Archive filename includes a stable playlist ID, so source-side renames don't
  orphan the archive.

Also exposes a Windows-safe `sanitize_name` (extended from v1's `/\` set).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config

_UNSAFE_FILENAME_CHARS = re.compile(r'[/\\:?*<>|"]')


def sanitize_name(name: str) -> str:
    """Replace filesystem-unsafe chars with `_`. Safe on APFS, NTFS, SMB, FAT32.

    The v1 implementation only handled `/` and `\\` since macOS APFS is permissive,
    but Finder/iTunes/SMB shares all choke on `:?*<>|"` even when the FS doesn't.
    """
    return _UNSAFE_FILENAME_CHARS.sub("_", name)


def archive_path(archives_dir: Path, folder_name: str, archive_id: str) -> Path:
    """Stable archive filename. Both folder_name and archive_id are sanitized.

    Format: `<folder>__<id>.txt`. Even if `folder_name` is renamed on the
    source side, the new archive's `<id>` matches the old one for the same
    playlist — so the file is rediscoverable.
    """
    return archives_dir / f"{sanitize_name(folder_name)}__{sanitize_name(archive_id)}.txt"


def read_archive(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def filter_new(
    video_ids: list[str], archived: set[str], extractor: str = config.YTDLP_ARCHIVE_PREFIX
) -> list[str]:
    """Return only the video IDs not present in the archive.

    `extractor` matches the prefix yt-dlp writes (`youtube`, `youtubemusic`, …).
    """
    prefix = f"{extractor} "
    return [vid for vid in video_ids if f"{prefix}{vid}" not in archived]


def count_archived(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def total_archived(archives_dir: Path) -> int:
    if not archives_dir.is_dir():
        return 0
    return sum(count_archived(p) for p in archives_dir.glob("*.txt"))
