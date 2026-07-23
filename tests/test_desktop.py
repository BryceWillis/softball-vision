"""Tests for the desktop Dock-app launcher plumbing (items 54d, 68b).

The AppKit UI itself is not tested (it needs a macOS GUI session); everything
below the GUI line — data dir, port picking, the uvicorn server thread, the
menu models the GUI renders — is.
"""

from __future__ import annotations

import ast
import os
import signal
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


def test_prepare_data_dir_creates_without_changing_cwd(tmp_path):
    # 70f retired the os.chdir: the data dir is created and returned to be
    # threaded as an explicit data_root, and the process CWD is left untouched
    # (App Sandbox and native file dialogs both break on a chdir).
    target = tmp_path / "nested" / "data-dir"
    with _RestoreCwd():
        before = Path.cwd()
        result = prepare_data_dir(target)
        assert result == target
        assert target.is_dir()
        assert Path.cwd() == before
        assert Path.cwd() != target


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


def test_desktop_pipeline_kwargs_reads_config_from_the_data_root(monkeypatch, tmp_path):
    """70f: the pipeline's roster/template come from the data dir passed in as
    ``data_root``, not from the launcher's CWD (no chdir any more)."""

    from sidelinehd_extractor import ocr as ocr_module
    from sidelinehd_extractor.config import ProjectConfig, write_project_config
    from sidelinehd_extractor.roster import default_roster_path, write_roster_csv
    from sidelinehd_extractor.roster import parse_team_list

    monkeypatch.setattr(ocr_module, "create_ocr_backend", lambda name: object())

    data_root = tmp_path / "data"
    data_root.mkdir()
    roster_path = default_roster_path("Blue Thunder", base=data_root)
    write_roster_csv(parse_team_list("#7 Zoe H.\n", team_name="Blue Thunder"), roster_path)
    write_project_config(
        ProjectConfig(roster=roster_path, team_name="Blue Thunder"), cwd=data_root
    )

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # CWD is deliberately *not* the data dir

    kwargs = desktop_pipeline_kwargs(data_root=data_root)
    assert kwargs["roster"] is not None
    assert kwargs["roster"].name_for_number("7") == "Zoe H."
    # And with no base, the same CWD (no config) yields no roster.
    assert desktop_pipeline_kwargs()["roster"] is None


def test_controller_points_the_app_at_its_data_dir(tmp_path):
    """70f: a controller given a data dir threads it to the app so rosters/
    runs/videos/config resolve there without an os.chdir."""

    data_dir = tmp_path / "data"
    controller = ServerController(port=8137, data_dir=data_dir)
    app = controller._default_app_factory()
    assert app.state.data_root == data_dir
    assert app.state.runner.output_dir == data_dir / "runs"
    # The launcher reads controller.store for the badge/quit confirmation.
    assert controller.store is app.state.store


def test_controller_without_a_data_dir_keeps_cwd_relative_defaults(tmp_path, monkeypatch):
    """No data dir (a from-source run) preserves the pre-70f behaviour exactly:
    the runner writes to the CWD-relative ``runs/``."""

    monkeypatch.chdir(tmp_path)
    controller = ServerController(port=8138)
    app = controller._default_app_factory()
    assert app.state.data_root is None
    assert app.state.runner.output_dir == Path("runs")


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
        lambda port, data_dir=None: ServerController(
            port=port, data_dir=data_dir, app_factory=lambda: app
        ),
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
        def __init__(self, port, data_dir=None):
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


class _FakeController:
    """Stands in for ServerController in the main() orchestration tests."""

    host = "127.0.0.1"

    def __init__(self, port, events=None):
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self._events = events if events is not None else []

    def start(self):
        self._events.append("server-start")

    def stop(self):
        self._events.append("server-stop")


def _patch_main_launch(monkeypatch, events, tmp_path):
    """Wire main()'s collaborators to fakes, leaving the record path real."""

    monkeypatch.setattr(
        desktop, "prepare_data_dir", lambda: events.append("data-dir") or tmp_path
    )
    # CR-95: deliberately *not* DEFAULT_PORT — a record built from the default
    # rather than the bound port is indistinguishable from a correct one when
    # the two are the same number, and `status` would then advertise a URL
    # nothing is listening on.
    monkeypatch.setattr(desktop, "find_open_port", lambda: 8123)
    monkeypatch.setattr(
        desktop,
        "ServerController",
        lambda port, data_dir=None: _FakeController(port, events),
    )
    monkeypatch.setattr(desktop, "UpdateCheck", lambda check=None: _NoopCheck())
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: events.append("browser"))
    monkeypatch.setattr(
        "sidelinehd_extractor.webapp.lifecycle.default_data_dir", lambda: tmp_path
    )
    # Item 70d: the present-path alert is the one thing a headless test must
    # never actually run. Recorded as "notice" so the present tests can assert
    # it fired; harmless on every other path, which never reaches it.
    monkeypatch.setattr(
        desktop, "_present_notice_modal", lambda title, body: events.append("notice")
    )


class _NoopCheck:
    def start(self):
        return None


def test_main_starts_the_update_check_after_the_server_and_hands_it_to_the_dock_app(
    monkeypatch, tmp_path
):
    """Item 67d: the check starts only once the server is up (it must never
    block launch) and the Dock app receives it to poll."""

    events = []

    class _Check:
        def start(self):
            events.append("update-check-start")

    check = _Check()
    captured = {}

    def fake_dock_app(controller, update_check=None, on_quit=None):
        captured["update_check"] = update_check
        events.append("dock-app")

    _patch_main_launch(monkeypatch, events, tmp_path)
    monkeypatch.setattr(desktop, "UpdateCheck", lambda **_kw: check)
    monkeypatch.setattr(desktop, "run_dock_app", fake_dock_app)

    assert desktop.main([]) == 0
    assert captured["update_check"] is check
    assert events.index("server-start") < events.index("update-check-start")
    assert events.index("update-check-start") < events.index("dock-app")


def test_launch_no_longer_opens_a_browser(monkeypatch, tmp_path):
    """Item 70b (D4): launch presents the app's own window. Opening a browser
    tab from the Dock app is the invention this milestone exists to retire —
    *"I've never used an app that when I click the icon in the Dock it opens a
    browser window."*

    ``_patch_main_launch`` records every ``webbrowser.open`` as ``"browser"``,
    so this asserts over the whole launch path rather than one call site.
    """

    events = []
    _patch_main_launch(monkeypatch, events, tmp_path)
    monkeypatch.setattr(
        desktop, "run_dock_app", lambda *a, **k: events.append("dock-app")
    )

    assert desktop.main([]) == 0
    assert "dock-app" in events
    assert "browser" not in events


# --- Lifecycle registration (item 70a) ---------------------------------------


def test_main_records_the_running_app_and_removes_it_on_quit(monkeypatch, tmp_path):
    """Item 70a: `status` and `stop` could not see the Dock app at all — the
    one server item 65's staleness defence did not cover."""

    from sidelinehd_extractor.webapp import lifecycle

    events = []
    seen = {}

    def fake_dock_app(controller, update_check=None, on_quit=None):
        seen["record"] = lifecycle.read_server_state(tmp_path / "webapp.json")
        on_quit()  # the applicationShouldTerminate_ path, without a GUI

    _patch_main_launch(monkeypatch, events, tmp_path)
    monkeypatch.setattr(desktop, "run_dock_app", fake_dock_app)

    assert desktop.main([]) == 0

    record = seen["record"]
    assert record is not None
    assert record.origin == lifecycle.ORIGIN_APP
    assert record.port == 8123  # the *actual* port, not desktop.DEFAULT_PORT
    assert record.data_dir == str(tmp_path)
    assert record.pid == os.getpid()
    # Quit removes it, so the next `status` says "not running" rather than
    # naming a server that stopped an hour ago.
    assert not (tmp_path / "webapp.json").exists()


def test_main_removes_the_record_even_when_the_gui_never_reaches_quit(
    monkeypatch, tmp_path
):
    """The source-run path and any startup failure clean up too: main()'s
    finally is the only cleanup those get, and Cocoa's terminate: is the only
    one the bundle gets — so both exist and both are idempotent."""

    events = []

    def fake_dock_app(controller, update_check=None, on_quit=None):
        raise RuntimeError("no GUI session")

    _patch_main_launch(monkeypatch, events, tmp_path)
    monkeypatch.setattr(desktop, "run_dock_app", fake_dock_app)

    with pytest.raises(RuntimeError):
        desktop.main([])
    assert not (tmp_path / "webapp.json").exists()


def test_the_app_presents_a_live_recorded_server_instead_of_starting_a_rival(
    monkeypatch, tmp_path
):
    """Item 70d (D6): with a live, healthy server already recorded, a second
    launch presents *that* server — opens it in the browser and exits, having
    started nothing and touched no record. This replaces 70a's honest interim
    (serve-unregistered): the copied-`.app` case and the running-CLI-server
    case now both hand off rather than start a rival."""

    from sidelinehd_extractor.webapp import lifecycle

    events = []
    incumbent = lifecycle.new_server_state(
        "127.0.0.1", 8000, pid=777, version="0.test", data_dir="/checkout"
    )
    lifecycle.write_server_state(incumbent, tmp_path / "webapp.json")

    _patch_main_launch(monkeypatch, events, tmp_path)
    # The health probe is injected, so no test binds a socket or probes a PID.
    monkeypatch.setattr(desktop, "server_is_healthy", lambda record: True)

    def _must_not_start(*args, **kwargs):
        raise AssertionError("the present path must not start a server or a GUI")

    monkeypatch.setattr(desktop, "run_dock_app", _must_not_start)

    assert desktop.main([]) == 0

    # It handed off and got out of the way: notice shown, browser opened, and
    # no server ever started.
    assert "notice" in events
    assert "browser" in events
    assert "server-start" not in events
    # The running server's record is left exactly as it was — the present
    # instance neither claims nor removes it.
    assert lifecycle.read_server_state(tmp_path / "webapp.json") == incumbent


def test_a_dead_or_wedged_record_is_cleared_and_the_app_starts(monkeypatch, tmp_path):
    """Item 70d (D6): a record whose server is alive-but-wedged (PID up, `GET /`
    failing) is cleared so this launch can take over — proven by the app's own
    record replacing it. Without the clear, `claim_server_record` would decline
    to overwrite a live PID and the app would serve unregistered instead."""

    from sidelinehd_extractor.webapp import lifecycle

    events = []
    seen = {}
    wedged = lifecycle.new_server_state(
        "127.0.0.1", 8000, pid=999, version="0.old", data_dir="/gone"
    )
    lifecycle.write_server_state(wedged, tmp_path / "webapp.json")

    def fake_dock_app(controller, update_check=None, on_quit=None):
        # Capture the record before main()'s finally removes it on the way out.
        seen["record"] = lifecycle.read_server_state(tmp_path / "webapp.json")

    _patch_main_launch(monkeypatch, events, tmp_path)
    # Alive (so an un-cleared claim would decline) but wedged (so the decision
    # is clear-and-start, not present).
    monkeypatch.setattr(lifecycle, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(desktop, "server_is_healthy", lambda record: False)
    monkeypatch.setattr(desktop, "run_dock_app", fake_dock_app)

    assert desktop.main([]) == 0
    assert "server-start" in events

    record = seen["record"]
    assert record is not None
    assert record.origin == lifecycle.ORIGIN_APP
    assert record.port == 8123  # our port, not the wedged record's 8000
    assert record.pid == os.getpid()  # ours replaced pid 999 — the clear worked


def test_register_server_record_declines_a_live_foreign_record(
    monkeypatch, tmp_path, capsys
):
    """The defence-in-depth behind 70d's present path: even if a live foreign
    server appears between the launch decision and the claim, registration
    refuses to erase its record and serves unregistered instead (item 70a).

    Kept as a direct unit test now that 70d's present path means main() no
    longer reaches this branch on the ordinary CLI-server collision. CR-93: the
    PID is a foreign literal with the liveness check injected — never a real
    one, which on Windows `os.kill` would `TerminateProcess`."""

    from sidelinehd_extractor.webapp import lifecycle

    incumbent = lifecycle.new_server_state(
        "127.0.0.1", 8000, pid=777, version="0.test", data_dir="/checkout"
    )
    lifecycle.write_server_state(incumbent, tmp_path / "webapp.json")

    asked = []

    def _alive(pid):
        asked.append(pid)
        return True

    monkeypatch.setattr(lifecycle, "is_pid_alive", _alive)

    result = desktop.register_server_record(
        _FakeController(8123), tmp_path, path=tmp_path / "webapp.json"
    )

    assert result is None  # declined — served unregistered
    assert asked == [777], "the injected liveness check was bypassed"
    assert lifecycle.read_server_state(tmp_path / "webapp.json") == incumbent
    err = capsys.readouterr().err
    assert "already running" in err
    assert "PID 777" in err


def test_a_failed_record_write_warns_but_still_launches(monkeypatch, tmp_path, capsys):
    """A launcher must never fail to launch over metadata (the M1 rule): the
    record is a defence, not a dependency."""

    events = []
    _patch_main_launch(monkeypatch, events, tmp_path)
    monkeypatch.setattr(
        "sidelinehd_extractor.webapp.lifecycle.claim_server_record",
        lambda state, path=None, **kwargs: (_ for _ in ()).throw(
            PermissionError("read-only data dir")
        ),
    )
    monkeypatch.setattr(
        desktop, "run_dock_app", lambda controller, update_check=None, on_quit=None: None
    )

    assert desktop.main([]) == 0
    assert "dock-app" not in events  # the fake never appends; the launch ran
    assert events.count("server-start") == 1
    assert "could not record this server" in capsys.readouterr().err


def test_register_server_record_uses_the_build_stamp_version(monkeypatch, tmp_path):
    """A frozen bundle has no distribution metadata to read — importlib
    reports "unknown" — so the 67a build stamp is the version of record."""

    from sidelinehd_extractor.build_info import BuildStamp

    monkeypatch.setattr(
        desktop,
        "build_stamp",
        lambda: BuildStamp(version="9.9.9", sha="abc1234", built_at=None, origin="bundle"),
    )
    record = desktop.register_server_record(
        _FakeController(8123), tmp_path, path=tmp_path / "webapp.json"
    )

    assert record is not None
    assert record.version == "9.9.9"


def test_release_server_record_never_removes_someone_elses(tmp_path):
    from sidelinehd_extractor.webapp import lifecycle

    path = tmp_path / "webapp.json"
    theirs = lifecycle.new_server_state("127.0.0.1", 8000, pid=4242, version="0.test")
    lifecycle.write_server_state(theirs, path)
    ours = lifecycle.new_server_state("127.0.0.1", 8001, pid=5555, version="0.test")

    desktop.release_server_record(ours, path)
    assert lifecycle.read_server_state(path) == theirs

    # Ours goes, and going twice is not an error.
    lifecycle.write_server_state(ours, path)
    desktop.release_server_record(ours, path)
    desktop.release_server_record(ours, path)
    assert not path.exists()

    desktop.release_server_record(None, path)  # nothing claimed, nothing to do


def test_selftest_never_writes_a_server_record(monkeypatch, tmp_path):
    """--selftest is a smoke test, not a server: a record would make `status`
    and `stop` name a process that has already exited."""

    _point_selftest_at(monkeypatch, tmp_path, _tiny_app)
    monkeypatch.setattr(
        "sidelinehd_extractor.webapp.lifecycle.default_data_dir", lambda: tmp_path
    )

    assert desktop.run_selftest() == 0
    assert not (tmp_path / "webapp.json").exists()


# --- SIGTERM as a non-interactive quit (item 70a, D5) ------------------------


def test_sigterm_handler_takes_the_graceful_path_and_flags_it_non_interactive():
    """`stop` must funnel into the same applicationShouldTerminate: every
    other quit uses — and 70c must be able to tell that nobody is at the
    screen to answer a dialog."""

    context = desktop.QuitContext()
    assert context.interactive  # a normal quit is interactive until told otherwise

    terminated = []
    installed = {}
    handler = desktop.install_sigterm_quit_handler(
        lambda: terminated.append("terminate"),
        context,
        install=lambda signum, fn: installed.update(signum=signum, fn=fn),
    )

    assert installed["signum"] == signal.SIGTERM
    assert installed["fn"] is handler

    handler(signal.SIGTERM, None)
    assert terminated == ["terminate"]
    assert not context.interactive


def test_quit_context_stays_interactive_without_a_signal():
    # The flag is set by the signal handler and nowhere else: a stray setter
    # would silently disarm 70c's confirmation for ⌘Q too.
    assert desktop.QuitContext().interactive


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
        ("Open in Browser", ENTRY_ACTION),
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
        ("Open in Browser", ENTRY_ACTION),
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


def test_open_in_browser_sits_beside_open_in_both_menus():
    """D4: the window replaces the browser auto-open, so the browser has to be
    reachable in one click — and from the same place in both menus."""

    app_titles = [title for title, _ in app_menu_entries(_URL, _STAMP)]
    dock_titles = [title for title, _ in dock_menu_entries(_URL)]
    for titles in (app_titles, dock_titles):
        assert titles.index("Open in Browser") == titles.index(
            "Open SidelineHD Extractor"
        ) + 1
    # Both are clickable — a display-only "Open in Browser" would be a
    # convincing-looking no-op.
    assert dict(app_menu_entries(_URL, _STAMP))["Open in Browser"] == ENTRY_ACTION
    assert dict(dock_menu_entries(_URL))["Open in Browser"] == ENTRY_ACTION


# --- The Edit and Window menus (item 70b) ------------------------------------


def test_edit_menu_wires_the_clipboard_selectors():
    """The Edit menu is what makes ⌘C work inside a WKWebView: in AppKit the
    key equivalents come from the menu, so without it manual copy is dead — in
    a tool whose entire output is copy-paste kits."""

    entries = desktop.edit_menu_entries()
    by_selector = {selector: (title, key) for title, selector, key in entries}
    assert by_selector["copy:"] == ("Copy", "c")
    assert by_selector["paste:"] == ("Paste", "v")
    assert by_selector["cut:"] == ("Cut", "x")
    assert by_selector["selectAll:"] == ("Select All", "a")
    # ⇧⌘Z, the standard Redo equivalent — an uppercase key equivalent is how
    # AppKit spells the shift.
    assert by_selector["redo:"] == ("Redo", "Z")


def test_window_menu_closes_the_window_on_command_w():
    entries = desktop.window_menu_entries()
    by_selector = {selector: (title, key) for title, selector, key in entries}
    # performClose: closes the window; D3 is what stops that quitting the app.
    assert by_selector["performClose:"] == ("Close", "w")
    assert by_selector["performMiniaturize:"] == ("Minimize", "m")


def test_standard_menu_entries_are_all_first_responder_selectors():
    """These carry no target: they travel the responder chain to the web view,
    which is the whole mechanism. A selector that is not a real AppKit action
    would silently grey out instead."""

    for entries in (desktop.edit_menu_entries(), desktop.window_menu_entries()):
        for title, selector, _key in entries:
            if selector == desktop.ENTRY_SEPARATOR:
                assert title == ""
                continue
            assert selector.endswith(":"), selector
            assert title


# --- Navigation policy (item 70b, D4) ----------------------------------------
#
# The classifier that keeps our page in the window and sends everything else to
# the real browser, where the user's YouTube and GitHub logins are.

_APP_URL = "http://127.0.0.1:8123"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8123",
        "http://127.0.0.1:8123/",
        "http://127.0.0.1:8123/jobs/abc/review",
        "http://127.0.0.1:8123/feedback?sent=1",
        "http://127.0.0.1:8123/rosters#anchor",
    ],
)
def test_our_own_pages_stay_in_the_window(url):
    assert desktop.navigation_opens_in_window(url, _APP_URL)


@pytest.mark.parametrize(
    "url",
    [
        # Item 63's review-row deep links: the flow that most needs the user's
        # real browser, logged in, with a back button.
        "https://www.youtube.com/watch?v=abc123&t=95s",
        "https://github.com/BryceWillis/softball-vision/issues/new",
        "mailto:someone@example.com?subject=feedback",
        "https://127.0.0.1:8123/",  # same host and port, different scheme
        "http://127.0.0.1:8124/",  # a different local server
        "http://localhost:8123/",  # a different host string is a different origin
        "file:///etc/passwd",
    ],
)
def test_everything_else_goes_to_the_browser(url):
    assert not desktop.navigation_opens_in_window(url, _APP_URL)


@pytest.mark.parametrize(
    "url", ["", "about:blank", "data:text/html,<p>hi", "blob:null/abc", "javascript:void(0)"]
)
def test_view_internal_schemes_are_never_handed_to_the_browser(url):
    """These are loads the view performs on itself. Handing one off would open
    a browser tab on nothing."""

    assert desktop.navigation_opens_in_window(url, _APP_URL)


def test_default_ports_make_one_origin_not_two():
    assert desktop.navigation_opens_in_window("http://example.test/", "http://example.test:80")
    assert desktop.navigation_opens_in_window("https://example.test:443/a", "https://example.test")


def test_a_malformed_port_does_not_raise():
    """A launcher must never fail over metadata — and urlsplit raises on
    `.port` for a non-numeric port rather than returning None."""

    assert not desktop.navigation_opens_in_window("http://127.0.0.1:notaport/", _APP_URL)


def test_navigation_action_url_survives_an_action_with_no_url():
    class _NoURL:
        def request(self):
            return self

        def URL(self):
            return None

    assert desktop._navigation_action_url(_NoURL()) == ""
    assert desktop._navigation_action_url(object()) == ""
    # And "" classifies as in-view, so an unreadable action allows the load
    # rather than opening the browser on an empty string.
    assert desktop.navigation_opens_in_window("", _APP_URL)


# --- Single instance and port truth (item 70d, D6) --------------------------
#
# The launch decision and the notice are pure functions — the alert and the
# browser call are the thin render layer around them — so the whole contract
# is tested here without binding a socket or presenting a modal.


class _FakeResponse:
    """A stand-in for the urlopen context manager the health probe uses."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _record(origin=None, data_dir="/checkout", pid=777, version="0.5.0",
            started_at="2026-07-22T09:14:00Z"):
    from sidelinehd_extractor.webapp import lifecycle

    return lifecycle.new_server_state(
        "127.0.0.1",
        8000,
        pid=pid,
        version=version,
        started_at=started_at,
        origin=origin or lifecycle.ORIGIN_CLI,
        data_dir=data_dir,
    )


def test_launch_decision_starts_when_there_is_no_record():
    def _must_not_probe(record):
        raise AssertionError("no record means no probe")

    assert desktop.launch_decision(None, _must_not_probe) == desktop.LAUNCH_START


def test_launch_decision_presents_a_live_healthy_server():
    assert (
        desktop.launch_decision(_record(), lambda record: True)
        == desktop.LAUNCH_PRESENT
    )


def test_launch_decision_clears_a_dead_or_wedged_record():
    assert (
        desktop.launch_decision(_record(), lambda record: False)
        == desktop.LAUNCH_CLEAR_AND_START
    )


def test_launch_decision_ignores_data_dir_and_presents_regardless():
    """The regression guard for the rule this slice corrected (D6): a record
    whose data dir differs from ours must still resolve to *present*. Branching
    on data_dir is what made the CLI-server collision unreachable in the first
    draft — the CLI's data dir is its CWD and the app's never is."""

    from sidelinehd_extractor.webapp import lifecycle

    foreign = _record(origin=lifecycle.ORIGIN_CLI, data_dir="/some/other/checkout")
    assert (
        desktop.launch_decision(foreign, lambda record: True)
        == desktop.LAUNCH_PRESENT
    )


def test_server_is_healthy_needs_both_a_live_pid_and_a_200(monkeypatch):
    from sidelinehd_extractor.webapp import lifecycle

    record = _record(pid=4242)

    # Dead PID: never even probed over the network.
    monkeypatch.setattr(lifecycle, "is_pid_alive", lambda pid: False)

    def _must_not_probe(*args, **kwargs):
        raise AssertionError("a dead PID must not be probed")

    monkeypatch.setattr(desktop.urllib.request, "urlopen", _must_not_probe)
    assert desktop.server_is_healthy(record) is False

    # Alive + 200 → healthy.
    monkeypatch.setattr(lifecycle, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(
        desktop.urllib.request, "urlopen", lambda url, timeout=None: _FakeResponse(200)
    )
    assert desktop.server_is_healthy(record) is True

    # Alive but wedged (non-200) → not healthy: PID-alive alone is not enough.
    monkeypatch.setattr(
        desktop.urllib.request, "urlopen", lambda url, timeout=None: _FakeResponse(503)
    )
    assert desktop.server_is_healthy(record) is False

    # Alive but the probe raises (connection refused, timeout) → not healthy.
    def _boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(desktop.urllib.request, "urlopen", _boom)
    assert desktop.server_is_healthy(record) is False


def test_present_notice_always_names_the_version_and_start_time():
    notice = desktop.present_notice(_record(version="0.5.0"), "/our/data")
    assert "0.5.0" in notice
    assert "2026-07-22 09:14" in notice  # the ISO record, made readable
    assert "Opening it in your browser" in notice


def test_present_notice_names_the_folder_only_when_it_differs():
    from sidelinehd_extractor.webapp import lifecycle

    differs = desktop.present_notice(_record(data_dir="/checkout"), "/our/data")
    assert "serving" in differs
    assert lifecycle.display_path("/checkout") in differs

    same = desktop.present_notice(_record(data_dir="/our/data"), "/our/data")
    assert "serving" not in same


def test_present_notice_remedy_varies_with_origin():
    from sidelinehd_extractor.webapp import lifecycle

    cli = desktop.present_notice(_record(origin=lifecycle.ORIGIN_CLI), "/our/data")
    assert "Terminal" in cli
    assert "sidelinehd-extractor stop" in cli

    # The app case, asserted against a matching data dir (the acceptance path):
    # the folder clause is absent, so the remedy is the only thing left to be
    # wrong — and it must name the Dock and ⌘Q, and *neither* a Terminal nor
    # the CLI command a downloaded `.app` has no way to run.
    app = desktop.present_notice(
        _record(origin=lifecycle.ORIGIN_APP, data_dir="/our/data"), "/our/data"
    )
    assert "Dock" in app
    assert "⌘Q" in app
    assert "Terminal" not in app
    assert "sidelinehd-extractor" not in app
    assert "serving" not in app


def test_present_notice_survives_an_old_format_record():
    """70a tolerates a record with `origin` and `data_dir` missing (defaulted);
    the notice must too — no crash, the CLI sentence (nothing before 70a wrote
    an app record), and the version and start time still shown."""

    from sidelinehd_extractor.webapp import lifecycle

    old = _record(origin=lifecycle.ORIGIN_CLI, data_dir="", version="0.4.0")
    notice = desktop.present_notice(old, "/our/data")
    assert "0.4.0" in notice
    assert "2026-07-22 09:14" in notice
    assert "serving" not in notice  # no data_dir to name
    assert "sidelinehd-extractor stop" in notice  # the CLI remedy


def test_friendly_started_at_falls_back_to_the_raw_string():
    # A launcher must never fail over metadata: an unparseable timestamp is
    # shown as-is rather than raising.
    assert desktop._friendly_started_at("not-a-timestamp") == "not-a-timestamp"
    assert desktop._friendly_started_at("2026-07-22T09:14:00Z") == "2026-07-22 09:14"


def test_present_running_server_hands_off_even_if_the_alert_cannot_show(
    monkeypatch,
):
    """The M1 rule: a modal that cannot be presented must not become a hand-off
    that cannot happen. The browser opens either way."""

    opened = []

    def _broken_modal(title, body):
        raise RuntimeError("no GUI session")

    monkeypatch.setattr(desktop, "_present_notice_modal", _broken_modal)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url))

    desktop.present_running_server(_record(), "/our/data")
    assert opened == ["http://127.0.0.1:8000"]


# --- Long-run visibility (item 70c) ------------------------------------------
#
# The Dock badge and the quit-mid-run confirmation are pure functions over job
# state, so the whole contract — including "SIGTERM never asks", the one rule
# whose failure silently disarms the dialog for ⌘Q too — is tested here rather
# than clicked through on a bundle.


def _job(status="running", frames_done=0, frames_total=0, job_id="j1"):
    from sidelinehd_extractor.webapp.jobs import Job

    return Job(
        id=job_id,
        kind="single",
        url="https://youtu.be/example",
        status=status,
        frames_done=frames_done,
        frames_total=frames_total,
    )


def test_badge_shows_the_read_percentage():
    """The OCR percentage is the number worth showing: it is the half-hour
    the user is actually waiting on."""

    assert desktop.badge_label(_job(frames_done=4900, frames_total=10000)) == "49%"
    assert desktop.badge_label(_job(frames_done=0, frames_total=10000)) == "0%"
    assert desktop.badge_label(_job(frames_done=10000, frames_total=10000)) == "100%"


def test_badge_falls_back_to_an_activity_mark_without_counts():
    """Downloading, and every stage before OCR, has no frame counts — but the
    app is not idle and the tile must not say it is."""

    assert desktop.badge_label(_job(frames_total=0)) == desktop.BADGE_ACTIVITY_MARK
    # A queued job is work accepted and not yet done, not idleness.
    assert desktop.badge_label(_job(status="queued")) == desktop.BADGE_ACTIVITY_MARK


def test_badge_clears_when_nothing_is_running():
    """Clearing is the *guaranteed* completion signal — the one that works
    whether or not the OS lets an ad-hoc-signed bundle post a notification."""

    assert desktop.badge_label(None) is None
    assert desktop.badge_label(_job(status="done", frames_done=99, frames_total=99)) is None
    assert desktop.badge_label(_job(status="error")) is None


def test_badge_percentage_never_exceeds_100():
    """Playlist jobs reset the counts per entry (documented Job behaviour), so
    a stale frames_done can briefly outrun the new total."""

    assert desktop.badge_label(_job(frames_done=1200, frames_total=800)) == "100%"


def test_active_job_prefers_the_running_one_over_a_queued_one():
    """JobStore.list() is newest-first, so a second submission sits ahead of
    the job actually being worked on."""

    queued = _job(status="queued", job_id="new")
    running = _job(frames_done=1, frames_total=10, job_id="old")
    assert desktop.active_job([queued, running]) is running


def test_active_job_falls_back_to_the_newest_pending_job():
    newest = _job(status="queued", job_id="new")
    older = _job(status="queued", job_id="old")
    assert desktop.active_job([newest, older]) is newest


def test_active_job_is_none_when_every_job_has_finished():
    assert desktop.active_job([]) is None
    assert desktop.active_job([_job(status="done"), _job(status="error", job_id="j2")]) is None


def test_quit_asks_when_a_read_is_in_flight():
    for status in ("queued", "running"):
        assert desktop.should_confirm_quit([_job(status=status)], interactive=True)


def test_quit_asks_nothing_when_no_job_is_running():
    assert not desktop.should_confirm_quit([], interactive=True)
    assert not desktop.should_confirm_quit([_job(status="done")], interactive=True)
    assert not desktop.should_confirm_quit([_job(status="error")], interactive=True)


def test_sigterm_never_asks_even_mid_run():
    """D5, and the rule this slice most needs pinned: a dialog raised in answer
    to `stop` can only be dismissed by someone who is not looking at that
    screen, so it would stall the quit until the CLI's timer killed the app —
    a SIGKILL mid-frame, which is worse for the run than the graceful stop the
    dialog exists to protect."""

    for status in ("queued", "running", "done", "error"):
        assert not desktop.should_confirm_quit([_job(status=status)], interactive=False)


def test_quit_confirmation_reads_the_70a_flag_the_signal_handler_sets():
    """End to end over the two 70a/70c pieces: the flag is set by the SIGTERM
    handler and nowhere else, and it is what disarms the dialog."""

    context = desktop.QuitContext()
    jobs = [_job(status="running")]
    assert desktop.should_confirm_quit(jobs, interactive=context.interactive)

    desktop.install_sigterm_quit_handler(
        lambda: None, context, install=lambda signum, fn: None
    )(signal.SIGTERM, None)
    assert not desktop.should_confirm_quit(jobs, interactive=context.interactive)


def test_quit_confirmation_copy_names_the_consequence():
    """Plain language, per the milestone rule: the user is being asked to weigh
    forty minutes of work, so the dialog has to say that is what is at stake —
    not "are you sure?"."""

    assert desktop.QUIT_CONFIRM_MESSAGE == "A game is still being read. Quit anyway?"
    assert "won't produce timestamps" in desktop.QUIT_CONFIRM_DETAIL
    assert (desktop.QUIT_CONFIRM_QUIT_TITLE, desktop.QUIT_CONFIRM_CANCEL_TITLE) == (
        "Quit",
        "Cancel",
    )


def test_newly_finished_announces_each_job_exactly_once():
    seen = {}
    running = _job(status="running")
    assert desktop.newly_finished([running], seen) == []

    done = _job(status="done")
    assert desktop.newly_finished([done], seen) == [done]
    # Still there on the next tick, and already announced.
    assert desktop.newly_finished([done], seen) == []


def test_newly_finished_ignores_a_job_first_seen_already_terminal():
    """A false "your game is ready" is worse than a missing one."""

    assert desktop.newly_finished([_job(status="done")], {}) == []


def test_newly_finished_announces_failures_too():
    seen = {}
    desktop.newly_finished([_job(status="running")], seen)
    error = _job(status="error")
    assert desktop.newly_finished([error], seen) == [error]
    # CR-95 (ride-along): the `error` half must announce exactly *once*, like
    # the `done` half above. An `error` job stays terminal on every 1s badge
    # tick, so if `error` ever fell out of `_TERMINAL_STATUSES` (e.g. narrowed
    # to `{"done"}`, or a third terminal status added to `Job.is_terminal` and
    # not here) it would post "that game didn't finish" once a second forever —
    # the notification storm the slice's own edge case forbids. This second
    # call is the assertion that kills that mutant.
    assert desktop.newly_finished([error], seen) == []


def test_completion_notification_is_honest_about_a_failed_run():
    """A coach who waited forty minutes needs to be told it did not work just
    as much as they need to be told it did."""

    title, body = desktop.completion_notification(_job(status="done"))
    assert title == "Your game is ready"
    assert body

    failed_title, failed_body = desktop.completion_notification(_job(status="error"))
    assert failed_title != title
    assert "didn't finish" in failed_title
    assert failed_body


def test_controller_exposes_the_job_store_it_builds(monkeypatch):
    """70c reads job state in-process (controller.store) rather than adding an
    HTTP surface — the launcher and the server are one process."""

    from sidelinehd_extractor.webapp import jobs as jobs_module

    controller = ServerController(port=8199)
    assert controller.store is None  # nothing built yet

    built = controller._app_factory()
    assert isinstance(controller.store, jobs_module.JobStore)
    assert built is not None


def test_a_controller_with_a_custom_app_factory_has_no_store():
    """The badge and the confirmation must degrade to "nothing is running"
    rather than assume a store is there — a blank tile and a quit that does
    not ask, which is the safe reading."""

    controller = ServerController(port=8199, app_factory=lambda: _tiny_app)
    controller._app_factory()
    assert controller.store is None


# --- Dock-first packaging and dependency guards (item 68b) -------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_spec_no_longer_marks_the_app_menubar_only():
    text = (_REPO_ROOT / "packaging" / "sidelinehd.spec").read_text(encoding="utf-8")
    assert "LSUIElement" not in text


def test_desktop_extra_swapped_rumps_for_pyobjc():
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "rumps" not in text
    assert "pyobjc-framework-Cocoa" in text
    # Item 70b: the window is a system WKWebView, so the extra must carry it —
    # otherwise run_dock_app raises ImportError on the first launch after a
    # source install and the app never appears at all.
    assert "pyobjc-framework-WebKit" in text
    # Item 70c: "your game is ready". Best-effort at runtime, but the extra is
    # where it has to be declared or the bundle cannot post one at all.
    assert "pyobjc-framework-UserNotifications" in text


def test_desktop_module_keeps_gui_frameworks_out_of_module_scope():
    """The module must stay importable headless (CI, --selftest, this suite):
    AppKit, WebKit, and UserNotifications may only be imported inside
    run_dock_app."""

    tree = ast.parse(Path(desktop.__file__).read_text(encoding="utf-8"))
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_level.add((node.module or "").split(".")[0])
    assert top_level.isdisjoint(
        {"AppKit", "Cocoa", "WebKit", "UserNotifications", "objc", "rumps"}
    )
