import argparse

from yt_playlists.__main__ import _pick_dashboard_mode


def _args(no_dashboard: bool = False) -> argparse.Namespace:
    return argparse.Namespace(no_dashboard=no_dashboard)


def test_non_tty_forces_plain():
    assert _pick_dashboard_mode(_args(), isatty=False) == "plain"


def test_non_tty_overrides_no_dashboard():
    assert _pick_dashboard_mode(_args(no_dashboard=True), isatty=False) == "plain"


def test_tty_default_is_bars():
    assert _pick_dashboard_mode(_args(), isatty=True) == "bars"


def test_tty_with_no_dashboard_is_summary():
    assert _pick_dashboard_mode(_args(no_dashboard=True), isatty=True) == "summary"
