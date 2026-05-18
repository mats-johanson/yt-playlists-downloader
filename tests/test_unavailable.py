from pathlib import Path

from yt_playlists.unavailable import _VIDEO_ID_RE, UnavailableTracker


def test_video_id_re_matches_standard_format():
    m = _VIDEO_ID_RE.search("[youtube] dQw4w9WgXcQ: Video unavailable")
    assert m is not None
    assert m.group(1) == "dQw4w9WgXcQ"


def test_video_id_re_ignores_other_extractors():
    assert _VIDEO_ID_RE.search("[vimeo] abc123: Video unavailable") is None


def test_video_id_re_handles_underscores_and_dashes():
    m = _VIDEO_ID_RE.search("[youtube] AB_cd-12X: gone")
    assert m is not None
    assert m.group(1) == "AB_cd-12X"


def test_record_error_persists_unavailable(tmp_path: Path):
    log = tmp_path / "unavailable.txt"
    t = UnavailableTracker(log)
    t.reset()
    t.record_error("Mix A", "[youtube] dQw4w9WgXcQ: Video unavailable")
    entries = t.entries()
    assert len(entries) == 1
    assert entries[0].playlist == "Mix A"
    assert entries[0].url.endswith("dQw4w9WgXcQ")
    assert log.read_text().strip() == "Mix A|https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_constructor_does_not_truncate(tmp_path: Path):
    log = tmp_path / "u.txt"
    log.write_text("preexisting\n")
    UnavailableTracker(log)  # must not touch the file
    assert log.read_text() == "preexisting\n"


def test_reset_truncates(tmp_path: Path):
    log = tmp_path / "u.txt"
    log.write_text("preexisting\n")
    t = UnavailableTracker(log)
    t.reset()
    assert log.read_text() == ""


def test_bot_block_detection(tmp_path: Path):
    t = UnavailableTracker(tmp_path / "u.txt")
    t.reset()
    t.record_error("Mix A", "ERROR: Sign in to confirm you're not a bot")
    t.record_error("Mix B", "ERROR: HTTP Error 429: Too Many Requests")
    assert t.is_bot_blocked("Mix A")
    assert t.is_bot_blocked("Mix B")
    assert not t.is_bot_blocked("Mix C")
    assert t.bot_blocked_playlists() == {"Mix A", "Mix B"}


def test_record_error_ignores_non_unavailable(tmp_path: Path):
    t = UnavailableTracker(tmp_path / "u.txt")
    t.reset()
    t.record_error("Mix", "[youtube] dQw4w9WgXcQ: Some unrelated message")
    assert t.entries() == []


def test_count_for_groups_by_playlist(tmp_path: Path):
    t = UnavailableTracker(tmp_path / "u.txt")
    t.reset()
    t.record_error("Cool", "[youtube] aaaaaaaaaaa: Video unavailable")
    t.record_error("Cool", "[youtube] bbbbbbbbbbb: Private video")
    t.record_error("Deep", "[youtube] ccccccccccc: has been removed")
    assert t.count_for("Cool") == 2
    assert t.count_for("Deep") == 1
    assert t.count_for("Unknown") == 0
