# Building the macOS app (item 54d)

Produces a double-clickable `SidelineHD Extractor.app` that bundles Python,
all dependencies, ffmpeg (via imageio-ffmpeg), and Tesseract OCR (via the
self-contained `tesserocr` wheel + `eng.traineddata`). No terminal, no pip,
no brew for the end user. Windows packaging is out of scope (item 19).

## 1. Build environment

Use a clean virtualenv on the Mac architecture you're shipping for (the
bundle is single-arch; build on Apple Silicon for arm64):

```sh
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install -e ".[web,ocr,desktop]" pyinstaller
```

`tesserocr` (from the `ocr` extra) must install from a wheel, not a source
build, so the bundle doesn't depend on a brew-installed libtesseract:
`pip show -f tesserocr` should list bundled `.dylibs/`.

## 2. Language data

The tesserocr wheel embeds libtesseract but no language data. Download
`eng.traineddata` (the "fast" variant is fine and small) next to the spec:

```sh
mkdir -p packaging/tessdata
curl -L -o packaging/tessdata/eng.traineddata \
  https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata
```

`packaging/tessdata/` is gitignored — the file is ~4 MB of upstream data,
fetched per build.

## 3. Build

```sh
pyinstaller --noconfirm packaging/sidelinehd.spec
```

The app lands at `dist/SidelineHD Extractor.app`.

## 4. Ad-hoc signing (local distribution)

Unsigned apps are blocked outright on Apple Silicon; ad-hoc signing makes
the app runnable, though Gatekeeper still requires right-click → Open the
first time on a machine that downloaded it:

```sh
codesign --force --deep -s - "dist/SidelineHD Extractor.app"
```

Real Developer ID signing + notarization is deferred until distribution
matters (explicitly out of scope for 54d).

## 5. Verify on a clean account

1. Copy the `.app` to a user account (or machine) with no brew/python setup.
2. Double-click (first time: right-click → Open). The **SHD** menubar item
   appears and the browser opens `http://127.0.0.1:8000`.
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
