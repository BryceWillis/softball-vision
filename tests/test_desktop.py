"""Tests for the desktop menubar launcher plumbing (item 54d, phase 1).

The rumps UI itself is not tested (it needs a macOS GUI session); everything
around it — data dir, port picking, the uvicorn server thread — is.
"""

from __future__ import annotations

import os
import socket
import urllib.request
from pathlib import Path

import pytest

from sidelinehd_extractor import desktop
from sidelinehd_extractor.desktop import (
    ServerController,
    default_data_dir,
    desktop_pipeline_kwargs,
    find_open_port,
    prepare_data_dir,
)

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
    assert kwargs["auto_detect_batting_half"] is True
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
    monkeypatch.setattr(desktop, "ServerController", _DeadController)
    assert desktop.run_selftest() == 1
    assert "selftest: FAIL" in capsys.readouterr().err
    assert controllers and controllers[0].stopped


def test_main_selftest_flag_dispatches_without_starting_the_gui(monkeypatch):
    monkeypatch.setattr(desktop, "run_selftest", lambda: 7)

    def _must_not_run(*args, **kwargs):
        raise AssertionError("--selftest must not reach the launch path")

    monkeypatch.setattr(desktop, "prepare_data_dir", _must_not_run)
    monkeypatch.setattr(desktop, "run_menubar_app", _must_not_run)
    assert desktop.main(["--selftest"]) == 7


def test_main_starts_the_update_check_after_the_server_and_hands_it_to_the_menubar(
    monkeypatch,
):
    """Item 67d: the check starts only once the server is up (it must never
    block launch) and the menubar app receives it to poll."""

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

    def fake_menubar(controller, update_check=None):
        captured["update_check"] = update_check
        events.append("menubar")

    monkeypatch.setattr(desktop, "prepare_data_dir", lambda: events.append("data-dir"))
    monkeypatch.setattr(desktop, "find_open_port", lambda: 8000)
    monkeypatch.setattr(desktop, "ServerController", _Controller)
    monkeypatch.setattr(desktop, "UpdateCheck", lambda: check)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: events.append("browser"))
    monkeypatch.setattr(desktop, "run_menubar_app", fake_menubar)

    assert desktop.main([]) == 0
    assert captured["update_check"] is check
    assert events.index("server-start") < events.index("update-check-start")
    assert events.index("update-check-start") < events.index("menubar")


def test_server_controller_start_raises_when_port_is_taken():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy_port = taken.getsockname()[1]
        controller = ServerController(port=busy_port, app_factory=lambda: _tiny_app)
        with pytest.raises(RuntimeError, match="failed to start"):
            controller.start()
        controller.stop()
