"""Triage review flags into action tiers with plain-language explanations.

Item 58: the review/game page flagged nearly every at-bat with raw
``flag=value`` strings, burying the few exceptions that actually need a
human. This module maps each flag from ``review.py`` to an action tier —

- ``needs-action``: the tool could NOT resolve something; the user should fix it.
- ``review``: the tool resolved an ambiguity; a glance is advised.
- ``informational``: normal operation or a success signal; usually ignore.

— and to a human title + one-line meaning + recommended action. The review
CSV and ``review_report.md`` are unchanged; this is a presentation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from sidelinehd_extractor.review import ReviewRow

TIER_NEEDS_ACTION = "needs-action"
TIER_REVIEW = "review"
TIER_INFORMATIONAL = "informational"

#: Ordered most- to least-urgent; a row's tier is its most urgent flag's tier.
TIER_ORDER = (TIER_NEEDS_ACTION, TIER_REVIEW, TIER_INFORMATIONAL)


@dataclass(frozen=True)
class FlagExplanation:
    """One raw review flag translated for a non-technical reader."""

    raw: str
    flag: str
    detail: Optional[str]
    tier: str
    title: str
    meaning: str
    action: str


#: ``flag -> (tier, title, meaning, action)``. ``{detail}`` is replaced with
#: the flag's ``=value`` part where that value reads cleanly on its own (a
#: jersey number or a duration); messier payloads (e.g. card-vs-lineup's
#: ``batter_card=12 lineup=2``) stay tooltip-only so the default view has no
#: raw jargon.
_EXPLANATIONS = {
    # needs-action: the tool could not resolve this itself.
    "missing-player": (
        TIER_NEEDS_ACTION,
        "Batter not identified",
        "The scoreboard didn't show a readable name or jersey number for this at-bat.",
        "Fill in the player number, or delete the play if it isn't a real at-bat.",
    ),
    "unrostered-card-number": (
        TIER_NEEDS_ACTION,
        "Jersey #{detail} isn't on your roster",
        "The batter card showed a number that doesn't match anyone on your roster.",
        "Add the number to your roster, or correct the player number here.",
    ),
    "garbled-card-name": (
        TIER_NEEDS_ACTION,
        "Couldn't read the batter's name",
        "The name on the batter card came through as unreadable text.",
        "Check the video at this time and fix the player name if it's wrong.",
    ),
    "ocr-number": (
        TIER_NEEDS_ACTION,
        "Scoreboard shows #{detail}, tool picked a different number",
        "The scoreboard read one number but the tool assigned another and couldn't "
        "confirm either against your roster.",
        "Check the video and correct the player number if the tool chose wrong.",
    ),
    # review: the tool resolved an ambiguity; a glance is advised.
    "card-vs-lineup": (
        TIER_REVIEW,
        "Two scoreboard readings disagreed",
        "The batter card and the lineup strip showed different numbers; the tool "
        "picked the more reliable one.",
        "Only check the video if this batter looks wrong.",
    ),
    "lineup-had-rostered-candidate": (
        TIER_REVIEW,
        "Lineup hinted at jersey #{detail}",
        "The lineup strip contained a rostered number the tool didn't use.",
        "Double-check this batter if the name looks wrong.",
    ),
    "close-at-bat": (
        TIER_REVIEW,
        "At-bats very close together",
        "This at-bat started only {detail} after the previous one, so one of them "
        "might be a duplicate.",
        "Check the video; delete the duplicate play if there is one.",
    ),
    "repeat-player": (
        TIER_REVIEW,
        "Same batter twice in a row",
        "The same jersey number batted again within {detail} — this could be a "
        "re-read of the same at-bat.",
        "Delete this play if it's a duplicate of the previous one.",
    ),
    "close-chapter": (
        TIER_REVIEW,
        "Innings very close together",
        "This inning marker came only {detail} after the previous one, so one may "
        "be a false detection.",
        "Check the video; delete the extra inning marker if needed.",
    ),
    "inferred-missing": (
        TIER_REVIEW,
        "Missed at-bat filled in",
        "The batting order implied an at-bat the scoreboard never showed, so the "
        "tool added it with an estimated time.",
        "Glance at the video around this time to confirm the timestamp.",
    ),
    "out-of-order-candidate": (
        TIER_REVIEW,
        "Unexpected batting order",
        "This batter appeared outside the expected order and the tool couldn't "
        "explain it as a substitution.",
        "Check the batter number against the video.",
    ),
    # informational: normal/success — usually ignore.
    "possible-substitute": (
        TIER_INFORMATIONAL,
        "Batting order jumped",
        "This batter wasn't in the expected batting order — normal when a "
        "substitute enters the game.",
        "Only check if the batter looks wrong.",
    ),
    "lineup-recovered": (
        TIER_INFORMATIONAL,
        "Identified from the lineup strip",
        "The batter card was unreadable, so the tool identified this batter from "
        "the lineup strip instead. This worked as designed.",
        "No action needed.",
    ),
}


def split_flag(raw: str) -> tuple:
    """Split ``"flag=value"`` into ``(flag, value-or-None)``."""

    flag, separator, detail = raw.partition("=")
    return flag, (detail if separator else None)


def explain_flag(raw: str) -> FlagExplanation:
    """Translate one raw flag string. Unknown flags surface as ``review``.

    A flag added to ``review.py`` before this table learns about it must stay
    visible — defaulting it to the middle tier shows it without shouting.
    """

    flag, detail = split_flag(raw)
    entry = _EXPLANATIONS.get(flag)
    if entry is None:
        return FlagExplanation(
            raw=raw,
            flag=flag,
            detail=detail,
            tier=TIER_REVIEW,
            title=f"Check this play ({flag})",
            meaning="The tool flagged this play for a reason it can't explain in "
            "plain language yet.",
            action="Check the play against the video.",
        )
    tier, title, meaning, action = entry
    substitution = detail if detail is not None else "?"
    return FlagExplanation(
        raw=raw,
        flag=flag,
        detail=detail,
        tier=tier,
        title=title.replace("{detail}", substitution),
        meaning=meaning.replace("{detail}", substitution),
        action=action,
    )


def flag_tier(raw: str) -> str:
    return explain_flag(raw).tier


@dataclass(frozen=True)
class TriagedRow:
    """A ReviewRow plus its translated flags and overall tier."""

    index: int
    event: object
    flags: List[str]
    explanations: List[FlagExplanation]
    tier: Optional[str]  # None when the row has no flags

    @property
    def needs_attention(self) -> bool:
        """True when at least one flag is action-worthy (not informational)."""

        return self.tier in (TIER_NEEDS_ACTION, TIER_REVIEW)

    @property
    def attention_explanations(self) -> List[FlagExplanation]:
        return [item for item in self.explanations if item.tier != TIER_INFORMATIONAL]


def triage_review_rows(rows: Sequence[ReviewRow]) -> List[TriagedRow]:
    """Attach explanations + a most-urgent tier to each review row."""

    triaged = []
    for row in rows:
        explanations = [explain_flag(raw) for raw in row.flags]
        tiers = {item.tier for item in explanations}
        tier = next((candidate for candidate in TIER_ORDER if candidate in tiers), None)
        triaged.append(
            TriagedRow(
                index=row.index,
                event=row.event,
                flags=list(row.flags),
                explanations=explanations,
                tier=tier,
            )
        )
    return triaged


def summarize_triage(rows: Iterable[TriagedRow]) -> dict:
    """Counts for the at-a-glance summary line.

    ``fine`` counts plays that need no human action: unflagged plays plus
    plays whose only flags are informational.
    """

    rows = list(rows)
    attention = sum(1 for row in rows if row.needs_attention)
    informational_only = sum(
        1 for row in rows if row.tier == TIER_INFORMATIONAL
    )
    return {
        "total": len(rows),
        "attention": attention,
        "fine": len(rows) - attention,
        "informational_only": informational_only,
    }
