# Code Review

**Reviewer:** Claude (Senior Software Architect)
**Last updated:** 2026-06-30
**Review passes:** 6 (Pass 6: CR-24/25, items 31/33, OCR improvements, tiered spacing)

This document is the running record of architectural observations, bugs, and improvement recommendations for the `sidelinehd-extractor` codebase. It is updated after each review pass. Items move to **Resolved** once confirmed fixed.

## Status Workflow

- **Open**: reviewed finding is accepted as work to do.
- **Ready for Review**: Codex has implemented the change and verified tests; awaiting reviewer/user confirmation.
- **Resolved**: reviewer/user has confirmed the implementation and moved the item to the Resolved section.
- **Deferred**: valid finding, but intentionally postponed.

Codex may update an Open item to **Ready for Review** after implementing it and should include a short implementation note. The reviewer/user owns moving items from Open to Resolved after reviewing the diff and behavior.

---

## Open Items

_No open items._

## Resolved Items

#### CR-25 — Review report lacks flags for unrostered card numbers and garbled card names
**File:** [review.py](src/sidelinehd_extractor/review.py)
**Resolved:** Pass 6

All three flags implemented: `unrostered-card-number=N` (batter-card source, number not in roster), `garbled-card-name` (batter_card_name with no 3+-char token and no name match), `lineup-had-rostered-candidate=M` (lineup side of batter_number_disagreement contains or is a rostered number). `batter_card_name` stored in AT_BAT_START metadata. Roster threaded through `review-events` and `review-report` CLI commands via new `--roster` flags. Note: `_lineup_has_rostered_candidate()` checks 1- and 2-digit substrings, so teams with single-digit jersey numbers may see this flag more often; accepted as the correct conservative behavior for a review signal. 153 tests pass.

#### CR-24 — `_is_plausible_batter_source` does not reject unrostered batter-card events
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 6

Implemented using the broader `_has_roster_match_for_state()` helper rather than the narrower `player_name is not None` check from the design. The broader check is correct: a lineup-confirmed rostered number should also satisfy the guard even when the batter card name was not resolved. Two new tests cover unrostered card with empty name and unrostered card with non-matching OCR name. 153 tests pass.

#### CR-23 — `infer_batting_half` zeroed at-bat totals in `roster is None` early return
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 5 re-review

Loop now always counts at-bat totals; match step guarded with `if roster is not None`. The `roster is None` branch checks after the loop and returns real top/bottom at-bat counts with zeroed match counts. Regression test updated to assert `top_at_bats == 1`. 133 tests pass.

#### CR-22 — TTY confirmation prompt showed relative output path
**File:** [cli.py](src/sidelinehd_extractor/cli.py)
**Resolved:** Pass 5 re-review

`display_output_path = output_path.expanduser().resolve()` computed and used in TTY confirmation prompt. Test verifies the resolved absolute path appears in the prompt string. 133 tests pass.

#### CR-21 — `_read_roster_lines_interactive` had zero test coverage
**File:** [cli.py](src/sidelinehd_extractor/cli.py)
**Resolved:** Pass 5 re-review

Test added using patched `builtins.input` with a double-blank terminator sequence. Asserts the trailing single blank is included and the second consecutive blank stops iteration. 133 tests pass.

#### CR-20 — `_format_roster_next_command` hardcoded the default template path
**File:** [cli.py](src/sidelinehd_extractor/cli.py)
**Resolved:** Pass 5 re-review

Hint now uses `--template YOUR_TEMPLATE`. Unit test updated to match. 133 tests pass.

#### CR-19 — `_event_has_roster_name_match` has an unused `roster` parameter
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 5

#### CR-18 — Tesseract missing-binary error message is macOS-only
**File:** [ocr.py](src/sidelinehd_extractor/ocr.py)
**Resolved:** Pass 3

`_tesseract_install_hint()` branches on `sys.platform` for darwin, linux, and win, with a generic fallback for unrecognised platforms. Tests cover all three specific platforms via `patch`. 111 tests pass.

#### CR-10a — `export_paths` return type is untyped
**File:** [workflow.py](src/sidelinehd_extractor/workflow.py)
**Resolved:** Pass 3

`export_paths` now returns `tuple[Path, Path]`. 100 tests pass.

---

#### CR-10b — `PathLike` alias defined in two modules
**Files:** [models.py](src/sidelinehd_extractor/models.py), [video.py](src/sidelinehd_extractor/video.py), [crops.py](src/sidelinehd_extractor/crops.py)
**Resolved:** Pass 3

`PathLike` consolidated into `models.py`; `video.py` and `crops.py` import the shared alias. 100 tests pass.

---

#### CR-10c — `format_inning_header` type annotation disagrees with implementation
**File:** [exports.py](src/sidelinehd_extractor/exports.py)
**Resolved:** Pass 3

`format_inning_header` now accepts `Optional[int]`, matching the existing `None` guard. 100 tests pass.

---

#### CR-13 — Frame read errors omit video duration
**File:** [video.py](src/sidelinehd_extractor/video.py)
**Resolved:** Pass 3

`read_frame_at` and `read_frames_at` now include duration in frame-read error messages by probing FPS and frame count from the already-open OpenCV capture. `_capture_duration_seconds` returns `None` if either property is unavailable, so the message degrades gracefully. Fake-capture unit tests added for both functions; 100 tests pass.

---

#### CR-17 — `PROJECT_CREDIT` duplicated in `test_workflow.py`
**File:** [tests/test_workflow.py](tests/test_workflow.py)
**Resolved:** Pass 3

`test_workflow.py` now imports `PROJECT_CREDIT` from `sidelinehd_extractor.exports`; local copy removed. 100 tests pass.

---

#### CR-14 — `ruff` not listed as a dev dependency
**File:** [pyproject.toml](pyproject.toml)
**Resolved:** Pass 3

`ruff>=0.4` added to `[project.optional-dependencies] dev`. README "Development Checks" section added with dev install, test, and lint commands. 98 tests pass.

---

#### CR-15 — README misstates OCR default for primary commands
**File:** [README.md](README.md)
**Resolved:** Pass 3

Setup section and OCR section now correctly state that `run-game`/`run-youtube` default to `--ocr tesseract`, and that `--ocr none` is the explicit debug/no-OCR mode for lower-level `process` use. 98 tests pass.

---

#### CR-01 — No license file
**File:** repo root
**Resolved:** Pass 3

`LICENSE` (MIT, copyright Ryan Moore 2026) created at repo root. `## License` section added to README with a link to the file — this final fix was applied by the reviewer, not Codex.

---

#### CR-16 — README pre-release cleanup: specific URLs and team names in examples
**File:** [README.md](README.md)
**Resolved:** Pass 3

Real YouTube video ID (`j4At63cNpkc`) replaced with `YOUR_VIDEO_ID`; team-specific slug (`smash_it_sports_12u_flx_ice`) replaced with `your_team_game_name` throughout. "Current State" section removed (the intro paragraph already covers what the tool does without WIP framing).

---

#### CR-02 — CLI leaked raw tracebacks on common user errors
**File:** [cli.py:806-822](src/sidelinehd_extractor/cli.py#L806-L822)
**Resolved:** Pass 2

`main()` now catches `json.JSONDecodeError` (with a dedicated clear message), plus `(ValueError, FileNotFoundError, OSError)`. The original yt-dlp and OCR error handlers are intact. Correct fix.

---

#### CR-03 — `smooth_states` mutated frozen dataclasses in place
**File:** [state.py:187](src/sidelinehd_extractor/state.py#L187)
**Resolved:** Pass 2

Was assigning `state.inning = inning` / `state.half = half` directly. Now uses `dataclasses.replace(state, inning=inning, half=half)`. Correct fix.

---

#### CR-04 — `OverlayState` was the only mutable core model
**File:** [models.py:131](src/sidelinehd_extractor/models.py#L131)
**Resolved:** Pass 2

`OverlayState` is now `@dataclass(frozen=True)`, consistent with `Video`, `RegionFraction`, `OCRSample`, `Event`, and `Correction`. After CR-03 was fixed, this was safe to apply.

---

#### CR-06 — `parse_inning` OCR heuristics were undocumented
**File:** [state.py:91-92](src/sidelinehd_extractor/state.py#L91-L92)
**Resolved:** Pass 2

The `"4..."` → TOP and `"7..."` → BOTTOM prefix handling now has a comment explaining that SidelineHD's half-inning arrow can OCR as a leading digit fused with the inning number. Exactly the right amount of explanation.

---

#### CR-07 — `preprocess_for_ocr` would `AttributeError` on `None` input
**File:** [ocr.py:114-117](src/sidelinehd_extractor/ocr.py#L114-L117)
**Resolved:** Pass 2

Now checks `if image is None` first, then `if not hasattr(image, "shape") or len(image.shape) < 2` as a separate readable guard. Correct fix.

---

#### CR-08 — `process_video` unconditionally SHA-256 hashed the full video
**File:** [processing.py:131](src/sidelinehd_extractor/processing.py#L131)
**Resolved:** Pass 2

`process_video` now takes a `compute_video_hash` parameter. The CLI exposes `--hash-video` (opt-in). Default is no hashing. Correct fix; saves 10–30 seconds on large video files for the common case.

---

#### CR-09 — ~25 CLI arguments duplicated verbatim between `run-game` and `run-youtube`
**File:** [cli.py:462-539](src/sidelinehd_extractor/cli.py#L462-L539)
**Resolved:** Pass 2

Shared arguments are now defined in `_add_run_processing_arguments(parser)`. YouTube-only arguments (`--format`, `--youtube-client`, etc.) remain on `run-youtube` only. The duplication is eliminated.

---

## Architectural Notes

These are observations on design decisions and trade-offs that do not require immediate action but should inform future work.

### Data flow: smoothed states go to JSONL
`parse_samples_file` writes the *smoothed* states (post `smooth_states`) to `states.jsonl`, not the raw parsed states. This is the correct behavior for auditability — the file represents what the pipeline actually used. The implication is that re-running `detect-events` on a saved `states.jsonl` uses the same smoothed data, but re-running `parse-states` from `samples.jsonl` would re-smooth from scratch. Keep this in mind if you ever add a `--no-smooth` flag for debugging.

### OCR backend extensibility
The `OCRCallable = Callable[[object, str], OCRBackendResult]` type alias and `create_ocr_backend(name)` factory make adding new backends (EasyOCR, PaddleOCR, a vision API) straightforward. The only coupling point is `FIELD_CONFIGS`, which is Tesseract-specific. A future backend may need its own config structure — consider a `backend_config` parameter or per-backend config dict when that time comes.

### `detect_events` parameter growth
`detect_events` has 8 parameters, 5 of which are tuning knobs. This is still manageable. If more tuning knobs are added (e.g., per-overlay-type batter confirmation windows, score-change detection thresholds), a `DetectionConfig` dataclass would clean this up and make per-game config files feasible.

### Corrections as CSV
The CSV corrections approach is simple, auditable, and easy to explain to non-developers. The tradeoff is that collaborative review (two people correcting the same run independently) requires merging CSV files by hand. This is fine for the current single-videographer use case. JSONL correction events would be better for a multi-reviewer workflow but add complexity that isn't warranted yet.

### Package naming
`sidelinehd-extractor` and the `sidelinehd_extractor` module name are SidelineHD-specific. The architecture (normalized templates, configurable regions, pluggable OCR) already supports other overlay systems. Renaming the package is low-priority while the tool is SidelineHD-focused, but the Roadmap correctly flags it as something to revisit before a broader release.
