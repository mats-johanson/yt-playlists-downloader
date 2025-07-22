#!/bin/bash

set -e

# Config
PLAYLIST_FILE="yt_playlists.txt"
OUTPUT_ROOT="Youtube Downloads"
PARALLEL_JOBS=10
ARCHIVE_FILE="downloaded.txt"
UNAVAILABLE_FILE="unavailable_videos.txt"
DOWNLOADED_FILE="downloaded_songs.txt"

mkdir -p "$OUTPUT_ROOT"
TEMP_DIR="$(mktemp -d)"

# Clear the downloaded songs file for this run
> "$DOWNLOADED_FILE"

download_playlist() {
    local playlist_url="$1"
    local temp_path
    temp_path="$(mktemp -d -p "$TEMP_DIR")"
    local error_log
    error_log="$(mktemp -p "$TEMP_DIR")"
    local info_log
    info_log="$(mktemp -p "$TEMP_DIR")"

    local output_template="$temp_path/%(playlist_title)s/%(artist)s - %(title).100s.%(ext)s"

    # Get playlist name first
    local playlist_name
    playlist_name=$(yt-dlp --quiet --no-warnings --flat-playlist --print "%(playlist_title)s" "$playlist_url" 2>/dev/null | head -1 || echo "Unknown Playlist")
    
    echo "📀 Processing: $playlist_name"

    # Download with minimal output
    if ! yt-dlp \
        --quiet \
        --no-warnings \
        --progress \
        --yes-playlist \
        --extract-audio \
        --audio-format mp3 \
        --audio-quality 0 \
        --download-archive "$ARCHIVE_FILE" \
        --output "$output_template" \
        --concurrent-fragments 5 \
        --print-to-file "%(playlist_title)s|%(artist)s|%(title)s|%(webpage_url)s" "$info_log" \
        --exec "echo '   ✓ Downloaded: %(artist)s - %(title)s'" \
        "$playlist_url" 2>"$error_log"; then
        
        # Parse error log for unavailable videos
        while IFS= read -r line; do
            if [[ "$line" =~ \[youtube\]\ ([^:]+):.*Video\ unavailable ]] || \
               [[ "$line" =~ \[youtube\]\ ([^:]+):.*Private\ video ]] || \
               [[ "$line" =~ \[youtube\]\ ([^:]+):.*has\ been\ removed ]]; then
                
                local video_id="${BASH_REMATCH[1]}"
                local video_url="https://www.youtube.com/watch?v=$video_id"
                
                # Try to get video info using a separate yt-dlp call
                local video_info
                video_info=$(yt-dlp --quiet --no-warnings --skip-download --print "%(artist)s|%(title)s" "$video_url" 2>/dev/null || echo "Unknown Artist|Unknown Title")
                
                echo "$playlist_name|$video_info|$video_url" >> "$UNAVAILABLE_FILE"
            fi
        done < "$error_log"
    fi

    # Save downloaded songs info
    if [ -f "$info_log" ] && [ -s "$info_log" ]; then
        cat "$info_log" >> "$DOWNLOADED_FILE"
    fi

    # Move files to final destination
    for playlist_folder in "$temp_path"/*; do
        [ -d "$playlist_folder" ] || continue
        playlist_title="$(basename "$playlist_folder")"
        final_dest="$OUTPUT_ROOT/$playlist_title"
        mkdir -p "$final_dest"
        mv "$playlist_folder"/* "$final_dest/" 2>/dev/null || true
    done

    rm -rf "$temp_path" "$error_log" "$info_log"
    echo "✅ Completed: $playlist_name"
    echo ""
}

export -f download_playlist
export TEMP_DIR
export OUTPUT_ROOT
export ARCHIVE_FILE
export UNAVAILABLE_FILE
export DOWNLOADED_FILE

echo "🎵 Starting YouTube playlist downloads..."
echo "========================================"
echo ""

# Run downloads in parallel
grep -v '^\s*$' "$PLAYLIST_FILE" | xargs -P "$PARALLEL_JOBS" -I {} bash -c 'download_playlist "$@"' _ {}

# Clean up NA prefixes
find "$OUTPUT_ROOT" -type f -name "NA - *.mp3" 2>/dev/null | while IFS= read -r file; do
    newfile="$(dirname "$file")/$(basename "$file" | sed 's/^NA - //')"
    mv "$file" "$newfile"
done

rm -rf "$TEMP_DIR"

echo "========================================"
echo "🎉 All downloads complete!"
echo ""

# Display summary of downloaded songs
if [ -f "$DOWNLOADED_FILE" ] && [ -s "$DOWNLOADED_FILE" ]; then
    local download_count=$(wc -l < "$DOWNLOADED_FILE")
    echo "📊 Downloaded $download_count new songs"
    echo ""
fi

# Display unavailable videos if any were found
if [ -f "$UNAVAILABLE_FILE" ] && [ -s "$UNAVAILABLE_FILE" ]; then
    echo "⚠️  Some videos were unavailable:"
    echo "================================="
    while IFS='|' read -r playlist artist title url; do
        echo "  ❌ $artist - $title"
        echo "     Playlist: $playlist"
        echo "     URL: $url"
        echo ""
    done < "$UNAVAILABLE_FILE"
    echo "Full list saved to: $UNAVAILABLE_FILE"
else
    echo "✨ All videos were successfully processed!"
fi

echo ""
echo "📁 Files saved in: '$OUTPUT_ROOT'"