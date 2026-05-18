from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock


class YDLLogger:
    """Custom yt-dlp logger that funnels output to the debug log and an error sink."""

    _file_lock = Lock()

    def __init__(self, playlist: str, debug_log: Path, on_error):
        self._playlist = playlist
        self._debug_log = debug_log
        self._on_error = on_error

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            self._write(msg)

    def info(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            self._write(msg)

    def warning(self, msg: str) -> None:
        self._write(f"WARN [{self._playlist}] {msg}")

    def error(self, msg: str) -> None:
        self._write(f"ERROR [{self._playlist}] {msg}")
        self._on_error(self._playlist, msg)

    def _write(self, line: str) -> None:
        stamped = f"[{datetime.now():%H:%M:%S}] {line}\n"
        with self._file_lock, self._debug_log.open("a", encoding="utf-8") as f:
            f.write(stamped)
