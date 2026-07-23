"""Guard tests for the hardened-runtime entitlements (M6 slice 69a).

Notarization requires the hardened runtime, and the entitlements file is
the list of its defaults this bundle opts out of — each entry is a security
posture decision. These tests pin the file to exactly the documented set,
so a new entitlement must arrive as a deliberate diff line here as well as
in the plist, and they pin the workflow to actually using the file — a
signing step that silently dropped ``--entitlements`` would build a bundle
the hardened runtime kills on the first ctypes call, which only CI's
selftest (or a coach) would otherwise notice. Text-level guards in the
``test_packaging_icon.py`` style: no codesign, no network.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENTITLEMENTS = REPO / "packaging" / "entitlements.plist"
WORKFLOW = REPO / ".github" / "workflows" / "package-macos.yml"

# The documented set (packaging/entitlements.plist explains each entry):
# unsigned-executable-memory for ctypes/cffi/cysignals, and
# disable-library-validation for the tesserocr wheel's bundled dylibs.
DOCUMENTED_ENTITLEMENTS = {
    "com.apple.security.cs.allow-unsigned-executable-memory": True,
    "com.apple.security.cs.disable-library-validation": True,
}


def test_entitlements_file_parses_to_exactly_the_documented_set() -> None:
    # Exact equality, not subset: an entitlement appearing here without a
    # matching edit to this test is the diff line a reviewer must see.
    with ENTITLEMENTS.open("rb") as fh:
        parsed = plistlib.load(fh)
    assert parsed == DOCUMENTED_ENTITLEMENTS


def test_workflow_signs_with_the_entitlements_file() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--entitlements packaging/entitlements.plist" in text


def test_workflow_signs_with_the_hardened_runtime() -> None:
    # --options runtime is what notarization requires; a signing step
    # without it would notarize-fail long after the cheap checks passed.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--options runtime --timestamp" in text


def test_workflow_asset_name_matches_the_updater_constant() -> None:
    # M6 slice 69c: the self-updater downloads the release asset by exact name.
    # CI uploads it under ZIP_NAME; updates.RELEASE_ASSET_NAME looks it up. If
    # the two drift, the updater silently finds no asset and every release reads
    # as "not installable" — so pin the recipe-pairing here.
    from sidelinehd_extractor.updates import RELEASE_ASSET_NAME

    text = WORKFLOW.read_text(encoding="utf-8")
    assert f"ZIP_NAME: {RELEASE_ASSET_NAME}" in text
