"""Spotify track → YouTube video resolution.

Split into:
- `score(track, candidates) -> Match | NoMatch`  — pure function; testable
                                                   with fixture data.
- `resolve(track, search_fn) -> ResolvedTrack | Unmatched` — thin I/O wrapper.

Signal set ported from spotDL (artist similarity, exponential duration decay,
forbidden-words penalty for live/cover/karaoke/instrumental/remix when not
in the original title, explicit-flag mismatch penalty).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from . import config
from .tracks import ResolvedTrack, SpotifyTrackMeta, Unmatched

# Unicode letter (any script) + decimal digit. Matches Cyrillic, Estonian õäöü,
# CJK, etc. The earlier [a-z0-9]+ silently dropped non-Latin scripts entirely.
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_PARENTHETICAL_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_SUFFIX_DASH_RE = re.compile(r"\s+-\s+.*$")  # " - 2019 Remaster", " - Live", etc.


@dataclass(frozen=True)
class YtCandidate:
    """Flat search result fields. Matches what extract_flat='in_playlist' returns."""

    video_id: str
    title: str
    uploader: str | None = None
    duration_s: float | None = None


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def normalize_text(s: str) -> str:
    """Lowercase, strip accents/diacritics, keep underlying letters (incl. Cyrillic/CJK).

    Use NFKD to decompose accented letters into base+combining, then drop the
    combining marks (Unicode category Mn). Crucially do NOT `encode("ascii", "ignore")`
    — that wipes Cyrillic/Greek/CJK entirely, which is what caused tracks like
    `ЗОМБ — Даже не половина` to score 0 against any candidate.
    """
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower()


def tokens(s: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalize_text(s)))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def coverage(needle: set[str], haystack: set[str]) -> float:
    """Fraction of `needle` tokens present in `haystack`. Asymmetric on purpose:
    a candidate title with extra words (year, "Official Video") shouldn't penalize
    the match when the track's own tokens are fully present."""
    if not needle:
        return 0.0
    return len(needle & haystack) / len(needle)


def strip_for_search(title: str) -> str:
    """Spotify titles often carry `(Remastered)`, `- 2019 Mix` — strip for the
    YouTube search query (improves recall). Kept intact for scoring."""
    out = _PARENTHETICAL_RE.sub("", title)
    out = _SUFFIX_DASH_RE.sub("", out)
    return out.strip()


def build_search_query(track: SpotifyTrackMeta) -> str:
    return f"{track.artist} {strip_for_search(track.title)}".strip()


_ARTIST_SPLIT_RE = re.compile(r"\s*[,&]\s*|\s+(?:feat\.?|ft\.?|with)\s+", re.IGNORECASE)


def artist_similarity(track: SpotifyTrackMeta, candidate: YtCandidate) -> float:
    """For multi-artist tracks, take the MAX coverage across individual artists.

    Spotify often lists 2–5 collaborators in `artist`; YouTube titles typically
    credit only the primary (or the most-searchable) one. Averaging coverage
    across ALL token sets unfairly penalizes legitimate matches; we instead
    reward "any one credited artist is clearly present in the candidate".
    Falls back to the previous combined-tokens behaviour when the artist string
    doesn't split into multiples.
    """
    if not track.artist:
        return 0.0
    haystack = tokens(f"{candidate.uploader or ''} {candidate.title}")
    individual_artists = [a.strip() for a in _ARTIST_SPLIT_RE.split(track.artist) if a.strip()]
    if not individual_artists:
        return 0.0
    return max(coverage(tokens(a), haystack) for a in individual_artists)


def title_similarity(track: SpotifyTrackMeta, candidate: YtCandidate) -> float:
    """Coverage of track-title tokens in candidate title."""
    return coverage(tokens(track.title), tokens(candidate.title))


def duration_score(track: SpotifyTrackMeta, candidate: YtCandidate) -> float:
    """Exponential decay over seconds delta. 0s diff → 1.0; 10s diff → ~0.61."""
    if candidate.duration_s is None or track.duration_s <= 0:
        return 0.5  # neutral when unknown
    delta = abs(candidate.duration_s - track.duration_s)
    return math.exp(-config.MATCH_DURATION_DECAY_PER_SEC * delta)


def forbidden_penalty(track: SpotifyTrackMeta, candidate: YtCandidate) -> float:
    """Penalize candidates whose title contains words the original doesn't.

    E.g., a studio track matched to a 'Live' or 'Cover' video.
    """
    track_norm = normalize_text(track.title)
    cand_norm = normalize_text(candidate.title)
    penalty = 0.0
    for word in config.MATCH_FORBIDDEN_TOKENS:
        if word in cand_norm and word not in track_norm:
            penalty += config.MATCH_FORBIDDEN_PENALTY
    return penalty


@dataclass(frozen=True)
class _Score:
    candidate: YtCandidate
    score: float
    artist_sim: float
    title_sim: float
    duration_sim: float
    penalty: float


def score_candidate(track: SpotifyTrackMeta, candidate: YtCandidate) -> _Score:
    """Combine signals into a 0..100 score."""
    a = artist_similarity(track, candidate)
    t = title_similarity(track, candidate)
    d = duration_score(track, candidate)
    base = 40 * a + 30 * t + 30 * d
    penalty = forbidden_penalty(track, candidate)
    return _Score(candidate, base - penalty, a, t, d, penalty)


def score(
    track: SpotifyTrackMeta, candidates: list[YtCandidate]
) -> tuple[_Score | None, list[_Score]]:
    """Return (best, all_ranked). best is None if no candidate clears the bar."""
    if not candidates:
        return None, []
    ranked = sorted(
        (score_candidate(track, c) for c in candidates),
        key=lambda s: s.score,
        reverse=True,
    )
    best = ranked[0]
    if best.score < config.MATCH_THRESHOLD:
        return None, ranked
    if best.artist_sim < config.MATCH_ARTIST_MIN_SIMILARITY:
        return None, ranked
    return best, ranked


# ---------------------------------------------------------------------------
# I/O wrapper
# ---------------------------------------------------------------------------

SearchFn = Callable[[str, int], list[YtCandidate]]


def resolve(
    track: SpotifyTrackMeta,
    search_fn: SearchFn,
) -> ResolvedTrack | Unmatched:
    """Search YouTube for `track`, score, decide.

    `search_fn(query, n_candidates) -> list[YtCandidate]` is injected so tests
    can supply fixture data.
    """
    query = build_search_query(track)
    candidates = search_fn(query, config.YT_SEARCH_CANDIDATES)
    best, ranked = score(track, candidates)

    if best is None:
        # If we have ANY candidate, surface the top one as a starting suggestion
        # the user can override.
        top = ranked[0].candidate.video_id if ranked else None
        top_score = ranked[0].score if ranked else 0.0
        return Unmatched(
            spotify=track,
            best_candidate_video_id=top,
            best_score=top_score,
            reason=f"below threshold (best score {top_score:.1f} < {config.MATCH_THRESHOLD})",
        )

    return ResolvedTrack(
        youtube_video_id=best.candidate.video_id,
        spotify=track,
        match_score=best.score,
        match_reason=(
            f"matched artist_sim={best.artist_sim:.2f} title_sim={best.title_sim:.2f} "
            f"duration_sim={best.duration_sim:.2f} penalty={best.penalty:.1f}"
        ),
    )
