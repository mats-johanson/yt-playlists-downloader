#!/bin/bash

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-$SCRIPT_DIR/../Youtube Downloads}"
PARALLEL_JOBS=10
DEBUG_MODE=false

# ANSI formatting (disabled when output is not a terminal)
if [ -t 1 ]; then
    BOLD=$'\033[1m'
    DIM=$'\033[2m'
    GREEN=$'\033[32m'
    RED=$'\033[31m'
    RESET=$'\033[0m'
else
    BOLD="" DIM="" GREEN="" RED="" RESET=""
fi

# Handle --clean-orphans (early exit)
if [ "$1" = "--clean-orphans" ]; then
    echo "Cleaning orphaned archive entries..."
    echo ""
    total_cleaned=0
    for archive in "$SCRIPT_DIR"/logs/archives/*.txt; do
        [ -f "$archive" ] || continue
        playlist_name="$(basename "$archive" .txt)"
        playlist_dir="$OUTPUT_ROOT/$playlist_name"
        if [ ! -d "$playlist_dir" ] || [ -z "$(find "$playlist_dir" -name "*.mp3" -print -quit 2>/dev/null)" ]; then
            count=$(wc -l < "$archive" 2>/dev/null || echo 0)
            count="${count// }"
            if [ "$count" -gt 0 ]; then
                echo "  Clearing $count entries from $playlist_name archive (folder missing/empty)"
                true > "$archive"
                total_cleaned=$((total_cleaned + count))
            fi
        fi
    done
    echo ""
    echo "Cleaned $total_cleaned orphaned archive entries"
    exit 0
fi

# Parse arguments
PLAYLIST_FILE=""
for arg in "$@"; do
    case "$arg" in
        --debug) DEBUG_MODE=true ;;
        *) PLAYLIST_FILE="$arg" ;;
    esac
done
PLAYLIST_FILE="${PLAYLIST_FILE:-$SCRIPT_DIR/config/playlists.txt}"

# Ensure directories exist
mkdir -p "$OUTPUT_ROOT" "$SCRIPT_DIR/logs" "$SCRIPT_DIR/logs/archives"

# Log files and temp directories
UNAVAILABLE_FILE="$SCRIPT_DIR/logs/unavailable-videos.txt"
DEBUG_LOG="$SCRIPT_DIR/logs/debug.log"
STATUS_DIR="$(mktemp -d)"
SCAN_DIR="$(mktemp -d)"
PROGRESS_FILE="$(mktemp)"

# Initialize logs
true > "$UNAVAILABLE_FILE"
true > "$DEBUG_LOG"
true > "$PROGRESS_FILE"

# On interrupt: kill entire process group (background yt-dlp processes)
trap 'trap - INT TERM; kill 0' INT TERM
# On exit: clean up temp files
trap 'rm -rf "$STATUS_DIR" "$SCAN_DIR" "$PROGRESS_FILE" 2>/dev/null' EXIT

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

update_ytdlp() {
    printf "Updating yt-dlp... "
    local update_output
    if update_output=$(yt-dlp -U 2>&1); then
        yt-dlp --version
    elif command -v brew &>/dev/null; then
        if brew upgrade yt-dlp 2>&1 | tail -1; then
            yt-dlp --version
        else
            echo "update failed (run manually)"
            echo "[$(date '+%H:%M:%S')] yt-dlp update failed: $update_output" >> "$DEBUG_LOG"
        fi
    else
        echo "update failed (run manually)"
        echo "[$(date '+%H:%M:%S')] yt-dlp update failed: $update_output" >> "$DEBUG_LOG"
    fi
}

scan_playlist() {
    local url="$1"
    local index="$2"
    local output

    # Get playlist name and video IDs in one call (replaces separate name fetch)
    output=$(yt-dlp --flat-playlist --force-ipv4 --print $'%(playlist_title)s\t%(id)s' "$url" 2>/dev/null) || true

    if [ -z "$output" ]; then
        printf 'Unknown Playlist\t0\t0\t%s\n' "$url" > "$SCAN_DIR/$index.txt"
        return
    fi

    local playlist_name
    playlist_name=$(head -1 <<< "$output" | cut -f1)
    [ -z "$playlist_name" ] && playlist_name="Unknown Playlist"

    # Sanitize for filesystem
    local safe_name="${playlist_name//\//_}"
    safe_name="${safe_name//\\/_}"

    local total
    total=$(wc -l <<< "$output")
    total="${total// }"

    # Extract IDs in archive format ("youtube <id>")
    local archive_ids
    archive_ids=$(cut -f2 <<< "$output" | sed 's/^/youtube /')

    # Count new videos not yet in archive
    local archive="$SCRIPT_DIR/logs/archives/${safe_name}.txt"
    local new_count
    if [ -f "$archive" ] && [ -s "$archive" ]; then
        new_count=$(grep -Fxvcf "$archive" <<< "$archive_ids" || true)
        new_count="${new_count// }"
    else
        new_count="$total"
    fi

    printf '%s\t%s\t%s\t%s\n' "$playlist_name" "$total" "$new_count" "$url" > "$SCAN_DIR/$index.txt"
}

download_playlist() {
    local playlist_name="$1"
    local url="$2"

    local safe_name="${playlist_name//\//_}"
    safe_name="${safe_name//\\/_}"

    local playlist_archive="$SCRIPT_DIR/logs/archives/${safe_name}.txt"
    local temp_dir
    temp_dir="$(mktemp -d)"
    local error_log
    error_log="$(mktemp)"

    echo "downloading" > "$STATUS_DIR/${safe_name}.status"

    # Build yt-dlp arguments
    local ytdlp_args=(
        --yes-playlist
        --extract-audio
        --audio-format mp3
        --audio-quality 0
        --download-archive "$playlist_archive"
        --concurrent-fragments 5
        --force-ipv4
        # yt-dlp conditional template: if artist exists, output "Artist - ", otherwise nothing
        --output "$temp_dir/%(playlist_title)s/%(artist&{} - |)s%(title).100s.%(ext)s"
    )

    if [ "$DEBUG_MODE" = true ]; then
        ytdlp_args+=(-v)
    fi

    # Download with progress tracking (process substitution keeps vars in current shell)
    local song_count=0
    while IFS= read -r line; do
        if [[ "$line" =~ \[ExtractAudio\]\ Destination:\ (.*/)?([^/]+\.mp3)$ ]]; then
            local filename="${BASH_REMATCH[2]}"
            song_count=$((song_count + 1))

            # Atomic append for global progress (short writes are POSIX-atomic)
            echo "1" >> "$PROGRESS_FILE" 2>/dev/null || true
            local current
            current=$(wc -l < "$PROGRESS_FILE" 2>/dev/null || echo "?")
            current="${current// }"

            # Strip .mp3 extension and truncate long names
            filename="${filename%.mp3}"
            if [ "${#filename}" -gt 60 ]; then
                filename="${filename:0:57}..."
            fi
            printf "  ${DIM}%${#TOTAL_NEW}s/%s${RESET}  ${BOLD}%s:${RESET} %s\n" "$current" "$TOTAL_NEW" "$playlist_name" "$filename"
        fi
    done < <(yt-dlp "${ytdlp_args[@]}" "$url" 2>"$error_log" || true)

    # Log errors and extract unavailable video info
    local had_errors=false
    if [ -s "$error_log" ]; then
        {
            echo "[$(date '+%H:%M:%S')] Errors for: $playlist_name"
            cat "$error_log"
            echo ""
        } >> "$DEBUG_LOG"

        # Detect rate limiting / auth errors
        if grep -qE "Sign in to confirm|confirm you're not a bot|HTTP Error 429" "$error_log" 2>/dev/null; then
            had_errors=true
        fi

        grep -E "Video unavailable|Private video|has been removed" "$error_log" 2>/dev/null | while read -r err_line; do
            if [[ "$err_line" =~ \[youtube\]\ ([^:]+): ]]; then
                echo "$playlist_name|Unknown|Unknown|https://www.youtube.com/watch?v=${BASH_REMATCH[1]}" >> "$UNAVAILABLE_FILE"
            fi
        done
    fi
    rm -f "$error_log"

    # Move downloaded files to final destination
    if [ -d "$temp_dir" ]; then
        find "$temp_dir" -type d -mindepth 1 -maxdepth 1 | while read -r playlist_dir; do
            local dest
            dest="$OUTPUT_ROOT/$(basename "$playlist_dir")"
            mkdir -p "$dest"
            find "$playlist_dir" -type f -name "*.mp3" -exec mv {} "$dest/" \;
        done
    fi

    rm -rf "$temp_dir"

    # Mark status — 0 songs from a playlist we expected to have new ones is a failure
    if [ "$song_count" -gt 0 ]; then
        echo "completed|$song_count" > "$STATUS_DIR/${safe_name}.status"
        printf "%*s  ${GREEN}✓${RESET} %s ${DIM}(%s songs)${RESET}\n" $((${#TOTAL_NEW} * 2 + 14)) "" "$playlist_name" "$song_count"
    elif [ "$had_errors" = true ]; then
        echo "failed|0" > "$STATUS_DIR/${safe_name}.status"
        printf "%*s  ${RED}✗ %s (blocked by YouTube)${RESET}\n" $((${#TOTAL_NEW} * 2 + 14)) "" "$playlist_name"
    else
        echo "failed|0" > "$STATUS_DIR/${safe_name}.status"
        printf "%*s  ${RED}✗ %s (no songs downloaded)${RESET}\n" $((${#TOTAL_NEW} * 2 + 14)) "" "$playlist_name"
    fi
}

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

# Step 1: Update yt-dlp
update_ytdlp
echo ""

# Step 2: Read playlist URLs
declare -a urls
while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    urls+=("$line")
done < "$PLAYLIST_FILE"

# Step 3: Pre-scan playlists in parallel
echo "Scanning ${#urls[@]} playlists..."
echo ""

export -f scan_playlist
export SCRIPT_DIR SCAN_DIR

for i in "${!urls[@]}"; do
    while [ "$(jobs -r | wc -l)" -ge "$PARALLEL_JOBS" ]; do
        sleep 0.5
    done
    scan_playlist "${urls[$i]}" "$i" &
    sleep 0.5
done
wait

# Step 4: Read scan results and display summary
TOTAL_NEW=0
declare -a playlist_names
declare -a playlist_urls

for i in "${!urls[@]}"; do
    if [ -f "$SCAN_DIR/$i.txt" ]; then
        IFS=$'\t' read -r name total new url < "$SCAN_DIR/$i.txt"
        TOTAL_NEW=$((TOTAL_NEW + new))

        if [ "$new" -gt 0 ]; then
            playlist_names+=("$name")
            playlist_urls+=("$url")
            printf "  %-20s %3s videos, ${BOLD}%s new${RESET}\n" "$name" "$total" "$new"
        else
            uptodate_count=$((${uptodate_count:-0} + 1))
        fi
    fi
done

[ "${uptodate_count:-0}" -gt 0 ] && echo "  ${DIM}($uptodate_count playlists up to date)${RESET}"
echo ""
if [ "$TOTAL_NEW" -eq 0 ]; then
    echo "All playlists up to date — nothing to download"
    exit 0
fi
echo "${BOLD}$TOTAL_NEW${RESET} new songs to download"
echo ""

# Step 5: Download playlists in parallel (skip those with no new songs)
export -f download_playlist
export OUTPUT_ROOT UNAVAILABLE_FILE SCRIPT_DIR STATUS_DIR DEBUG_LOG PROGRESS_FILE TOTAL_NEW DEBUG_MODE
export BOLD DIM GREEN RED RESET

# Print all starting playlists first, then launch
for name in "${playlist_names[@]}"; do
    echo "  ${DIM}→ $name${RESET}"
done
echo ""

for i in "${!playlist_names[@]}"; do
    while [ "$(jobs -r | wc -l)" -ge "$PARALLEL_JOBS" ]; do
        sleep 0.5
    done
    download_playlist "${playlist_names[$i]}" "${playlist_urls[$i]}" &
    sleep 1
done
wait

# Step 6: Final summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

downloaded=$(wc -l < "$PROGRESS_FILE")
downloaded="${downloaded// }"
echo "Done — ${BOLD}$downloaded${RESET} songs downloaded"
echo ""

# Two-column playlist status grid
declare -a status_lines
for status_file in "$STATUS_DIR"/*.status; do
    [ -f "$status_file" ] || continue
    safe_name="$(basename "$status_file" .status)"
    IFS='|' read -r status count < "$status_file"

    if [ "$status" = "completed" ]; then
        if [ "${count:-0}" -gt 0 ] 2>/dev/null; then
            status_lines+=("$(printf "  ${GREEN}✓${RESET} %-18s %3s" "$safe_name" "$count")")
        else
            status_lines+=("$(printf "  ${GREEN}✓${RESET} %-18s ${DIM}  -${RESET}" "$safe_name")")
        fi
    else
        status_lines+=("$(printf "  ${RED}✗${RESET} %-18s ${RED}fail${RESET}" "$safe_name")")
    fi
done

for ((i = 0; i < ${#status_lines[@]}; i += 2)); do
    if [ $((i + 1)) -lt ${#status_lines[@]} ]; then
        echo "${status_lines[$i]}    ${status_lines[$((i + 1))]}"
    else
        echo "${status_lines[$i]}"
    fi
done

# Archive statistics
echo ""
total_count=0
for archive in "$SCRIPT_DIR"/logs/archives/*.txt; do
    [ -f "$archive" ] || continue
    count=$(wc -l < "$archive")
    count="${count// }"
    total_count=$((total_count + count))
done
[ "$total_count" -gt 0 ] && echo "${DIM}$total_count total songs in archive${RESET}"

# Unavailable videos
if [ -s "$UNAVAILABLE_FILE" ]; then
    echo ""
    echo "Some videos were unavailable:"
    awk -F'|' '{printf "  ✗ %s - %s\n    Playlist: %s\n    URL: %s\n\n", $2, $3, $1, $4}' "$UNAVAILABLE_FILE"
fi

echo ""
echo "${DIM}Files saved to: $OUTPUT_ROOT${RESET}"
