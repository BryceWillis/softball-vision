"""CLI parity for the three web-only mutations (M7 / 70e).

``delete-roster``, ``set-default-roster``, and ``clear-corrections`` give the
command line a form of ``POST /rosters/{slug}/delete``,
``POST /rosters/{slug}/set-default``, and
``POST /jobs/{job_id}/corrections/clear`` — the three gaps the CLI-parity
invariant's audit named. The parity tests drive both the CLI and the real web
route on identical fixtures and compare the on-disk result byte for byte, so a
future edit that lets the two diverge fails here.

All fixtures use sanitized placeholder names per the project security
constraint. Every command resolves ``rosters/``, ``runs/``, and
``sidelinehd.cfg`` relative to CWD, so each test chdirs into a tmp dir.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from sidelinehd_extractor.cli import main
from sidelinehd_extractor.config import (
    ProjectConfig,
    load_project_config_values,
    write_project_config,
)
from sidelinehd_extractor.corrections import (
    EventCorrection,
    load_event_corrections,
    write_event_corrections,
)
from sidelinehd_extractor.models import Event, EventType, HalfInning
from sidelinehd_extractor.processing import write_json, write_jsonl
from sidelinehd_extractor.roster import default_roster_path, parse_team_list, write_roster_csv
from sidelinehd_extractor.workflow import finalize_run_exports

TEAM_LIST = "#26 Amelia V.\n#7 Zoe H.\n#22 Maya R.\n"


class _FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _run(argv, stdin_text=""):
    """Run the CLI with a non-interactive stdin; return (code, stdout, stderr)."""

    out, err = io.StringIO(), io.StringIO()
    with patch("sys.stdin", io.StringIO(stdin_text)), redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _seed_roster(team_name="Blue Thunder", text=TEAM_LIST):
    """Write a roster CSV under the CWD's ``rosters/``; returns (slug, path)."""

    path = default_roster_path(team_name)
    write_roster_csv(parse_team_list(text, team_name=team_name), path)
    return path.stem, path


def _seed_run(root: Path, corrections):
    """A run dir with events, a manifest, corrections, and its exports written."""

    run_dir = root / "runs" / "game-run"
    run_dir.mkdir(parents=True)
    write_json(run_dir / "manifest.json", {"export": {"output_prefix": str(run_dir / "full")}})
    events = [
        Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
        Event(EventType.AT_BAT_START, 605, "#22", inning=1, player_number="22"),
    ]
    write_jsonl(run_dir / "events.jsonl", events)
    write_event_corrections(run_dir / "corrections.csv", corrections)
    finalize_run_exports(run_dir, corrections=corrections, roster=None)
    return run_dir


def _label_correction():
    return EventCorrection(
        timestamp_seconds=605.0,
        field_name="label",
        value="Fixed Label",
        event_type=EventType.AT_BAT_START,
    )


def _name_correction():
    return EventCorrection(
        timestamp_seconds=605.0,
        field_name="player_name",
        value="Maya R.",
        event_type=EventType.AT_BAT_START,
    )


# --- delete-roster -----------------------------------------------------------


def test_delete_roster_removes_csv_with_yes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug, path = _seed_roster()
    code, out, err = _run(["delete-roster", slug, "--yes"])
    assert code == 0
    assert not path.exists()
    assert "Deleted" in out


@pytest.mark.parametrize("bad", ["../roster", "foo/bar", "/etc/passwd", "no_such"])
def test_delete_roster_rejects_traversal_and_missing(tmp_path, monkeypatch, bad):
    monkeypatch.chdir(tmp_path)
    _, path = _seed_roster()
    code, out, err = _run(["delete-roster", bad, "--yes"])
    assert code == 1
    assert "roster" in err.lower()
    # A rejected slug touches nothing.
    assert path.exists()


def test_delete_default_without_yes_refuses_naming_consequence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug, path = _seed_roster()
    write_project_config(ProjectConfig(roster=path, team_name="Blue Thunder"), cwd=tmp_path)
    code, out, err = _run(["delete-roster", slug])  # non-interactive stdin, no --yes
    assert code == 1
    assert path.exists()
    assert "default" in err
    assert "roster names" in err  # the consequence is named, per the spec
    assert "--yes" in err


def test_delete_non_default_without_yes_refuses_non_interactively(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug, path = _seed_roster()
    code, out, err = _run(["delete-roster", slug])
    assert code == 1
    assert path.exists()
    assert "--yes" in err


def test_delete_interactive_confirm_and_cancel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug, path = _seed_roster()

    # Cancel at the prompt leaves the file.
    with patch("sys.stdin", _FakeTTY()), patch("builtins.input", return_value="n"):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert main(["delete-roster", slug]) == 1
    assert path.exists()

    # Confirming deletes it.
    with patch("sys.stdin", _FakeTTY()), patch("builtins.input", return_value="y"):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert main(["delete-roster", slug]) == 0
    assert not path.exists()


# --- set-default-roster ------------------------------------------------------


def test_set_default_roster_updates_config_preserving_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug, path = _seed_roster()
    template = tmp_path / "overlay.json"
    template.write_text("{}", encoding="utf-8")
    write_project_config(
        ProjectConfig(roster=None, template=template, team_name="Blue Thunder"), cwd=tmp_path
    )

    code, out, err = _run(["set-default-roster", slug])
    assert code == 0
    values = load_project_config_values(cwd=tmp_path)
    assert values["roster"] == str(path)
    assert values["template"] == str(template)
    assert values["team_name"] == "Blue Thunder"


def test_set_default_roster_preserves_unmanaged_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slug, path = _seed_roster()
    (tmp_path / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = false\n", encoding="utf-8"
    )

    code, out, err = _run(["set-default-roster", slug])
    assert code == 0
    values = load_project_config_values(cwd=tmp_path)
    assert values["roster"] == str(path)
    # The 67d opt-out survives a default-roster change, exactly as via the web.
    assert values["check_for_updates"] == "false"


def test_set_default_roster_unknown_slug_errors_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, err = _run(["set-default-roster", "no_such"])
    assert code == 1
    assert not (tmp_path / "sidelinehd.cfg").exists()


# --- clear-corrections -------------------------------------------------------


def test_clear_corrections_all_reverts_export(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _seed_run(tmp_path, [_label_correction()])
    at_bats = run_dir / "full_at_bats.txt"
    assert "Fixed Label" in at_bats.read_text(encoding="utf-8")

    code, out, err = _run(["clear-corrections", "--run", str(run_dir), "--all"])
    assert code == 0
    assert load_event_corrections(run_dir / "corrections.csv") == []
    text = at_bats.read_text(encoding="utf-8")
    assert "Fixed Label" not in text
    assert "#22" in text  # reverted to the uncorrected label


def test_clear_corrections_by_selector_keeps_the_others(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _seed_run(tmp_path, [_label_correction(), _name_correction()])

    code, out, err = _run(
        [
            "clear-corrections",
            "--run",
            str(run_dir),
            "--event-type",
            "at_bat_start",
            "--timestamp",
            "605",
            "--field",
            "label",
        ]
    )
    assert code == 0
    remaining = load_event_corrections(run_dir / "corrections.csv")
    assert [(c.field_name, c.value) for c in remaining] == [("player_name", "Maya R.")]
    assert "Fixed Label" not in (run_dir / "full_at_bats.txt").read_text(encoding="utf-8")


def test_clear_corrections_no_match_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _seed_run(tmp_path, [_label_correction()])
    before = (run_dir / "corrections.csv").read_text(encoding="utf-8")

    code, out, err = _run(
        ["clear-corrections", "--run", str(run_dir), "--timestamp", "999", "--field", "label"]
    )
    assert code == 0
    assert "No matching corrections" in out
    assert (run_dir / "corrections.csv").read_text(encoding="utf-8") == before


def test_clear_corrections_absent_file_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs" / "game-run").mkdir(parents=True)
    code, out, err = _run(
        ["clear-corrections", "--run", str(tmp_path / "runs" / "game-run"), "--all"]
    )
    assert code == 0
    assert "nothing to clear" in out


def test_clear_corrections_requires_selector_or_all(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_dir = _seed_run(tmp_path, [_label_correction()])
    code, out, err = _run(["clear-corrections", "--run", str(run_dir)])
    assert code == 1
    assert "--all" in err
    # The corrections file is untouched on the input error.
    assert load_event_corrections(run_dir / "corrections.csv") != []


# --- byte-identical parity with the web routes -------------------------------


def test_delete_roster_matches_web_route(tmp_path, monkeypatch):
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    pytest.importorskip("jinja2")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    from sidelinehd_extractor.webapp.app import create_app

    cli_root = tmp_path / "cli"
    web_root = tmp_path / "web"
    cli_root.mkdir()
    web_root.mkdir()

    monkeypatch.chdir(cli_root)
    slug, cli_path = _seed_roster()
    _run(["delete-roster", slug, "--yes"])

    monkeypatch.chdir(web_root)
    _, web_path = _seed_roster()
    client = TestClient(create_app(runs_dir=Path("no-such-runs-dir")))
    assert client.post(f"/rosters/{slug}/delete").status_code == 200

    assert not cli_path.exists()
    assert not web_path.exists()
    assert sorted(p.name for p in (cli_root / "rosters").iterdir()) == sorted(
        p.name for p in (web_root / "rosters").iterdir()
    )


def test_set_default_roster_matches_web_route(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("jinja2")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    from sidelinehd_extractor.webapp.app import create_app

    # A template outside both roots so the persisted path is identical either way.
    template = tmp_path / "overlay.json"
    template.write_text("{}", encoding="utf-8")

    cli_root = tmp_path / "cli"
    web_root = tmp_path / "web"

    def seed(root):
        root.mkdir()
        monkeypatch.chdir(root)
        slug, _ = _seed_roster()
        write_project_config(
            ProjectConfig(roster=None, template=template, team_name="Blue Thunder"), cwd=root
        )
        return slug

    slug = seed(cli_root)
    _run(["set-default-roster", slug])

    seed(web_root)
    client = TestClient(create_app(runs_dir=Path("no-such-runs-dir")))
    assert client.post(f"/rosters/{slug}/set-default").status_code == 200

    assert (cli_root / "sidelinehd.cfg").read_bytes() == (web_root / "sidelinehd.cfg").read_bytes()


def test_clear_corrections_matches_web_route(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("jinja2")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    from sidelinehd_extractor.webapp.app import create_app
    from sidelinehd_extractor.webapp.jobs import JobStore

    cli_root = tmp_path / "cli"
    web_root = tmp_path / "web"
    cli_root.mkdir()
    web_root.mkdir()

    corrections = [_label_correction(), _name_correction()]
    cli_run = _seed_run(cli_root, corrections)
    web_run = _seed_run(web_root, corrections)

    # CLI clears the label correction.
    monkeypatch.chdir(cli_root)
    _run(
        [
            "clear-corrections",
            "--run",
            str(cli_run),
            "--event-type",
            "at_bat_start",
            "--timestamp",
            "605",
            "--field",
            "label",
        ]
    )

    # The web route clears the same one through a done job over the web run dir.
    monkeypatch.chdir(web_root)
    store = JobStore()
    client = TestClient(create_app(store=store, runs_dir=Path("no-such-runs-dir")))
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(
        job.id,
        status="done",
        result={
            "kind": "single",
            "run_dir": str(web_run),
            "chapters_path": str(web_run / "full_chapters.txt"),
            "at_bats_path": str(web_run / "full_at_bats.txt"),
        },
    )
    response = client.post(
        f"/jobs/{job.id}/corrections/clear",
        data={"event_type": "at_bat_start", "timestamp": "605", "field": "label"},
    )
    assert response.status_code == 200

    for name in ("corrections.csv", "full_at_bats.txt", "full_chapters.txt"):
        assert (cli_run / name).read_bytes() == (web_run / name).read_bytes(), name
