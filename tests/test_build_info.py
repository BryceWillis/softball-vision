"""Tests for the build stamp (item 67a).

The frozen paths monkeypatch ``sys.frozen`` / ``sys._MEIPASS`` — no bundle
and no GUI needed. The load-bearing property throughout: ``build_stamp()``
must never raise, whatever state the provenance file is in.
"""

from __future__ import annotations

import json
import sys

import pytest

from sidelinehd_extractor import build_info
from sidelinehd_extractor.build_info import BuildStamp, build_stamp, stamp_label
from sidelinehd_extractor.webapp import lifecycle


def _freeze(monkeypatch, meipass) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)


def _write_build_info(tmp_path, payload) -> None:
    (tmp_path / build_info.BUILD_INFO_FILENAME).write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )


def _stub_source_lookup(monkeypatch, version="0.source", sha=None) -> None:
    monkeypatch.setattr(lifecycle, "package_version", lambda: version)
    monkeypatch.setattr(lifecycle, "git_short_sha", lambda cwd=None: sha)


def test_frozen_bundle_reads_baked_stamp(tmp_path, monkeypatch):
    _freeze(monkeypatch, tmp_path)
    _write_build_info(
        tmp_path, {"version": "0.2.0", "sha": "a1b2c3d", "built_at": "2026-07-20T18:04:05Z"}
    )

    stamp = build_stamp()

    assert stamp == BuildStamp(
        version="0.2.0", sha="a1b2c3d", built_at="2026-07-20T18:04:05Z", origin="bundle"
    )


def test_frozen_bundle_without_git_sha_still_stamps(tmp_path, monkeypatch):
    """A source-tarball build bakes ``sha: null``; the stamp keeps the date."""

    _freeze(monkeypatch, tmp_path)
    _write_build_info(tmp_path, {"version": "0.2.0", "sha": None, "built_at": "2026-07-20T18:04:05Z"})

    stamp = build_stamp()

    assert stamp.origin == "bundle"
    assert stamp.sha is None
    assert stamp.built_at == "2026-07-20T18:04:05Z"


def test_frozen_bundle_missing_file_degrades_to_source(tmp_path, monkeypatch):
    _freeze(monkeypatch, tmp_path)
    _stub_source_lookup(monkeypatch, version="0.2.0", sha=None)

    stamp = build_stamp()

    assert stamp == BuildStamp(version="0.2.0", sha=None, built_at=None, origin="source")


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        "[]",
        '"just a string"',
        {"sha": "a1b2c3d"},  # version missing
        {"version": ""},  # version empty
        {"version": 2},  # version wrong type
        {"version": "0.2.0", "sha": 123},  # sha wrong type
        {"version": "0.2.0", "built_at": {"date": "2026-07-20"}},  # built_at wrong type
    ],
)
def test_frozen_bundle_malformed_file_degrades_to_source(tmp_path, monkeypatch, payload):
    """A corrupt provenance file must never stop the launcher — nor raise."""

    _freeze(monkeypatch, tmp_path)
    _write_build_info(tmp_path, payload)
    _stub_source_lookup(monkeypatch)

    stamp = build_stamp()

    assert stamp.origin == "source"
    assert stamp.version == "0.source"


def test_frozen_bundle_with_unreadable_meipass_degrades_to_source(tmp_path, monkeypatch):
    _freeze(monkeypatch, tmp_path / "does-not-exist")
    _stub_source_lookup(monkeypatch)

    assert build_stamp().origin == "source"


def test_source_run_uses_package_version_and_git(monkeypatch, tmp_path):
    """Not frozen → origin is 'source' even if a build_info.json is lying around."""

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    _write_build_info(tmp_path, {"version": "9.9.9", "sha": "baked00"})
    _stub_source_lookup(monkeypatch, version="0.2.0", sha="f00d123")

    stamp = build_stamp()

    assert stamp == BuildStamp(version="0.2.0", sha="f00d123", built_at=None, origin="source")


def test_stamp_label_full():
    stamp = BuildStamp(
        version="0.2.0", sha="a1b2c3d", built_at="2026-07-20T18:04:05Z", origin="bundle"
    )
    assert stamp_label(stamp) == "v0.2.0 (a1b2c3d) · built 2026-07-20"


def test_stamp_label_drops_absent_segments():
    no_sha = BuildStamp(version="0.2.0", sha=None, built_at="2026-07-20T18:04:05Z", origin="bundle")
    assert stamp_label(no_sha) == "v0.2.0 · built 2026-07-20"

    bare = BuildStamp(version="0.2.0", sha=None, built_at=None, origin="source")
    assert stamp_label(bare) == "v0.2.0"


def test_stamp_label_renders_unparseable_built_at_raw():
    stamp = BuildStamp(version="0.2.0", sha=None, built_at="sometime in july", origin="bundle")
    assert stamp_label(stamp) == "v0.2.0 · built sometime in july"
