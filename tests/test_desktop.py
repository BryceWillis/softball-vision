"""Tests for the desktop Dock-app launcher plumbing (items 54d, 68b).

The AppKit UI itself is not tested (it needs a macOS GUI session); everything
below the GUI line — data dir, port picking, the uvicorn server thread, the
menu models the GUI renders — is.
"""

from __future__ import annotations

import ast
import os
import socket
import urllib.request
from pathlib import Path

import pytest

from sidelinehd_extractor import desktop
from sidelinehd_extractor.desktop import (
    ENTRY_ACTION,
    ENTRY_DISPLAY_ONLY,
    ServerController,
    app_menu_entries,
    default_data_dir,
    desktop_pipeline_kwargs,
    dock_menu_entries,
    find_open_port,
    prepare_data_dir,
)
from sidelinehd_extractor.events import DetectionConfig
from sidelinehd_extractor.updates import update_menu_title

pytest.importorskip("uvicorn")


class _RestoreCwd:
    def __enter__(self):
        self._cwd = os.getcwd()
        return self

    def __exit__(self, *exc):
        os.chdir(self._cwd)


def test_default_data_dir_is_application_support_on_mac(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    assert default_data_dir() == (
        Path.home() / "Library" / "Application Support" / "SidelineHD Extractor"
    )


def test_prepare_data_dir_creates_and_chdirs(tmp_path):
    target = tmp_path / "nested" / "data-dir"
    with _RestoreCwd():
        result = prepare_data_dir(target)
        assert result == target
        assert target.is_dir()
        assert Path.cwd() == target


def test_prepare_data_dir_points_frozen_bundle_at_tessdata(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "tessdata").mkdir(parents=True)
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    with _RestoreCwd():
        prepare_data_dir(tmp_path / "data")
    assert os.environ.pop("TESSDATA_PREFIX") == str(bundle / "tessdata")


def test_prepare_data_dir_respects_user_tessdata_prefix(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "tessdata").mkdir(parents=True)
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("TESSDATA_PREFIX", "/custom/tessdata")
    with _RestoreCwd():
        prepare_data_dir(tmp_path / "data")
    assert os.environ["TESSDATA_PREFIX"] == "/custom/tessdata"


def test_unfrozen_run_does_not_touch_tessdata_prefix(tmp_path, monkeypatch):
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    with _RestoreCwd():
        prepare_data_dir(tmp_path / "data")
    assert "TESSDATA_PREFIX" not in os.environ


def test_find_open_port_skips_a_taken_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy_port = taken.getsockname()[1]
        port = find_open_port("127.0.0.1", start_port=busy_port, attempts=3)
        assert port != busy_port
        assert busy_port < port < busy_port + 3


def test_find_open_port_raises_when_every_port_is_taken():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy_port = taken.getsockname()[1]
        with pytest.raises(RuntimeError, match="no open port"):
            find_open_port("127.0.0.1", start_port=busy_port, attempts=1)


def test_desktop_pipeline_kwargs_requests_tesserocr_backend(monkeypatch, tmp_path):
    """The bundle ships tesserocr, not the Tesseract CLI, so the desktop
    runner must ask for that backend (which itself falls back cleanly)."""

    from sidelinehd_extractor import ocr as ocr_module

    requested = []

    def fake_backend(name):
        requested.append(name)
        return object()

    monkeypatch.setattr(ocr_module, "create_ocr_backend", fake_backend)
    monkeypatch.chdir(tmp_path)  # no sidelinehd.cfg -> template/roster None
    kwargs = desktop_pipeline_kwargs()
    assert requested == ["tesserocr"]
    assert kwargs["detection"] == DetectionConfig(auto_detect_batting_half=True)
    assert kwargs["template"] is None and kwargs["roster"] is None


async def _tiny_app(scope, receive, send):
    if scope["type"] != "http":
        return
    await send(
        {"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]}
    )
    await send({"type": "http.response.body", "body": b"ok"})


def test_server_controller_starts_serves_and_stops():
    port = find_open_port(start_port=8901)
    controller = ServerController(port=port, app_factory=lambda: _tiny_app)
    assert not controller.running
    controller.start()
    try:
        assert controller.running
        assert controller.url == f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(controller.url, timeout=5) as response:
            assert response.read() == b"ok"
        controller.start()  # idempotent while running
        assert controller.running
    finally:
        controller.stop()
    assert not controller.running


async def _error_app(scope, receive, send):
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 500, "headers": []})
    await send({"type": "http.response.body", "body": b"boom"})


def _point_selftest_at(monkeypatch, tmp_path, app):
    """Wire run_selftest's collaborators to a tmp data dir and a stub app.

    The real data-dir chdir and the real webapp factory are exercised
    elsewhere; here the subject is the selftest orchestration itself.
    """

    prepared = []

    def fake_prepare_data_dir(data_dir=None):
        prepared.append(tmp_path)
        return tmp_path

    monkeypatch.setattr(desktop, "prepare_data_dir", fake_prepare_data_dir)
    # Dependency self-containment is exercised by its own tests below; the
    # stub keeps these orchestration tests independent of the host's OCR and
    # yt-dlp installs.
    monkeypatch.setattr(desktop, "bundle_dependency_failures", lambda: [])
    monkeypatch.setattr(
        desktop,
        "ServerController",
        lambda port: ServerController(port=port, app_factory=lambda: app),
    )
    return prepared


def test_selftest_passes_when_the_server_serves_200(monkeypatch, tmp_path, capsys):
    prepared = _point_selftest_at(monkeypatch, tmp_path, _tiny_app)
    assert desktop.run_selftest() == 0
    # prepare_data_dir() is deliberate — exercising it is part of the point.
    assert prepared == [tmp_path]
    assert "selftest: OK" in capsys.readouterr().out


def test_selftest_fails_on_a_non_200_response(monkeypatch, tmp_path, capsys):
    _point_selftest_at(monkeypatch, tmp_path, _error_app)
    assert desktop.run_selftest() == 1
    assert "selftest: FAIL" in capsys.readouterr().err


def test_selftest_fails_when_dependencies_lean_on_the_host(monkeypatch, tmp_path, capsys):
    _point_selftest_at(monkeypatch, tmp_path, _tiny_app)
    monkeypatch.setattr(
        desktop,
        "bundle_dependency_failures",
        lambda: ["dependency yt-dlp unhealthy: the yt_dlp module is not importable"],
    )
    assert desktop.run_selftest() == 1
    err = capsys.readouterr().err
    assert "selftest: FAIL" in err
    assert "yt-dlp" in err


def test_bundle_dependency_failures_empty_for_a_healthy_bundle(monkeypatch):
    from sidelinehd_extractor import ocr as ocr_module

    backend = ocr_module.TesserocrOCRBackend(object(), object())
    monkeypatch.setattr("sidelinehd_extractor.preflight.missing_dependencies", lambda: [])
    monkeypatch.setattr("sidelinehd_extractor.ocr.create_ocr_backend", lambda name: backend)
    assert desktop.bundle_dependency_failures() == []


def test_bundle_dependency_failures_flag_the_cli_fallback(monkeypatch):
    from sidelinehd_extractor import ocr as ocr_module

    monkeypatch.setattr("sidelinehd_extractor.preflight.missing_dependencies", lambda: [])
    monkeypatch.setattr(
        "sidelinehd_extractor.ocr.create_ocr_backend",
        lambda name: ocr_module.tesseract_ocr_image,
    )
    failures = desktop.bundle_dependency_failures()
    assert any("fell back to the Tesseract CLI" in failure for failure in failures)


def test_bundle_dependency_failures_report_unhealthy_dependencies(monkeypatch):
    from sidelinehd_extractor import ocr as ocr_module

    backend = ocr_module.TesserocrOCRBackend(object(), object())
    monkeypatch.setattr(
        "sidelinehd_extractor.preflight.missing_dependencies",
        lambda: [
            {
                "name": "yt-dlp",
                "ok": False,
                "detail": "the yt_dlp module is not importable",
                "install_hint": "reinstall",
            }
        ],
    )
    monkeypatch.setattr("sidelinehd_extractor.ocr.create_ocr_backend", lambda name: backend)
    failures = desktop.bundle_dependency_failures()
    assert failures == [
        "dependency yt-dlp unhealthy: the yt_dlp module is not importable"
    ]


def test_bundle_dependency_failures_capture_backend_errors(monkeypatch):
    def broken_backend(name):
        raise RuntimeError("bundled OCR failed to load")

    monkeypatch.setattr("sidelinehd_extractor.preflight.missing_dependencies", lambda: [])
    monkeypatch.setattr("sidelinehd_extractor.ocr.create_ocr_backend", broken_backend)
    failures = desktop.bundle_dependency_failures()
    assert any("bundled OCR failed to load" in failure for failure in failures)


def test_selftest_fails_and_still_stops_when_the_server_never_starts(monkeypatch, capsys):
    controllers = []

    class _DeadController:
        def __init__(self, port):
            self.url = f"http://127.0.0.1:{port}"
            self.stopped = False
            controllers.append(self)

        def start(self, timeout):
            raise RuntimeError(f"web server failed to start on {self.url}")

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(desktop, "prepare_data_dir", lambda data_dir=None: None)
    monkeypatch.setattr(desktop, "bundle_dependency_failures", lambda: [])
    monkeypatch.setattr(desktop, "ServerController", _DeadController)
    assert desktop.run_selftest() == 1
    assert "selftest: FAIL" in capsys.readouterr().err
    assert controllers and controllers[0].stopped


def test_main_selftest_flag_dispatches_without_starting_the_gui(monkeypatch):
    monkeypatch.setattr(desktop, "run_selftest", lambda: 7)

    def _must_not_run(*args, **kwargs):
        raise AssertionError("--selftest must not reach the launch path")

    monkeypatch.setattr(desktop, "prepare_data_dir", _must_not_run)
    monkeypatch.setattr(desktop, "run_dock_app", _must_not_run)
    assert desktop.main(["--selftest"]) == 7


def test_main_starts_the_update_check_after_the_server_and_hands_it_to_the_dock_app(
    monkeypatch,
):
    """Item 67d: the check starts only once the server is up (it must never
    block launch) and the Dock app receives it to poll."""

    events = []

    class _Controller:
        def __init__(self, port):
            self.url = f"http://127.0.0.1:{port}"

        def start(self):
            events.append("server-start")

        def stop(self):
            events.append("server-stop")

    class _Check:
        def start(self):
            events.append("update-check-start")

    check = _Check()
    captured = {}

    def fake_dock_app(controller, update_check=None):
        captured["update_check"] = update_check
        events.append("dock-app")

    monkeypatch.setattr(desktop, "prepare_data_dir", lambda: events.append("data-dir"))
    monkeypatch.setattr(desktop, "find_open_port", lambda: 8000)
    monkeypatch.setattr(desktop, "ServerController", _Controller)
    monkeypatch.setattr(desktop, "UpdateCheck", lambda: check)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: events.append("browser"))
    monkeypatch.setattr(desktop, "run_dock_app", fake_dock_app)

    assert desktop.main([]) == 0
    assert captured["update_check"] is check
    assert events.index("server-start") < events.index("update-check-start")
    assert events.index("update-check-start") < events.index("dock-app")


def test_server_controller_start_raises_when_port_is_taken():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy_port = taken.getsockname()[1]
        controller = ServerController(port=busy_port, app_factory=lambda: _tiny_app)
        with pytest.raises(RuntimeError, match="failed to start"):
            controller.start()
        controller.stop()


# --- Menu models (item 68b) --------------------------------------------------
#
# The AppKit layer renders these verbatim, so the models are where the menu
# contract is enforced: what exists, in what order, and what is clickable.

_URL = "http://127.0.0.1:8000"
_STAMP = "v0.4.1 (a1b2c3d) · built 2026-07-21"


def test_app_menu_base_entries_and_order():
    assert app_menu_entries(_URL, _STAMP) == [
        ("About SidelineHD Extractor", ENTRY_ACTION),
        ("", "separator"),
        ("Open SidelineHD Extractor", ENTRY_ACTION),
        (f"Running on {_URL}", ENTRY_DISPLAY_ONLY),
        (_STAMP, ENTRY_DISPLAY_ONLY),
        ("", "separator"),
        ("Quit SidelineHD Extractor", ENTRY_ACTION),
    ]


def test_app_menu_update_entry_exists_exactly_when_a_tag_does():
    without = app_menu_entries(_URL, _STAMP)
    assert not any("Update available" in title for title, _ in without)
    entries = app_menu_entries(_URL, _STAMP, update_tag="v9.9.9")
    update_entry = (update_menu_title("v9.9.9"), ENTRY_ACTION)
    assert update_entry in entries
    # In the informational block: right after the stamp, before Quit.
    assert entries.index(update_entry) == entries.index((_STAMP, ENTRY_DISPLAY_ONLY)) + 1
    assert entries[-1] == ("Quit SidelineHD Extractor", ENTRY_ACTION)


def test_dock_menu_entries_and_update_item():
    assert dock_menu_entries(_URL) == [
        ("Open SidelineHD Extractor", ENTRY_ACTION),
        (f"Running on {_URL}", ENTRY_DISPLAY_ONLY),
    ]
    with_update = dock_menu_entries(_URL, update_tag="v1.2.3")
    assert with_update[-1] == (update_menu_title("v1.2.3"), ENTRY_ACTION)


def test_dock_menu_never_carries_its_own_quit():
    # macOS appends Quit to Dock menus itself; a model Quit would double it.
    for tag in (None, "v9.9.9"):
        assert not any(
            "Quit" in title for title, _ in dock_menu_entries(_URL, update_tag=tag)
        )


def test_status_and_stamp_lines_are_display_only():
    app_kinds = dict(app_menu_entries(_URL, _STAMP, update_tag="v9.9.9"))
    assert app_kinds[f"Running on {_URL}"] == ENTRY_DISPLAY_ONLY
    assert app_kinds[_STAMP] == ENTRY_DISPLAY_ONLY
    dock_kinds = dict(dock_menu_entries(_URL, update_tag="v9.9.9"))
    assert dock_kinds[f"Running on {_URL}"] == ENTRY_DISPLAY_ONLY


# --- Dock-first packaging and dependency guards (item 68b) -------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_spec_no_longer_marks_the_app_menubar_only():
    text = (_REPO_ROOT / "packaging" / "sidelinehd.spec").read_text(encoding="utf-8")
    assert "LSUIElement" not in text


def test_desktop_extra_swapped_rumps_for_pyobjc():
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "rumps" not in text
    assert "pyobjc-framework-Cocoa" in text


def test_desktop_module_keeps_gui_frameworks_out_of_module_scope():
    """The module must stay importable headless (CI, --selftest, this suite):
    AppKit may only be imported inside run_dock_app."""

    tree = ast.parse(Path(desktop.__file__).read_text(encoding="utf-8"))
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_level.add((node.module or "").split(".")[0])
    assert top_level.isdisjoint({"AppKit", "Cocoa", "objc", "rumps"})
