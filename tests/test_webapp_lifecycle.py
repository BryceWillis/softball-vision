from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidelinehd_extractor import desktop
from sidelinehd_extractor.webapp import lifecycle


def _state(
    pid: int = 1234,
    *,
    origin: str = lifecycle.ORIGIN_CLI,
    data_dir: str = "",
) -> lifecycle.ServerState:
    return lifecycle.ServerState(
        pid=pid,
        host="127.0.0.1",
        port=8000,
        version="0.test",
        started_at="2026-07-10T12:00:00Z",
        origin=origin,
        data_dir=data_dir,
    )


def test_server_state_registration_writes_and_removes_state_file(tmp_path, monkeypatch):
    path = tmp_path / "webapp.json"
    monkeypatch.setattr(lifecycle, "package_version", lambda: "0.test")

    with lifecycle.ServerStateRegistration("127.0.0.1", 9999, path=path) as state:
        loaded = lifecycle.read_server_state(path)
        assert loaded is not None
        assert loaded.pid == state.pid
        assert loaded.host == "127.0.0.1"
        assert loaded.port == 9999
        assert loaded.version == "0.test"

    assert not path.exists()


def test_stop_live_pid_sends_sigterm_and_clears_state(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=2222), path)
    sent = []
    alive = {"value": True}

    def fake_kill(pid, sig):
        sent.append((pid, sig))
        if sig == signal.SIGTERM:
            alive["value"] = False

    message = lifecycle.stop_recorded_server(
        path,
        kill=fake_kill,
        sleep=lambda _: None,
        alive=lambda pid: alive["value"],
    )

    assert message == "Stopped (PID 2222)."
    assert sent == [(2222, signal.SIGTERM)]
    assert not path.exists()


def test_stop_escalates_when_process_survives_sigterm(tmp_path, monkeypatch):
    """The forced stop says so: it means the server was still shutting down
    when we killed it, which is different news from a graceful stop."""

    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=3333), path)
    sent = []
    monkeypatch.setattr(lifecycle, "wait_until_dead", lambda *args, **kwargs: False)

    message = lifecycle.stop_recorded_server(
        path,
        kill=lambda pid, sig: sent.append((pid, sig)),
        alive=lambda pid: True,
    )

    assert message == (
        "Force-stopped (PID 3333) — it did not exit within 12 seconds."
    )
    assert sent[0] == (3333, signal.SIGTERM)
    assert sent[1][0] == 3333
    assert sent[1][1] == getattr(signal, "SIGKILL", signal.SIGTERM)
    assert not path.exists()


def test_stop_waits_longer_than_the_desktop_app_takes_to_stop_gracefully():
    """Item 70a/D5: the CLI's SIGKILL wait must exceed the app's own graceful
    bound, or SIGKILL becomes the normal path for a *graceful* app quit and
    `stop` reports success over a server it actually killed mid-shutdown."""

    assert lifecycle.STOP_TIMEOUT_SECONDS > desktop._SERVER_STOP_TIMEOUT_SECONDS


def test_stop_and_status_clear_stale_state(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=4444), path)

    assert lifecycle.status_message(path, alive=lambda pid: False) == (
        "not running (cleared stale record)"
    )
    assert not path.exists()

    lifecycle.write_server_state(_state(pid=5555), path)
    assert lifecycle.stop_recorded_server(path, alive=lambda pid: False) == (
        "Server not running (cleared stale record)."
    )
    assert not path.exists()


def test_status_formats_running_server_with_age(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=6666), path)

    message = lifecycle.status_message(
        path,
        alive=lambda pid: True,
        now=datetime(2026, 7, 10, 14, 30, tzinfo=timezone.utc),
    )

    assert message == (
        "running · PID 6666 · http://127.0.0.1:8000 · "
        "v0.test · started 2026-07-10T12:00:00Z (2h 30m ago)"
    )


def test_footer_runtime_label_uses_state_when_present(tmp_path, monkeypatch):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(), path)

    assert lifecycle.footer_runtime_label(path) == "v0.test · started 2026-07-10T12:00:00Z"

    path.unlink()
    monkeypatch.setattr(lifecycle, "package_version", lambda: "0.fallback")
    monkeypatch.setattr(lifecycle, "git_short_sha", lambda cwd=None: None)
    assert lifecycle.footer_runtime_label(path) == "v0.fallback"


def test_footer_runtime_label_prefers_build_stamp_when_frozen(tmp_path, monkeypatch):
    """Item 67a: a frozen bundle's footer shows the baked build stamp, even
    when a (stale, CLI-written) server record exists in the data dir."""

    import json
    import sys

    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(), path)

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "build_info.json").write_text(
        json.dumps(
            {"version": "0.2.0", "sha": "a1b2c3d", "built_at": "2026-07-20T18:04:05Z"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    assert lifecycle.footer_runtime_label(path) == "v0.2.0 (a1b2c3d) · built 2026-07-20"


def test_version_display_includes_sha_when_available():
    assert lifecycle.version_display("1.2.3", "abc123") == "v1.2.3 (abc123)"
    assert lifecycle.version_display("1.2.3", None) == "v1.2.3"


# --- Origin and data dir in the record (item 70a) ----------------------------


def test_record_round_trips_the_origin_and_data_dir(tmp_path):
    path = tmp_path / "webapp.json"
    state = _state(origin=lifecycle.ORIGIN_APP, data_dir="/tmp/games")
    lifecycle.write_server_state(state, path)

    assert lifecycle.read_server_state(path) == state


def test_old_format_record_still_reads_with_defaults(tmp_path):
    """A server already running when the reader is upgraded must not become
    invisible to `status` and `stop` because its record lacks a field."""

    path = tmp_path / "webapp.json"
    path.write_text(
        json.dumps(
            {
                "pid": 4242,
                "host": "127.0.0.1",
                "port": 8000,
                "version": "0.test",
                "started_at": "2026-07-10T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    state = lifecycle.read_server_state(path)
    assert state is not None
    assert state.pid == 4242
    # The CLI default is not a guess: nothing before 70a wrote a record from
    # the app, so every old-format record really is a CLI one.
    assert state.origin == lifecycle.ORIGIN_CLI
    assert state.data_dir == ""


def test_status_names_the_desktop_app_and_the_folder_it_serves(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(
        _state(pid=6666, origin=lifecycle.ORIGIN_APP, data_dir="/games/current"), path
    )

    message = lifecycle.status_message(
        path,
        alive=lambda pid: True,
        now=datetime(2026, 7, 10, 14, 30, tzinfo=timezone.utc),
    )

    assert message == (
        "running (desktop app) · PID 6666 · http://127.0.0.1:8000 · "
        "v0.test · started 2026-07-10T12:00:00Z (2h 30m ago) · serving /games/current"
    )


def test_status_keeps_the_cli_wording_and_appends_the_same_serving_clause(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=6666, data_dir="/checkout"), path)

    message = lifecycle.status_message(
        path,
        alive=lambda pid: True,
        now=datetime(2026, 7, 10, 14, 30, tzinfo=timezone.utc),
    )

    assert message.startswith("running · PID 6666 ·")
    assert message.endswith(" · serving /checkout")


def test_status_omits_the_serving_clause_for_an_old_format_record(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=6666), path)

    message = lifecycle.status_message(path, alive=lambda pid: True)

    assert "serving" not in message


def test_display_path_abbreviates_the_home_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle.Path, "home", classmethod(lambda cls: tmp_path))

    # CR-104: the expectation is built with `Path` rather than hardcoded as
    # "~/Library/Games", because the abbreviated form follows the platform's
    # separator. The old literal was a macOS assumption that failed on the
    # windows-latest leg — and it failed against a genuinely wrong answer, the
    # mixed "~/Library\Games", not merely against a differently-spelled right
    # one. On POSIX this is the same string it always was.
    assert lifecycle.display_path(str(tmp_path / "Library" / "Games")) == str(
        Path("~") / "Library" / "Games"
    )
    assert lifecycle.display_path(str(tmp_path)) == "~"
    assert lifecycle.display_path("/elsewhere/games") == "/elsewhere/games"
    assert lifecycle.display_path("") == ""


def test_new_server_state_defaults_to_the_cli_and_the_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    state = lifecycle.new_server_state("127.0.0.1", 8000, version="0.test")

    assert state.origin == lifecycle.ORIGIN_CLI
    assert state.data_dir == str(tmp_path.resolve())


# --- The claim guard (item 70a) ----------------------------------------------
#
# The record is a *live* server's identity, so overwriting one is how `status`
# and `stop` start naming a server that is not the one running. `is_pid_alive`
# is injected throughout: no test in *this* section spawns a process, because
# the guard's behaviour is a decision about a liveness answer, not about how
# the answer was obtained — injection keeps it deterministic on every OS.
#
# The rule used to be absolute, and CR-94 is why it no longer is: handing the
# real probe a live PID was unsafe on Windows, so the section below — which
# exists to prove it is now safe — is the one place that does spawn.


def test_claim_writes_when_no_record_exists(tmp_path):
    path = tmp_path / "webapp.json"

    assert lifecycle.claim_server_record(_state(pid=111), path, alive=lambda pid: True)
    assert lifecycle.read_server_state(path).pid == 111


def test_claim_overwrites_a_stale_record(tmp_path):
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=222), path)

    assert lifecycle.claim_server_record(_state(pid=333), path, alive=lambda pid: False)
    assert lifecycle.read_server_state(path).pid == 333


def test_claim_refuses_to_erase_a_live_foreign_record(tmp_path):
    path = tmp_path / "webapp.json"
    incumbent = _state(pid=444, data_dir="/checkout")
    lifecycle.write_server_state(incumbent, path)

    assert not lifecycle.claim_server_record(
        _state(pid=555), path, alive=lambda pid: True
    )
    # Nothing written: the incumbent's record is byte-for-byte intact.
    assert lifecycle.read_server_state(path) == incumbent


def test_claim_rewrites_the_callers_own_record(tmp_path):
    """Same PID is us, not a rival — re-registering must not deadlock on
    ourselves (a restarted server thread in one process, say)."""

    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=666, data_dir="/old"), path)

    assert lifecycle.claim_server_record(
        _state(pid=666, data_dir="/new"), path, alive=lambda pid: True
    )
    assert lifecycle.read_server_state(path).data_dir == "/new"


def test_registration_serves_unregistered_when_the_claim_is_refused(
    tmp_path, monkeypatch
):
    path = tmp_path / "webapp.json"
    incumbent = _state(pid=777)
    lifecycle.write_server_state(incumbent, path)

    # CR-91: the injected check must actually run. `claim_server_record`
    # resolves `alive` at call time precisely so this replacement is reachable;
    # when it was a definition-time default the guard silently consulted the
    # real process table instead, and the test passed only where some unrelated
    # process happened to hold PID 777.
    asked = []

    def _alive(pid):
        asked.append(pid)
        return True

    monkeypatch.setattr(lifecycle, "is_pid_alive", _alive)

    registration = lifecycle.ServerStateRegistration("127.0.0.1", 9999, path=path)
    with registration:
        assert asked == [777], "the injected liveness check was bypassed"
        assert not registration.registered
        assert registration.conflict == incumbent

    # The critical half: leaving the block must not delete a record we never
    # owned — that is how a live server becomes invisible to `stop`.
    assert lifecycle.read_server_state(path) == incumbent


def test_unregistered_warning_names_the_server_that_kept_the_record():
    message = lifecycle.unregistered_warning(_state(pid=888))

    assert "PID 888" in message
    assert "http://127.0.0.1:8000" in message
    assert "`status`" in message and "`stop`" in message


def test_restart_decline_message_points_at_the_dock_not_the_terminal():
    message = lifecycle.restart_decline_message(
        _state(pid=999, origin=lifecycle.ORIGIN_APP)
    )

    assert "PID 999" in message
    assert "Dock" in message
    assert "sidelinehd-extractor stop" in message


# --- The liveness probe (CR-94) ----------------------------------------------
#
# `is_pid_alive` backs `status`, `stop`, `restart`, and the desktop app's
# single-instance check. It probed with `os.kill(pid, 0)` — the correct POSIX
# idiom, and on Windows a `TerminateProcess` call, so `status` killed the
# server it was reporting on and a stale record aimed it at whatever process
# had inherited the PID.
#
# The real Win32 calls cannot be made here, but the Windows branch's *decisions*
# can: `_windows_kernel32` is a seam, and stubbing the DLL rather than the
# platform runs the whole table on macOS and Linux. So these tests carry the
# branch selector, the unchanged POSIX probe, every path through the handle
# probe, and — through the public function, on whatever OS is running — the
# property the whole finding is about: **asking must not change the answer.**
#
# What is left unverified until CI's windows-latest leg is only the ctypes
# bindings: whether the declared `argtypes`/`restype` match the real ABI.


def _recorder(calls, name, result):
    def _probe(pid):
        calls.append((name, pid))
        return result

    return _probe


def test_liveness_selector_uses_the_handle_probe_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle.os, "name", "nt")
    monkeypatch.setattr(
        lifecycle, "_is_pid_alive_windows", _recorder(calls, "nt", True)
    )
    monkeypatch.setattr(
        lifecycle, "_is_pid_alive_posix", _recorder(calls, "posix", True)
    )

    assert lifecycle.is_pid_alive(4321) is True
    # Not "both agree" — the signal probe must not be *reached* on Windows,
    # since reaching it is what fires TerminateProcess.
    assert calls == [("nt", 4321)]


def test_liveness_selector_uses_the_signal_probe_elsewhere(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle.os, "name", "posix")
    monkeypatch.setattr(
        lifecycle, "_is_pid_alive_windows", _recorder(calls, "nt", True)
    )
    monkeypatch.setattr(
        lifecycle, "_is_pid_alive_posix", _recorder(calls, "posix", False)
    )

    assert lifecycle.is_pid_alive(4321) is False
    assert calls == [("posix", 4321)]


def test_handle_probe_refuses_a_non_positive_pid():
    """The guard ahead of the ctypes call — it returns before `kernel32` is
    reached at all, so it needs no stub. A negative PID is a POSIX process
    *group*; DWORD cannot carry it."""

    assert lifecycle._is_pid_alive_windows(0) is False
    assert lifecycle._is_pid_alive_windows(-1) is False


class _FakeKernel32:
    """Stands in for `kernel32` so the Windows probe's decision table runs here.

    The stub is the *DLL*, not the platform — `_windows_kernel32` is the seam,
    and replacing it means no `os.name` patch is needed. `ctypes.wintypes`
    imports and works on macOS and Linux; the one Windows-only symbol is
    `ctypes.WinDLL`, and it lives behind this seam. What a stub cannot check is
    the bindings themselves — whether `argtypes`/`restype` match the real
    Win32 ABI — so that remains unverified until CI's windows-latest leg runs.
    What it does check is every decision this change makes.
    """

    def __init__(self, *, handle, exit_code=None, get_exit_code_succeeds=True):
        self.handle = handle
        self._exit_code = exit_code
        self._get_exit_code_succeeds = get_exit_code_succeeds
        self.open_calls = []
        self.closed = []

    def OpenProcess(self, access, inherit_handle, pid):  # noqa: N802 - the Win32 name
        self.open_calls.append((access, inherit_handle, pid))
        return self.handle

    def GetExitCodeProcess(self, handle, out_pointer):  # noqa: N802 - the Win32 name
        if not self._get_exit_code_succeeds:
            return 0
        ctypes.cast(out_pointer, wintypes.LPDWORD)[0] = self._exit_code
        return 1

    def CloseHandle(self, handle):  # noqa: N802 - the Win32 name
        self.closed.append(handle)
        return 1


@pytest.mark.parametrize(
    ("kwargs", "expected_alive", "expected_closes"),
    [
        # OpenProcess failed: the process is gone, or belongs to another user
        # and we may not ask. Both are reported as "not alive" by design — see
        # the helper's docstring. Nothing was opened, so nothing is closed.
        ({"handle": None}, False, 0),
        ({"handle": 0}, False, 0),
        # The handle opened, so the answer comes from the exit code. 259 is
        # written out rather than read from the module: STILL_ACTIVE is Win32's
        # number, not ours, and feeding the constant back in would make this
        # row agree with whatever the module happened to say.
        ({"handle": 77, "exit_code": 259}, True, 1),
        ({"handle": 77, "exit_code": 0}, False, 1),
        ({"handle": 77, "exit_code": 1}, False, 1),
        # GetExitCodeProcess itself failed. Conservative direction, same as
        # above — and the handle is still closed, which is what the `finally`
        # is for.
        ({"handle": 77, "get_exit_code_succeeds": False}, False, 1),
    ],
)
def test_handle_probe_decision_table(monkeypatch, kwargs, expected_alive, expected_closes):
    fake = _FakeKernel32(**kwargs)
    monkeypatch.setattr(lifecycle, "_windows_kernel32", lambda: fake)

    assert lifecycle._is_pid_alive_windows(4321) is expected_alive
    assert fake.closed == [fake.handle] * expected_closes


def test_handle_probe_asks_for_the_query_only_access_right(monkeypatch):
    """The access right is the whole reason this probe is non-destructive: it
    is the right to *ask after* a process and carries no right to touch it.
    Widening it passes the table above, so it is pinned here.

    `0x1000` is written out rather than read from the module for the same
    reason 259 is above — `PROCESS_QUERY_LIMITED_INFORMATION` is Win32's
    number. Asserting the module's own constant back at it would accept any
    value the module chose, including `PROCESS_ALL_ACCESS`.
    """

    fake = _FakeKernel32(handle=77, exit_code=259)
    monkeypatch.setattr(lifecycle, "_windows_kernel32", lambda: fake)

    lifecycle._is_pid_alive_windows(4321)

    assert fake.open_calls == [(0x1000, False, 4321)]


@pytest.mark.skipif(
    os.name == "nt", reason="the signal probe is exactly what must not run on Windows"
)
def test_signal_probe_reads_a_live_process_and_a_reaped_one():
    assert lifecycle._is_pid_alive_posix(os.getpid()) is True

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)

    assert lifecycle._is_pid_alive_posix(child.pid) is False


def test_liveness_probe_does_not_kill_the_process_it_is_asked_about():
    """CR-94's regression test — and the test the defect itself forbade.

    Every other caller of the real probe in this suite injects a fake, and
    `test_webapp.py` says why in as many words: a live PID "would kill pytest's
    parent on the windows-latest leg". That is the bug describing itself. With
    the handle probe in place the test is safe to write, and on Windows it is
    the only thing that actually proves the fix.

    **The evidence is how the child died, not `poll()`** — CR-101. A fork/exec
    child killed before it is ever scheduled leaves `poll()` returning `None`
    at every point this test could consult it (the parent's non-blocking
    `waitpid` keeps returning 0, and the resulting zombie still answers
    `os.kill(pid, 0)`), so a `poll()`-based version of this test let a
    destructive probe through on roughly ten runs in twelve, measured here.
    The exit status has no such race: only `terminate()` may set it.

    Fail it by making either branch destructive. SIGKILL on POSIX gives `-9`
    where `terminate()` gives `-SIGTERM`; restoring `os.kill(pid, 0)` on
    Windows gives exit code `0`, because that call is
    `TerminateProcess(handle, 0)`, where `terminate()` gives `1`.
    """

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert lifecycle.is_pid_alive(child.pid) is True

        # `wait_until_dead` polls this up to 120 times in a single `stop`, so a
        # probe that only kills on a later call is no better than one that
        # kills on the first — and a leaked handle would show up here too.
        for _ in range(5):
            assert lifecycle.is_pid_alive(child.pid) is True

        # Positive proof the child outlived the probing, rather than the
        # assertions above having been answered by a corpse.
        with pytest.raises(subprocess.TimeoutExpired):
            child.wait(timeout=0.5)
    finally:
        child.terminate()
        returncode = child.wait(timeout=30)

    # The load-bearing assertion: the child died of `terminate()` and of
    # nothing else. Anything the probe did to it lands here instead.
    expected = 1 if os.name == "nt" else -signal.SIGTERM
    assert returncode == expected, "the child did not die of terminate() — the probe killed it"

    # And it still reports a genuinely dead process as dead, which is what
    # lets `status` and `stop` clear a stale record.
    assert lifecycle.is_pid_alive(child.pid) is False
