"""Guard tests for the development-checks contract — the README half, and
(CR-103) the ``pyproject.toml`` half that decides what those checks actually run.

The suite mixes ``unittest.TestCase`` classes with pytest fixture and
function-style tests, so ``unittest discover`` silently collects only part of
it and skips the entire web-app surface. A README that prescribes it hands a
contributor a false green: they run it, see green, and ship a web-app
regression that the skipped tests would have caught. CI runs the full suite
under pytest, so nothing catches the drift — it is the *local* signal that
lies, and only a check on the README text can notice it.

The lint half failed the same way from the other direction. ``ruff`` was
declared as a floor, so CI resolved a newer release than the implementer had
and linted against a different rule set — the step was red on every leg for
twelve pushes, which meant a *real* lint regression could no longer be seen.
Both halves are guarded here as text, not by importing a TOML parser: 3.10 has
no ``tomllib``, and the surrounding suite already reads these files as text.

CR-106 adds the third half, which is the same drift seen from inside a source
file: an in-file suppression naming a rule the declared set does not enable
suppresses nothing, while reading to every future maintainer as though it does.
That is a documentation defect rather than a lint one — nothing goes red either
way — so it needs a text check too. CR-107 made that check read every code in a
directive rather than only the first, and CR-108 pointed it at the other place
the defect had been sitting all along: seven broad-except sites in ``src/``.

CR-109 finishes the thread. The check now reads every spelling ruff honours,
and it is pointed at **every tracked module** rather than at a named list of
files. That general form was deliberately held back through the last two
changes: it was red while the ten inert directives survived, and the two ways
to green it — fixing them from inside an unrelated diff, or naming them as
exceptions in the guard — were both worse than waiting. With the sweep at zero
there is nothing left to except, so the invariant can finally be stated in the
shape it was always meant to have.
"""

from __future__ import annotations

import re
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
README = _REPO_ROOT / "README.md"
PYPROJECT = _REPO_ROOT / "pyproject.toml"
LIFECYCLE_TESTS = _REPO_ROOT / "tests" / "test_webapp_lifecycle.py"


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def _development_checks_section(text: str) -> str:
    """The '## Development Checks' section, up to the next top-level heading."""
    marker = "\n## Development Checks\n"
    start = text.index(marker) + len(marker)
    rest = text[start:]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def _fenced_commands(text: str) -> list[str]:
    """Every line inside a ``` fenced block — the lines a reader runs."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            lines.append(line)
    return lines


def test_readme_never_instructs_unittest_discover() -> None:
    # Prose may name it to warn against it; a runnable line must never be it.
    offenders = [line for line in _fenced_commands(_readme_text()) if "unittest" in line]
    assert offenders == []


def test_development_checks_prescribes_pytest_and_ruff() -> None:
    section = _development_checks_section(_readme_text())
    assert "python -m pytest tests/" in section
    assert "python -m ruff check ." in section


def test_development_checks_installs_the_web_extra_with_dev() -> None:
    # The web-app test modules import fastapi/uvicorn at module scope, so a
    # dev-only install cannot collect them — the same skip by another route.
    section = _development_checks_section(_readme_text())
    assert '".[dev,web]"' in section


# --- The lint contract (CR-103) ----------------------------------------------


def _dev_extra(text: str) -> str:
    """The ``dev = [...]`` array of ``[project.optional-dependencies]``."""
    rest = text[text.index("\ndev = [") :]
    return rest[: rest.index("]") + 1]


def _select_array(text: str) -> str:
    """The ``select = [...]`` array under ``[tool.ruff.lint]``."""
    lint = text[text.index("[tool.ruff.lint]") :]
    rest = lint[lint.index("select = [") :]
    return rest[: rest.index("]") + 1]


def test_ruff_is_pinned_exactly_so_ci_lints_what_the_implementer_linted() -> None:
    """CR-103. ``ruff>=0.4`` let CI resolve 0.16.0 against a local 0.15.20, and
    the two disagreed completely — 968 errors there, clean here, on code no one
    had touched. The cost was never the 968: it was that a genuine lint
    regression became invisible, because the step that would turn red already
    was. A floor cannot express "the same version"; only a pin can."""

    requirements = [
        line.strip() for line in _dev_extra(_pyproject_text()).splitlines()
        if "ruff" in line
    ]
    assert len(requirements) == 1, requirements
    assert requirements[0].startswith('"ruff=='), (
        f"ruff must be pinned exactly, not floored — found {requirements[0]}"
    )


def test_the_lint_rule_set_is_declared_rather_than_inherited() -> None:
    """CR-103's other half, and the one that survives a version bump. With the
    rules named here, upgrading ``ruff`` changes what is linted only when
    someone edits this list; without it, the upgrade silently redefines the
    gate — which is precisely how 968 errors appeared against unchanged code."""

    select = _select_array(_pyproject_text())
    # E4 has to stay selected: four E402 suppressions in test_desktop.py and
    # test_updates.py answer real violations today, and dropping E4 would
    # render them inert with nothing going red to say so. (Spelled without the
    # directive's own prefix — ruff scans comments for it and warns on the
    # prose form.)
    assert '"E4"' in select
    assert '"F"' in select


def test_the_pin_names_the_ruff_that_is_actually_installed() -> None:
    """The two tests above check the *shape* of the contract; this one checks
    the thing the contract is for. A pin that has drifted from the interpreter
    running the suite puts the implementer back where CR-103 found them —
    reporting "ruff clean" about a version CI will not use. Skipped when the
    dev extra is not installed, which is the one honest reason to have no
    opinion; a `pip install -e ".[dev,web]"` always produces the pin."""

    try:
        installed = version("ruff")
    except PackageNotFoundError:
        pytest.skip("the dev extra is not installed")
    assert f'"ruff=={installed}"' in _dev_extra(_pyproject_text()), (
        f"pyproject pins a different ruff than the {installed} installed here"
    )


# --- Suppressions must name a rule the declared set enables (CR-106) ---------

# The `_FakeKernel32` methods that mirror Win32 names, and so break the
# pep8-naming convention deliberately.
_WIN32_STUB_METHODS = ("OpenProcess", "GetExitCodeProcess", "CloseHandle")

# Assembled from parts rather than written out: ruff scans comments for its own
# directive, so spelling it here would turn this line into one.
#
# CR-107: the code list is matched whole and split afterwards, rather than
# captured one code at a time. Capturing a single code inspected only the
# *first* of a multi-code directive, so an inert code hiding behind an enabled
# one — `E402, N802` — passed the guard while violating the property it claims.
# The list is optional so the bare, code-less form matches too and can be
# failed explicitly instead of falling through as "nothing to check".
#
# The separator is comma *or* whitespace because ruff honours both: measured
# against 0.15.20, `E402 F401` spelled with a space suppresses each of them
# exactly as the comma form does. A comma-only pattern would therefore reopen
# the same hole in a different spelling.
#
# CR-109 adds the last two shapes ruff reads and this pattern could not. Each
# clause below was measured against the pinned 0.15.20 on a scratch project
# carrying a real E402 and a real F401, not read off the documentation:
#
#   * `re.IGNORECASE`, because the directive token is case-insensitive —
#     `NOQA` and `NoQa` suppress exactly as the lowercase form does.
#   * the optional `ruff:` / `flake8:` qualifier, because that is the
#     *file-level* blanket: one such comment silences every rule in the module,
#     which is strictly worse than the line-level blanket CR-107 closed. Both
#     spellings are honoured identically, and with or without whitespace around
#     the colon.
#
# CR-110: the file-level form is honoured **only when the comment stands on its
# own line** — that is, when nothing but whitespace precedes the `#`. Position
# is therefore part of the spelling, and the table below carries it. Measured on
# 0.15.20 against the same scratch module (3 diagnostics with no directive):
#
#   own line, at the top, at the foot, or indented inside a function
#                                 `ruff: ⟨token⟩`        -> 0, the whole file
#                                 `ruff: ⟨token⟩: E402`  -> 2, that rule file-wide
#   trailing on a line of code    either of the above    -> 3, and ruff warns:
#     "Unexpected `# ruff: ⟨token⟩` directive at ⟨file⟩:⟨line⟩. File-level
#      suppression comments must appear on their own line. For line-level
#      suppression, omit the `ruff:` prefix."
#
# It then lints the line anyway and still exits 0 on an otherwise clean tree, so
# the warning is the only thing distinguishing that comment from a real
# suppression — which is not something a reader of the source can see at all.
# (Ruff names the `ruff:` spelling in that warning even when the comment said
# `flake8:`; both are refused identically.)
#
# CR-111: the qualifier is matched in any casing, and its casing is then
# *judged*. Ruff honours the file-level prefix *only lower-cased*; every other
# capitalisation it ignores outright — and, unlike the refused trailing form
# above, it says nothing at all about it. Measured on 0.15.20 against the same
# scratch module, at the top, at the foot, indented inside a function, and
# trailing code alike; the position made no difference to any row:
#
#   `ruff: ⟨token⟩: E402`     -> 2, honoured file-wide (the lower-cased spelling)
#   `RUFF: ⟨TOKEN⟩: E402`     -> 3, and no warning of any kind
#   `Ruff: ⟨token⟩: E402`     -> 3, and no warning
#   `FLAKE8: ⟨token⟩: E402`   -> 3, and no warning
#   `ruff: ⟨TOKEN⟩: E402`     -> 2, honoured — the *token* is case-insensitive,
#                                so the qualifier is the one part of this
#                                spelling whose casing decides anything
#
# A capitalised qualifier is therefore inert in *every* position, and the guard
# rejects it on casing before it ever reaches the position rule above — whose
# message quotes a warning ruff does not emit for this form.
#
# This was got wrong once, and the way it was wrong is worth keeping: the text
# here used to say the upper-cased qualifier was "ignored by the linter
# entirely — in every position", which is true, and conclude that it was
# therefore already handled and could be "spelled safely" in the table below,
# which was not. Nothing in `_inert_suppression` judged the qualifier's casing
# at all. The two `RUFF: ⟨TOKEN⟩` rows reached the right verdict through the
# blanket rule, because they name no code — so they pinned nothing about
# casing, and a capitalised qualifier *with* a code was waved straight through.
# Being stricter than ruff here is still deliberate rather than sloppy — a
# comment the linter ignores while every human reader takes it for a
# suppression is the exact defect this guard is named for — but the strictness
# now lives in the helper, where it can fail, rather than in this paragraph.
#
# CR-112: position decides the *line-level* form too. A directive carrying no
# qualifier is applied by ruff to the line it sits on, so standing on its own
# line it suppresses nothing and the violation beneath it is reported anyway.
# Ruff emits no warning for this one either. The worry that had to be answered
# before asserting it was a false positive — a rule that failed this suite on
# legitimate code — so it was measured across every shape where "its own line"
# and "the logical line" come apart: a bracketed continuation (directive above,
# below, and first inside the brackets), a backslash continuation, a multi-line
# f-string, an implicitly concatenated string, and a multi-line signature. The
# f-string is the one that could have gone the other way, since ruff remaps the
# lookup for a diagnostic inside a string to its *closing* line — and even
# there the own-line directive was inert and only the one trailing the closing
# quotes was honoured. Across 25 shapes, 13 of them own-line, no directive
# standing on a comment-only line was honoured once; every trailing control in
# the same 25 was.
#
# The rule codes stay case-sensitive even under the flag — see
# `_inert_suppression`, which rejects a lower-cased code rather than folding it
# up. ruff refuses `# ⟨token⟩: e402` as an invalid directive and suppresses
# nothing, so treating it as a spelling of an enabled rule would wave through a
# line that is inert in precisely the way this guard exists to catch.
_SEPARATOR = r"[\s,]+"
_CODE = r"[A-Za-z]+[0-9]+"
_QUALIFIER = r"(?:ruff|flake8)\s*:\s*"
# CR-110. What precedes the `#` is captured, not skipped over, because the
# file-level form is honoured only when that prefix is empty or whitespace.
_SUPPRESSION = re.compile(
    r"(?P<before>.*?)#\s*(?P<qualifier>" + _QUALIFIER + r")?" + "noqa"
    + r"\b(?:\s*:\s*(?P<codes>" + _CODE + r"(?:" + _SEPARATOR + _CODE + r")*))?",
    re.IGNORECASE,
)


def _selected_prefixes(text: str) -> list[str]:
    """The rule prefixes named in ``[tool.ruff.lint] select``."""
    return re.findall(r'"([A-Z]+[0-9]*)"', _select_array(text))


def _inert_suppression(line: str, selected: list[str]) -> str | None:
    """Why ``line``'s suppression is inert, or ``None`` if it carries none.

    The shared form of the check (CR-108), so the rule lives in one place and
    every file pointed at it is judged the same way.

    A directive naming *no* code fails rather than being waved through: it can
    never name an enabled rule, and unlike a misnamed code it would also
    silence a real future violation — strictly the worse of the two. Since
    CR-109 that covers the file-level blanket as well, which silences a whole
    module rather than one line.

    CR-110 adds the one judgement that is about *position* rather than about
    what the directive names: a file-level directive trailing a line of code is
    inert whatever it names, because ruff refuses it there. CR-111 and CR-112
    complete that half of the check — the file-level prefix is read by ruff only
    lower-cased, and the line-level form is inert on its own line for the mirror
    reason the file-level form is inert off it.

    The order below is deliberate: everything that decides whether ruff reads
    the directive *at all* comes first, and only then what it names. A rule that
    fires on a line ruff never read would otherwise explain it with the wrong
    defect — and, in the position rule's case, with a quotation of a warning
    ruff does not emit for that spelling.
    """

    found = _SUPPRESSION.search(line)
    if found is None:
        return None
    qualifier = found.group("qualifier")
    before = found.group("before")
    # CR-111. Ruff reads the file-level prefix only lower-cased and ignores
    # every other capitalisation in silence — no warning, in any position — so
    # such a comment suppresses nothing wherever it sits. Judged ahead of the
    # position rule below, whose message quotes ruff's warning: ruff never
    # warns about this form, so reaching that message would attribute a real
    # quotation to a case ruff has never spoken about. The same shape as the
    # lower-cased-code rule further down — the pattern reads any casing so the
    # guard can *see* the line, and the helper is what judges it.
    if qualifier is not None and qualifier != qualifier.lower():
        return (
            f"`{qualifier.strip()}` is not a prefix ruff reads — it honours the "
            "file-level form only lower-cased and ignores every other "
            "capitalisation silently, without even the warning it gives the "
            "misplaced lower-cased form, so this line suppresses nothing in any "
            f"position: {line.strip()}"
        )
    # CR-110. A file-level directive is honoured only as the whole of a comment
    # standing on its own line. Trailing on a line of code, ruff refuses it with
    # a warning and lints the line anyway — so it reads to every human as a
    # suppression, and to a tree that still exits 0, while silencing nothing.
    # That is this guard's own definition of inert, arriving in the one shape
    # the guard was written to describe.
    if qualifier is not None and before.strip():
        qualifier = qualifier.strip()
        return (
            f"the `{qualifier}` prefix makes this a file-level suppression, and it "
            "trails code — ruff refuses it there and lints the line anyway, so it "
            'suppresses nothing. Ruff\'s own words: "File-level suppression '
            "comments must appear on their own line. For line-level suppression, "
            'omit the `ruff:` prefix." (It names the `ruff:` spelling in that '
            f"warning whichever of the two the comment used.) {line.strip()}"
        )
    # CR-112. The mirror of the rule above, for the form carrying no qualifier.
    # Ruff applies a line-level directive to the line it sits on; on a
    # comment-only line that is a line with no diagnostic on it, so the
    # violation underneath is reported regardless and the comment silences
    # nothing. Ruff gives no warning here at all, which makes it quieter than
    # the misplaced file-level form and invisible to everything but this guard.
    if qualifier is None and not before.strip():
        return (
            "a line-level directive standing on its own line suppresses nothing: "
            "ruff applies it to the line it sits on, and that line carries no "
            "violation to suppress — the one below it is reported anyway, without "
            f"a warning. Move it onto the line it is meant for: {line.strip()}"
        )
    codes = found.group("codes")
    if codes is None:
        return (
            "a blanket suppression names no rule, so it cannot name an enabled "
            f"one — and it would hide a real violation as well: {line.strip()}"
        )
    for code in re.split(_SEPARATOR, codes.strip()):
        # CR-109. The pattern is case-insensitive so it can read the directive
        # token in any casing, but ruff accepts only upper-case rule codes —
        # it reports a lower-cased one as an invalid directive and lints the
        # line anyway. Comparing `code.upper()` against the select would call
        # such a line enabled when it suppresses nothing, so the casing is
        # checked rather than normalised away.
        if code != code.upper():
            return (
                f"{code} is not a rule code ruff accepts — it reads a lower-cased "
                "code as an invalid directive and suppresses nothing, so this line "
                f"is inert whatever the select enables: {line.strip()}"
            )
        if not any(code.startswith(prefix) for prefix in selected):
            return (
                f"{code} is not enabled by select={selected}, so this suppression is "
                f"inert and only reads as though it matters: {line.strip()}"
            )
    return None


# CR-109, corrected by CR-110 and again by CR-111 and CR-112. Each row below was
# measured against the pinned 0.15.20 before it was written down here, on a
# scratch module carrying a real E402 and a real F401 — three diagnostics with
# no directive present at all.
#
# **A spelling is only true of a position** (CR-110). The file-level qualifier
# forms are honoured on their own line and refused trailing a line of code, so
# every row carries the position it was measured in and the test builds the line
# that way. Reading the table without the middle column is what produced the
# error this row set is a correction of: six qualifier rows were measured
# trailing, where ruff honours none of them, and one of those rows recorded
# `honoured` for a line that suppressed nothing.
#
# `flagged` is what the *guard* must say, which is not always what ruff does:
# the two blanket rows are honoured by ruff and flagged anyway, deliberately,
# because a directive naming no code cannot name an enabled one and would
# swallow a real future violation too (CR-107). Those two are marked in place.
# Every other flagged row is inert in the plain sense — it reads as a
# suppression and silences nothing.
#
# The directive text is dropped into a comment at run time rather than spelled
# out, for the same reason the pattern is assembled from parts: a literal one in
# this module would be read as real — by ruff, and by the repository-wide sweep
# at the foot of this file, which reads this module along with every other.
_TRAILING = "trailing"
_OWN_LINE = "own-line"
_SPELLINGS = (
    # Line-level forms, in the position where ruff honours them.
    ("noqa: E402", _TRAILING, False),  # honoured, and E4 is selected — the ordinary case
    ("NOQA: E402", _TRAILING, False),  # honoured too: the token is case-insensitive
    ("NOQA: BLE001", _TRAILING, True),  # CR-109's first uncovered form
    ("NoQa: E402, BLE001", _TRAILING, True),  # and CR-107's, in the new casing
    ("noqa: e402", _TRAILING, True),  # refused by ruff as invalid: suppresses nothing
    ("noqa", _TRAILING, True),  # honoured; flagged anyway — CR-107's blanket rule
    ("noqa: E402 F401", _TRAILING, False),  # the whitespace separator, unchanged
    ("noqa: E402 BLE001", _TRAILING, True),
    # File-level forms on their own line, which is the only place ruff reads
    # them. Measured: `ruff: ⟨token⟩` leaves 0 of the 3 diagnostics standing,
    # `ruff: ⟨token⟩: E402` leaves 2, `flake8:` behaves identically to `ruff:`.
    ("ruff: noqa", _OWN_LINE, True),  # silences the module; flagged as a blanket
    ("ruff:noqa", _OWN_LINE, True),  # which ruff reads with or without the space
    ("ruff: noqa: BLE001", _OWN_LINE, True),  # reaches ruff, and names nothing enabled
    ("ruff: noqa: E402", _OWN_LINE, False),  # a file-level directive can still be honest
    ("flake8: noqa", _OWN_LINE, True),  # honoured identically to the ruff: spelling
    ("flake8: noqa: BLE001", _OWN_LINE, True),
    ("flake8: noqa: E402", _OWN_LINE, False),  # the flake8 spelling, pinned honest too
    # ...and the same forms trailing code, where ruff refuses them outright.
    # This is CR-110: each of these reads as a suppression and silences nothing.
    ("ruff: noqa", _TRAILING, True),
    ("ruff: noqa: E402", _TRAILING, True),  # the row that used to record `honoured`
    ("flake8: noqa", _TRAILING, True),  # refused identically, warning and all
    # Ignored by ruff in every position tested — so it is inert wherever it
    # sits, and the guard is stricter than ruff on purpose. Both positions are
    # pinned, since "inert everywhere" is the claim being made.
    ("RUFF: NOQA", _OWN_LINE, True),
    ("RUFF: NOQA", _TRAILING, True),
    # CR-111. The same capitalised qualifier carrying a *code*, which is what
    # makes these rows load-bearing where the two above are not: those reach
    # `inert` through the blanket rule, which never looks at casing, so they
    # would stay green with every trace of casing-awareness deleted. Each of
    # these three was green before the casing rule and is red after it. They sit
    # on their own line, the position where ruff honours the lower-cased
    # spelling — so nothing but the capitalisation is doing the work.
    ("RUFF: NOQA: E402", _OWN_LINE, True),
    ("Ruff: noqa: E402", _OWN_LINE, True),
    ("FLAKE8: noqa: E402", _OWN_LINE, True),
    # ...and the control that keeps the rule aimed at the qualifier rather than
    # at capitals generally: the *token* upper-cased behind a lower-cased
    # qualifier is honoured by ruff (measured, 2 of 3), so it must stay green.
    ("ruff: NOQA: E402", _OWN_LINE, False),
    # CR-112. Line-level forms on their own line, where ruff applies them to a
    # line that carries no violation and they suppress nothing — the mirror of
    # the file-level rows above, which are inert everywhere *but* their own line.
    ("noqa: E402", _OWN_LINE, True),
    ("noqa: E402, F401", _OWN_LINE, True),
    ("a comment that carries no directive at all", _TRAILING, False),  # the control
)


@pytest.mark.parametrize(("directive", "position", "inert"), _SPELLINGS)
def test_the_suppression_check_reads_every_spelling_ruff_honours(
    directive: str, position: str, inert: bool
) -> None:
    """CR-109. The guard's property is *any suppression names a rule the select
    enables* — so a spelling the guard cannot read is a hole in it, however
    exotic the spelling looks. Two were left after CR-107: the upper-cased
    token, and the file-level blanket, which is the worst form of all since it
    silences a module rather than a line. This is the ruff measurement written
    as a test rather than as prose, so a pattern edit that stops reading one of
    these forms fails here instead of quietly narrowing what the sweep sees.

    CR-110 gives every row its position, because the file-level forms are read
    by ruff only on their own line — so a verdict recorded against the wrong
    position is not a measurement of anything, however carefully it was taken.

    CR-111 adds the rows that pin the qualifier's *casing*, which the table
    previously only appeared to cover: its two capitalised rows named no code,
    so they were judged by the blanket rule and would have survived the casing
    check being deleted outright. A row that reaches the right verdict for an
    unrelated reason pins nothing, and that is the second time in this table it
    has happened. CR-112 adds the line-level forms on their own line."""

    selected = _selected_prefixes(_pyproject_text())
    assert selected, "the select array parsed to nothing — the guard would be vacuous"

    if position == _OWN_LINE:
        line = f"    # {directive}"
    else:
        line = f"    import sys  # {directive}"
    verdict = _inert_suppression(line, selected)
    if inert:
        assert verdict is not None, (
            f"read as carrying no inert suppression, but ruff honours it "
            f"({position}): {line.strip()}"
        )
    else:
        assert verdict is None, verdict


def test_the_win32_stub_keeps_its_reason_and_carries_no_inert_suppression() -> None:
    """CR-106. The three stub methods are camel-cased on purpose — they stand in
    for real Win32 entry points — so they break a naming rule knowingly, and the
    reason has to stay on the line. What must *not* stay is a suppression naming
    a rule the declared select never enables: it silences nothing and misreads as
    load-bearing, which is exactly the mistake CR-106 records. A prefix in some
    release's default select does not mean every rule under it is enabled (0.16.0
    lists `N`, enables only N999), and selecting a rule on the command line
    proves only that it fires when selected.

    Written against the select array rather than against a hardcoded rule name,
    so widening the rule set re-permits the directive on its own instead of
    leaving a stale assertion behind. The check itself is shared with the
    broad-except sites below, and since CR-107 it reads every code in a
    directive rather than only the first.
    """

    selected = _selected_prefixes(_pyproject_text())
    assert selected, "the select array parsed to nothing — the guard would be vacuous"

    lines = [
        line
        for line in LIFECYCLE_TESTS.read_text(encoding="utf-8").splitlines()
        if any(line.lstrip().startswith(f"def {name}(") for name in _WIN32_STUB_METHODS)
    ]
    assert len(lines) == len(_WIN32_STUB_METHODS), (
        f"expected one definition per Win32 stub method, found {lines}"
    )

    for line in lines:
        assert "the Win32 name" in line, (
            f"the reason for the deliberate casing was dropped from: {line.strip()}"
        )
        inert = _inert_suppression(line, selected)
        assert inert is None, inert


# The files whose broad `except Exception` sites carried a suppression that was
# inert for its whole life (CR-108) — it named a rule the declared select has
# never enabled, so it silenced nothing while reading as load-bearing.
#
# The suppression half of this test is now also covered by the repository-wide
# sweep at the foot of this file, which CR-109 unblocked. What is *not* covered
# there, and is why this list survives, is the other half: these seven sites
# must each keep the reason that replaced the directive, and there must still be
# seven of them. Neither property generalises — no sweep can know which broad
# excepts were audited.
_BROAD_EXCEPT_FILES = (
    "src/sidelinehd_extractor/config.py",
    "src/sidelinehd_extractor/template_probe.py",
    "src/sidelinehd_extractor/webapp/history.py",
    "src/sidelinehd_extractor/webapp/jobs.py",
    "src/sidelinehd_extractor/workflow.py",
)
_BROAD_EXCEPT_SITES = 7


def test_the_broad_except_sites_keep_their_reason_and_carry_no_inert_suppression() -> None:
    """CR-108, and the same property as the Win32 guard above pointed at the
    other place it was violated. Each of these `except Exception` clauses is
    deliberately broad — a config read, a probe, a history scan and a job worker
    that must all survive anything the layer beneath them raises — so what
    matters on the line is the *reason*, not a suppression that suppresses
    nothing. The count is asserted so the guard cannot quietly stop finding its
    subjects and pass on an empty sweep."""

    selected = _selected_prefixes(_pyproject_text())
    assert selected, "the select array parsed to nothing — the guard would be vacuous"

    sites = 0
    for relative in _BROAD_EXCEPT_FILES:
        text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            where = f"{relative}:{number}"
            inert = _inert_suppression(line, selected)
            assert inert is None, f"{where}: {inert}"
            if not line.lstrip().startswith("except Exception"):
                continue
            sites += 1
            assert line.partition("#")[2].strip(), (
                f"{where}: the reason this except is deliberately broad was dropped, "
                f"leaving nothing on the line to explain it: {line.strip()}"
            )
    assert sites == _BROAD_EXCEPT_SITES, (
        f"expected {_BROAD_EXCEPT_SITES} broad-except sites across these files, found {sites}"
    )


# --- The same invariant, repository-wide (CR-108, CR-109) --------------------

# Only the suffixes ruff actually lints. A directive in a Markdown file or a
# workflow YAML is prose: nothing reads it, so nothing about it can be inert.
_LINTED_SUFFIXES = (".py", ".pyi")

# Floors, not targets. They exist so that a sweep which stops finding its
# subjects — a file list that comes back empty, a pattern that no longer
# matches — fails instead of passing on nothing at all, which is the failure
# mode a whole-repository guard is most exposed to. Today the sweep reads 75
# modules carrying 29 directives; these are set well below that so ordinary
# work does not have to touch them.
_MINIMUM_LINTED_MODULES = 50
_MINIMUM_DIRECTIVES = 10


def _tracked_modules() -> list[Path]:
    """Every Python module git tracks — which is also every one ruff lints.

    Asked of git rather than walked, so the sweep sees exactly the public tree:
    no `.venv`, no `build/`, no gitignored `runs/`. The known cost is the same
    one the name-safety guard carries — a module that has never been `git
    add`ed is invisible here until it is staged.
    """

    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *(f"*{suffix}" for suffix in _LINTED_SUFFIXES)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            "cannot list tracked files; run the suite from a git checkout so the "
            f"suppression sweep can do its job (git said: {result.stderr.strip()})"
        )
    return [_REPO_ROOT / name for name in result.stdout.split("\0") if name]


def test_no_tracked_module_carries_an_inert_suppression() -> None:
    """The general form of CR-106's invariant, and the end of the thread that
    began when one declined finding was checked rather than believed: **every
    suppression in the repository names a rule the declared select enables.**

    It could not be written until now. While the ten inert directives survived
    it was red, and both ways to green it were worse than waiting — fixing them
    from inside an unrelated diff, or naming them as exceptions in the guard,
    which writes the debt into the thing meant to detect it. The sweep is at
    zero, so the invariant is stated with no exceptions at all, which is the
    only version of it worth having.

    What this buys over the two scoped guards above is the file nobody thought
    to list: a suppression added tomorrow, in a module neither of them names,
    is now caught on the way in rather than found by a reviewer three changes
    later. It reads this module too — hence the assembled directive text
    throughout, which is the convention any future guard here inherits.
    """

    selected = _selected_prefixes(_pyproject_text())
    assert selected, "the select array parsed to nothing — the guard would be vacuous"

    modules = _tracked_modules()
    assert len(modules) >= _MINIMUM_LINTED_MODULES, (
        f"the sweep found only {len(modules)} tracked modules, which is too few to be "
        "the whole repository — it is looking in the wrong place, not passing"
    )

    directives = 0
    inert: list[str] = []
    for path in modules:
        where = path.relative_to(_REPO_ROOT)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _SUPPRESSION.search(line) is None:
                continue
            directives += 1
            reason = _inert_suppression(line, selected)
            if reason is not None:
                inert.append(f"{where}:{number}: {reason}")

    assert inert == [], "\n".join(inert)
    assert directives >= _MINIMUM_DIRECTIVES, (
        f"the sweep read {directives} suppressions across {len(modules)} modules, far "
        "fewer than this repository carries — the pattern has stopped matching, and a "
        "guard that finds nothing cannot fail"
    )
