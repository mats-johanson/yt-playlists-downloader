# YouTube Playlists Downloader

Downloads YouTube playlists as MP3 with a Homebrew-style live multi-bar dashboard. Parallel downloads, per-playlist archive tracking, no re-downloads.

## Requirements

- Python 3.11+
- `ffmpeg` (audio conversion)
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `python3 -m venv` fallback

Install on macOS:
```bash
brew install ffmpeg uv
```

`yt-dlp` and `rich` are installed automatically into a local virtual environment on first run.

## Setup

1. Clone the repository.
2. Create `config/playlists.txt` with your playlist URLs (one per line):
   ```
   https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxx
   https://www.youtube.com/playlist?list=PLyyyyyyyyyyyy
   ```

## Usage

```bash
./download_playlists.sh
```

MP3 files are saved to `../Youtube Downloads/[Playlist Name]/`.

### Flags

```
./download_playlists.sh [--clean-orphans] [--no-dashboard] [--debug]
                        [--parallel N] [playlists_file]
```

- `--clean-orphans` — empty archive files whose output folder is missing/empty.
- `--no-dashboard` — single-line live summary instead of the multi-bar view.
- `--debug` — verbose yt-dlp output to `logs/debug.log`.
- `--parallel N` — number of concurrent downloads (default 10).
- `playlists_file` — alternative URL file (default `config/playlists.txt`).

The dashboard auto-disables when stdout isn't a terminal (CI, log files); in that mode it prints one line per completed song.

## Testing

```bash
./test.sh
```

Downloads a small set of test playlists into `./test_downloads/` so changes can be validated without touching the main library.

## Files Created

- `logs/archives/<Playlist Name>.txt` — per-playlist download history; same song can appear in multiple playlists.
- `logs/unavailable-videos.txt` — videos that failed in the current run (private, removed, region-blocked).
- `logs/debug.log` — yt-dlp warnings/errors and `--debug` verbose output.

## Layout

```
yt-playlists-downloader/
├── download_playlists.sh    # thin launcher: uv sync + uv run -m yt_playlists
├── pyproject.toml           # Python package metadata (yt-dlp, rich)
├── yt_playlists/            # all logic
│   ├── __main__.py          # CLI + orchestration
│   ├── config.py            # paths, constants
│   ├── scanner.py           # parallel playlist scan
│   ├── downloader.py        # parallel download + yt-dlp progress hooks
│   ├── dashboard.py         # multi-bar / summary / plain renderers
│   ├── archive.py           # archive read / diff
│   ├── unavailable.py       # tracker for failed videos
│   ├── summary.py           # final report
│   ├── orphan_cleaner.py    # --clean-orphans subcommand
│   ├── updater.py           # auto-update yt-dlp at startup
│   └── ydl_logger.py        # custom yt-dlp logger → debug.log + error sink
├── config/
│   └── playlists.txt        # user playlist URLs (gitignored)
├── logs/
│   ├── archives/            # per-playlist archives
│   ├── debug.log
│   └── unavailable-videos.txt
└── test.sh                  # smoke test runner
```

## Features

- Brew-style multi-progress dashboard with byte-level fill per current song.
- Parallel downloads (10 concurrent by default).
- Per-playlist archive tracking — a song can live in multiple playlists.
- MP3 metadata preserved via yt-dlp's `FFmpegExtractAudio` postprocessor.
- Scroll-above-dashboard log of completed songs.
- Auto-update of yt-dlp at startup.
- Orphaned archive detection and cleaning.
