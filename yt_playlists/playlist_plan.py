"""Group discovered playlists into `PlannedFolder`s.

Merges multiple discovered playlists with the same sanitized folder name.
When that happens, the merge is explicit — a `merge_note` is set so the
dashboard / summary can show what got combined.

Dedup video IDs across merged playlists. When the same video appears in
both a Spotify (resolved) and a YouTube source path, Spotify metadata wins
(per the user's design call #4).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace

from .sources import DiscoveredPlaylist
from .tracks import PlannedFolder, ResolvedTrack, Unmatched


def plan(
    spotify_resolved: list[tuple[DiscoveredPlaylist, list[ResolvedTrack], list[Unmatched]]],
    youtube_discovered: list[DiscoveredPlaylist],
) -> list[PlannedFolder]:
    """Build per-folder plans.

    spotify_resolved: each Spotify DiscoveredPlaylist with its resolved/unmatched
                      tracks already computed.
    youtube_discovered: YouTube DiscoveredPlaylists; each track is already a
                       ResolvedTrack equivalent (direct video id).
    """
    folders: OrderedDict[str, PlannedFolder] = OrderedDict()

    for dpl, resolved, unmatched in spotify_resolved:
        _absorb(
            folders,
            folder_name=dpl.folder_name,
            archive_id=dpl.archive_id,
            source_label=dpl.source_label,
            resolved=resolved,
            unmatched=unmatched,
        )

    for dpl in youtube_discovered:
        # Convert YouTube UnresolvedTracks to ResolvedTracks (no Spotify meta).
        resolved = [
            ResolvedTrack(
                youtube_video_id=t.youtube_video_id,
                spotify=None,
                match_reason="youtube-direct",
            )
            for t in dpl.tracks
            if t.youtube_video_id
        ]
        _absorb(
            folders,
            folder_name=dpl.folder_name,
            archive_id=dpl.archive_id,
            source_label=dpl.source_label,
            resolved=resolved,
            unmatched=[],
        )

    return list(folders.values())


def _absorb(
    folders: OrderedDict[str, PlannedFolder],
    *,
    folder_name: str,
    archive_id: str,
    source_label: str,
    resolved: list[ResolvedTrack],
    unmatched: list[Unmatched],
) -> None:
    existing = folders.get(folder_name)
    if existing is None:
        folders[folder_name] = PlannedFolder(
            folder_name=folder_name,
            archive_id=archive_id,
            resolved=list(resolved),
            unmatched=list(unmatched),
            merge_note=None,
        )
        return

    # Merge — log it.
    new_resolved = _dedup_merge(existing.resolved, resolved)
    existing.resolved = new_resolved
    existing.unmatched.extend(unmatched)
    existing.merge_note = (
        (existing.merge_note + " + " if existing.merge_note else "")
        + source_label
    )


def _dedup_merge(
    existing: list[ResolvedTrack], incoming: list[ResolvedTrack]
) -> list[ResolvedTrack]:
    """Dedup by video_id. Spotify-meta entries win over no-meta on conflict."""
    by_id: OrderedDict[str, ResolvedTrack] = OrderedDict(
        (r.youtube_video_id, r) for r in existing
    )
    for r in incoming:
        prev = by_id.get(r.youtube_video_id)
        if prev is None:
            by_id[r.youtube_video_id] = r
            continue
        # Conflict: Spotify wins on metadata.
        if prev.spotify is None and r.spotify is not None:
            by_id[r.youtube_video_id] = replace(prev, spotify=r.spotify)
    return list(by_id.values())
