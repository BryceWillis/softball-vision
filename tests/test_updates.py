"""Tests for the update check (item 67d).

The HTTP layer is stubbed throughout — no test touches the network. The
load-bearing properties: a failed check is indistinguishable from no check
(``None`` everywhere, nothing raised), and the opt-outs suppress the request
itself, not merely the display of the result.
"""

from __future__ import annotations

import subprocess
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


def test_available_update_forwards_cwd_to_the_enable_gate(monkeypatch, tmp_path):
    """`available_update(cwd=)` reads the opt-out from the cwd it is handed.

    Pins the `available_update(cwd=)` → `update_check_enabled(cwd=)` forwarding
    that 70f relies on so a bundle's data-dir opt-out is honoured (CR-98). The
    leaf gate is covered with an explicit cwd elsewhere; the forwarding was
    not, and a refactor dropping it would silently read `check_for_updates`
    from the launcher's CWD (`/`) with the whole suite green.
    """

    seen = []

    def _record_cwd(cwd=None):
        seen.append(cwd)
        return False  # disabled → short-circuit before any network I/O

    monkeypatch.setattr(updates, "update_check_enabled", _record_cwd)
    calls = _serve(monkeypatch)
    sentinel = tmp_path / "data-dir"

    assert available_update(cwd=sentinel) is None
    assert seen == [sentinel]
    assert calls == []  # the gate said no → the request is never attempted


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


# --- The self-updater (item 69c) --------------------------------------------
#
# No test here touches the network, codesign, ditto, or spawns a shell: every
# I/O seam is injected. The load-bearing properties are the gate (D4 — the
# download must be signed by the same team, or nothing happens, with no bypass)
# and the "nothing changes on failure" contract.

import json  # noqa: E402 — grouped with the 69c helpers it serves

from pathlib import Path  # noqa: E402

from sidelinehd_extractor.updates import (  # noqa: E402
    Installability,
    ReleaseUpdate,
    UpdateError,
    UpdateInstaller,
    available_release,
    clear_update_staging,
    codesign_team,
    codesign_verify,
    download_asset,
    enclosing_app_bundle,
    parse_release_asset,
    parse_team_identifier,
    perform_update_install,
    read_bundle_short_version,
    render_swap_script,
    spawn_swap_helper,
    update_installability,
    verify_staged_bundle,
)


# --- available_release / parse_release_asset --------------------------------


def _asset_body(
    tag="v0.3.0",
    *,
    name=updates.RELEASE_ASSET_NAME,
    url="https://example.com/app.zip",
    size=4096,
    with_asset=True,
):
    payload = {"tag_name": tag}
    if with_asset:
        payload["assets"] = [
            {"name": name, "browser_download_url": url, "size": size}
        ]
    return json.dumps(payload).encode("utf-8")


def test_available_release_returns_the_tag_and_asset(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch, version="0.2.0")
    _serve(monkeypatch, body=_asset_body("v0.3.0", size=4096))

    result = available_release()
    assert result == ReleaseUpdate(
        tag="v0.3.0", asset_url="https://example.com/app.zip", asset_size=4096
    )


def test_available_release_carries_the_tag_when_the_asset_is_absent(
    monkeypatch, tmp_path
):
    """A tag can be published minutes before CI uploads its zip. The release is
    surfaced (so the menu shows the Releases fallback) but not installable."""

    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch, version="0.2.0")
    _serve(monkeypatch, body=_asset_body("v0.3.0", with_asset=False))

    result = available_release()
    assert result is not None
    assert result.tag == "v0.3.0"
    assert result.asset_url is None and result.asset_size is None


def test_available_release_none_when_not_newer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _stub_stamp(monkeypatch, version="0.3.0")
    _serve(monkeypatch, body=_asset_body("v0.3.0"))

    assert available_release() is None


def test_available_release_none_when_disabled(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv(updates.UPDATE_CHECK_ENV_VAR, "0")
    _stub_stamp(monkeypatch)
    calls = _serve(monkeypatch, body=_asset_body())

    assert available_release() is None
    assert calls == []  # the gate short-circuits before any network I/O


def test_available_release_forwards_cwd_to_the_gate(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(
        updates, "update_check_enabled", lambda cwd=None: seen.append(cwd) or False
    )
    calls = _serve(monkeypatch, body=_asset_body())
    sentinel = tmp_path / "data-dir"

    assert available_release(cwd=sentinel) is None
    assert seen == [sentinel]
    assert calls == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"assets": [{"name": updates.RELEASE_ASSET_NAME,
                         "browser_download_url": "https://x/y.zip", "size": 10}]},
            ("https://x/y.zip", 10),
        ),
        # A foreign asset name is ignored — only our exact zip counts.
        ({"assets": [{"name": "other.zip",
                      "browser_download_url": "https://x/y.zip", "size": 10}]},
         (None, None)),
        # Non-https URL → treated as absent (we will not fetch a bundle over http).
        ({"assets": [{"name": updates.RELEASE_ASSET_NAME,
                      "browser_download_url": "http://x/y.zip", "size": 10}]},
         (None, None)),
        # No assets at all.
        ({"tag_name": "v0.3.0"}, (None, None)),
        ({"assets": "nope"}, (None, None)),
        (None, (None, None)),
        # A missing/zero size keeps the URL — the download caps itself anyway.
        ({"assets": [{"name": updates.RELEASE_ASSET_NAME,
                      "browser_download_url": "https://x/y.zip"}]},
         ("https://x/y.zip", None)),
        ({"assets": [{"name": updates.RELEASE_ASSET_NAME,
                      "browser_download_url": "https://x/y.zip", "size": 0}]},
         ("https://x/y.zip", None)),
    ],
)
def test_parse_release_asset(payload, expected):
    assert parse_release_asset(payload) == expected


# --- Installability preconditions -------------------------------------------


def test_enclosing_app_bundle_finds_the_dot_app():
    exe = Path("/Applications/SidelineHD Extractor.app/Contents/MacOS/sidelinehd")
    assert enclosing_app_bundle(exe) == Path(
        "/Applications/SidelineHD Extractor.app"
    )


def test_enclosing_app_bundle_none_from_source():
    assert enclosing_app_bundle(Path("/usr/local/bin/python3")) is None


def test_installability_happy_path():
    result = update_installability(
        frozen=True,
        executable=Path("/Applications/SidelineHD Extractor.app/Contents/MacOS/x"),
        is_writable=lambda _p: True,
    )
    assert result.installable is True
    assert result.app_path == Path("/Applications/SidelineHD Extractor.app")
    assert result.reason == ""


@pytest.mark.parametrize(
    ("frozen", "executable", "writable"),
    [
        # A source run updates via `git pull`, never in place.
        (False, "/Applications/SidelineHD Extractor.app/Contents/MacOS/x", True),
        # No enclosing .app.
        (True, "/usr/local/bin/python3", True),
        # App-Translocated: a read-only randomized mount, no in-place swap.
        (True, "/private/var/folders/AppTranslocation/A/SidelineHD Extractor.app/"
               "Contents/MacOS/x", True),
        # Parent directory not writable.
        (True, "/Applications/SidelineHD Extractor.app/Contents/MacOS/x", False),
    ],
)
def test_installability_refuses(frozen, executable, writable):
    result = update_installability(
        frozen=frozen, executable=Path(executable), is_writable=lambda _p: writable
    )
    assert result.installable is False
    assert result.reason and result.app_path is None
    assert isinstance(result, Installability)


# --- download_asset ---------------------------------------------------------


class _FakeDownloadResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read(self, _size):
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_asset_streams_to_disk_and_reports_progress(tmp_path):
    dest = tmp_path / "app.zip"
    fractions = []

    def fake_urlopen(url, timeout=None):
        assert url == "https://example.com/app.zip"
        return _FakeDownloadResponse([b"aaaa", b"bbbb"])

    download_asset(
        "https://example.com/app.zip",
        dest,
        expected_size=8,
        progress=fractions.append,
        urlopen=fake_urlopen,
    )

    assert dest.read_bytes() == b"aaaabbbb"
    assert fractions[-1] == 1.0
    assert fractions == [0.5, 1.0, 1.0]  # mid, complete, and the final 1.0


def test_download_asset_refuses_a_body_over_the_cap(tmp_path):
    def fake_urlopen(url, timeout=None):
        return _FakeDownloadResponse([b"x" * 100])

    with pytest.raises(UpdateError):
        download_asset(
            "https://example.com/app.zip",
            tmp_path / "app.zip",
            urlopen=fake_urlopen,
            cap=10,
        )


def test_download_asset_refuses_a_non_https_url(tmp_path):
    with pytest.raises(UpdateError):
        download_asset("http://example.com/app.zip", tmp_path / "app.zip")


# --- Signature gate ---------------------------------------------------------


def test_parse_team_identifier_reads_the_team():
    out = "Executable=/x\nIdentifier=dev.sidelinehd\nTeamIdentifier=TEAM1234567\n"
    assert parse_team_identifier(out) == "TEAM1234567"


@pytest.mark.parametrize(
    "text",
    ["TeamIdentifier=not set", "no team line here", "", None, 3],
)
def test_parse_team_identifier_none_without_a_team(text):
    assert parse_team_identifier(text) is None


def _fake_codesign(*, verify_rc=0, team_out="TeamIdentifier=TEAM1234567"):
    """A `run` seam answering codesign --verify and codesign -d."""

    def run(cmd):
        if "--verify" in cmd:
            return (verify_rc, "")
        if "-d" in cmd:
            return (0, team_out)
        raise AssertionError(f"unexpected command {cmd}")

    return run


def test_codesign_verify_and_team_over_injected_output():
    run = _fake_codesign()
    assert codesign_verify(Path("/x.app"), run=run) is True
    assert codesign_team(Path("/x.app"), run=run) == "TEAM1234567"


def test_codesign_team_none_on_nonzero_exit():
    assert codesign_team(Path("/x.app"), run=lambda cmd: (1, "error")) is None


def test_read_bundle_short_version(tmp_path):
    import plistlib

    app = tmp_path / "SidelineHD Extractor.app"
    (app / "Contents").mkdir(parents=True)
    with (app / "Contents" / "Info.plist").open("wb") as fh:
        plistlib.dump({"CFBundleShortVersionString": "0.6.0"}, fh)

    assert read_bundle_short_version(app) == "0.6.0"


def test_read_bundle_short_version_none_when_absent(tmp_path):
    assert read_bundle_short_version(tmp_path / "nope.app") is None


@pytest.mark.parametrize(
    ("kwargs", "ok"),
    [
        # Valid, same team, matching version → the only pass.
        (dict(verify_ok=True, staged_team="T", running_team="T",
              staged_version="0.6.0", offered_tag="v0.6.0"), True),
        # Different team → the security refusal.
        (dict(verify_ok=True, staged_team="A", running_team="B",
              staged_version="0.6.0", offered_tag="v0.6.0"), False),
        # Signature does not verify.
        (dict(verify_ok=False, staged_team="T", running_team="T",
              staged_version="0.6.0", offered_tag="v0.6.0"), False),
        # Download has no team (ad-hoc).
        (dict(verify_ok=True, staged_team=None, running_team="T",
              staged_version="0.6.0", offered_tag="v0.6.0"), False),
        # Running app has no team (ad-hoc dev build can't self-update).
        (dict(verify_ok=True, staged_team="T", running_team=None,
              staged_version="0.6.0", offered_tag="v0.6.0"), False),
        # Version mismatch — a wrong/stale asset must not swap in.
        (dict(verify_ok=True, staged_team="T", running_team="T",
              staged_version="0.5.0", offered_tag="v0.6.0"), False),
        # Unparseable staged version.
        (dict(verify_ok=True, staged_team="T", running_team="T",
              staged_version=None, offered_tag="v0.6.0"), False),
    ],
)
def test_verify_staged_bundle(kwargs, ok):
    result, reason = verify_staged_bundle(**kwargs)
    assert result is ok
    assert (reason == "") is ok  # a refusal always carries a reason


# --- render_swap_script -----------------------------------------------------


def _swap_script(reopen=True, app="/Applications/SidelineHD Extractor.app"):
    return render_swap_script(
        pid=4321,
        staged_app="/data/updates/extracted/SidelineHD Extractor.app",
        target_app=app,
        park_path="/data/updates/previous-SidelineHD Extractor.app",
        reopen=reopen,
    )


def test_swap_script_quotes_the_space_in_the_app_name():
    script = _swap_script()
    # Single-quoted so the space cannot split the mv/open arguments.
    assert "'/Applications/SidelineHD Extractor.app'" in script
    assert "'/data/updates/extracted/SidelineHD Extractor.app'" in script


def test_swap_script_uses_absolute_binaries_and_a_bounded_wait():
    script = _swap_script()
    assert "/bin/mv" in script and "/usr/bin/open" in script
    assert "/bin/kill -0" in script and "/bin/sleep" in script
    # No bare binary names — the no-PATH-resolution rule.
    assert "\nmv " not in script and "\nopen " not in script
    assert "-ge 60" in script  # the bounded wait for our PID to exit


def test_swap_script_reopen_flag_is_honored_both_ways():
    assert "/usr/bin/open" in _swap_script(reopen=True)
    assert "/usr/bin/open" not in _swap_script(reopen=False)


def test_swap_script_is_valid_shell_for_both_reopen_values():
    # CR-99: with reopen=False the reopen line was the only statement in the
    # success `then`, leaving it empty — a POSIX `sh` syntax error that aborted
    # the helper before any `mv`, so the `stop`-with-staged path never swapped.
    # `sh -n` parses without executing; both scripts must be syntactically valid.
    for reopen in (True, False):
        script = _swap_script(reopen=reopen)
        result = subprocess.run(
            ["/bin/sh", "-n", "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        assert result.returncode == 0, (
            f"rendered swap script (reopen={reopen}) is not valid shell: "
            f"{result.stderr.decode(errors='replace')}"
        )


def test_swap_script_restores_the_original_on_a_failed_move_in():
    script = _swap_script()
    # The else branch moves the parked bundle back to the target.
    assert (
        "/bin/mv '/data/updates/previous-SidelineHD Extractor.app' "
        "'/Applications/SidelineHD Extractor.app'" in script
    )


def test_swap_script_escapes_an_embedded_single_quote():
    script = render_swap_script(
        pid=1,
        staged_app="/a'b.app",
        target_app="/c.app",
        park_path="/p.app",
        reopen=False,
    )
    assert "'/a'\\''b.app'" in script


def test_spawn_swap_helper_launches_detached():
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs

    spawn_swap_helper("#!/bin/sh\necho hi\n", popen=fake_popen)
    assert calls["args"][:2] == ["/bin/sh", "-c"]
    assert calls["args"][2] == "#!/bin/sh\necho hi\n"
    assert calls["kwargs"]["start_new_session"] is True


# --- perform_update_install -------------------------------------------------


def _stage_a_bundle(extract_dir, *, version="0.6.0"):
    """A fake `extract` that materializes a signed-looking .app to stage."""

    import plistlib

    def extract(zip_path, dest_dir, *, run):
        app = Path(dest_dir) / "SidelineHD Extractor.app"
        (app / "Contents").mkdir(parents=True)
        with (app / "Contents" / "Info.plist").open("wb") as fh:
            plistlib.dump({"CFBundleShortVersionString": version}, fh)

    return extract


def _install_seams(tmp_path, *, staged_team="TEAM1234567", running_team="TEAM1234567",
                   verify_rc=0, version="0.6.0"):
    def fake_urlopen(url, timeout=None):
        return _FakeDownloadResponse([b"zipbytes"])

    def run(cmd):
        if "--verify" in cmd:
            return (verify_rc, "")
        if "-d" in cmd:
            # The running app is the one under /Applications; the staged one is
            # under the data dir. Answer each with its configured team.
            target = cmd[-1]
            team = running_team if "updates" not in target else staged_team
            out = f"TeamIdentifier={team}" if team else "TeamIdentifier=not set"
            return (0, out)
        raise AssertionError(cmd)

    return dict(
        urlopen=fake_urlopen,
        run=run,
        extract=_stage_a_bundle(tmp_path, version=version),
    )


def test_perform_update_install_stages_a_valid_bundle(tmp_path):
    release = ReleaseUpdate(
        tag="v0.6.0", asset_url="https://x/app.zip", asset_size=8
    )
    staged = perform_update_install(
        release,
        data_dir=tmp_path,
        running_app=Path("/Applications/SidelineHD Extractor.app"),
        **_install_seams(tmp_path),
    )
    assert staged.name == "SidelineHD Extractor.app"
    assert staged.exists()
    assert (tmp_path / "updates" / "download.zip").exists()


def test_perform_update_install_refuses_a_different_team(tmp_path):
    release = ReleaseUpdate(tag="v0.6.0", asset_url="https://x/app.zip", asset_size=8)
    with pytest.raises(UpdateError):
        perform_update_install(
            release,
            data_dir=tmp_path,
            running_app=Path("/Applications/SidelineHD Extractor.app"),
            **_install_seams(tmp_path, staged_team="DIFFERENT0"),
        )


def test_perform_update_install_refuses_a_version_mismatch(tmp_path):
    release = ReleaseUpdate(tag="v0.6.0", asset_url="https://x/app.zip", asset_size=8)
    with pytest.raises(UpdateError):
        perform_update_install(
            release,
            data_dir=tmp_path,
            running_app=Path("/Applications/SidelineHD Extractor.app"),
            **_install_seams(tmp_path, version="0.5.0"),
        )


def test_perform_update_install_refuses_a_release_without_an_asset(tmp_path):
    release = ReleaseUpdate(tag="v0.6.0", asset_url=None, asset_size=None)
    with pytest.raises(UpdateError):
        perform_update_install(
            release,
            data_dir=tmp_path,
            running_app=Path("/Applications/x.app"),
        )


# --- UpdateInstaller / cleanup ----------------------------------------------


def test_update_installer_reaches_staged(tmp_path):
    marker = tmp_path / "staged.app"

    def fake_install(release, *, data_dir, running_app, progress):
        progress(0.5)
        progress(1.0)
        return marker

    installer = UpdateInstaller(install=fake_install)
    assert installer.phase == UpdateInstaller.PHASE_IDLE
    release = ReleaseUpdate(tag="v0.6.0", asset_url="https://x", asset_size=1)
    installer.start(release, data_dir=tmp_path, running_app=Path("/x.app"))

    assert _wait_for(lambda: installer.phase == UpdateInstaller.PHASE_STAGED)
    assert installer.staged_app_path == marker
    assert installer.progress == 1.0


def test_update_installer_failure_cleans_the_staging_dir(tmp_path):
    staging = tmp_path / "updates"
    staging.mkdir()
    (staging / "download.zip").write_bytes(b"partial")

    def boom(release, *, data_dir, running_app, progress):
        raise UpdateError("verification failed")

    installer = UpdateInstaller(install=boom)
    installer.start(
        ReleaseUpdate(tag="v0.6.0", asset_url="https://x", asset_size=1),
        data_dir=tmp_path,
        running_app=Path("/x.app"),
    )

    assert _wait_for(lambda: installer.phase == UpdateInstaller.PHASE_FAILED)
    assert installer.staged_app_path is None  # never advertised on failure
    assert installer.error == "verification failed"
    assert not staging.exists()  # cleaned up


def test_update_installer_ignores_a_second_start_while_downloading(tmp_path):
    import threading as _threading

    release_first = _threading.Event()
    starts = []

    def slow_install(release, *, data_dir, running_app, progress):
        starts.append(release.tag)
        release_first.wait(5)
        return tmp_path / "staged.app"

    installer = UpdateInstaller(install=slow_install)
    r1 = ReleaseUpdate(tag="v0.6.0", asset_url="https://x", asset_size=1)
    installer.start(r1, data_dir=tmp_path, running_app=Path("/x.app"))
    assert _wait_for(lambda: installer.phase == UpdateInstaller.PHASE_DOWNLOADING)
    installer.start(r1, data_dir=tmp_path, running_app=Path("/x.app"))  # no-op
    release_first.set()
    assert _wait_for(lambda: installer.phase == UpdateInstaller.PHASE_STAGED)
    assert starts == ["v0.6.0"]  # only one download ever began


def test_clear_update_staging_removes_the_dir(tmp_path):
    staging = tmp_path / "updates"
    (staging / "extracted").mkdir(parents=True)
    (staging / "download.zip").write_bytes(b"x")

    clear_update_staging(tmp_path)
    assert not staging.exists()


def test_clear_update_staging_tolerates_absence(tmp_path):
    clear_update_staging(tmp_path)  # must not raise when nothing is staged
