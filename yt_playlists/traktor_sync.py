"""Overwrite Traktor's IMPORT_DATE per ENTRY with the user's discovery date.

Traktor's "Imported" column reflects when Traktor first scanned the file —
not when the user added the track to their playlist. This module sources
the real discovery date (Spotify `added_at` or the YT position proxy) and
writes it into `collection.nml` so sorting by Imported reflects discovery
order.

Operation is idempotent and safe:
- timestamped backup of collection.nml created on every run
- XML re-parsed from a tmp file before atomic rename, so a write that
  somehow produces invalid XML is rejected without touching the live NML
- only ENTRY records whose file currently exists and whose video id has
  a known discovery date are touched; everything else is left intact
- IMPORT_DATE values already matching the target are skipped (no write)
"""

from __future__ import annotations

import os
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.console import Console

from .discovery_dates import DiscoveryDates
from .purl_index import PurlIndex


def is_traktor_running() -> bool:
    """`pgrep -ix Traktor` — returns True if any process matches exactly."""
    try:
        result = subprocess.run(
            ["pgrep", "-ix", "Traktor"],
            capture_output=True, check=False, timeout=2,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # If pgrep is missing or hangs, assume Traktor isn't running. The
        # absolute worst case is a race-with-Traktor-open; the atomic-rename
        # write protects collection.nml from partial corruption, and the
        # backup we always make is the rollback.
        return False


def sync_import_dates(
    *,
    console: Console,
    nml_path: Path,
    discovery_dates: DiscoveryDates,
    synced_root: Path,
    purl_index: PurlIndex | None = None,
) -> int:
    if not nml_path.exists():
        console.print(f"[red]collection.nml not found:[/] {nml_path}")
        return 1
    dates = discovery_dates.all()
    if not dates:
        console.print("[yellow]No discovery dates recorded yet.[/]")
        console.print(
            "[dim]Run ./download_playlists.sh once to populate "
            "logs/discovery-dates.json from your Spotify + YT playlists, "
            "then re-run --sync-traktor-dates.[/]"
        )
        return 0

    bak = nml_path.with_suffix(
        nml_path.suffix + f".bak.discovery-dates.{time.strftime('%Y%m%d-%H%M%S')}"
    )
    bak.write_bytes(nml_path.read_bytes())
    console.print(f"[dim]Backup → {bak.name}[/]")

    tree = ET.parse(nml_path)
    root = tree.getroot()

    counts = _Counts()
    with console.status("Indexing MP3 video IDs…"):
        path_to_vid = _build_path_to_video_id_index(synced_root, purl_index)
    if purl_index is not None:
        purl_index.flush()

    for entry in root.iter("ENTRY"):
        loc = entry.find("LOCATION")
        if loc is None:
            counts.skipped_no_location += 1
            continue
        path = _loc_to_path(loc)
        if path is None:
            counts.skipped_no_location += 1
            continue
        if not Path(path).exists():
            counts.skipped_missing_file += 1
            continue
        video_id = path_to_vid.get(path)
        if video_id is None:
            counts.skipped_no_purl += 1
            continue
        added_at = dates.get(video_id)
        if added_at is None:
            counts.skipped_no_discovery_date += 1
            continue
        traktor_date = _iso_to_traktor_date(added_at)
        if traktor_date is None:
            counts.skipped_bad_date += 1
            continue
        if _update_import_date(entry, traktor_date):
            counts.updated += 1
        else:
            counts.unchanged += 1

    tmp = nml_path.with_suffix(nml_path.suffix + ".tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    try:
        ET.parse(tmp)
    except ET.ParseError as e:
        tmp.unlink(missing_ok=True)
        console.print(f"[red]ABORT: produced invalid XML — {e}[/]")
        return 1
    os.replace(tmp, nml_path)

    console.print(counts.render())
    return 0


def _loc_to_path(loc: ET.Element) -> str | None:
    vol = loc.attrib.get("VOLUME", "")
    dir_ = loc.attrib.get("DIR", "").replace("/:", "/")
    file_ = loc.attrib.get("FILE", "")
    if not dir_ or not file_:
        return None
    return dir_ + file_ if vol == "Macintosh HD" else f"/Volumes/{vol}{dir_}{file_}"


def _build_path_to_video_id_index(
    synced_root: Path, purl_index: PurlIndex | None = None
) -> dict[str, str]:
    """Walk synced_root, build {path: video_id}.

    When a PurlIndex is supplied, cache hits skip the ffprobe subprocess. New
    paths get ffprobe'd and written into the cache, so subsequent syncs are
    near-instant for unchanged libraries.
    """
    index: dict[str, str] = {}
    for mp3 in synced_root.rglob("*.mp3"):
        path_s = str(mp3)
        if purl_index is not None:
            cached = purl_index.get(path_s)
            if cached:
                index[path_s] = cached
                continue
        video_id = _purl_to_video_id(mp3)
        if video_id:
            index[path_s] = video_id
            if purl_index is not None:
                purl_index.set(path_s, video_id)
    return index


def _purl_to_video_id(mp3: Path) -> str | None:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=purl",
         "-of", "default=nokey=1:noprint_wrappers=1", str(mp3)],
        capture_output=True, text=True
    )
    url = (res.stdout or "").strip()
    if not url:
        return None
    # purl is "https://www.youtube.com/watch?v=<id>"
    if "v=" not in url:
        return None
    return url.split("v=", 1)[-1].split("&", 1)[0] or None


def _iso_to_traktor_date(iso: str) -> str | None:
    """ISO-8601 → Traktor's 'YYYY/MM/DD' (zero-padded).

    Padding matters: Traktor sorts IMPORT_DATE lexicographically as strings,
    NOT as dates. Without padding, "2024/9/1" sorts ABOVE "2024/11/20"
    because '9' > '1' under char comparison. Zero padding restores monotonic
    ordering across the whole column.
    """
    # ISO is always at least "YYYY-MM-DD" prefix.
    parts = iso[:10].split("-")
    if len(parts) != 3:
        return None
    y, m, d = parts
    if not (y.isdigit() and m.isdigit() and d.isdigit()):
        return None
    return f"{int(y):04d}/{int(m):02d}/{int(d):02d}"


def _update_import_date(entry: ET.Element, traktor_date: str) -> bool:
    """Set IMPORT_DATE on the entry's INFO child. Returns True if changed."""
    info = entry.find("INFO")
    if info is None:
        info = ET.SubElement(entry, "INFO")
    if info.attrib.get("IMPORT_DATE") == traktor_date:
        return False
    info.attrib["IMPORT_DATE"] = traktor_date
    return True


class _Counts:
    __slots__ = (
        "updated", "unchanged",
        "skipped_no_location", "skipped_missing_file", "skipped_no_purl",
        "skipped_no_discovery_date", "skipped_bad_date",
    )

    def __init__(self):
        self.updated = 0
        self.unchanged = 0
        self.skipped_no_location = 0
        self.skipped_missing_file = 0
        self.skipped_no_purl = 0
        self.skipped_no_discovery_date = 0
        self.skipped_bad_date = 0

    def render(self) -> str:
        return (
            f"[green]Updated:[/]               {self.updated}\n"
            f"[dim]Unchanged:[/]             {self.unchanged}\n"
            f"[dim]Skipped — no LOCATION:[/]  {self.skipped_no_location}\n"
            f"[dim]Skipped — file gone:[/]    {self.skipped_missing_file}\n"
            f"[dim]Skipped — no purl tag:[/]  {self.skipped_no_purl}\n"
            f"[dim]Skipped — no discovery:[/] {self.skipped_no_discovery_date}\n"
            f"[dim]Skipped — bad date:[/]     {self.skipped_bad_date}\n"
        )
