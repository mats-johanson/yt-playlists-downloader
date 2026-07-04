"""Tests for `UnavailableTracker`'s per-run and persistent state."""

from yt_playlists.unavailable import UnavailableTracker


def test_per_run_unavailable_recorded(tmp_path):
    tr = UnavailableTracker(tmp_path / "unavail.txt")
    tr.record_error("MyPlaylist", "[youtube] abc12345: Video unavailable in your region")
    assert len(tr.entries()) == 1
    assert tr.count_for("MyPlaylist") == 1


def test_bot_block_phrases_recorded(tmp_path):
    tr = UnavailableTracker(tmp_path / "unavail.txt")
    tr.record_error("MyPlaylist", "Sign in to confirm you're not a bot")
    assert tr.is_bot_blocked("MyPlaylist")
    assert tr.any_bot_blocked()


def test_reset_run_state_clears_per_run_only(tmp_path):
    dead = tmp_path / "dead.txt"
    tr = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    tr.record_error(
        "P",
        "[youtube] DEAD12345: Video unavailable. This video is no longer "
        "available because the YouTube account associated with this video "
        "has been terminated.",
    )
    assert tr.is_known_dead("DEAD12345")
    assert tr.count_for("P") == 1

    tr.reset_run_state()
    assert tr.count_for("P") == 0
    # Persistent dead-list survives reset.
    assert tr.is_known_dead("DEAD12345")


def test_dead_list_persists_across_instances(tmp_path):
    dead = tmp_path / "dead.txt"
    tr1 = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    tr1.record_error(
        "P",
        "[youtube] DEAD12345: Video unavailable. This video is no longer "
        "available due to a copyright claim by [Merlin] K7 Records",
    )
    assert tr1.is_known_dead("DEAD12345")

    # Fresh instance reads the same persistent file.
    tr2 = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    assert tr2.is_known_dead("DEAD12345")


def test_dead_list_uniques_not_duplicated(tmp_path):
    dead = tmp_path / "dead.txt"
    tr = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    for _ in range(3):
        tr.record_error(
            "P",
            "[youtube] SAME1234: Video unavailable. The YouTube account "
            "associated with this video has been terminated.",
        )
    assert dead.read_text().count("SAME1234") == 1


def test_transient_unavailable_not_marked_dead(tmp_path):
    """A bare 'Video unavailable' without a permanent-failure phrase should
    NOT land in the persistent dead-list — could still be a transient issue.
    """
    dead = tmp_path / "dead.txt"
    tr = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    tr.record_error("P", "[youtube] MAYBE12345: Video unavailable")
    assert not tr.is_known_dead("MAYBE12345")
    assert not dead.exists() or dead.read_text() == ""


def test_bare_403_circuit_breaks_run_not_marks_dead(tmp_path):
    """An HTTP 403 on the video data fetch means YT is rate-limiting OUR client.
    The video is fine; we just need to stop hammering. The dead-list must NOT
    grow on a 403 (the video isn't dead), but bot-block circuit MUST trip so
    we don't deepen the rate-limit hole.
    """
    dead = tmp_path / "dead.txt"
    tr = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    tr.record_error(
        "MyPlaylist",
        "[youtube] LIVE12345: ERROR: unable to download video data: "
        "HTTP Error 403: Forbidden",
    )
    assert tr.any_bot_blocked()
    assert tr.is_bot_blocked("MyPlaylist")
    assert not tr.is_known_dead("LIVE12345")
    assert not dead.exists() or dead.read_text() == ""


def test_known_dead_returns_false_for_unrelated(tmp_path):
    tr = UnavailableTracker(tmp_path / "unavail.txt")
    assert not tr.is_known_dead("LiveVidId")


def test_dead_file_comments_ignored(tmp_path):
    dead = tmp_path / "dead.txt"
    dead.write_text("# manually added\nDEAD12345\n\n# trailing\nDEAD67890\n")
    tr = UnavailableTracker(tmp_path / "unavail.txt", dead_videos_file=dead)
    assert tr.is_known_dead("DEAD12345")
    assert tr.is_known_dead("DEAD67890")
