"""Update check against GitHub Releases (item 67d).

Item 67a made staleness *visible* to someone who thinks to look at the build
stamp; this module makes it *arrive*: after the server is up, a daemon thread
asks GitHub whether a newer release exists, and the menubar offers a
Download item only when one does.

The whole module is built around one rule: a failed update check must be
indistinguishable from no update check. There is no network at a ballpark,
and nothing here may block launch, raise into the launcher, or surface an
error. Offline, rate-limited, malformed JSON, a non-semver tag — all of
them mean "show nothing."

There is deliberately no self-replacement: the update item opens the
Releases page and the user swaps the bundle by hand. An auto-swapped
ad-hoc-signed bundle arrives re-quarantined and can leave the user with an
app macOS refuses to open — a worse failure than a stale one.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import urllib.request
from typing import Callable, Optional, Tuple

RELEASES_PAGE_URL = "https://github.com/BryceWillis/softball-vision/releases/latest"
LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/BryceWillis/softball-vision/releases/latest"
)

#: ``check_for_updates = false`` under ``[defaults]`` in sidelinehd.cfg
#: (item 28's config, read from the data dir the desktop app chdirs into)
#: suppresses the request entirely — not merely the display of the result.
UPDATE_CHECK_CONFIG_KEY = "check_for_updates"
#: Env override, stronger than the config file: falsey values ("0", "false",
#: "no", "off") suppress the check — the CI selftest sets this so a runner
#: never touches the network — and truthy values force it on even when not
#: frozen, which is the manual-testing path for the source tree.
UPDATE_CHECK_ENV_VAR = "SIDELINEHD_CHECK_FOR_UPDATES"

#: Hard cap per the spec: on a ballpark hotspot a hung socket must bound
#: itself rather than keep the thread alive indefinitely.
DEFAULT_TIMEOUT_SECONDS = 3.0

_FALSEY = frozenset({"0", "false", "no", "off"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})

_VERSION_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def parse_version_tag(tag: object) -> Optional[Tuple[int, int, int]]:
    """``v0.3.0`` → ``(0, 3, 0)``; anything else → ``None``.

    Never guess an ordering from a string that does not match the pattern:
    ``release-2026-07``, ``v0.3``, and a bare ``0.3.0`` all mean "no update
    information," not a comparison.
    """

    if not isinstance(tag, str):
        return None
    match = _VERSION_TAG_PATTERN.match(tag.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def latest_release(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Optional[str]:
    """The latest release's ``tag_name``, or ``None`` on any failure at all.

    Non-200 (including a 403 rate limit), a redirect to HTML, malformed
    JSON, a missing or non-string ``tag_name``, timeout, offline — all
    ``None``. No retry and no backoff state; the next launch is the next
    check.
    """

    try:
        request = urllib.request.Request(
            LATEST_RELEASE_API_URL,
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        tag = payload.get("tag_name")
        if not isinstance(tag, str) or not tag.strip():
            return None
        return tag.strip()
    except Exception:
        return None


def update_check_enabled() -> bool:
    """Whether the check may run — decided before any network I/O.

    Precedence: env var (either direction) > config-file opt-out > the
    default, which is frozen-only — the check is a bundle affordance, and a
    developer mid-version should not see an offer for a release older than
    their tree (``git pull`` remains the source install's update path).
    """

    env = (os.environ.get(UPDATE_CHECK_ENV_VAR) or "").strip().lower()
    if env in _FALSEY:
        return False
    if env in _TRUTHY:
        return True
    try:
        # Lazy import keeps this module import-safe headless and cheap.
        from sidelinehd_extractor.config import load_project_config_values

        value = load_project_config_values().get(UPDATE_CHECK_CONFIG_KEY, "")
    except Exception:
        value = ""
    if value.strip().lower() in _FALSEY:
        return False
    return bool(getattr(sys, "frozen", False))


def available_update(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Optional[str]:
    """The newer release's tag (e.g. ``"v0.3.0"``), or ``None``.

    ``None`` covers every non-update outcome alike: up to date, ahead of the
    latest tag, disabled, offline, or any failure — by design there is no
    way to distinguish them, so no caller can accidentally surface an error.
    """

    try:
        if not update_check_enabled():
            return None
        from sidelinehd_extractor.build_info import build_stamp

        current = parse_version_tag(f"v{build_stamp().version}")
        if current is None:
            return None
        tag = latest_release(timeout=timeout)
        latest = parse_version_tag(tag)
        if latest is None or latest <= current:
            return None
        return tag
    except Exception:
        return None


def update_menu_title(tag: str) -> str:
    """The menubar item's label for an available update."""

    return f"Update available: {tag} — Download…"


class UpdateCheck:
    """Runs ``available_update`` once, on a daemon thread, and holds the result.

    The GUI never joins the thread: it polls ``done``/``result`` from a
    ``rumps.Timer`` (main-thread) callback, which is how the background
    result reaches the menu without touching AppKit from a worker thread.
    A daemon thread cannot block Quit, and the timeout above bounds it
    anyway.
    """

    def __init__(self, check: Callable[[], Optional[str]] = available_update) -> None:
        self._check = check
        self._result: Optional[str] = None
        self._done = threading.Event()

    def start(self) -> None:
        threading.Thread(
            target=self._run, name="sidelinehd-update-check", daemon=True
        ).start()

    def _run(self) -> None:
        try:
            self._result = self._check()
        except Exception:
            # available_update already swallows everything; this catches a
            # misbehaving injected check so the thread can never die loudly.
            self._result = None
        finally:
            self._done.set()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def result(self) -> Optional[str]:
        """The update tag, or ``None`` — never a partial read mid-check."""

        return self._result if self._done.is_set() else None
