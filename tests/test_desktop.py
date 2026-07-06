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


def test_server_controller_start_raises_when_port_is_taken():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy_port = taken.getsockname()[1]
        controller = ServerController(port=busy_port, app_factory=lambda: _tiny_app)
        with pytest.raises(RuntimeError, match="failed to start"):
            controller.start()
        controller.stop()
