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

from sidelinehd_extractor.desktop import default_data_dir

STATE_FILENAME = "webapp.json"
PACKAGE_NAME = "sidelinehd-extractor"
STOP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ServerState:
    pid: int
    host: str
    port: int
    version: str
    started_at: str

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def server_state_path(data_dir: Optional[Path] = None) -> Path:
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
) -> ServerState:
    return ServerState(
        pid=pid or os.getpid(),
        host=host,
        port=port,
        version=version or package_version(),
        started_at=started_at or utc_started_at(),
    )


def write_server_state(state: ServerState, path: Optional[Path] = None) -> Path:
    destination = path or server_state_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    return destination


def read_server_state(path: Optional[Path] = None) -> Optional[ServerState]:
    source = path or server_state_path()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        return ServerState(
            pid=int(data["pid"]),
            host=str(data["host"]),
            port=int(data["port"]),
            version=str(data["version"]),
            started_at=str(data["started_at"]),
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


class ServerStateRegistration:
    """Register the current foreground web server in the shared state file."""

    def __init__(self, host: str, port: int, path: Optional[Path] = None) -> None:
        self.state = new_server_state(host, port)
        self.path = path or server_state_path()
        self._old_sigterm = None
        self._registered = False

    def __enter__(self) -> ServerState:
        write_server_state(self.state, self.path)
        atexit.register(self.cleanup)
        self._registered = True
        if hasattr(signal, "SIGTERM"):
            self._old_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, self._handle_sigterm)
        return self.state

    def __exit__(self, *exc: object) -> None:
        self.cleanup()
        if self._old_sigterm is not None:
            signal.signal(signal.SIGTERM, self._old_sigterm)

    def cleanup(self) -> None:
        remove_server_state(self.path, expected_pid=self.state.pid)
        if self._registered:
            try:
                atexit.unregister(self.cleanup)
            except ValueError:
                pass
            self._registered = False

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
    if not wait_until_dead(state.pid, sleep=sleep, alive=alive):
        escalation = signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM
        kill(state.pid, escalation)
    remove_server_state(state_path)
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
    return (
        f"running · PID {state.pid} · {state.url} · "
        f"v{state.version} · started {state.started_at} ({age})"
    )


def footer_runtime_label(path: Optional[Path] = None) -> str:
    # Item 67a: a frozen bundle never records a server (the CLI does that),
    # so prefer its baked build stamp — a build date beats a bare version.
    if getattr(sys, "frozen", False):
        from sidelinehd_extractor.build_info import build_stamp, stamp_label

        return stamp_label(build_stamp())
    state = read_server_state(path)
    if state is None:
        return version_display()
    return f"v{state.version} · started {state.started_at}"
