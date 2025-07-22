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
# Test with a single playlist
echo "https://youtube.com/playlist?list=EXAMPLE" > test_playlist.txt
./download_playlists.sh test_playlist.txt

# Check download logs
tail -f downloaded_songs.txt
tail -f unavailable_videos.txt
```

## Architecture Overview

### Core Components
1. **download_playlists.sh**: Main bash script that orchestrates parallel downloads
   - Uses `yt-dlp` for downloading and `ffmpeg` for MP3 conversion
   - Implements parallel processing (default: 10 concurrent jobs)
   - Maintains download archive to prevent re-downloads

### Directory Structure
- Script lives in `yt-playlists-downloader/`
- Downloads are stored in `../Youtube Downloads/` (parent directory)
- Each playlist gets its own folder named after the playlist title

### Key Design Decisions
1. **Temporary Downloads**: Uses system temp directory during download to prevent partial files
2. **Archive System**: `downloaded.txt` tracks all downloaded video IDs
3. **Error Tracking**: `unavailable_videos.txt` logs failed downloads with metadata
4. **Progress Tracking**: `downloaded_songs.txt` shows current session downloads

### Configuration Variables
- `PLAYLIST_FILE`: Input file with playlist URLs (default: `yt_playlists.txt`)
- `OUTPUT_ROOT`: Download destination (default: `../Youtube Downloads`)
- `PARALLEL_JOBS`: Number of concurrent downloads (default: 10)
- `ARCHIVE_FILE`: File tracking downloaded videos (default: `downloaded.txt`)

### Output Format
- Files named: `Artist - Song Title.mp3`
- Max title length: 100 characters
- Audio quality: Best available (yt-dlp quality 0)
- Metadata preserved in MP3 tags

## Common Development Tasks

### Modifying Download Behavior
The main yt-dlp command is in the `download_playlist()` function:
```bash
yt-dlp --extract-audio --audio-format mp3 --audio-quality 0 ...
```

### Adding New Features
- Parallel processing logic is in the main loop at the bottom of the script
- Error handling for unavailable videos is in the `download_playlist()` function
- Filename cleaning happens post-download in the same function

### Testing Changes
1. Create a test playlist file with 1-2 small playlists
2. Run with modified `PARALLEL_JOBS=1` for easier debugging
3. Check all three output files: `downloaded.txt`, `unavailable_videos.txt`, `downloaded_songs.txt`