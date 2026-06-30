"""Create a local paste kit for publishing timestamps to YouTube."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sidelinehd_extractor.naming import game_name_for_run, game_slug_for_run


@dataclass(frozen=True)
class PublishKitResult:
    """Summary of a generated publishing paste kit."""

    output_path: Path
    game_name: str
    chapters_path: Path
    at_bats_path: Path


def default_publish_kit_path(
    run_path: Path,
    output_dir: Optional[Path] = None,
    game_name: Optional[str] = None,
) -> Path:
    """Return the default paste-kit path for a run/game."""

    slug = game_slug_for_run(run_path, explicit_name=game_name)
    base_dir = output_dir.expanduser() if output_dir else run_path.expanduser() / "exports"
    return base_dir / slug / "youtube_paste_kit.md"


def write_publish_kit(
    run_path: Path,
    chapters_path: Path,
    at_bats_path: Path,
    output_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    game_name: Optional[str] = None,
) -> PublishKitResult:
    """Write a Markdown paste kit from chapter and at-bat text files."""

    resolved_game_name = game_name_for_run(run_path, explicit_name=game_name)
    destination = output_path.expanduser() if output_path else default_publish_kit_path(
        run_path,
        output_dir=output_dir,
        game_name=resolved_game_name,
    )
    chapters_source = chapters_path.expanduser()
    at_bats_source = at_bats_path.expanduser()

    chapters_text = _read_text(chapters_source)
    at_bats_text = _read_text(at_bats_source)
    kit_text = render_publish_kit(
        game_name=resolved_game_name,
        chapters_text=chapters_text,
        at_bats_text=at_bats_text,
        chapters_path=chapters_source,
        at_bats_path=at_bats_source,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(kit_text, encoding="utf-8")
    return PublishKitResult(
        output_path=destination,
        game_name=resolved_game_name,
        chapters_path=chapters_source,
        at_bats_path=at_bats_source,
    )


def render_publish_kit(
    game_name: str,
    chapters_text: str,
    at_bats_text: str,
    chapters_path: Optional[Path] = None,
    at_bats_path: Optional[Path] = None,
) -> str:
    """Render a Markdown paste kit."""

    chapters_source = f"\nSource: `{chapters_path}`\n" if chapters_path else ""
    at_bats_source = f"\nSource: `{at_bats_path}`\n" if at_bats_path else ""

    return (
        f"# YouTube Paste Kit: {game_name}\n\n"
        "## Description Chapters\n\n"
        "Paste this into the YouTube video description. YouTube chapters require a `0:00` line.\n"
        f"{chapters_source}\n"
        "```text\n"
        f"{chapters_text.rstrip()}\n"
        "```\n\n"
        "## Pinned Comment\n\n"
        "Paste this as a YouTube comment, then pin it.\n"
        f"{at_bats_source}\n"
        "```text\n"
        f"{at_bats_text.rstrip()}\n"
        "```\n\n"
        "## Checklist\n\n"
        "- [ ] Description saved\n"
        "- [ ] Chapters visible on the video progress bar\n"
        "- [ ] At-bat comment posted\n"
        "- [ ] At-bat comment pinned\n"
    )


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")
