from __future__ import annotations

from pathlib import Path

from rich.console import Console

from .archive import count_archived


def clean_orphans(
    console: Console, archives_dir: Path, output_root: Path
) -> int:
    """Empty archive files whose corresponding output folder is missing/empty."""
    console.print("Cleaning orphaned archive entries...\n")
    total_cleaned = 0

    if not archives_dir.is_dir():
        console.print("No archives directory; nothing to clean.")
        return 0

    for archive in sorted(archives_dir.glob("*.txt")):
        playlist_name = archive.stem
        playlist_dir = output_root / playlist_name
        mp3s_present = playlist_dir.is_dir() and any(playlist_dir.glob("*.mp3"))

        if mp3s_present:
            continue

        count = count_archived(archive)
        if count == 0:
            continue

        console.print(
            f"  Clearing {count} entries from [bold]{playlist_name}[/] archive "
            f"(folder missing/empty)"
        )
        archive.write_text("", encoding="utf-8")
        total_cleaned += count

    console.print(f"\nCleaned [bold]{total_cleaned}[/] orphaned archive entries")
    return total_cleaned
