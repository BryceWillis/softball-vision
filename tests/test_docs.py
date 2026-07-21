"""Guard tests for the README's contributor-facing test instructions.

The suite mixes ``unittest.TestCase`` classes with pytest fixture and
function-style tests, so ``unittest discover`` silently collects only part of
it and skips the entire web-app surface. A README that prescribes it hands a
contributor a false green: they run it, see green, and ship a web-app
regression that the skipped tests would have caught. CI runs the full suite
under pytest, so nothing catches the drift — it is the *local* signal that
lies, and only a check on the README text can notice it.
"""

from __future__ import annotations

from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


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
