# Building the macOS app (item 54d)

Produces a double-clickable `SidelineHD Extractor.app` that bundles Python,
all dependencies, ffmpeg (via imageio-ffmpeg), and Tesseract OCR (via the
self-contained `tesserocr` wheel + `eng.traineddata`). No terminal, no pip,
no brew for the end user. Windows packaging is out of scope (item 19).

**This document and `.github/workflows/package-macos.yml` are one recipe**
(item 67b): the workflow runs these same steps in this same order on every
`v*` tag, on pushes touching `packaging/**`, and on manual dispatch.
Whenever one changes, change the other in the same commit — the
`packaging/**` trigger exists to make drift fail loudly.

## 1. Build environment

Use a clean virtualenv on the Mac architecture you're shipping for (the
bundle is single-arch; build on Apple Silicon for arm64):

```sh
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install -e ".[web,ocr,desktop]" pyinstaller
```

`tesserocr` (from the `ocr` extra) must install from a wheel, not a source
build, so the bundle doesn't depend on a brew-installed libtesseract.
**Check before building** — a source build produces a bundle that builds
clean and dies on the first OCR call:

```sh
pip show -f tesserocr | grep '\.dylibs/'   # must match; abort if it doesn't
```

CI pins Python 3.13 for this reason (tesserocr ships macOS arm64 wheels
for it); locally, any version with an arm64 wheel works.

## 2. Language data

The tesserocr wheel embeds libtesseract but no language data. Download
`eng.traineddata` (the "fast" variant is fine and small) next to the spec:

```sh
mkdir -p packaging/tessdata
curl -fL --retry 3 -o packaging/tessdata/eng.traineddata \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata
```

`packaging/tessdata/` is gitignored — the file is ~4 MB of upstream data,
fetched per build. `-f` makes an HTTP error fail the download instead of
saving an error page; CI additionally rejects a file under 1 MB so a
truncated traineddata can never reach a bundle.

## 3. Build

```sh
pyinstaller --noconfirm packaging/sidelinehd.spec
```

The app lands at `dist/SidelineHD Extractor.app`.

The spec bakes a `build_info.json` (package version, git short SHA, build
date) into the bundle — item 67a's build stamp, shown in the app menu and
the web footer so a stale bundle is self-evident. It also sets the bundle's
`CFBundleShortVersionString` from the installed package version; the version
macOS reports (Get Info) should match `pyproject.toml`. Building from a
source tarball with no git is fine — the stamp just drops the SHA segment.

## 4. Signing — local builds are ad-hoc; CI does the real signing

Local and dev builds are **ad-hoc signed**, deliberately. Unsigned apps are
blocked outright on Apple Silicon; ad-hoc signing makes the app runnable,
though Gatekeeper still requires right-click → Open the first time on a
machine that downloaded it:

```sh
codesign --force --deep -s - "dist/SidelineHD Extractor.app"
codesign --verify "dist/SidelineHD Extractor.app"
```

Real Developer ID signing, notarization, and stapling landed in CI (M6
slice 69a) — `.github/workflows/package-macos.yml` carries the steps:

- **Branch builds** (signing secrets present) sign with the Developer ID
  Application identity, the hardened runtime (`--options runtime
  --timestamp`), and the committed `packaging/entitlements.plist` —
  inside-out, nested Mach-Os first, then the bundle. Notarization is
  skipped on branches so Apple's service is not a dependency of every
  packaging push.
- **Tag builds** additionally submit the zip to Apple's notary service
  (`notarytool submit --wait`), staple the ticket onto the app, **rebuild
  the zip** (stapling mutates the bundle — the pre-staple zip must never
  ship), then hard-assert `stapler validate` and `spctl --assess --type
  execute`. A tag build missing any signing secret **fails loudly** rather
  than shipping ad-hoc; if the notary service is down, the job fails —
  re-run it. A tag never ships unnotarized.
- **Forks** (no secrets) run the ad-hoc line above and stay green.

`packaging/entitlements.plist` is the hardened runtime's exception list —
unsigned executable memory (ctypes/cffi/cysignals) and library validation
off (the tesserocr wheel's bundled dylibs). Each entry is a security
posture decision: `tests/test_packaging_entitlements.py` pins the file to
exactly that set, and the scrubbed-PATH selftest (step 5) runs against the
*signed* bundle in CI, so an entitlement gap fails there rather than on a
coach's machine.

Secrets, by name (values live only in GitHub Actions): `APPLE_TEAM_ID`,
`MACOS_CERT_P12` (base64 `.p12`), `MACOS_CERT_PASSWORD`,
`MACOS_KEYCHAIN_PASSWORD`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_API_KEY_P8`
(base64 `.p8`).

## 5. Smoke-test the built bundle with a scrubbed PATH

```sh
SIDELINEHD_CHECK_FOR_UPDATES=0 \
  env PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
  "dist/SidelineHD Extractor.app/Contents/MacOS/SidelineHD Extractor" --selftest
```

`--selftest` (item 67b) runs the full startup path minus the GUI — data
dir, dependency self-containment, port pick, server thread, one `GET /`
that must return 200 — and exits non-zero on any failure. It asserts every
dependency resolves *inside the bundle*: `missing_dependencies()` empty,
and OCR backed by the bundled tesserocr engine rather than a Tesseract CLI.

**The scrubbed `PATH` is not optional.** It reproduces the bare launchd
environment a double-clicked `.app` actually gets — no `/opt/homebrew/bin`.
Every pre-v0.4.0 verification ran from a terminal whose PATH silently
supplied tesseract and yt-dlp, which is exactly how a bundle that could
neither OCR nor download passed its checks (bundle CR, 2026-07-20).

The env var is item 67d's update-check override: `--selftest` never starts
the check, but the suppression is explicit so a selftest run provably never
touches the network (CI sets the same variable). It runs the *built
binary*, not the source tree, so it catches bundle-only breakage (missing
data files, a source-built tesserocr, a module PyInstaller failed to
collect). CI has no login GUI, so this is also the only launch test a
runner can do. Note it uses the real data dir
(`~/Library/Application Support/SidelineHD Extractor/`) deliberately —
exercising `prepare_data_dir()` is part of the point.

## 6. Package for distribution

```sh
ditto -c -k --keepParent "dist/SidelineHD Extractor.app" \
  "dist/SidelineHD-Extractor-macos-arm64.zip"
```

**`ditto`, not `zip`** — `zip` drops the symlinks and extended attributes
that make a bundle launchable, which surfaces to the recipient as the
"app won't open (damaged)" failure below. The artifact name says arm64
because the bundle is single-arch.

## 7. Verify on a clean account

1. Copy the `.app` to a user account (or machine) with no brew/python setup.
2. Double-click (first time on an ad-hoc local build: right-click → Open;
   a notarized release download opens with the ordinary one-question
   confirm). The app's icon (the
   item 68a artwork) appears in the Dock and in ⌘Tab — and **no** "SHD" item
   appears in the menu bar — and **the app's own window opens** on the home
   page, titled *SidelineHD Extractor*. **No browser tab opens** (item 70b
   retired the launch-time browser open). The app menu and the web footer
   both show the build stamp, e.g. `v0.2.0 (a1b2c3d) · built 2026-07-20` —
   check the date is today's.
3. Press ⌘W, then click the Dock icon: the same window comes back, and the
   server never stopped. Right-click the Dock icon: **Open SidelineHD
   Extractor**, **Open in Browser**, a non-clickable *Running on …* line, and
   **Quit**. *Open in Browser* opens the same page in the default browser.
   - **Select some text in the window and press ⌘C, then paste it
     elsewhere.** This is what the Edit menu exists for — in AppKit the ⌘C
     key equivalent comes from that menu, and this product's entire output is
     copy-paste kits. Check both **Copy** buttons on a finished game too: if
     one falls back to "Select the text and copy manually", manual copy must
     actually work.
   - **Click a review row's timestamp link.** It must open YouTube in the
     **default browser**, not inside the app's window. Same for the feedback
     page's GitHub hand-off.
   - Resize and move the window, quit, and relaunch: the size and position
     come back.
4. Data lives in `~/Library/Application Support/SidelineHD Extractor/`
   (`runs/`, `videos/`, `rosters/`, `sidelinehd.cfg`).
5. Run a short game video end-to-end: OCR must work with no Tesseract
   installed (embedded tesserocr + bundled `eng.traineddata`).
   - **While it reads, look at the Dock icon** (item 70c): the tile carries a
     percentage badge that climbs, and it clears when the game finishes.
     Close the window first — the badge is what makes a 40-minute read
     visible with no window open, which is the whole point of it.
   - **Press ⌘Q while it is still reading.** A plain-language confirmation
     appears naming the consequence; **Cancel** leaves the read running
     untouched; **Quit** stops within `controller.stop()`'s 10-second bound.
   - **Then `sidelinehd-extractor stop` during a read** (item 70c / D5): it
     must **not** put a dialog on screen. The app stops gracefully inside the
     CLI's 12-second wait and `stop` prints `Stopped (PID …)`, not the
     force-stopped message.
6. Quit — Dock right-click → **Quit**, or ⌘Q — stops the server and exits:
   the port is freed (`lsof -i` on the port the app's menus showed — the real
   port floats off `:8000` if another app holds it) and no process survives.
7. **Second launch (item 70d):** with the app already running, open a second
   copy of the `.app`. It must **not** start a rival server: a one-button
   notice says what is already running and since when, opens that server in the
   default browser, and the second instance exits — no new Dock entry, and
   `sidelinehd-extractor status` still names exactly one server. Do the same
   with a CLI server up first (`sidelinehd-extractor start`, then launch the
   `.app`): same hand-off, and the CLI server keeps running untouched.
8. **Self-update (item 69c).** This needs *two* Developer-ID-signed builds with
   different versions — a `workflow_dispatch` run of `package-macos.yml` on two
   commits (bump `version` in `pyproject.toml`) gives you a signed-but-not-yet
   notarized pair, which is exactly what the runtime gate is designed to accept.
   Install the **older** one into `/Applications`, publish the newer one as the
   `releases/latest` asset (or point the check at it), and launch the old app:
   - The **Update Now / Not Now** prompt appears once. **Update Now** →
     progress shows in the menu → the app quits and **reopens by itself** as the
     new version. Confirm: the app menu + web footer show the new stamp,
     `sidelinehd-extractor status` names the new server, exactly one record
     exists, and `~/Library/Application Support/SidelineHD Extractor/updates/`
     is empty after the relaunch settles.
   - **Substitute a corrupted zip** for the release asset: the failure alert
     appears (*"The update didn't work. Nothing has been changed …"*), the app
     keeps running, the installed bundle is byte-for-byte untouched, and the
     staging dir is cleaned.
   - **Substitute a bundle re-signed with a *different* identity**: the team
     gate must **refuse** it — same clean, nothing-changed outcome. This is the
     security check; it must be *seen* to refuse, not assumed to.
   - **Update Now while a read is in flight**: no restart. The menu shows
     **Restart to finish updating**; the read runs to completion untouched, and
     quitting afterward performs the swap.
   - **`sidelinehd-extractor stop` with an update staged**: the app stops, `stop`
     prints the graceful message, the swap happens, and **nothing reopens** —
     the next manual launch is the new version.
   - A **source run** (`python -m sidelinehd_extractor.desktop`, with
     `SIDELINEHD_CHECK_FOR_UPDATES=1`): the menu shows the Releases-page
     fallback, never the installer — a source tree updates with `git pull`.

## App icon

The artwork lives in `packaging/icon/` (item 68a). Both the source
`icon-1024.png` and the rendered `sidelinehd.icns` are **committed**, so
neither this recipe nor `.github/workflows/package-macos.yml` has an icon
step — the spec consumes the checked-in `.icns` directly, and fails fast
if it is missing (like a missing traineddata).

The shipped icon (item 71) is a photographic softball dissolving into pixels
on the app's deep-navy ground. Its **master** is
`softball-vision-dock-icon.png` (also committed); `icon-1024.png` is a
**derived** file — `make_dock_icon.py` conditions the master into the shape
`make-icns.sh` expects: it masks the full-bleed squircle to real transparency
(the master's corners are opaque white, which macOS would otherwise composite
as four pale wedges), scales the tile to Apple's 824-of-1024 grid, and insets
it on a transparent canvas.

To swap the artwork:

- **Real artwork** — replace `softball-vision-dock-icon.png`, run
  `python packaging/icon/make_dock_icon.py` (regenerates `icon-1024.png`),
  then `sh packaging/icon/make-icns.sh`, rebuild.
- **Back to the placeholder** — the "SHD" monogram is reproducible via
  `python packaging/icon/generate_icon.py`, which writes `icon-1024.png`
  directly; then `sh packaging/icon/make-icns.sh`, rebuild.

No code changes either way. Fine detail (the red stitching, the small
dissolving squares) washes out at the 16px menu-bar/Finder-list size, leaving
a recognizable yellow-ball-on-navy — acceptable; `make-icns.sh` renders every
size from the one 1024 source, so a distinct simplified small icon would be a
pipeline change, not an artwork swap. Icon rules: no player names, no
photographs of people, no SidelineHD-owned artwork — confirm any new master is
yours to redistribute under the repo's MIT license before committing it.

## Troubleshooting

- **"tesserocr failed to load"** — the venv installed tesserocr from
  source against a brew libtesseract. Recreate the venv and install with
  `pip install --only-binary tesserocr tesserocr`.
- **OCR errors mentioning tessdata** — step 2 was skipped; the spec fails
  fast if `packaging/tessdata/eng.traineddata` is missing.
- **App won't open ("damaged")** — for a **release download** (v0.6.0 and
  later are notarized), Gatekeeper distrust is not the cause: the zip was
  repacked with `zip` instead of `ditto`, or mangled in transit (mailed
  `.app`, step 6's warning). Re-download the original zip. For a **local
  ad-hoc build**, the signing step was skipped or the bundle was
  transferred without preserving symlinks; re-sign per step 4.
- **Rebuilt app still shows the old (or generic) icon** — Finder and the
  Dock cache icons aggressively, so after replacing an existing `.app` the
  old artwork can persist and look like a failed build. Move or rename the
  copy, or restart the Dock (`killall Dock`), before concluding the icon
  didn't take.
