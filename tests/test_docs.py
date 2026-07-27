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
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
README = _REPO_ROOT / "README.md"
PYPROJECT = _REPO_ROOT / "pyproject.toml"


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
