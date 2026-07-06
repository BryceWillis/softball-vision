# Code Review

**Reviewer:** Claude (Senior Software Architect)
**Last updated:** 2026-07-06
**Review passes:** 31 (Pass 7: item 36 — lineup-strip confidence split; CR-26 through CR-31 resolved) (Pass 8: items 34 + 32 — game-start detection and batting-order validator; CR-32 through CR-37 resolved) (Pass 9: item 29 — score at inning transitions; CR-38 resolved) (Pass 10: item 28 — project config defaults; CR-39 resolved) (Pass 11: item 35 — final scorebug marker; CR-40 and CR-41 resolved) (Pass 12: item 37 — playlist batch queue; CR-42 through CR-46 resolved, CR-47 deferred) (Pass 13: item 44 — pregame game-start suppressor; CR-48 and CR-49 resolved) (Pass 14: item 45 — right_score calibration + empty-field guard approved; CR-50 opened) (Pass 15: item 46 — local web app phase 39a skeleton + job runner, by Fable 5, approved; CR-51 opened) (Pass 16: item 47 — web app phase 39b results + paste kits, by Fable 5, approved; CR-50 and CR-51 resolved; item 48 opened for the review-report generation gap Fable flagged) (Pass 17: BATCH review of six co-mingled items — 48 + 49 (Fable) and 41 + 40 + 42 + 38 (Codex) — all approved; CR-52 opened; forced by a shared-tree tangle, prevention recorded in ROLES.md worktree-isolation policy) (Pass 18: CR-52 resolved by Fable 5 — feedback label-only name redaction; first item landed via the new worktree-isolation flow) (Pass 19: item 50 — roster management web UI, by Fable 5, approved and merged from impl/item-50) (Pass 20: item 51 — send-feedback web UI, by Codex, approved and merged from impl/item-51; PII-leak invariant verified across preview/GitHub/email/copy; completes the Local Web App epic, item 39) (Pass 21: item 43 — OCR multi-PSM voting + per-field preprocessing, by Fable 5, approved and merged from impl/item-43; measured deviation from the design's example strategies, flagged with data + a committed regression test) (Pass 22: item 53 — yt-dlp module fallback, by Codex; one review defect fixed on-branch before merge: absent-yt-dlp RuntimeError escaped cli.main() -> now FileNotFoundError, caught, clean exit 1) (Pass 23: item 54 turnkey fixes P1-P4 by Fable 5 — real SidelineHD template as default, no-scoreboard health warning, live frame progress, consolidated game page — approved; deviations all flagged; item 55 template-auto-detect design filed pending architect validation) (Pass 24: item 54 phases 54a+54b by Fable 5 — automatic ffmpeg via bundled imageio-ffmpeg + dependency preflight/setup card, and a one-command `start` that launches+opens the browser+stops cleanly — approved; deviations local-tier) (Pass 25: BATCH — item 59 (Codex: roster-confirmed batters no longer flagged possible-substitute) + Fable items 54c onboarding, 55 template probe/fail-fast, 52 roster display name, 30 originality audit, 54e coach README, 54d macOS-bundle design — all approved+merged; item 56 inning recalibration REJECTED — proposed coords validated ineffective on real footage, inning still misreads 72/43, needs frame-based recalibration) (Pass 26: scorebug accuracy cluster items 60+61+56 by Fable 5 — glyph-isolation preprocessing, PSM/whitelist fix for single-digit 0, arrow half detection, score plausibility + confidence guards, half-boundary batter reset — approved; independently re-validated on both real videos: G1 164->16 + clean inning, G2 early scores read + at-bats 23->28) (Pass 27: items 57 persistent run history [independently verified: 25 real runs recovered on a fresh store], 58 exception triage + plain language, 54d macOS menubar app bundle [tesserocr self-bundling validated, .app built+launched] — all by Fable 5, approved; 54d data dir ~/Library/Application Support confirmed correct by architect) (Pass 28: item 62 by Codex — glyph isolation extended to batter_card_number; card-present reads up + false absent-card noise 8->0, no scorebug regression, independently spot-checked clean; scoped to batter_card_number only, flagged) (Pass 29: CR-53 by Codex — user-reported live-fire fix for `PrITEF1eozM`: `smooth_states` gap-capped at 15s so a stray pregame inning no longer smears across the banner span, first-chapter gate now requires the full active scorebug (`_has_active_scorebug_signal`), and half-inning chapter scores switched to end-of-half semantics (next half's start / FINAL); approved and merged from impl/item-top1-score — 497 tests pass, ruff clean, user-directed semantics deviation flagged) (Pass 30: item 63 by Fable 5 — review rows deep-link to the source YouTube video at each play's timestamp; `run_youtube_game` now persists `youtube.video_id` (shared `record_youtube_source` factored out of the batch path), new `youtube_watch_url`/`extract_video_id` helpers, `_review_rows.html` gated anchor; approved as-is, no deviations, 507 tests pass.) (Pass 31: item 19 full Windows support by Fable 5 — cross-platform README/checklist (labelled macOS/Linux/Windows install + venv activation, `py -3`), ffmpeg documented as recommended-not-required, `next_commands` switched to the installed `sidelinehd-extractor` console script with cmd.exe-safe double quotes, `requires-python`/ruff target raised to 3.10, and a 3-OS × py{3.10,3.14} GitHub Actions matrix; **Fable flagged** that the designed `unittest discover` step silently skips the pytest-style web-app tests — reviewer corrected the CI step to `pytest` (379→498 tests, restoring the whole web-app surface) before merge; approved, 498 tests pass, ruff clean.)

This document is the running record of architectural observations, bugs, and improvement recommendations for the `sidelinehd-extractor` codebase. It is updated after each review pass. Items move to **Resolved** once confirmed fixed.

## Status Workflow

- **Reported**: an implementer (Codex or Fable 5) found a bug outside the scope of the item it was working on and logged it here instead of fixing it inline. Not yet triaged.
- **Open**: reviewed finding is accepted as work to do (either from an architect review pass, or triaged up from Reported).
- **Ready for Review**: the implementer has implemented the change and verified tests; awaiting reviewer/user confirmation.
- **Resolved**: reviewer/user has confirmed the implementation and moved the item to the Resolved section.
- **Deferred**: valid finding, but intentionally postponed.

Implementers may add new **Reported** items directly (bug found while working on something else — file/line + short description, no fix), and may update an **Open** item to **Ready for Review** after implementing it with a short implementation note. Only the architect (Claude) triages Reported → Open/Deferred, and only the architect moves items from Ready for Review to Resolved after verifying the diff and behavior. **Approval is signalled by a git commit** — the architect stages and commits all reviewed changes as the final step of a successful review pass. If findings require fixes, no commit is made until all open items are resolved.

---

## Ready for Review Items

_No items ready for review._

## Reported Items

_No reported bugs pending triage._

## Open Items

_No open items._

## Deferred Items

#### CR-47 — 30-parameter passthrough fan-out should bundle into the planned `DetectionConfig`
**File:** [batch.py](src/sidelinehd_extractor/batch.py) — `run_playlist_batch` / `_run_playlist_entry` signatures
**Pass:** 12 — altitude (deferred to item 22)

`run_playlist_batch` → `_run_playlist_entry` → `run_youtube` re-declares ~30 detection/tuning knobs at each hop with no transformation. Adding one new knob now means editing four parallel signatures, and a missed hop silently passes a stale default (batch runs would diverge from single-game runs). This materially weakens the deferral rationale for **item 22 (Detection Configuration Object)** — the fan-out just tripled. Not blocking item 37; folded into item 22's scope, which should now bundle these knobs into a `DetectionConfig` dataclass threaded through `run_game`/`run_youtube_game`/`run_playlist_batch`.

## Resolved Items

#### Item 19 — Full Windows Support
**File:** [README.md](README.md), [NEW_GAME_CHECKLIST.md](NEW_GAME_CHECKLIST.md), [pyproject.toml](pyproject.toml), [.github/workflows/ci.yml](.github/workflows/ci.yml) (new), [cli.py](src/sidelinehd_extractor/cli.py) (`_next_commands`, `_format_roster_next_command`)
**Pass:** 31 (by Fable 5, branch `impl/item-19`)
**Resolved:** Pass 31 — approved with one reviewer-applied CI fix

Implemented all 7 sub-tasks of the item 19 design: cross-platform README + `NEW_GAME_CHECKLIST.md` (labelled macOS/Linux/Windows install blocks, ffmpeg as recommended-not-required, `py -3` + PowerShell/cmd.exe venv activation, no line continuations), `next_commands`/`_format_roster_next_command` switched to the installed `sidelinehd-extractor` console script with cmd.exe-safe double quotes (user-visible output change, covered by a new CLI test), `requires-python` and ruff target raised to `3.10`, and a new GitHub Actions matrix (ubuntu/macos/windows × py3.10/3.14). Fable's three local-tier deviations (`.[dev,web]` install so the web-app tests import; ruff target bump; roster-command quote change) are all appropriate and flagged.

**Reviewer-applied fix (design defect Fable correctly escalated).** The item 19 design (decision 3) specified `python -m unittest discover -s tests`. But the suite mixes `unittest.TestCase` classes with pytest fixture/function-style modules, so `unittest discover` runs only **379 of 498** tests and **silently skips the entire web-app test surface** (`test_webapp*`, `test_desktop`, `test_review_triage`) — a false-green CI that defeats the item's cross-platform-regression purpose. Fable implemented per the design and flagged the gap in a "Note for architect" rather than deviating silently — exactly right. I corrected the CI test step to `python -m pytest tests/` (pytest is already in the installed `dev` extra) before merge, restoring full coverage. Verified: 498 pass, ruff clean.

---

#### Item 63 — Deep-link review rows to the source video timestamp
**File:** [youtube.py](src/sidelinehd_extractor/youtube.py) (`youtube_watch_url`, `extract_video_id`); [workflow.py](src/sidelinehd_extractor/workflow.py) (`record_youtube_source`); [batch.py](src/sidelinehd_extractor/batch.py); [webapp/app.py](src/sidelinehd_extractor/webapp/app.py) (`_run_source_video_id`, `build_review_context`); [_review_rows.html](src/sidelinehd_extractor/webapp/templates/_review_rows.html)
**Pass:** 30 (by Fable 5, branch `impl/item-63`)
**Resolved:** Pass 30

Verified against the item 63 design; **no deviations, approved as-is**:
- **Prerequisite done right.** `run_youtube_game` now persists `youtube.video_id` to the run manifest. Since `DownloadResult` carries no authoritative id, the id is parsed from the submitted URL via a new `extract_video_id` (handles `watch?v=`, `youtu.be/`, and `shorts`/`live`/`embed` path forms; unrecognizable → `None`) — the correct call given no cheaper source. The batch path's duplicated `_record_youtube_video_id` was **factored into a shared `workflow.record_youtube_source`** used by both paths (batch still layers `playlist_index`/`title` on top); manifest content unchanged for batch.
- **URL helper.** `youtube_watch_url(video_id, seconds)` floors fractional seconds (`int()`), exact (no lead-in), registered as a Jinja global next to `format_timestamp`.
- **Wiring/render.** `_run_source_video_id` reuses the existing guarded-manifest-read pattern (`_run_health_warning`), returns `None` on missing manifest/section/blank id; `_review_rows.html` gates the `<a target="_blank" rel="noopener">` on `source_video_id`, plain `<span>` otherwise. Additive display only — corrections/exports/`finalize_run_exports`/`review_report.md` untouched; no roster/player name enters any URL.
- **Tests.** `youtube_watch_url` (exact / fractional floor / `t=0s`), `extract_video_id` across all URL forms + unrecognizable, workflow manifest-persistence with existing-section survival, and route tests asserting anchors on a YouTube run and no anchor on local/blank-id runs. Independently re-verified: 507 pass, ruff clean.

---

#### CR-53 — First Top 1 chapter emitted from banner-only pregame span; half-inning chapter scores now use end-of-half semantics
**File:** [state.py](src/sidelinehd_extractor/state.py) — `smooth_states` / `_nearby_known_value`; [events.py](src/sidelinehd_extractor/events.py) — `_game_active_timestamp` / `_has_active_scorebug_signal` / `_apply_half_inning_end_scores`
**Pass:** 29 — correctness (user-reported live-fire, by Codex)
**Resolved:** Pass 29

User-reported bug from `PrITEF1eozM`: the opening `Top 1` chapter exported at `10:40` (still banner-only UI) with no score suffix, while the real active scorebug first appeared ~`18:04`. Root cause: `smooth_states()` propagated a stray `inning=1, half=top` across a multi-minute banner-only gap, and the first-chapter activity gate then accepted banner noise.

**Resolution.** Verified all three changes on branch `impl/item-top1-score`:
- `smooth_states()` was rewritten from unbounded backward/forward propagation (`_next_known_values`) to `_nearby_known_value` with a 15s cap (`_MAX_STATE_SMOOTH_GAP_SECONDS`), so a stray pregame inning read can no longer smear across the banner gap. Regression test `test_smooth_states_preserves_long_leading_gap_from_next_known_state`.
- `_has_active_scorebug_signal()` gates the first chapter on the full scorebug (`inning` + `count` + `left_score` + `right_score` OCR fields present together, plus parsed count/scores) — a strictly stronger signal than the bare `0-0` that CR-36/CR-48 reject, and correctly placed after the `_is_pregame_state` short-circuit. Confirmed `metadata["fields"]` is populated at [state.py:249](src/sidelinehd_extractor/state.py#L249) and field names match `FIELD_CONFIGS`.
- `_apply_half_inning_end_scores()` rewrites each HALF_INNING_START chapter's score to end-of-half semantics (next half's start score; last half gets FINAL). Start-scores are snapshotted by `id()` before mutation, so the next-half lookup reads original values. Only `_chapter_label` consumes these; `GAME_FINAL`'s own score is untouched.

**Deviation accepted:** user-directed behavior change (score-at-half-start → score-at-half-end), outside a roadmap item, flagged by Codex. **Behavioral note surfaced to Ryan:** a half's score now depends on the *next* half's readability, and the last half depends on a detected FINAL — so a truncated video with no FINAL will show no score on its final half-inning chapter (previously the start-of-half score). Accepted as inherent to the directed semantics; possible small fallback follow-up if desired. Independently re-verified: `PYTHONPATH=src python3 -m pytest tests/` → 497 passed, `ruff` clean.

---

#### CR-52 — Feedback sanitizer only redacts names it can register as a source; a label-only or non-`name` field name can leak
**File:** [feedback.py](src/sidelinehd_extractor/feedback.py) — `build_name_sanitizer` / `NameSanitizer.sanitize_text`
**Pass:** 17 — correctness/privacy (non-blocking follow-up to item 38)
**Resolved:** Pass 18 (by Fable 5)

`build_name_sanitizer` registers replacement sources from the roster, `event.player_name`, `"name"`-keyed metadata, and samples whose `field_name` contains `"name"`. `sanitize_text` then only masks those registered strings/tokens. A real name that appears **only** in an `event.label` or in a sample field whose name does not contain `"name"` — and never as a registered source — passes through unchanged into the feedback log, which is the one sanctioned egress surface. In practice labels are derived from the same `player_name` that is registered, so the gap is narrow and the guard tests cover the common paths, but a miss here leaks PII. Harden by also registering names parsed from `event.label` (e.g. the `"Name (#NN)"` pattern) into the sanitizer, and/or add a stricter net; extend the leak-guard test to seed a name that exists *only* in a label. Approved item 38 regardless — this is defense-in-depth on an already-guarded surface, not a demonstrated leak in current fixtures.

**Implementation note.** `build_name_sanitizer()` now registers names parsed from event labels matching the `"Name (#NN)"` pattern before rendering feedback, so label-only names get stable `Player X` pseudonyms. The feedback leak-guard fixture now includes `Charlotte P. (#44)` with no `player_name`, no roster entry, and no name-keyed metadata/sample source, and asserts `Charlotte` is absent while the generated `Player D` pseudonym appears.

**Resolution.** `build_name_sanitizer` now also registers names parsed from `"Name (#NN)"` event labels, closing the concrete label-only leak vector; the guard test seeds a label-only name (`Charlotte P. (#44)`) and asserts redaction to `Player D`. The speculative non-`name`-field vector has no known trigger among current OCR fields (name-bearing fields already contain `name`); reopen if such a field is added.

---

#### CR-50 — `write_review_report` read `manifest.json` with an unguarded `json.loads`
**File:** [review_report.py](src/sidelinehd_extractor/review_report.py) — `_manifest_warnings`
**Resolved:** Pass 16 (by Fable 5)

`_manifest_warnings()` now wraps the parse in `try/except (json.JSONDecodeError, OSError)` and returns `[]` when `manifest.json` is unreadable or corrupt, so `write_review_report` keeps producing a report for a bad run dir instead of raising. Verified: `test_write_review_report_ignores_corrupt_manifest` writes an invalid manifest, runs `write_review_report()`, and asserts the report is still produced with no Run Warnings section. 286 tests pass.

---

#### CR-51 — Web submit-error slot was cleared by every successful HTMX request, including the 1s status polls
**File:** [index.html](src/sidelinehd_extractor/webapp/templates/index.html) — `htmx:afterRequest` handler
**Resolved:** Pass 16 (by Fable 5)

The clear is now gated on `evt.detail.successful && evt.detail.requestConfig.path === "/jobs"` (with a CR-51 comment), so only a successful submit clears `#form-error`; the status polls hit `/jobs/{id}/status` and leave a shown validation message alone. Verified against the fix: status polls no longer match the gate. `test_index_error_clear_is_scoped_to_the_submit_request` asserts the rendered template gates on the `/jobs` path. 286 tests pass.

---

#### CR-48 — Pregame→ingame game-start path conditionally re-opened the item-34 / CR-36 "0-0 must not qualify" guard
**File:** [events.py](src/sidelinehd_extractor/events.py) — `_game_active_timestamp`
**Resolved:** Pass 13

Implemented Roadmap item 44's suppressor design. The `saw_pregame_status` latch and `_has_ingame_overlay_signal` early-return branch are removed (verified: no stale references in src/ or tests/). A `game_status == "pregame"` state now only suppresses — it is skipped and resets the batter-change baseline — and the game-start trigger remains item 34's positive-activity gate (`balls>0 or strikes>0`, or a trusted batter change), so a bare `0-0` never qualifies, pregame or not. Two crux regression tests confirm the fix: `test_game_active_timestamp_ignores_first_non_pregame_zero_count_state` (pregame → non-pregame 0-0 with a stable batter → `None`, where the old code returned the 0-0 timestamp) and `test_game_active_timestamp_waits_for_positive_activity_after_intermittent_pregame_reads` (flickering pregame reads + stable 0-0 → fires only at the first `strikes=1` state, t=405). 253 tests pass; ruff clean.

---

#### CR-49 — `_normalize_game_status` pregame matcher was a fragile hardcoded-OCR-variant denylist with redundant/over-broad tokens
**File:** [state.py](src/sidelinehd_extractor/state.py) — `_normalize_game_status`; [events.py](src/sidelinehd_extractor/events.py)
**Resolved:** Pass 13

Rewritten to tokenize alphabetic runs (`re.findall(r"[a-z]+", ...)`) and require a game-prefixed token (`gam`/`qam`/`oam`) **followed within 3 tokens** by a soon-like token — adding the adjacency/ordering constraint the old "gameish AND soonish anywhere" matcher lacked, and tightening away the riskiest token (`ong` dropped). The digit guard is gone, so `"GAME 7:00 SOON"` now normalizes to `"pregame"` (tokenizing already excludes `"0-0"`/`"top1"`, which carry no alphabetic game/soon tokens). A comment routes the durable fuzzy/confidence matcher to item 40. Shared `_game_status(state)` accessor added and used by both `_is_pregame_state` and `_detect_game_final`, removing the duplicated `"game_status"` literal. Tests cover the accepted OCR variants, the digit-bearing label, and tightened negatives (`"GAME ON FIELD"`, `"Smash-It Sports 12U"`, `"a1 0-0"`). 253 tests pass; ruff clean.

---

#### CR-42 — Playlist batch retried deterministic failures, re-running full download + OCR up to `retries+1` times
**File:** [batch.py](src/sidelinehd_extractor/batch.py) — `_run_playlist_entry`
**Resolved:** Pass 12

Retry is now scoped to `except YTDLPError` (the transient download stage); a generic `except Exception` returns a `failed` result on the first attempt, so deterministic processing/config/OCR errors no longer re-run the full download + whole-video OCR pipeline. Verified against the two regression tests: `test_run_playlist_batch_does_not_retry_deterministic_failures` raises `RuntimeError` and asserts the URL is called exactly once (`attempts == 1`, batch continues to the next entry), while `test_run_playlist_batch_retries_ytdlp_failures` raises `YTDLPError` and asserts the URL is called twice (`attempts == 2`, `retries=1`). The pair precisely exercises the transient-vs-deterministic distinction. 247 tests pass.

---

#### CR-43 — Skip path trusted prior state without verifying the run outputs still exist on disk
**File:** [batch.py](src/sidelinehd_extractor/batch.py) — `_is_complete_prior_result`
**Resolved:** Pass 12

New `_is_complete_prior_result(prior)` gates the skip branch: it requires `status == "done"` **and** `run_dir`, `chapters_path`, `at_bats_path` all non-None and `path.exists()`. A prior `done` record whose outputs were deleted now reprocesses instead of reporting a false skip with dead paths. Covered by `test_run_playlist_batch_reprocesses_done_entry_when_outputs_are_missing`. 247 tests pass.

---

#### CR-44 — Batch state file was append-only and grew unbounded; last-write status drifted
**File:** [batch.py](src/sidelinehd_extractor/batch.py), [processing.py](src/sidelinehd_extractor/processing.py)
**Resolved:** Pass 12

State is now an in-memory keyed snapshot (`state_snapshot`) rewritten atomically via the new `write_jsonl_atomic()` as one record per `video_id`, sorted by `(index, video_id)`. Skips no longer mutate the snapshot, so a `done` record keeps its status rather than drifting to `skipped`. `test_run_playlist_batch_compacts_state_to_one_record_per_entry` runs the batch twice over the same playlist and asserts the state file holds exactly two lines, both `done` — proving compaction, no drift, and correct skip-on-existing-outputs. Legacy append-only state files still load (last row per id wins) and are compacted on the next write. 247 tests pass.

---

#### CR-45 — `batch.py` re-implemented manifest-update and JSONL I/O that already existed
**File:** [batch.py](src/sidelinehd_extractor/batch.py), [workflow.py](src/sidelinehd_extractor/workflow.py), [processing.py](src/sidelinehd_extractor/processing.py)
**Resolved:** Pass 12

Shared `update_manifest_section(path, section_name, values)`, `write_jsonl_atomic()`, and `read_jsonl()` added to `processing.py`. `workflow._update_manifest_detection_config` now delegates to `update_manifest_section(..., "detection", ...)` and batch's `_record_youtube_video_id` uses it with the `"youtube"` section; batch state I/O uses the shared JSONL helpers instead of hand-rolled loops. The manifest write goes through `write_json` in both callers, so on-disk format stays consistent (indent=2, trailing newline). 247 tests pass.

---

#### CR-46 — Tidied `_run_playlist_entry` internals: dead state, unreachable branch, redundant counters, falsy-index guard
**File:** [batch.py](src/sidelinehd_extractor/batch.py), [youtube.py](src/sidelinehd_extractor/youtube.py)
**Resolved:** Pass 12

Retry loop rewritten as `for attempt in range(1, retries + 2)`; the dead `previous[...] = result` mutation is gone (replaced by the meaningful `state_snapshot[...] = result`); tallies use `collections.Counter`; a shared `_result_from_entry()` factory builds the done/failed/skipped results; and `_playlist_entry_index` uses explicit `None` checks so a legitimate `0` index no longer falls through to the fallback. The former `raise AssertionError` is replaced by an unreachable graceful `return`. 247 tests pass.

---

#### CR-41 — `OPTIONAL_TEMPLATE_FIELDS` in `processing.py` splits field optionality from field definitions in `ocr.py`
**File:** [processing.py](src/sidelinehd_extractor/processing.py), [ocr.py](src/sidelinehd_extractor/ocr.py)
**Resolved:** Pass 11

`optional: bool = False` added to `OCRFieldConfig`; `FIELD_CONFIGS["game_status"]` now carries `optional=True`, co-locating optionality with the field's OCR settings. `OPTIONAL_TEMPLATE_FIELDS` removed entirely (verified no dangling references in src/ or tests/). `select_template_regions` now derives optionality via the new `_is_optional_template_field()` helper, which reads `FIELD_CONFIGS[field].optional`. A future optional field is now a single-location change in `ocr.py`. Tests `test_game_status_field_config_is_optional` and `test_select_template_regions_skips_missing_optional_game_status` cover the config flag and the missing-optional selection path. 236 tests pass.

---

#### CR-40 — `detect_events_file` never forwarded `min_game_final_observations`; parameter was dead at CLI and workflow layer
**File:** [events.py](src/sidelinehd_extractor/events.py), [workflow.py](src/sidelinehd_extractor/workflow.py), [cli.py](src/sidelinehd_extractor/cli.py)
**Resolved:** Pass 11

`min_game_final_observations` added to `detect_events_file()` and forwarded to `detect_events()`; added to `run_game()` and `run_youtube_game()` in `workflow.py`, forwarded through the detection call, and recorded in the run manifest detection config. CLI flag `--min-game-final-observations` added to `run-game`, `run-youtube` (via `_add_run_processing_arguments`), and `detect-events`, and threaded through `_cmd_run_game`, `_cmd_run_youtube`, and `_cmd_detect_events`. Regression test `test_detect_events_file_forwards_min_game_final_observations` proves the fix: it passes `min_game_final_observations=2` with exactly 2 FINAL states and asserts one `game_final` event is emitted — which is impossible under the old hardcoded default of 3, so the test genuinely exercises the forwarded path. Workflow test asserts the manifest records the value and that `run_youtube_game` forwards it; CLI test asserts `--min-game-final-observations 2` parses. 236 tests pass.

---

#### CR-39 — `_offer_config_update` permanently drops template key when template path is absent at read time
**File:** [cli.py](src/sidelinehd_extractor/cli.py) — `_offer_config_update`, [config.py](src/sidelinehd_extractor/config.py)
**Resolved:** Pass 10

`_project_config_path` returns `None` for paths that don't exist on disk at read time. `_offer_config_update` used the loaded `ProjectConfig` to decide what to preserve on rewrite — so if the template file was temporarily unavailable, `existing.template` was `None`, the user was prompted for a template, and pressing Enter silently erased the previously-configured key. The same mechanism caused a spurious "Update config?" prompt when the configured roster path was also absent at read time. Fixed by adding `load_project_config_values(cwd)` to `config.py`, which returns raw `Dict[str, str]` INI strings without any path-existence check. `_offer_config_update` now calls this instead of `load_project_config`, and uses a new `_config_path_value()` helper to convert raw strings to `Path` objects (no existence check). Two regression tests added: `test_offer_config_update_preserves_missing_template_key` and `test_offer_config_update_skips_prompt_when_raw_roster_matches`. 222 tests pass.

---

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
