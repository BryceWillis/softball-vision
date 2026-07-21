# PyInstaller spec for the macOS .app bundle (item 54d).
# Build per packaging/build-macos.md:
#   pyinstaller packaging/sidelinehd.spec
# -*- mode: python ; coding: utf-8 -*-

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from importlib import metadata

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

APP_NAME = "SidelineHD Extractor"
# The single version source: pyproject.toml, via the installed package. The
# plist below and the baked build_info.json both read it — never hardcode.
APP_VERSION = metadata.version("sidelinehd-extractor")


def _git_short_sha():
    # A source-tarball build has no git; the stamp then drops the SHA segment.
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=SPECPATH,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


# Item 67a: bake build provenance into the bundle so a frozen app — which has
# no git checkout — can still say when it was built (read back by
# sidelinehd_extractor/build_info.py, shown in the menubar and web footer).
_build_info_dir = tempfile.mkdtemp(prefix="sidelinehd-build-info-")
_build_info_path = os.path.join(_build_info_dir, "build_info.json")
with open(_build_info_path, "w", encoding="utf-8") as _fh:
    json.dump(
        {
            "version": APP_VERSION,
            "sha": _git_short_sha(),
            "built_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        },
        _fh,
    )

# Package data: webapp templates/ + static/, and data/ overlay templates.
datas = collect_data_files("sidelinehd_extractor")
# imageio-ffmpeg ships its ffmpeg binary as package data (item 54a's
# no-brew ffmpeg path); collect it so downloads work inside the bundle.
datas += collect_data_files("imageio_ffmpeg")
# Language data for the embedded libtesseract (the tesserocr wheel has the
# library but no traineddata). Downloaded by the build doc's step 2.
datas += [(os.path.join(SPECPATH, "tessdata", "eng.traineddata"), "tessdata")]
# Build provenance at the bundle root (sys._MEIPASS/build_info.json).
datas += [(_build_info_path, ".")]

# The tesserocr wheel embeds libtesseract + libleptonica as bundled dylibs.
binaries = collect_dynamic_libs("tesserocr")

# Item 68a: the app icon is committed artwork (see packaging/icon/), so the
# build needs no generation step. Fail fast if it is missing — a build must
# never silently produce a blank-Dock-tile bundle.
ICON_PATH = os.path.join(SPECPATH, "icon", "sidelinehd.icns")
if not os.path.isfile(ICON_PATH):
    raise SystemExit(
        f"App icon missing: {ICON_PATH}\n"
        "packaging/icon/sidelinehd.icns is committed artwork; restore it or "
        "regenerate it per packaging/build-macos.md (make-icns.sh)."
    )

a = Analysis(
    [os.path.join(SPECPATH, "sidelinehd_desktop.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # uvicorn resolves these at runtime via its "auto" strings, which
        # static analysis misses.
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        # Bundle-CR (2026-07-20): the v0.4.0 bundle shipped unable to import
        # tesserocr, so the app silently fell back to a Tesseract CLI the GUI
        # PATH does not have. Root cause (confirmed with a local debug
        # build): tesserocr's compiled Cython extension imports cysignals at
        # init — an import that lives in compiled code, which PyInstaller's
        # bytecode scan cannot see — so cysignals was never collected and
        # `import tesserocr` died with ImportError inside the bundle.
        # cysignals is the load-bearing entry; tesserocr/PIL.Image/yt_dlp are
        # declared so none of them ever depends on an import buried in
        # application code. The scrubbed-PATH selftest asserts all of this.
        "cysignals",
        "tesserocr",
        "PIL.Image",
        "yt_dlp",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="sidelinehd-extractor",
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=ICON_PATH,
    bundle_identifier="dev.sidelinehd.extractor",
    info_plist={
        # Menubar-only: no Dock icon, no app switcher entry.
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": APP_VERSION,
    },
)
