"""Spotify PKCE OAuth flow.

PKCE means: no client secret. We open the browser to consent, get an auth
code on a localhost callback, exchange for tokens. Refresh token persists
at `~/.config/yt-playlists/spotify-token.json` (chmod 600).

Fails fast with actionable messages for:
- missing client_id
- callback port in use
- token file unreadable
"""

from __future__ import annotations

import os
import socket
import sys

from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

from .. import config


class AuthError(Exception):
    """Actionable auth setup failure."""


def _check_port_free(host: str, port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
    except OSError as e:
        raise AuthError(
            f"Spotify OAuth callback port {port} is in use ({e}). "
            f"Either quit the program holding it or set "
            f"SPOTIFY_REDIRECT_PORT to a different value and update the redirect "
            f"URI in your Spotify dev-app dashboard to match."
        ) from None
    finally:
        s.close()


def get_auth_manager() -> SpotifyPKCE:
    """Construct the PKCE auth manager. Caller passes this to spotipy.Spotify(auth_manager=…)."""
    client_id = os.environ.get(config.SPOTIFY_CLIENT_ID_ENV)
    if not client_id:
        raise AuthError(
            f"Environment variable {config.SPOTIFY_CLIENT_ID_ENV} is not set.\n"
            f"Create a Spotify dev app at https://developer.spotify.com/dashboard\n"
            f"  - Redirect URI: {config.SPOTIFY_REDIRECT_URI}\n"
            f"  - Required scope: {config.SPOTIFY_SCOPES}\n"
            f"Then: export {config.SPOTIFY_CLIENT_ID_ENV}=<your-client-id>"
        )

    config.USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cache_handler = CacheFileHandler(cache_path=str(config.SPOTIFY_TOKEN_FILE))

    # Only check port if no cached token yet — otherwise the bind would block
    # subsequent runs unnecessarily.
    if not config.SPOTIFY_TOKEN_FILE.exists():
        _check_port_free("127.0.0.1", config.SPOTIFY_REDIRECT_PORT)

    return SpotifyPKCE(
        client_id=client_id,
        redirect_uri=config.SPOTIFY_REDIRECT_URI,
        scope=config.SPOTIFY_SCOPES,
        cache_handler=cache_handler,
        open_browser=True,
    )


def post_token_chmod() -> None:
    """After spotipy writes the token, tighten its perms to 600."""
    p = config.SPOTIFY_TOKEN_FILE
    if p.exists():
        try:
            os.chmod(p, 0o600)
        except OSError:
            print(f"warning: could not chmod 600 {p}", file=sys.stderr)


def logout() -> bool:
    """Delete the cached token. Returns True if a token was actually removed."""
    p = config.SPOTIFY_TOKEN_FILE
    if p.exists():
        p.unlink()
        return True
    return False
