from yt_playlists.archive import filter_new, sanitize_name


def test_sanitize_strips_windows_reserved_chars():
    assert sanitize_name("foo/bar") == "foo_bar"
    assert sanitize_name("foo\\bar") == "foo_bar"
    assert sanitize_name("file:name") == "file_name"
    assert sanitize_name("a?b*c") == "a_b_c"
    assert sanitize_name('"quoted"') == "_quoted_"
    assert sanitize_name("a<b>c|d") == "a_b_c_d"


def test_sanitize_preserves_safe_chars():
    assert sanitize_name("Top 100 Daily") == "Top 100 Daily"
    assert sanitize_name("Lõpulood") == "Lõpulood"


def test_filter_new_uses_extractor_prefix():
    archived = {"youtube abc123", "youtubemusic def456"}
    # default extractor "youtube"
    assert filter_new(["abc123", "xyz789", "def456"], archived) == ["xyz789", "def456"]
    # explicit "youtubemusic"
    assert filter_new(["abc123", "def456"], archived, extractor="youtubemusic") == ["abc123"]
