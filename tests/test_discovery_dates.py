"""Tests for DiscoveryDates persistent store + YT synthesized dates."""

import datetime as _dt
import json

from yt_playlists.discovery_dates import DiscoveryDates
from yt_playlists.sources.youtube import _synth_added_at

# --- DiscoveryDates merge / load / persistence ---


def test_record_and_get(tmp_path):
    d = DiscoveryDates(tmp_path / "dates.json")
    d.record("v1", "2024-03-15T10:00:00Z", "spotify:DJ Mix")
    assert d.get("v1") == "2024-03-15T10:00:00Z"


def test_earliest_date_wins_on_overlap(tmp_path):
    """A video appearing across multiple playlists keeps the EARLIEST added_at —
    that's 'when I first discovered it', not 'when I last added it to anything'.
    """
    d = DiscoveryDates(tmp_path / "dates.json")
    d.record("v1", "2024-06-01T00:00:00Z", "spotify:Later Playlist")
    d.record("v1", "2024-01-01T00:00:00Z", "spotify:Earlier Playlist")
    assert d.get("v1") == "2024-01-01T00:00:00Z"


def test_later_date_does_not_overwrite(tmp_path):
    d = DiscoveryDates(tmp_path / "dates.json")
    d.record("v1", "2024-01-01T00:00:00Z", "early")
    d.record("v1", "2024-12-31T00:00:00Z", "late")
    assert d.get("v1") == "2024-01-01T00:00:00Z"


def test_persists_across_instances(tmp_path):
    path = tmp_path / "dates.json"
    d1 = DiscoveryDates(path)
    d1.record("v1", "2024-03-15T10:00:00Z", "spotify:X")
    d2 = DiscoveryDates(path)
    assert d2.get("v1") == "2024-03-15T10:00:00Z"


def test_record_many_single_atomic_write(tmp_path):
    d = DiscoveryDates(tmp_path / "dates.json")
    changed = d.record_many([
        ("v1", "2024-01-01", "p1"),
        ("v2", "2024-02-01", "p1"),
        ("v3", "2024-03-01", "p1"),
    ])
    assert changed == 3
    assert d.get("v1") == "2024-01-01"
    assert d.get("v3") == "2024-03-01"


def test_record_many_counts_only_actual_changes(tmp_path):
    d = DiscoveryDates(tmp_path / "dates.json")
    d.record("v1", "2024-01-01", "p1")
    # Now re-record same with a LATER date (won't overwrite) + a new vid
    changed = d.record_many([
        ("v1", "2024-06-01", "p2"),  # ignored — later
        ("v2", "2024-02-01", "p1"),  # new
    ])
    assert changed == 1
    assert d.get("v1") == "2024-01-01"
    assert d.get("v2") == "2024-02-01"


def test_invalid_inputs_silently_ignored(tmp_path):
    d = DiscoveryDates(tmp_path / "dates.json")
    d.record("", "2024-01-01", "p")
    d.record("v1", "", "p")
    assert d.get("v1") is None


def test_load_ignores_wrong_schema_version(tmp_path):
    path = tmp_path / "dates.json"
    path.write_text(json.dumps({"version": 999, "entries": {"v1": {"added_at": "x"}}}))
    d = DiscoveryDates(path)
    assert d.get("v1") is None


# --- YouTube position synthesis ---


def test_yt_synth_position_one_oldest():
    today = _dt.date(2026, 6, 19)
    out = _synth_added_at(position=1, total=6, today=today)
    # Position 1 of 6 → today - 5 days = 2026-06-14
    assert out == "2026-06-14T00:00:00Z"


def test_yt_synth_position_last_is_today():
    today = _dt.date(2026, 6, 19)
    out = _synth_added_at(position=6, total=6, today=today)
    assert out == "2026-06-19T00:00:00Z"


def test_yt_synth_preserves_order():
    today = _dt.date(2026, 6, 19)
    dates = [_synth_added_at(p, 10, today) for p in range(1, 11)]
    assert dates == sorted(dates)  # strictly monotonic increase


def test_yt_synth_single_item_playlist():
    today = _dt.date(2026, 6, 19)
    out = _synth_added_at(position=1, total=1, today=today)
    assert out == "2026-06-19T00:00:00Z"
