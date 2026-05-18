#!/bin/bash

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_OUTPUT_DIR="$SCRIPT_DIR/test_downloads"

echo "Setting up test environment..."
echo ""

# Clear the test output directory
if [ -d "$TEST_OUTPUT_DIR" ]; then
    echo "Clearing existing test folder: $TEST_OUTPUT_DIR"
    rm -rf "$TEST_OUTPUT_DIR"
fi
mkdir -p "$TEST_OUTPUT_DIR"

# Test playlists (3 small playlists to verify parallel downloads)
declare -a TEST_PLAYLISTS=(
    "Reeda löga|https://www.youtube.com/playlist?list=PLh4d96gc6mcaKRYnWtgWCs1JvaUHeaT0v"
    "Nostalgia|https://www.youtube.com/playlist?list=PLh4d96gc6mcb-FVPS2vppz2UpRmYo7FGI"
    "Lõpulood|https://www.youtube.com/playlist?list=PLh4d96gc6mcYOa2k_flaNvo_BJFSR7bwj"
)

# Clear archive files for test playlists
for entry in "${TEST_PLAYLISTS[@]}"; do
    name="${entry%%|*}"
    archive="$SCRIPT_DIR/logs/archives/${name}.txt"
    if [ -f "$archive" ]; then
        echo "Clearing archive: $name"
        rm -f "$archive"
    fi
done

# Create test playlist file
TEST_PLAYLIST_FILE="$(mktemp)"
for entry in "${TEST_PLAYLISTS[@]}"; do
    echo "${entry#*|}" >> "$TEST_PLAYLIST_FILE"
done

echo ""
echo "Running download with ${#TEST_PLAYLISTS[@]} test playlists..."
echo ""

# Run the download script
OUTPUT_ROOT="$TEST_OUTPUT_DIR" "$SCRIPT_DIR/download_playlists.sh" "$TEST_PLAYLIST_FILE"

# Cleanup
rm -f "$TEST_PLAYLIST_FILE"

echo ""
echo "Test complete! Files saved in: $TEST_OUTPUT_DIR"
