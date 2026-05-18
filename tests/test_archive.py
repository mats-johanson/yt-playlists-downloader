from pathlib import Path

from yt_playlists.archive import (
    archive_path,
    count_archived,
    filter_new,
    read_archive,
    sanitize_name,
    total_archived,
)


def test_sanitize_name_replaces_path_separators():
    assert sanitize_name("foo/bar") == "foo_bar"
    assert sanitize_name("foo\\bar") == "foo_bar"
    assert sanitize_name("foo/bar\\baz") == "foo_bar_baz"


def test_sanitize_name_passthrough():
    assert sanitize_name("Top 100 Daily") == "Top 100 Daily"


def test_filter_new_drops_archived():
    archived = {"youtube abc123", "youtube def456"}
    assert filter_new(["abc123", "xyz789", "def456"], archived) == ["xyz789"]


def test_filter_new_empty_archive():
    assert filter_new(["a", "b"], set()) == ["a", "b"]


def test_filter_new_prefix_must_match_exactly():
    # A line in the archive that happens to *contain* the id but with a
    # different extractor prefix must NOT be treated as archived.
    archived = {"vimeo abc123"}
    assert filter_new(["abc123"], archived) == ["abc123"]


def test_read_archive_missing(tmp_path: Path):
    assert read_archive(tmp_path / "missing.txt") == set()


def test_read_archive_strips_blank_lines(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("youtube a\n\n  \nyoutube b\n")
    assert read_archive(p) == {"youtube a", "youtube b"}


def test_count_archived(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("youtube a\nyoutube b\n\n")
    assert count_archived(p) == 2


def test_total_archived(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x\ny\n")
    (tmp_path / "b.txt").write_text("z\n")
    assert total_archived(tmp_path) == 3


def test_total_archived_missing_dir(tmp_path: Path):
    assert total_archived(tmp_path / "nope") == 0


def test_archive_path_sanitizes(tmp_path: Path):
    assert archive_path(tmp_path, "foo/bar") == tmp_path / "foo_bar.txt"
