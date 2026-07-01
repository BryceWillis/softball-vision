# Code Review

**Reviewer:** Claude (Senior Software Architect)
**Last updated:** 2026-07-01
**Review passes:** 9 (Pass 7: item 36 — lineup-strip confidence split; CR-26 through CR-31 resolved) (Pass 8: items 34 + 32 — game-start detection and batting-order validator; CR-32 through CR-37 resolved) (Pass 9: item 29 — score at inning transitions; CR-38 ready for review)

This document is the running record of architectural observations, bugs, and improvement recommendations for the `sidelinehd-extractor` codebase. It is updated after each review pass. Items move to **Resolved** once confirmed fixed.

## Status Workflow

- **Open**: reviewed finding is accepted as work to do.
- **Ready for Review**: Codex has implemented the change and verified tests; awaiting reviewer/user confirmation.
- **Resolved**: reviewer/user has confirmed the implementation and moved the item to the Resolved section.
- **Deferred**: valid finding, but intentionally postponed.

Codex may update an Open item to **Ready for Review** after implementing it and should include a short implementation note. The architect (Claude) owns moving items from Ready for Review to Resolved after verifying the diff and behavior. **Approval is signalled by a git commit** — the architect stages and commits all reviewed changes as the final step of a successful review pass. If findings require fixes, no commit is made until all open items are resolved.

---

## Ready for Review Items

_No items ready for review._

## Open Items

_No open items._

## Resolved Items

#### CR-38 — `_score_snapshot` returns score from wrong half-inning when current-half states all have `None` scores
**File:** [events.py](src/sidelinehd_extractor/events.py) — `_score_snapshot`
**Resolved:** Pass 9

`_score_snapshot` had no `half_key` guard: when the 12-state confirmation window overlapped the next half-inning and all current-half states had `None` scores, it returned the next half's score and silently stamped it onto the current `HALF_INNING_START` event. Fixed by adding `half_key: Optional[Tuple[int, HalfInning]] = None` parameter — states whose `_half_key()` doesn't match are skipped. Call site in `detect_events()` passes `half_key=half_key`. New test `test_score_snapshot_ignores_scores_from_different_half_inning` covers the exact failure path; existing `test_score_snapshot_returns_first_complete_pair_in_window` updated to pass `half_key`. 112 tests pass.

---

#### CR-37 — Manifest recorded `order_validation: True` even when validation was skipped
**File:** [workflow.py](src/sidelinehd_extractor/workflow.py)
**Resolved:** Pass 8

Manifest now records `order_validation_requested` and `order_validation_ran` as separate fields. `order_validation_ran` is computed from the actual execution path: True when detect_events_file ran validation (non-auto path with roster), or True when the auto-half path ran validation at line 127. Manifest write is deferred until after the conditional validation block so it accurately reflects what executed. 201 tests pass.

---

#### CR-36 — `_has_named_batter_card_with_count_signal` fired on explicit `0-0` count, bypassing the item 34 pregame gate
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 8

`_has_named_batter_card_with_count_signal` removed entirely. `_game_active_timestamp` now has two activity signal paths only: (1) non-zero count (`balls > 0 or strikes > 0`), (2) batter change via `_has_batter_change_activity_signal`. A named batter card at 0-0 no longer passes the gate. 201 tests pass.

---

#### CR-35 — Missed detection at end of inning N generated false `inferred-missing` events at start of inning N+1
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 8

`validate_batting_order` now tracks `at_seed_half_start` (set True on each HALF_INNING_START, cleared on each AT_BAT_START). Inference is suppressed when `at_seed_half_start` is True — the first detected batter of each half never triggers cross-inning inference, regardless of `forward_skip`. Same-inning gap inference (batters 2+ in the half) is unaffected. 201 tests pass.

---

#### CR-34 — `_player_name_lookup` overwrote event-observed names with roster display names
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 8

Roster loop now guards with `if number not in number_to_name:` — observed event names take priority and roster names fill in only when no observed name exists. Inferred and detected events for the same jersey number now use consistent names. 201 tests pass.

---

#### CR-33 — `_has_batter_change_activity_signal` returned `False` for all non-lineup-strip sources; batter-card-only and old-style-template t=0 streams emitted no first chapter
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 8

`_has_batter_change_activity_signal` now returns `True` for `BATTER_SOURCE_LINEUP_NUMBER` unconditionally (old-style template, already roster-confirmed), and `True` for `BATTER_SOURCE_BATTER_CARD` when `batter_name` looks like a player name (`_looks_like_player_name`). Full-strip lineup_strip remains untrusted (requires highlight confirmation). Old-style and batter-card-only t=0 streams can now trigger activity via batter change, restoring first-chapter emission without regressing the item 34 pregame fix. 201 tests pass.

---

#### CR-32 — `_infer_seed_info` alphabetical sort picked `"bottom"` before `"top"` when both halves qualified
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 8

`_half_inning_sort_key(key)` helper added: maps TOP to index 0, BOTTOM to index 1. `_infer_seed_info` now passes this as the sort key, ensuring TOP always precedes BOTTOM within the same inning when both halves qualify. 201 tests pass.

---

#### CR-31 — `review.py` inline duplicated the `_lineup_is_highlight_confirmed` logic
**File:** [review.py](src/sidelinehd_extractor/review.py), [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 7

`_metadata_is_highlight_confirmed(metadata: dict)` helper added to `events.py`; `_lineup_is_highlight_confirmed` now delegates to it. Because CR-30 removed the dead review-side confidence comparison, `review.py` no longer has any duplication to resolve. 183 tests pass.

---

#### CR-30 — `lineup-unconfirmed` review flag was dead code for newly processed games
**File:** [review.py](src/sidelinehd_extractor/review.py)
**Resolved:** Pass 7

Chose fix option (b): removed the dead `lineup-unconfirmed` flag path and added a comment explaining that non-highlight lineup-strip reads are blocked before event emission. `lineup-recovered` flag remains for accepted highlight-confirmed lineup-strip at-bats. 183 tests pass.

---

#### CR-29 — String literals for lineup source/confidence scattered across 4 files with no shared constant
**Files:** [constants.py](src/sidelinehd_extractor/constants.py), [ocr.py](src/sidelinehd_extractor/ocr.py), [events.py](src/sidelinehd_extractor/events.py), [review.py](src/sidelinehd_extractor/review.py), [state.py](src/sidelinehd_extractor/state.py)
**Resolved:** Pass 7

New `constants.py` defines `LINEUP_SOURCE_HIGHLIGHT`, `LINEUP_SOURCE_FULL_STRIP`, `LINEUP_STRIP_CONFIDENCE_KEY`, `BATTER_SOURCE_BATTER_CARD`, `BATTER_SOURCE_LINEUP_STRIP`, and `BATTER_SOURCE_LINEUP_NUMBER`. All four consumer files import and use these constants. 183 tests pass.

---

#### CR-28 — Fused-digit full-strip window states dropped below `min_batter_observations`, silently suppressing real at-bats
**File:** [events.py](src/sidelinehd_extractor/events.py) — `_confirmed_batter_identity`
**Resolved:** Pass 7

`_confirmed_batter_identity()` now resolves unambiguous fused digit runs from window states inline (via `_resolve_lineup_digit_run`) for confirmation counting only. Full-strip window states with e.g. `batter_number="265"` that unambiguously resolve to a rostered `"26"` now count toward the observation minimum. Regression test covers the exact failure scenario: highlight trigger plus full-strip `"265"` window resolving to `#26`. 183 tests pass.

---

#### CR-27 — `_preferred_lineup_number_for_state` over-broadly blocked full-strip lineup from correcting wrong batter-card numbers
**File:** [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 7

`_preferred_lineup_number_for_state()` restored to use `_active_lineup_number_for_state()` (not `_highlight_lineup_number_for_state`). Full-strip reads can again correct batter-card misreads; the highlight gate remains exclusively in `_is_plausible_batter_source()` governing AT_BAT_START emission. 183 tests pass.

---

#### CR-26 — `batter_number_source` hardcoded to `"lineup_strip"` when number came from old `batter_number` OCR field
**File:** [state.py](src/sidelinehd_extractor/state.py)
**Resolved:** Pass 7

`state_from_samples()` now uses a proper if/elif cascade: `batter_number_source` is `"batter_card"` when the card OCR contributed, `"lineup_strip"` when `lineup_strip_number` contributed, and `"lineup_number"` when the old `batter_number` field contributed. The highlight-confidence gate in `_is_plausible_batter_source` only applies to the `"lineup_strip"` source. Old-style templates without a `lineup_strip` field continue to emit at-bats. 183 tests pass.

---

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
