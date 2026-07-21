"""Guard against committing a real player's name.

This repository is public and the data is youth sports, so a real name reaching
a tracked file is the one defect the project cannot fix forward — git history
stays public even after the name is removed. The rule has always been written
down; it was still broken. Three real roster names sat in ``test_events.py`` and
``test_review.py`` from commit ``b33cc4b`` until a sweep during an unrelated bug
fix found them, having passed a code review on the way in. Prose does not
enforce itself, so this does.

**How it works, and why this way round.** The obvious check — grep the tracked
files for the names in ``rosters/`` — cannot be the main guard: ``rosters/`` is
gitignored, so it is absent in CI and absent for any contributor who has never
run a game. A check that silently does nothing where it matters most is a false
green. So the primary guard inverts it: every name-shaped string in a tracked
file must appear in ``SANCTIONED_PLACEHOLDER_NAMES`` below. That set is closed,
it lives in this repository, and it needs no roster to enforce.

The friction is deliberate. Pasting a real name in fails the suite; the only way
past is to add it to the list, which is a visible line in a diff that a reviewer
must consciously approve. That is exactly the moment the question "is this a
real name?" needs to be asked, and it is the moment that was missed before.

``test_no_real_roster_names_in_tracked_files`` adds a second, local-only pass
using the real roster when one is present. It catches the residual case the
allowlist cannot: a real name mistakenly *added* to the sanctioned set.
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Names the project has sanctioned as placeholders. Every one is invented.
#:
#: The canonical prose list lives in the documentation vault's ``AGENTS.md``;
#: this is the enforced copy, because the vault is local-only and never reaches
#: CI. The two have drifted — the repository legitimately needs more placeholders
#: than the prose list names, for example rosters long enough to exercise a
#: batting order and for deliberate OCR-garble fixtures.
#:
#: **Adding a name here is a security decision, not housekeeping.** Add one only
#: when you invented it. Never add a name that came out of a run, a roster, a
#: review report, or a video.
SANCTIONED_PLACEHOLDER_NAMES = frozenset(
    {
        # The documented core list.
        "Emma B.",
        "Olivia M.",
        "Maya R.",
        "Amelia V.",
        "Ava T.",
        "Sofia L.",
        "Riley S.",
        "Mia K.",
        "Charlotte P.",
        "Ella C.",
        "Abby W.",
        "Zoe H.",
        "Chloe N.",
        # Extra invented names for the example roster and team list, which need
        # a full lineup rather than a handful of names.
        "Chloe W.",
        "Stella H.",
        "Nora F.",
        "Grace N.",
        "Riley J.",
        "Zoe P.",
        "Luna Q.",
        # Deliberate misreads, used as OCR-garble fixtures. Each is a corruption
        # of a placeholder above, not of anyone real: "Amelea V." is "Amelia V."
        # with an i-to-e substitution, "Moya R." is "Maya R.".
        "Amelea V.",
        "Moya R.",
        # Generic stand-ins in non-roster contexts (config and label tests).
        "Jane S.",
        "Bobby S.",
    }
)

#: A roster display name: a given name followed by a surname initial, which is
#: the shape SidelineHD shows and the shape every real name in this project
#: takes. This is what leaked before.
_DISPLAY_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]{1,15} [A-Z]\.(?![a-zA-Z])")

#: Document furniture that happens to fit the pattern ("Appendix A.", "Item B.").
#: Not names, and not worth failing over.
_STRUCTURAL_WORDS = frozenset(
    {
        "Appendix",
        "Chapter",
        "Class",
        "Column",
        "Example",
        "Figure",
        "Item",
        "Note",
        "Option",
        "Part",
        "Phase",
        "Plan",
        "Section",
        "Step",
        "Table",
        "Type",
    }
)

_BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".pdf", ".zip"})


def _tracked_files() -> list[Path]:
    """Every file git tracks — precisely the set that is public."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "cannot list tracked files; run the suite from a git checkout so the "
            f"name-safety guard can do its job (git said: {result.stderr.strip()})"
        )
    names = [name for name in result.stdout.split("\0") if name]
    assert names, "git reported no tracked files"
    return [REPO_ROOT / name for name in names]


def _readable_tracked_files() -> list[Path]:
    return [
        path
        for path in _tracked_files()
        if path.suffix.lower() not in _BINARY_SUFFIXES and path.is_file()
    ]


def _found_display_names(include_this_module: bool = True) -> dict[str, set[str]]:
    """Map each display-name-shaped string to the files it appears in.

    Once this module is committed it becomes a tracked file that spells out
    every sanctioned name, so counting it as a *usage* would make the
    unused-name check vacuous. It is still scanned for the leak checks, because
    a real name mistakenly added to the sanctioned set has to be catchable.
    """

    this_module = Path(__file__).resolve()
    found: dict[str, set[str]] = {}
    for path in _readable_tracked_files():
        if not include_this_module and path.resolve() == this_module:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for match in _DISPLAY_NAME_PATTERN.finditer(text):
            name = match.group(0)
            if name.split(" ", 1)[0] in _STRUCTURAL_WORDS:
                continue
            found.setdefault(name, set()).add(str(path.relative_to(REPO_ROOT)))
    return found


def test_tracked_files_use_only_sanctioned_placeholder_names():
    """No name may reach a tracked file unless it was invented for this repo."""

    found = _found_display_names()
    unsanctioned = {
        name: sorted(paths)
        for name, paths in found.items()
        if name not in SANCTIONED_PLACEHOLDER_NAMES
    }

    assert not unsanctioned, (
        "Unsanctioned player-style name(s) in tracked files:\n"
        + "\n".join(f"  {name!r} in {', '.join(paths)}" for name, paths in sorted(unsanctioned.items()))
        + "\n\nIf this is a real person's name, remove it — this repository is public "
        "and its history cannot be cleaned. Use a name from "
        "SANCTIONED_PLACEHOLDER_NAMES in tests/test_name_safety.py. If you invented "
        "the name yourself, add it to that set in the same commit."
    )


def test_sanctioned_names_are_all_still_used():
    """Keep the sanctioned set honest.

    An allowlist nobody prunes stops being a considered list and becomes a place
    names accumulate. If an entry is unused, delete it rather than leaving a
    standing permission for a name no test needs.
    """

    found = set(_found_display_names(include_this_module=False))
    unused = {name for name in SANCTIONED_PLACEHOLDER_NAMES if name not in found}

    assert not unused, (
        "Sanctioned placeholder name(s) no longer used anywhere: "
        f"{sorted(unused)}. Remove them from SANCTIONED_PLACEHOLDER_NAMES."
    )


def _real_roster_entries() -> list[tuple[str, str]]:
    """Every (number, name-form) in the local rosters, if any exist.

    ``rosters/`` is gitignored, so this returns nothing in CI and nothing for a
    contributor who has never processed a game.
    """

    roster_dir = REPO_ROOT / "rosters"
    if not roster_dir.is_dir():
        return []
    entries: list[tuple[str, str]] = []
    for path in sorted(roster_dir.glob("*.csv")):
        try:
            rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        except (UnicodeDecodeError, OSError, csv.Error):
            continue
        for row in rows:
            number = (row.get("number") or "?").strip()
            for field in ("full_name", "display_name", "preferred_name", "aliases"):
                for value in (row.get(field) or "").split(","):
                    value = value.strip()
                    if len(value) >= 3:
                        entries.append((number, value))
    return entries


def test_no_real_roster_names_in_tracked_files():
    """Local backstop: a real name must not appear even if it was allowlisted.

    Unlike the guard above this one sees the actual roster, so it also catches
    bare given names and aliases, not just the display form. Failures
    report the jersey number rather than the name — there is no reason to copy a
    real name into a terminal, a log, or a CI transcript.
    """

    entries = _real_roster_entries()
    if not entries:
        pytest.skip("no local rosters/*.csv to check against (expected in CI)")

    leaks: set[tuple[str, str]] = set()
    for path in _readable_tracked_files():
        # This module is scanned like any other: a real name wrongly added to
        # SANCTIONED_PLACEHOLDER_NAMES is precisely what this pass exists to catch.
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, value in entries:
            if re.search(rf"\b{re.escape(value)}(?![a-zA-Z])", text):
                leaks.add((str(path.relative_to(REPO_ROOT)), number))

    assert not leaks, (
        "Real roster name(s) found in tracked files — jersey numbers shown, not names:\n"
        + "\n".join(f"  {path}: roster #{number}" for path, number in sorted(leaks))
        + "\n\nReplace with a name from SANCTIONED_PLACEHOLDER_NAMES."
    )
