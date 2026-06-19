"""Thin Spotify HTTP wrapper.

Just paging and rate-limit-aware retry. No business logic. Discovery and
[DJ]-tag filtering live in `spotify_discover.py`.
"""

from __future__ import annotations

from collections.abc import Iterator

import spotipy

from ..auth.spotify_pkce import AuthError, get_auth_manager, post_token_chmod


def make_client() -> spotipy.Spotify:
    """Build an authenticated Spotify client. Triggers OAuth on first run."""
    auth = get_auth_manager()
    client = spotipy.Spotify(
        auth_manager=auth,
        requests_timeout=20,
        retries=3,
        status_retries=3,
        backoff_factor=1.5,
    )
    # Force a token-bearing call so PKCE consent happens here, not deep in the
    # discovery loop. Also gives us a clear error point.
    try:
        client.current_user()
    except spotipy.SpotifyException as e:
        if e.http_status == 403:
            raise AuthError(
                "Spotify returned 403. The dev-app owner needs a Premium "
                "subscription as of Feb 2026; verify your account."
            ) from None
        raise
    post_token_chmod()
    return client


def page_my_playlists(client: spotipy.Spotify) -> Iterator[dict]:
    """Yield every playlist the authed user has access to. Handles paging."""
    limit = 50
    offset = 0
    while True:
        page = client.current_user_playlists(limit=limit, offset=offset)
        items = page.get("items") or []
        for item in items:
            if item:
                yield item
        if not page.get("next"):
            return
        offset += limit


def page_playlist_items(client: spotipy.Spotify, playlist_id: str) -> Iterator[dict]:
    """Yield every track item in a playlist. Handles paging.

    NOTE: dropped the `fields=` filter — Spotify's playlist-items response
    nests track data under `item.item` (unified field) rather than the legacy
    `item.track`. Reductive fields filters that target `track(...)` come back
    empty. We fetch full items and let the caller pick fields.
    """
    limit = 100
    offset = 0
    while True:
        page = client.playlist_items(
            playlist_id,
            limit=limit,
            offset=offset,
            additional_types=("track",),
        )
        items = page.get("items") or []
        for item in items:
            if item:
                yield item
        if not page.get("next"):
            return
        offset += limit
