#!/bin/bash

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-$SCRIPT_DIR/../Youtube Downloads}"
PARALLEL_JOBS=10

# Handle command-line arguments
if [ "$1" = "--clean-orphans" ]; then
    echo "🧹 Cleaning orphaned archive entries..."
    echo ""
    total_cleaned=0
    for archive in "$SCRIPT_DIR"/logs/archives/*.txt; do
        if [ -f "$archive" ]; then
            playlist_name="$(basename "$archive" .txt)"
            playlist_dir="$OUTPUT_ROOT/$playlist_name"
            if [ ! -d "$playlist_dir" ] || [ -z "$(find "$playlist_dir" -name "*.mp3" -print -quit 2>/dev/null)" ]; then
                count=$(wc -l < "$archive" 2>/dev/null || echo 0)
                if [ "$count" -gt 0 ]; then
                    echo "  Clearing $count entries from $playlist_name archive (folder missing/empty)"
                    true > "$archive"
                    total_cleaned=$((total_cleaned + count))
                fi
            fi
        fi
    done
    echo ""
    echo "✅ Cleaned $total_cleaned orphaned archive entries"
    exit 0
fi

PLAYLIST_FILE="${1:-$SCRIPT_DIR/config/playlists.txt}"

# Ensure directories exist
mkdir -p "$OUTPUT_ROOT" "$SCRIPT_DIR/logs" "$SCRIPT_DIR/logs/archives"

# Log files
UNAVAILABLE_FILE="$SCRIPT_DIR/logs/unavailable-videos.txt"
DEBUG_LOG="$SCRIPT_DIR/logs/debug.log"
STATUS_DIR="$(mktemp -d)"

# Initialize logs
true > "$UNAVAILABLE_FILE"
true > "$DEBUG_LOG"

# Download a single playlist
download_playlist() {
    local url="$1"
    local temp_dir
    local error_log
    local output_log
    local playlist_name
    local playlist_archive
    temp_dir="$(mktemp -d)"
    error_log="$(mktemp)"
    output_log="$(mktemp)"

    # Get playlist name (this happens in parallel now)
    playlist_name="$(yt-dlp --flat-playlist --print "%(playlist_title)s" "$url" 2>"$output_log" | head -1 || echo "Unknown Playlist")"

    # Log errors from playlist name fetch
    if [ -s "$output_log" ]; then
        {
            echo "[$(date '+%H:%M:%S')] Playlist name fetch errors: $url"
            cat "$output_log"
        } >> "$DEBUG_LOG"
    fi

    # Sanitize playlist name for filesystem
    safe_name="${playlist_name//\//_}"
    safe_name="${safe_name//\\/_}"

    # Use per-playlist archive (allows songs in multiple playlists)
    playlist_archive="$SCRIPT_DIR/logs/archives/${safe_name}.txt"

    echo "📀 Downloading: $playlist_name"

    # Create status file for this playlist
    echo "downloading" > "$STATUS_DIR/${safe_name}.status"

    # Temporary files for capturing and processing output
    local combined_output
    combined_output="$(mktemp)"

    # Run yt-dlp and pipe output through progress parser
    yt-dlp \
        --yes-playlist \
        --extract-audio \
        --audio-format mp3 \
        --audio-quality 0 \
        --download-archive "$playlist_archive" \
        --output "$temp_dir/%(playlist_title)s/%(artist)s - %(title).100s.%(ext)s" \
        --concurrent-fragments 5 \
        -v \
        "$url" 2>&1 | while IFS= read -r line; do
        # Capture all output
        echo "$line" >> "$combined_output"

        # Extract and display progress for download/extract lines
        if [[ "$line" =~ \[ExtractAudio\]\ Destination:\ (.*/)?([^/]+\.mp3)$ ]]; then
            filename="${BASH_REMATCH[2]}"
            # Remove the "NA - " prefix if present
            filename="${filename#NA - }"
            echo "[$(date '+%H:%M:%S')] ⬇️  $playlist_name: $filename"
        fi
    done || true  # Don't fail on yt-dlp errors

    # Separate stdout and stderr for debugging
    grep -v "^\[ffmpeg\]" "$combined_output" >"$output_log" 2>/dev/null || true
    grep "^\[ffmpeg\]" "$combined_output" >"$error_log" 2>/dev/null || true
    rm -f "$combined_output"

    # Log all yt-dlp output for debugging
    if [ -s "$output_log" ]; then
        {
            echo "[$(date '+%H:%M:%S')] Download output for: $playlist_name"
            cat "$output_log"
            echo ""
        } >> "$DEBUG_LOG"
    fi

    if [ -s "$error_log" ]; then
        {
            echo "[$(date '+%H:%M:%S')] Download errors for: $playlist_name"
            cat "$error_log"
            echo ""
        } >> "$DEBUG_LOG"
    fi

    # Handle unavailable videos
    grep -E "Video unavailable|Private video|has been removed" "$error_log" 2>/dev/null | while read -r line; do
        if [[ "$line" =~ \[youtube\]\ ([^:]+): ]]; then
            echo "$playlist_name|Unknown|Unknown|https://www.youtube.com/watch?v=${BASH_REMATCH[1]}" >> "$UNAVAILABLE_FILE"
        fi
    done
    
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
    rm -rf "$temp_dir" "$error_log" "$output_log"
    
    # Mark as completed in status file (silently)
    echo "completed" > "$STATUS_DIR/${safe_name}.status"
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
export OUTPUT_ROOT UNAVAILABLE_FILE SCRIPT_DIR STATUS_DIR DEBUG_LOG

job_count=0
for url in "${urls[@]}"; do
    # Wait if we've reached the parallel job limit
    while [ "$(jobs -r | wc -l)" -ge "$PARALLEL_JOBS" ]; do
        sleep 0.5
    done
    
    # Start the download in background
    download_playlist "$url" &
    ((job_count++))
done

echo ""
echo "⏳ All playlists queued ($job_count total), waiting for completion..."
echo ""

# Wait for all downloads to complete
wait

# Display completion status for all playlists
echo ""
echo "📊 Playlist completion status:"
echo "================================="
completed_count=0
incomplete_count=0
for status_file in "$STATUS_DIR"/*.status; do
    if [ -f "$status_file" ]; then
        safe_name="$(basename "$status_file" .status)"
        status="$(cat "$status_file")"
        
        # Try to find the original playlist name from the archive filename
        archive_file="$SCRIPT_DIR/logs/archives/${safe_name}.txt"
        if [ -f "$archive_file" ]; then
            # Use the safe name as display name (slashes were replaced with underscores)
            display_name="${safe_name}"
        else
            display_name="${safe_name}"
        fi
        
        if [ "$status" = "completed" ]; then
            echo "✅ $display_name"
            ((completed_count++))
        else
            echo "❌ $display_name (incomplete)"
            ((incomplete_count++))
        fi
    fi
done

echo ""
echo "Summary: $completed_count completed, $incomplete_count incomplete"

# Clean up "NA - " prefixes from filenames
find "$OUTPUT_ROOT" -type f -name "NA - *.mp3" | while read -r file; do
    mv "$file" "${file/NA - /}" 2>/dev/null || true
done

# Summary
echo ""
echo "========================================"
echo "🎉 All downloads complete!"
echo ""

# Count total downloads across all playlists
total_count=0
orphaned_count=0
for archive in "$SCRIPT_DIR"/logs/archives/*.txt; do
    if [ -f "$archive" ]; then
        count=$(wc -l < "$archive")
        total_count=$((total_count + count))
        
        # Check for orphaned entries (songs in archive but folder missing/empty)
        playlist_name="$(basename "$archive" .txt)"
        playlist_dir="$OUTPUT_ROOT/$playlist_name"
        if [ ! -d "$playlist_dir" ] || [ -z "$(find "$playlist_dir" -name "*.mp3" -print -quit 2>/dev/null)" ]; then
            # If playlist folder doesn't exist or has no MP3 files, count all archive entries as orphaned
            archive_count=$(wc -l < "$archive")
            if [ "$archive_count" -gt 0 ]; then
                orphaned_count=$((orphaned_count + archive_count))
            fi
        fi
    fi
done
[ "$total_count" -gt 0 ] && echo "📊 Total songs in archives: $total_count"
[ "$orphaned_count" -gt 0 ] && echo "⚠️  Found $orphaned_count orphaned archive entries (songs previously downloaded but files missing)"

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
echo ""
echo "📋 Debug log: '$DEBUG_LOG'"

# Cleanup
rm -rf "$STATUS_DIR"