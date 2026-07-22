"""Local web-server lifecycle state for the CLI launcher."""

from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Callable, Optional

from sidelinehd_extractor.desktop import APP_NAME, default_data_dir

STATE_FILENAME = "webapp.json"
PACKAGE_NAME = "sidelinehd-extractor"
#: How long `stop` waits after SIGTERM before escalating to SIGKILL. It must
#: stay *above* ``desktop._SERVER_STOP_TIMEOUT_SECONDS`` (item 70a, D5): the
#: app's own graceful uvicorn stop is bounded at 10s, so a shorter wait here
#: would make SIGKILL the normal path for a perfectly graceful app quit
#: rather than the backstop it is meant to be. A test asserts the ordering.
STOP_TIMEOUT_SECONDS = 12.0

#: Which launcher started the recorded server (item 70a, D5). `restart` cannot
#: relaunch an `.app` it did not start, so it has to be able to tell.
ORIGIN_CLI = "cli"
ORIGIN_APP = "app"


@dataclass(frozen=True)
class ServerState:
    pid: int
    host: str
    port: int
    version: str
    started_at: str
    #: ``ORIGIN_CLI`` or ``ORIGIN_APP``. Defaults to the CLI, which is correct
    #: rather than a guess: nothing before item 70a wrote a record from the app.
    origin: str = ORIGIN_CLI
    #: The directory the server resolves ``rosters/``, ``runs/``, ``videos/``
    #: and ``sidelinehd.cfg`` against. **Information, not a decision key**
    #: (D6): it tells a reader *which files* the running server is serving,
    #: and nothing branches on it. Empty when the record predates the field.
    data_dir: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def server_state_path(data_dir: Optional[Path] = None) -> Path:
    """The record's location — **machine-global**, whatever directory is served.

    Deliberately not one record per data dir (D6): item 65's defence exists to
    find a server you have *forgotten*, and a forgotten server is precisely the
    one whose data dir you are no longer standing in. A per-directory file
    would also drop a ``webapp.json`` into the user's game folders.
    """

    return (data_dir or default_data_dir()).expanduser() / STATE_FILENAME


def utc_started_at(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def package_version() -> str:
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"


def git_short_sha(cwd: Optional[Path] = None) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = completed.stdout.strip()
    return sha or None


def version_display(version: Optional[str] = None, sha: Optional[str] = None) -> str:
    resolved = version or package_version()
    suffix = f" ({sha})" if sha else ""
    return f"v{resolved}{suffix}"


def new_server_state(
    host: str,
    port: int,
    *,
    pid: Optional[int] = None,
    version: Optional[str] = None,
    started_at: Optional[str] = None,
    origin: str = ORIGIN_CLI,
    data_dir: Optional[str] = None,
) -> ServerState:
    return ServerState(
        pid=pid or os.getpid(),
        host=host,
        port=port,
        version=version or package_version(),
        started_at=started_at or utc_started_at(),
        origin=origin,
        data_dir=data_dir if data_dir is not None else current_working_dir(),
    )


def current_working_dir() -> str:
    """CWD as a string, or empty if it is gone (a deleted directory raises)."""

    try:
        return os.getcwd()
    except OSError:
        return ""


def write_server_state(state: ServerState, path: Optional[Path] = None) -> Path:
    destination = path or server_state_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    return destination


def read_server_state(path: Optional[Path] = None) -> Optional[ServerState]:
    """Read the record, tolerating one written by an older version.

    ``origin`` and ``data_dir`` (item 70a) are **optional on read**: a server
    that was already running when the reader was upgraded must not become
    invisible to ``status`` and ``stop`` because its record lacks a field.
    """

    source = path or server_state_path()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        return ServerState(
            pid=int(data["pid"]),
            host=str(data["host"]),
            port=int(data["port"]),
            version=str(data["version"]),
            started_at=str(data["started_at"]),
            origin=str(data.get("origin") or ORIGIN_CLI),
            data_dir=str(data.get("data_dir") or ""),
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def remove_server_state(path: Optional[Path] = None, *, expected_pid: Optional[int] = None) -> None:
    target = path or server_state_path()
    if expected_pid is not None:
        state = read_server_state(target)
        if state is None or state.pid != expected_pid:
            return
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def claim_server_record(
    state: ServerState,
    path: Optional[Path] = None,
    *,
    alive: Optional[Callable[[int], bool]] = None,
) -> bool:
    """Write the record unless a *different, live* server already owns it.

    Item 70a: both writers — the CLI's ``ServerStateRegistration`` and the
    desktop app's ``main()`` — go through here, so no path can silently make a
    running server invisible to ``status`` and ``stop``. A dead or absent
    record is overwritten (the stale-record tolerance elsewhere in this module
    is the same judgement). Returns False when the claim was declined, which is
    *not* a failure — the caller serves anyway, unregistered, and says so.

    A caller that did not claim must not register cleanup.

    ``alive`` resolves to :func:`is_pid_alive` *at call time*, not as a default
    bound at definition time — a default would be captured before any test can
    replace the module attribute, so an injected liveness check would silently
    never run and the guard would be exercised against the real process table
    (CR-91).
    """

    alive = alive or is_pid_alive
    target = path or server_state_path()
    existing = read_server_state(target)
    if existing is not None and existing.pid != state.pid and alive(existing.pid):
        return False
    write_server_state(state, target)
    return True


def unregistered_warning(existing: ServerState) -> str:
    """The shared half of the "we declined to overwrite the record" warning.

    Each launcher appends its own way out — the CLI has a terminal and Ctrl+C,
    a double-clicked ``.app`` has neither.
    """

    return (
        f"Another {APP_NAME} server is already running "
        f"(PID {existing.pid}, {existing.url}). This one will not appear in "
        "`status`, and `stop` will act on the other one."
    )


class ServerStateRegistration:
    """Register the current foreground web server in the shared state file.

    The claim can be **declined** (item 70a): when another live server already
    owns the record, this one serves anyway but unregistered — ``registered``
    is False, ``conflict`` names the server that kept the record, and the
    caller is expected to print ``unregistered_warning(conflict)``. Declining
    is safe here precisely because ``start``/``serve`` are foreground commands
    with a terminal attached; the desktop app has no such fallback, which is
    why 70d gives it different treatment.
    """

    def __init__(self, host: str, port: int, path: Optional[Path] = None) -> None:
        self.state = new_server_state(host, port, origin=ORIGIN_CLI)
        self.path = path or server_state_path()
        self.registered = False
        self.conflict: Optional[ServerState] = None
        self._old_sigterm = None

    def __enter__(self) -> ServerState:
        self.registered = claim_server_record(self.state, self.path)
        if self.registered:
            atexit.register(self.cleanup)
        else:
            self.conflict = read_server_state(self.path)
        if hasattr(signal, "SIGTERM"):
            self._old_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, self._handle_sigterm)
        return self.state

    def __exit__(self, *exc: object) -> None:
        self.cleanup()
        if self._old_sigterm is not None:
            signal.signal(signal.SIGTERM, self._old_sigterm)

    def cleanup(self) -> None:
        # A caller that did not claim must not remove: `remove_server_state`'s
        # expected_pid guard would already refuse, and the belt-and-braces is
        # deliberate — this is the path that could make a live server vanish.
        if not self.registered:
            return
        remove_server_state(self.path, expected_pid=self.state.pid)
        try:
            atexit.unregister(self.cleanup)
        except ValueError:
            pass
        self.registered = False

    def _handle_sigterm(self, signum: int, frame: object) -> None:
        self.cleanup()
        if callable(self._old_sigterm):
            self._old_sigterm(signum, frame)
        elif self._old_sigterm == signal.SIG_IGN:
            return
        else:
            raise SystemExit(0)


def wait_until_dead(
    pid: int,
    *,
    timeout: float = STOP_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    alive: Callable[[int], bool] = is_pid_alive,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        sleep(0.1)
    return not alive(pid)


def stop_recorded_server(
    path: Optional[Path] = None,
    *,
    kill: Callable[[int, int], None] = os.kill,
    sleep: Callable[[float], None] = time.sleep,
    alive: Callable[[int], bool] = is_pid_alive,
) -> str:
    state_path = path or server_state_path()
    state = read_server_state(state_path)
    if state is None:
        return "No running server recorded."
    if not alive(state.pid):
        remove_server_state(state_path)
        return "Server not running (cleared stale record)."

    kill(state.pid, signal.SIGTERM)
    forced = not wait_until_dead(state.pid, sleep=sleep, alive=alive)
    if forced:
        escalation = signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM
        kill(state.pid, escalation)
    remove_server_state(state_path)
    # The two outcomes are genuinely different news (item 70a): a forced stop
    # means the server was still shutting down when we killed it, and whatever
    # it was in the middle of did not finish. Reporting both as "Stopped."
    # hid exactly that.
    if forced:
        return (
            f"Force-stopped (PID {state.pid}) — it did not exit within "
            f"{STOP_TIMEOUT_SECONDS:g} seconds."
        )
    return f"Stopped (PID {state.pid})."


def humanized_age(started_at: str, *, now: Optional[datetime] = None) -> str:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return "unknown age"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    seconds = max(0, int((current.astimezone(timezone.utc) - started).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s ago"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h {minutes}m ago"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h ago"


def display_path(raw: str) -> str:
    """A path a person can read: ``~`` for home, the raw string otherwise."""

    if not raw:
        return ""
    path = Path(raw)
    home = Path.home()
    if path == home:
        return "~"
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return raw


def status_message(
    path: Optional[Path] = None,
    *,
    alive: Callable[[int], bool] = is_pid_alive,
    now: Optional[datetime] = None,
) -> str:
    state_path = path or server_state_path()
    state = read_server_state(state_path)
    if state is None:
        return "not running"
    if not alive(state.pid):
        remove_server_state(state_path)
        return "not running (cleared stale record)"
    age = humanized_age(state.started_at, now=now)
    # Item 70a: the Dock app records itself too, so "running" is no longer
    # implicitly "running in some terminal" — say which, and say which files
    # it is serving, since the two launchers resolve different directories.
    origin = " (desktop app)" if state.origin == ORIGIN_APP else ""
    serving = f" · serving {display_path(state.data_dir)}" if state.data_dir else ""
    return (
        f"running{origin} · PID {state.pid} · {state.url} · "
        f"v{state.version} · started {state.started_at} ({age}){serving}"
    )


def restart_decline_message(state: ServerState) -> str:
    """Why `restart` will not relaunch a server the desktop app started (D5).

    The CLI cannot respawn an ``.app`` it did not start, and pretending
    otherwise would strand the user worse than saying so.
    """

    return (
        f"That server was started from the {APP_NAME} app (PID {state.pid}, "
        f"{state.url}), so `restart` cannot start it again. To restart it, quit "
        "the app from the Dock and open it again. To just shut it down, run "
        "`sidelinehd-extractor stop`."
    )


def footer_runtime_label(path: Optional[Path] = None) -> str:
    # Item 67a, restated for 70a: the bundle's footer must describe *this*
    # process, and the record — which since 70a the app also writes — may
    # belong to another server entirely, so the baked build stamp is the
    # authority here. A build date beats a bare version too.
    if getattr(sys, "frozen", False):
        from sidelinehd_extractor.build_info import build_stamp, stamp_label

        return stamp_label(build_stamp())
    state = read_server_state(path)
    if state is None:
        return version_display()
    return f"v{state.version} · started {state.started_at}"
