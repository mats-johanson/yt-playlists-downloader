#!/bin/bash
# Thin launcher — syncs deps via uv (or venv+pip fallback) and runs the
# yt_playlists Python package. All real logic lives in yt_playlists/.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

die() {
    echo "download_playlists.sh: $1" >&2
    exit 1
}

if command -v uv &>/dev/null; then
    # Upgrade yt-dlp in-place each run, then sync the rest. Doing this from
    # the launcher (not from Python) avoids reloading an already-imported
    # yt_dlp module mid-process — a no-op that the in-process updater used
    # to do before being deleted.
    uv sync --quiet --upgrade-package yt-dlp || die "uv sync failed — check network / lockfile"
    exec uv run --quiet python -m yt_playlists "$@"
fi

# Fallback: project-local venv via system python3 + pip.
VENV="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV" || die "could not create $VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip yt-dlp || die "pip upgrade failed"
"$VENV/bin/pip" install --quiet -e . || die "pip install failed"
exec "$VENV/bin/python" -m yt_playlists "$@"
