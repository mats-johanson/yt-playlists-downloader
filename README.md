# YouTube Playlists Downloader

A parallel YouTube playlist downloader that efficiently downloads multiple playlists as MP3 files with proper metadata and error tracking.

## Features

- 🚀 **Parallel Downloads**: Download multiple playlists simultaneously
- 🎵 **MP3 Conversion**: Automatically converts videos to high-quality MP3
- 📊 **Progress Tracking**: Clean output showing only essential information
- ❌ **Error Handling**: Tracks unavailable videos with metadata
- 📝 **Archive Support**: Avoids re-downloading previously downloaded songs
- 🏷️ **Metadata Preservation**: Maintains artist and title information

## Requirements

- `yt-dlp` - YouTube downloader
- `ffmpeg` - For audio conversion
- `bash` - Shell environment

## Installation

1. Install dependencies:
```bash
# macOS
brew install yt-dlp ffmpeg

# Linux
sudo apt install yt-dlp ffmpeg
```

2. Clone this repository:
```bash
git clone <your-repo-url>
cd youtube-playlist-downloader
```

3. Make the script executable:
```bash
chmod +x download_playlists.sh
```

## Usage

1. Create a `yt_playlists.txt` file with your playlist URLs (one per line):
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxx
https://www.youtube.com/playlist?list=PLyyyyyyyyyyyy
```

2. Run the script:
```bash
./download_playlists.sh
```

## Configuration

Edit these variables in the script to customize behavior:

- `PLAYLIST_FILE`: Input file with playlist URLs (default: `yt_playlists.txt`)
- `OUTPUT_ROOT`: Output directory (default: `../Youtube Downloads`)
- `PARALLEL_JOBS`: Number of parallel downloads (default: 10)
- `ARCHIVE_FILE`: Track downloaded files (default: `downloaded.txt`)

## Output Files

- **Downloaded Music**: Saved in `../Youtube Downloads/<Playlist Name>/` (parent directory)
- **Archive**: `downloaded.txt` - Prevents re-downloading
- **Unavailable Videos**: `unavailable_videos.txt` - Lists videos that couldn't be downloaded in the current session (cleared on each run)

All script files are kept in the script directory, while downloaded music is stored in a separate `Youtube Downloads/` folder in the parent directory.

## Output Format

The script provides clean, minimal output:
```
🎵 Starting YouTube playlist downloads...
========================================

📀 Processing: My Favorite Playlist
   ✓ Downloaded: Artist Name - Song Title
   ✓ Downloaded: Another Artist - Another Song
✅ Completed: My Favorite Playlist

========================================
🎉 All downloads complete!

📊 Downloaded 15 new songs

⚠️  Some videos were unavailable:
=================================
  ❌ Unknown Artist - Private Video
     Playlist: My Favorite Playlist
     URL: https://www.youtube.com/watch?v=xxxxx

📁 Files saved in: '../Youtube Downloads'
```

## Troubleshooting

### Videos show as "Unknown Artist - Unknown Title"
This happens when videos are private or deleted. The script attempts to fetch metadata but may fail for inaccessible videos.

### Downloads are slow
- Reduce `PARALLEL_JOBS` if your connection is overwhelmed
- Check if `yt-dlp` needs updating: `yt-dlp -U`

### Permission errors
Ensure the script has write permissions in the current directory.

## License

MIT License - feel free to modify and distribute as needed.