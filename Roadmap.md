# Roadmap

This roadmap captures implementation deliverables from code review findings and
product ideas. The intent is to work through these one at a time, keeping the
tool useful and stable after each step.

`CODE-REVIEW.md` is the source of truth for CR lifecycle. Roadmap items that
come from review findings include a `Source: CR-XX` line. Feature ideas that are
not from code review use `Source: Product backlog`.

## Guiding Priorities

1. Keep the local CLI reliable for non-developer users.
2. Protect the deterministic OCR/state/event pipeline from subtle mutation bugs.
3. Improve maintainability before adding larger product features.
4. Keep public-release readiness visible, even while the tool is still personal-use first.

## Implementation Queue

**CODE-REVIEW.md open items always preempt this queue.** Check that file first; if anything is Open, implement it before picking up the next roadmap item.

For items marked **Needs design**, Codex should stop and ask the architect (Claude) to write the full design before starting implementation.

| # | Item | Status | Rationale |
|---|------|--------|-----------|
| — | **54 live-fire fixes P1–P4** (default template, no-scoreboard health check, OCR progress, consolidated game page) | Ready for review (`impl/turnkey-fixes`, Fable 5) | Live-fire against a real 2.4h game: unconfigured runs silently produced zero results (P1/P2), the 20–40 min OCR phase looked frozen (P3), and managing a game required hopping across three pages (P4). See item 54 section for details. |
| 2 | **55** — Overlay Template Auto-Detection (probe pass) | Ready for review (`impl/item-55`, Fable 5) | Item 54 P5 follow-up: probe a few frames, score known layouts, auto-select the template so users never configure one. One-candidate no-op until item 26 lands more layouts. |
| 1 | **54** — Turnkey Web App (zero-friction install/launch/onboarding) | 54a + 54b Ready for review (`impl/turnkey-launch`, Fable 5); 54c next | **Release gate.** Make the web app usable by a non-technical coach: auto-provision ffmpeg via pip, one-command launch that opens the browser, in-app onboarding, and (endgame) a double-clickable bundled app. Phases 54a–54e. Motivated by live-fire prep — the owner couldn't start it unaided. |
| — | **45** — Fix `right_score` Calibration + Empty-Field Guard | Done (Pass 14) | Recalibrated `right_score` from real Victor Vipers frames and added field-read stats plus all-empty warnings in manifest, run output, and review reports. Follow-up: CR-50 (harden review-report manifest read). |
| — | **46** — Web App 39a: Skeleton + Job Runner | Done (Pass 15) | **Web track (Fable 5).** FastAPI localhost app: paste URL/playlist → background job → live HTMX status. Approved Pass 15; follow-up CR-51 (submit-error slot cleared by status polls). |
| — | **47** — Web App 39b: Results + Paste Kits | Done (Pass 16) | **Web track (Fable 5).** `GET /jobs/{id}/results` with stacked per-game copy kits (via new `render_publish_kit_fragment`) + review-report flagged count/run warnings. Approved Pass 16; CR-50/CR-51 resolved. **Review summary is dark until item 48** (nothing writes `review_report.md` during runs). |
| — | **48** — Generate `review_report.md` during runs | Done (Pass 17) | **Web track (Fable 5).** Implemented: `run_game` writes `review_report.md` after export (degrades via `warning review-report-failed`; opt-out flag threaded through `run_youtube_game`); item 47's per-game review summary now lights up end-to-end. Awaiting architect review. |
| — | **49** — Web App 39c: Exception Review + Corrections UI | Done (Pass 17) | **Web track (Fable 5).** Implemented: `/jobs/{id}/review` flagged-events UI → edit/delete/add → de-duped `<run_dir>/corrections.csv` → faithful re-export via new shared `finalize_run_exports` + manifest-persisted export options. Awaiting architect review. |
| — | **50** — Web App 39d: Roster Management UI | Done (Pass 19) | **Web track (Fable 5).** `/rosters` list/create + `/rosters/{slug}` edit/replace/delete/set-default, all writes through `parse_team_list`/`write_roster_csv`; slug traversal-guarded; set-default via item 28's config writer. Names stay local. |
| — | **51** — Web App 39e: Send-Feedback UI | Done (Pass 20) | **Web track (Codex).** Sanitized feedback preview (item 38's `render_feedback_log`) → prefilled GitHub-issue/mailto/copy hand-off, no outbound request. PII-leak test across preview/GitHub/email/copy. |
| — | **41** — OCR Pipeline Performance | Done (Pass 17) | **OCR track (Codex).** Added worker-pool OCR with stable sample ordering, optional `tesserocr` backend/fallback, and opt-in end-to-end crop saving via `--save-crops`. |
| — | **40** — OCR Confidence Capture | Done (Pass 17) | **OCR track (Codex).** Tesseract TSV parsing now captures 0–1 OCR confidence with numeric-min/text-weighted aggregation and degrades safely on malformed output. |
| — | **42** — Tesseract Version Capture | Done (Pass 17) | Captures `tesseract --version`, warns non-fatally for missing/old/unrecognized versions, and records the version in `manifest.json`. |
| — | **38** — Feedback Log | Done (Pass 17) | Added CLI-first sanitized Markdown feedback logs with stable player pseudonyms, preserved jersey numbers, environment/version metadata, review flags, and guard tests against name leakage. |
| — | **43** — OCR Accuracy Follow-ons | Done (Pass 21) | **Fable 5.** Multi-PSM voting (psm 7 vs 10, higher item-40 confidence wins) for the six numeric fields + `OCRFieldConfig.preprocess` dispatch. Measured deviation: shipped `numeric_glyph_pad` (Otsu + pad); the design's hard-threshold/adaptive examples regressed and were dropped. |
| 9b | **52** — Persist Roster Display Name | Ready for review (`impl/item-52`, Fable 5; based on `impl/item-55`) | Small. Roster CSV doesn't store the pretty team name → reloads as the file stem (e.g. `st_mary_s_12u`). Persist via a `# team_name:` header line, stem fallback. Surfaced by item 50 review. |
| — | **53** — Make declared `yt-dlp` dep sufficient | Done (Pass 22) | Small. yt-dlp is already a core dep (auto-installed); add a `python -m yt_dlp` fallback + clear error so it works even where the console script isn't on PATH. Surfaced by live-fire prep. |
| — | **39** — Local Web App | Epic complete (Pass 20) | All phases done: 39a/39b/39c/39d/39e = items 46/47/49/50/51. Local-first FastAPI + HTMX. Cloud/hosted is a later seam (see deferred CSRF hardening). |
| 11 | **30** — Originality Audit | Ready for review (`impl/item-30`, Fable 5) | Pre-release hygiene — research and documentation only, no code changes. Complete before broader release. |
| 12 | **26** — Multi-Layout Template Support | Ready to implement | Enables other SidelineHD overlay types. Larger effort — **blocked until Ryan supplies example videos for the new layouts.** |
| 13 | **19** — Full Windows Support | Ready to implement | Elevated relevance: the per-device install model (item 39) puts cross-platform packaging on the web-app path. Fold path/subprocess hygiene into items 46/47 as you go. |
| — | **44** — Pregame Status as Game-Start Suppressor | Done | Approved Pass 13 (CR-48, CR-49 resolved). |
| — | **37** — YouTube Playlist Batch Queue (CLI) | Done | Approved Pass 12 (CR-42–46 resolved; CR-47 deferred to item 22). |
| — | **35** — Final Scorebug Marker | Done | Approved Pass 11. |
| — | **29** — Score at Inning Transitions | Done | Approved Pass 9. |
| — | **28** — Project Config Defaults | Done | Approved Pass 10. |

Items 22, 23, 24, 25 are deferred architectural notes — they stay in the backlog but have no implementation slot until a concrete trigger arises.

## Accepted Deliverables

### 1. Add Project License

Source: CR-01
Status: Done

Pick a license and add a `LICENSE` file before any public release.

Acceptance criteria:
- `LICENSE` exists at the repo root.
- README includes a short license note.
- License choice is explicit: MIT, Apache-2.0, proprietary, or another chosen option.

### 2. Improve CLI Error Handling

Source: CR-02
Status: Done

Make CLI failures readable for non-developer users instead of leaking raw tracebacks for common input/runtime problems.

Acceptance criteria:
- `main()` catches common user-facing failures such as `ValueError`, `FileNotFoundError`, `OSError`, and JSON decode errors.
- Error output is concise and sent to stderr.
- Existing explicit handling for yt-dlp and OCR errors remains intact.
- Tests cover at least one user-facing CLI error path.

### 3. Remove `smooth_states` In-Place Mutation

Source: CR-03
Status: Done

Change state smoothing so it returns new `OverlayState` instances instead of mutating the input list.

Acceptance criteria:
- `smooth_states` uses `dataclasses.replace` or equivalent copy construction.
- Tests prove the original input states are not mutated.
- Current parsing/export behavior remains unchanged.

### 4. Decide and Enforce `OverlayState` Immutability

Source: CR-04
Status: Done

After removing smoothing mutation, make a deliberate decision about whether `OverlayState` should be frozen like most other core models.

Acceptance criteria:
- Either `OverlayState` is made `frozen=True`, or the reason for keeping it mutable is documented.
- Tests cover whichever behavior is chosen.
- Any needed construction/update helpers are added before freezing.

### 5. Expand Parser and Smoothing Tests

Source: Code review follow-up
Status: Done

Add direct tests for the fragile OCR parsing and state smoothing rules.

Acceptance criteria:
- `parse_inning` tests cover arrow-like OCR artifacts such as `42`, `72`, `o2`, `04`, oversized digits, and blank/no-inning states.
- `smooth_states` tests cover short OCR gaps, inning transitions, and no-mutation behavior.
- Tests remain fast and local.

### 6. Document Inning OCR Heuristics

Source: CR-06
Status: Done

Explain the SidelineHD-specific inning parsing artifacts in code comments where the logic lives.

Acceptance criteria:
- The `4...` and `7...` prefix handling is documented near `parse_inning`.
- The comment explains that OCR can fuse the up/down half-inning arrow with the inning digit.
- The comment is short and tied to the actual observed artifact.

### 7. Add Safer OCR Preprocessing Validation

Source: CR-07
Status: Done

The review called out a possible `None` image bug. The current short-circuit check appears safe, but this area should still be made clearer and tested.

Acceptance criteria:
- `preprocess_for_ocr(None, ...)` has an explicit test.
- Invalid image-shape errors are clear.
- The validation reads plainly enough that future reviewers will not misread it as unsafe.

### 8. Make Video Hashing Configurable

Source: CR-08
Status: Done

Avoid unconditional full-file SHA-256 hashing during `process_video` unless the user asks for audit-grade hashing.

Acceptance criteria:
- Processing defaults avoid full-video hashing or clearly justify keeping it.
- CLI exposes an option such as `--hash-video` if full hashing becomes opt-in.
- Manifest still records enough identity metadata for normal debugging.
- README explains the tradeoff.

### 9. Consolidate Duplicate Run CLI Arguments

Source: CR-09
Status: Done

Reduce the duplicated argument definitions between `run-game` and `run-youtube`.

Acceptance criteria:
- Shared run arguments are defined by a helper such as `_add_run_args`.
- YouTube-only arguments remain on `run-youtube`.
- Existing help text and defaults remain equivalent.
- CLI tests or parser smoke tests cover both commands.

### 10. Type and Utility Cleanup

Source: CR-10a, CR-10b, CR-10c
Status: Done

Clean up small consistency issues before they spread.

Acceptance criteria:
- `workflow.export_paths` returns `Tuple[Path, Path]` or `tuple[Path, Path]`.
- Repeated newline-at-end export behavior is centralized in one helper.
- Duplicate `PathLike` aliases are consolidated or intentionally left local with a comment.
- Serialization assumptions around tuples-as-lists are documented or covered by tests if relied on.

### 11. Improve Publish Output Defaults

Source: Product backlog
Status: Done

Revisit the default `scratch/publish/` behavior so first-time users can find outputs easily outside the repo workflow.

Acceptance criteria:
- Decide whether paste kits should default inside the run directory or remain under `scratch/publish`.
- If the default changes, README and tests are updated.
- If the default stays, README makes the output location very obvious.

### 12. Generalize New Game Checklist

Source: Product backlog
Status: Done

Make `NEW_GAME_CHECKLIST.md` feel like a reusable template for other teams and users.

Acceptance criteria:
- Replace any team-specific examples with placeholders or clearly labeled examples.
- Include `--batting-half auto` behavior note and mention of `top|bottom` override (item 17 is done; checklist already updated).
- Include `review-report` in the review workflow (done as part of item 17 implementation).
- Keep the checklist short enough to use during a real game-posting workflow.

### 13. Improve Frame Read Error Messages

Source: CR-13
Status: Done

Make out-of-range or unreadable frame errors easier to debug.

Acceptance criteria:
- `read_frame_at` / `read_frames_at` errors include the requested timestamp.
- When available, errors also include video duration.
- Tests cover the improved error message without requiring large media files.

### 14. Add Development Tooling Dependencies

Source: CR-14
Status: Done

Make linting/static checks reproducible for contributors.

Acceptance criteria:
- `ruff` is listed in an optional dev dependency group or documented install path.
- Consider `mypy` or `pyright` after the current type hints are cleaned up.
- README includes the command for running tests and lint checks.

### 15. Clarify OCR Defaults in README

Source: CR-15
Status: Done

Make setup and OCR docs match the current CLI defaults.

Acceptance criteria:
- README says `run-game` and `run-youtube` default to Tesseract OCR.
- README says lower-level `process` can run without OCR for crop/template debugging.
- README mentions `--ocr none` as the explicit non-OCR mode.

### 16. Remove Duplicated Project Credit Test Constant

Source: CR-17
Status: Done

Keep export-credit tests tied to the production constant.

Acceptance criteria:
- `test_workflow.py` imports `PROJECT_CREDIT` from `sidelinehd_extractor.exports`.
- No duplicate copy of the project-credit string remains in workflow tests.

### 17. Auto-Detect Batting Half

Source: Product backlog
Status: Done

Eliminate `--batting-half top|bottom` as a required user input. The tool should infer which half the rostered team bats in automatically.

**Background — why this is tractable:**
SidelineHD only shows named batter cards for the team that set up the SidelineHD
system. The opposing team's batters appear with no name data in the overlay — the
batter card either shows nothing useful or an anonymous jersey number that won't
match any roster entry. This means one half of each inning will produce near-100%
roster-matched at-bat events, and the other will produce near-zero matches. The
signal is essentially binary and should be reliable even with imperfect OCR.

**Approach:**
1. Run `detect_events` with `batting_half=both` (unchanged from current behaviour).
2. After detection, score each half:
   `match_rate = roster-matched at-bats / total at-bats` for top and bottom.
3. The half with a meaningful match rate is the rostered team's batting half.
4. Re-filter events to that half (or pass the inferred half back into the event
   label/export step — whichever is architecturally cleaner).
5. Log the inference for auditability:
   `Inferred batting half: top (7/8 roster matches in top, 0/9 in bottom)`.
6. If neither half has any roster matches (no roster provided, or OCR too noisy
   to resolve any player), fall back to `both` with a warning.

**CLI change:**
- `--batting-half` on `run-game` and `run-youtube` gains an `auto` option and
  defaults to it.
- `--batting-half top|bottom` remain as explicit overrides.
- Lower-level `detect-events` keeps `--batting-half both` as its default so
  callers retain full control.

**Note for item 12:** Update `NEW_GAME_CHECKLIST.md` to remove the `--batting-half`
step once this is shipped, since it will no longer be needed in the normal workflow.

Acceptance criteria:
- `run-game` and `run-youtube` default `--batting-half` to `auto`.
- Auto-detection logs the inferred half and the match counts used to decide.
- `--batting-half top|bottom` still overrides the inference.
- Inference falls back to `both` with a warning when no roster is provided or
  no roster matches are found in either half.
- Existing tests pass; new tests cover the inference logic with a mock roster
  and mock events split across top/bottom halves.

### 18. Reduce Noisy OCR Number Review Warnings

Source: Product backlog
Status: Done

Real-game testing showed that SidelineHD's font often makes specific jersey
numbers OCR incorrectly even when the player name is read well enough to match
the roster. The review report should flag number mismatches when they matter,
but it should not distract users with harmless number noise after a roster-name
match has already corrected the exported player.

Acceptance criteria:
- `ocr-number=...` remains flagged for number-only or otherwise unanchored detections.
- `ocr-number=...` is suppressed when `roster_match_source` is `name`.
- Plain review output and Markdown review reports share the same behavior.
- Tests cover both the flagged and suppressed paths.

### 19. Full Windows Support

Source: Product backlog
Status: Ready for Review

Implementation note for review:
- Added `PlaylistEntry` plus flat-playlist yt-dlp enumeration in `youtube.py`.
- Added reusable `batch.py` orchestration with JSONL state, `batch_summary.md`, skip-on-complete, `--force`, `--limit`, `--start-index`, retry isolation, per-entry result summaries, and per-run YouTube metadata in `manifest.json`.
- Added `run-playlist` CLI command sharing the existing run-processing arguments and YouTube download options.
- Documented playlist usage in `README.md` and added tests for enumeration, batch ordering, resume/skip, force, retry failure isolation, slicing, and CLI parsing.
- Pass 12 CR fixes are Ready for Review in `CODE-REVIEW.md`: retries are scoped to `YTDLPError`, skip validates existing outputs, state is compacted atomically, manifest/JSONL helpers are shared, and the batch internals were tidied.

Make the tool fully usable on Windows with accurate documentation and a CI
matrix that catches regressions on both platforms.

**Background — current state:**
The Python code is already cross-platform (pathlib throughout, no shell=True,
no Unix-specific syscalls). The gaps are entirely in documentation and the
absence of any CI. The v0.1.0 release notes explicitly call out Windows as
untested.

**Gap inventory (documentation):**

| Gap | Location |
|---|---|
| `source .venv/bin/activate` is Unix-only | README Setup, checklist |
| `python3` command | README throughout (Windows usually uses `python`) |
| `brew install tesseract` appears twice | README Setup + OCR sections |
| `PYTHONPATH=src python3 ...` env-var syntax | README Dev Checks + inline fallback |
| `ffmpeg` is completely undocumented | README, checklist |

**Note on ffmpeg:** `yt-dlp` silently falls back to lower-quality single-stream
formats when `ffmpeg` is unavailable, but for best results it needs `ffmpeg` to
merge separate audio and video streams. On macOS users typically already have it
(`brew install ffmpeg`). On Windows it requires a manual step that is currently
invisible to users. This should be documented alongside Tesseract in Setup.

**Gap inventory (CI):**
No `.github/` directory exists. Adding a GitHub Actions workflow that runs the
test suite on `macos-latest` and `windows-latest` would surface any platform
divergence early. The test suite is already fast (~0.2 s) and dependency-free
for external binaries, so this should be low-friction to maintain.

**Design decisions (all points resolved):**

1. **Linux in CI — included, not a bonus.** `ubuntu-latest` is in the matrix
   alongside `macos-latest` and `windows-latest`. The Tesseract hint already
   documents Linux; CI should match.

2. **Python version — raise to `>=3.10`.** Python 3.9 EOL'd in October 2025
   and yt-dlp already warns on it. Update `pyproject.toml` `requires-python`
   to `>=3.10` as part of this deliverable. CI tests 3.10 plus the current
   stable Python version.

3. **CI installs via pip, not PYTHONPATH.** `python -m pip install -e ".[dev]"`
   then `python -m unittest discover -s tests` and `ruff check .`. Tests the
   console entry point packaging path correctly.

4. **`next_commands` — use installed CLI commands.** Switch generated
   `next_commands` output from `PYTHONPATH=src python3 -m sidelinehd_extractor.cli ...`
   to `sidelinehd-extractor ...` throughout. This is a code change, not just
   documentation.

5. **Windows venv activation — document both shells.** README should show
   `.venv\Scripts\Activate.ps1` for PowerShell and `.venv\Scripts\activate.bat`
   for cmd.exe. Recommend `py -3` as the Python launcher on Windows instead of
   `python3`.

6. **ffmpeg — recommended, not required.** Document it as "recommended for
   reliable/best-quality YouTube downloads." Do not add a preflight check or
   make CI depend on ffmpeg.

7. **Shell examples — short and labelled.** No backslash/caret/backtick line
   continuations in Windows docs. Use separate labelled blocks (macOS/Linux
   and Windows) for commands that differ across platforms.

8. **`next_commands` portability in acceptance criteria — included.** Already
   reflected below.

**Sub-tasks for Codex:**

1. **README — Setup section**: add a tabbed or clearly-marked set of
   Windows alternatives for venv creation (`python -m venv`), activation
   (`.venv\Scripts\activate`), and Tesseract install (UB Mannheim link).

2. **README — OCR section**: the second `brew install tesseract` reference
   (line ~257) should mirror the same multi-platform guidance as Setup.

3. **README — Development Checks**: `PYTHONPATH=src python -m unittest` works
   on macOS/Linux. Add a Windows note: use
   `set PYTHONPATH=src && python -m unittest discover -s tests` in cmd.exe, or
   `$env:PYTHONPATH="src"; python -m unittest discover -s tests` in PowerShell.

4. **README — ffmpeg**: add a brief "External dependencies" summary near the
   top of Setup listing both Tesseract and ffmpeg with per-platform install
   commands. ffmpeg on Windows: `winget install Gyan.FFmpeg` or manual download
   from https://ffmpeg.org/download.html.

5. **NEW_GAME_CHECKLIST.md**: mirror the same Tesseract + ffmpeg install blocks
   and add Windows venv-activation alternative.

6. **GitHub Actions CI** (`.github/workflows/ci.yml`): matrix of
   `ubuntu-latest`, `macos-latest`, `windows-latest` × Python 3.10 and current
   stable Python. Steps: `pip install -e ".[dev]"`, then
   `python -m unittest discover -s tests`, then `ruff check .`. Triggered on
   push and pull request. Also bump `pyproject.toml` `requires-python` to
   `>=3.10` in this same PR.

7. **CLI follow-up commands**: update generated `next_commands` to be
   cross-platform. Preferred output is installed-console-script commands such as
   `sidelinehd-extractor review-events ...`, with docs retaining `python -m ...`
   only as a fallback.

Acceptance criteria:
- README Setup section documents venv creation, activation, Tesseract, and
  ffmpeg for macOS, Linux, and Windows.
- `brew install tesseract` does not appear without a Windows/Linux alternative
  nearby.
- ffmpeg is documented as a recommended system dependency, or the code adds a
  deliberate preflight check if the project wants to make it required.
- Generated `next_commands` are copy/pasteable on Windows after the package is
  installed.
- A GitHub Actions workflow exists and passes on `ubuntu-latest`,
  `macos-latest`, and `windows-latest`.
- All existing tests and Ruff continue to pass on all CI platforms.

### 20. HTML Paste Kit with One-Click Copy Buttons

Source: Product backlog
Status: Done

Generate an optional self-contained HTML file alongside the existing Markdown
paste kit so users can copy each YouTube section to the clipboard with a single
click instead of manually selecting text.

**Background — current workflow friction:**
The current `publish-helper` writes a `youtube_paste_kit.md` file with two
blocks of text that must be copy-pasted into YouTube: the description chapters
and the pinned-comment at-bats. Opening a Markdown file and manually selecting
the right block is awkward, especially when posting from a phone or a secondary
machine. A local HTML file opened in any browser removes that friction.

**Feature description:**
`publish-helper` gains a `--html` flag (or generates the HTML file alongside
the Markdown by default — see decision note below) that writes a
`youtube_paste_kit.html` next to the `.md` file. When opened in a browser it
shows:

- **Section 1 — Description chapters**: the timestamp chapter block, with a
  "Copy to clipboard" button. One click, ready to paste into the YouTube
  description.
- **Section 2 — Pinned-comment at-bats**: the inning-grouped at-bat block,
  with its own "Copy to clipboard" button.
- **Section 3 — Posting checklist**: the same checklist from the Markdown kit,
  rendered as a readable HTML checklist (checkboxes the user can tick in the
  browser to track their progress through the posting workflow).

**Decision note — opt-in vs always-on:**
Generating HTML by default adds no runtime cost (pure string output), but a
first-time user who opens the run directory may find two output files
confusing. Recommended approach: generate HTML by default and add
`--no-html` to suppress it if desired. Codex should make the final call and
document it.

**Codex design review feedback:**

I support this feature. It addresses a real workflow problem and fits naturally
inside `publish-helper`. I do not consider the design fully implementation-ready
until these details are resolved:

1. **Credit decision: include credit in both copy boxes.** The user wants the
   project credit included in both copyable payloads. The HTML should therefore
   put the already-rendered chapter text, including its credit footer, in the
   chapter copy box and the already-rendered at-bat text, including its credit
   footer, in the at-bat copy box. The HTML page may also include a small footer
   that explains the tool, but that footer is informational only and does not
   replace the copy-box credit.

2. **Generate HTML by default.** I agree with the recommended always-on approach.
   `publish-helper` is already the "make this easy to paste" command, and a
   sibling `youtube_paste_kit.html` is discoverable. Add `--no-html` only for
   users who want Markdown-only output. Keep the Markdown file as the stable,
   plain-text fallback.

3. **Return both output paths from the publish API.** `PublishKitResult`
   currently has one `output_path`. If HTML is generated alongside Markdown,
   extend the result with `markdown_path` and optional `html_path`, or rename the
   existing field deliberately. This avoids ambiguous CLI JSON output.

4. **Escape all inserted content.** Game names, paths, chapters, and at-bats must
   be HTML-escaped before insertion. Use the standard library `html.escape`.
   The text inside `<textarea>` or `<pre>` still needs escaping; do not assume
   timestamp output is always harmless.

5. **Use `<textarea readonly>` for copy payloads.** This makes the fallback
   simple: if both clipboard APIs fail, users can manually select/copy from the
   visible field. It also avoids tricky whitespace preservation bugs and makes
   byte-for-byte copy testing easier.

6. **Make clipboard failure visible.** The current plan only mentions "Copied!"
   on success. Add a visible "Select the text and copy manually" message when
   both `navigator.clipboard.writeText` and the `execCommand` fallback fail,
   which can happen in local-file browser contexts.

7. **Keep browser compatibility expectations realistic.** Unit tests can verify
   generated HTML structure/content, but Chrome/Firefox/Safari clipboard behavior
   from `file://` is a manual smoke-test item unless Playwright/browser tests are
   added. Do not overstate automated coverage.

8. **Do not add persistent checklist state in v1.** Interactive checkboxes are
   useful during a posting session, but storing state in `localStorage` is not
   necessary for the first version and could surprise users opening multiple
   game files. Plain in-page checkboxes are enough.

9. **Update docs and checklist.** If HTML is generated by default, README and
   `NEW_GAME_CHECKLIST.md` should mention the `.html` file as the easiest path
   for copying sections, while still documenting the `.md` fallback.

10. **Design/style — decided.** Use the restrained, local-tool approach:
    no external assets, no decorative imagery, high-contrast text, large copy
    buttons, responsive stacked sections. This is a utility, not a product page.

11. **API shape — decided.** Keep `output_path` on `PublishKitResult` as the
    Markdown path for backward compatibility. Add optional `html_path`. Clean up
    the naming in a later breaking release if needed.

**Implementation constraints:**

1. **Self-contained, no external dependencies.** The HTML file must work when
   opened as a `file://` URL with no internet connection. All CSS and
   JavaScript must be inline. No CDN links, no external fonts.

2. **Clipboard API with fallback.** `navigator.clipboard.writeText()` is the
   modern API but may be blocked on `file://` URLs in some browsers. Include
   a `document.execCommand('copy')` fallback (deprecated but reliable for
   local files). Show a brief "Copied!" confirmation message on the button
   after a successful copy.

3. **No new Python runtime dependencies.** Use `string.Template` or f-strings
   for HTML generation. Do not add Jinja2 or any other templating library.

4. **Plain, functional styling.** The HTML does not need to be beautiful — it
   needs to be clear and usable. A clean two-column or stacked layout with
   large "Copy" buttons is sufficient. Avoid elaborate CSS that would be hard
   to maintain.

5. **Content parity with Markdown.** The chapters and at-bats text must be
   identical to what `export_youtube_chapters` and `export_at_bat_comment`
   produce (including the project credit footer). Do not re-derive the text in
   the HTML generator — pass the already-rendered strings through.

6. **Project credit in the HTML footer.** Include the same MIT license and
   GitHub link that appears in the text exports as an informational page footer,
   while also preserving the credit text inside both copy boxes.

Acceptance criteria:
- `publish-helper` generates `youtube_paste_kit.html` alongside the Markdown
  file by default, with `--no-html` available to suppress HTML generation.
- CLI JSON output clearly reports both the Markdown path and the HTML path when
  HTML is generated.
- The HTML file opens correctly in Chrome, Firefox, and Safari from a
  `file://` URL with no internet connection as a documented manual smoke test.
- Both copy buttons work in all three browsers; a "Copied!" confirmation is
  shown after a successful copy, and a manual-copy message appears if clipboard
  APIs fail.
- The posting checklist is rendered as interactive HTML checkboxes.
- The chapters and at-bats text in the HTML is byte-for-byte identical to the
  corresponding `.txt` export content, including the project credit footer.
- No new runtime dependencies are added to `pyproject.toml`.
- Tests verify that the HTML output contains escaped chapter text, escaped
  at-bat text, both copy buttons, clipboard fallback code, and the checklist.
- The generator function is unit-testable without a browser.
- README and `NEW_GAME_CHECKLIST.md` explain when to open the `.html` file versus
  the `.md` fallback.

### 21. Lineup Strip Fallback for Missing Batter Cards

Source: Product backlog
Status: Done

Use the SidelineHD top-header `batter_number` region as a secondary signal when
the large batter card is missing, blank, or fails to parse.

**Issue observed:**
In the `7Caey7n-4jA` run, the top of the 2nd inning missed the first two
rostered batters. The large batter card did not appear for those at-bats, so the
pipeline emitted one number-only event (`18:35 #7`) and missed `#26` and `#2`
entirely. The top-header lineup strip was present in those frames and would have
recovered the missing batters.

**Design decisions (all questions resolved):**

**Q: Does `batter_number` reliably point at the current highlighted lineup slot?**
The `batter_number` region in the template is a fixed pixel crop
(`x: 0.265, y: 0.111, w: 0.039, h: 0.050`). It was calibrated on one game and
will read whatever is in that position for any video using the same SidelineHD
layout. It is not theme-invariant — a different SidelineHD theme could shift
the lineup strip position. Mitigation: require roster validation before treating
a lineup-sourced number as authoritative. An unrostered number from the lineup
strip is discarded when a roster is available.

**Q: Should `lineup_strip` (full-strip OCR) be added now?**
No. v1 adds only `batter_number` to the default field list. The `batter_number`
region is already tuned (`psm=10`, digit whitelist, scale=6) and already has a
fallback path in `state_from_samples()`. Full lineup-strip parsing (multi-number
text, positional current-batter detection) is deferred until fixed-region OCR
proves insufficient.

**Q: Should lineup-recovered matches count toward batting-half inference?**
No. `infer_batting_half()` scores only `roster_match_source == "name"` hits (named
batter-card OCR). Lineup number matches produce `roster_match_source:
"lineup_number"` — a distinct value that the inference function ignores. This
keeps inference based on the strongest signal only and avoids overconfidence from
the weaker lineup fallback.

**Implementation plan:**

**`cli.py` — `_default_run_fields()`**

Add `"batter_number"` to the default field list:

```python
return _parse_field_list(args.field) or [
    "inning",
    "count",
    "batter_card_name",
    "batter_card_number",
    "batter_number",
]
```

**`state.py` — `state_from_samples()`**

Replace the single `or`-chained fallback with an explicit if/elif/else to track
which source produced the batter number:

```python
batter_card_text = _sample_text(samples_by_field, "batter_card_number")
lineup_text = _sample_text(samples_by_field, "batter_number")

if batter_card_text:
    batter_number = parse_jersey_number(batter_card_text)
    batter_number_source = "batter_card" if batter_number else None
elif lineup_text:
    batter_number = parse_jersey_number(lineup_text)
    batter_number_source = "lineup_strip" if batter_number else None
else:
    batter_number, batter_number_source = None, None

# Detect disagreement when both sources parse successfully to different numbers
batter_number_disagreement = None
if batter_card_text and lineup_text:
    card_num = parse_jersey_number(batter_card_text)
    lineup_num = parse_jersey_number(lineup_text)
    if card_num and lineup_num and card_num != lineup_num:
        batter_number_disagreement = f"batter_card={card_num} lineup={lineup_num}"
```

Store both in `metadata`:

```python
metadata={
    "batter_name": _sample_text(samples_by_field, "batter_card_name"),
    "batter_number_source": batter_number_source,
    "batter_number_disagreement": batter_number_disagreement,
    "fields": {...},
}
```

**`events.py` — new `_is_plausible_batter_source()` helper**

Add a filter that rejects unrostered lineup-strip numbers when a roster is
available. Slot it into `detect_events()` after the existing
`_is_plausible_batter_identity()` check:

```python
def _is_plausible_batter_source(
    state: OverlayState,
    player_name: Optional[str],
    roster: Optional[Roster],
) -> bool:
    """Reject unrostered lineup-strip numbers when a roster is present."""
    if state.metadata.get("batter_number_source") != "lineup_strip":
        return True
    if roster is None:
        return True
    # player_name is set by player_name_for_state() only when the roster matches
    return player_name is not None
```

Add to the condition in `detect_events()`:

```python
and _is_plausible_batter_source(state, player_name, roster)
```

**`events.py` — `roster_match_source_for_state()`**

When the batter number is from the lineup strip and matches the roster, return
`"lineup_number"` instead of `"number"`:

```python
if state.batter_number and roster.name_for_number(state.batter_number):
    source = state.metadata.get("batter_number_source")
    return "lineup_number" if source == "lineup_strip" else "number"
```

**`events.py` — event metadata in `detect_events()`**

Add two new keys to the emitted event:

```python
metadata={
    ...
    "batter_number_source": state.metadata.get("batter_number_source"),
    "batter_number_disagreement": state.metadata.get("batter_number_disagreement"),
},
```

**`review.py` — new review flags**

Add two new flags in `_review_flags()`:

- `lineup-recovered` when `event.metadata.get("batter_number_source") == "lineup_strip"`
- `card-vs-lineup=<detail>` when `event.metadata.get("batter_number_disagreement")` is set

Also suppress `ocr-number=` noise for lineup-recovered roster matches (same
rationale as suppressing it for named-card matches):

```python
if (
    event.metadata.get("roster_match_source") not in {"name", "lineup_number"}
    and event.metadata.get("ocr_player_number")
    and event.player_number != event.metadata.get("ocr_player_number")
):
    flags.append(f"ocr-number={event.metadata['ocr_player_number']}")
```

Acceptance criteria:
- `"batter_number"` is in the default run field list alongside `batter_card_number`.
- When `batter_card_number` is absent or unparseable and `batter_number` is
  present and rostered, the pipeline emits an at-bat with
  `batter_number_source: "lineup_strip"` in its metadata.
- When `batter_card_number` is present and parseable, it takes priority; the
  lineup strip number is recorded only in `batter_number_disagreement` if it
  differs.
- Named batter-card roster matches (`roster_match_source: "name"`) are never
  overridden by the lineup strip.
- `roster_match_source_for_state()` returns `"lineup_number"` for roster matches
  sourced from the lineup strip.
- `infer_batting_half()` scoring is unchanged: only `"name"` source events
  count; `"lineup_number"` events do not.
- Unrostered lineup numbers are not emitted as at-bat events when a roster is
  provided.
- Review report shows `lineup-recovered` flag for lineup-sourced events.
- Review report shows `card-vs-lineup=batter_card=N lineup=M` flag when both
  sources parse to different numbers.
- `ocr-number=` flag is suppressed for `"lineup_number"` source matches (same
  as for `"name"` source).
- Tests cover:
  - missing batter card (`batter_card_number` absent) recovered from rostered
    `batter_number`;
  - unrostered `batter_number` is not emitted when roster is provided;
  - present `batter_card_number` takes priority; lineup fallback does not fire;
  - named batter-card match not overridden by conflicting lineup number;
  - `batter_number_disagreement` metadata set when both sources differ;
  - `roster_match_source_for_state()` returns `"lineup_number"` for lineup match;
  - `infer_batting_half()` does not count `"lineup_number"` matches.

### 26. Multi-Layout Template Support

Source: Product backlog
Status: Ready for Review

Support all 10 SidelineHD stream styling combinations via named template files,
plus a small code fix so Minimal-style layouts (name badge only, no batter
number) work correctly with the activity signal gate.

**Background — overlay layout variants:**

SidelineHD's Stream Styling settings produce 10 distinct burned-in overlay
layouts. The current template (`sidelinehd_640x360_active.example.json`) covers
only one: Default style, Bottom scoreboard position, Flip player card ON.

The 10 variants come from two axes:

**Style axis — Default vs Minimal:**

- *Default*: Full scorebug block (teams, scores, inning, count, diamonds,
  lineup strip "12 24 88 14") plus a large batter card with player photo,
  name, jersey number, and batting stats (Bats/Throws/Class).
- *Minimal*: A thin single-line scorebug bar (teams, scores, inning, count,
  outs) plus a small name-only badge for the current batter. No photo, no
  number, no lineup strip.

**Position/flip axis:**

| Style   | Scoreboard Position | Flip | Batter card corner     |
|---------|---------------------|------|------------------------|
| Default | Bottom (full-width) | ON   | Bottom-left ← CURRENT  |
| Default | Bottom (full-width) | OFF  | Bottom-right           |
| Default | Top (full-width)    | ON   | Bottom-left            |
| Default | Top (full-width)    | OFF  | Bottom-right           |
| Default | Bottom Left (block) | N/A  | Bottom-right           |
| Default | Top Right (block)   | N/A  | Top-left               |
| Minimal | Bottom              | ON   | Bottom-left            |
| Minimal | Bottom              | OFF  | Bottom-right           |
| Minimal | Top                 | ON   | Top-right              |
| Minimal | Top                 | OFF  | Top-left               |

Batter card corners for Default + Top layouts and Minimal layouts should be
verified with `template-guide` before use — the table above reflects the most
likely positions based on the SidelineHD settings preview, but pixel-level
confirmation requires actual game footage.

**What changes between layouts:**

*Between Default variants:*
- `batter_card`, `batter_card_name`, `batter_card_number` regions shift corner.
- `scorebug_full`, `inning`, `count`, `left_score`, `right_score` shift
  between full-width strip and compact block.
- `lineup_strip`, `batter_number`, `on_deck_number` shift with the scorebug.

*Default vs Minimal:*
- Minimal templates omit `batter_card_number`, `lineup_strip`, `batter_number`,
  `on_deck_number` (these are not present in the Minimal overlay).
- `batter_card_name` in Minimal covers the small name badge, not a card.
- The scorebug regions cover the thin bar, not the wider block.

**Code change — activity signal for Minimal layouts:**

`_has_half_inning_activity_signal()` currently only returns `True` when
`_is_plausible_batter_state(state)` passes, which requires `state.batter_number`
to be set. In Minimal mode `state.batter_number` is always `None` (no number
in the overlay), so the pregame-guard would never clear and the first inning
chapter would be suppressed when running from `--start 0:00`.

Fix: extend the function to also accept a plausible player name as an activity
signal. A name-only batter badge appearing on screen is equally valid evidence
that the game is live.

```python
def _has_half_inning_activity_signal(state: OverlayState) -> bool:
    if _is_plausible_batter_state(state):
        return True
    batter_name = state.metadata.get("batter_name")
    return bool(batter_name and _looks_like_player_name(str(batter_name)))
```

This is the only code change required. No other pipeline logic needs updating:
- `player_name_for_state()` already handles name-only states.
- `player_number_for_state()` already falls back to roster lookup by name.
- `_is_plausible_batter_identity()` already takes the `player_name` path when
  `state.batter_number` is `None` (lines 395–399 in events.py).
- `_confirmed_batter_identity()` works correctly with name-only states.

Minimal layouts without a roster will produce no at-bat events (acceptable:
the tool is designed for rostered use).

**Template naming scheme:**

Twelve template files total (current one plus 9 new):

```
examples/sidelinehd_640x360_active.example.json    ← existing, do not rename
examples/sidelinehd_default_bottom_noflip.example.json
examples/sidelinehd_default_top_flip.example.json
examples/sidelinehd_default_top_noflip.example.json
examples/sidelinehd_default_bottomleft.example.json
examples/sidelinehd_default_topright.example.json
examples/sidelinehd_minimal_bottom_flip.example.json
examples/sidelinehd_minimal_bottom_noflip.example.json
examples/sidelinehd_minimal_top_flip.example.json
examples/sidelinehd_minimal_top_noflip.example.json
```

The `sidelinehd_640x360_active.example.json` file is kept as-is for backward
compatibility. A `NOTE` field in each new template identifies which SidelineHD
settings it matches.

**Template skeleton format for new files:**

Each new template ships with `TODO` placeholders in the `notes` field and
approximate coordinates derived by mirroring the calibrated Default-Bottom-Flip
template. Example for `sidelinehd_default_bottom_noflip.example.json`:

```json
{
  "name": "sidelinehd_default_bottom_noflip",
  "video_width": 640,
  "video_height": 360,
  "regions": {
    "inning": { "x": ..., ... },
    "count": { "x": ..., ... },
    "batter_card_name": { "x": ..., ... },
    "batter_card_number": { "x": ..., ... },
    "lineup_strip": { "x": ..., ... },
    "batter_number": { "x": ..., ... },
    "on_deck_number": { "x": ..., ... }
  },
  "notes": "SidelineHD settings: Default style, Bottom scoreboard, Flip OFF. SKELETON — verify all regions with template-guide before first use."
}
```

Minimal templates omit the four regions not present in that overlay style.

**Calibration workflow for new templates:**

Skeleton templates ship with mirrored/estimated coordinates. Each must be
verified against real footage using the existing `template-guide` command:

```sh
sidelinehd-extractor template-guide path/to/game.mp4 scratch/guide.png \
  --template examples/sidelinehd_default_bottom_noflip.example.json \
  --timestamp 10:00
```

Adjust fractional coordinates until the guide overlays align, then commit the
validated template. Ryan must validate templates he actually uses.

**README additions:**

- New "Template Selection" section listing the 10 layouts in a table, matching
  each to its template file and the corresponding SidelineHD settings page
  selections (Style, Scoreboard Position, Flip toggle).
- Note that skeleton templates require calibration before first use.

Acceptance criteria:
- `_has_half_inning_activity_signal()` returns `True` for states with a
  plausible player name even when `batter_number` is `None`.
- 9 new skeleton template files exist in `examples/`, one per layout variant
  not covered by the existing calibrated template.
- Each skeleton template includes a `notes` field identifying the SidelineHD
  settings it matches and a calibration reminder.
- Minimal templates do not include `batter_card_number`, `lineup_strip`,
  `batter_number`, or `on_deck_number` regions.
- README "Template Selection" section maps all 10 SidelineHD layout
  combinations to template files.
- Tests cover:
  - `_has_half_inning_activity_signal()` returns `True` for a name-only state
    with a plausible player name;
  - `_has_half_inning_activity_signal()` returns `False` for a state with
    neither a batter number nor a plausible player name;
  - existing batter-number activity signal test still passes.

### 27. Interactive Roster Setup (`setup-roster`)

Source: Product backlog
Status: Done

Add an interactive `setup-roster` command that guides a user through pasting
their roster and writing it to `rosters/<team-slug>.csv` — no text file
required, no path to remember, no silent parse failures.

This is the v1 of what Codex proposed. The v2 (project config defaults so
`--roster` and `--template` can be omitted entirely) is a separate design
problem involving a stdlib version question and is tracked as item 28.

**Why now:** Roster quality directly improves batting-half inference, OCR
correction, and lineup-strip fallback safety (items 17 and 21). Lowering the
barrier to creating and maintaining a good roster has compounding value.

**Design decisions (all open questions resolved):**

**Terminator:** Two consecutive blank lines OR EOF (Ctrl+D / Ctrl+Z). Print
clear instructions. A single accidental Enter while pasting doesn't terminate
early. No custom sentinel needed.

**Duplicate numbers:** Refuse to write. `parse_team_list()` already raises
`ValueError` with the line number — surface that message as-is and exit 1.

**Invalid lines:** Fail the whole roster and show the bad line. Same reason:
a partial roster is worse than no roster.

**Non-interactive (piped stdin):** Detect with `sys.stdin.isatty()`. When not
a TTY, read all of stdin and skip the name prompt (require `--team-name`),
skip preview and confirmation, write directly. This makes the command
testable and scriptable without fighting interactive mocks.

**No config file writing in v1.** See item 28.

**`.gitignore`:** Add `rosters/` — real rosters contain player names and must
not be committed to a public repo.

**Implementation plan:**

**`.gitignore`**

Add `rosters/` to the local-generated-artifacts block alongside `runs/` and
`scratch/`.

**`roster.py` — new `default_roster_path()` helper**

```python
def default_roster_path(team_name: str) -> Path:
    """Return the default roster path for a team name."""
    from sidelinehd_extractor.naming import slugify
    return Path("rosters") / f"{slugify(team_name)}.csv"
```

**`cli.py` — `_cmd_setup_roster(args)`**

```python
def _cmd_setup_roster(args: argparse.Namespace) -> int:
    is_tty = sys.stdin.isatty()

    # Step 1: team name
    team_name = args.team_name
    if not team_name:
        if not is_tty:
            print("Error: --team-name is required when stdin is not a terminal.", file=sys.stderr)
            return 1
        team_name = input("Team name: ").strip()
        if not team_name:
            print("Error: team name is required.", file=sys.stderr)
            return 1

    # Step 2: roster lines
    if is_tty:
        print("Paste your roster lines (#number Name). Press Enter twice when done:")
        lines = _read_roster_lines_interactive()
    else:
        lines = sys.stdin.read().splitlines()

    if not any(line.strip() for line in lines):
        print("Error: no roster lines entered.", file=sys.stderr)
        return 1

    # Step 3: parse
    try:
        roster = parse_team_list("\n".join(lines), team_name=team_name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Step 4: preview (TTY only)
    if is_tty:
        _print_roster_preview(roster)

    # Step 5: confirm (TTY only)
    output_path = args.output or default_roster_path(team_name)
    if is_tty:
        response = input(f"\nWrite {len(roster.players)} players to {output_path}? [Y/n] ").strip().lower()
        if response and response not in {"y", "yes"}:
            print("Cancelled.", file=sys.stderr)
            return 1

    # Step 6: write
    result = write_roster_csv(roster, output_path)
    print(f"Wrote {result.player_count} players to {result.output_path}")
    if is_tty:
        print(f"\nUse your roster:")
        print(f"  sidelinehd-extractor run-youtube 'YOUTUBE_URL' --roster {result.output_path} --template YOUR_TEMPLATE")
    return 0
```

`_read_roster_lines_interactive()` reads with `input()` in a loop, tracking
consecutive blank lines. Two in a row = done; EOFError = done. Returns
`List[str]`.

`_print_roster_preview(roster)` prints a column-aligned table to stdout. Compute
column widths from the data; no external libraries. Example output:

```
 # | Name       | Aliases
---+------------+--------
 2 | Emma B.    | Emma
26 | Amelia V.  | Amelia
```

**`cli.py` — `setup-roster` subparser**

```python
setup_roster = subparsers.add_parser(
    "setup-roster",
    help="Interactively paste a team roster and save it to rosters/.",
)
setup_roster.add_argument("--team-name", help="Team name (required when stdin is not a terminal).")
setup_roster.add_argument("--output", "-o", type=Path, help="Override the default output path.")
setup_roster.set_defaults(func=_cmd_setup_roster)
```

Acceptance criteria:
- `setup-roster` (TTY): prompts for team name, reads lines, shows preview,
  confirms, writes `rosters/<slug>.csv`.
- `setup-roster --team-name "X"` with piped stdin: reads stdin, writes directly,
  no preview or confirmation.
- Generated CSV passes `load_roster()` without error.
- Duplicate jersey numbers → error on stderr, no file written, exit 1.
- Invalid line → error on stderr with line number, no file written, exit 1.
- Empty input → error on stderr, exit 1.
- `--output` overrides the default path.
- `rosters/` added to `.gitignore`.
- `make-roster` is unchanged.
- `default_roster_path()` is exported from `roster.py` and unit-tested.
- Tests cover: piped happy-path write, duplicate number rejection, invalid line
  rejection, empty input rejection, default path slug, `--output` override,
  next-command text in TTY output.
- README "Quick Start" and `NEW_GAME_CHECKLIST.md` mention `setup-roster` as
  the preferred first-run path.

### 28. Project Config Defaults (`sidelinehd.cfg`)

Source: Product backlog
Status: Ready for Review

Allow users to set `roster` and `template` once per working directory so every
`run-youtube` call only needs the URL. This is the v2 of what Codex proposed
in item 27.

**Design decisions (all open questions resolved):**

**Format: INI via `configparser` (stdlib, no new dependencies).** The alternative
was TOML: `tomllib` is only in stdlib from Python 3.11+, our target is 3.10
(item 19), and adding `tomli` as a runtime dependency for a file with 3 string
values is disproportionate. `configparser` works on Python 3.9+, is rock-solid,
and the format is universally readable. If the config ever needs complex types,
a migration at that point is the right call — not now.

**File name: `sidelinehd.cfg`** in the current working directory. Not hidden —
`.`-prefix files are invisible in macOS Finder and Windows Explorer, which
matters for a tool whose primary user is not a developer.

**Section and keys:** One section (`[defaults]`) with three keys: `roster`,
`template`, `team_name`. No separate `[team]` section — the flat `[defaults]`
layout is easier to explain and edit.

**Both `roster` and `template` are config keys.** This is the whole point:
after first-run setup, `sidelinehd-extractor run-youtube 'URL'` should work
with no flags. `team_name` is included for the `publish-helper` label.

**`setup-roster` integration:** After writing the roster in TTY mode,
`setup-roster` (item 27) checks `sidelinehd.cfg`:
- If no config file exists: offer to create it with `roster = <written path>`
  and prompt for the template path. Default [Y/n].
- If the file exists but has a different roster: offer to update the roster key.
- If the file already has the same roster: print nothing (already set).

**Gitignore: YES.** Add `sidelinehd.cfg` to `.gitignore`. The config file
contains local absolute-ish paths that won't work on another machine. Ship
`examples/sidelinehd.example.cfg` as the copyable template.

**Missing file:** Silent — no error, no warning. The config feature is
transparent; users who never create the file see no difference.

**Unknown keys:** Silently ignored (forward compatibility).

**Bad values:** Warn to stderr, skip the bad key, continue. Do not crash.

**Precedence:** CLI flag > config file > built-in default. Never reverse this.

**Implementation plan:**

**`sidelinehd.cfg` (gitignored, not committed)**

Example user-created file:
```ini
[defaults]
roster   = rosters/smash-it-sports-12u.csv
template = examples/sidelinehd_640x360_active.example.json
team_name = Smash It Sports 12U
```

**`examples/sidelinehd.example.cfg` (committed to repo)**

```ini
# sidelinehd.cfg — local project config (this file is gitignored)
# Copy to sidelinehd.cfg at the repo root and fill in your paths.
# CLI flags always override these defaults.

[defaults]
roster   = rosters/your-team-name.csv
template = examples/sidelinehd_640x360_active.example.json
# team_name = Your Team 12U
```

**`.gitignore`**

Add `sidelinehd.cfg` to the local-generated-artifacts block.

**New module: `src/sidelinehd_extractor/config.py`**

```python
import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CONFIG_FILENAME = "sidelinehd.cfg"
_SECTION = "defaults"

@dataclass(frozen=True)
class ProjectConfig:
    roster: Optional[Path] = None
    template: Optional[Path] = None
    team_name: Optional[str] = None

def load_project_config(cwd: Optional[Path] = None) -> ProjectConfig:
    """Load sidelinehd.cfg from cwd; return empty config if absent."""
    path = (cwd or Path.cwd()) / CONFIG_FILENAME
    if not path.exists():
        return ProjectConfig()
    parser = configparser.ConfigParser()
    parser.read(str(path), encoding="utf-8")
    if _SECTION not in parser:
        return ProjectConfig()
    section = parser[_SECTION]
    roster_str = section.get("roster")
    template_str = section.get("template")
    team_name = section.get("team_name") or None
    return ProjectConfig(
        roster=Path(roster_str) if roster_str else None,
        template=Path(template_str) if template_str else None,
        team_name=team_name,
    )

def write_project_config(config: ProjectConfig, cwd: Optional[Path] = None) -> Path:
    """Write config to sidelinehd.cfg in cwd, overwriting if present."""
    path = (cwd or Path.cwd()) / CONFIG_FILENAME
    parser = configparser.ConfigParser()
    parser[_SECTION] = {}
    if config.roster is not None:
        parser[_SECTION]["roster"] = str(config.roster)
    if config.template is not None:
        parser[_SECTION]["template"] = str(config.template)
    if config.team_name:
        parser[_SECTION]["team_name"] = config.team_name
    with path.open("w", encoding="utf-8") as f:
        parser.write(f)
    return path
```

`write_project_config` is used by both `setup-roster` (item 27 integration)
and any future `setup-defaults` or config-editing command.

**`cli.py` — `_apply_config_defaults(args)`**

```python
def _apply_config_defaults(args: argparse.Namespace) -> None:
    """Apply sidelinehd.cfg values where the user did not pass a CLI flag."""
    from sidelinehd_extractor.config import load_project_config
    config = load_project_config()
    if not getattr(args, "roster", None) and config.roster:
        args.roster = config.roster
    if not getattr(args, "template", None) and config.template:
        args.template = config.template
    if not getattr(args, "team_name", None) and config.team_name:
        args.team_name = config.team_name
```

Called at the start of each handler that uses these args:

| Command | Reads from config |
|---|---|
| `run-game` | `roster`, `template` |
| `run-youtube` | `roster`, `template` |
| `process` | `template` |
| `detect-events` | `roster` |

Commands that do NOT read config: `export`, `publish-helper`, `review-events`,
`review-report`, `setup-roster`, `make-roster`, `template-guide`,
`calibration-frames`, `ocr-image` — they are downstream or utility tools
that don't take `--roster`/`--template`.

**`setup-roster` integration in `cli.py` (`_cmd_setup_roster`)**

After writing the roster (step 6), in TTY mode:

```python
if is_tty:
    _offer_config_update(result.output_path)
```

```python
def _offer_config_update(roster_path: Path) -> None:
    from sidelinehd_extractor.config import (
        CONFIG_FILENAME, load_project_config, write_project_config, ProjectConfig
    )
    existing = load_project_config()
    if existing.roster == roster_path:
        return  # already set, say nothing
    verb = "Update" if Path(CONFIG_FILENAME).exists() else "Create"
    response = input(f"\n{verb} {CONFIG_FILENAME} to use this roster by default? [Y/n] ").strip().lower()
    if response and response not in {"y", "yes"}:
        return
    template = existing.template
    if not template:
        template_input = input("Template path (Enter to skip): ").strip()
        template = Path(template_input) if template_input else None
    updated = ProjectConfig(
        roster=roster_path,
        template=template,
        team_name=existing.team_name,
    )
    written = write_project_config(updated)
    print(f"Wrote {written}")
```

Acceptance criteria:
- `load_project_config()` returns empty `ProjectConfig` when `sidelinehd.cfg`
  is absent.
- `load_project_config()` returns correct `Path` values for `roster` and
  `template` when the file exists.
- `load_project_config()` silently ignores missing `[defaults]` section.
- Unknown keys in `[defaults]` are silently ignored.
- `write_project_config()` round-trips: written file parses back to same values.
- `_apply_config_defaults()` applies config values when the corresponding arg
  is `None`; does NOT override an arg that was explicitly passed.
- `run-youtube 'URL'` with `sidelinehd.cfg` present uses config roster and
  template without requiring flags.
- `run-youtube 'URL' --roster other.csv` still uses the explicit flag, not config.
- `setup-roster` offers to create/update config after writing the roster (TTY
  mode only); skips silently if config already has the same roster.
- `sidelinehd.cfg` added to `.gitignore`; `examples/sidelinehd.example.cfg`
  committed to repo.
- Tests cover: load absent file, load valid file, load file with unknown keys,
  round-trip write/load, `_apply_config_defaults` precedence (config vs CLI
  flag), `_apply_config_defaults` when args lack the attribute.
- README "Quick Start" updated to mention `sidelinehd.cfg` after showing
  `setup-roster`. Show the one-liner result: `sidelinehd-extractor run-youtube 'URL'`
  with no flags once config is in place.

Implementation note:
- Added `ProjectConfig`, `load_project_config()`, and `write_project_config()` to
  `config.py`.
- Added `sidelinehd.cfg` to `.gitignore` and committed
  `examples/sidelinehd.example.cfg`.
- Added `_apply_config_defaults()` and wired config defaults into `run-game`,
  `run-youtube`, `process` (template only), and `detect-events` (roster only).
- Interactive `setup-roster` now offers to create/update `sidelinehd.cfg` after
  writing the roster.
- README and `NEW_GAME_CHECKLIST.md` document the one-flagless
  `run-youtube 'URL'` flow after setup.
- Tests cover absent/valid/missing-section/bad-path config loads, round-trip
  writes, CLI precedence, missing-attribute safety, run-youtube config usage, and
  setup-roster config creation.

### 29. Score at Inning Transitions

Source: Product backlog
Status: Done (Pass 9, commit d8b3b40)

Record the score at each half-inning start and include it in chapter labels by
default, so YouTube chapters read `10:00 Top 3 (2-1)` instead of `10:00 Top 3`.
On by default; `--no-inning-score` suppresses it.

**Background:**

`OverlayState` already has `home_score` and `away_score` fields and the model
has a `SCORE_CHANGE` event type, but scores are never sampled or populated.
`FIELD_CONFIGS` in `ocr.py` has tuned configs for `left_score` and `right_score`
(PSM 10, digit whitelist, scale 6) and the example template defines both
regions. The plumbing exists; it just needs to be wired up.

**Scorebug convention:** SidelineHD always places the away team on the left and
the home team on the right. This is set at game creation in the app and is
enforced by the scoring mode (pitching vs batting). The OCR crop fields keep
their positional names (`left_score`, `right_score`) since they describe crop
geometry, but the semantic mapping is now known: `left_score` → `away_score`,
`right_score` → `home_score`. The `OverlayState` fields are named accordingly.

**Known limitation:** If the home/away assignment is corrected mid-game in the
SidelineHD app (wrong setup at game start, then fixed), the scorebug sides will
flip at the correction point. The OCR numbers remain accurate, but
`away_score`/`home_score` labeling in metadata will be inverted for events
before the correction. There is no reliable way to detect this from the overlay
alone. The mitigation is correct game setup before the first pitch.

**What changes:**

**`cli.py` — `_default_run_fields()`**

Add `"left_score"` and `"right_score"` to the default field list:

```python
return _parse_field_list(args.field) or [
    "inning",
    "count",
    "left_score",
    "right_score",
    "batter_card_name",
    "batter_card_number",
    "batter_number",
]
```

**`state.py` — `parse_score()` and `state_from_samples()`**

Add a score parser alongside the existing number/count parsers:

```python
def parse_score(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r'\d+', value)
    return int(match.group(0)) if match else None
```

In `state_from_samples()`, apply the away-left / home-right convention:

```python
away_score = parse_score(_sample_text(samples_by_field, "left_score"))
home_score = parse_score(_sample_text(samples_by_field, "right_score"))
```

Pass them into the `OverlayState` constructor:

```python
return OverlayState(
    ...
    away_score=away_score,
    home_score=home_score,
    ...
)
```

**`events.py` — `_score_snapshot()` and `detect_events()`**

Add a helper that finds the first non-None score pair in the confirmation window.
Taking the first available pair (not just the trigger state) handles the common
case where the trigger state has an OCR gap but adjacent states are readable. Do
not look beyond the confirmation window — the score could change if runs score
early in the half-inning.

```python
def _score_snapshot(
    states: List[OverlayState],
    start_index: int,
    window: int,
) -> tuple:
    for state in states[start_index : start_index + window]:
        if state.away_score is not None and state.home_score is not None:
            return state.away_score, state.home_score
    return None, None
```

When emitting a `HALF_INNING_START` event, add the score to metadata:

```python
away_score, home_score = _score_snapshot(ordered_states, index, half_inning_confirmation_window)
metadata={
    "source": "state_change",
    "away_score": away_score,
    "home_score": home_score,
}
```

**`exports.py` — `export_youtube_chapters()`**

Add `include_score: bool = True` parameter. When True and both score values are
present in event metadata, append `(away-home)` to the chapter label. Sports
scores are conventionally shown away-first, which matches the scorebug left-right
order:

```python
def export_youtube_chapters(events, ..., include_score: bool = True):
    ...
    for event in events:
        label = event.label
        if include_score and event.event_type == EventType.HALF_INNING_START:
            away = event.metadata.get("away_score")
            home = event.metadata.get("home_score")
            if away is not None and home is not None:
                label = f"{label} ({away}-{home})"
        lines.append(f"{format_timestamp(event.timestamp_seconds)} {label}")
```

**`cli.py` — `--no-inning-score` flag**

Add `--no-inning-score` to `run-game`, `run-youtube`, and `export` commands.
Pass `include_score=not args.no_inning_score` to `export_youtube_chapters()`.
The shared `_add_run_processing_arguments()` helper can carry this flag for the
two run commands; `export` wires it independently.

Acceptance criteria:
- `left_score` and `right_score` are in the default run field list.
- `state_from_samples()` maps `left_score` → `away_score` and `right_score` →
  `home_score` on `OverlayState`.
- `HALF_INNING_START` events include `away_score` and `home_score` in metadata;
  both are `None` when OCR was absent for the entire confirmation window.
- Chapter export appends `(away-home)` to each `HALF_INNING_START` line when
  both scores are non-None.
- Chapter export omits the parenthetical when either score is None — no
  placeholder, no interpolation.
- `--no-inning-score` suppresses the score in chapter output.
- Score is not appended to the pregame intro line (`0:00 Pregame`).
- At-bat exports are unchanged.
- Tests cover:
  - `parse_score()` for digits, `#`-prefixed strings, empty/None input;
  - `state_from_samples()` maps left OCR → `away_score`, right OCR → `home_score`;
  - `_score_snapshot()` returns first non-None pair, falls back to `(None, None)`;
  - `detect_events()` stores `away_score`/`home_score` in `HALF_INNING_START` metadata;
  - `export_youtube_chapters()` appends score as `(away-home)` when present;
  - `export_youtube_chapters(include_score=False)` omits score;
  - score absent from all window states → no parenthetical in export.

Implementation note:
- Added score parsing and left/right score mapping in `state.py`.
- Added `_score_snapshot()` and attached `away_score`/`home_score` metadata to
  `HALF_INNING_START` events.
- Chapter exports now append `(away-home)` by default when both scores are
  available; `--no-inning-score` disables this for `run-game`, `run-youtube`,
  and `export`.
- Kept `lineup_strip` in the default run fields while adding `left_score` and
  `right_score`, because recent at-bat detection depends on lineup-strip OCR.
- Focused tests added for score parsing, state mapping, score snapshot selection,
  event metadata, chapter export rendering/suppression, and CLI default fields.

### 30. Originality and Differentiation Audit vs. `jcspeegs/loups`

Source: Engineering hygiene / pre-release
Status: Ready to implement

A closely related project exists: `jcspeegs/loups` (MIT, on PyPI), also built for
fastpitch softball, also using template matching plus EasyOCR to emit YouTube
chapters keyed on batter name and jersey number. We did not start from or reference
its code. But the model assistance used while building ours may have been informed
by training data that included loups, so some convergence could have crept in
without us choosing it.

This is not a licensing concern. MIT permits reuse, and independent creation is not
infringement. The goal is genuine originality: confirm our implementation is our own
in substance, and diverge deliberately wherever a real design choice exists, so the
tool reflects our decisions rather than the obvious-path defaults loups also landed
on.

**Scope:** Audit the core pipeline against what is publicly known about loups,
document where we already differ, and consciously diverge (or record independent
rationale) wherever the two could look alike.

**Already differentiated — document the rationale, no change needed:**

These are real architectural differences in our favor. Capture a short "design
decisions" note in the README or CLAUDE.md so the independent derivation is on
record.

- **Ingestion:** we pull source via yt-dlp; loups operates on a local file argument.
- **State:** we persist run state in JSONL files; loups is stateless with file output.
- **Identity resolution:** we resolve batters through a roster CSV keyed on jersey
  number; loups OCRs the name and number straight off the frame with no roster layer.
- **Target format:** we are specific to the SidelineHD scorebug layout; loups is a
  generic bring-your-own-template model with one bundled team overlay.

**Review for convergence — change where practical, justify where not:**

- **OCR engine choice.** EasyOCR is a common library, so sharing it is not
  significant. Differentiate at the layer around it: our ROI cropping, preprocessing
  (threshold/denoise/upscale), and confidence handling should be our own. Record a
  decision on whether to make the OCR backend pluggable so EasyOCR is a selectable
  option rather than a hard dependency. (Note: we currently use Tesseract, not
  EasyOCR — this is already a material difference.)
- **Frame-of-interest trigger.** loups uses OpenCV template matching as the "this
  frame matters" signal. Confirm that ours keys off the SidelineHD layout-aware ROI
  and scorebug-change detection rather than a generic template image. Document the
  approach.
- **OCR result ordering.** loups sorts detected text left-to-right. If we do the same
  anywhere, note it; prefer targeting known sub-regions of the SidelineHD bug (name
  field, number field) so we read by position rather than sorting a flat result set.
- **Chapter title composition.** The timestamp format is fixed by YouTube, so that is
  not differentiable. For title text: confirm we use roster-resolved canonical names,
  our own handling for unknown or low-confidence numbers, and context loups does not
  include (inning, score state per item 29) so our output is distinct on its face.
- **At-bat boundary logic.** Document how we decide a new at-bat has started (dedup
  window, minimum gap, batter-number change) and confirm it is our own logic, not a
  mirror of loups's first-match/threshold approach.
- **CLI surface.** Flag names, command structure, and defaults should be ours. Avoid
  matching loups's `-t / -o / -q / --debug` arrangement or its options-before-positional
  ordering by coincidence. A quick diff of help output against loups's documented flags
  is enough.
- **Thumbnail feature (if we add one).** loups does SSIM first-match thumbnail
  extraction. If we want thumbnails, pick a different strategy (e.g., best-scoring
  frame across a window, or a roster/event-driven pick) rather than copying first-match
  SSIM.

Acceptance criteria:
- Side-by-side comparison table (ours vs. loups) committed to `docs/` covering:
  ingestion, trigger mechanism, OCR layer, identity resolution, state, output
  composition, CLI.
- Every "review for convergence" point above is resolved as either *diverged* (with the
  change made) or *retained* (with a one-line independent rationale).
- No file, function, or comment in our repo reproduces loups naming or structure.
  Confirm we have never vendored or pasted any loups source.
- A short "Prior art and independence" note added to the README acknowledging loups
  exists, stating we built independently, and summarizing how the implementations
  differ.
- Decision recorded on OCR-backend abstraction (do it now / defer / decline) with
  reasoning.

Notes:
- loups is explicitly designed to accept custom templates. If open-sourcing, a
  friendly path is to contribute a SidelineHD template/recipe upstream rather than
  position as a competitor. Optional — not part of this item's acceptance criteria.
- Worth a one-time read of how loups handles OCR confidence filtering and text sorting
  before finalizing ours, purely to make informed *different* choices, not to copy.

### 31. Tiered At-Bat Spacing Gate by Signal Confidence

Source: CR-24 follow-up
Status: Done (Pass 6)

`min_at_bat_spacing_roster_confirmed_seconds` parameter added to `detect_events()`, `run_game()`, `run_youtube_game()`, and both CLI detection commands (`run-game`, `run-youtube`, `detect-events`). Roster-confirmed signals use the lower 20-second floor; unconfirmed signals keep the original 45-second floor. Detection spacing settings written to `manifest.json`. 153 tests pass.

The current 45-second minimum spacing is calibrated for unconfirmed detections and can suppress legitimate short at-bats in fast innings. On a real 2nd inning, four rostered at-bats were missed at 30–50 second spacing.

**Design decisions (all questions resolved):**

**How the tiers work:** `roster_match_source` is already computed at line 155 of `events.py` — before the spacing check at line 166. The tier is derivable from this value without any new state.

Three tiers:
- `"name"` — roster-name match from batter-card OCR: allow 20 seconds
- `"lineup_number"` or `"number"` — rostered number match (card or lineup): allow 25 seconds
- `None` or anything else — unrostered/noisy: keep 45 seconds (the current default)

**New parameter:** Add `min_at_bat_spacing_roster_confirmed_seconds: float = 20.0` to `detect_events()` and `detect_events_file()`. This is the floor for both name-confirmed and number-confirmed tiers. A single param is enough: name-confirmed events are almost always also number-confirmed, so two sub-tiers add complexity without measurable benefit. The existing `min_at_bat_spacing_seconds` remains the unrostered floor.

**Implementation plan:**

**`events.py` — helper and `detect_events()` signature**

```python
def _at_bat_spacing_for_roster_match(
    roster_match_source: Optional[str],
    min_spacing_seconds: float,
    min_spacing_roster_confirmed_seconds: float,
) -> float:
    if roster_match_source in {"name", "number", "lineup_number"}:
        return min_spacing_roster_confirmed_seconds
    return min_spacing_seconds
```

Add parameter to `detect_events()`:

```python
def detect_events(
    states: Iterable[OverlayState],
    roster: Optional[Roster] = None,
    batting_half: Optional[HalfInning] = None,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
    ...
) -> List[Event]:
```

In the detection loop, replace the `_has_minimum_at_bat_spacing` call:

```python
spacing = _at_bat_spacing_for_roster_match(
    roster_match_source,
    min_at_bat_spacing_seconds,
    min_at_bat_spacing_roster_confirmed_seconds,
)
and _has_minimum_at_bat_spacing(
    state.timestamp_seconds,
    last_at_bat_timestamp,
    spacing,
)
```

Note: `roster_match_source` is already computed before this check (line 155), so no reordering needed.

**`detect_events_file()` — mirror the new parameter:**

```python
def detect_events_file(
    ...,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
) -> EventDetectionResult:
    ...
    return detect_events(
        ...,
        min_at_bat_spacing_seconds=min_at_bat_spacing_seconds,
        min_at_bat_spacing_roster_confirmed_seconds=min_at_bat_spacing_roster_confirmed_seconds,
    )
```

**`cli.py` — new flag on `run-game`, `run-youtube`, `detect-events`**

Add to the shared spacing argument block (near the existing `--min-at-bat-spacing`):

```python
parser.add_argument(
    "--min-at-bat-spacing-roster-confirmed",
    type=float,
    default=20.0,
    dest="min_at_bat_spacing_roster_confirmed",
    metavar="SECONDS",
    help=(
        "Minimum seconds between at-bats when the new batter is roster-confirmed. "
        "Default: 20."
    ),
)
```

Pass to detection:

```python
min_at_bat_spacing_roster_confirmed_seconds=args.min_at_bat_spacing_roster_confirmed,
```

**Stored in `manifest.json`:** The existing manifest already stores `min_at_bat_spacing_seconds`. Add `min_at_bat_spacing_roster_confirmed_seconds` alongside it so runs are reproducible.

Acceptance criteria:
- `detect_events()` accepts `min_at_bat_spacing_roster_confirmed_seconds` (default 20.0).
- Roster-confirmed candidates (`roster_match_source` in `{"name", "number", "lineup_number"}`) use the lower threshold; all others use `min_at_bat_spacing_seconds`.
- `--min-at-bat-spacing-roster-confirmed` flag available on `run-game`, `run-youtube`, and `detect-events`.
- Tests cover:
  - Two at-bats 22 s apart, name-confirmed → both emitted.
  - Two at-bats 22 s apart, unrostered → second suppressed.
  - Two at-bats 22 s apart, name-confirmed, explicit `--min-at-bat-spacing-roster-confirmed 30` → second suppressed.
  - `_at_bat_spacing_for_roster_match()` unit-tested for all three tier values.
- Previously validated games produce comparable or better at-bat lists (manual regression check).

### 32. Batting-Order Continuity Validator

Source: Product backlog (CR-24 observation)
Status: Done (Pass 8, commit b33cc4b)

Implementation note: `infer_batting_cycle()` and `validate_batting_order()` are
implemented as a post-detection pass. The pass infers the first confirmed batting
cycle, synthesizes flagged `inferred-missing` events for 1-2 batter gaps within that
cycle, and flags `possible-substitute` / `out-of-order-candidate` without suppressing
any original OCR-detected events. `detect-events`, `run-game`, and `run-youtube` run
the pass by default when a roster is present; `--no-order-validation` disables it.
For `--batting-half auto`, validation runs after half inference/filtering so the
opponent half cannot seed the cycle. Review output and review reports now pass through
`order_flags`.

2026-07-01 Victor Vipers rerun note: the pass correctly surfaces the second-inning
lineup-substitution area as review work (`possible-substitute`, `out-of-order-candidate`,
close-at-bat flags). Because `#24` was a real substitution inserted after `#4`, the
validator does not suppress or rewrite those at-bats; it leaves the paste output stable
and makes the questionable area visible for human review.

Once a likely batting order is established from confirmed at-bats (e.g. `26 → 2 → 13 → 5 → 4 → 24 → 15 → 3`), the validator has two jobs:

1. **Fill gaps** — when the next confirmed batter is 1–2 positions ahead of expected, the skipped batters are likely missing from OCR. Synthesize inferred AT_BAT_START events for them with `order_flags: ["inferred-missing"]` so they appear in the review report and can be accepted, corrected, or deleted via the corrections CSV. This addresses the missing-batter cases from the Victor Vipers run.

2. **Flag anomalies** — batters appearing more than 2 positions ahead of expected, or appearing at all without being in the inferred cycle, get review flags (`out-of-order-candidate`, `possible-substitute`). No event is ever suppressed.

**Substitution constraint:** Substitutions are valid. A player may replace an existing slot or be inserted between two batters. A player not in the cycle gets `possible-substitute`; a player in the cycle but appearing more than 2 positions ahead gets `out-of-order-candidate`. Neither flag suppresses the event.

---

#### Architecture — new functions in `events.py`

**Public functions:**

```python
def infer_batting_cycle(events: List[Event]) -> List[str]:
    """Return ordered player numbers from the first qualifying seed half-inning."""

def validate_batting_order(
    events: List[Event],
    roster: Optional[Roster] = None,
    tolerance: int = 2,
) -> List[Event]:
    """Post-pass: flag anomalies and synthesize inferred-missing events."""
```

**Internal helper:**

```python
def _infer_seed_info(events: List[Event]) -> Tuple[List[str], Optional[HalfInning]]:
    """Return (cycle, seed_half) — the half the cycle was seeded from."""
```

`infer_batting_cycle()` calls `_infer_seed_info()` and returns only the cycle.

---

#### `_infer_seed_info()` — full logic

A half-inning qualifies if it has ≥ 3 AT_BAT_START events whose `roster_match_source` is in `{"name", "number", "lineup_number"}`. The first such half-inning (earliest `(inning, half)` tuple in sort order) provides the seed.

```python
CONFIRMED_SOURCES = frozenset({"name", "number", "lineup_number"})
MIN_SEED = 3

groups: Dict[Tuple[int, HalfInning], List[str]] = defaultdict(list)
for event in events:
    if (
        event.event_type == EventType.AT_BAT_START
        and event.inning is not None
        and event.half is not None
        and event.player_number
        and event.metadata.get("roster_match_source") in CONFIRMED_SOURCES
    ):
        groups[(event.inning, event.half)].append(event.player_number)

for key in sorted(groups.keys()):
    players = list(dict.fromkeys(groups[key]))  # dedup, preserve order
    if len(players) >= MIN_SEED:
        return players, key[1]  # cycle, seed HalfInning

return [], None
```

`dict.fromkeys()` deduplicates while preserving insertion order. A player who bats twice in a long half-inning (cycle wrap) appears once in the cycle.

---

#### `validate_batting_order()` — full logic

**Setup:**

```python
cycle, seed_half = _infer_seed_info(events)
if len(cycle) < 3 or seed_half is None:
    return list(events)

cycle_len = len(cycle)

# name lookup: from observed events, then roster
number_to_name: Dict[str, str] = {}
for event in events:
    if event.event_type == EventType.AT_BAT_START and event.player_number and event.player_name:
        number_to_name[event.player_number] = event.player_name
# fill from roster for players not yet seen with a name
if roster is not None:
    for num in cycle:
        if num not in number_to_name:
            name = roster.name_for_number(num)
            if name:
                number_to_name[num] = name

# half-inning start timestamps — used as prev_ts at the start of each new half
half_start_ts: Dict[Tuple[int, HalfInning], float] = {}
for event in events:
    if event.event_type == EventType.HALF_INNING_START and event.inning and event.half:
        half_start_ts[(event.inning, event.half)] = event.timestamp_seconds
```

**Tracking state:**

```python
cycle_pos = 0          # next expected position in cycle (modular)
prev_ts: Optional[float] = None   # timestamp reference for inferred event spacing
result: List[Event] = []
```

**Main loop:**

```python
for event in events:
    # Track current half start timestamp for inferred event timing
    if (
        event.event_type == EventType.HALF_INNING_START
        and event.half == seed_half
    ):
        prev_ts = event.timestamp_seconds  # reset to half-inning start
        result.append(event)
        continue

    if (
        event.event_type != EventType.AT_BAT_START
        or event.half != seed_half
        or not event.player_number
    ):
        result.append(event)
        continue

    player_num = event.player_number

    if player_num not in cycle:
        # Possible substitute — not in the inferred cycle
        flags = list(event.metadata.get("order_flags") or [])
        flags.append("possible-substitute")
        result.append(replace(event, metadata={**event.metadata, "order_flags": flags}))
        # Do NOT advance pointer; a sub does not consume a cycle slot
        prev_ts = event.timestamp_seconds
        continue

    actual_pos = cycle.index(player_num)
    forward_skip = (actual_pos - cycle_pos) % cycle_len

    if forward_skip <= tolerance:
        # Within tolerance: synthesize inferred events for any skipped positions
        if forward_skip > 0 and prev_ts is not None:
            gap = event.timestamp_seconds - prev_ts
            for j in range(forward_skip):
                skipped_pos = (cycle_pos + j) % cycle_len
                skipped_num = cycle[skipped_pos]
                ts = prev_ts + gap * (j + 1) / (forward_skip + 1)
                result.append(
                    Event(
                        event_type=EventType.AT_BAT_START,
                        timestamp_seconds=ts,
                        label=format_at_bat_label(
                            skipped_num,
                            number_to_name.get(skipped_num),
                        ),
                        inning=event.inning,
                        half=event.half,
                        player_number=skipped_num,
                        player_name=number_to_name.get(skipped_num),
                        metadata={
                            "roster_match_source": "batting_order",
                            "order_flags": ["inferred-missing"],
                        },
                    )
                )
        # Confirmed event: no order flag
        result.append(event)
        cycle_pos = (actual_pos + 1) % cycle_len

    else:
        # Out of tolerance
        flags = list(event.metadata.get("order_flags") or [])
        flags.append("out-of-order-candidate")
        result.append(replace(event, metadata={**event.metadata, "order_flags": flags}))
        # Still advance the pointer — the player is at-bat regardless
        cycle_pos = (actual_pos + 1) % cycle_len

    prev_ts = event.timestamp_seconds

result.sort(key=lambda e: e.timestamp_seconds)
return result
```

**Key design decisions captured above:**

- **`prev_ts` resets at each HALF_INNING_START for the seed half.** When the first batter of a new half was missed (Bottom 4 starts with #2 instead of #26), `prev_ts` equals the HALF_INNING_START timestamp. The inferred event for #26 gets `ts = half_start_ts + gap/2`, placing it between the half start and the first detected batter.

- **Pointer always advances after out-of-tolerance events.** We still need to track where the cycle is, even when something looks wrong. If we didn't advance, subsequent correct batters would cascade into more out-of-order flags.

- **Substitutes don't advance the pointer.** A substitute takes an at-bat but occupies no cycle slot. The next rostered batter should continue from the same expected position.

- **Inferred events get `roster_match_source="batting_order"`.** This is a new value. `infer_batting_half()` only counts `"name"` matches, so inferred events don't affect half-side inference. `_at_bat_spacing_for_roster_match()` treats unknown sources as unconfirmed (standard spacing). No other code paths are affected.

- **No dedup guard on inferred events.** Inferred events are only synthesized when there is a confirmed gap (forward_skip ≥ 1 within tolerance). Since the confirmed event that triggered the gap is not a duplicate of the inferred event, no dedup is needed.

---

#### `forward_skip` worked example

Cycle: `["26", "2", "13", "5", "4"]`, tolerance: 2.

| cycle_pos | detected | actual_pos | forward_skip | action |
|---|---|---|---|---|
| 0 | 26 | 0 | 0 | no flag, advance to 1 |
| 1 | 13 | 2 | 1 | infer #2 between prev and 13, advance to 3 |
| 3 | 5 | 3 | 0 | no flag, advance to 4 |
| 4 | 26 | 0 | 1 | infer #4 between prev and 26, advance to 1 (wrapped) |
| 1 | 5 | 3 | 2 | infer #2 and #13 between prev and 5, advance to 4 |
| 4 | 2 | 1 | 2 | forward_skip=2: `(1-4+5)%5 = 2` ≤ tolerance — infer #4 and #26, advance to 2 |

Note on the last row: when cycle_pos=4 and actual_pos=1, `(1-4+5)%5 = 2` — this is interpreted as "2 forward skips" (skip #4 at position 4, then #26 at position 0), landing on #2 at position 1. If the cycle were longer and forward_skip > 2, that same situation would be flagged as `out-of-order-candidate` instead.

---

#### Review integration

`_review_flags()` in `review.py` already passes through `order_flags`:

```python
for flag in (event.metadata.get("order_flags") or []):
    flags_by_index[index].append(flag)
```

No change needed. `inferred-missing`, `out-of-order-candidate`, and `possible-substitute` all appear in the flags column of `review-events` and `review-report` output.

Note: `review-report` collects only events with flags. Inferred-missing events always have flags, so they always appear in the report for human review. This is intentional — the reviewer should confirm or correct every inferred at-bat before exporting.

---

#### Pipeline calling sites

**`detect_events_file()`:** Add `order_validation: bool = True` parameter and call after detection:

```python
def detect_events_file(
    states_path,
    output_path=None,
    roster=None,
    batting_half=None,
    min_at_bat_spacing_seconds=45.0,
    min_at_bat_spacing_roster_confirmed_seconds=20.0,
    order_validation: bool = True,   # new
) -> EventDetectionResult:
    ...
    events = detect_events(...)
    if roster is not None and order_validation:
        events = validate_batting_order(events, roster=roster)
    write_jsonl(destination, events)
    ...
```

**`workflow.py` → `run_game()`:** Add `order_validation: bool = True` parameter, thread into `detect_events_file()`.

**CLI (`cli.py`):** Add `--no-order-validation` to `_add_run_processing_arguments()` and to the `detect-events` subparser:

```python
parser.add_argument(
    "--no-order-validation",
    action="store_true",
    dest="no_order_validation",
    help="Skip batting-order continuity validation after event detection.",
)
```

Pass `order_validation=not args.no_order_validation` at each call site.

---

#### Edge cases

- **`prev_ts is None` for the very first at-bat in the seed half** — if no HALF_INNING_START precedes it (e.g., the first event in the file is an AT_BAT_START), no inferred events are generated for the gap. The validator cannot estimate a timestamp without a reference point. Flag `out-of-order-candidate` on the first detected batter if forward_skip > 0.

- **Cycle shorter than 3 players** — no validation, events pass through unchanged. This handles the case where the roster is present but all games were short or OCR never confirmed enough batters.

- **`batting_half="both"` run** — the seed is from one half; events from the other half pass through unchanged. The validator never applies to the other team's at-bats.

- **End of game / incomplete inning** — if the game ends mid-inning without the expected remaining batters, no inferred events are generated for trailing positions since there's no "next confirmed event" to anchor the timing.

- **Inferred events in the corrections CSV** — the user can delete inferred events that are wrong using `delete=true` on the inferred timestamp, or correct the timestamp using `timestamp_seconds`. The `roster_match_source="batting_order"` in the event metadata distinguishes inferred events from OCR-detected ones for correction targeting.

---

#### Acceptance criteria

- `infer_batting_cycle()` returns ordered player numbers from the first half-inning with ≥ 3 confirmed at-bats; returns `[]` if no qualifying half-inning exists.
- `validate_batting_order()` with `tolerance=2`:
  - Expected position (forward_skip=0): no flag, pointer advances.
  - forward_skip 1–2: inferred-missing events synthesized for skipped positions; pointer advances.
  - forward_skip > 2: `out-of-order-candidate` flag added; pointer still advances.
  - Player not in cycle: `possible-substitute` flag added; pointer does not advance.
  - Cycle wraps modularly at end-of-lineup.
  - Inferred events have `roster_match_source="batting_order"` and `order_flags=["inferred-missing"]`.
  - Inferred event timestamps split the gap proportionally between prev_ts and current event.
  - Inferred events use roster name when available; player_name from observed events as fallback.
  - No event is removed or suppressed (all original events remain in output).
  - Output is sorted by timestamp.
- Events from the opposite half pass through unchanged.
- When no cycle is inferred, all events pass through unchanged.
- `validate_batting_order()` is called in `detect_events_file()` when roster is present and `order_validation=True`.
- `--no-order-validation` skips the pass.
- `inferred-missing`, `out-of-order-candidate`, `possible-substitute` flags appear in `review-events` and `review-report` output.
- On `9AaT4645z6s` bottom 4: an inferred-missing event appears for the first batter before the next confirmed batter.
- On the FLX regression run: known 2nd-inning confirmed sequence still exports; inferred events only appear where gaps exist.

#### Tests to add

- `test_infer_batting_cycle_returns_cycle_from_first_qualifying_half`
- `test_infer_batting_cycle_returns_empty_when_insufficient_confirmed_events`
- `test_infer_batting_cycle_ignores_unconfirmed_events`
- `test_infer_batting_cycle_deduplicates_repeated_player`
- `test_validate_batting_order_no_flag_at_expected_position`
- `test_validate_batting_order_synthesizes_inferred_event_for_one_skipped_batter`
- `test_validate_batting_order_synthesizes_two_inferred_events_for_two_skipped_batters`
- `test_validate_batting_order_flags_out_of_order_when_forward_skip_exceeds_tolerance`
- `test_validate_batting_order_flags_possible_substitute_for_unknown_player`
- `test_validate_batting_order_substitute_does_not_advance_pointer`
- `test_validate_batting_order_cycle_wraps_modularly`
- `test_validate_batting_order_inferred_event_uses_roster_name`
- `test_validate_batting_order_inferred_event_splits_gap_proportionally`
- `test_validate_batting_order_inferred_event_uses_half_start_when_first_batter_missing`
- `test_validate_batting_order_opposite_half_events_pass_through`
- `test_validate_batting_order_no_cycle_returns_events_unchanged`
- `test_validate_batting_order_out_of_order_event_still_advances_pointer`
- `test_detect_events_file_calls_order_validation_when_roster_present`
- `test_detect_events_file_skips_order_validation_when_no_roster`
- `test_no_order_validation_flag_skips_pass`

### 33. Full Lineup-Strip Digit-Run Parsing

Source: Product backlog (CR-24 observation)
Status: Done (Pass 6)

`lineup_strip` added to default run fields. `_extract_highlighted_lineup_crop()` in `ocr.py` uses HSV color detection to isolate the active batter chip before OCR (falls back to full-strip OCR if no highlight found). `_resolve_lineup_digit_run()` extracts the single unambiguous rostered number from fused digit strings (e.g. `"265"` → `"26"` when `#26` is rostered and `#5` is not, or returns `None` when ambiguous). State parsing now stores both `lineup_strip_number` (from full strip) and `lineup_batter_number` (from fixed crop) in metadata. `_preferred_lineup_number_for_state()` prefers active lineup over nameless batter-card reads. `_jersey_number_from_text()` handles `#N` OCR artifacts in the batter-name field. 153 tests pass.

When the batter card is absent and the lineup-strip crop OCRs as a fused digit run like `265` or `426`, `_is_plausible_batter_state()` rejects it (jersey numbers longer than 2 digits are invalid). Those fused runs are often two adjacent roster numbers smeared by OCR. With a roster, the correct number can be extracted.

**Root cause in `state.py`:**
`state_from_samples()` calls `parse_jersey_number()` which extracts the first digit run via `re.search(r"\d+", value)`. For `"265"` it returns `"265"`. When this is the only source (`batter_card_number` absent), the state is emitted with `batter_number = "265"`, which `_is_plausible_batter_state()` then rejects because `len("265") > 2`.

**Design decisions (all questions resolved):**

**Resolution happens in `detect_events()`, not `state_from_samples()`.** Roster is not available during state parsing. Rather than plumbing the roster through the parsing layer, add a pre-pass inside `detect_events()` that enriches states with resolved digit-run numbers before the detection loop runs.

**New helper `_resolve_lineup_digit_run(text, roster) -> Optional[str]`** in `events.py`:

```python
def _resolve_lineup_digit_run(text: str, roster: Roster) -> Optional[str]:
    """Find a single rostered number within a fused OCR digit run."""
    import re
    digits = re.sub(r"\D", "", text)
    if len(digits) <= 2:
        return None
    candidates: set[str] = set()
    for length in (1, 2):
        for start in range(len(digits) - length + 1):
            candidate = digits[start : start + length]
            if candidate.lstrip("0") and roster.name_for_number(candidate):
                candidates.add(candidate)
    return candidates.pop() if len(candidates) == 1 else None
```

For `"265"`: checks `"2"`, `"26"`, `"6"`, `"65"`, `"5"`. If only `"26"` is rostered → returns `"26"`. If both `"2"` and `"26"` are rostered → ambiguous → returns `None`.

**New pre-pass `_enrich_states_digit_runs(states, roster) -> List[OverlayState]`** in `events.py`:

```python
def _enrich_states_digit_runs(
    states: List[OverlayState],
    roster: Roster,
) -> List[OverlayState]:
    result = []
    for state in states:
        if (
            state.metadata.get("batter_number_source") == "lineup_strip"
            and state.batter_number
            and len(state.batter_number) > 2
        ):
            resolved = _resolve_lineup_digit_run(state.batter_number, roster)
            if resolved:
                new_meta = dict(state.metadata)
                new_meta["batter_number_digit_run_original"] = state.batter_number
                state = dataclasses.replace(state, batter_number=resolved, metadata=new_meta)
        result.append(state)
    return result
```

Called at the top of `detect_events()`, after sorting, when roster is present:

```python
ordered_states = sorted(states, key=lambda s: s.timestamp_seconds)
if roster is not None:
    ordered_states = _enrich_states_digit_runs(ordered_states, roster)
```

After enrichment, `state.batter_number` is the resolved 1- or 2-digit number. `_is_plausible_batter_state()`, `player_name_for_state()`, and `roster_match_source_for_state()` all work normally. `roster_match_source_for_state()` will return `"lineup_number"` because the resolved number is in the roster and the source is still `"lineup_strip"`.

**Review report:** No new flag needed — `lineup-recovered` already fires for lineup-strip source events. Optionally, if `batter_number_digit_run_original` is set in metadata, `_review_flags()` can add `digit-run-split=<original>` to make the resolution visible. Add this as a low-priority enhancement.

**`manifest.json`:** No change needed. The pre-pass runs in-memory; the enriched state is never written to `states.jsonl`.

Acceptance criteria:
- `_resolve_lineup_digit_run("265", roster)` returns `"26"` when only `"26"` is rostered.
- `_resolve_lineup_digit_run("265", roster)` returns `None` when both `"2"` and `"26"` are rostered (ambiguous).
- `_resolve_lineup_digit_run("265", roster)` returns `None` when no roster number matches.
- `_enrich_states_digit_runs()` replaces 3+-digit lineup-strip numbers with resolved 1- or 2-digit numbers when unambiguous.
- `batter_number_digit_run_original` is stored in state metadata after resolution.
- After enrichment, `_is_plausible_batter_state()` accepts the resolved number and the event is emitted.
- `roster_match_source` on the emitted event is `"lineup_number"` (lineup strip source + rostered number).
- Batter-card source states and already-valid lineup numbers are not affected by the pre-pass.
- When roster is `None`, the pre-pass is skipped entirely.
- Tests cover: fused run with one match → resolved; fused run with two matches → not resolved; fused run with no match → not resolved; ≤2-digit string → no-op; batter-card source state → untouched.

### 34. True Game-Start Detection After Pregame Team-Side Changes

Source: Product QA from `9AaT4645z6s` / Victor Vipers run
Status: Done (Pass 8, commit b33cc4b)

Implementation note: first-half-inning confirmation now uses a window-based game-active
signal when the stream starts at zero. A stable pregame scorebug no longer qualifies on
a plausible batter number alone. The detector waits for one of: a non-zero count
(`balls > 0 or strikes > 0`), a trusted batter change (highlight-confirmed lineup-strip,
named batter card, or old-style lineup-number source). The `0-0` count path was removed
in CR-36 to prevent pregame batter cards with a parsed count from bypassing the gate.
Subsequent half-inning transitions and non-zero-start clips keep the old confirmation
behavior. Against the saved `9AaT4645z6s` states, chapters begin with `0:00 Pregame`
and `6:50 Top 1` instead of `0:00 Top 1`.

Follow-up from the 2026-07-01 `9AaT4645z6s` rerun: restoring the legacy
`lineup_number` source for CR-26 briefly allowed noisy pregame digit changes to qualify
as batter-change activity, producing `0:55 Top 1`. The game-start gate now treats only
highlight-confirmed lineup-strip changes as trusted batter-change activity. Legacy
`lineup_number` remains valid for at-bat detection but no longer starts the first
chapter during pregame.

The Victor Vipers game exposed an assumption around pregame setup: the scoring app initially had Smash It Sports configured as away and Victor Vipers as home, but after the coin toss the teams were swapped before the real game state began. The exported chapters currently start `Top 1` at `0:00`, even though the visible in-game overlay does not show the real first-inning game state until about `6:34`.

Confirmed still present after item 36 rerun: `0:00 Top 1` still appears in the export for `9AaT4645z6s`. The correct chapter start is around `6:34`.

---

#### Root cause

The activity-signal check (`_has_half_inning_activity_signal`) only examines a SINGLE state at the trigger point:

```python
def _has_half_inning_activity_signal(state: OverlayState) -> bool:
    return _is_plausible_batter_state(state)
```

After item 33, the lineup strip's HSV chip detection (`lineup_strip_confidence="lineup_highlight"`) fires on the pregame lineup display and populates `state.batter_number` with the highlighted first batter's jersey number. `_is_plausible_batter_state()` returns True at t=0, even though no pitch has been thrown. The stable `Top 1` overlay clears the confirmation window, and `HALF_INNING_START` is emitted at 0:00.

**The key distinguishing property of real game activity:** the ball-strike count changes from 0-0 once a pitch is thrown, or the batter changes once an at-bat completes. During pregame, the count is stuck at 0-0 and the lineup highlight shows the same first batter for the entire pregame period. These are observably different from the window perspective.

---

#### Architecture — changes to `events.py`

**Remove** `_has_half_inning_activity_signal(state: OverlayState) -> bool`.

**Add** two new functions:

```python
def _window_has_game_active_signal(
    window_states: List[OverlayState],
    half_key: Tuple[int, HalfInning],
) -> bool:
    """Return True if any state in the window shows real game activity.

    A plausible batter number alone is not enough — the pregame lineup
    highlight passes that test after item 33. We also require a non-zero
    ball-strike count (at least one pitch thrown) or a batter-number change
    (at least one at-bat completed) within the confirmation window.
    """
    prev_batter: Optional[str] = None
    for state in window_states:
        if _half_key(state) != half_key:
            continue
        if not _is_plausible_batter_state(state):
            continue
        if (
            state.balls is not None
            and state.strikes is not None
            and (state.balls > 0 or state.strikes > 0)
        ):
            return True
        if prev_batter is not None and state.batter_number and state.batter_number != prev_batter:
            return True
        if state.batter_number:
            prev_batter = state.batter_number
    return False


def _game_active_timestamp(
    states: List[OverlayState],
    start_index: int,
    half_key: Tuple[int, HalfInning],
    window: int,
) -> Optional[float]:
    """Return the timestamp of the first state in the window that satisfies the
    activity signal — the earliest evidence of a real pitch or batter change.

    Used to place the HALF_INNING_START chapter at the moment game activity
    first appeared rather than at the trigger state (which may still be
    pregame). Returns None if no activity signal is found in the window.
    """
    window_states = states[start_index : start_index + window]
    prev_batter: Optional[str] = None
    for state in window_states:
        if _half_key(state) != half_key:
            continue
        if not _is_plausible_batter_state(state):
            continue
        if (
            state.balls is not None
            and state.strikes is not None
            and (state.balls > 0 or state.strikes > 0)
        ):
            return state.timestamp_seconds
        if prev_batter is not None and state.batter_number and state.batter_number != prev_batter:
            return state.timestamp_seconds
        if state.batter_number:
            prev_batter = state.batter_number
    return None
```

**Update** `_confirmed_half_key()` to use the window-based check:

```python
def _confirmed_half_key(
    states: List[OverlayState],
    start_index: int,
    half_key: Tuple[int, HalfInning],
    window: int,
    minimum: int,
    require_activity_signal: bool = False,
) -> bool:
    window_states = states[start_index : start_index + window]
    observations = sum(1 for s in window_states if _half_key(s) == half_key)
    if len(window_states) < minimum:
        confirmed = len(window_states) >= 2 and observations == len(window_states)
    else:
        confirmed = observations >= minimum
    if not confirmed:
        return False
    if require_activity_signal:
        return _window_has_game_active_signal(window_states, half_key)
    return True
```

**Update** the emit site in `detect_events()` to use `_game_active_timestamp` when placing the chapter:

```python
if (
    half_key is not None
    and half_key != last_half_key
    and _is_valid_half_inning_progression(last_half_key, half_key)
    and _confirmed_half_key(
        ordered_states,
        index,
        half_key,
        half_inning_confirmation_window,
        min_half_inning_observations,
        require_activity_signal=last_half_key is None and starts_at_zero,
    )
):
    inning, half = half_key
    chapter_ts = state.timestamp_seconds
    if last_half_key is None and starts_at_zero:
        active_ts = _game_active_timestamp(
            ordered_states, index, half_key, half_inning_confirmation_window
        )
        if active_ts is not None:
            chapter_ts = active_ts
    events.append(
        Event(
            event_type=EventType.HALF_INNING_START,
            timestamp_seconds=chapter_ts,
            label=format_half_inning_label(inning, half),
            inning=inning,
            half=half,
            metadata={"source": "state_change"},
        )
    )
    last_half_key = half_key
```

---

#### How each scenario behaves

**Victor Vipers pregame (the bug):** pregame shows `Top 1`, count=0-0, batter=`#26` (lineup highlight). `require_activity_signal=True`. Window of 12 states (≈60s at 5s sampling) all have count=0-0 and batter unchanged. `_window_has_game_active_signal` returns False. HALF_INNING_START is NOT emitted at 0:00.

At the game start (~6:34), the first pitch changes the count to 0-1. When the trigger window first spans past this count-change state, `_window_has_game_active_signal` returns True. `_game_active_timestamp` returns the timestamp of the 0-1 count state. HALF_INNING_START emitted near 6:34. The export automatically adds `0:00 Pregame` because the first chapter is not at 0:00. ✓

**Mid-game stream start (already active at 0:00):** the first sampled state is mid-at-bat with a non-zero count. `_window_has_game_active_signal` returns True immediately. `_game_active_timestamp` returns a timestamp near 0:00. Chapter placed near 0:00. ✓

**Very fast first at-bat (first-pitch out, count never sampled non-zero):** a different batter appears within the window. `_window_has_game_active_signal` returns True via the batter-change criterion. ✓

**Subsequent half-inning transitions:** `last_half_key is not None`, so `require_activity_signal=False`. Window activity check not invoked. Behavior unchanged. ✓

**`--start 10:00` run (not zero-starting):** `starts_at_zero=False`, `require_activity_signal=False`. Window activity check never invoked. Behavior unchanged. ✓

---

#### Edge cases

- **Window spans the game-start boundary:** the trigger fires at t=334s (window reaches t=394s). If the first non-zero count is at t=399s, `_game_active_timestamp` returns 399s. The chapter is emitted near 6:39, not at 0:00 or at the 5:34 trigger. Within sampling-resolution error of the real game start — good enough for a chapter marker.

- **Template without count fields:** if `balls` and `strikes` are not OCR'd, both are always `None`. The non-zero-count criterion never fires; only the batter-change criterion gates the activity signal. If the lineup highlight is stable throughout pregame (same batter displayed), the first chapter is correctly deferred until a batter change is sampled. If count is needed for tighter detection, add `count` to the field list.

- **Game where count is always 0-0 in the window (very fast first at-bat, first-pitch out, next batter also at 0-0 when sampled):** the batter-change criterion covers this. Two different numbers visible in the window → activity signal fires.

---

#### Acceptance criteria

- On `9AaT4645z6s`, exported chapters include `0:00 Pregame` and the first inning chapter appears at or after the first non-zero count in the overlay (approximately 6:34), not at 0:00.
- Videos with mid-game stream starts still allow a chapter at or near 0:00.
- `--start 10:00` runs are unaffected.
- Team-side swaps before the game do not select the batting half or create a first inning chapter on their own.
- `_window_has_game_active_signal` returns True as soon as a non-zero count or batter change appears in the window.
- `_game_active_timestamp` returns the timestamp of the first activity-signal state.
- Subsequent half-inning transitions are unaffected by the window activity check.

#### Tests to add

- `test_window_has_game_active_signal_returns_false_for_pregame_zero_count_stable_batter`
- `test_window_has_game_active_signal_returns_true_on_nonzero_balls`
- `test_window_has_game_active_signal_returns_true_on_nonzero_strikes`
- `test_window_has_game_active_signal_returns_true_on_batter_change`
- `test_window_has_game_active_signal_ignores_states_with_wrong_half_key`
- `test_window_has_game_active_signal_ignores_implausible_batter_states`
- `test_game_active_timestamp_returns_first_nonzero_count_state`
- `test_game_active_timestamp_returns_batter_change_timestamp_when_no_count`
- `test_game_active_timestamp_returns_none_when_no_signal_in_window`
- `test_detect_events_defers_first_chapter_to_game_active_timestamp_on_pregame_stream`
- `test_detect_events_emits_first_chapter_at_zero_for_mid_game_stream_start`
- `test_detect_events_skips_activity_signal_for_non_zero_starting_stream`
- `test_detect_events_subsequent_half_innings_unaffected_by_activity_signal_change`

### 35. Final Scorebug Marker

Source: Product QA from `9AaT4645z6s` / Victor Vipers run
Status: Done (Pass 11)

Implementation note:
- Added `EventType.GAME_FINAL`, `game_status` OCR configuration, state metadata normalization, stable-run final detection, and chapter export support with optional score suffix.
- Added `game_status` to default run fields while treating it as an optional template field, so existing templates that omit the crop continue to run.
- Added targeted tests for final status normalization, final event detection, final chapter export, default fields, and optional-template behavior.
- Pass 11 CR fixes (resolved): CR-40 threads `min_game_final_observations` through the CLI/workflow/event-file paths; CR-41 moves optional template-field metadata onto `OCRFieldConfig.optional`.

The current chapter export stops at the last detected half-inning. A useful publishing marker would be a final timestamp when the scorebug changes from inning/count display to `FINAL` in the middle/status area of the scorebug.

Important template caveat: this applies to the current SidelineHD 640x360 active overlay style. Other SidelineHD templates may place `FINAL` in a different region or use different styling, so this should be modeled as an optional template region/field rather than hardcoded global coordinates.

**Dependency:** Item 29 (Score at Inning Transitions) must be implemented first. Item 35 uses `OverlayState.away_score` / `.home_score` and `_score_snapshot()` which are introduced in item 29.

---

**`models.py` — new `EventType` variant**

Add `GAME_FINAL = "game_final"` to the `EventType` enum:

```python
class EventType(str, Enum):
    GAME_START = "game_start"
    HALF_INNING_START = "half_inning_start"
    AT_BAT_START = "at_bat_start"
    SCORE_CHANGE = "score_change"
    GAME_FINAL = "game_final"    # new
```

---

**`ocr.py` — `FIELD_CONFIGS` entry**

Add a tuned OCR config for the `game_status` field:

```python
"game_status": OCRFieldConfig(psm=7, scale=4),
```

No whitelist — "FINAL" is a word, not a digit set; restricting whitelist risks rejecting characters like `I` or `L`. PSM 7 (single text line) is appropriate for a small isolated label.

---

**`cli.py` — default run fields**

Add `"game_status"` to `_default_run_fields()` alongside the item 29 score fields:

```python
return _parse_field_list(args.field) or [
    "inning",
    "count",
    "left_score",
    "right_score",
    "game_status",
    "batter_card_name",
    "batter_card_number",
    "batter_number",
]
```

Templates that do not define a `game_status` region silently skip this field (existing behavior for any field absent from the template).

---

**`state.py` — `_normalize_game_status()` and `state_from_samples()`**

Add a normalizer alongside `parse_count()`, `parse_inning()`, and `parse_score()`:

```python
def _normalize_game_status(text: Optional[str]) -> Optional[str]:
    if text and "final" in text.lower():
        return "final"
    return None
```

In `state_from_samples()`, extract and normalize the status field, then store it in metadata:

```python
game_status = _normalize_game_status(_sample_text(samples_by_field, "game_status"))
```

```python
metadata={
    ...
    "game_status": game_status,
    ...
}
```

When `game_status` is not a configured template field, `_sample_text()` returns `None`, `_normalize_game_status(None)` returns `None`, and the metadata key is `None`. Zero cost and zero behavior change.

---

**`events.py` — `_detect_game_final()` and `detect_events()`**

Add the detector after the existing helpers. Takes `ordered_states` (already sorted by timestamp) and `min_observations` — the minimum consecutive run of FINAL states required before firing:

```python
def _detect_game_final(
    states: List[OverlayState],
    min_observations: int = 3,
) -> Optional[Event]:
    """Return a GAME_FINAL event at the first stable run of 'final' status, or None."""
    run_start: Optional[int] = None
    run_length = 0
    for index, state in enumerate(states):
        if state.metadata.get("game_status") == "final":
            if run_start is None:
                run_start = index
            run_length += 1
            if run_length >= min_observations:
                away_score, home_score = _score_snapshot(states, run_start, run_length)
                return Event(
                    event_type=EventType.GAME_FINAL,
                    timestamp_seconds=states[run_start].timestamp_seconds,
                    label="Final",
                    metadata={"away_score": away_score, "home_score": home_score},
                )
        else:
            run_start = None
            run_length = 0
    return None
```

The detector fires on the first consecutive run of `min_observations` states showing `game_status=="final"`. The timestamp is taken from the first state in the confirmed run (earliest reliable detection point). Score is drawn from `_score_snapshot()` over the same confirmed run window — no additional lookahead needed. A gap (OCR miss) resets the counter; the next clean run triggers instead.

Expose `min_game_final_observations` in `detect_events()` for testability:

```python
def detect_events(
    states: Iterable[OverlayState],
    ...
    min_game_final_observations: int = 3,
) -> List[Event]:
```

After the main detection loop, call the detector and merge:

```python
    # after main loop:
    game_final = _detect_game_final(ordered_states, min_observations=min_game_final_observations)
    if game_final is not None:
        events.append(game_final)
        events.sort(key=lambda e: e.timestamp_seconds)

    return events
```

`detect_events_file()` does not need to expose `min_game_final_observations`; the default of 3 is correct for production and tests call `detect_events()` directly.

---

**`exports.py` — `export_youtube_chapters()`**

After item 29 is in place, the chapter loop already has `include_score` and appends `(away-home)` for `HALF_INNING_START`. Item 35 makes two targeted changes:

1. Add `EventType.GAME_FINAL` to the event-type filter:

```python
if event.event_type in {EventType.INNING_START, EventType.HALF_INNING_START, EventType.GAME_FINAL}:
```

2. Extend the score-append block to cover `GAME_FINAL`:

```python
if include_score and event.event_type in {EventType.HALF_INNING_START, EventType.GAME_FINAL}:
    away = event.metadata.get("away_score")
    home = event.metadata.get("home_score")
    if away is not None and home is not None:
        label = f"{label} ({away}-{home})"
```

Example output: `1:36:00 Final (3-7)`

The existing `0:00 Pregame` intro guard (`first_chapter_seconds > 0`) is unaffected — GAME_FINAL is never the first chapter. `--no-inning-score` (from item 29) also suppresses the score suffix on the Final line.

---

**Template field**

`game_status` is an optional region in any template JSON:

```json
{
  "fields": {
    "game_status": {"x": 0, "y": 0, "width": 0, "height": 0}
  }
}
```

**Important:** Do not add `game_status` to the public example template (`examples/sidelinehd_640x360.json`) without confirmed pixel bounds derived from an actual FINAL frame. Inspect a real crop to determine coordinates before committing. The field should be omitted from the example template until coordinates are verified.

---

Acceptance criteria:
- `GAME_FINAL` is a new `EventType` variant with value `"game_final"`.
- `game_status` has a tuned entry in `FIELD_CONFIGS` (PSM 7, scale 4, no whitelist).
- `"game_status"` is in the default field list in `cli.py`.
- `_normalize_game_status()` returns `"final"` when text (case-insensitive) contains "final"; `None` otherwise.
- `state_from_samples()` stores `"game_status"` in state metadata; `None` when field absent from template.
- `_detect_game_final()` returns `None` when fewer than `min_observations` consecutive FINAL states are found.
- `_detect_game_final()` returns `None` when no states have `game_status=="final"` (template has no field).
- A gap (non-final state) between two short runs does not accumulate — each run is counted independently.
- The emitted `GAME_FINAL` event has `label="Final"`, timestamp at the first confirmed state, and score in metadata (`None` when unavailable).
- `export_youtube_chapters()` includes the GAME_FINAL line; score appended as `(away-home)` when both values are non-None.
- `--no-inning-score` suppresses the score suffix on the Final chapter line.
- Templates without `game_status` produce identical output to before this item (zero regression).
- Tests cover:
  - `_normalize_game_status()`: `"FINAL"` → `"final"`, `"Game Final"` → `"final"`, `"in play"` → `None`, `None` → `None`
  - `_detect_game_final()`: stable run of 3+ → event at first timestamp; only 2 → `None`; no "final" states → `None`; gap resets counter, next clean run triggers
  - `detect_events()`: `GAME_FINAL` in output when stable FINAL present; sorted after other events
  - `export_youtube_chapters()`: GAME_FINAL line present; score appended when available; `include_score=False` omits score; `(None, None)` score → no parenthetical

### 36. Active Lineup-Strip Confidence and Order Recovery

Source: Product QA from `9AaT4645z6s` / Victor Vipers run
Status: Done (Pass 7, confirmed on `9AaT4645z6s`)

`OCRBackendResult` and `OCRSample` carry `source_detail`. `lineup_strip` OCR marks reads as
`lineup_highlight` when the HSV active chip was isolated, or `lineup_full_strip` when falling
back to whole-strip OCR. Processing persists that value; state parsing stores it as
`lineup_strip_confidence`; event detection blocks lineup-strip at-bat starts and lineup-number
overrides unless highlight-confirmed; review flags unconfirmed lineup events. The Victor Vipers
`19:20` false positive (a non-highlighted `#15` visible in the strip) was eliminated on the real
run. 169 tests pass.

The lineup-strip improvements in item 33 recovered missing batters in the FLX game, but the Victor Vipers run exposes a false-positive side effect:

- At `19:20`, the export shows `Riley S. (#15)`. `#15` is visible somewhere in the lineup strip but is not the highlighted active batter. The HSV chip detector did not fire (no highlighted chip found), so the fallback full-strip OCR ran and returned `#15` — the first number Tesseract found in the strip image. The detector accepted this as a real at-bat start because #15 is rostered.
- Around `18:33`, `Maya R. (#22)` is missing. Recovery of missing batters is deferred to item 32 (batting-order continuity validator); item 36 focuses only on stopping the false-positive from full-strip reads.
- Bottom-of-4th ordering (`#26` before `#2`) is also deferred to item 32.

**Root cause:** `tesseract_ocr_image("lineup_strip")` currently returns the same `OCRBackendResult` shape regardless of whether the HSV highlight chip was found. The caller — `processing.py`, then `state.py`, then `events.py` — has no way to distinguish "the highlighted chip was found and OCR'd" from "the whole strip was OCR'd and we got whatever Tesseract found first." Item 33 stored both `lineup_strip_number` and `lineup_batter_number` but both are treated equally as usable signals.

**Fix: propagate lineup strip OCR confidence end-to-end**

---

#### Layer 1 — `ocr.py`: add `source_detail` to `OCRBackendResult`

```python
@dataclass(frozen=True)
class OCRBackendResult:
    text: str
    normalized_text: str
    confidence: Optional[float] = None
    backend: str = "none"
    source_detail: Optional[str] = None  # new
```

`tesseract_ocr_image()` sets this field for `lineup_strip` only:

```python
if field_name == "lineup_strip":
    highlighted = _extract_highlighted_lineup_crop(image)
    if highlighted is not None:
        processed_highlighted = preprocess_for_ocr(highlighted, "batter_number")
        highlighted_result = _tesseract_ocr_preprocessed_image(
            processed_highlighted,
            OCRFieldConfig(psm=10, whitelist="0123456789#", scale=6),
            field_name,
        )
        if highlighted_result.normalized_text:
            return dataclasses.replace(highlighted_result, source_detail="lineup_highlight")
    processed = preprocess_for_ocr(image, field_name)
    config = FIELD_CONFIGS.get(field_name, OCRFieldConfig())
    result = _tesseract_ocr_preprocessed_image(processed, config, field_name)
    return dataclasses.replace(result, source_detail="lineup_full_strip")
```

All other fields leave `source_detail=None`.

Values:
- `"lineup_highlight"` — HSV chip detection succeeded and Tesseract returned text from that crop.
- `"lineup_full_strip"` — HSV chip detection failed or returned no text; Tesseract ran on the whole strip.
- `None` — any field other than `lineup_strip`.

---

#### Layer 2 — `models.py`: add `source_detail` to `OCRSample`

```python
@dataclass
class OCRSample:
    timestamp_seconds: float
    field_name: str
    raw_text: str
    video_sha256: Optional[str] = None
    normalized_text: Optional[str] = None
    confidence: Optional[float] = None
    crop_path: Optional[Path] = None
    source_detail: Optional[str] = None  # new
    created_at: datetime = field(default_factory=_utc_now)
```

Backward-compatible: existing `samples.jsonl` files without this field deserialize with `source_detail=None`, which is treated as `"lineup_full_strip"` (conservative — old full-strip reads don't auto-emit at-bats without re-running OCR).

---

#### Layer 3 — `processing.py`: pass `source_detail` through

```python
OCRSample(
    ...
    source_detail=ocr_result.source_detail,
)
```

Also update `write_jsonl` / `load_ocr_samples` to serialize/deserialize the new field.

---

#### Layer 4 — `state.py`: store confidence in OverlayState metadata

In `load_ocr_samples()`, read `source_detail` from JSONL:

```python
OCRSample(
    ...
    source_detail=row.get("source_detail"),
)
```

In `state_from_samples()`, extract and store it:

```python
lineup_strip_sample = samples_by_field.get("lineup_strip")
lineup_strip_confidence = (
    lineup_strip_sample.source_detail if lineup_strip_sample else None
)
```

Store in metadata:

```python
metadata={
    ...
    "lineup_strip_confidence": lineup_strip_confidence,
    ...
}
```

`lineup_strip_confidence` will be `"lineup_highlight"`, `"lineup_full_strip"`, or `None` (old data / field not sampled).

---

#### Layer 5 — `events.py`: gate lineup-strip at-bat starts on confidence

**New helper:**

```python
def _lineup_is_highlight_confirmed(state: OverlayState) -> bool:
    """True when the lineup-strip read came from the HSV-detected chip, not the full strip."""
    return state.metadata.get("lineup_strip_confidence") == "lineup_highlight"
```

**Update `_is_plausible_batter_source()`:**

```python
if source == "lineup_strip":
    if roster is None:
        # Without a roster, only allow highlight-confirmed reads
        return _lineup_is_highlight_confirmed(state)
    if not _lineup_is_highlight_confirmed(state):
        return False  # full-strip reads cannot trigger at-bat starts
    return _has_roster_match_for_state(state, roster)
```

This is a tightening relative to the current code (which only checked `_has_roster_match_for_state`). Full-strip reads are now hard-blocked from emitting at-bat starts regardless of roster match, because the number may simply be visible in the strip but not the current batter.

**Update `_preferred_lineup_number_for_state()`:**

Change the internal call from `_active_lineup_number_for_state()` to a new helper that only returns a lineup number when highlight-confirmed:

```python
def _preferred_lineup_number_for_state(state, roster):
    source = state.metadata.get("batter_number_source")
    lineup_number = _highlight_lineup_number_for_state(state, roster)  # changed
    if not lineup_number:
        return None
    if source == "lineup_strip":
        return lineup_number
    if source != "batter_card":
        return None
    batter_name = state.metadata.get("batter_name")
    if batter_name and roster.number_for_name(str(batter_name)):
        return None
    if batter_name and _jersey_number_from_text(str(batter_name)):
        return None
    return lineup_number
```

**New helper `_highlight_lineup_number_for_state()`:**

```python
def _highlight_lineup_number_for_state(
    state: OverlayState, roster: Roster
) -> Optional[str]:
    """Return a rostered lineup number only when the lineup-strip read is highlight-confirmed."""
    if not _lineup_is_highlight_confirmed(state):
        return None
    return _active_lineup_number_for_state(state, roster)
```

`_active_lineup_number_for_state()` continues to check all lineup sources (including full-strip `lineup_strip_number`) and is used for roster-match checks in `_has_roster_match_for_state()` — full-strip reads can still confirm a roster match, they just can't be the basis for starting an at-bat.

**Update `_enrich_states_digit_runs()`:**

Only resolve fused digit runs from highlight-confirmed lineup reads:

```python
def _enrich_states_digit_runs(states, roster):
    enriched = []
    for state in states:
        if (
            state.metadata.get("batter_number_source") == "lineup_strip"
            and _lineup_is_highlight_confirmed(state)  # new guard
            and state.batter_number
            and len(state.batter_number) > 2
        ):
            resolved = _resolve_lineup_digit_run(state.batter_number, roster)
            if resolved:
                metadata = dict(state.metadata)
                metadata["batter_number_digit_run_original"] = state.batter_number
                state = replace(state, batter_number=resolved, metadata=metadata)
        enriched.append(state)
    return enriched
```

A full-strip read that OCRs as a fused `"265"` is not safe to resolve — we don't know which chip in the strip was at the top and whether the fused string is from adjacent chips or a single chip smear.

---

#### Layer 6 — `review.py`: flag accepted lineup-recovered events

Accepted at-bats that came from a highlight-confirmed lineup strip should be
visible in review output:

```python
if event.metadata.get("batter_number_source") == "lineup_strip":
    flags_by_index[index].append("lineup-recovered")
```

The earlier `lineup-unconfirmed` idea was removed during review. Non-highlight
lineup-strip reads are blocked before event emission, so they cannot appear in
event-review output without adding a separate candidate/diagnostic event stream.
That diagnostic stream may be useful later, but it is intentionally outside item
36's false-positive suppression fix.

---

#### What's deferred to item 32

Recovery of missing batters (`Maya R. #22`) and ordering problems (bottom 4 starting with `#2` instead of `#26`) require batting-order continuity. Item 36 only addresses the false-positive suppression. Item 32's validator will use `lineup_strip_confidence` in metadata to know when a lineup-strip read is trustworthy versus speculative.

---

#### Backward compatibility

Existing `samples.jsonl` files produced before this change have no `source_detail` field. When loaded, `lineup_strip_confidence` will be `None` for those samples. Since `None != "lineup_highlight"`, existing lineup-strip reads from old runs will be treated as full-strip (non-highlight) and will no longer trigger at-bat starts on `detect-events` re-runs. Users must re-run `process` (or `run-game`/`run-youtube`) to get the new `source_detail` field into their samples. This is expected and consistent with the behavior of any OCR-layer change.

---

#### Acceptance criteria

- `lineup_strip_confidence` key is present in `OverlayState` metadata whenever a `lineup_strip` sample exists; value is `"lineup_highlight"`, `"lineup_full_strip"`, or `None` for fields that were not sampled.
- `OCRSample.source_detail` is serialized to and deserialized from JSONL. Old JSONL rows without the field load with `source_detail=None`.
- A state with `lineup_strip_confidence="lineup_full_strip"` and `batter_number_source="lineup_strip"` does NOT emit an `AT_BAT_START`, even when the number is rostered.
- A state with `lineup_strip_confidence="lineup_highlight"` and a rostered number DOES emit an `AT_BAT_START` (regression: item 33 FLX behavior preserved).
- A state with `lineup_strip_confidence="lineup_highlight"` and a 3-digit fused string has the digit run resolved via `_resolve_lineup_digit_run()`.
- A state with `lineup_strip_confidence="lineup_full_strip"` and a 3-digit fused string is NOT digit-run resolved (the `len > 2` state will be rejected by `_is_plausible_batter_state()` as usual).
- `lineup-recovered` review flag appears on accepted events where `batter_number_source == "lineup_strip"`.
- `lineup-unconfirmed` is not emitted; non-highlight lineup-strip reads are intentionally blocked before event emission.
- On `9AaT4645z6s`, the `19:20 Riley S. (#15)` event is suppressed (it was a full-strip read; #15 was visible in the strip but not highlighted).
- On the FLX regression run, the confirmed 2nd-inning batter sequence is unchanged.

#### Tests to add

- `test_lineup_is_highlight_confirmed_returns_true_for_lineup_highlight`
- `test_lineup_is_highlight_confirmed_returns_false_for_full_strip`
- `test_lineup_is_highlight_confirmed_returns_false_for_none`
- `test_detect_events_suppresses_full_strip_lineup_event_even_when_rostered`
- `test_detect_events_emits_at_bat_from_lineup_highlight_with_roster`
- `test_detect_events_emits_at_bat_from_lineup_highlight_without_roster`
- `test_detect_events_suppresses_full_strip_event_without_roster` (no roster → still suppressed)
- `test_enrich_states_digit_runs_skips_full_strip_states`
- `test_render_event_review_flags_lineup_recovered`
- `test_enrich_states_digit_runs_resolves_highlight_confirmed_states`
- `test_lineup_unconfirmed_flag_appears_for_full_strip_event`
- `test_lineup_unconfirmed_flag_not_appears_for_batter_card_event`
- `test_ocr_sample_serializes_source_detail`
- `test_load_ocr_samples_reads_source_detail`
- `test_load_ocr_samples_defaults_source_detail_to_none_for_old_rows`
- `test_state_from_samples_stores_lineup_strip_confidence_in_metadata`

### 37. YouTube Playlist Batch Queue (CLI)

Source: Product backlog
Status: Done (Pass 12, CR-42–46 resolved; CR-47 deferred to item 22)

Process an entire YouTube playlist of game recordings in one command: enumerate
the playlist, then run the existing single-game pipeline over each video in a
resumable, failure-isolated queue. This is the top near-term priority.

**Why this first:** beyond the immediate workflow win, the batch orchestrator is
the prototype of the local web app's background job runner (item 39). Building
the queue abstraction cleanly here — a list of game-processing jobs, run
sequentially, each isolated, each resumable, with per-job and batch-level status
— means the web layer later reuses this machinery with an HTTP face instead of
throwaway work. Keep the orchestration in a library function (in `workflow.py`
or a new `batch.py`) that the CLI and the future web layer both call.

**Command:** `sidelinehd-extractor run-playlist PLAYLIST_URL [options]`

- Shares the run-processing arguments with `run-youtube` via
  `_add_run_processing_arguments` (template, roster, spacing knobs,
  `--min-game-final-observations`, order validation, etc.).
- Adds `--force` (reprocess videos already completed), `--limit N` (cap how many
  to process this invocation), and `--start-index N` (skip the first N entries).

**Enumeration (cheap, no download):** new function in `youtube.py`:
`list_playlist_videos(playlist_url) -> List[PlaylistEntry]`, backed by yt-dlp's
flat-playlist mode (`--flat-playlist`, or the Python API with
`extract_flat=True`). `PlaylistEntry` carries `video_id`, `url`, `title`, and
`index`. No frames are downloaded during enumeration.

**Sequential processing:** for each entry, call the existing
`run_youtube_game()`. OCR is CPU/IO-heavy, so process one game at a time —
parallelism buys little on a single machine and complicates status. Print batch
progress (`[3/12] Processing "<title>"…`) and reuse each game's existing
per-video progress callbacks, prefixed with the batch position.

**Resumability / idempotency:** maintain a batch state file
(`playlist_state.jsonl` or a batch manifest) in the playlist output directory
that maps `video_id → {status: done|failed|skipped, run_dir, export_paths}`. On
re-run, entries already marked `done` are skipped unless `--force`. Persist the
`youtube_video_id` in each run manifest so batch state can be reconstructed if
the state file is lost.

**Failure isolation and retries:** wrap each `run_youtube_game()` in try/except.
Transient download failures (yt-dlp rate limits, network blips) get a small
number of retries with backoff before the entry is marked `failed`. A private,
deleted, or persistently unreadable video records a `failed` entry with the
error and the batch continues to the next game — one bad video never aborts the
run. `--retries N` (default 2) controls the attempt count.

**Batch summary:** emit JSON to stdout (consistent with other commands)
summarizing counts (processed / skipped / failed). **Each per-game entry must
carry the source video's `title` and `url` alongside its `run_dir`, `status`, and
export paths** — a human posting N games needs to route each game's chapters and
at-bats to the correct YouTube video without cross-referencing bare video IDs.
Also write a **human-readable batch index** (`batch_summary.md` in the playlist
output dir) that lists, per game, the title, URL, and the paths to the chapters
file and at-bats file — this is the artifact a videographer actually works from
when pasting into YouTube, and it is the CLI precursor to the web app's
multi-game paste view (item 39b). Close with a one-line human summary to stdout.

**Explicitly out of scope (future items):**
- **Channel ingestion + "is this video a game?" classifier.** The elegant
  version reuses our scorebug detection — sample a few frames, check for a
  SidelineHD overlay — but that means partially downloading every candidate,
  which is expensive. Deferred; playlist-URL (pre-curated) ships first.
- **Parallel processing.** Sequential is correct for a single machine.

**Testing:** mock `list_playlist_videos` and `run_youtube_game`; assert
sequential invocation order, skip-on-already-done, `--force` reprocess, error
isolation (one entry raises, batch still completes and records the failure), and
batch-manifest shape. Cover `--limit` and `--start-index` slicing.

### 38. Feedback Log — Capture, Sanitize, Export

Source: Product backlog
Status: Ready for Review

Produce a sanitized, portable **Markdown** log from a completed run that a
videographer can attach to a GitHub issue or email and send to us. We feed that
log into Claude/Codex to infer issues and generate new work or tests. Because
each videographer runs entirely locally (item 39), this log is the **only** data
that ever crosses a machine boundary — so sanitization is mandatory, and the
user must be able to preview exactly what it contains before sending.

**Why Markdown, not JSON:** it is LLM-native (Claude/Codex parse it directly)
and simultaneously human-readable, so a single artifact serves both the
machine-analysis purpose and the "review before you send it" requirement.
Structured sections with fenced blocks keep it machine-parseable.

**Why CLI-first:** the sanitizer is the most privacy-critical component in the
whole system. Build and harden it in the CLI — where its output can be eyeballed
and pinned with fixtures — before any web "Send feedback" button (item 39e) ever
exposes it.

**Command:** `sidelinehd-extractor feedback RUN_DIR [--note "..."] [--output feedback.md]`

Reads a completed run (`states.jsonl`, `events.jsonl`, review output, manifest,
and the roster used) and writes a sanitized Markdown log. The tool makes **no
network calls** — it writes a file the user opens, reads, and attaches manually.

**Content kept (non-PII, diagnostically useful):**
- Environment: tool version, Tesseract version, platform, template name,
  detection parameters (from the manifest).
- Every review flag that fired, with structured detail — flag type, timestamp,
  **jersey numbers involved**, OCR raw-vs-normalized text for the failing field,
  and confidence scores.
- Event-sequence summary (types, timestamps, inning/half), names redacted.
- Optional freeform `--note` shown verbatim (the user owns its content and sees
  it in the previewable output).

**Sanitization rule — the core contract:**
- **Jersey numbers: kept.** Not identifying on their own, and essential for
  OCR-disagreement diagnosis (e.g. "`batter_number_disagreement`: lineup=12 vs
  card=72 at t=634").
- **Player names: always redacted** → stable per-log pseudonyms (`Player A`,
  `Player B`) built from a name→pseudonym map (from the roster plus any observed
  names) and applied to every string field, so cross-references stay coherent
  within a log while no real name leaves the machine.
- **Team names: redacted** (`Home Team` / `Away Team`).
- **Video URL/ID: dropped** by default.
- **Raw frames/crops: excluded** by default (they contain faces and names). No
  opt-in in v1; a future blurred-crop attachment is a separate, larger item.

**Sanitizer as a hardened library function:**
`sanitize_feedback(run_data, name_map) -> FeedbackLog`, rendered to Markdown by a
separate formatter. This is the privacy boundary; test it as one.

**Testing:** build a fixture run using sanitized placeholder names (per the
security constraint) and assert consistent pseudonymization, preserved jersey
numbers, and no team/name leakage in the rendered log. Add a **guard test** that
feeds a deliberately name-laden run and asserts none of those name tokens survive
in the output — a property check that every roster name is absent from the
rendered Markdown.

**Implementation note.** Added `feedback.py` with `load_feedback_data()`,
`build_name_sanitizer()`, `sanitize_feedback()`, `render_feedback_log()`, and
`write_feedback_log()`. The CLI command is
`sidelinehd-extractor feedback RUN_DIR [--note "..."] [--output feedback.md]`.
The rendered Markdown includes selected environment metadata (tool/platform,
Tesseract version, OCR backend/workers, template, fields, detection params), run
warnings, review flags with exact-timestamp OCR raw/normalized/confidence rows,
and a sanitized event sequence. Player names are replaced with stable `Player A`
style pseudonyms built from roster and observed names; jersey numbers are kept;
team names are redacted; URLs/video IDs/crop paths are dropped. `--note` remains
verbatim by design. Tests cover useful diagnostic content, preserved jersey
numbers/confidence/version metadata, name/team/URL/crop exclusion, observed-name
pseudonyms, and CLI parsing.

### 39. Local Web App (Epic)

Source: Product backlog
Status: Epic — phases promoted to standalone numbered items with full designs when scheduled

A local-first, single-user web interface each videographer runs on their own
machine at `localhost`, wrapping the existing pipeline. **No auth, no shared
server, no multi-tenancy** — every install is one person on one machine. Built
with a clean seam for eventual cloud hosting. Player data never leaves the
machine except through the sanitized feedback log (item 38).

**Recommended stack:** FastAPI + server-rendered HTML + HTMX; a lightweight
in-process background job runner (reusing the batch orchestrator from item 37);
a small SQLite index for job status and feedback, with the JSONL run artifacts
in `runs/` remaining the source of truth. The CLI is preserved; the web layer
calls the same `workflow` / `exports` / `roster` / `events` / `corrections`
functions. HTMX (not a React SPA) keeps a single-user local tool low-complexity;
revisit only if this ever becomes a hosted product.

**Phases** (each becomes its own item with a full design when picked up):
- **39a — Web skeleton + job runner.** → **Promoted to item 46** (full design below).
  FastAPI app; submit a single video URL or a playlist; background job runner
  reusing item 37's batch orchestrator; live status via HTMX polling. Proves the
  hardest new plumbing.
- **39b — Results + multi-game paste kits.** → **Promoted to item 47** (full design
  below). Render chapter and at-bat exports for every game in a batch on a single
  page — multiple copy-kit blocks stacked, one per game, each with one-click copy.
  Reuses item 20's HTML paste-kit machinery.
- **39c — Exception review UI.** → **Promoted to item 49** (full design below).
  Surface `review.py` flags, resolve them into `corrections.py`, and re-export —
  a friendly front-end for the corrections workflow that today is hand-edited CSV.
- **39d — Roster management UI.** → **Promoted to item 50** (full design below).
  CRUD over the roster CSVs (`roster.py`).
- **39e — Send-feedback UI.** → **Promoted to item 51** (full design below).
  Wraps item 38's sanitizer: preview the Markdown log in-browser, then hand off to
  a GitHub-issue or email flow. No new sanitization logic in the web layer.

**Cross-cutting — packaging/install (with item 19):** the per-device install
model puts smooth "install and run" ergonomics for non-developers (Mac and
Windows) on the critical path for this epic.

**Dependencies:** 39a → item 37; 39b → item 20; 39c → `corrections.py`; 39e →
item 38.

### 40. OCR Confidence Capture

Source: Architect review 2026-07-02 / accuracy
Status: Ready for Review

**Problem:** [`_tesseract_ocr_preprocessed_image`](src/sidelinehd_extractor/ocr.py)
hardcodes `confidence=None`. `OCRSample.confidence`, the review flags, and the
tiered at-bat spacing gate (item 31) are all built to consume a confidence value
that never arrives — the accuracy machinery is half-wired and inert.

**Design:**
- Switch the Tesseract call from plain text (`tesseract input stdout`) to TSV
  output so per-word confidence (`conf` column) is captured. Reconstruct the
  text by joining the `text` tokens in row order (preserving the existing
  plain-text result), and compute an aggregate confidence.
- **Aggregation policy**, in a helper keyed on field type:
  - Numeric single-token fields (`left_score`, `right_score`, `count`,
    `batter_number`, `batter_card_number`, `on_deck_number`): use the **minimum**
    word confidence — the weakest digit governs correctness.
  - Multi-word text (`batter_card_name`, `lineup_strip`, team fields): use the
    **length-weighted mean** of positive-confidence tokens.
- Populate `OCRBackendResult.confidence` on a **0–1 scale** (normalize Tesseract's
  0–100), and document the scale so future backends match it.
- Surface the value where the review/gate logic reads it (verify current wiring
  in `state.py` and item 31's gate; thread it through if a gap exists).
- **Backward compatibility:** TSV headers differ between Tesseract 4 and 5. If the
  TSV can't be parsed, degrade to `confidence=None` and still return the text —
  never crash on a version mismatch.

**Testing:** TSV fixtures with known `conf` values → assert the reconstructed text
matches the old plain-text path and the aggregate matches the numeric-min vs
text-mean policy; malformed TSV → `confidence=None`, text preserved; existing OCR
tests still pass with the new command.

**Value:** unblocks item 31 (tiered gate), sharpens review flags, and roughly
doubles the diagnostic value of the feedback log (item 38) — hence "precede 38."

**Implementation note.** The subprocess Tesseract path now requests TSV output
and parses `text`/`conf` rows into `OCRBackendResult.confidence` on the existing
0–1 scale. Numeric fields (`left_score`, `right_score`, `count`,
`batter_number`, `batter_card_number`, `on_deck_number`) use the minimum parsed
word confidence; text fields use a length-weighted mean of positive-confidence
tokens. Malformed/non-TSV output returns the raw text with `confidence=None` so
OCR does not fail on output-format drift. The optional `tesserocr` backend uses
the same aggregation policy via `AllWordConfidences()`. Existing
`process_video()`/`OCRSample` wiring already persisted confidence; tests now
cover TSV numeric/text aggregation, malformed fallback, the `tsv` command mode,
and sample-file persistence.

### 41. OCR Pipeline Performance

Source: Architect review 2026-07-02 / performance
Status: Ready for Review

**Problem:** the pipeline spawns one `tesseract` subprocess and writes one temp
PNG **per crop** ([ocr.py](src/sidelinehd_extractor/ocr.py) `_tesseract_ocr_preprocessed_image`;
loop at [processing.py](src/sidelinehd_extractor/processing.py) `process_video`).
A 2-hour game at 5s sampling × ~10 fields ≈ **14,000 subprocess spawns and temp
files**, with Tesseract reloading its LSTM model every call. That fork/exec +
model-load overhead is the dominant cost, it multiplies across a playlist (item
37), and a fork-storm competes with the web job runner (item 39).

**Design — two independent wins, ship #1 first:**

1. **Parallelize per-crop OCR across a worker pool.** The per-field OCR calls are
   independent and the subprocess releases the GIL, so a `ThreadPoolExecutor`
   yields near-linear speedup. Collect results keyed by `(timestamp, field)` and
   **reassemble samples in the original order** so `samples.jsonl` stays stable
   and diffable. Progress reporting stays monotonic (report by completed count).
   Add `--ocr-workers N` (default `os.cpu_count()`; `1` = serial for debugging).

2. **In-process Tesseract backend.** Add a backend via `tesserocr` that holds one
   initialized `PyTessBaseAPI`, sets the image directly from the numpy array (no
   temp file), and reuses the engine across crops — model loads once.
   `create_ocr_backend` gains the new name; the dependency goes in a pyproject
   extra; **fall back to the subprocess backend when `tesserocr` isn't installed.**
   A `PyTessBaseAPI` instance is not thread-safe, so combine with #1 as one API
   per worker thread (or a small pool of APIs).

Also in scope: **flip `save_crops` to default `False`** for `run-game`/
`run-playlist` (an opt-in `--save-crops` stays for debugging) — otherwise every
run litters ~14k PNGs.

**Testing:** the parallel path must produce a **byte-identical `samples.jsonl`** to
the serial path (ordering guarantee); `--ocr-workers 1` vs `N` equivalence; the
tesserocr backend behind an import guard that skips when unavailable; assert the
new `save_crops` default.

**Implementation note.** `process_video()` now accepts `ocr_workers` (defaulting
to CPU count, `1` for serial debugging), runs per-timestamp crop OCR through a
`ThreadPoolExecutor`, and reassembles samples in template field order so
`samples.jsonl` ordering remains stable. The worker count is recorded in
`manifest.json` and is threaded through `run_game`, `run_youtube_game`,
`run_playlist_batch`, and the CLI as `--ocr-workers N`. Added optional
`--ocr tesserocr` / backend name `tesserocr`: when the `ocr` extra is installed,
it uses a thread-local `PyTessBaseAPI` per worker; when unavailable, it falls
back to the existing subprocess backend after the normal Tesseract availability
check. End-to-end run commands now default to not writing crop PNGs, with opt-in
`--save-crops`; the old `--no-crops` spelling remains accepted as a compatibility
no-op. The low-level `process` audit command keeps its crop-saving default.
Added regression coverage for serial-vs-parallel row equivalence/order, invalid
worker counts, shared CLI parsing, the new run crop default, and the guarded
`tesserocr` fallback path.

### 42. Tesseract Version Capture and Compatibility Check

Source: Architect review 2026-07-02 / support
Status: Ready for Review

**Problem:** [`ensure_tesseract_available`](src/sidelinehd_extractor/ocr.py) checks
only that the binary exists. OCR output differs meaningfully between Tesseract 4
and 5, and the per-device install model (item 39) makes version drift the most
likely "works on my machine" support issue.

**Design:**
- Add `tesseract_version() -> Optional[str]` (parse the first line of
  `tesseract --version`).
- Capture the version at backend creation / process start; record it in the run
  manifest and expose it for the feedback log (item 38).
- If the version is below a defined `MIN_SUPPORTED` (e.g. 4.1) or unrecognized,
  print a **non-fatal** stderr warning. Never hard-fail on version alone.

**Testing:** mock `--version` output for 4.x and 5.x → parsed correctly;
garbled/absent → returns `None` and warns; manifest records the version.

**Implementation note.** Added `tesseract_version() -> Optional[str]`, parsing the
first `tesseract --version` line into a version string such as `5.3.0`.
`create_ocr_backend("tesseract")` and the `tesserocr` path now capture that
version onto the backend callable/object and emit only non-fatal stderr warnings
when the version is missing, unrecognized, or below `MIN_SUPPORTED_TESSERACT_VERSION`
(`4.1`). `process_video()` records the captured value as `tesseract_version` in
`manifest.json`, making it available to item 38's feedback log. Tests cover
version parsing, unrecognized output, old-version warning without backend
failure, and manifest persistence.

### 43. OCR Accuracy Follow-ons — Multi-PSM Voting and Per-Field Preprocessing

Source: Architect review 2026-07-02 / accuracy
Status: Ready for review (implemented on branch `impl/item-43` by Fable 5; measured
strategy deviation flagged in CODE-REVIEW.md)

Depends on confidence being available (item 40); measure every change against
confidence deltas on a small fixture set before committing thresholds.

**Design:**
1. **Multi-PSM voting for critical numeric fields** (`left_score`, `right_score`,
   `count`, `batter_number`, `batter_card_number`, `on_deck_number`): run psm 7
   and psm 10, keep the higher-confidence normalized result; on a tie prefer the
   whitelist-valid candidate. Gate behind field membership so text fields are
   never double-run.
2. **Per-field preprocessing strategy:** extend `OCRFieldConfig` with a
   `preprocess` variant (e.g. `"default"`, `"numeric_hard_threshold"`,
   `"text_adaptive"`); `preprocess_for_ocr` dispatches on it. Numeric fields get a
   strategy tuned for isolated glyphs; name/strip fields keep an adaptive
   threshold. Strategies stay in config so they're tunable per template.

**Testing:** voting picks the higher-confidence variant on fixtures and leaves
text fields untouched; each preprocess strategy is exercised; a small
before/after confidence comparison confirms no regression on the numeric fields.

### 44. Pregame Status as Game-Start Suppressor

Status: Done (Pass 13, CR-48 and CR-49 resolved)

Source: CR-48 / CR-49 (Pass 13). An initial implementation of this landed in the
working tree outside the item/CR workflow; this design retro-specifies it and
fixes the two review findings before it is committed.

**Problem.** SidelineHD renders an explicit pregame banner ("GAME STARTING SOON")
in the scorebug status area before play begins. Item 34 already defers the first
chapter using count/batter activity signals, but an explicit pregame marker is a
stronger, independent way to say "definitely not live yet" — useful for the
Victor Vipers class of games where a stable pregame overlay (including a 0-0
count and a lineup-highlight batter) otherwise risks an early `Top 1` at 0:00.

**Core design principle (resolves CR-48).** The pregame banner is a reliable
**negative** signal ("still pregame → suppress game start") but an **unreliable
positive** one: `game_status` OCR is intermittent, so "banner absent this frame"
does not mean "game is live" — it may just be a missed read. Therefore the
pregame status must be used as a **suppressor layered on item 34's existing
activity gate**, never as an independent trigger that fires on a bare non-null
(e.g. 0-0) count. The initial implementation did the latter — `saw_pregame_status
and _has_ingame_overlay_signal(state)` returned on the first 0-0 after a single
latched pregame read — which conditionally re-opens the item-34 / CR-36 guard.

**Behavior.**
- A state whose `game_status` normalizes to `"pregame"` is treated as
  confirmed-pregame: it is skipped and **suppresses** game-start emission for that
  frame, regardless of the count shown. It also resets the batter-change baseline
  (`previous_batter_number = None`) so a post-pregame batter change is measured
  from after the banner.
- The **trigger** for game start remains item 34's positive activity gate only:
  `balls > 0 or strikes > 0`, or a trusted batter change
  (`_has_batter_change_activity_signal`). Remove the `saw_pregame_status`
  early-return branch and the `_has_ingame_overlay_signal` helper entirely — a
  bare 0-0 never qualifies, pregame or not.
- Net effect: a stable pregame 0-0 overlay is suppressed (explicit banner ∧ no
  positive activity); the chapter fires at the first real pitch/activity after
  the banner clears. Correctness no longer depends on `game_status` OCR being
  perfectly reliable, and the item-34/CR-36 guard is preserved.
- Trade-off (document in code): this places the chapter at first *activity*, not
  at banner-clear. If a future real-footage study shows banner-clear is a
  materially better placement, trusting it as a trigger would require a
  **confirmed stable pregame→ingame transition** (a run of ≥N pregame reads then
  ≥N in-game reads, mirroring `_detect_game_final`), not a single latched flag —
  spec that separately, backed by footage.

**Normalizer robustness (resolves CR-49).** In `_normalize_game_status`:
- Dedupe the token sets — `"gam"` subsumes `"game"`/`"gamo"`; `"oon"` subsumes
  `"soon"`/`"boon"`. Keep only genuinely distinct variants and tighten the
  over-broad short tokens (`"oon"`, `"oom"`, `"ong"`, `"eom"`) that can
  false-positive on crop bleed.
- Drop the digit guard: `gameish AND soonish` already excludes `"0-0"`/`"top1"`
  (neither carries the alphabetic tokens), so the guard only harms — it wrongly
  rejects legitimate labels like `"GAME 7:00 SOON"`.
- The hardcoded-misread enumeration is a known-fragile interim. The durable form
  is confidence-scored or edit-distance matching; tie that to **item 40 (OCR
  Confidence Capture)** rather than growing the token lists. Leave a comment
  saying so.
- Add a shared `game_status` accessor (e.g. `_game_status(state)`) so
  `_is_pregame_state` and `_detect_game_final` stop independently hardcoding the
  `"game_status"` metadata key and its literal values.

**Testing.**
- A confirmed-pregame state followed by a **stable 0-0** overlay (no pitch) must
  **not** emit a chapter — the realistic case CR-48 flagged. Update the existing
  `test_window_has_game_active_signal_returns_false_for_pregame_zero_count_stable_batter`
  to carry `game_status: "pregame"` and assert suppression.
- A flaky pregame read (drops for a frame) with a stable 0-0 in the gap must not
  fire early.
- After a pregame period, the first `balls>0/strikes>0` (or trusted batter
  change) state fires the chapter at that timestamp.
- `_normalize_game_status`: keep the pregame-variant coverage tests, add
  `"GAME 7:00 SOON"` → `"pregame"` (digit-guard removal), and a negative for a
  short-token false-positive that the tightened set now rejects.

### 45. Fix `right_score` Region Calibration + Empty-Field Guard

Status: Done (Pass 14)

Source: Product QA (Pass 13 diagnosis). On the `9AaT4645z6s` / Victor Vipers run,
chapters exported with no score suffix even though item 29 is Done and score
display is on by default.

**Root cause (diagnosed, not hypothetical).** In that run, `left_score` OCR'd
successfully on 687 states, but `right_score` produced **empty OCR on all 1153
states** — the home score is read **zero** times. `_score_snapshot` requires both
scores to be non-None, so every one of the 13 `HALF_INNING_START` events got
`(None, None)` and `_chapter_label` correctly dropped the suffix. Inspecting the
saved crops confirmed it: the `left_score` crop shows a clean `11`, while the
`right_score` crop is **empty background** (solid fill, no digit). The
`right_score` region is miscalibrated — it crops the wrong part of the scorebug.

This is the region shipped in
`examples/sidelinehd_640x360_active.example.json` (`right_score` at
`x: 0.612, y: 0.033, width: 0.05, height: 0.064`), so anyone using that template
(or one derived from it) silently loses the home score.

**Part A — recalibrate `right_score`.**
- The home-score digit sits **left/up** from the old `x: 0.612, y: 0.033`
  region. Real-frame calibration found `x: 0.580, y: 0.025, width: 0.050,
  height: 0.064`.
- Codex should extract a real frame from the game video (the calibration-frame
  command / `calibration.py`) — neither the architect nor Ryan has a loose frame
  to hand — locate the actual home-score digit, set the corrected coordinate in
  the example template, and **verify by re-processing**: both `away_score` and
  `home_score` populate, and exported chapters show `(a-b)` suffixes.
- If the away/right layout turns out not to be mirror-symmetric (e.g. team-name
  widths shift the digits), calibrate empirically from the frame rather than by
  the mirror hint.

**Part B — empty-field guard so this never fails silently again.**
- The current behavior is *silent*: a field that reads empty for the entire run
  produces no output and no warning; Ryan only caught it by noticing the missing
  suffix. Add a guard that, after a run, detects any **configured field whose OCR
  was empty across the whole run** (0 non-empty samples) and surfaces it:
  a stderr warning during `run-*`, a flag in the manifest, and a line in the
  review report (e.g. `field-never-read=right_score`).
- Keep `_score_snapshot`'s both-scores-required rule as-is (don't emit a partial
  `(4-?)`); the guard is what makes the partial-failure visible.
- This dovetails with item 38 (the feedback log should include per-field
  read-rate) and item 40 (confidence would further explain *why* a field is
  empty vs. low-confidence).

**Testing.**
- Part A: a fixture/regression asserting the example template's `right_score`
  region, once corrected, yields a parsed home score on a representative frame
  (or a coordinate-sanity test if a full-frame fixture is impractical).
- Part B: a run where one configured field has all-empty samples produces the
  warning + manifest flag + review-report line; a run where every field reads at
  least once does not.

**Implementation note.** The corrected template region read `right_score` on
8/8 real smoke-test samples from the Victor Vipers video (`0, 0, 2, 2, 2, 4, 4,
4`) with no warnings. `process_video` now records `field_read_stats` and
`warnings` in `manifest.json`; `run-game` / `run-youtube` surface warnings via
the existing stage-progress callback; and `review_report` renders manifest
warnings under "Run Warnings".

### 46. Local Web App — Phase 39a: Web Skeleton + Job Runner

Status: Done (Pass 15, implemented by Fable 5; approved with follow-up CR-51)
Source: Promoted from item 39 (epic), phase 39a. Depends on item 37 (Done).

The foundational slice of the local web app (item 39): a `localhost` FastAPI app
that accepts a single video URL or a playlist URL, runs it in a background job,
and streams live status via HTMX polling. This proves the hardest new plumbing
(long-running work behind a responsive UI) and is the base every later phase
(47/39c/39d/39e) builds on. **Reuse the pipeline; do not reimplement it** — the
web layer only calls existing `workflow` / `batch` functions and presents their
output.

**Package layout (new).** Create `src/sidelinehd_extractor/webapp/`:
- `app.py` — `create_app()` factory returning a `FastAPI` instance; route
  handlers. Keep route handlers thin — they call into `jobs.py`.
- `jobs.py` — `Job` dataclass + `JobStore` (in-memory registry) + a single-worker
  background runner.
- `templates/` — Jinja2 templates (`index.html`, `job_detail.html`, and HTMX
  partials `_job_row.html`, `_job_status.html`).
- `static/htmx.min.js` — **vendored** HTMX (no CDN; the app must work offline and
  the artifact CSP/local-first constraint forbids external fetches).

**Dependencies.** Add an optional extra `web` in `pyproject.toml`
(`fastapi`, `uvicorn[standard]`, `jinja2`) so the core CLI install stays
dependency-light. Document `pip install -e ".[web]"`. Import of `webapp` must
fail with a clear "install the web extra" message if FastAPI is missing (guard
the `serve` CLI command, not module import at package top level).

**Job model (`jobs.py`).**
- `Job`: `id: str` (uuid4 hex), `kind: Literal["single","playlist"]`, `url: str`,
  `status: Literal["queued","running","done","error"]`, `stages: list[str]`
  (append-only, fed by the pipeline's `stage_progress` callback),
  `current_stage: Optional[str]`, `warnings: list[str]` (stage strings that start
  with `"warning "` — item 45 surfaces `field-never-read` here), `result:
  Optional[dict]` (run dir(s) + export paths + per-entry summaries), `error:
  Optional[str]`, `created_at`, `finished_at`.
- `JobStore`: thread-safe dict of `id → Job` with `create()`, `get()`, `list()`
  (newest first), and `update()` under a `threading.Lock`. Define it behind a tiny
  interface so a later phase can swap in the epic's SQLite index without touching
  routes — but **do not build SQLite now**; in-memory is the correct scope for the
  skeleton (single user, single process). Note this deferral in a comment.
- Runner: one dedicated worker via `ThreadPoolExecutor(max_workers=1)` so heavy
  download+OCR jobs serialize on a laptop rather than contend. **Do not use
  FastAPI `BackgroundTasks`** — those are tied to the request lifecycle and are
  wrong for multi-minute jobs. On submit, the route creates the Job (status
  `queued`), submits it to the executor, and returns immediately.
- Execution: the worker sets status `running`, then calls
  `run_youtube_game(...)` for `kind == "single"` or `run_playlist_batch(...)` for
  `kind == "playlist"`, passing a `stage_progress` callback that appends to
  `job.stages`, updates `job.current_stage`, and routes `"warning …"` strings into
  `job.warnings` (all under the store lock). On success set `result` and status
  `done`; on any exception set `error` (str) and status `error`. Never let the
  worker thread crash silently — wrap the body in try/except.

**Routes.**
- `GET /` → `index.html`: a form (URL text field + single/playlist selector +
  submit) and the recent-jobs list (`JobStore.list()` rendered as `_job_row`
  partials).
- `POST /jobs` (form-encoded `url`, `kind`) → validate `url` is non-empty and
  looks like an http(s) URL (reject otherwise with a 400 + inline error partial);
  create + enqueue the job; return the `_job_row` partial for the new job (HTMX
  swaps it into the list). The row polls its own status.
- `GET /jobs/{id}` → `job_detail.html`: full stage log, warnings, and — when
  `done` — a link forward to the results page (item 47 provides
  `/jobs/{id}/results`; for 39a just link to it / show the raw result dict).
  404 if unknown id.
- `GET /jobs/{id}/status` → `_job_status.html` partial for HTMX polling. While
  `queued`/`running`, include `hx-get` + `hx-trigger="every 1s"` so it keeps
  polling; when `done`/`error`, render the terminal state **without** the polling
  trigger so HTMX stops. 404 if unknown id.

**CLI.** Add a `serve` subparser: `sidelinehd serve [--host 127.0.0.1]
[--port 8000] [--reload]`. It imports `create_app` and runs `uvicorn.run(...)`.
Bind `127.0.0.1` by default (local-first, no auth — never default to `0.0.0.0`).
Print the `http://127.0.0.1:PORT` URL on startup.

**Security.** No auth, single user, loopback bind only. Exports carry jersey
numbers, not names, so nothing new leaves the machine — but do not add any route
that renders roster *names*; the send-feedback sanitizer (item 38 / phase 39e) is
the only sanctioned egress path. Vendored assets only (no CDN).

**Testing** (FastAPI `TestClient`; never hit the network or OCR):
- Monkeypatch `run_youtube_game` / `run_playlist_batch` with fakes that emit a
  few stage strings (including one `"warning field-never-read: right_score"`) and
  return a canned result dict.
- `POST /jobs` with a valid single URL → 200, job appears in `JobStore`,
  transitions `queued → running → done` (drive the executor to completion
  deterministically — e.g. inject a synchronous/inline executor in tests).
- `GET /jobs/{id}/status` reflects stages and surfaces the warning; the terminal
  partial omits the `every 1s` trigger.
- `kind == "playlist"` dispatches to `run_playlist_batch`; a fake that raises sets
  status `error` with the message.
- `POST /jobs` with an empty/invalid URL → 400 + inline error, no job created.
- `create_app()` builds without binding a socket; `serve` wiring is unit-tested by
  asserting the app factory + uvicorn args, not by starting a server.

**Acceptance criteria.**
1. `sidelinehd serve` starts a loopback FastAPI app; `/` renders the submit form.
2. Submitting a single URL or playlist creates a background job that runs the real
   pipeline via the existing workflow functions (verified with fakes in tests).
3. Job status (including item 45 warnings) streams to the browser via HTMX polling
   and stops polling at a terminal state.
4. Core CLI install is unaffected; web deps live behind the `[web]` extra.
5. Full suite passes; no real player names introduced in fixtures or templates.

**Out of scope (later phases):** rich results/paste kits (item 47), corrections
UI (39c), roster UI (39d), feedback egress (39e), SQLite persistence.

### 47. Local Web App — Phase 39b: Results + Multi-Game Paste Kits

Status: Done (Pass 16, implemented by Fable 5; approved. Criterion #2 — per-game review summary — is gated on item 48.)
Source: Promoted from item 39 (epic), phase 39b. Depends on item 46 and item 20 (Done).

The presentation slice: for a completed job, render a results page that stacks one
copy-kit block per game (chapters + at-bat jump links with one-click copy),
alongside the review-report summary. For a playlist job, one block per game in
batch order. **This is a thin view over existing renderers — reuse, do not
rebuild the paste kit or the report.**

**Reuse targets (do not reimplement).**
- `render_publish_kit_html(...)` in [publish.py:125](src/sidelinehd_extractor/publish.py#L125)
  already renders export text into HTML with working one-click copy buttons
  (`navigator.clipboard`). Call it per game and embed the fragments. If it renders
  a full standalone document rather than an embeddable fragment, refactor it to
  expose a fragment-returning helper and have the existing callers wrap it — do
  **not** copy-paste its clipboard JS into the web layer.
- `write_review_report` / `render_review_report` in
  [review_report.py](src/sidelinehd_extractor/review_report.py) for the flagged-event
  count and the "Run Warnings" section (item 45). Render its Markdown to the page
  (or surface the structured counts) rather than recomputing.
- Job `result` from item 46 provides the run dir(s) and export paths; read the
  already-written `full_chapters.txt` / at-bat / `review_report.md` artifacts —
  do not re-run detection.

**Route.**
- `GET /jobs/{id}/results` → `results.html`. For a single job, one game block; for
  a playlist job, iterate the batch entries (reuse the per-entry result shape
  `run_playlist_batch` returns) and stack a block per successful game, with a
  clearly-marked error block for any entry that failed. 404 if unknown id; if the
  job is not yet `done`, redirect/link back to `/jobs/{id}`.
- Wire the "view results" link from item 46's `job_detail.html` to this route.

**Each game block contains:** game label (playlist title/index or video name),
the chapters copy kit and the at-bats copy kit (via `render_publish_kit_html`),
the flagged-event count, and the run-warnings list. Keep names out of it — blocks
show jersey numbers and timestamps only, matching current export content.

**Testing** (`TestClient`, fakes):
- Build a fake `done` job whose `result` points at a temp run dir containing
  `full_chapters.txt`, the at-bats file, and `review_report.md` (with a Run
  Warnings section). Assert the page contains the chapters, the at-bats, the
  copy-button markup from `render_publish_kit_html`, the flagged count, and the
  warning text.
- Playlist job with two entries (one success, one failure) → two blocks, the
  failure rendered as an error block, in batch order.
- `GET /jobs/{id}/results` on a not-yet-done job links back to the detail page;
  unknown id → 404.
- If `render_publish_kit_html` is refactored to a fragment helper, its existing
  publish tests still pass unchanged.

**Acceptance criteria.**
1. A completed single or playlist job renders a results page with one copy-kit
   block per game, each with functioning one-click copy (reusing
   `render_publish_kit_html`).
2. The review-report flagged count and item 45 run warnings appear per game.
3. Batch results preserve order and clearly mark failed entries.
4. No new clipboard/paste logic and no re-run of the pipeline; artifacts are read
   from the run dir.
5. Full suite passes; publish reuse refactor (if any) leaves existing tests green;
   no real player names in fixtures.

**Out of scope:** corrections editing (39c), roster editing (39d), feedback egress
(39e).

**Post-review note (Pass 16).** Criterion #2 is implemented but **inert in
production**: `run_game`/`run_youtube_game` never write `review_report.md` — only
the `review-report` CLI command does — so real web jobs always hit the graceful
"No review report found" path. The results-page code is correct and reads the
artifact when present; the missing producer is tracked as **item 48**. Fable 5
followed the design's "read already-written artifacts; do not recompute" rule and
flagged the gap rather than silently adding generation.

### 48. Generate `review_report.md` During Runs

Status: Ready for review (implemented by Fable 5)
Source: Item 47 review (Pass 16). Depends on item 45 (manifest warnings, Done) and
item 47 (consumer, Done).

The run pipeline writes `samples.jsonl` / `states.jsonl` / `events.jsonl` /
`manifest.json` but **not** `review_report.md`; only the `review-report` CLI
command produces it. So item 47's per-game review summary (flagged count + item 45
run warnings) is dark for every real web job. Make the review report a standard
run artifact.

**Change.** After the export step in `run_game` (so `run_youtube_game` and each
`run_playlist_batch` entry inherit it), call the existing
`write_review_report(run_dir)` — which reads the already-written
events/states/samples/manifest and writes `review_report.md`. No detection is
recomputed; this is the same call the CLI already makes. The `review-report` CLI
command then becomes a re-render/relocation convenience rather than the sole
producer.

**Placement + safety.**
- Generate after exports are written and after the manifest is finalized (the
  report reads manifest warnings), so the artifact reflects the completed run.
- **Do not let report generation fail the run.** Wrap it so an error degrades
  (surface via the existing `stage_progress` callback, e.g. a
  `warning review-report-failed` stage) but the run still returns its result.
- Optional `write_review_report: bool = True` knob threaded like the other run
  flags if opt-out is ever wanted; default on.

**Testing.**
- `run_game` on a fixture leaves `review_report.md` in the run dir with the
  expected flagged count / warnings.
- The item 47 results-page test can drop its hand-written `review_report.md`
  fixture and instead assert the count/warnings come from a report generated by a
  real (faked-OCR) run — an end-to-end check that criterion #2 now lights up.
- Existing `review-report` CLI tests still pass unchanged.
- A forced report-generation failure degrades without failing the run.

**Acceptance criteria.**
1. A completed `run_game` / `run_youtube_game` leaves `review_report.md` in the run
   dir.
2. Item 47's results page shows the per-game flagged count + item 45 warnings for
   real jobs (no longer the degraded path).
3. Report-generation failure degrades gracefully; the run still succeeds.
4. `review-report` CLI behavior is unchanged.

### 49. Local Web App — Phase 39c: Exception Review + Corrections UI

Status: Ready for review (implemented by Fable 5)
Source: Promoted from item 39 (epic), phase 39c. Depends on item 46 (web skeleton,
Done), item 47 (results page, Done), item 48 (review report as a run artifact,
Ready for Review) — and the existing `review.py` / `corrections.py` / `exports.py`.

A browser front-end for the corrections workflow that today is a hand-edited CSV.
For a completed run, show the **flagged events** the review pass surfaced, let the
user resolve each one — edit a field, delete a false positive, or add a missing
event — persist those resolutions to the run's corrections file, and **re-export
the chapters/at-bats with corrections applied**, without re-running download,
OCR, or detection. The re-exported files are the same ones item 47's results page
reads, so a correction immediately improves the copy kits.

**Reuse the pipeline; do not reinvent correction or export logic.** Every piece
below already exists:
- `collect_event_review_rows(events, kind="all", options, roster)` →
  `List[ReviewRow(index, event, flags)]` in [review.py](src/sidelinehd_extractor/review.py)
  is the flag source. A row is "flagged" when `row.flags` is non-empty.
- `EventCorrection` + `load_event_corrections(path)` + `apply_event_corrections(events, corrections)`
  in [corrections.py](src/sidelinehd_extractor/corrections.py) are the correction
  model, reader, and applier. Do not write a new correction format.
- `load_events(events.jsonl)` + `export_youtube_chapters(...)` /
  `export_at_bat_comment(...)` in [exports.py](src/sidelinehd_extractor/exports.py)
  are the re-export path. `run_game` already does exactly
  `load_events → apply_event_corrections → export_*` (see
  [workflow.py](src/sidelinehd_extractor/workflow.py) ~L155-176).

**Correction semantics (from `corrections.py`, do not change them).**
- **Edit** an event: `field` ∈ {`label`, `timestamp_seconds`, `player_number`,
  `player_name`, `inning`, `half`, `event_type`}, with the new value in `value`.
- **Delete** a false positive: `field` ∈ {`delete`, `remove`, `skip`}.
- **Add** a missing event: `field` ∈ {`add`, `insert`}, requires `event_type` and
  a `label` (or `player_number`/`player_name` to synthesize one).
- A correction targets an event by nearest `timestamp_seconds` within
  `match_window_seconds` (default 0.5), optionally constrained by `event_type`.
  **The UI must pre-fill the corrected event's exact `timestamp_seconds` and
  `event_type`** so each correction targets precisely the intended event.

**Persistence — corrections live in the run dir.**
- Write corrections to `<run_dir>/corrections.csv`. This makes them a run artifact:
  diffable, and directly usable by the existing CLI
  (`export --corrections <run_dir>/corrections.csv`). The web reads this file on
  load and rewrites it on each change.
- **Canonical columns** (superset that `load_event_corrections` already accepts):
  `event_type,timestamp,field,value,match_window_seconds,reason,label,player_number,player_name,inning,half`.
  Emit the full header; leave unused cells blank.
- **De-dup on write** so the file stays clean and idempotent: key a correction by
  `(event_type, timestamp_seconds, field)`. Saving a correction with an existing
  key replaces that row rather than appending a duplicate; a "clear correction"
  removes it. (Deletes and adds are keyed the same way; a second delete of the
  same target is a no-op replace.) Never let the web corrupt a hand-edited file:
  round-trip through `load_event_corrections` / the writer, preserving unknown-but-
  valid rows.

**Faithful re-export — reuse the run's export options (altitude).** The exports
`run_game` produced depend on formatting options (`include_chapter_intro`,
`chapter_intro_label`, `include_inning_score`, `include_at_bat_inning_headers`,
…). Re-exporting with different options would silently reformat the files.
Resolve this by **extracting `run_game`'s corrections-apply → export → review-report
tail into one shared helper** — e.g. `finalize_run_exports(run_dir, *, corrections,
output_prefix, export_options, roster)` in `workflow.py` — and calling it from both
`run_game` and the web corrections endpoint. Persist the `export_options` the run
used into `manifest.json` (a small section) so the helper can re-export faithfully
even after a restart. This generalizes the mechanism instead of special-casing the
web path, and it means the re-export and the original run can never drift. For v1
the persisted values equal `run_game`'s defaults (web jobs use them), but persisting
them now is what makes the helper self-sufficient.
- After re-export, also regenerate `review_report.md` via item 48's path (same
  helper), so the results page's flagged count/warnings and the review UI's flag
  list both reflect the corrected events.

**Roster for flags.** `collect_event_review_rows` takes the roster to compute
roster-aware flags (`missing-player`, `unrostered-card-number=…`, etc.). Load it
the same way the job did — via `default_pipeline_kwargs()` / the project config
(item 46). Record the roster path in the manifest if convenient so the review page
is exact; otherwise re-derive from config and note the assumption.

**Routes (extend the item 46/47 FastAPI app).**
- `GET /jobs/{id}/review` → `review.html`: the exception review page for a `done`
  job. List the flagged events (default) — index, `mm:ss` timestamp, event type,
  current label, player number/name, and the `flags`. Each row carries an inline
  correction form (edit fields pre-filled from the event; a delete button) posting
  via HTMX. A separate "add missing event" form. A toggle to show all events, not
  just flagged. Link to `/jobs/{id}/results`. 404 on unknown id; if not `done`,
  link back to `/jobs/{id}`.
- `POST /jobs/{id}/corrections` → apply one correction: validate, upsert it into
  `<run_dir>/corrections.csv` (de-dup by key), re-apply all corrections + re-export
  + regenerate the review report via the shared helper, then return the refreshed
  flagged-events partial (HTMX swaps it) showing the now-corrected flags. On a bad
  correction (e.g. no event within the match window, invalid `event_type`), return
  a 400 inline error and do not modify the file.
- `POST /jobs/{id}/corrections/clear` (or a `field=""`/remove action) → drop a
  correction row by key and re-export.
- Keep player names **local only**: the review UI may display OCR'd/roster names
  (single-user local tool), but nothing here writes names to anything that leaves
  the machine — that egress path is item 38 / phase 39e exclusively.

**Testing** (`TestClient` + fakes; never re-run OCR/detection):
- Seed a temp run dir with a real `events.jsonl` (a mix that produces at least one
  flag) and a manifest; drive the routes against it.
- `GET /jobs/{id}/review` lists the flagged events with their flags; the show-all
  toggle includes unflagged events.
- `POST` an **edit** (e.g. fix a `player_number`) → `corrections.csv` gains one
  row with the canonical columns, the exports are rewritten with the corrected
  value, and the refreshed partial shows the flag resolved.
- `POST` a **delete** of a false positive → event drops from exports; `POST` an
  **add** → event appears in exports at the right spot.
- Re-`POST` the same edit with a new value → the CSV row is replaced, not
  duplicated (de-dup by key); `clear` removes it and reverts the export.
- A correction that matches no event in-window → 400 inline error, file unchanged.
- Round-trip safety: loading a hand-written `corrections.csv`, saving one change,
  and reloading preserves the other rows.
- The extracted `finalize_run_exports` helper: `run_game`'s existing export/review
  tests still pass unchanged (behavior-preserving extraction), and a direct test
  re-exports a run dir faithfully using manifest-persisted options.

**Acceptance criteria.**
1. For a completed run, `/jobs/{id}/review` shows the review-flagged events with
   their flags, reusing `collect_event_review_rows`.
2. Editing, deleting, or adding an event writes a valid `<run_dir>/corrections.csv`
   (loadable by `load_event_corrections`), de-duplicated by key, and re-exports the
   chapters/at-bats — no download/OCR/detection re-run.
3. The re-exported files match the run's original formatting (shared helper +
   manifest-persisted export options); item 47's results page reflects the
   corrections, and the review page's flags recompute on the corrected events.
4. Bad corrections are rejected with an inline error and leave the file intact;
   hand-edited rows survive round-trips.
5. No player names leave the machine; full suite passes; no real names in fixtures.

**Out of scope (later phases):** roster editing (39d), feedback egress (39e),
undo/history beyond the flat corrections file, and exposing export-format toggles
in the UI (the options are persisted and reused, not yet user-editable).

### 50. Local Web App — Phase 39d: Roster Management UI

Status: Ready for review (implemented on branch `impl/item-50` by Fable 5)
Source: Promoted from item 39 (epic), phase 39d. Depends on item 46 (web skeleton,
Done) and the existing `roster.py` / `config.py` roster machinery. Independent of
the OCR track and of items 48/49.

A browser front-end for the roster CSVs that today are created by
`make-roster` / `setup-roster` (item 27) and hand-edited. Let a user view, create,
edit, and delete the roster(s) under `rosters/`, using the **paste-a-team-list**
flow the CLI already supports, plus per-player row editing. A better roster
directly improves detection (roster-aware review flags, name resolution), so this
closes the loop with item 49's review UI.

**Reuse the roster machinery; do not reinvent parsing or the CSV format.**
- `parse_team_list(text, team_name)` in [roster.py](src/sidelinehd_extractor/roster.py)
  parses pasted `#26 Amelia V.` lines into a `Roster` (dedupes numbers, raises on
  bad lines) — this is the create/bulk-edit path.
- `write_roster_csv(roster, output_path)` writes the exact CSV `load_roster`
  consumes (`number,full_name,preferred_name,display_name,aliases`).
- `load_roster_csv(path, team_name)` / `load_roster(path)` in
  [config.py](src/sidelinehd_extractor/config.py) read existing rosters.
- `default_roster_path(team_name)` → `rosters/<slug>.csv` is the canonical location.
- `RosterPlayer` fields (`number`, `full_name`, `preferred_name`, `display_name`,
  `aliases`) are the row model.
- The project config (`sidelinehd.cfg`, item 28) records the active roster path +
  team name; surface which roster is the configured default and allow setting it.

**Persistence.** Rosters remain plain CSVs under `rosters/`, one per team, the same
files the CLI and pipeline already use. The UI reads and rewrites them in place via
`write_roster_csv` — no new store, no DB. Writes go through `parse_team_list` /
`write_roster_csv` so the file stays in the canonical format and dedupe/validation
is enforced centrally (never hand-serialize CSV in the web layer).

**Routes (extend the item 46 FastAPI app).**
- `GET /rosters` → `rosters.html`: list the CSVs under `rosters/` (team name +
  player count + which one is the configured default), with links to edit each and
  a "new roster" form (team name + paste box).
- `GET /rosters/{slug}` → `roster_edit.html`: the roster's players in an editable
  table (number, full name, preferred name, aliases), an add-player row, a
  per-row delete, and a "replace from pasted list" box (re-`parse_team_list`).
- `POST /rosters` → create from a team name + pasted list: `parse_team_list` →
  `write_roster_csv(default_roster_path(team_name))`. On a parse error (bad line,
  duplicate number) return a 400 inline error naming the line; create nothing.
- `POST /rosters/{slug}` → save edits: rebuild the `Roster` from the submitted rows
  (or the pasted list) and `write_roster_csv` back to the same path. Validate
  numbers are unique and names non-empty; 400 inline on failure, file untouched.
- `POST /rosters/{slug}/delete` → remove the CSV (guard: confirm; do not delete a
  roster referenced as the config default without a warning).
- Optionally `POST /rosters/{slug}/set-default` → update `sidelinehd.cfg` to point
  at this roster (reuse item 28's config writer; do not hand-edit the cfg).

**Security — this UI handles real names, all local.** Rosters are private local
files under `rosters/` (already git-ignored / never committed per the project
security constraint). Editing and displaying real names in a single-user localhost
tool is expected and fine. The hard rule: **nothing in this UI writes names to any
egress surface** — the only sanctioned outbound path is item 51 / 39e's sanitizer.
Do not add roster data to job results, the feedback log, or any shared output here.

**Testing** (`TestClient`; temp `rosters/` dir):
- `GET /rosters` lists existing CSVs with counts and marks the configured default.
- Create via paste → a CSV appears at `default_roster_path`, loadable by
  `load_roster_csv`, with the parsed players.
- Edit a player (change a number/name) and save → the CSV round-trips through
  `write_roster_csv` with the change; reload shows it.
- Duplicate number / unparseable line → 400 inline error, no write.
- Delete removes the file; set-default updates `sidelinehd.cfg` (assert via the
  config loader, not by reading raw text).
- No real names in fixtures — use placeholders like `#26 Amelia V.`.

**Acceptance criteria.**
1. `/rosters` lists the roster CSVs; a user can create one from a pasted team list
   (via `parse_team_list` + `write_roster_csv`) at the canonical path.
2. A user can edit/add/delete players and save back to the same CSV in the format
   `load_roster` consumes; validation errors are shown inline and never corrupt the
   file.
3. The configured default roster is visible and settable (through item 28's config
   writer).
4. All roster data stays local; no names reach any egress surface; full suite
   passes with placeholder-only fixtures.

**Out of scope:** multi-team merging, alias auto-suggestion from OCR, and wiring a
just-edited roster into an already-completed run's review (item 49 already re-reads
the configured roster on each review render).

### 51. Local Web App — Phase 39e: Send-Feedback UI

Status: Ready for review.
Source: Promoted from item 39 (epic), phase 39e. Depends on item 46 (web skeleton,
Done) and **item 38 (feedback log)** — which is the sanitizer this UI wraps. Do
not start until item 38 is approved and on `main`.

The single sanctioned egress surface: for a completed run, preview the **sanitized**
Markdown feedback log in the browser, let the user add a note, then hand off to a
GitHub issue or email with the sanitized text pre-filled. **No new sanitization
logic lives in the web layer** — it renders exactly what item 38 produces.

**Reuse item 38 end to end; add nothing to the sanitization path.**
- `load_feedback_data(run_path, note)` → `build_name_sanitizer(data)` →
  `sanitize_feedback(data, sanitizer)` → `render_feedback_log(log)` in
  [feedback.py](src/sidelinehd_extractor/feedback.py) is the whole pipeline. The
  browser only ever receives the output of `render_feedback_log(...)` — i.e. the
  **post-redaction** Markdown (player names replaced with pseudonyms, jersey
  numbers kept).
- `write_feedback_log(run_path, note=…)` writes `feedback.md` to the run dir; the
  UI can persist alongside previewing.

**The security invariant (state it in code and the design).** Raw player names
must never reach the egress surface. The route builds the preview by calling the
**sanitizer pipeline only** — it must not read roster names, `events.jsonl`
labels, or samples directly into the response. Add a test that seeds a run whose
artifacts contain a known real-looking name and asserts that name is **absent**
from the preview response, the GitHub-issue body, and the email body, while the
jersey number is present. This is the one place a bug leaks PII, so the test is
mandatory, not optional.

**Routes (extend the item 46 FastAPI app).**
- `GET /jobs/{id}/feedback` → `feedback.html`: render the sanitized log
  (`render_feedback_log`) in a read-only preview panel, a note textarea, and two
  actions — "Open GitHub issue" and "Copy for email" / "Open email". 404 unknown
  id; if not `done`, link back to `/jobs/{id}`.
- `POST /jobs/{id}/feedback/preview` → re-render the sanitized preview with the
  submitted note included (the note is user-authored text; include it verbatim in
  the sanitized log via item 38's `note` path — do not run names through it, but do
  not sanitize the user's own words either).
- **Hand-off (no server-side network calls).** Build client-side links from the
  sanitized text:
  - GitHub issue: a prefilled `https://github.com/<repo>/issues/new?title=…&body=…`
    URL with the sanitized Markdown URL-encoded as the body (repo from
    `PROJECT_URL`). Opens in a new tab; the user reviews and submits.
  - Email: a `mailto:?subject=…&body=…` link (or a one-click "copy" of the
    sanitized text) — long bodies may exceed `mailto` limits, so provide copy as
    the reliable path and `mailto` as convenience.
  The app itself performs **no outbound request** — it only constructs links the
  user chooses to open, keeping the local-first, no-egress-without-consent posture.

**Testing** (`TestClient`, fakes):
- Seed a run dir with manifest/events/samples containing a placeholder that looks
  like a real name; `GET /jobs/{id}/feedback` preview contains the pseudonym and
  the jersey number and **not** the seeded name (the mandatory leak test, repeated
  for the issue-body and email-body strings).
- The note is included in the rendered preview.
- The GitHub-issue link is well-formed (URL-encoded sanitized body, correct repo);
  the email/copy path carries the same sanitized text.
- Not-done job links back; unknown id → 404.
- No server-side HTTP is made (assert the handler doesn't call out).

**Acceptance criteria.**
1. For a completed run, `/jobs/{id}/feedback` previews the sanitized feedback log
   (item 38's `render_feedback_log` output) with an editable note.
2. The user can hand the **sanitized** text to a GitHub issue (prefilled URL) or
   email/clipboard; the app makes no outbound request itself.
3. A real-looking name seeded into the run artifacts never appears in the preview
   or either hand-off body; the jersey number does (mandatory PII-leak test).
4. No new sanitization logic in the web layer; full suite passes.

**Out of scope:** authenticated GitHub API submission, attachments, and any
telemetry — hand-off is user-initiated links only.

### 52. Persist Roster Display Name (round-trip pretty team name)

Status: Ready to implement
Source: Item 50 review (Pass 19). Small, contained; not an item 50 defect —
surfaces a pre-existing roster-CSV format limitation.

The roster CSV stores only `number,full_name,preferred_name,display_name,aliases`
(no team name), and `load_roster_csv` falls back to `team_name or source.stem`.
So creating **"St. Mary's 12U"** saves `st_mary_s_12u.csv` and, on reload, the UI
(and CLI) display **"st_mary_s_12u"** — the pretty capitalization/spacing is lost.
Item 50's roster UI made this visible because it creates by pretty name then
re-displays the stem.

**Change.** Persist the roster's display/team name in the file so it survives a
round-trip, without breaking the existing header-based readers. Preferred
approach: write a leading comment line (e.g. `# team_name: St. Mary's 12U`) that
`write_roster_csv` emits and `load_roster_csv`/`load_roster` parse back, falling
back to the stem when absent (so old files still load). Keep the `csv.DictReader`
column contract unchanged. Touch points: `write_roster_csv`, `load_roster_csv`
(and `load_roster`/`make_roster_from_lines`); the web `create_roster` already has
the pretty name and just needs the writer to keep it. Verify `feedback.py`
`_roster_from_manifest` and any manifest roster snapshot still round-trip.

**Acceptance criteria.**
1. A roster created as "St. Mary's 12U" reloads (CLI and web) with team name
   "St. Mary's 12U", not the stem.
2. Roster files written before this change still load (stem fallback), and the
   `number,full_name,…` column contract is unchanged.
3. Full suite passes; placeholder-only fixtures.

**Implementation (2026-07-05, branch `impl/item-52`, by Fable 5, based on
`impl/item-55`) — Ready for review.** `write_roster_csv` emits a leading
`# team_name:` comment; `load_roster_csv` skips leading comments and resolves
explicit arg > header > stem. Old files unaffected; column contract unchanged.

### 53. Make the Declared `yt-dlp` Dependency Sufficient (module fallback)

Status: Ready for review.
Source: Live-fire prep (2026-07-03). Small.

`yt-dlp>=2025.1` is already a core dependency, so `pip install -e .` /
`.[web]` installs it — there is no manual install step. The gap is robustness:
`youtube.py` invokes the **`yt-dlp` console script** (`build_ytdlp_command` /
`build_ytdlp_playlist_command` default `executable=["yt-dlp"]`). In install
layouts where the module is importable but the script isn't on PATH (pipx, some
`--user`/CI setups), that subprocess raises a bare `FileNotFoundError` even though
the declared dependency is present.

**Change.** Resolve the yt-dlp invocation so the declared dependency is always
sufficient:
1. A helper (e.g. `default_ytdlp_executable()`) that returns `["yt-dlp"]` when the
   console script is found (`shutil.which("yt-dlp")`), else falls back to
   `[sys.executable, "-m", "yt_dlp"]` when the module is importable
   (`importlib.util.find_spec("yt_dlp")`).
2. If neither is available, raise a clear, actionable error ("yt-dlp is required
   and ships with this package — reinstall with `pip install -e .`") instead of a
   raw `FileNotFoundError`.
3. Route `build_ytdlp_command` / `build_ytdlp_playlist_command`'s default
   `executable` through the helper. Keep the explicit-`executable` override intact
   (tests pass a fake).

Do not add yt-dlp to `dependencies` again (already there) or pin it tighter —
yt-dlp needs to float so users can update it as YouTube changes.

**Testing.**
- `default_ytdlp_executable()` returns the script path when `which` finds it; the
  `python -m yt_dlp` form when only the module is importable; raises the actionable
  error when neither (monkeypatch `shutil.which` / `find_spec`).
- `build_ytdlp_command` uses the resolved default and still honors an explicit
  `executable` override.

**Acceptance criteria.**
1. With yt-dlp installed as a Python package but its console script not on PATH,
   the download path still runs (via `python -m yt_dlp`).
2. With yt-dlp entirely absent, the user gets a clear reinstall message, not a raw
   `FileNotFoundError`.
3. Existing youtube/download/batch tests pass unchanged.

### 54. Turnkey Web App — Zero-Friction Install, Launch, Stop, and Onboarding (Epic)

Status: Epic — phases promoted to numbered items with full designs when scheduled.
Source: Product owner (2026-07-03), from live-fire prep: the project owner — who
built the tool — could not start the web app unaided, and Tesseract/ffmpeg/yt-dlp
are external binaries a non-developer will not install by hand. This is the gate
between "usable by us" and "usable by a softball coach."

**Goal.** A non-technical user (a parent/coach with a SidelineHD channel) can
install, start, use, and stop the web app **without a terminal, without pip, and
without knowing what Tesseract or ffmpeg are.** The app explains itself. Failures
are actionable in-UI, never a stack trace. Aligns with the item 39 "local-first,
per-device install" goal and item 19 (packaging/CI).

**The dependency reality (the core problem).**
- `yt-dlp` — already pip-installed automatically (items 53/dependency). ✅
- `ffmpeg` — a system binary today, but **pip-installable as a bundled static
  build** via `imageio-ffmpeg` (`get_ffmpeg_exe()` returns a path) or
  `static-ffmpeg`. yt-dlp accepts `--ffmpeg-location`, so we can make ffmpeg
  automatic through pip and stop asking users to `brew install ffmpeg`.
- `tesseract` — the hard one: no clean official pip wheel bundling the binary +
  language data. Options: bundle it in the packaged app (phase 54d), or
  detect-and-guide with a one-line per-platform install (phase 54a). This is the
  only dep that can't be fully pip-automated short of app bundling.

**Phases** (each becomes its own item with a full design when picked up):
- **54a — Dependency doctor + auto-provisioning.** A preflight that runs on
  `start` and on the web app's first page: detect `yt-dlp`/`ffmpeg`/`tesseract`
  (reuse item 42's Tesseract version check); **auto-provide ffmpeg via a bundled
  pip build** and wire yt-dlp's `--ffmpeg-location` to it; for a missing Tesseract,
  show a clear in-UI card with the exact copy-paste install for the user's OS
  (`brew install tesseract` / winget / apt) and a "re-check" button — never a
  traceback. Everything degrades to actionable guidance.
- **54b — One-command launch + clean lifecycle.** `sidelinehd-extractor start`
  (friendly alias) that runs the doctor, starts the server, **auto-opens the
  browser** (`webbrowser.open`), prints "open http://127.0.0.1:8000 — press Ctrl+C
  here to stop," and shuts down gracefully. Handle "port already in use" and
  "already running" cleanly.
- **54c — In-app onboarding + plain language.** A first-run welcome/explainer:
  what the tool does, the four-step flow (roster → submit a game → results →
  send feedback), empty-state guidance on every page, plain-language labels
  (no "OCR"/"manifest"/"job" jargon in the primary UI), and a persistent "How this
  works" panel. Directly answers "I don't understand how it works."
  **Roster-first is a specific requirement (owner feedback, live-fire):** the
  submit page must explain *before the run* that adding the batting team's roster
  first improves name matching (the manifest snapshots the roster at run time, so
  a roster added afterward does not backfill), and offer a one-click path to add
  it — e.g. a prompt/link on the submit page when no roster is configured, and a
  paste box reachable from the submit flow rather than a separate "Manage rosters"
  detour. Making the roster easy to add and clearly recommended up front is part
  of 54c's done criteria.
- **54d — Packaged desktop app (the endgame).** A double-clickable macOS `.app`
  (py2app/PyInstaller) and a Windows installer that **bundle Python + all deps
  including Tesseract + language data**, with a menubar/tray control to start/stop
  the server and open the UI. No terminal, no pip, no brew — download and run.
  Depends on 54a/54b and item 19 (cross-platform packaging/CI).
- **54e — Non-developer quickstart docs.** Rewrite the README/quickstart for a
  coach, not a developer (screenshots, "download → double-click → paste your
  game," troubleshooting). Folds item 19's doc gaps in.

**Sequencing.** 54a → 54b → 54c deliver most of the value while staying
pip-installable (ffmpeg becomes automatic, launch becomes one command, the UI
teaches itself). 54d is the heavy lift that removes the terminal entirely; do it
once 54a–54c prove the flow and item 19 establishes packaging/CI. Capture concrete
friction from the current live-fire runs directly into 54a/54c acceptance criteria.

**Deliberately out of scope (for now):** auto-updating the packaged app, code
signing/notarization beyond what distribution requires (revisit at 54d), and the
hosted/cloud seam (still deferred; see the CSRF hardening note).

**Live-fire fixes (2026-07-05, branch `impl/turnkey-fixes`, by Fable 5) — Ready
for review.** A real 2.4h-game run exposed four turnkey failures, fixed in
priority order on one branch (each its own commit):

- **P1 — Packaged default template (critical).** `default_overlay_template()`
  returned a whole-frame stub, so an unconfigured run OCR'd frame mush and
  "succeeded" with zero events. The calibrated
  `sidelinehd_640x360_active` template (14 regions) now ships as package data
  (`sidelinehd_extractor/data/`) and is the built-in default; the full-frame
  stub survives only as the explicit `full_frame_overlay_template()` opt-in.
  Verified in the built wheel.
- **P2 — No-scoreboard health check (safety net).** `run_game` now runs
  `scoreboard_health_warning()` after every OCR run: zero events, or all of
  `left_score`/`right_score`/`count`/`inning` empty across the run, writes a
  manifest `health` section and emits a `warning no-scoreboard-detected` stage
  warning. The web app renders it as a loud red banner on job status, job
  detail, results blocks, and the game page. `no_ocr` runs are exempt.
- **P3 — OCR progress + live detail page.** `process_video`'s per-frame
  callback is wired through the web `JobRunner` into `Job.frames_done/_total`;
  the status partial shows "Processing: N / M frames (X%)" and the job-detail
  body is now an HTMX-polled partial (`/jobs/{id}/detail`) that live-updates
  the stage log in place.
- **P4 — Consolidated game page.** `GET /jobs/{id}/game?entry=N` combines copy
  kits, the inline flagged-exception editor (shared partials, page-aware
  swaps), a roster panel, and a one-click `POST /jobs/{id}/reexport`
  (corrections + current roster through `finalize_run_exports`). Done single
  jobs link straight to it; `/results` and `/review` remain for playlists and
  backward compatibility.
- **P5 — Template auto-detection** was *not* implemented; it is designed as
  item 55 (Ready to implement, pending architect validation of the design).

**Phases 54a + 54b (2026-07-05, branch `impl/turnkey-launch`, by Fable 5) —
Ready for review.**

- **54a — Automatic dependencies.** `imageio-ffmpeg` is now a core dependency;
  `resolve_ffmpeg_location()` in `youtube.py` prefers a system `ffmpeg` on
  PATH, falls back to the pip-bundled static build, else `None` — never
  raises (mirrors the item-53 yt-dlp resolver). Both yt-dlp command builders
  append `--ffmpeg-location <path>` automatically when resolved. New
  `preflight.py` module: `preflight_dependencies()` reports
  yt-dlp/ffmpeg/tesseract with ok/detail and an OS-specific install hint,
  reusing item 53's resolver and item 42's `tesseract_version()`. The web
  index renders a plain-language setup card (exact copy-paste install + a
  Re-check button) only when something is missing; healthy installs show
  nothing.
- **54b — One-command launch.** New `sidelinehd-extractor start` command:
  prints the preflight report (a missing Tesseract prints its install hint
  but does not block), refuses a busy port with a clear `--port` suggestion,
  prints "Open http://127.0.0.1:PORT — press Ctrl+C here to stop.",
  auto-opens the browser (`--no-browser` to opt out), and shuts down cleanly
  on Ctrl+C. `serve` is unchanged for development use.
- Verified live: real launch, index 200, port-collision exit, clean Ctrl+C.

### 55. Overlay Template Auto-Detection (Probe Pass)

Source: Item 54 live-fire follow-up (P5), 2026-07-05. Design drafted by the
implementer at the product owner's direction; **architect should validate
before implementation.**
Status: Ready to implement

**Goal.** The user never configures a template. Before the full OCR pass, the
pipeline samples a few frames, scores each known SidelineHD layout against
them, and auto-selects the best match — falling back to the packaged default
(item 54 P1) with a visible notice when nothing scores well.

**Design.**

1. **Candidate registry.** A packaged list of candidate templates under
   `sidelinehd_extractor/data/`: today just `sidelinehd_640x360_active`
   (Default/Bottom/Flip-ON); item 26's nine additional layout templates join
   the registry as they are calibrated (Default vs Minimal × position/flip).
   New helper `candidate_overlay_templates() -> list[OverlayTemplate]` in
   `config.py`.
2. **Probe sampling.** New `probe_template(video_path, candidates, ocr,
   probe_timestamps=None)` in a new `template_probe.py`. Sample ~5 frames
   spread across the first third of the video (e.g. 10%, 15%, 20%, 25%, 30% of
   duration — avoids pregame dead air at 0:00 while staying cheap). Reuse
   `read_frames_at` + `crop_frame`; do NOT write a run dir.
3. **Scoring.** For each candidate, OCR only the key scorebug regions
   (`left_score`, `right_score`, `count`, `inning`, plus `batter_card_name`
   when present) on each probe frame. Score = fraction of (region × frame)
   reads that are *valid* for that field: scores parse as small ints (0–30),
   `count` matches the `B-S` pattern, `inning` matches `T#`/`B#`/arrow forms —
   reuse the existing per-field normalizers in `state.py`/`ocr.py` rather than
   new validators.
4. **Selection.** Pick the highest-scoring candidate above a floor (e.g.
   ≥ 0.25 valid-read rate); ties break toward the packaged default. Below the
   floor, keep the default and emit `warning template-autodetect-low-score`
   (surfaces via the item 54 P2 plumbing). Record the chosen template name and
   per-candidate scores in the manifest (`template_autodetect` section).
5. **Wiring.** `run_game`/`run_youtube_game` gain
   `auto_detect_template: bool = True` (only consulted when `template is
   None`); the web app's `default_pipeline_kwargs` keeps `template=None` so
   web runs probe automatically. CLI `--template` always wins; add
   `--no-auto-template` to force the packaged default.

**Acceptance criteria.**
- With one candidate, an unconfigured run still selects it and records the
  probe scores in the manifest.
- A video that matches no candidate keeps the default and emits the low-score
  warning (test with stubbed OCR returning garbage).
- Probe adds ≤ ~30s to a 2.4h run (5 frames × ≤ 15 regions).
- No run-dir artifacts from the probe; manifest records name + scores.
- Unit tests: scoring math with stubbed OCR; selection floor; tie-break.

**Edge cases.** Very short videos (< 10 min): probe at fixed 30s intervals
instead of percentages. Videos where the overlay appears late (pregame scenes):
low probe scores are acceptable — the P2 health check still catches a dead
run. Do not probe in `no_ocr` runs.

**Dependencies.** Item 26 supplies the additional layout templates; until it
lands, auto-detect is a one-candidate no-op that still validates the plumbing
and manifest recording.

**Implementation (2026-07-05, branch `impl/item-55`, by Fable 5) — Ready for
review.** Implemented per this design with all three validation refinements:
`template_probe.py` (5-frame probe, primary-field scoring with `inning`
de-weighted to 0.25, 0.25 floor, tie-break to the packaged default, manifest
`template_autodetect` section), `candidate_overlay_templates()` registry,
`auto_detect_template=True` threaded through `run_game`/`run_youtube_game`/
`run_playlist_batch`, CLI `--no-auto-template`. Probe failures degrade with a
warning; `no_ocr` runs never probe. Verified live on the real 2.4h stream:
1.9s probe, score 0.70, correct selection. 419 tests pass.

**Architect validation (Pass 23).** Approach approved. Three required changes
from live-fire evidence:

1. **De-weight `inning` in scoring (evidence-based).** On the real 640×360
   stream, the `inning` region misread even under the *correct* template
   (values like "72"/"43"/"720"), while `left_score`/`right_score`/`count` read
   148–179/181. Including `inning` at equal weight would penalize the right
   template. Score primarily on `left_score`, `right_score`, `count`; treat
   `inning` (and `batter_card_name`) as low-weight tie-breakers, not gates. This
   also protects the ≥0.25 floor from a single unreliable field.
2. **Frame the immediate deliverable as a pre-run fail-fast guard, not
   multi-layout selection.** With one candidate, selection is a no-op — but
   probing the single known template *before* the 40-minute OCR pass and warning
   on a low score catches a mismatched overlay up front (a strict improvement
   over item 54 P2, which only catches it after the full run wastes ~40 min).
   That standalone value justifies building it now; multi-layout selection
   matures as item 26 adds candidates. The low-score warning must say the run
   *can still proceed* on the default — don't hard-block.
3. **Cost note:** probe cost scales with candidate count (5 frames × ~15 regions
   × N). Fine at N=1; when item 26 brings N≈10, cap probing to the three scoring
   fields and keep frames at 5 so the probe stays well under a minute.

Sequencing: Ready to implement now for the fail-fast value; it blocks nothing,
and item 26 unlocks its full selection value. Note (separate follow-up): the
`inning` misread on real 640×360 streams is its own calibration bug worth a small
item — the current `inning` region likely overlaps adjacent digits.

### 57. Persistent Run History (view completed runs across restarts)

Status: Ready to implement — HIGH priority (breaks the basic local flow)
Source: Live-fire (2026-07-05). The web JobStore is in-memory, so after the app
restarts, every completed run 404s in the UI even though its artifacts are intact
on disk (`runs/<...>/` with events.jsonl + exports + manifest). A user who runs a
game, closes the app, and reopens it loses access to results — unacceptable for a
start/stop local tool. (Confirmed: a real 62-event run became unviewable purely
because the server was restarted.)

**Design.** Make `runs/` the source of truth the UI reads, rather than only the
ephemeral in-memory store.
1. `rehydrate_jobs_from_runs(store, runs_dir)` — scan `runs/` for completed runs
   (has `events.jsonl` + `manifest.json`), reconstruct a done `Job` per run
   (kind=single; `result` = the `summarize_result` single-shape from run_dir +
   exports + event_count; recover a display label/date from the dir name/manifest
   youtube section), and seed the store. Skip incomplete/in-flight run dirs.
2. Call it at web-app startup (create_app / the `start` command) so the index lists
   past runs and `/game` `/results` `/review` `/feedback` all resolve for them.
3. De-dupe against live in-session jobs (don't double-list a run that's also a live
   job). Order newest-first.
5. **Legacy/incomplete runs:** only rehydrate runs with the COMPLETE modern
   artifact set (events + exports + manifest with the fields the pages read).
   Pre-web-app or partial run dirs that would render broken must be SKIPPED
   (hidden), not listed. A run with 0 events is skipped from the results list
   (nothing to show) but its health warning still applies where surfaced.
4. Playlist runs: rehydrate per-entry where the batch state file records them.

Keep it disk-first (runs/ is canonical); a SQLite index (the epic's original 39a
note) is NOT required for this — reconstructing from run dirs is simpler and
sufficient. A throwaway bridge (`scratch/serve_with_history.py`) already proves the
approach end-to-end.

**Acceptance criteria.**
1. After a restart, the index lists prior completed runs and their results/exports/
   review/feedback pages all load (no 404).
2. In-flight/partial run dirs are skipped; live jobs are not duplicated.
3. Recovered runs show a sensible label (team/date), not a raw hash.
4. No real names in fixtures; full suite + ruff green.

### 58. Exception Review Triage + Plain-Language Flags

Status: Ready to implement — HIGH (usability)
Source: Live-fire 2026-07-05. The review/game page flags nearly every at-bat, the
flags are cryptic (`possible-substitute`, `card-vs-lineup=batter_card=12 lineup=2`,
`lineup-recovered`), and the corrections the tool already made look correct — so
noise buries the few exceptions that need a human. The owner couldn't tell what
each flag meant or what to do.

**Design.**
1. **Triage each review flag into an action tier** (mapping in review.py / a new
   `review_triage.py`):
   - **needs-action** (tool could NOT resolve — user should fix): `missing-player`,
     `unrostered-card-number`, `garbled-card-name`, `ocr-number`.
   - **review** (tool resolved an ambiguity; glance advised): `card-vs-lineup`,
     `lineup-had-rostered-candidate`, `close-at-bat`, `repeat-player`.
   - **informational** (normal/success — usually ignore): `possible-substitute`
     (order jumps are normal with subs), `lineup-recovered` (a success signal).
2. **Default the review/game page to needs-action (+ review) only**, with an
   at-a-glance summary ("3 need your attention · 40 look fine") and the
   informational flags collapsed behind the existing show-all toggle.
3. **Plain language per flag**: render a human title + one-line meaning +
   recommended action from a `{flag: (title, meaning, action)}` table, replacing
   the raw `flag=value` strings. E.g. `unrostered-card-number` -> "Jersey #N isn't
   on your roster — add it to the roster or fix the number." `possible-substitute`
   -> "Batting order jumped — normal for a substitution; only check if the batter
   looks wrong." Keep raw flags available on expand/tooltip; the review CSV/report
   is unchanged.

Note (separate, not required here): the volume of `possible-substitute` suggests
item 32's order validator over-fires; tuning it is its own detection item — triage
fixes the UX regardless.

**Acceptance criteria.**
1. The page defaults to only likely-action exceptions with a clear count summary;
   informational flags are collapsed, not deleted.
2. Every shown flag has a plain-language title + meaning + action; no raw
   `flag=value` jargon in the default view.
3. Unit tests cover the tier mapping for each known flag.
4. Placeholder-only fixtures; suite + ruff green.

### 59. Reduce `possible-substitute` False Positives (roster-confirmed batters)

Status: Ready for review (`impl/item-59`, Codex) — isolated to events.py (safe alongside Fable's webapp batch)
Source: Live-fire 2026-07-05. The order validator flags `possible-substitute`
whenever a batter's number is not in the inferred seed batting-order cycle
([events.py](src/sidelinehd_extractor/events.py) ~L334). The seed rarely captures
every player in youth ball, so legitimate, correctly-identified batters — often
**on the roster** — are flagged on nearly every at-bat, burying the genuinely
suspicious ones. (The owner confirmed the tool's picks were correct; the flag was
just noise.) This is the detection-side complement to item 58's UI triage.

**Change.** In `validate_batting_order`, when `player_number not in cycle`, do NOT
emit `possible-substitute` if the number is **roster-confirmed** (roster provided
and number present on it) — a known player is not a suspicious substitution. Keep
flagging genuinely-unexplained numbers (not in cycle AND not on roster). Optionally
also suppress a number seen ≥N times (a regular the seed missed) even without a
roster. Do not change the synthesized inferred-missing events or any other flag.

**Acceptance criteria.**
1. A roster-confirmed batter outside the seed cycle produces NO `possible-substitute`.
2. An unrostered/unknown number outside the cycle is still flagged.
3. Existing order-validator (item 32/34) tests stay green; add tests for both cases.
4. Placeholder-only fixtures; suite + ruff green.

## Discussion / Later Deliverables

### Web App — CSRF / same-origin hardening (deferred)

Source: Item 50 review (Pass 19).

None of the webapp's state-changing routes (job submit, corrections apply/clear,
roster create/save/delete/set-default across items 46–50) have CSRF or
same-origin protection, and there is no auth. On a single-user `localhost`
install this is the accepted posture, but a malicious page open in the user's
browser could POST to `127.0.0.1:<port>` and, e.g., delete a roster or mutate a
run. Low risk today; **must be addressed before the epic's "cloud/hosted" seam**
is ever taken (add a same-origin/Origin-header check or a CSRF token to all
mutating routes). Deletes/mutations should also prefer server-side confirmation
tokens over client-only `onsubmit` prompts if this hardens.

Reason to defer: local-first, single-user, loopback-bound, no auth by design; no
hosted deployment exists yet.



### 22. Detection Configuration Object

Source: Architectural note / Product backlog / CR-47

`detect_events` is accumulating parameters. A `DetectionConfig` dataclass would make defaults and per-game tuning easier.

Reason to defer:
- Current parameter count is still manageable.
- This is more valuable after one or two more detection knobs are proven necessary.

**Update (Pass 12, CR-47):** item 37's `run_playlist_batch` → `_run_playlist_entry` → `run_youtube_game` now re-declares ~30 of these knobs at each hop, so the "still manageable" rationale has weakened materially. When this item is picked up, scope it to a `DetectionConfig` (or `RunConfig`) dataclass threaded through `run_game`/`run_youtube_game`/`run_playlist_batch` so a new knob is a one-line change instead of a four-signature edit.

### 23. Correction Log Format

Source: Architectural note / Product backlog

CSV corrections are simple and practical today. JSONL correction events could be better for collaborative review later.

Reason to defer:
- CSV is currently easy to paste, diff, and explain.
- JSONL would add complexity before multi-reviewer workflows exist.

### 24. Package/Product Naming

Source: Architectural note / Product backlog

The current name is SidelineHD-specific, while the architecture could eventually support other overlays.

Reason to defer:
- The MVP is intentionally SidelineHD-focused.
- Renaming package/module paths too early creates churn without improving today’s workflow.

### 25. Half-Inning Progression Policy

Source: Architectural note / Product backlog

The current progression logic rejects skipped innings after an established previous half-inning. That is probably right for clean data, but it can hide chapters if OCR misses an entire inning.

Reason to defer:
- The current behavior prevents many false chapter jumps.
- This should be revisited with real examples where an inning is skipped mid-stream.

Potential future acceptance criteria:
- Add a documented policy for skipped innings.
- Optionally expose a strict/permissive chapter progression mode.
