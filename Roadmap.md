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
Status: Ready to implement

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
Status: Ready to implement

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

### 29. Score at Inning Transitions

Source: Product backlog
Status: Ready to implement

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
Status: Ready to design

The current 45-second minimum spacing is calibrated for unconfirmed detections and can suppress legitimate short at-bats in fast innings. On the `7Caey7n-4jA` 2nd inning, four rostered at-bats were missed that occurred 30–50 seconds apart.

**Design direction:** Apply shorter minimums when the candidate is strongly roster-confirmed:
- Roster-name match (`roster_match_source == "name"`): allow ~20 seconds
- Lineup-number roster match (`roster_match_source == "lineup_number"`): allow ~25 seconds
- Unrostered/noisy number: keep 45 seconds or higher

Intersects item 22 (DetectionConfig). Do not expose new CLI flags until defaults are validated across at least two previously correct games to avoid trading missed at-bats for false positives.

Acceptance criteria:
- `detect_events()` applies a shorter minimum spacing when the incoming candidate is roster-confirmed by name or lineup number.
- Unrostered/weak-signal spacing is unchanged from the current 45-second default.
- Previously validated games produce comparable or better at-bat lists.
- Synthetic fixture reproducing the `7Caey7n-4jA` short-spacing case validates the fix.

### 32. Batting-Order Continuity Validator

Source: Product backlog (CR-24 observation)
Status: Ready to design

Once a likely batting order is established (e.g. `26 → 2 → 13 → 5 → 4 → 24 → 15 → 3`), the expected next batter can be used to prefer or reject ambiguous candidates. This is the strongest possible signal for fast innings with OCR noise.

**Design note:** The order is only observable after a full inning, so the validator must operate in a post-detection pass, not inline. This may require restructuring `detect_events()` or adding a correction step. Design the architecture before implementing.

Acceptance criteria (to be filled in during design):
- Observed batting order is derivable from confirmed roster-matched at-bats within a game.
- A post-pass can correct or flag events that contradict the observed order.
- Architecture document or Roadmap update captures the chosen approach.

### 33. Full Lineup-Strip Digit-Run Parsing

Source: Product backlog (CR-24 observation)
Status: Ready to design

The fixed `batter_number` crop (item 21) recovers single lineup-strip numbers as a fallback. When OCR returns a fused digit run like `265` or `426`, the current parser discards it as an invalid single number. Those runs are often two adjacent roster numbers.

**Design direction:** When `parse_jersey_number()` fails on a multi-digit string, attempt a roster-aware split. Prefer splits that maximize matched roster numbers (`265` → `26` + `5` if both are rostered, over `2` + `65`). Only apply when a roster is present; discard ambiguous splits where multiple interpretations score equally.

Acceptance criteria (to be filled in during design):
- `parse_jersey_number()` or a new helper can attempt a roster-aware split of a multi-digit OCR string.
- Split is used only when exactly one rostered number is unambiguously resolved.
- Ambiguous splits (multiple valid candidates) are discarded, not guessed.

## Discussion / Later Deliverables

### 22. Detection Configuration Object

Source: Architectural note / Product backlog

`detect_events` is accumulating parameters. A `DetectionConfig` dataclass would make defaults and per-game tuning easier.

Reason to defer:
- Current parameter count is still manageable.
- This is more valuable after one or two more detection knobs are proven necessary.

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
