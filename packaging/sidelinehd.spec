# PyInstaller spec for the macOS .app bundle (item 54d).
# Build per packaging/build-macos.md:
#   pyinstaller packaging/sidelinehd.spec
# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

APP_NAME = "SidelineHD Extractor"

# Package data: webapp templates/ + static/, and data/ overlay templates.
datas = collect_data_files("sidelinehd_extractor")
# imageio-ffmpeg ships its ffmpeg binary as package data (item 54a's
# no-brew ffmpeg path); collect it so downloads work inside the bundle.
datas += collect_data_files("imageio_ffmpeg")
# Language data for the embedded libtesseract (the tesserocr wheel has the
# library but no traineddata). Downloaded by the build doc's step 2.
datas += [(os.path.join(SPECPATH, "tessdata", "eng.traineddata"), "tessdata")]

# The tesserocr wheel embeds libtesseract + libleptonica as bundled dylibs.
binaries = collect_dynamic_libs("tesserocr")

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
    icon=None,
    bundle_identifier="dev.sidelinehd.extractor",
    info_plist={
        # Menubar-only: no Dock icon, no app switcher entry.
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "CFBundleShortVersionString": "0.1.0",
    },
)
