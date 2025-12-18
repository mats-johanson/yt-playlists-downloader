#!/bin/bash

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_OUTPUT_DIR="$SCRIPT_DIR/test_downloads"
TEST_PLAYLIST_DIR="$TEST_OUTPUT_DIR/Reeda löga"

echo "🧪 Setting up test environment..."
echo ""

# Clear the test output directory
if [ -d "$TEST_OUTPUT_DIR" ]; then
    echo "🧹 Clearing existing test folder: $TEST_OUTPUT_DIR"
    rm -rf "$TEST_OUTPUT_DIR"
fi

# Create test output directory
mkdir -p "$TEST_OUTPUT_DIR"

# Clear the archive file for this test playlist
ARCHIVE_FILE="$SCRIPT_DIR/logs/archives/Reeda löga.txt"
if [ -f "$ARCHIVE_FILE" ]; then
    echo "🧹 Clearing archive history for test playlist"
    rm -f "$ARCHIVE_FILE"
fi

# Create test playlist file
TEST_PLAYLIST_FILE="$(mktemp)"
echo "https://www.youtube.com/playlist?list=PLh4d96gc6mcaKRYnWtgWCs1JvaUHeaT0v" > "$TEST_PLAYLIST_FILE"

echo "📋 Running download with test playlist..."
echo ""

# Run the download script with test playlist, using custom output directory
OUTPUT_ROOT="$TEST_OUTPUT_DIR" "$SCRIPT_DIR/download_playlists.sh" "$TEST_PLAYLIST_FILE"

# Cleanup
rm -f "$TEST_PLAYLIST_FILE"

echo ""
echo "✅ Test complete! Files saved in: $TEST_PLAYLIST_DIR"
