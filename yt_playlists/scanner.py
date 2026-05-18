from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL

from .archive import archive_path, filter_new, read_archive


@dataclass(frozen=True)
class ScanResult:
    url: str
    name: str
    total: int
    new_count: int

    @property
    def has_work(self) -> bool:
        return self.new_count > 0


_SCAN_OPTS = {
    "extract_flat": True,
    "quiet": True,
    "no_warnings": True,
    "force_ipv4": True,
    "skip_download": True,
}


def _scan_one(url: str, archives_dir: Path) -> ScanResult:
    try:
        with YoutubeDL(_SCAN_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return ScanResult(url=url, name="Unknown Playlist", total=0, new_count=0)

    if not info:
        return ScanResult(url=url, name="Unknown Playlist", total=0, new_count=0)

    name = info.get("title") or "Unknown Playlist"
    entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
    ids = [e["id"] for e in entries]

    archived = read_archive(archive_path(archives_dir, name))
    new = filter_new(ids, archived)

    return ScanResult(url=url, name=name, total=len(ids), new_count=len(new))


def scan_all(urls: list[str], archives_dir: Path, parallel: int) -> list[ScanResult]:
    """Scan playlists in parallel. Results returned in input order."""
    if not urls:
        return []

    results: list[ScanResult] = [None] * len(urls)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {
            ex.submit(_scan_one, url, archives_dir): idx
            for idx, url in enumerate(urls)
        }
        for fut, idx in futures.items():
            results[idx] = fut.result()
    return results
