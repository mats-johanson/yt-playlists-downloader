#!/bin/bash

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAYLIST_FILE="${1:-$SCRIPT_DIR/config/playlists.txt}"
OUTPUT_ROOT="$SCRIPT_DIR/../Youtube Downloads"
PARALLEL_JOBS=10

# Ensure directories exist
mkdir -p "$OUTPUT_ROOT" "$SCRIPT_DIR/logs"

# Log files
ARCHIVE_FILE="$SCRIPT_DIR/logs/download-archive.txt"
UNAVAILABLE_FILE="$SCRIPT_DIR/logs/unavailable-videos.txt"
ARCHIVE_SNAPSHOT="$(mktemp)"

# Initialize logs
true > "$UNAVAILABLE_FILE"
if [ -f "$ARCHIVE_FILE" ]; then
    cp "$ARCHIVE_FILE" "$ARCHIVE_SNAPSHOT"
else
    touch "$ARCHIVE_SNAPSHOT"
fi

# Download a single playlist
download_playlist() {
    local url="$1"
    local temp_dir
    local error_log
    local playlist_name
    temp_dir="$(mktemp -d)"
    error_log="$(mktemp)"
    
    # Get playlist name (this happens in parallel now)
    playlist_name="$(yt-dlp --quiet --no-warnings --flat-playlist --print "%(playlist_title)s" "$url" 2>/dev/null | head -1 || echo "Unknown Playlist")"
    
    echo "📀 Downloading: $playlist_name"
    yt-dlp \
        --quiet \
        --no-warnings \
        --yes-playlist \
        --extract-audio \
        --audio-format mp3 \
        --audio-quality 0 \
        --download-archive "$ARCHIVE_FILE" \
        --output "$temp_dir/%(playlist_title)s/%(artist)s - %(title).100s.%(ext)s" \
        --concurrent-fragments 5 \
        "$url" 2>"$error_log"
    
    local exit_code=$?
    
    # Handle unavailable videos
    if [ $exit_code -ne 0 ]; then
        grep -E "Video unavailable|Private video|has been removed" "$error_log" | while read -r line; do
            if [[ "$line" =~ \[youtube\]\ ([^:]+): ]]; then
                echo "$playlist_name|Unknown|Unknown|https://www.youtube.com/watch?v=${BASH_REMATCH[1]}" >> "$UNAVAILABLE_FILE"
            fi
        done
    fi
    
    # Move downloaded files to final destination
    if [ -d "$temp_dir" ]; then
        find "$temp_dir" -type d -mindepth 1 -maxdepth 1 | while read -r playlist_dir; do
            local dest
            dest="$OUTPUT_ROOT/$(basename "$playlist_dir")"
            mkdir -p "$dest"
            find "$playlist_dir" -type f -name "*.mp3" -exec mv {} "$dest/" \;
        done
    fi
    
    # Cleanup
    rm -rf "$temp_dir" "$error_log"
    echo "✅ Completed: $playlist_name"
}

# Main execution
echo "🎵 Starting YouTube playlist downloads..."
echo ""

# Read playlists
declare -a urls
while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    urls+=("$line")
done < "$PLAYLIST_FILE"

echo "📋 Found ${#urls[@]} playlists to download"
echo ""
echo "⏳ Starting downloads (max $PARALLEL_JOBS parallel)..."
echo ""

# Download playlists in parallel
export -f download_playlist
export OUTPUT_ROOT ARCHIVE_FILE UNAVAILABLE_FILE

for url in "${urls[@]}"; do
    download_playlist "$url" &
    
    # Limit parallel jobs
    while [ "$(jobs -r | wc -l)" -ge "$PARALLEL_JOBS" ]; do
        sleep 0.1
    done
done

# Wait for all downloads
wait

# Clean up "NA - " prefixes from filenames
find "$OUTPUT_ROOT" -type f -name "NA - *.mp3" | while read -r file; do
    mv "$file" "${file/NA - /}" 2>/dev/null || true
done

# Summary
echo ""
echo "========================================"
echo "🎉 All downloads complete!"
echo ""

# Count new downloads
if [ -f "$ARCHIVE_FILE" ] && [ -f "$ARCHIVE_SNAPSHOT" ]; then
    new_count="$(comm -13 <(sort "$ARCHIVE_SNAPSHOT") <(sort "$ARCHIVE_FILE") | wc -l)"
    [ "$new_count" -gt 0 ] && echo "📊 Downloaded $new_count new songs"
fi

# Show unavailable videos
if [ -s "$UNAVAILABLE_FILE" ]; then
    echo ""
    echo "⚠️  Some videos were unavailable:"
    echo "================================="
    awk -F'|' '{printf "  ❌ %s - %s\n     Playlist: %s\n     URL: %s\n\n", $2, $3, $1, $4}' "$UNAVAILABLE_FILE"
    echo "Full list saved to: $UNAVAILABLE_FILE"
else
    echo "✨ All videos were successfully processed!"
fi

echo ""
echo "📁 Files saved in: '$OUTPUT_ROOT'"

# Cleanup
rm -f "$ARCHIVE_SNAPSHOT"