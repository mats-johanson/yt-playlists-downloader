# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Spotify-first music library downloader with a Homebrew-style live multi-bar dashboard. The user curates playlists in Spotify, tags them `[DJ]` in the description. The tool reads those playlists via the Spotify Web API, matches each track to a YouTube video, downloads MP3 V0 with full ID3 tags + embedded cover art, and lands them in mood-named folders.

YouTube is the audio backend (no Spotify decryption; the user explicitly ruled out account-ban-risk paths like librespot). The matcher is in-house, ported from spotDL's signal set (artist coverage, exponential duration decay, forbidden-words penalty for live/cover/karaoke/remix).

`download_playlists.sh` is a thin launcher; all logic lives in the `yt_playlists` package.

## Essential commands

### Setup and run

```bash
# Install runtime requirements (macOS)
brew install ffmpeg deno uv
# deno is REQUIRED: yt-dlp uses it to solve YouTube JS challenges. Without it the
# player_client set collapses to android_vr and 403 / "Sign in to confirm" errors
# become much more common.

# One-time auth setup (see README §Setup)
cp config/playlists.toml.example config/playlists.toml
cp .env.example .env  # paste your SPOTIFY_CLIENT_ID

# Run
./download_playlists.sh
```

### Development

```bash
# Unit tests (35 pure-function cases)
uv run --extra dev pytest

# Linter
uv run --extra dev ruff check yt_playlists/ tests/

# Direct invocation (bypasses launcher's .env sourcing — set env var first)
SPOTIFY_CLIENT_ID="..." uv run python -m yt_playlists [--debug] [--no-dashboard]

# CLI help
uv run python -m yt_playlists --help

# Diagnostic: list every Spotify playlist + tag-match verdict
uv run python diagnose_spotify.py

# Diagnostic: run discover + resolve + plan, no downloads (validates match quality)
uv run python diagnose_resolve.py

# Force re-auth with Spotify
./download_playlists.sh --logout
```

## Architecture

### Phases (orchestrated in `yt_playlists/pipeline.py::Pipeline`)

1. **DISCOVER** — `sources/spotify_discover.py` walks `GET /me/playlists`, filters by `[DJ]` tag in description; `sources/youtube.py` extracts each URL in `playlists.toml[sources.youtube]`. Both yield `DiscoveredPlaylist` records.
2. **RESOLVE** (Spotify only) — for each `SpotifyTrackMeta`: check `overrides.toml` → check `match_cache.json` → else `ytsearch5:` + score → pick winner OR log to `unmatched.txt`. Threading via `ThreadPoolExecutor(RESOLVE_PARALLEL=8)`. Resolutions cached.
3. **PLAN** — `playlist_plan.plan()` groups results by sanitized folder name. Same-folder collisions (Spotify + YouTube target the same name) merge with an explicit `merge_note`. Dedup by `video_id`; Spotify-meta wins on conflicts.
4. **DOWNLOAD** — `downloader.Downloader` builds yt-dlp opts per playlist, including a `SpotifyMetadataPP` that mutates `info_dict` at `pre_process` time so Spotify-canonical artist/title/album/date flows through `FFmpegMetadata` into the final ID3 tags.
5. **SUMMARY** — `summary.render_final_summary()` shows per-folder source breakdown, unmatched tracks (paste-ready for overrides), bot-block detection.

### Module map

- `__main__.py` — CLI args, phase orchestration
- `config.py` — paths, thresholds, ports, tag regex (CENTRALIZED — no other module hardcodes these)
- `pipeline.py` — `Pipeline` class wraps the phase wiring
- `playlist_plan.py` — `PlannedFolder` dataclass + `plan()` dedup+merge logic
- `matcher.py` — pure `score(track, candidates)` + `resolve(track, search_fn)` I/O wrapper; spotDL-style signals
- `yt_search.py` — `ytsearch5:` wrapper via yt-dlp with `extract_flat="in_playlist"` for performance
- `match_cache.py` — JSON cache with `version` envelope + atomic incremental writes + full SpotifyTrackMeta snapshots
- `overrides.py` — `spotify_overrides.toml` reader, checked BEFORE cache + matcher
- `tracks.py` — `SpotifyTrackMeta`, `UnresolvedTrack`, `ResolvedTrack`, `Unmatched`, `PlannedFolder`
- `outcomes.py` — `OutcomeReason` (`DONE`/`EMPTY`/`BOT_BLOCKED`/`ERROR`), `PlaylistOutcome`
- `archive.py` — `sanitize_name` (Windows-safe), `archive_path(<folder>__<id>.txt)` keyed by stable playlist ID
- `unavailable.py` — `UnavailableTracker` (bot-block circuit-breaker + unavailable-videos log)
- `ydl_logger.py` — custom yt-dlp logger funneling to `debug.log` and the unavailable tracker
- `downloader.py` — PROVIDER-AGNOSTIC; eats `PlannedFolder` instances, builds per-video metadata override map for `SpotifyMetadataPP`
- `dashboard.py` — three `Dashboard` impls behind one Protocol: `BarDashboard` (rich Progress), `SummaryDashboard` (single live line), `PlainDashboard` (no TTY)
- `summary.py` — final report with per-folder source breakdown
- `orphan_cleaner.py` — `--clean-orphans` subcommand
- `config_loader.py` — TOML reader for `playlists.toml`
- `sources/` — `Source` Protocol + impls
  - `sources/spotify_client.py` — spotipy HTTP wrapper (paging, retry)
  - `sources/spotify_discover.py` — `[DJ]` tag filter + `SpotifyTrackMeta` extraction
  - `sources/youtube.py` — yt-dlp `extract_flat` for YT URLs in config
- `auth/spotify_pkce.py` — PKCE flow on `127.0.0.1:8765`, port fail-fast, token chmod 600
- `postprocessors/spotify_metadata.py` — custom yt-dlp PP run at `pre_process` so mutations reach FFmpegMetadata

### yt-dlp options (built in `downloader._build_ydl_opts`)

- `format: "bestaudio/best"`
- `postprocessors`: FFmpegExtractAudio (MP3 V0) → MetadataFromField (regex parse `Artist - Title` for YT-only tracks) → FFmpegMetadata → EmbedThumbnail
- `extractor_args: {youtube: {player_client: ["default", "web_embedded"]}}` — `web_embedded` doesn't need PO Token; fallback when bot-check fires
- `remote_components: ["ejs:github"]` — fetches the EJS JS-challenge solver, runs it through deno
- `concurrent_fragment_downloads: 2` — 10 parallel × 5 fragments = 50 streams was tripping YouTube's 429
- `ignoreerrors: "only_download"` — playlist-level errors propagate; per-video errors get logged + skipped
- `match_filter` — global bot-block circuit-breaker; first 403/sign-in halts every subsequent video this run

### Key design decisions

1. **Pure-Python pipeline**: uses `yt_dlp` as a library (`YoutubeDL` class), not subprocess. Progress arrives as structured dicts from `progress_hooks`. No stdout regex parsing.
2. **Audio comes from YouTube only**: Spotify provides metadata. Audio decryption (librespot etc.) is ToS-violating + account-ban risk.
3. **Matcher is in-house**: spotDL's matching logic ported (~150 lines) rather than depending on spotDL the package — Feb 2026 Spotify Dev Mode changes broke spotDL's shared Client ID model; per-user PKCE side-steps that fragility.
4. **`SpotifyMetadataPP` runs at `pre_process`**: critical — `post_process` would append it AFTER `FFmpegMetadata`, by which time tags are already written. Pre-process mutates `info_dict` so the downstream postprocessor chain sees Spotify-canonical values.
5. **Archive key includes playlist ID**: `<folder>__<id>.txt` survives source-side playlist renames.
6. **Cache is schema-versioned**: `{"version": 1, "entries": {...}}`. Mismatch on load = treat as missing, don't crash.
7. **Override file is the correction surface**: matcher will pick wrong on some tracks (live versions, covers, regional weirdness). User pastes a line from `unmatched.txt` into `spotify_overrides.toml`; future runs use the pin.
8. **Folder name = playlist title (sanitized)**: Spotify-derived and YouTube-derived names merge when they collide. Logged at scan time so the merge is explicit.

### Configuration

- `OUTPUT_ROOT` env var overrides destination (default: `<repo parent>/Synced Music`).
- `SPOTIFY_CLIENT_ID` env var (from `.env`) is required.
- `SPOTIFY_REDIRECT_PORT` env var overrides default 8765 (must also update Spotify dev-app redirect URI to match).
- All tunables (`MATCH_THRESHOLD`, `MATCH_ARTIST_MIN_SIMILARITY`, `MATCH_FORBIDDEN_TOKENS`, `RESOLVE_PARALLEL`, `DOWNLOAD_STAGGER_SECONDS`, etc.) centralized in `yt_playlists/config.py`.

## Common development tasks

### Tuning the matcher

Score thresholds and signal weights are in `config.py`. The matcher's pure-function design means you can run `diagnose_resolve.py`, see the score distribution + per-track decisions in `logs/resolutions.log`, tweak a constant, blow away `logs/match_cache.json` (only if changing scoring weights — threshold changes don't invalidate cached matches), and re-run for a fast iteration loop.

### Adding a new dashboard mode

1. Subclass `Dashboard` in `dashboard.py`, implement `start/stop/add_playlist`.
2. Implement a `PlaylistTaskHandle` with `update_song`, `song_completed`, `playlist_completed`.
3. Add mode string to `make_dashboard()` factory and `__main__._pick_dashboard_mode`.

### Modifying download behavior

yt-dlp options live in `downloader._build_ydl_opts`. Format string for paths is `outtmpl`. `FFmpegExtractAudio` does MP3 conversion (`preferredquality="0"` = LAME V0).

### Testing changes

```bash
uv run --extra dev pytest                 # full suite, < 1s
uv run --extra dev ruff check yt_playlists/ tests/
```

Tests are pure-function only — no live Spotify or YouTube. Matcher fixtures simulate ytsearch results so threshold/scoring changes can be regression-tested without network.

### Linting

`ruff` is configured in `pyproject.toml`. Auto-fixes most issues with `ruff check --fix`.

## Output format

- Files: `<OUTPUT_ROOT>/<Sanitized Playlist Name>/Artist - Song Title.mp3`
- Title max 100 chars (yt-dlp `%(title).100s`)
- Audio quality: 0 (LAME V0 VBR, ~245 kbps avg)
- ID3v2.3 tags (broad compatibility) from Spotify-canonical metadata when available, falling back to MetadataFromField regex for YouTube-only tracks
- Cover art: video thumbnail embedded as APIC frame
- Filename uses Spotify's `,` separator for multi-artist tracks (not YouTube's `+ `)

## What this project is NOT

- **Not a Spotify ripper** — we never download audio from Spotify. Only metadata.
- **Not a continuous sync service** — runs on demand, not as a daemon.
- **Not for non-personal use** — Spotify's Feb 2026 Dev Mode changes cap each dev app to 5 users; this is personal-account scope.

## Old workflow being replaced

Pre-v0.3 was a 4-step manual workflow: curate in Spotify → mirror to YT playlist → sync via Soundiiz → download YT playlist via `download_playlists.sh`. The matcher in v0.3 replaces Soundiiz; metadata via Spotify Web API replaces the YT playlist mirror; net result is one step (`./download_playlists.sh`).
