# yt-playlists-downloader

Spotify-first music library downloader. Tag your Spotify playlists with `[DJ]` in their description, run one command, get tagged MP3s organized into mood folders. Optional YouTube playlist URLs for tracks not on Spotify.

Files land in `../Synced Music/<Playlist Name>/Artist - Title.mp3` with proper ID3 tags (Spotify-canonical artist/title/album/date) + embedded cover art.

## Quick start

```bash
# One-time setup
brew install ffmpeg deno uv
cp config/playlists.toml.example config/playlists.toml
# Register a Spotify app at developer.spotify.com (see Setup section), then:
cp .env.example .env  # and paste your Client ID

# Daily use
./download_playlists.sh
```

## What it does

1. **DISCOVER** — reads your Spotify playlists, keeps those with `[DJ]` in the description; also reads YT playlists from `config/playlists.toml`.
2. **RESOLVE** — for each Spotify track, searches YouTube and scores 5 candidates (artist, title, duration, forbidden-word penalty). Caches every resolution.
3. **PLAN** — groups results by folder name, dedups across sources.
4. **DOWNLOAD** — parallel yt-dlp, MP3 V0, embeds Spotify metadata + thumbnail.
5. **SUMMARY** — per-folder counts, unmatched list ready to paste into the overrides file.

## Setup

### Requirements

- macOS (other Unix probably works, untested)
- Python 3.11+
- `ffmpeg` (audio conversion + thumbnail embedding)
- `deno` (JS challenge solver for YouTube extraction — without it, the player_client set collapses and bot-check triggers more often)
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `python3 -m venv` fallback

`yt-dlp`, `rich`, and `spotipy` are installed automatically into a local virtual environment on first run.

### Spotify Developer App

1. Go to <https://developer.spotify.com/dashboard>.
2. Create app with:
   - **Redirect URI:** `http://127.0.0.1:8765/callback`
   - **Scopes:** `playlist-read-private`
3. Copy the **Client ID** (not the secret — PKCE doesn't use it).
4. Paste into `.env`:
   ```
   SPOTIFY_CLIENT_ID="your-client-id"
   ```
   (Already gitignored.)
5. First run opens a browser for PKCE consent. Refresh token cached at `~/.config/yt-playlists/spotify-token.json` (chmod 600). Refresh is automatic for months.

> As of Feb 2026, Spotify Dev Mode apps require the **app owner** to have a Premium subscription. Single-user personal use is the documented intended case.

### Config

`config/playlists.toml`:

```toml
[sources.spotify]
# Case-insensitive, word-bounded match in playlist description.
tag = "[DJ]"

[sources.youtube]
# Extras for YT-only playlists (no Spotify equivalent).
# Playlist title becomes folder name (sanitized).
playlists = [
    # "https://www.youtube.com/playlist?list=PL...",
]
```

`config/spotify_overrides.toml` (only if the matcher picks the wrong video for a track):

```toml
# Format:  <spotify_track_id> = "<youtube_video_id>"
"3n3Ppam7vgaVa1iaRUc9Lp" = "dQw4w9WgXcQ"
```

## Flags

```
./download_playlists.sh [--no-dashboard] [--debug] [--logout] [--clean-orphans]
```

- `--no-dashboard` — single-line live summary instead of the multi-bar dashboard
- `--debug` — verbose yt-dlp output to `logs/debug.log`
- `--logout` — delete the cached Spotify token + exit (forces re-auth on next run)
- `--clean-orphans` — empty archive files whose output folder is missing/empty

`OUTPUT_ROOT` env var overrides the default `../Synced Music/` destination.

## Where things live

| File / Dir | Purpose |
|---|---|
| `.env` | Your `SPOTIFY_CLIENT_ID` (gitignored) |
| `config/playlists.toml` | Source declarations (gitignored — yours) |
| `config/spotify_overrides.toml` | Manual track-ID overrides (gitignored — yours) |
| `~/.config/yt-playlists/spotify-token.json` | OAuth refresh token (chmod 600) |
| `logs/match_cache.json` | Resolved Spotify track snapshots `{track_id: {video_id, title, artist, …}}` |
| `logs/resolutions.log` | One structured line per Spotify track per run: `track_id\|status\|video_id\|score\|reason` |
| `logs/unmatched.txt` | Tracks below match threshold; paste lines into `spotify_overrides.toml` to fix |
| `logs/archives/<folder>__<playlist_id>.txt` | yt-dlp download archive, keyed by stable playlist ID so renames don't orphan |
| `logs/debug.log` | yt-dlp warnings/errors |

## Project layout

```
yt-playlists-downloader/
├── download_playlists.sh         # launcher
├── pyproject.toml                # deps: yt-dlp, rich, spotipy
├── .env, .env.example            # SPOTIFY_CLIENT_ID
├── config/
│   ├── playlists.toml(.example)
│   └── spotify_overrides.toml(.example)
├── logs/                         # caches + run logs
└── yt_playlists/                 # the package
    ├── __main__.py               # CLI entry + phase orchestration
    ├── config.py                 # all thresholds, ports, tag regex
    ├── pipeline.py               # Pipeline class
    ├── playlist_plan.py          # PlannedFolder + dedup logic
    ├── matcher.py                # pure score() + resolve() I/O wrapper
    ├── yt_search.py              # ytsearch5: wrapper
    ├── match_cache.py            # JSON cache, schema-versioned, atomic
    ├── overrides.py              # spotify_overrides.toml reader
    ├── archive.py                # per-folder download archive
    ├── tracks.py                 # SpotifyTrackMeta, UnresolvedTrack, ResolvedTrack, Unmatched, PlannedFolder
    ├── outcomes.py               # OutcomeReason, PlaylistOutcome
    ├── unavailable.py            # global bot-block circuit-breaker + unavailable.txt
    ├── ydl_logger.py             # custom yt-dlp logger
    ├── downloader.py             # provider-agnostic; eats PlannedFolder
    ├── dashboard.py              # rich Progress — Bar / Summary / Plain
    ├── summary.py                # final report
    ├── orphan_cleaner.py         # --clean-orphans
    ├── sources/                  # Source protocol + implementations
    │   ├── spotify_client.py     # spotipy HTTP wrapper
    │   ├── spotify_discover.py   # [DJ] tag filter, track extraction
    │   └── youtube.py            # yt-dlp extract_flat
    ├── auth/
    │   └── spotify_pkce.py       # PKCE flow + port + chmod 600
    └── postprocessors/
        └── spotify_metadata.py   # injects Spotify metadata into ID3 via custom yt-dlp PP
```

## Troubleshooting

- **"No Spotify playlists matched tag [DJ]"** — verify the literal `[DJ]` appears in the playlist's description (word-bounded; spaces around it OK; embedded in another word, no). Spotify caches description edits for ~30s; if you just edited, wait and retry.
- **"Port 8765 in use"** — quit the program holding it, or set `SPOTIFY_REDIRECT_PORT=8766` in `.env` AND update the dev-app redirect URI in Spotify dashboard.
- **Token expired / refused** — `./download_playlists.sh --logout` clears the token; next run prompts re-auth.
- **Match looks wrong for a track** — open `logs/unmatched.txt` or grep `logs/resolutions.log` for the track id, paste the corrected video id into `config/spotify_overrides.toml`.
- **JS challenge / 403 errors** — `remote_components: ["ejs:github"]` is enabled in the downloader; deno fetches and runs the EJS solver. Make sure `deno` is on `PATH`.
- **Tests** — `uv run --extra dev pytest`. 35 pure-function tests cover matcher scoring, cache schema, overrides, dashboard mode selection.

## Diagnostics

Two utility scripts you can use when something looks off:

```bash
uv run python diagnose_spotify.py     # list every Spotify playlist + raw description + tag-match verdict
uv run python diagnose_resolve.py     # full discover + resolve + plan, no downloads — see how the matcher scores against your real data
```
