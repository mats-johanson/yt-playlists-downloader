#!/bin/bash
# Thin launcher for the next/ experimental version.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

die() { echo "run.sh: $1" >&2; exit 1; }

# Load .env if present. set -a auto-exports each var, so the file can be plain
# KEY=value lines without explicit `export`. .env is gitignored.
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.env"
    set +a
fi

if command -v uv &>/dev/null; then
    uv sync --quiet --upgrade-package yt-dlp || die "uv sync failed"
    exec uv run --quiet python -m yt_playlists "$@"
fi

VENV="$SCRIPT_DIR/.venv"
[ -d "$VENV" ] || python3 -m venv "$VENV" || die "could not create $VENV"
"$VENV/bin/pip" install --quiet --upgrade pip yt-dlp || die "pip failed"
"$VENV/bin/pip" install --quiet -e . || die "pip install failed"
exec "$VENV/bin/python" -m yt_playlists "$@"
