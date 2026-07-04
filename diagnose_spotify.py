"""One-off diagnostic: list every Spotify playlist the auth account can see,
with its raw description + our tag-match verdict.

Run via:  uv run python diagnose_spotify.py
"""

import html
import sys

from yt_playlists import config
from yt_playlists.sources.spotify_client import make_client, page_my_playlists


def main() -> int:
    try:
        client = make_client()
    except Exception as e:
        print(f"auth failed: {e}")
        return 1

    me = client.current_user()
    print(f"Authed as: {me.get('id')} ({me.get('display_name')!r})")
    print()

    regex = config.spotify_tag_regex(config.DEFAULT_SPOTIFY_TAG)
    print(f"Tag regex: {regex.pattern!r}")
    print()
    print(f"{'TAG?':<6} {'OWNER':<22} {'NAME':<30}  DESCRIPTION (repr)")
    print("-" * 110)

    count = 0
    matched = 0
    for pl in page_my_playlists(client):
        count += 1
        name = pl.get("name") or "(untitled)"
        owner_id = (pl.get("owner") or {}).get("id") or "?"
        description = pl.get("description")
        decoded = html.unescape(description) if description else ""
        is_match = bool(regex.search(decoded)) if decoded else False
        if is_match:
            matched += 1
        flag = "MATCH" if is_match else "—"
        print(
            f"{flag:<6} {owner_id[:21]:<22} {name[:29]:<30}  {description!r}"
        )

    print()
    print(f"Total playlists visible: {count}")
    print(f"Matched the tag:         {matched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
