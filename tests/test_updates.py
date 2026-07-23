"""Tests for the update check (item 67d).

The HTTP layer is stubbed throughout — no test touches the network. The
load-bearing properties: a failed check is indistinguishable from no check
(``None`` everywhere, nothing raised), and the opt-outs suppress the request
itself, not merely the display of the result.
"""

from __future__ import annotations

import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from sidelinehd_extractor import build_info, updates
from sidelinehd_extractor.build_info import BuildStamp
from sidelinehd_extractor.updates import (
    UpdateCheck,
    available_update,
    latest_release,
    parse_version_tag,
    update_check_enabled,
    update_menu_title,
)


class _FakeResponse:
    def __init__(self, status=200, body=b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, status=200, body=b"{}", error=None):
    """Stub ``urllib.request.urlopen``; returns the recorded (request, timeout) calls."""

    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append((request, timeout))
        if error is not None:
            raise error
        return _FakeResponse(status=status, body=body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def _clear_gates(monkeypatch, tmp_path, frozen=True):
    """A clean gate state: no env override, no cfg file, chosen frozen state."""

    monkeypatch.delenv(updates.UPDATE_CHECK_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)  # no sidelinehd.cfg here
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)


def _stub_stamp(monkeypatch, version="0.2.0"):
    monkeypatch.setattr(
        build_info,
        "build_stamp",
        lambda: BuildStamp(version=version, sha=None, built_at=None, origin="bundle"),
    )


# --- parse_version_tag ------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.3.0", (0, 3, 0)),
        ("v10.20.30", (10, 20, 30)),
        (" v0.3.0 ", (0, 3, 0)),
    ],
)
def test_parse_version_tag_accepts_v_semver(tag, expected):
    assert parse_version_tag(tag) == expected


@pytest.mark.parametrize(
    "tag",
    [
        "release-2026-07",
        "v0.3",
        "0.3.0",  # no leading v
        "v0.3.0.1",
        "v0.3.0-rc1",
        "",
        None,
        3,
        ["v0.3.0"],
    ],
)
def test_parse_version_tag_rejects_everything_else(tag):
    """Never guess an ordering from a string outside the pattern."""

    assert parse_version_tag(tag) is None


# --- latest_release ---------------------------------------------------------


def test_latest_release_returns_the_tag(monkeypatch):
    calls = _serve(monkeypatch, body=b'{"tag_name": "v0.3.0"}')

    assert latest_release() == "v0.3.0"
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == updates.LATEST_RELEASE_API_URL
    assert timeout == updates.DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 403, "body": b'{"message": "rate limited"}'},  # rate limit
        {"body": b"<html>error page</html>"},  # not JSON
        {"body": b'["v0.3.0"]'},  # JSON, wrong shape
        {"body": b"{}"},  # tag_name missing
        {"body": b'{"tag_name": 3}'},  # tag_name wrong type
        {"body": b'{"tag_name": ""}'},  # tag_name empty
        {"error": urllib.error.URLError("no network")},  # offline
        {
            "error": urllib.error.HTTPError(
                updates.LATEST_RELEASE_API_URL, 404, "not found", None, None
            )
        },
        {"error": TimeoutError("timed out")},
    ],
)
def test_latest_release_returns_none_on_any_failure(monkeypatch, kwargs):
    _serve(monkeypatch, **kwargs)

    assert latest_release() is None


# --- update_check_enabled ---------------------------------------------------


def test_enabled_by_default_only_when_frozen(monkeypatch, tmp_path):
    """The check is a bundle affordance; a source run skips it."""

    _clear_gates(monkeypatch, tmp_path, frozen=True)
    assert update_check_enabled() is True

    _clear_gates(monkeypatch, tmp_path, frozen=False)
    assert update_check_enabled() is False


def test_config_opt_out_disables_a_frozen_bundle(monkeypatch, tmp_path):
    _clear_gates(monkeypatch, tmp_path, frozen=True)
    (tmp_path / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = false\n", encoding="utf-8"
    )

    assert update_check_enabled() is False


def test_config_opt_out_is_read_from_an_explicit_cwd(monkeypatch, tmp_path):
    """M7 / 70f: the desktop passes its data dir as ``cwd`` so the opt-out keeps
    working now that the launcher no longer chdirs into the data dir — the CWD
    itself has no config."""

    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = false\n", encoding="utf-8"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _clear_gates(monkeypatch, elsewhere, frozen=True)  # CWD has no cfg

    # Read from the data dir: the opt-out is honoured.
    assert update_check_enabled(cwd=data_root) is False
    # Read from the CWD (no cfg): a frozen bundle defaults to enabled — proving
    # the base is what carries the opt-out, not the process CWD.
    assert update_check_enabled() is True


def test_config_explicit_true_keeps_a_frozen_bundle_enabled(monkeypatch, tmp_path):
    _clear_gates(monkeypatch, tmp_path, frozen=True)
    (tmp_path / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = true\n", encoding="utf-8"
    )

    assert update_check_enabled() is True


def test_config_unrecognized_value_falls_back_to_the_default(monkeypatch, tmp_path):
    _clear_gates(monkeypatch, tmp_path, frozen=True)
    (tmp_path / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = maybe\n", encoding="utf-8"
    )

    assert update_check_enabled() is True


def test_env_var_zero_wins_over_everything(monkeypatch, tmp_path):
    _clear_gates(monkeypatch, tmp_path, frozen=True)
    (tmp_path / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = true\n", encoding="utf-8"
    )
    monkeypatch.setenv(updates.UPDATE_CHECK_ENV_VAR, "0")

    assert update_check_enabled() is False


def test_env_var_one_forces_the_check_from_source(monkeypatch, tmp_path):
    """The manual-testing path: the source tree can demo the update item."""

    _clear_gates(monkeypatch, tmp_path, frozen=False)
    monkeypatch.setenv(updates.UPDATE_CHECK_ENV_VAR, "1")

    assert update_check_enabled() is True


# --- available_update -------------------------------------------------------


def _enable(monkeypatch, tmp_path):
    _clear_gates(monkeypatch, tmp_path, frozen=True)


def test_available_update_returns_a_newer_tag(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch, version="0.2.0")
    _serve(monkeypatch, body=b'{"tag_name": "v0.3.0"}')

    assert available_update() == "v0.3.0"


@pytest.mark.parametrize(
    ("current", "tag"),
    [
        ("0.3.0", "v0.3.0"),  # equal
        ("0.4.0", "v0.3.0"),  # ahead of the latest tag
        ("0.2.0", "release-2026-07"),  # malformed tag
        ("0.2.0", "v0.3"),  # malformed tag
    ],
)
def test_available_update_returns_none_without_a_newer_release(
    monkeypatch, tmp_path, current, tag
):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch, version=current)
    _serve(monkeypatch, body=f'{{"tag_name": "{tag}"}}'.encode("utf-8"))

    assert available_update() is None


def test_available_update_returns_none_offline(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch)
    _serve(monkeypatch, error=urllib.error.URLError("no network"))

    assert available_update() is None


def test_available_update_skips_the_request_on_an_unparseable_current_version(
    monkeypatch, tmp_path
):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch, version="0.3.0.dev1")
    calls = _serve(monkeypatch)

    assert available_update() is None
    assert calls == []


def test_config_opt_out_suppresses_the_request_entirely(monkeypatch, tmp_path):
    """No HTTP call is attempted — not merely nothing displayed."""

    _enable(monkeypatch, tmp_path)
    (tmp_path / "sidelinehd.cfg").write_text(
        "[defaults]\ncheck_for_updates = false\n", encoding="utf-8"
    )
    _stub_stamp(monkeypatch)
    calls = _serve(monkeypatch)

    assert available_update() is None
    assert calls == []


def test_env_var_suppresses_the_request_entirely(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(updates.UPDATE_CHECK_ENV_VAR, "0")
    _stub_stamp(monkeypatch)
    calls = _serve(monkeypatch)

    assert available_update() is None
    assert calls == []


def test_available_update_swallows_an_unexpected_raise(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch)
    monkeypatch.setattr(
        updates, "latest_release", lambda timeout: (_ for _ in ()).throw(RuntimeError)
    )

    assert available_update() is None


# --- UpdateCheck / menu label ----------------------------------------------


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_update_check_runs_on_a_named_daemon_thread():
    release = threading.Event()

    def blocking_check():
        release.wait(5)
        return "v9.9.9"

    check = UpdateCheck(check=blocking_check)
    assert check.done is False and check.result is None
    check.start()
    worker = next(
        thread
        for thread in threading.enumerate()
        if thread.name == "sidelinehd-update-check"
    )
    assert worker.daemon  # cannot block Quit
    assert check.result is None  # never a partial read mid-check
    release.set()
    worker.join(5)
    assert check.done is True
    assert check.result == "v9.9.9"


def test_update_check_holds_none_when_no_update(monkeypatch):
    check = UpdateCheck(check=lambda: None)
    check.start()
    assert _wait_for(lambda: check.done)
    assert check.result is None


def test_update_check_swallows_a_raising_check():
    def broken_check():
        raise RuntimeError("boom")

    check = UpdateCheck(check=broken_check)
    check.start()
    assert _wait_for(lambda: check.done)
    assert check.result is None


def test_update_menu_title():
    assert update_menu_title("v0.3.0") == "Update available: v0.3.0 — Download…"
