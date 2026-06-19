"""Spotify discovery: pick out [DJ]-tagged playlists, build track lists."""

from __future__ import annotations

import html

from .. import config
from ..archive import sanitize_name
from ..tracks import SpotifyTrackMeta, UnresolvedTrack
from . import DiscoveredPlaylist
from .spotify_client import make_client, page_my_playlists, page_playlist_items


class SpotifySource:
    def __init__(self, tag: str):
        self._tag_regex = config.spotify_tag_regex(tag)

    def discover(self) -> list[DiscoveredPlaylist]:
        client = make_client()
        result: list[DiscoveredPlaylist] = []

        for pl in page_my_playlists(client):
            if not self._matches_tag(pl.get("description")):
                continue
            name = pl.get("name") or "(untitled)"
            pl_id = pl.get("id") or ""
            tracks = list(self._fetch_tracks(client, pl_id))
            if not tracks:
                continue
            result.append(
                DiscoveredPlaylist(
                    folder_name=sanitize_name(name),
                    archive_id=f"spotify:{pl_id}",
                    source_label=f"spotify:{name}",
                    tracks=tracks,
                )
            )
        return result

    def _matches_tag(self, description) -> bool:
        if not description:
            return False
        # Spotify round-trips HTML entities (&#x2F;, &amp;…). Decode first.
        decoded = html.unescape(description)
        return bool(self._tag_regex.search(decoded))

    def _fetch_tracks(self, client, playlist_id: str):
        for item in page_playlist_items(client, playlist_id):
            # Spotify's playlist-items response uses `item` (unified type), with
            # legacy `track` populated for older clients. Read either.
            track = item.get("track") or item.get("item") or {}
            tid = track.get("id")
            if not tid:
                continue  # local file, podcast, or unavailable
            artists = [a.get("name", "") for a in (track.get("artists") or [])]
            artist_str = ", ".join(a for a in artists if a)
            album = (track.get("album") or {}).get("name") or ""
            release_date = (track.get("album") or {}).get("release_date")
            isrc = (track.get("external_ids") or {}).get("isrc")
            duration = int(track.get("duration_ms") or 0)
            meta = SpotifyTrackMeta(
                spotify_id=tid,
                title=track.get("name") or "",
                artist=artist_str,
                album=album,
                duration_ms=duration,
                explicit=bool(track.get("explicit")),
                isrc=isrc,
                release_date=release_date,
            )
            yield UnresolvedTrack(spotify=meta)
