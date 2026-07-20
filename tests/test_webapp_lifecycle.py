from __future__ import annotations

import signal
from datetime import datetime, timezone

from sidelinehd_extractor.webapp import lifecycle


def _state(pid: int = 1234) -> lifecycle.ServerState:
    return lifecycle.ServerState(
        pid=pid,
        host="127.0.0.1",
        port=8000,
        version="0.test",
        started_at="2026-07-10T12:00:00Z",
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
    path = tmp_path / "webapp.json"
    lifecycle.write_server_state(_state(pid=3333), path)
    sent = []
    monkeypatch.setattr(lifecycle, "wait_until_dead", lambda *args, **kwargs: False)

    message = lifecycle.stop_recorded_server(
        path,
        kill=lambda pid, sig: sent.append((pid, sig)),
        alive=lambda pid: True,
    )

    assert message == "Stopped (PID 3333)."
    assert sent[0] == (3333, signal.SIGTERM)
    assert sent[1][0] == 3333
    assert sent[1][1] == getattr(signal, "SIGKILL", signal.SIGTERM)
    assert not path.exists()


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
