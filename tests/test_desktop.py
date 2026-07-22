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
        desktop, "ServerController", lambda port: _FakeController(port, events)
    )
    monkeypatch.setattr(desktop, "UpdateCheck", lambda: _NoopCheck())
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: events.append("browser"))
    monkeypatch.setattr(
        "sidelinehd_extractor.webapp.lifecycle.default_data_dir", lambda: tmp_path
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
    monkeypatch.setattr(desktop, "UpdateCheck", lambda: check)
    monkeypatch.setattr(desktop, "run_dock_app", fake_dock_app)

    assert desktop.main([]) == 0
    assert captured["update_check"] is check
    assert events.index("server-start") < events.index("update-check-start")
    assert events.index("update-check-start") < events.index("dock-app")


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


def test_the_app_does_not_erase_a_live_cli_servers_record(monkeypatch, tmp_path, capsys):
    """The honest interim until 70d presents the running server instead of
    starting a rival: serve, say so, and leave `status` naming the CLI one."""

    from sidelinehd_extractor.webapp import lifecycle

    events = []
    # An arbitrary *foreign* PID with the liveness check injected — never a real
    # one. CR-93: `is_pid_alive` probes with `os.kill(pid, 0)`, which on Windows
    # is not a probe but `TerminateProcess`, so handing it a genuinely live PID
    # would kill pytest's parent on the windows-latest CI leg. os.getpid() would
    # read as "our own record" and be rewritten, which is the other case.
    incumbent = lifecycle.new_server_state(
        "127.0.0.1", 8000, pid=777, version="0.test", data_dir="/checkout"
    )
    lifecycle.write_server_state(incumbent, tmp_path / "webapp.json")

    # CR-91's seam, earning its keep: `claim_server_record` resolves `alive` at
    # call time, so this replacement is reachable. The `asked` list is what makes
    # a bypass loud rather than silent — an unasserted monkeypatch is how CR-91
    # hid for a whole review pass.
    asked = []

    def _alive(pid):
        asked.append(pid)
        return True

    monkeypatch.setattr(lifecycle, "is_pid_alive", _alive)

    _patch_main_launch(monkeypatch, events, tmp_path)
    monkeypatch.setattr(
        desktop, "run_dock_app", lambda controller, update_check=None, on_quit=None: None
    )

    assert desktop.main([]) == 0

    assert asked == [777], "the injected liveness check was bypassed"
    # Untouched, including through our own quit-time cleanup.
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
