# YouTube Playlists Downloader

Downloads YouTube playlists as MP3 files.

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

## Configuration

Edit these variables in the script if needed:
- `PARALLEL_JOBS`: Number of parallel downloads (default: 10)
- `OUTPUT_ROOT`: Where to save files (default: `../Youtube Downloads`)

## Files Created

- `logs/download-archive.txt` - Tracks all downloaded videos to avoid re-downloading
- `logs/unavailable-videos.txt` - Lists videos that failed in the current run