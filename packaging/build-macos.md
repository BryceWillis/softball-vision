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
date) into the bundle — item 67a's build stamp, shown in the menubar and
the web footer so a stale bundle is self-evident. It also sets the bundle's
`CFBundleShortVersionString` from the installed package version; the version
macOS reports (Get Info) should match `pyproject.toml`. Building from a
source tarball with no git is fine — the stamp just drops the SHA segment.

## 4. Ad-hoc signing (local distribution)

Unsigned apps are blocked outright on Apple Silicon; ad-hoc signing makes
the app runnable, though Gatekeeper still requires right-click → Open the
first time on a machine that downloaded it:

```sh
codesign --force --deep -s - "dist/SidelineHD Extractor.app"
codesign --verify "dist/SidelineHD Extractor.app"
```

Real Developer ID signing + notarization is deferred until distribution
matters — revisit when the recipient count passes about three, or on the
first recipient who cannot get past Gatekeeper unaided (see the roadmap's
M1 distribution decision).

## 5. Smoke-test the built bundle

```sh
"dist/SidelineHD Extractor.app/Contents/MacOS/SidelineHD Extractor" --selftest
```

`--selftest` (item 67b) runs the full startup path minus the menubar — data
dir, port pick, server thread, one `GET /` that must return 200 — and exits
non-zero on any failure. It runs the *built binary*, not the source tree,
so it catches bundle-only breakage (missing data files, a source-built
tesserocr). CI has no login GUI, so this is also the only launch test a
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
2. Double-click (first time: right-click → Open). The **SHD** menubar item
   appears and the browser opens `http://127.0.0.1:8000`.
   The menubar and the web footer both show the build stamp, e.g.
   `v0.2.0 (a1b2c3d) · built 2026-07-20` — check the date is today's.
3. Data lives in `~/Library/Application Support/SidelineHD Extractor/`
   (`runs/`, `videos/`, `rosters/`, `sidelinehd.cfg`).
4. Run a short game video end-to-end: OCR must work with no Tesseract
   installed (embedded tesserocr + bundled `eng.traineddata`).
5. Menubar → Quit stops the server and exits.

## Troubleshooting

- **"tesserocr failed to load"** — the venv installed tesserocr from
  source against a brew libtesseract. Recreate the venv and install with
  `pip install --only-binary tesserocr tesserocr`.
- **OCR errors mentioning tessdata** — step 2 was skipped; the spec fails
  fast if `packaging/tessdata/eng.traineddata` is missing.
- **App won't open ("damaged")** — signing step skipped, or the zip was
  transferred without preserving the bundle; re-sign per step 4.
