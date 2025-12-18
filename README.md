# YouTube Playlists Downloader

Downloads YouTube playlists as MP3 files with smart archive tracking and parallel processing.

## Requirements

- `yt-dlp`
- `ffmpeg`

Install on macOS:
```bash
brew install yt-dlp ffmpeg
```

## Setup

1. Clone the repository
2. Make the script executable:
```bash
chmod +x download_playlists.sh
```

## Usage

1. Create `config/playlists.txt` with your playlist URLs (one per line):
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxx
https://www.youtube.com/playlist?list=PLyyyyyyyyyyyy
```

2. Run:
```bash
./download_playlists.sh
```

MP3 files will be saved in `../Youtube Downloads/[Playlist Name]/`

### Additional Commands

Clean orphaned archive entries (when files were deleted but archives remain):
```bash
./download_playlists.sh --clean-orphans
```

## Testing

Use the included test script to validate changes without affecting your main downloads:

```bash
chmod +x test.sh
./test.sh
```

This will:
- Download a small test playlist (`Reeda löga` with 2 videos)
- Save files to `./test_downloads/` (within the project, not your main library)
- Clear the test folder and archive history before each run
- Show real-time progress as videos are processed

Perfect for testing new features or bug fixes!

## Configuration

Edit these variables in the script if needed:
- `PARALLEL_JOBS`: Number of parallel downloads (default: 10)
- `OUTPUT_ROOT`: Where to save files (default: `../Youtube Downloads`)

## Files Created

- `logs/archives/[Playlist Name].txt` - Per-playlist archive tracking (allows same song in multiple playlists)
- `logs/unavailable-videos.txt` - Lists videos that failed in the current run

## Features

- 🎵 Downloads YouTube playlists and converts to MP3
- ⚡ Parallel downloads (10 concurrent by default)
- 📝 Preserves metadata (artist, title, album)
- 🔄 Per-playlist archive tracking (songs can exist in multiple playlists)
- 📊 Progress tracking and error reporting
- 🗂️ Organized folder structure per playlist
- 🧹 Orphaned archive detection and cleaning