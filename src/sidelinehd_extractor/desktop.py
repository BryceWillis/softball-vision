"""Dock-first desktop launcher for the local web app (items 54d, 68b, 70a, 70b).

Runs the same FastAPI app as ``sidelinehd-extractor start`` but as a normal
macOS Dock app (AppKit, via PyObjC) instead of a terminal process: launch
presents the app's own window with the web page inside it (``WKWebView``),
clicking the Dock icon brings that window back, the Dock right-click menu and
the app menu carry Open / Open in Browser / status / Quit, and every standard
quit path (⌘Q, the app menu, the Dock, logout, and `stop` via SIGTERM) stops
the server gracefully. No terminal required. This module is the entrypoint the
PyInstaller ``.app`` bundle wraps (see ``packaging/``), and it also works from
source:

    python -m sidelinehd_extractor.desktop

**The window is a frame, not a second UI** (70b, decision D2): it renders the
page and nothing else, so the footer stamp, the health banner, progress, and
the plain-language rule keep exactly one home and nothing can drift out of
sync. The only native chrome is what macOS gives every window for free.

Everything except ``run_dock_app`` is import-safe headless (no AppKit, no
WebKit, no GUI) so the server-thread, data-dir, menu-model, and
navigation-policy logic stay unit-testable.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Tuple

from sidelinehd_extractor.build_info import build_stamp, stamp_label
from sidelinehd_extractor.updates import (
    RELEASES_PAGE_URL,
    UpdateCheck,
    update_menu_title,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sidelinehd_extractor.webapp.lifecycle import ServerState

APP_NAME = "SidelineHD Extractor"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
#: How many consecutive ports to try when the default is taken (a second
#: launch or another local app); the desktop app has no terminal to print a
#: "pick another port" error to, so it must find one itself.
PORT_ATTEMPTS = 10

_SERVER_START_TIMEOUT_SECONDS = 15.0
_SERVER_STOP_TIMEOUT_SECONDS = 10.0

#: Window geometry (item 70b). The default is roomy enough for the widest
#: working page (the game view's 72rem column plus chrome); the minimum is the
#: narrowest at which that column still reads without horizontal scrolling.
WINDOW_DEFAULT_SIZE = (1200.0, 860.0)
WINDOW_MIN_SIZE = (800.0, 600.0)
#: Size and position persist across launches under this name.
WINDOW_AUTOSAVE_NAME = "SidelineHDExtractorMainWindow"
#: A load failure gets exactly one silent retry after this long before the
#: user is told anything — the server is on loopback, so the realistic
#: transient is a request that raced startup, not a flaky network.
WINDOW_RELOAD_DELAY_SECONDS = 0.5


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
    from sidelinehd_extractor.events import DetectionConfig
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
        "detection": DetectionConfig(auto_detect_batting_half=True),
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
    the main thread; a GUI app needs the main thread for AppKit, so
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


# --- Lifecycle registration (item 70a) ---------------------------------------
#
# Item 65's staleness defence — `status` / `stop` / `restart` over the shared
# `webapp.json` record — was built because an orphaned stale server once
# produced two days of plausible wrong scores. It was CLI-side only, so the
# app that is now the *primary* onboarding path was the one server it could
# not see. The app writes the same record, tagged `origin="app"` so `restart`
# can decline politely rather than try to respawn a bundle.


def register_server_record(
    controller: ServerController,
    data_dir: Path,
    path: Optional[Path] = None,
) -> Optional["ServerState"]:
    """Record this app as the running server; return the record, or None.

    None means we are serving *unregistered* — either another live server owns
    the record (we decline to erase it) or the write failed. Both are warned
    about and neither stops the launch: a launcher must never fail to launch
    over metadata (the M1 rule), and the record is a defence, not a dependency.
    """

    from sidelinehd_extractor.webapp import lifecycle

    target = path or lifecycle.server_state_path()
    state = lifecycle.new_server_state(
        controller.host,
        controller.port,
        # A frozen bundle has no installed distribution metadata to read
        # (`importlib.metadata` reports "unknown" under PyInstaller), so the
        # 67a build stamp is the version of record there.
        version=build_stamp().version,
        origin=lifecycle.ORIGIN_APP,
        data_dir=str(data_dir),
    )
    try:
        claimed = lifecycle.claim_server_record(state, target)
    except OSError as error:
        print(
            f"warning: could not record this server ({error}) — `status` and "
            "`stop` will not see it.",
            file=sys.stderr,
        )
        return None
    if not claimed:
        blocker = lifecycle.read_server_state(target)
        if blocker is not None:
            print(
                f"{lifecycle.unregistered_warning(blocker)} Stop that one and "
                f"open {APP_NAME} again to put this one in charge.",
                file=sys.stderr,
            )
        return None
    return state


def release_server_record(
    state: Optional["ServerState"], path: Optional[Path] = None
) -> None:
    """Remove our record. Idempotent, and never raises (the M1 rule).

    ``expected_pid`` means this can only ever remove a record we own, so the
    duplicate call from ``main()``'s ``finally`` is harmless — and so is a
    quit that races a record another process has since claimed.
    """

    if state is None:
        return
    from sidelinehd_extractor.webapp import lifecycle

    try:
        lifecycle.remove_server_state(
            path or lifecycle.server_state_path(), expected_pid=state.pid
        )
    except OSError:
        pass


class QuitContext:
    """Whether the quit now in progress was asked for by a person at the screen.

    `stop` sends SIGTERM, and **SIGTERM is a non-interactive quit** (D5): it
    takes the same graceful path as ⌘Q but skips every confirmation on the
    way. A dialog raised in answer to a terminal command can only be dismissed
    by someone who is not looking at that screen, so asking would stall the
    quit until the CLI's own timer killed the app outright — the least
    graceful of the three outcomes available. The person who typed `stop` has
    already answered.

    70a has nothing to ask yet, so the flag has no visible effect here. It
    ships now because the signal handler that sets it is 70a's; **70c** is
    where it earns its keep, suppressing the quit-mid-run confirmation on this
    one path. It is set by the signal handler and nowhere else — a stray
    setter would silently disarm that confirmation for ⌘Q too.
    """

    def __init__(self) -> None:
        self.interactive = True

    def mark_non_interactive(self) -> None:
        self.interactive = False


def install_sigterm_quit_handler(
    terminate: Callable[[], None],
    quit_context: QuitContext,
    *,
    install: Optional[Callable[[int, Callable], object]] = None,
) -> Callable[[int, object], None]:
    """Route SIGTERM into the app's own graceful quit. Returns the handler.

    Without this, `stop` would kill the app where it stands: uvicorn never
    stopped, the record left behind. With it, `stop` funnels into the same
    ``applicationShouldTerminate:`` every other quit path uses.

    Its companion is the heartbeat timer in ``run_dock_app``: a Python signal
    handler only runs when Python bytecode next executes, and once the 67d
    poll timer invalidates itself, nothing else on the main run loop does.
    """

    def _handle(signum: int, frame: object) -> None:
        quit_context.mark_non_interactive()
        terminate()

    (install or signal.signal)(signal.SIGTERM, _handle)
    return _handle


# --- Navigation policy (item 70b) --------------------------------------------
#
# D4: the window shows *our* page; everything else belongs in the user's real
# browser, where their YouTube and GitHub logins live. The review rows'
# timestamp deep links and the feedback page's GitHub/mailto hand-offs are
# exactly the flows that must not land in a frameless app window with no
# address bar and no way back.
#
# It is a URL classifier, so it is a pure function and needs no GUI to test.

#: Schemes the web view resolves internally rather than navigating to a page.
#: Handing these to the browser would open a blank tab for a load the view is
#: doing to itself.
_IN_VIEW_SCHEMES = frozenset({"", "about", "data", "blob", "javascript"})
_DEFAULT_PORTS = {"http": 80, "https": 443}

#: Codes a failed provisional navigation reports when *we* stopped it:
#: ``NSURLErrorCancelled`` and WebKit's frame-load-interrupted-by-policy-change
#: — which is exactly what cancelling an external link to hand it to the
#: browser produces. Treating either as a load failure would put an alert on
#: screen every time someone clicked a YouTube link.
_CANCELLED_LOAD_ERROR_CODES = frozenset({-999, 102})


def _origin(url: str) -> Tuple[str, str, Optional[int]]:
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    try:
        port = parsed.port
    except ValueError:  # a malformed port ("http://h:notanumber")
        port = None
    return scheme, (parsed.hostname or "").lower(), port or _DEFAULT_PORTS.get(scheme)


def navigation_opens_in_window(url: str, app_url: str) -> bool:
    """True when a navigation stays in the window; False → the default browser.

    Same-origin means the *same server*: scheme, host, and port all match
    ours, with the scheme's default port filled in so ``http://host`` and
    ``http://host:80`` are one origin rather than two. Anything else — an
    external site, a ``mailto:``, a link to a different local port — is the
    user's browser's job.
    """

    scheme, host, port = _origin(url)
    if scheme in _IN_VIEW_SCHEMES:
        return True
    return (scheme, host, port) == _origin(app_url)


def _navigation_action_url(action: object) -> str:
    """The URL string of a ``WKNavigationAction``, or "" if it has none.

    Every hop is optional in principle, and a launcher must never fail over
    metadata: an unreadable action classifies as in-view, which allows the
    load rather than opening a browser tab on nothing.
    """

    request = getattr(action, "request", None)
    url = request().URL() if request is not None else None
    return url.absoluteString() if url is not None else ""


# --- Menu models (item 68b, extended by 70b) ---------------------------------
#
# The menus' *content* lives here as pure functions returning ordered tuples,
# so the unit tests exercise it with no GUI; the AppKit layer in
# ``run_dock_app`` merely renders them. Item 67d's rule holds in both the app
# and Dock models: the update entry exists exactly when the check produced a
# tag — never a "you're up to date" line.

ENTRY_ACTION = "action"
ENTRY_DISPLAY_ONLY = "display-only"
ENTRY_SEPARATOR = "separator"

ABOUT_MENU_TITLE = f"About {APP_NAME}"
OPEN_MENU_TITLE = f"Open {APP_NAME}"
OPEN_BROWSER_MENU_TITLE = "Open in Browser"
QUIT_MENU_TITLE = f"Quit {APP_NAME}"

EDIT_MENU_TITLE = "Edit"
WINDOW_MENU_TITLE = "Window"

MenuEntry = Tuple[str, str]
#: ``(title, selector, key equivalent)`` for the two standard menus, whose
#: items are wired to the *first responder* rather than to a target of ours.
StandardMenuEntry = Tuple[str, str, str]
_STANDARD_SEPARATOR: StandardMenuEntry = ("", ENTRY_SEPARATOR, "")


def edit_menu_entries() -> List[StandardMenuEntry]:
    """The Edit menu — mandatory, and the point (item 70b).

    In AppKit the ⌘C/⌘V key equivalents come *from this menu*: with no Edit
    menu, selecting text in a ``WKWebView`` and pressing ⌘C does nothing. In a
    tool whose entire output is copy-paste kits that is a first-five-minutes
    bug, and it is also what makes the page's own "select the text and copy
    manually" fallback honest.

    Every selector travels the responder chain to the web view, so these need
    no target and no code behind them.
    """

    return [
        ("Undo", "undo:", "z"),
        ("Redo", "redo:", "Z"),  # capital Z is ⇧⌘Z, the standard equivalent
        _STANDARD_SEPARATOR,
        ("Cut", "cut:", "x"),
        ("Copy", "copy:", "c"),
        ("Paste", "paste:", "v"),
        _STANDARD_SEPARATOR,
        ("Select All", "selectAll:", "a"),
    ]


def window_menu_entries() -> List[StandardMenuEntry]:
    """The Window menu: Minimize, Zoom, Close (item 70b).

    ⌘W closes the window and **does not quit** (D3) — the server, and a
    40-minute read with it, outlives a reflexive window tidy-up.
    """

    return [
        ("Minimize", "performMiniaturize:", "m"),
        ("Zoom", "performZoom:", ""),
        _STANDARD_SEPARATOR,
        ("Close", "performClose:", "w"),
    ]


def _status_line(url: str) -> str:
    return f"Running on {url}"


def app_menu_entries(
    url: str, stamp: str, update_tag: Optional[str] = None
) -> List[MenuEntry]:
    """The app menu: About, Open (⌘O), Open in Browser, status + stamp, update, Quit."""

    entries: List[MenuEntry] = [
        (ABOUT_MENU_TITLE, ENTRY_ACTION),
        ("", ENTRY_SEPARATOR),
        (OPEN_MENU_TITLE, ENTRY_ACTION),
        # D4: the window replaces the browser auto-open, but the browser stays
        # first-class one click away — dev tools, several tabs, printing.
        (OPEN_BROWSER_MENU_TITLE, ENTRY_ACTION),
        (_status_line(url), ENTRY_DISPLAY_ONLY),
        # Item 67a: build provenance, so a stale bundle is self-evident from
        # the menu (a frozen app has no git checkout to ask).
        (stamp, ENTRY_DISPLAY_ONLY),
    ]
    if update_tag is not None:
        entries.append((update_menu_title(update_tag), ENTRY_ACTION))
    entries.append(("", ENTRY_SEPARATOR))
    entries.append((QUIT_MENU_TITLE, ENTRY_ACTION))
    return entries


def dock_menu_entries(url: str, update_tag: Optional[str] = None) -> List[MenuEntry]:
    """The Dock right-click menu: Open, Open in Browser, status, update when one exists.

    Never a Quit entry — macOS appends its own Quit to every Dock menu, and
    a second one would double it.
    """

    entries: List[MenuEntry] = [
        (OPEN_MENU_TITLE, ENTRY_ACTION),
        (OPEN_BROWSER_MENU_TITLE, ENTRY_ACTION),
        (_status_line(url), ENTRY_DISPLAY_ONLY),
    ]
    if update_tag is not None:
        entries.append((update_menu_title(update_tag), ENTRY_ACTION))
    return entries


def run_dock_app(
    controller: ServerController,
    update_check: Optional[UpdateCheck] = None,
    on_quit: Optional[Callable[[], None]] = None,
) -> None:
    """The AppKit Dock app (items 68b, 70b): one window over the menu models
    above. Blocks until quit.

    AppKit and WebKit are imported here, never at module scope, so the module
    stays importable headless (CI, ``--selftest``, the test suite). Menus and
    the window are only ever touched from the main thread: the update poll is
    an ``NSTimer`` on the main run loop, and the Dock menu is rebuilt fresh on
    every show.

    ``on_quit`` runs inside ``applicationShouldTerminate:`` once the server is
    stopped — item 70a's record removal. It must not run at ``atexit``:
    Cocoa's ``terminate:`` exits the process without Python's interpreter
    finalization, so an ``atexit`` cleanup would silently never fire in the
    bundle.
    """

    import AppKit
    import WebKit

    app = AppKit.NSApplication.sharedApplication()
    # The bundle's plist yields a Regular (Dock) app now that LSUIElement is
    # gone; setting the policy here too makes a source run
    # (python -m sidelinehd_extractor.desktop) behave the same way, with the
    # generic Python Dock icon accepted for that path.
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

    stamp = stamp_label(build_stamp())
    key_equivalents = {OPEN_MENU_TITLE: "o", QUIT_MENU_TITLE: "q"}

    def action_for(title: str):
        # About and Quit use the standard Cocoa selectors, so Quit funnels
        # through applicationShouldTerminate_ like every other quit path.
        if title == ABOUT_MENU_TITLE:
            return "orderFrontStandardAboutPanel:", app
        if title == QUIT_MENU_TITLE:
            return "terminate:", app
        if title == OPEN_MENU_TITLE:
            # 70b: "Open" now means *our window*, not a browser tab.
            return "presentWindow:", delegate
        if title == OPEN_BROWSER_MENU_TITLE:
            return "openBrowser:", delegate
        return "openReleases:", delegate  # the update item is the only other action

    def render_menu(entries: List[MenuEntry]):
        menu = AppKit.NSMenu.alloc().initWithTitle_(APP_NAME)
        # Autoenable would manage enabled-state on its own schedule; explicit
        # control keeps the display-only lines (status, stamp) inert.
        menu.setAutoenablesItems_(False)
        for title, kind in entries:
            if kind == ENTRY_SEPARATOR:
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                continue
            item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, None, key_equivalents.get(title, "")
            )
            if kind == ENTRY_ACTION:
                selector, target = action_for(title)
                item.setAction_(selector)
                item.setTarget_(target)
                item.setEnabled_(True)
            else:
                item.setEnabled_(False)
            menu.addItem_(item)
        return menu

    def render_standard_menu(title: str, entries: List[StandardMenuEntry]):
        """Render Edit / Window: items wired to the responder chain, no target.

        Autoenabling is left on (unlike the app menu, whose display-only lines
        must stay inert): it is what lets AppKit ask the web view whether it
        currently has a selection to copy, and grey Copy out when it does not.
        """

        menu = AppKit.NSMenu.alloc().initWithTitle_(title)
        for entry_title, selector, key in entries:
            if selector == ENTRY_SEPARATOR:
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                continue
            item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                entry_title, None, key
            )
            item.setAction_(selector)
            menu.addItem_(item)
        return menu

    def add_submenu(main_menu, title: str, submenu):
        item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, None, ""
        )
        main_menu.addItem_(item)
        main_menu.setSubmenu_forItem_(submenu, item)
        return submenu

    def install_app_menu(update_tag: Optional[str] = None) -> None:
        main_menu = AppKit.NSMenu.alloc().initWithTitle_("MainMenu")
        add_submenu(
            main_menu,
            APP_NAME,
            render_menu(app_menu_entries(controller.url, stamp, update_tag)),
        )
        # 70b: the Edit menu is what makes ⌘C work inside the web view — see
        # edit_menu_entries. The Window menu carries ⌘W, which closes the
        # window without quitting (D3).
        add_submenu(
            main_menu,
            EDIT_MENU_TITLE,
            render_standard_menu(EDIT_MENU_TITLE, edit_menu_entries()),
        )
        window_menu = add_submenu(
            main_menu,
            WINDOW_MENU_TITLE,
            render_standard_menu(WINDOW_MENU_TITLE, window_menu_entries()),
        )
        app.setMainMenu_(main_menu)
        # Lets AppKit keep the standard window list at the foot of the menu.
        app.setWindowsMenu_(window_menu)

    # --- The window (item 70b) ---
    #
    # One window, ever. It is a frame around the page (D2): no native toolbar,
    # no native status widgets, nothing that could drift out of step with what
    # the page itself already shows.

    window_state: dict = {}

    def load_url(url: str) -> None:
        web_view = window_state.get("web_view")
        if web_view is None:
            return
        target = AppKit.NSURL.URLWithString_(url)
        if target is not None:
            web_view.loadRequest_(AppKit.NSURLRequest.requestWithURL_(target))

    def build_window():
        web_view = WebKit.WKWebView.alloc().initWithFrame_configuration_(
            AppKit.NSMakeRect(0.0, 0.0, *WINDOW_DEFAULT_SIZE),
            WebKit.WKWebViewConfiguration.alloc().init(),
        )
        web_view.setNavigationDelegate_(delegate)
        web_view.setUIDelegate_(delegate)
        web_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AppKit.NSMakeRect(0.0, 0.0, *WINDOW_DEFAULT_SIZE),
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setTitle_(APP_NAME)
        # Closing must not deallocate it (D3: close is not quit) — the app
        # stays in the Dock, and the click that follows re-presents this one.
        window.setReleasedWhenClosed_(False)
        window.setContentMinSize_(AppKit.NSMakeSize(*WINDOW_MIN_SIZE))
        window.setContentView_(web_view)
        window.center()
        window.setFrameAutosaveName_(WINDOW_AUTOSAVE_NAME)
        # setFrameAutosaveName_ arranges only the *saving*; this is what
        # restores the last launch's size and position when there is one.
        window.setFrameUsingName_(WINDOW_AUTOSAVE_NAME)
        window_state["window"] = window
        window_state["web_view"] = web_view
        load_url(controller.url)
        return window

    def present_window() -> None:
        window = window_state.get("window") or build_window()
        window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

    def open_externally(url: str) -> None:
        if url:
            webbrowser.open(url)

    def show_load_failure_alert() -> None:
        # Never a blank white window with no explanation: say what happened
        # and offer the two things that actually help.
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(f"{APP_NAME} could not show its page.")
        alert.setInformativeText_(
            "The app is running, but its page did not load. You can open it in "
            "your browser instead, or quit and open the app again."
        )
        alert.addButtonWithTitle_(OPEN_BROWSER_MENU_TITLE)
        alert.addButtonWithTitle_(QUIT_MENU_TITLE)
        if alert.runModal() == AppKit.NSAlertFirstButtonReturn:
            webbrowser.open(controller.url)
        else:
            app.terminate_(None)

    def handle_load_failure(error) -> None:
        if error is not None and error.code() in _CANCELLED_LOAD_ERROR_CODES:
            return  # we cancelled it ourselves, on its way to the browser
        if not window_state.get("retried"):
            window_state["retried"] = True
            AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                WINDOW_RELOAD_DELAY_SECONDS, delegate, "retryLoad:", None, False
            )
            return
        show_load_failure_alert()

    class _DockDelegate(AppKit.NSObject):
        def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _has_windows):
            # 70b: a Dock icon is a promise of windows, and this is the window
            # it promises. M5 answered this hook by launching Safari, which is
            # the invention the owner tripped over on first use.
            present_window()
            return False

        def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
            # D3. ⌘W tidies the window away; the server, and a 30–45-minute
            # read with it, keeps going. This is the Music/Mail model.
            return False

        def presentWindow_(self, _sender):
            present_window()

        def retryLoad_(self, _timer):
            load_url(controller.url)

        def webView_didFinishNavigation_(self, _web_view, _navigation):
            window_state["retried"] = False

        def webView_didFailProvisionalNavigation_withError_(
            self, _web_view, _navigation, error
        ):
            handle_load_failure(error)

        def webView_didFailNavigation_withError_(self, _web_view, _navigation, error):
            handle_load_failure(error)

        def webView_decidePolicyForNavigationAction_decisionHandler_(
            self, _web_view, action, decision_handler
        ):
            # D4: our origin stays here; everything else goes to the real
            # browser, where the user's YouTube and GitHub logins live.
            target = _navigation_action_url(action)
            if navigation_opens_in_window(target, controller.url):
                decision_handler(WebKit.WKNavigationActionPolicyAllow)
                return
            decision_handler(WebKit.WKNavigationActionPolicyCancel)
            open_externally(target)

        def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
            self, _web_view, _configuration, action, _features
        ):
            # target="_blank" — the review rows' YouTube deep links (item 63)
            # and the feedback page's GitHub hand-off arrive here. There is
            # exactly one window, ever: navigate it or hand off, create nothing.
            target = _navigation_action_url(action)
            if navigation_opens_in_window(target, controller.url):
                load_url(target)
            else:
                open_externally(target)
            return None

        def applicationDockMenu_(self, _app):
            # Rebuilt per show, so the update item needs no mutation path.
            tag = update_check.result if update_check is not None else None
            return render_menu(dock_menu_entries(controller.url, tag))

        def applicationShouldTerminate_(self, _app):
            # The single hook that makes ⌘Q, app menu → Quit, Dock → Quit,
            # logout, and now `stop` (via SIGTERM) all stop the server
            # gracefully. stop() bounds its thread join, so quit — including
            # logout — can never wedge.
            controller.stop()
            if on_quit is not None:
                on_quit()
            return AppKit.NSTerminateNow

        def heartbeat_(self, _timer):
            # Deliberately does nothing. Its only job is to run Python
            # bytecode on the main run loop about once a second, so a pending
            # SIGTERM gets delivered — see install_sigterm_quit_handler.
            return None

        def openBrowser_(self, _sender):
            webbrowser.open(controller.url)

        def openReleases_(self, _sender):
            webbrowser.open(RELEASES_PAGE_URL)

        def pollUpdateCheck_(self, timer):
            # Item 67d: the check runs on its own daemon thread, but menus
            # must only be touched from the main thread — where this timer
            # fires. Poll until the check finishes, then stop; the menu is
            # rebuilt from the model only when an update actually exists.
            if update_check is None or not update_check.done:
                return
            timer.invalidate()
            if update_check.result is not None:
                install_app_menu(update_check.result)

    delegate = _DockDelegate.alloc().init()
    app.setDelegate_(delegate)
    install_app_menu()
    # Item 70a: `stop` sends SIGTERM, and the graceful path is the same one
    # ⌘Q takes. The heartbeat is permanent (never invalidated) — it is what
    # gives the interpreter a chance to deliver the signal at all.
    # `quit_context` is what applicationShouldTerminate_ will consult in 70c;
    # here nothing asks a question yet, so it is only written to.
    quit_context = QuitContext()
    install_sigterm_quit_handler(lambda: app.terminate_(None), quit_context)
    # Item 70b: launch presents the app's own window. This is what replaced
    # main()'s `webbrowser.open` — a Dock app that opens a different
    # application is the shape this milestone exists to retire.
    present_window()
    AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0, delegate, "heartbeat:", None, True
    )
    if update_check is not None:
        AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, delegate, "pollUpdateCheck:", None, True
        )
    app.run()


def bundle_dependency_failures() -> List[str]:
    """Self-containment check: every helper must resolve inside this process.

    The v0.4.0 bundle shipped unable to OCR or download, masked because every
    verification ran from a terminal whose PATH supplied the missing pieces
    (bundle CR, 2026-07-20). These checks pass only when the dependencies the
    app will actually use — the tesserocr and yt_dlp modules, the bundled
    ffmpeg — are healthy with no help from the host environment; a GET-/
    check alone provably cannot catch that.
    """

    from sidelinehd_extractor.ocr import TesserocrOCRBackend, create_ocr_backend
    from sidelinehd_extractor.preflight import missing_dependencies

    failures = [
        f"dependency {status['name']} unhealthy: {status['detail']}"
        for status in missing_dependencies()
    ]
    try:
        backend = create_ocr_backend("tesserocr")
    except Exception as exc:
        failures.append(f"tesserocr OCR backend unavailable: {exc}")
    else:
        if not isinstance(backend, TesserocrOCRBackend):
            failures.append(
                "create_ocr_backend('tesserocr') fell back to the Tesseract CLI"
                " — the app is leaning on the host environment instead of its"
                " bundled engine"
            )
    return failures


def run_selftest(timeout: float = _SERVER_START_TIMEOUT_SECONDS) -> int:
    """Headless smoke test of the startup path (item 67b): exit 0 iff healthy.

    CI runners have no login GUI, so the Dock app cannot start there — this
    is the full ``main()`` path minus the GUI: data dir, dependency
    self-containment (``bundle_dependency_failures``), port pick, server
    thread, one real request to ``/`` asserting 200. CI runs it against the
    *built* bundle binary with a scrubbed PATH so a bundle that leans on the
    host environment fails the job instead of reaching a coach. Also useful
    by hand when diagnosing a broken install.
    """

    prepare_data_dir()
    failures = bundle_dependency_failures()
    port = find_open_port()
    controller = ServerController(port=port)
    try:
        controller.start(timeout=timeout)
        with urllib.request.urlopen(f"{controller.url}/", timeout=timeout) as response:
            status = response.status
        if status != 200:
            failures.append(f"GET / returned {status}")
    except Exception as exc:  # any failure at all is a failed selftest
        failures.append(str(exc))
    finally:
        controller.stop()
    if failures:
        for failure in failures:
            print(f"selftest: FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        f"selftest: OK: dependencies are self-contained and GET / returned 200 "
        f"on {controller.url}"
    )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Bundle entrypoint: chdir to the data dir, start the server, show the window."""

    args = sys.argv[1:] if argv is None else argv
    # Membership test rather than argparse: macOS passes legacy `-psn_...`
    # args to launched bundles, and the launcher must not die over an
    # unrecognized flag (see the milestone rule on never failing to launch).
    if "--selftest" in args:
        return run_selftest()

    data_dir = prepare_data_dir()
    port = find_open_port()
    controller = ServerController(port=port)
    controller.start()
    # Item 70a: only once the server is actually up — the record says "a
    # server is running here", and until start() returns that is not true.
    record = register_server_record(controller, data_dir)
    # Item 67d: only after the server is up, and on a daemon thread — the
    # check must never block launch, and --selftest never reaches this path.
    update_check = UpdateCheck()
    update_check.start()
    # Item 70b (D4): no `webbrowser.open` here any more. A double-click is
    # answered by the app's *own* window, which run_dock_app presents; the
    # browser stays one click away on the Open in Browser menu item.
    try:
        run_dock_app(
            controller, update_check, on_quit=lambda: release_server_record(record)
        )
    finally:
        # Idempotent, and the only cleanup a source run or a startup failure
        # gets: Cocoa's terminate: never reaches here in the bundle.
        controller.stop()
        release_server_record(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
