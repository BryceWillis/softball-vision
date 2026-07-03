"""Tests for the roster management UI (item 50 / phase 39d).

All fixtures use sanitized placeholder names per the project security
constraint. Routes resolve ``rosters/`` and ``sidelinehd.cfg`` relative to the
CWD, so every test chdirs into ``tmp_path``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jinja2")
pytest.importorskip("multipart")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from sidelinehd_extractor.config import (  # noqa: E402
    ProjectConfig,
    load_project_config_values,
    load_roster_csv,
    write_project_config,
)
from sidelinehd_extractor.roster import default_roster_path, parse_team_list, write_roster_csv  # noqa: E402
from sidelinehd_extractor.webapp.app import create_app  # noqa: E402

TEAM_LIST = "#26 Amelia V.\n#7 Zoe H.\n#22 Maya R.\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def _seed_roster(team_name="Blue Thunder", text=TEAM_LIST):
    """Write a roster CSV the way the CLI does; returns (slug, path)."""

    path = default_roster_path(team_name)
    write_roster_csv(parse_team_list(text, team_name=team_name), path)
    return path.stem, path


def test_rosters_index_empty(client):
    response = client.get("/rosters")
    assert response.status_code == 200
    assert "No rosters yet" in response.text


def test_rosters_index_lists_csvs_with_counts_and_default(client, tmp_path):
    slug, path = _seed_roster()
    _seed_roster(team_name="Red Storm", text="#3 Emma B.\n")
    write_project_config(ProjectConfig(roster=path, team_name="Blue Thunder"), cwd=tmp_path)

    response = client.get("/rosters")
    assert response.status_code == 200
    assert f"/rosters/{slug}" in response.text
    assert "3 players" in response.text
    assert "1 player" in response.text
    badge = '<span class="default-badge">'
    assert badge in response.text
    # Only the configured roster is marked default.
    assert response.text.count(badge) == 1
    assert response.text.index(slug) < response.text.index("red_storm")


def test_create_roster_from_pasted_list(client, tmp_path):
    response = client.post(
        "/rosters", data={"team_name": "Blue Thunder", "team_list": TEAM_LIST}
    )
    assert response.status_code == 200  # 303 followed to the edit page
    assert response.url.path == "/rosters/blue_thunder"

    path = tmp_path / "rosters" / "blue_thunder.csv"
    assert path.exists()
    roster = load_roster_csv(path)
    assert [(p.number, p.full_name) for p in roster.players] == [
        ("26", "Amelia V."),
        ("7", "Zoe H."),
        ("22", "Maya R."),
    ]
    assert "Amelia V." in response.text


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"team_name": "Blue Thunder", "team_list": "#26 Amelia V.\nnot a line\n"},
         "could not parse roster line 2"),
        ({"team_name": "Blue Thunder", "team_list": "#26 Amelia V.\n#26 Zoe H.\n"},
         "duplicate jersey number on line 2"),
        ({"team_name": "Blue Thunder", "team_list": ""},
         "did not contain any players"),
        ({"team_name": "   ", "team_list": TEAM_LIST}, "Enter a team name."),
    ],
)
def test_create_roster_invalid_returns_400_and_writes_nothing(client, tmp_path, data, message):
    response = client.post("/rosters", data=data)
    assert response.status_code == 400
    assert message in response.text
    assert not (tmp_path / "rosters").exists()
    # The submitted values are preserved in the re-rendered form.
    if data["team_list"]:
        assert "Amelia V." in response.text


def test_create_roster_refuses_to_overwrite_existing(client, tmp_path):
    _, path = _seed_roster()
    before = path.read_text(encoding="utf-8")
    response = client.post(
        "/rosters", data={"team_name": "Blue Thunder", "team_list": "#3 Emma B.\n"}
    )
    assert response.status_code == 400
    assert "already exists" in response.text
    assert path.read_text(encoding="utf-8") == before


def test_edit_page_shows_players_and_unknown_slug_404s(client, tmp_path):
    slug, path = _seed_roster()
    response = client.get(f"/rosters/{slug}")
    assert response.status_code == 200
    assert 'value="Amelia V."' in response.text
    assert 'value="26"' in response.text
    assert "Replace from pasted list" in response.text

    assert client.get("/rosters/no_such_team").status_code == 404
    # Slugs that could escape rosters/ are rejected, not resolved.
    assert client.get("/rosters/..%2Fsidelinehd").status_code == 404
    assert client.post("/rosters/no_such_team", data={}).status_code == 404
    assert client.post("/rosters/no_such_team/delete").status_code == 404
    assert client.post("/rosters/no_such_team/set-default").status_code == 404


def test_save_row_edits_round_trips_through_csv(client, tmp_path):
    slug, path = _seed_roster()
    response = client.post(
        f"/rosters/{slug}",
        data={
            "mode": "rows",
            "number_0": "28", "full_name_0": "Amelia V.", "preferred_name_0": "Amelia",
            "display_name_0": "Amelia V.", "aliases_0": "Amelia; Millie",
            "number_1": "7", "full_name_1": "Zoe H.", "preferred_name_1": "Zoe",
            "display_name_1": "Zoe H.", "aliases_1": "Zoe",
            "number_2": "22", "full_name_2": "Maya R.", "preferred_name_2": "Maya",
            "display_name_2": "Maya R.", "aliases_2": "Maya",
        },
    )
    assert response.status_code == 200
    roster = load_roster_csv(path)
    edited = roster.players[0]
    assert edited.number == "28"
    assert edited.aliases == ["Amelia", "Millie"]
    # Reload shows the change.
    assert 'value="28"' in client.get(f"/rosters/{slug}").text


def test_save_add_and_delete_rows(client, tmp_path):
    slug, path = _seed_roster()
    response = client.post(
        f"/rosters/{slug}",
        data={
            "mode": "rows",
            "number_0": "26", "full_name_0": "Amelia V.",
            "number_1": "7", "full_name_1": "Zoe H.", "delete_1": "1",
            "number_2": "22", "full_name_2": "Maya R.",
            # The blank add-player row, filled in.
            "number_3": "#11", "full_name_3": "  Riley   S. ",
        },
    )
    assert response.status_code == 200
    roster = load_roster_csv(path)
    assert [(p.number, p.full_name) for p in roster.players] == [
        ("26", "Amelia V."),
        ("22", "Maya R."),
        ("11", "Riley S."),
    ]


def test_save_untouched_blank_add_row_is_ignored(client, tmp_path):
    slug, path = _seed_roster(text="#26 Amelia V.\n")
    response = client.post(
        f"/rosters/{slug}",
        data={
            "mode": "rows",
            "number_0": "26", "full_name_0": "Amelia V.",
            "number_1": "", "full_name_1": "", "preferred_name_1": "", "aliases_1": "",
        },
    )
    assert response.status_code == 200
    assert len(load_roster_csv(path).players) == 1


@pytest.mark.parametrize(
    ("row_overrides", "message"),
    [
        ({"number_1": "26"}, "duplicate jersey number: 26"),
        ({"full_name_1": "   "}, "is missing a player name"),
        ({"number_1": ""}, "is missing a jersey number"),
    ],
)
def test_save_invalid_rows_400_and_file_untouched(client, tmp_path, row_overrides, message):
    slug, path = _seed_roster(text="#26 Amelia V.\n#7 Zoe H.\n")
    before = path.read_text(encoding="utf-8")
    data = {
        "mode": "rows",
        "number_0": "26", "full_name_0": "Amelia V.",
        "number_1": "7", "full_name_1": "Zoe H.",
    }
    data.update(row_overrides)
    response = client.post(f"/rosters/{slug}", data=data)
    assert response.status_code == 400
    assert message in response.text
    assert path.read_text(encoding="utf-8") == before
    # Submitted edits are re-rendered inline so they are not lost.
    assert 'value="Amelia V."' in response.text


def test_save_deleting_every_row_is_rejected(client, tmp_path):
    slug, path = _seed_roster(text="#26 Amelia V.\n")
    response = client.post(
        f"/rosters/{slug}",
        data={"mode": "rows", "number_0": "26", "full_name_0": "Amelia V.", "delete_0": "1"},
    )
    assert response.status_code == 400
    assert "at least one player" in response.text
    assert len(load_roster_csv(path).players) == 1


def test_replace_from_pasted_list(client, tmp_path):
    slug, path = _seed_roster()
    response = client.post(
        f"/rosters/{slug}",
        data={"mode": "paste", "team_list": "#3 Emma B.\n#14 Sofia L.\n"},
    )
    assert response.status_code == 200
    roster = load_roster_csv(path)
    assert [(p.number, p.full_name) for p in roster.players] == [
        ("3", "Emma B."),
        ("14", "Sofia L."),
    ]


def test_replace_with_bad_paste_400_and_file_untouched(client, tmp_path):
    slug, path = _seed_roster()
    before = path.read_text(encoding="utf-8")
    response = client.post(
        f"/rosters/{slug}", data={"mode": "paste", "team_list": "not a roster line"}
    )
    assert response.status_code == 400
    assert "could not parse roster line 1" in response.text
    assert path.read_text(encoding="utf-8") == before


def test_delete_removes_csv(client, tmp_path):
    slug, path = _seed_roster()
    response = client.post(f"/rosters/{slug}/delete")
    assert response.status_code == 200  # 303 followed back to the list
    assert response.url.path == "/rosters"
    assert not path.exists()
    assert client.get(f"/rosters/{slug}").status_code == 404


def test_delete_of_configured_default_renders_warning_confirm(client, tmp_path):
    slug, path = _seed_roster()
    write_project_config(ProjectConfig(roster=path, team_name="Blue Thunder"), cwd=tmp_path)
    response = client.get("/rosters")
    assert "configured default" in response.text  # the stronger confirm prompt

    # The guard is the confirm prompt; a confirmed POST still deletes.
    assert client.post(f"/rosters/{slug}/delete").status_code == 200
    assert not path.exists()


def test_set_default_updates_config_and_preserves_other_keys(client, tmp_path):
    slug, path = _seed_roster()
    template = tmp_path / "overlay.json"
    template.write_text("{}", encoding="utf-8")
    write_project_config(
        ProjectConfig(roster=None, template=template, team_name="Blue Thunder"),
        cwd=tmp_path,
    )

    response = client.post(f"/rosters/{slug}/set-default")
    assert response.status_code == 200

    values = load_project_config_values(cwd=tmp_path)
    assert values["roster"] == str(path)
    assert values["template"] == str(template)
    assert values["team_name"] == "Blue Thunder"
    # Assert via the config loader path comparison the UI itself uses.
    marked = client.get("/rosters")
    assert marked.text.count('<span class="default-badge">') == 1


def test_unloadable_csv_degrades_on_list_and_400s_on_edit(client, tmp_path):
    rosters_dir = tmp_path / "rosters"
    rosters_dir.mkdir()
    (rosters_dir / "broken.csv").write_text("not,a,roster\n1,2,3\n", encoding="utf-8")

    listing = client.get("/rosters")
    assert listing.status_code == 200
    assert "could not load" in listing.text

    assert client.get("/rosters/broken").status_code == 400
    assert client.post("/rosters/broken", data={"mode": "rows"}).status_code == 400


def test_index_links_to_rosters(client):
    response = client.get("/")
    assert '/rosters' in response.text
