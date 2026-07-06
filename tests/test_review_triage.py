"""Tests for item 58: review-flag triage tiers and plain-language explanations."""

from __future__ import annotations

import pytest

from sidelinehd_extractor.models import Event, EventType
from sidelinehd_extractor.review import ReviewRow
from sidelinehd_extractor.review_triage import (
    TIER_INFORMATIONAL,
    TIER_NEEDS_ACTION,
    TIER_REVIEW,
    explain_flag,
    flag_tier,
    split_flag,
    summarize_triage,
    triage_review_rows,
)


@pytest.mark.parametrize(
    ("raw", "expected_tier"),
    [
        # needs-action: the tool could not resolve these itself.
        ("missing-player", TIER_NEEDS_ACTION),
        ("unrostered-card-number=15", TIER_NEEDS_ACTION),
        ("garbled-card-name", TIER_NEEDS_ACTION),
        ("ocr-number=28", TIER_NEEDS_ACTION),
        # review: resolved ambiguity, glance advised.
        ("card-vs-lineup=batter_card=12 lineup=2", TIER_REVIEW),
        ("lineup-had-rostered-candidate=22", TIER_REVIEW),
        ("close-at-bat=30s", TIER_REVIEW),
        ("repeat-player=90s", TIER_REVIEW),
        ("close-chapter=120s", TIER_REVIEW),
        ("inferred-missing", TIER_REVIEW),
        ("out-of-order-candidate", TIER_REVIEW),
        # informational: normal/success signals.
        ("possible-substitute", TIER_INFORMATIONAL),
        ("lineup-recovered", TIER_INFORMATIONAL),
    ],
)
def test_every_known_flag_maps_to_its_tier(raw, expected_tier):
    assert flag_tier(raw) == expected_tier


def test_split_flag_separates_value():
    assert split_flag("ocr-number=28") == ("ocr-number", "28")
    assert split_flag("missing-player") == ("missing-player", None)
    # Only the first "=" splits; the rest is payload.
    assert split_flag("card-vs-lineup=batter_card=12 lineup=2") == (
        "card-vs-lineup",
        "batter_card=12 lineup=2",
    )


def test_explanations_speak_plain_language_with_detail():
    explanation = explain_flag("unrostered-card-number=15")
    assert explanation.title == "Jersey #15 isn't on your roster"
    assert explanation.raw == "unrostered-card-number=15"
    assert "roster" in explanation.action
    # No raw flag=value jargon in the words a coach reads.
    for text in (explanation.title, explanation.meaning, explanation.action):
        assert "=" not in text

    substitute = explain_flag("possible-substitute")
    assert substitute.title == "Batting order jumped"
    assert "substitute" in substitute.meaning


def test_every_known_flag_has_nonempty_plain_language():
    from sidelinehd_extractor.review_triage import _EXPLANATIONS

    for flag in _EXPLANATIONS:
        explanation = explain_flag(flag)
        assert explanation.title and explanation.meaning and explanation.action
        assert flag not in explanation.title or " " in explanation.title


def test_unknown_flag_defaults_to_review_and_stays_visible():
    explanation = explain_flag("brand-new-flag=7")
    assert explanation.tier == TIER_REVIEW
    assert "brand-new-flag" in explanation.title
    assert explanation.detail == "7"


def _row(index, flags):
    event = Event(EventType.AT_BAT_START, 100.0 * index, f"#{index}")
    return ReviewRow(index=index, event=event, flags=flags)


def test_triage_rows_take_most_urgent_tier_and_filter_informational():
    rows = triage_review_rows(
        [
            _row(1, ["lineup-recovered", "ocr-number=28"]),
            _row(2, ["possible-substitute"]),
            _row(3, []),
            _row(4, ["close-at-bat=30s"]),
        ]
    )
    assert [row.tier for row in rows] == [
        TIER_NEEDS_ACTION,
        TIER_INFORMATIONAL,
        None,
        TIER_REVIEW,
    ]
    assert [row.needs_attention for row in rows] == [True, False, False, True]
    # Informational flags are collapsed out of the default (attention) view
    # but never deleted.
    mixed = rows[0]
    assert [item.flag for item in mixed.attention_explanations] == ["ocr-number"]
    assert [item.flag for item in mixed.explanations] == ["lineup-recovered", "ocr-number"]


def test_summarize_triage_counts_for_the_glance_line():
    rows = triage_review_rows(
        [
            _row(1, ["missing-player"]),
            _row(2, ["possible-substitute"]),
            _row(3, ["lineup-recovered"]),
            _row(4, []),
            _row(5, ["repeat-player=60s", "possible-substitute"]),
        ]
    )
    summary = summarize_triage(rows)
    assert summary == {
        "total": 5,
        "attention": 2,  # rows 1 and 5
        "fine": 3,  # informational-only rows count as fine
        "informational_only": 2,  # rows 2 and 3
    }
