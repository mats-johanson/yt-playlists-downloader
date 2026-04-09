# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a YouTube playlist downloader that converts videos to MP3 format with proper metadata preservation. The main script (`download_playlists.sh`) downloads multiple playlists in parallel, storing music files in a separate directory structure.

## Essential Commands

### Setup and Run
```bash
# Install dependencies (macOS)
brew install yt-dlp ffmpeg

# Make script executable
chmod +x download_playlists.sh

# Run the downloader
./download_playlists.sh
```

### Development Commands
```bash
# Lint the script (ALWAYS run after changes)
shellcheck download_playlists.sh

# Test with a single playlist
echo "https://youtube.com/playlist?list=EXAMPLE" > test_playlist.txt
./download_playlists.sh test_playlist.txt

# Check download logs
ls -la logs/archives/  # View per-playlist archives
tail -f logs/unavailable-videos.txt
```

## Architecture Overview

### Core Components
1. **download_playlists.sh**: Main bash script that orchestrates parallel downloads
   - Auto-updates `yt-dlp` at startup
   - Pre-scans playlists to count new songs before downloading
   - Shows global progress counter (`12/47`) during downloads
   - Uses `yt-dlp` for downloading and `ffmpeg` for MP3 conversion
   - Implements parallel processing (default: 10 concurrent jobs)
   - Maintains download archive to prevent re-downloads

### Execution Phases
1. **Update** — auto-updates yt-dlp (with brew fallback)
2. **Scan** — pre-scans all playlists in parallel to get names and new song counts
3. **Download** — downloads new songs in parallel with progress tracking
4. **Summary** — compact two-column status grid with archive statistics

### Directory Structure
```
yt-playlists-downloader/
├── config/
│   ├── playlists.txt        # User's playlist URLs
│   └── playlists.example.txt # Example playlist file
├── logs/
│   ├── archives/              # Per-playlist download histories
│   │   └── [Playlist Name].txt
│   └── unavailable-videos.txt # Failed downloads from current run
├── download_playlists.sh     # Main script
├── README.md
└── CLAUDE.md

../Youtube Downloads/         # Music files (parent directory)
└── [Playlist Name]/
    └── Artist - Song Title.mp3
```

### Key Design Decisions
1. **Temporary Downloads**: Uses system temp directory during download to prevent partial files
2. **Archive System**: Each playlist has its own archive file in `logs/archives/[Playlist Name].txt` to track downloaded videos
3. **Error Tracking**: `logs/unavailable-videos.txt` logs failed downloads for current session only (cleared on each run)
4. **Progress Tracking**: Atomic file appends for global progress counter across parallel processes
5. **Pre-scan**: Uses `--flat-playlist` to count new songs before downloading (same API cost as the name fetch it replaced)

### Configuration Variables
- `PLAYLIST_FILE`: Input file with playlist URLs (default: `config/playlists.txt`)
- `OUTPUT_ROOT`: Download destination (default: `../Youtube Downloads`)
- `PARALLEL_JOBS`: Number of concurrent downloads (default: 10)
- Archive files are automatically created per playlist in `logs/archives/`

### Command-Line Flags
- `--clean-orphans`: Remove archive entries for playlists with missing/empty output folders
- `--debug`: Enable verbose yt-dlp output (written to debug.log)

### Output Format
- Files named: `Artist - Song Title.mp3`
- Max title length: 100 characters
- Audio quality: Best available (yt-dlp quality 0)
- Metadata preserved in MP3 tags

## Common Development Tasks

### Code Quality Checks
**IMPORTANT**: Always run shellcheck after making changes to bash scripts:
```bash
# Install shellcheck if needed
brew install shellcheck

# Run linting on the main script
shellcheck download_playlists.sh

# Fix any warnings before committing
```

### Modifying Download Behavior
The main yt-dlp command is in the `download_playlist()` function:
```bash
yt-dlp --extract-audio --audio-format mp3 --audio-quality 0 ...
```

### Adding New Features
- Parallel processing logic is in the main loop at the bottom of the script
- Error handling for unavailable videos is in the `download_playlist()` function
- Pre-scan logic is in `scan_playlist()` — runs before downloads to count new songs
- yt-dlp update logic is in `update_ytdlp()` — runs at script start

### Testing Changes
1. Create a test playlist file with 1-2 small playlists
2. Run with modified `PARALLEL_JOBS=1` for easier debugging
3. Check output files in `logs/` directory
4. Run `shellcheck download_playlists.sh` to ensure code quality

## Code Quality Requirements

### Shellcheck Linting
**IMPORTANT**: All bash scripts must pass shellcheck without warnings:
```bash
# Install shellcheck if not available
which shellcheck || brew install shellcheck

# Run linting
shellcheck download_playlists.sh
```

Common shellcheck issues to watch for:
- SC2046: Quote command substitutions to prevent word splitting
- SC2155: Declare and assign variables separately
- SC2188: Redirections without commands need `true` or `:` 
- SC2086: Double quote variables to prevent globbing

If shellcheck reports any issues, fix them before considering the code complete.