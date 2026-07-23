"""Update check and self-updater against GitHub Releases (items 67d, 69c).

Item 67a made staleness *visible* to someone who thinks to look at the build
stamp; item 67d made it *arrive*: after the server is up, a daemon thread asks
GitHub whether a newer release exists, and the app's menus surface it only when
one does. M6 slice 69c turns that signal into an action — the app can now
download the new release, verify it against its own signing identity, and swap
itself for it on the next quit, reopening as the new version.

The check half is built around one rule, unchanged: a failed update *check*
must be indistinguishable from no check. There is no network at a ballpark, and
nothing in the check may block launch, raise into the launcher, or surface an
error. Offline, rate-limited, malformed JSON, a non-semver tag — all of them
mean "show nothing." The *install* half adds exactly one loud surface: a
failure after the user has clicked "Update Now", because by then silence would
be a lie (D3/69c). Everything else in the install path still fails closed —
nothing is downloaded or replaced without a person asking, and any failure
leaves the installed bundle untouched and the staging dir cleaned.

Self-replacement was previously forbidden here, on the reasoning that an
auto-swapped *ad-hoc-signed* bundle could arrive re-quarantined and unopenable.
That premise fell with 69a: release artifacts are now Developer-ID-signed and
notarized, so a swapped-in bundle passes Gatekeeper even if quarantined — and
the bundle the updater downloads is never quarantined at all, because this app
does not set ``LSFileQuarantineEnabled`` (69c pins that with a test). The safety
property now comes from the signature gate (D4): the download must be validly
signed by the *same team* as the running app, read at runtime, or nothing
happens. A locally built ad-hoc bundle has no team, so it correctly declines to
self-update and falls back to the Releases page. The swap itself is done after
process exit by a detached ``/bin/sh`` helper (D5), because a PyInstaller
onedir bundle lazy-loads from disk for its whole life and must never be
modified in place.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

RELEASES_PAGE_URL = "https://github.com/BryceWillis/softball-vision/releases/latest"
LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/BryceWillis/softball-vision/releases/latest"
)

#: ``check_for_updates = false`` under ``[defaults]`` in sidelinehd.cfg
#: (item 28's config, read from the desktop app's data dir — passed in as
#: ``cwd`` since 70f retired the chdir) suppresses the request entirely — not
#: merely the display of the result.
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


#: The macOS release asset the updater downloads. Mirrors ``ZIP_NAME`` in
#: ``.github/workflows/package-macos.yml`` — the two must stay identical (the
#: workflow uploads under this name, the updater looks it up by it), so each
#: side carries a comment naming the other. A test pins the value.
RELEASE_ASSET_NAME = "SidelineHD-Extractor-macos-arm64.zip"


def _fetch_release_payload(timeout: float) -> Optional[dict]:
    """The parsed ``releases/latest`` JSON object, or ``None`` on any failure.

    Non-200 (including a 403 rate limit), a redirect to HTML, malformed JSON, a
    non-object payload, timeout, offline — all ``None``. No retry and no backoff
    state; the next launch is the next check.
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
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def latest_release(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Optional[str]:
    """The latest release's ``tag_name``, or ``None`` on any failure at all.

    See ``_fetch_release_payload`` for the failure contract; a missing or
    non-string ``tag_name`` is one more ``None``.
    """

    payload = _fetch_release_payload(timeout)
    if payload is None:
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not tag.strip():
        return None
    return tag.strip()


@dataclass(frozen=True)
class ReleaseUpdate:
    """A newer release the check found: its tag, plus its macOS asset if uploaded.

    ``asset_url``/``asset_size`` are ``None`` when the release exists but its
    ``.zip`` asset does not yet — a tag can be published minutes before CI
    finishes uploading its artifact. That state is *not installable*: the menu
    keeps 67d's Releases-page fallback and the prompt is not shown. Tag and
    asset are always read from the *same* payload, so they cannot disagree.
    """

    tag: str
    asset_url: Optional[str]
    asset_size: Optional[int]


def parse_release_asset(payload: object) -> Tuple[Optional[str], Optional[int]]:
    """``(https download URL, size)`` for the macOS zip asset, else ``(None, None)``.

    The URL must be ``https`` or the asset is treated as absent (a plain-http
    download URL is not something this updater will fetch a bundle from). A
    missing or unparseable ``size`` keeps the URL — the download enforces its
    own hard byte cap regardless, and size is only used to render a percentage.
    """

    if not isinstance(payload, dict):
        return (None, None)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return (None, None)
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != RELEASE_ASSET_NAME:
            continue
        url = asset.get("browser_download_url")
        if not isinstance(url, str) or not url.startswith("https://"):
            return (None, None)
        size = asset.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            size = None
        return (url, size)
    return (None, None)


def update_check_enabled(cwd: Optional[Path] = None) -> bool:
    """Whether the check may run — decided before any network I/O.

    Precedence: env var (either direction) > config-file opt-out > the
    default, which is frozen-only — the check is a bundle affordance, and a
    developer mid-version should not see an offer for a release older than
    their tree (``git pull`` remains the source install's update path).

    ``cwd`` is the base ``sidelinehd.cfg`` is read from — None means the process
    CWD. The desktop passes its data dir (70f) so the opt-out keeps working now
    that the entrypoint no longer ``chdir``s into it.
    """

    env = (os.environ.get(UPDATE_CHECK_ENV_VAR) or "").strip().lower()
    if env in _FALSEY:
        return False
    if env in _TRUTHY:
        return True
    try:
        # Lazy import keeps this module import-safe headless and cheap.
        from sidelinehd_extractor.config import load_project_config_values

        value = load_project_config_values(cwd=cwd).get(UPDATE_CHECK_CONFIG_KEY, "")
    except Exception:
        value = ""
    if value.strip().lower() in _FALSEY:
        return False
    return bool(getattr(sys, "frozen", False))


def available_update(
    timeout: float = DEFAULT_TIMEOUT_SECONDS, cwd: Optional[Path] = None
) -> Optional[str]:
    """The newer release's tag (e.g. ``"v0.3.0"``), or ``None``.

    ``None`` covers every non-update outcome alike: up to date, ahead of the
    latest tag, disabled, offline, or any failure — by design there is no
    way to distinguish them, so no caller can accidentally surface an error.
    ``cwd`` is threaded to the config opt-out check (70f).
    """

    try:
        if not update_check_enabled(cwd=cwd):
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


def available_release(
    timeout: float = DEFAULT_TIMEOUT_SECONDS, cwd: Optional[Path] = None
) -> Optional[ReleaseUpdate]:
    """The newer release, tag + asset, or ``None`` — the 69c check.

    Same gate and same failure contract as ``available_update`` (which stays the
    tag-only form for 67d's callers), but returns the richer ``ReleaseUpdate``
    the self-updater needs. ``asset_url`` is ``None`` when the tag is newer but
    its asset is not yet uploaded, which the caller reads as "surface it, but
    not installable". Every non-update outcome — up to date, ahead, disabled,
    offline, any failure — is a plain ``None``, indistinguishable by design.
    """

    try:
        if not update_check_enabled(cwd=cwd):
            return None
        from sidelinehd_extractor.build_info import build_stamp

        current = parse_version_tag(f"v{build_stamp().version}")
        if current is None:
            return None
        payload = _fetch_release_payload(timeout)
        if payload is None:
            return None
        tag = payload.get("tag_name")
        if not isinstance(tag, str) or not tag.strip():
            return None
        tag = tag.strip()
        latest = parse_version_tag(tag)
        if latest is None or latest <= current:
            return None
        asset_url, asset_size = parse_release_asset(payload)
        return ReleaseUpdate(tag=tag, asset_url=asset_url, asset_size=asset_size)
    except Exception:
        return None


def update_menu_title(tag: str) -> str:
    """The menu item's label for an available-but-not-installable update (67d)."""

    return f"Update available: {tag} — Download…"


class UpdateCheck:
    """Runs ``available_update`` once, on a daemon thread, and holds the result.

    The GUI never joins the thread: it polls ``done``/``result`` from a
    main-thread timer callback (an ``NSTimer`` on the main run loop), which
    is how the background result reaches the menu without touching AppKit
    from a worker thread.
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


# --- The self-updater (item 69c) --------------------------------------------
#
# prompt → download → verify → stage → (on quit) swap → relaunch. Every write
# stays inside the data dir's ``updates/`` staging area and the ``.app``'s own
# location, and none of it happens without the user having clicked "Update
# Now". The gate (D4) is the whole safety property: a staged bundle is swapped
# in only if it is validly signed by the same team as the running app.

#: Where downloads and the parked previous bundle live, under the data dir.
UPDATES_DIRNAME = "updates"

#: A hijacked feed must not be able to fill the disk: refuse an asset that
#: streams past this many bytes, whatever its declared size (D3/69c).
MAX_ASSET_BYTES = 1024 * 1024 * 1024  # ~1 GiB

_DOWNLOAD_CHUNK = 1 << 16
_DOWNLOAD_TIMEOUT_SECONDS = 30.0

#: Absolute paths only — the no-PATH-resolution rule in 01-architecture. The
#: swap helper and the verify step invoke these by full path so a poisoned
#: PATH cannot substitute a different binary.
_DITTO = "/usr/bin/ditto"
_CODESIGN = "/usr/bin/codesign"


class UpdateError(Exception):
    """A recoverable failure in the install path — reported, never fatal.

    Raised by the download/verify/stage steps so the one caller
    (``UpdateInstaller``) can clean up the staging dir and surface the single
    post-click failure alert. It never escapes to the launcher.
    """


def enclosing_app_bundle(executable: Path) -> Optional[Path]:
    """The nearest enclosing ``*.app`` walking up from ``executable``, or ``None``.

    A frozen bundle runs from ``…/SidelineHD Extractor.app/Contents/MacOS/…``;
    the swap operates on the ``.app`` root, so the updater has to find it from
    ``sys.executable``. A source run has no ``.app`` above it → ``None``.
    """

    executable = Path(executable)
    for candidate in (executable, *executable.parents):
        if candidate.name.endswith(".app"):
            return candidate
    return None


@dataclass(frozen=True)
class Installability:
    """Whether this running app can install an update in place, and if not, why.

    ``reason`` is empty when ``installable``; ``app_path`` is the resolved
    ``.app`` root, present only when installable (it is what the swap targets).
    """

    installable: bool
    reason: str
    app_path: Optional[Path] = None


def update_installability(
    *,
    frozen: bool,
    executable: Path,
    is_writable: Callable[[Path], bool],
) -> Installability:
    """The preconditions for an in-place self-update (D5/69c), as a pure decision.

    All must hold: the app is frozen (a source run updates via ``git pull``);
    the running bundle path resolves to an enclosing ``.app``; it is not
    App-Translocated (a quarantined app run from ``~/Downloads`` executes from a
    randomized read-only mount — the remedy is the drag-to-Applications the
    README teaches, not an in-place swap); and the bundle's parent directory is
    writable (the swap moves the ``.app`` within it). Any miss → not installable
    with a plain reason, and the caller keeps 67d's Releases-page fallback.
    """

    if not frozen:
        return Installability(False, "running from source, not a packaged app")
    app_path = enclosing_app_bundle(Path(executable))
    if app_path is None:
        return Installability(False, "no enclosing .app bundle was found")
    if "/AppTranslocation/" in str(app_path):
        return Installability(
            False, "the app is running translocated; move it to Applications first"
        )
    if not is_writable(app_path.parent):
        return Installability(False, "the app's folder is not writable")
    return Installability(True, "", app_path=app_path)


def installability_now() -> Installability:
    """``update_installability`` wired to the live process (``sys`` + ``os.access``)."""

    return update_installability(
        frozen=bool(getattr(sys, "frozen", False)),
        executable=Path(sys.executable),
        is_writable=lambda path: os.access(path, os.W_OK),
    )


def _run_command(cmd: Sequence[str]) -> Tuple[int, str]:
    """Run ``cmd`` and return ``(returncode, combined stdout+stderr)``.

    ``codesign`` writes its designated-requirement dump to stderr, so both
    streams are combined for the parsers below. The seam is injected everywhere
    it is used, so no test shells out.
    """

    import subprocess

    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def download_asset(
    url: str,
    dest: Path,
    *,
    expected_size: Optional[int] = None,
    progress: Optional[Callable[[float], None]] = None,
    urlopen: Callable = urllib.request.urlopen,
    cap: int = MAX_ASSET_BYTES,
    timeout: float = _DOWNLOAD_TIMEOUT_SECONDS,
) -> Path:
    """Stream ``url`` to ``dest``, reporting progress and refusing an over-cap body.

    ``https`` only (the caller has already vetted the URL, but this is the last
    line before bytes hit the disk). ``progress`` receives a 0..1 fraction as
    bytes arrive when ``expected_size`` is known, and 1.0 on completion. The cap
    is enforced against *received* bytes, not the declared size, so a feed that
    lies about its size still cannot overrun the disk.
    """

    if not isinstance(url, str) or not url.startswith("https://"):
        raise UpdateError("refusing a non-https download URL")
    dest.parent.mkdir(parents=True, exist_ok=True)
    received = 0
    with urlopen(url, timeout=timeout) as response, open(dest, "wb") as handle:
        while True:
            chunk = response.read(_DOWNLOAD_CHUNK)
            if not chunk:
                break
            received += len(chunk)
            if received > cap:
                raise UpdateError("the download exceeded the size cap")
            handle.write(chunk)
            if progress is not None and expected_size:
                progress(min(1.0, received / expected_size))
    if progress is not None:
        progress(1.0)
    return dest


def _extract_zip(zip_path: Path, dest_dir: Path, *, run: Callable = _run_command) -> None:
    """Extract with ``ditto -x -k`` — a plain unzip drops the symlinks a bundle
    needs to launch, which is why CI packages with ``ditto`` too."""

    returncode, output = run([_DITTO, "-x", "-k", str(zip_path), str(dest_dir)])
    if returncode != 0:
        raise UpdateError(f"could not extract the update: {output.strip()}")


def _find_app_bundle(directory: Path) -> Optional[Path]:
    """The single ``*.app`` an extracted archive should contain, or ``None``."""

    if not directory.is_dir():
        return None
    for child in sorted(directory.iterdir()):
        if child.name.endswith(".app") and child.is_dir():
            return child
    return None


def codesign_verify(app_path: Path, *, run: Callable = _run_command) -> bool:
    """``codesign --verify --deep --strict`` — True iff the bundle's seal holds."""

    returncode, _ = run([_CODESIGN, "--verify", "--deep", "--strict", str(app_path)])
    return returncode == 0


_TEAM_IDENTIFIER_PATTERN = re.compile(r"^TeamIdentifier=(.+)$", re.MULTILINE)


def parse_team_identifier(text: object) -> Optional[str]:
    """The ``TeamIdentifier`` from ``codesign -d`` output, or ``None``.

    ``codesign`` prints ``TeamIdentifier=not set`` for an ad-hoc bundle; that,
    an absent line, or a non-string input all read as "no team" — which is what
    makes a locally built ad-hoc bundle decline to self-update (D4).
    """

    if not isinstance(text, str):
        return None
    match = _TEAM_IDENTIFIER_PATTERN.search(text)
    if match is None:
        return None
    team = match.group(1).strip()
    if not team or team.lower() == "not set":
        return None
    return team


def codesign_team(app_path: Path, *, run: Callable = _run_command) -> Optional[str]:
    """The signing team of ``app_path`` via ``codesign -d``, or ``None`` on any miss."""

    returncode, output = run([_CODESIGN, "-d", "--verbose=4", str(app_path)])
    if returncode != 0:
        return None
    return parse_team_identifier(output)


def read_bundle_short_version(app_path: Path) -> Optional[str]:
    """``CFBundleShortVersionString`` from a bundle's ``Info.plist``, or ``None``."""

    plist_path = Path(app_path) / "Contents" / "Info.plist"
    try:
        with open(plist_path, "rb") as handle:
            data = plistlib.load(handle)
    except Exception:
        return None
    version = data.get("CFBundleShortVersionString") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else None


def verify_staged_bundle(
    *,
    verify_ok: bool,
    staged_team: Optional[str],
    running_team: Optional[str],
    staged_version: Optional[str],
    offered_tag: str,
) -> Tuple[bool, str]:
    """The gate (D4), as a pure decision over already-collected facts.

    In order: the staged bundle's signature must verify; it must carry a team;
    the running app must carry a team to compare against (an ad-hoc dev build
    has none, so it correctly refuses to self-update); the two teams must be
    equal; and the staged bundle's version must equal the offered tag's — a
    wrong or stale asset must never be swapped in. First failure wins, with a
    plain reason. There is no bypass: this function has no "force" input.
    """

    if not verify_ok:
        return (False, "the download's signature did not verify")
    if not staged_team:
        return (False, "the download is not signed by a team")
    if not running_team:
        return (False, "this app has no signing team to match (an ad-hoc build)")
    if staged_team != running_team:
        return (False, "the download is signed by a different team")
    offered = parse_version_tag(offered_tag)
    staged = parse_version_tag(f"v{staged_version}") if staged_version else None
    if offered is None or staged is None or staged != offered:
        return (False, "the download's version does not match the offered update")
    return (True, "")


def perform_update_install(
    release: ReleaseUpdate,
    *,
    data_dir: Path,
    running_app: Path,
    progress: Optional[Callable[[float], None]] = None,
    urlopen: Callable = urllib.request.urlopen,
    run: Callable = _run_command,
    extract: Callable = _extract_zip,
    read_version: Callable[[Path], Optional[str]] = read_bundle_short_version,
    cap: int = MAX_ASSET_BYTES,
) -> Path:
    """Download, verify, and stage ``release``; return the staged ``.app`` path.

    The staging area (``data_dir/updates/``) is wiped first so a prior aborted
    attempt cannot poison this one. On any failure — bad download, extraction
    error, or a gate refusal — an ``UpdateError`` is raised with a plain reason;
    the caller cleans the staging dir. The installed bundle is never touched
    here: the swap happens later, after process exit (D5).
    """

    if release.asset_url is None:
        raise UpdateError("this release has no downloadable asset yet")
    updates_dir = Path(data_dir) / UPDATES_DIRNAME
    _reset_dir(updates_dir)
    zip_path = updates_dir / "download.zip"
    download_asset(
        release.asset_url,
        zip_path,
        expected_size=release.asset_size,
        progress=progress,
        urlopen=urlopen,
        cap=cap,
    )
    extract_dir = updates_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    extract(zip_path, extract_dir, run=run)
    staged_app = _find_app_bundle(extract_dir)
    if staged_app is None:
        raise UpdateError("the downloaded archive held no .app bundle")
    ok, reason = verify_staged_bundle(
        verify_ok=codesign_verify(staged_app, run=run),
        staged_team=codesign_team(staged_app, run=run),
        running_team=codesign_team(Path(running_app), run=run),
        staged_version=read_version(staged_app),
        offered_tag=release.tag,
    )
    if not ok:
        raise UpdateError(reason)
    return staged_app


def _reset_dir(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)


def clear_update_staging(data_dir: Path) -> None:
    """Best-effort removal of the staging dir at launch (M1: never raises).

    It holds only staged downloads and the parked previous bundle, so this is
    also the "delete the old version once the new one demonstrably launched"
    step — the new app runs it on the launch the swap produced. A locked or
    absent dir is fine; failure is silent.
    """

    shutil.rmtree(Path(data_dir) / UPDATES_DIRNAME, ignore_errors=True)


def _shell_single_quote(value: str) -> str:
    """POSIX-safe single-quoting: wrap in ``'…'`` and escape embedded quotes.

    The app name contains a space, so every path in the helper script must be
    quoted; this is the one function a quoting test must exercise.
    """

    return "'" + value.replace("'", "'\\''") + "'"


def render_swap_script(
    *,
    pid: int,
    staged_app: str,
    target_app: str,
    park_path: str,
    reopen: bool,
    wait_seconds: int = 60,
) -> str:
    """The ``/bin/sh`` helper that swaps the bundle after our process exits (D5).

    It waits (bounded — a wedged old process must not strand the helper) for our
    PID to die, moves the running ``.app`` aside to ``park_path``, moves the
    staged ``.app`` into place, and — only when ``reopen`` — reopens it. If the
    move-in fails, it restores the parked original and reopens *that* instead.
    ``stop``'s SIGTERM sets ``reopen=False``: stop means stop, and relaunching
    against it would make the CLI a liar. Every binary is an absolute path.
    """

    pid_q = _shell_single_quote(str(int(pid)))
    staged_q = _shell_single_quote(staged_app)
    target_q = _shell_single_quote(target_app)
    park_q = _shell_single_quote(park_path)
    # Always a real statement so neither branch's body is ever empty — an
    # empty `then` is a POSIX `sh` syntax error, which would abort the whole
    # helper before any `mv`. `reopen=False` (stop's SIGTERM) becomes a no-op.
    reopen_stmt = f"/usr/bin/open {target_q}\n" if reopen else ":\n"
    return (
        "#!/bin/sh\n"
        f"pid={pid_q}\n"
        "waited=0\n"
        'while /bin/kill -0 "$pid" 2>/dev/null; do\n'
        f"  if [ \"$waited\" -ge {int(wait_seconds)} ]; then exit 0; fi\n"
        "  waited=$((waited + 1))\n"
        "  /bin/sleep 1\n"
        "done\n"
        f"if /bin/mv {target_q} {park_q}; then\n"
        f"  if /bin/mv {staged_q} {target_q}; then\n"
        f"    {reopen_stmt}"
        "  else\n"
        f"    /bin/mv {park_q} {target_q}\n"
        f"    {reopen_stmt}"
        "  fi\n"
        "fi\n"
    )


def spawn_swap_helper(
    script: str, *, popen: Optional[Callable] = None
) -> None:
    """Launch the swap helper detached, so it outlives this process (D5).

    ``start_new_session=True`` and discarded stdio put it in its own session,
    surviving our exit to do the swap. Thin render code around
    ``render_swap_script``; the ``popen`` seam keeps it testable without
    actually spawning a shell.
    """

    import subprocess

    launcher = popen or subprocess.Popen
    launcher(
        ["/bin/sh", "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


class UpdateInstaller:
    """Downloads, verifies, and stages an update on a daemon thread (69c).

    Mirrors ``UpdateCheck``'s model: the GUI never joins the thread — it polls
    ``phase``/``progress`` from a main-thread timer and reads ``staged_app_path``
    once staged. This object only ever touches the filesystem and subprocess;
    every AppKit call stays on the main thread in ``desktop.py``. On failure it
    cleans the staging dir and lands in ``PHASE_FAILED`` so the launcher can
    surface the one post-click failure alert.
    """

    PHASE_IDLE = "idle"
    PHASE_DOWNLOADING = "downloading"
    PHASE_STAGED = "staged"
    PHASE_FAILED = "failed"

    def __init__(
        self, *, install: Callable[..., Path] = perform_update_install
    ) -> None:
        self._install = install
        self._phase = self.PHASE_IDLE
        self._progress: Optional[float] = None
        self._staged_app: Optional[Path] = None
        self._error: Optional[str] = None

    def start(self, release: ReleaseUpdate, *, data_dir: Path, running_app: Path) -> None:
        """Begin an install. A no-op while one is already downloading — the menu
        is display-only then, but this guards a double click from both menus."""

        if self._phase == self.PHASE_DOWNLOADING:
            return
        self._phase = self.PHASE_DOWNLOADING
        self._progress = None
        self._staged_app = None
        self._error = None
        threading.Thread(
            target=self._run,
            args=(release,),
            kwargs={"data_dir": data_dir, "running_app": running_app},
            name="sidelinehd-update-install",
            daemon=True,
        ).start()

    def _set_progress(self, fraction: float) -> None:
        self._progress = fraction

    def _run(self, release: ReleaseUpdate, *, data_dir: Path, running_app: Path) -> None:
        try:
            staged = self._install(
                release,
                data_dir=data_dir,
                running_app=running_app,
                progress=self._set_progress,
            )
            self._staged_app = staged
            self._phase = self.PHASE_STAGED
        except Exception as error:
            self._error = str(error)
            try:
                clear_update_staging(data_dir)
            except Exception:
                pass
            # Flip the phase last, so anything observing PHASE_FAILED (the
            # main-thread poll timer) is guaranteed the staging dir is already
            # cleaned and no partial download lingers.
            self._phase = self.PHASE_FAILED

    def reset(self) -> None:
        """Return to idle after a failure has been surfaced, so a retry can run."""

        self._phase = self.PHASE_IDLE
        self._progress = None
        self._staged_app = None
        self._error = None

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def progress(self) -> Optional[float]:
        return self._progress

    @property
    def staged_app_path(self) -> Optional[Path]:
        return self._staged_app if self._phase == self.PHASE_STAGED else None

    @property
    def error(self) -> Optional[str]:
        return self._error
