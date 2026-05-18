from yt_playlists.outcomes import OutcomeReason, PlaylistOutcome


def test_done_is_not_failed():
    o = PlaylistOutcome(name="x", songs_done=3, reason=OutcomeReason.DONE)
    assert not o.failed


def test_empty_is_not_failed():
    # EMPTY means "scan saw new ids, downloader produced 0" — usually because
    # the videos are now unavailable. Informational, not a script failure.
    o = PlaylistOutcome(name="x", songs_done=0, reason=OutcomeReason.EMPTY)
    assert not o.failed


def test_real_failures_are_marked_failed():
    for r in (OutcomeReason.BOT_BLOCKED, OutcomeReason.ERROR):
        assert PlaylistOutcome(name="x", songs_done=0, reason=r).failed
