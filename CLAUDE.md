# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube playlist → MP3 downloader with a Homebrew-style live multi-bar dashboard. Parallel downloads (default 10), per-playlist archive tracking. `download_playlists.sh` is a thin launcher; all logic lives in the `yt_playlists` Python package.

## Essential Commands

### Setup and Run
```bash
# Install runtime requirements (macOS)
brew install ffmpeg uv

# Run the downloader (yt-dlp + rich are installed automatically into .venv)
./download_playlists.sh
```

### Development Commands
```bash
# Single-playlist smoke test
echo "https://youtube.com/playlist?list=EXAMPLE" > /tmp/p.txt
./download_playlists.sh /tmp/p.txt

# Run the bundled smoke test (downloads 3 small test playlists into ./test_downloads/)
./test.sh

# Direct invocation (bypasses launcher)
uv run python -m yt_playlists [--debug] [--no-dashboard] [playlists_file]

# Check logs
tail -f logs/debug.log
cat logs/unavailable-videos.txt
```

## Architecture

### Execution phases (orchestrated in `yt_playlists/__main__.py`)
1. **Update** — `updater.py`: `pip install --upgrade yt-dlp` in-venv, brew fallback.
2. **Scan** — `scanner.py`: parallel `extract_flat=True` per playlist, diffs IDs against the archive.
3. **Download** — `downloader.py`: `ThreadPoolExecutor` of N playlists; each `YoutubeDL.download()` runs with a `progress_hooks` callback feeding the live dashboard.
4. **Summary** — `summary.py`: per-playlist outcome grid, archive total, unavailable-video report.

### Module map
- `__main__.py` — CLI parsing, phase orchestration, dashboard mode selection
- `config.py` — paths (`OUTPUT_ROOT`, `ARCHIVES_DIR`, …), `PARALLEL_JOBS`
- `scanner.py` — `ScanResult`, parallel scan
- `downloader.py` — `Downloader`, `_PerPlaylistContext` (hook state), `PlaylistOutcome`
- `dashboard.py` — `Dashboard` ABC + three impls: `BarDashboard` (rich Progress, brew-style), `SummaryDashboard` (single live line), `PlainDashboard` (no TTY, one stdout line per event)
- `archive.py` — `sanitize_name`, archive read/diff/count
- `unavailable.py` — `UnavailableTracker` (thread-safe collector of failed videos + bot-block detection)
- `summary.py` — final report rendering
- `orphan_cleaner.py` — `--clean-orphans` subcommand
- `updater.py` — startup yt-dlp update (pip → brew fallback)
- `ydl_logger.py` — custom yt-dlp `logger` funneling output to `debug.log` and an error sink

### Dashboard contract
`Dashboard` is a context manager. `add_playlist(name, total_new)` returns a `PlaylistTaskHandle` with three methods:
- `update_song(title, pct)` — called per yt-dlp `progress_hooks` 'downloading' event
- `song_completed(song_title, songs_done)` — called per 'finished' event (deduped by video id; yt-dlp 2026 fires PP hooks twice)
- `playlist_completed(songs_done, failed=False)` — called when the playlist's `ydl.download()` returns

Mode selection in `__main__._pick_dashboard_mode`:
- not a TTY → `plain`
- `--no-dashboard` → `summary`
- default → `bars`

### Key design decisions
1. **Pure-Python pipeline**: uses `yt_dlp` as a library (`YoutubeDL` class), not subprocess. Progress arrives as structured dicts from `progress_hooks`, no stdout regex parsing.
2. **Temporary download dir**: each playlist downloads into `tempfile.mkdtemp(prefix="ytdl-")`, mp3s are moved to `OUTPUT_ROOT/<playlist>/` only after `ydl.download()` returns. Prevents partial files in the library.
3. **Per-playlist archive**: `logs/archives/<safe_name>.txt` — same song can live in multiple playlists, each tracked independently.
4. **Hook dedup by video id**: yt-dlp 2026.x fires postprocessor hooks twice; we count songs via `progress_hooks` 'finished' and keep a `set` of seen ids in `_PerPlaylistContext`.
5. **Thread-based parallelism**: yt-dlp is I/O-bound, so `ThreadPoolExecutor` is sufficient and avoids pickling state for processes.
6. **Console highlight disabled**: `Console(highlight=False)` in `__main__` — otherwise rich auto-colors numbers in playlist names ("Top **100** Daily").

### Configuration
- `OUTPUT_ROOT` env var overrides destination (default: `<repo parent>/Youtube Downloads`).
- `--parallel N` overrides `PARALLEL_JOBS` (default 10).
- `--debug` enables verbose yt-dlp logging to `logs/debug.log`.

### Directory layout
```
yt-playlists-downloader/
├── download_playlists.sh   # launcher: uv sync && uv run -m yt_playlists
├── pyproject.toml          # deps: yt-dlp, rich
├── yt_playlists/           # package (see module map above)
├── config/playlists.txt    # user URLs (gitignored)
├── logs/
│   ├── archives/<Playlist>.txt
│   ├── debug.log
│   └── unavailable-videos.txt
├── test.sh                 # smoke runner
└── test_downloads/         # smoke test output (gitignored)
```

## Common Development Tasks

### Adding a new dashboard mode
1. Subclass `Dashboard` in `dashboard.py`, implement `start/stop/add_playlist`.
2. Implement a corresponding handle class with `update_song`, `song_completed`, `playlist_completed`.
3. Add the mode string to `make_dashboard()` and to `__main__._pick_dashboard_mode`.

### Modifying download behavior
yt-dlp options are built in `downloader._build_ydl_opts`. The format string for output paths is `outtmpl`. The `FFmpegExtractAudio` postprocessor handles MP3 conversion (quality 0 = best).

### Testing changes
```bash
./test.sh                              # full smoke test
uv run python -m yt_playlists --help   # CLI help
uv run python -c "from yt_playlists import dashboard"  # import smoke
```

`test.sh` clears the test playlist archives and downloads into `./test_downloads/` — safe to run without affecting the real library.

### Debugging
- `--debug` writes verbose yt-dlp output to `logs/debug.log` (truncated each run).
- `--no-dashboard` switches to a single-line live summary — useful when the multi-bar view is making it hard to read errors.
- `--parallel 1` serializes downloads for easier inspection.

### Linting
No mandatory linter, but `ruff check yt_playlists/` is a reasonable starting point if added later. The bash launcher is intentionally trivial — no shellcheck enforcement is needed.

## Output Format
- Files: `<OUTPUT_ROOT>/<Playlist Name>/Artist - Song Title.mp3`
- Title max 100 chars (yt-dlp `%(title).100s`)
- Audio quality 0 (best available)
- MP3 metadata preserved by yt-dlp's `FFmpegExtractAudio` postprocessor
