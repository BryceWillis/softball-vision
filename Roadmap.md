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
Status: Ready to implement

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

## Discussion / Later Deliverables

### 21. Detection Configuration Object

Source: Architectural note / Product backlog

`detect_events` is accumulating parameters. A `DetectionConfig` dataclass would make defaults and per-game tuning easier.

Reason to defer:
- Current parameter count is still manageable.
- This is more valuable after one or two more detection knobs are proven necessary.

### 22. Correction Log Format

Source: Architectural note / Product backlog

CSV corrections are simple and practical today. JSONL correction events could be better for collaborative review later.

Reason to defer:
- CSV is currently easy to paste, diff, and explain.
- JSONL would add complexity before multi-reviewer workflows exist.

### 23. Package/Product Naming

Source: Architectural note / Product backlog

The current name is SidelineHD-specific, while the architecture could eventually support other overlays.

Reason to defer:
- The MVP is intentionally SidelineHD-focused.
- Renaming package/module paths too early creates churn without improving today’s workflow.

### 24. Half-Inning Progression Policy

Source: Architectural note / Product backlog

The current progression logic rejects skipped innings after an established previous half-inning. That is probably right for clean data, but it can hide chapters if OCR misses an entire inning.

Reason to defer:
- The current behavior prevents many false chapter jumps.
- This should be revisited with real examples where an inning is skipped mid-stream.

Potential future acceptance criteria:
- Add a documented policy for skipped innings.
- Optionally expose a strict/permissive chapter progression mode.
