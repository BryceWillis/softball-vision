"""Menubar desktop launcher for the local web app (item 54d, phase 1).

Runs the same FastAPI app as ``sidelinehd-extractor start`` but as a macOS
menubar app (via ``rumps``) instead of a terminal process: Open / Status /
Quit, no terminal required. This module is the entrypoint the PyInstaller
``.app`` bundle wraps (see ``packaging/``), and it also works from source:

    python -m sidelinehd_extractor.desktop

Everything except ``run_menubar_app`` is import-safe headless (no ``rumps``,
no GUI) so the server-thread and data-dir logic stay unit-testable.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Sequence

from sidelinehd_extractor.build_info import build_stamp, stamp_label

APP_NAME = "SidelineHD Extractor"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
#: How many consecutive ports to try when the default is taken (a second
#: launch or another local app); the menubar app has no terminal to print a
#: "pick another port" error to, so it must find one itself.
PORT_ATTEMPTS = 10

_SERVER_START_TIMEOUT_SECONDS = 15.0
_SERVER_STOP_TIMEOUT_SECONDS = 10.0


def default_data_dir() -> Path:
    """The per-user data dir the desktop app runs in.

    A double-clicked ``.app`` starts with CWD ``/``, but the web app resolves
    ``rosters/``, ``runs/``, ``videos/``, and ``sidelinehd.cfg`` relative to
    CWD — so the desktop entrypoint chdirs somewhere stable and findable.
    """

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    # Non-mac fallback so the module stays runnable/testable everywhere;
    # the packaged bundle itself is macOS-only (Windows is item 19).
    return Path.home() / f".{APP_NAME.lower().replace(' ', '-')}"


def prepare_data_dir(data_dir: Optional[Path] = None) -> Path:
    """Create the data dir, chdir into it, and point OCR at bundled tessdata."""

    target = (data_dir or default_data_dir()).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    os.chdir(target)
    _configure_bundled_tessdata()
    return target


def _configure_bundled_tessdata() -> None:
    """Point libtesseract at the bundle's ``tessdata/`` when frozen.

    The ``.app`` ships ``eng.traineddata`` (the tesserocr wheel embeds
    libtesseract but no language data). A user-set ``TESSDATA_PREFIX``
    always wins.
    """

    if not getattr(sys, "frozen", False):
        return
    bundle_dir = Path(getattr(sys, "_MEIPASS", "") or Path(sys.executable).parent)
    tessdata = bundle_dir / "tessdata"
    if tessdata.is_dir():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))


def desktop_pipeline_kwargs() -> dict:
    """Job pipeline kwargs for the bundled app.

    Mirrors ``jobs.default_pipeline_kwargs`` except the OCR backend is
    requested as ``tesserocr`` — the bundle ships the self-contained
    tesserocr wheel instead of a Tesseract CLI binary. ``create_ocr_backend``
    already falls back to the CLI backend when tesserocr is not importable
    (running from source), so this is safe in both worlds.
    """

    from sidelinehd_extractor.config import (
        load_overlay_template,
        load_project_config,
        load_roster,
    )
    from sidelinehd_extractor.ocr import create_ocr_backend

    config = load_project_config()
    template = load_overlay_template(config.template) if config.template else None
    roster = (
        load_roster(config.roster, team_name=config.team_name) if config.roster else None
    )
    return {
        "template": template,
        "roster": roster,
        "ocr": create_ocr_backend("tesserocr"),
        "auto_detect_batting_half": True,
    }


def find_open_port(
    host: str = DEFAULT_HOST, start_port: int = DEFAULT_PORT, attempts: int = PORT_ATTEMPTS
) -> int:
    """Return the first bindable port at or after ``start_port``."""

    for port in range(start_port, start_port + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
        return port
    raise RuntimeError(
        f"no open port found on {host} in {start_port}..{start_port + attempts - 1}"
    )


class ServerController:
    """Runs uvicorn on a daemon thread so a GUI can start/stop it.

    ``uvicorn.run`` (what the CLI uses) installs signal handlers and blocks
    the main thread; a menubar app needs the main thread for the GUI, so
    this drives ``uvicorn.Server`` directly and stops it by setting
    ``should_exit`` — the graceful path uvicorn's own signal handler uses.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        app_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self._app_factory = app_factory or self._default_app_factory
        self._server = None
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _default_app_factory() -> object:
        from sidelinehd_extractor.webapp.app import create_app
        from sidelinehd_extractor.webapp.jobs import JobRunner, JobStore

        store = JobStore()
        runner = JobRunner(store, pipeline_kwargs=desktop_pipeline_kwargs)
        return create_app(store=store, runner=runner)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, timeout: float = _SERVER_START_TIMEOUT_SECONDS) -> None:
        """Start serving; returns once the server accepts connections.

        Raises ``RuntimeError`` if the server thread dies during startup
        (e.g. the port was taken between the probe and the bind) or does not
        come up within ``timeout``.
        """

        import uvicorn

        if self.running:
            return
        config = uvicorn.Config(
            self._app_factory(), host=self.host, port=self.port, log_level="warning"
        )
        self._server = uvicorn.Server(config)

        def _run_server() -> None:
            try:
                self._server.run()
            except SystemExit:
                # uvicorn sys.exit(1)s the thread when startup fails (e.g.
                # port taken); start() detects the dead thread and reports.
                pass

        self._thread = threading.Thread(
            target=_run_server, name="sidelinehd-desktop-server", daemon=True
        )
        self._thread.start()
        deadline = threading.Event()
        waited = 0.0
        step = 0.05
        while waited < timeout:
            if self._server.started:
                return
            if not self._thread.is_alive():
                raise RuntimeError(f"web server failed to start on {self.url}")
            deadline.wait(step)
            waited += step
        raise RuntimeError(f"web server did not start within {timeout:.0f}s on {self.url}")

    def stop(self, timeout: float = _SERVER_STOP_TIMEOUT_SECONDS) -> None:
        """Ask uvicorn to exit gracefully and wait for the thread."""

        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)
        self._server = None
        self._thread = None


def run_menubar_app(controller: ServerController) -> None:
    """The rumps menubar UI: Open / Status / Quit. Blocks until Quit."""

    import rumps

    class _MenubarApp(rumps.App):
        def __init__(self) -> None:
            open_item = rumps.MenuItem(f"Open {APP_NAME}", callback=self._open)
            status_item = rumps.MenuItem(f"Running on {controller.url}")
            status_item.set_callback(None)  # display-only
            # Item 67a: build provenance, so a stale bundle is self-evident
            # from the menubar (a frozen app has no git checkout to ask).
            stamp_item = rumps.MenuItem(stamp_label(build_stamp()))
            stamp_item.set_callback(None)  # display-only
            super().__init__(
                APP_NAME,
                title="SHD",
                menu=[open_item, status_item, stamp_item],
                quit_button=rumps.MenuItem("Quit", callback=self._quit),
            )

        def _open(self, _sender) -> None:
            webbrowser.open(controller.url)

        def _quit(self, _sender) -> None:
            controller.stop()
            rumps.quit_application()

    _MenubarApp().run()


def run_selftest(timeout: float = _SERVER_START_TIMEOUT_SECONDS) -> int:
    """Headless smoke test of the startup path (item 67b): exit 0 iff it serves.

    CI runners have no login GUI, so ``rumps`` cannot start there — this is
    the full ``main()`` path minus the menubar: data dir, port pick, server
    thread, one real request to ``/`` asserting 200. CI runs it against the
    *built* bundle binary so a broken bundle fails the job instead of
    reaching a coach. Also useful by hand when diagnosing a broken install.
    """

    prepare_data_dir()
    port = find_open_port()
    controller = ServerController(port=port)
    try:
        controller.start(timeout=timeout)
        with urllib.request.urlopen(f"{controller.url}/", timeout=timeout) as response:
            status = response.status
    except Exception as exc:  # any failure at all is a failed selftest
        print(f"selftest: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        controller.stop()
    if status != 200:
        print(f"selftest: FAIL: GET / returned {status}", file=sys.stderr)
        return 1
    print(f"selftest: OK: GET / returned 200 on {controller.url}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Bundle entrypoint: chdir to the data dir, start the server, show the menubar."""

    args = sys.argv[1:] if argv is None else argv
    # Membership test rather than argparse: macOS passes legacy `-psn_...`
    # args to launched bundles, and the launcher must not die over an
    # unrecognized flag (see the milestone rule on never failing to launch).
    if "--selftest" in args:
        return run_selftest()

    prepare_data_dir()
    port = find_open_port()
    controller = ServerController(port=port)
    controller.start()
    # First launch orientation (matches the 54b `start` behavior): open the
    # browser so a double-click visibly does something.
    webbrowser.open(controller.url)
    try:
        run_menubar_app(controller)
    finally:
        controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
