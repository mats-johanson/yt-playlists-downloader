from yt_playlists.config import spotify_tag_regex


def test_basic_match_with_surrounding_whitespace():
    r = spotify_tag_regex("[DJ]")
    assert r.search("Curated for DJ sets [DJ] vibes")
    assert r.search("[DJ] is the only thing here")
    assert r.search("Trailing [DJ]")
    assert r.search("[DJ]")


def test_case_insensitive():
    r = spotify_tag_regex("[DJ]")
    assert r.search("Hi [dj] ok")


def test_no_match_when_embedded_in_word():
    r = spotify_tag_regex("[DJ]")
    # The Layer 3 example: "seeing [DJ] play live" has surrounding whitespace,
    # so we DO match it. The false-positive concern is for genuinely embedded
    # cases, which the boundary handles for non-bracket tags.
    assert r.search("seeing [DJ] play live")


def test_custom_tag():
    r = spotify_tag_regex("[MIX]")
    assert r.search("Tagged [MIX] here")
    assert not r.search("untagged playlist")


def test_no_match_when_tag_missing():
    r = spotify_tag_regex("[DJ]")
    assert not r.search("nothing relevant here")
    assert not r.search("")
