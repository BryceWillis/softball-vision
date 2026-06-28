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

Clean up small consistency issues before they spread.

Acceptance criteria:
- `workflow.export_paths` returns `Tuple[Path, Path]` or `tuple[Path, Path]`.
- Repeated newline-at-end export behavior is centralized in one helper.
- Duplicate `PathLike` aliases are consolidated or intentionally left local with a comment.
- Serialization assumptions around tuples-as-lists are documented or covered by tests if relied on.

### 11. Improve Publish Output Defaults

Source: Product backlog

Revisit the default `scratch/publish/` behavior so first-time users can find outputs easily outside the repo workflow.

Acceptance criteria:
- Decide whether paste kits should default inside the run directory or remain under `scratch/publish`.
- If the default changes, README and tests are updated.
- If the default stays, README makes the output location very obvious.

### 12. Generalize New Game Checklist

Source: Product backlog

Make `NEW_GAME_CHECKLIST.md` feel like a reusable template for other teams and users.

Acceptance criteria:
- Replace any team-specific examples with placeholders or clearly labeled examples.
- Include `--batting-half top|bottom` guidance.
- Include `review-report` in the review workflow.
- Keep the checklist short enough to use during a real game-posting workflow.

### 13. Improve Frame Read Error Messages

Source: CR-13

Make out-of-range or unreadable frame errors easier to debug.

Acceptance criteria:
- `read_frame_at` / `read_frames_at` errors include the requested timestamp.
- When available, errors also include video duration.
- Tests cover the improved error message without requiring large media files.

### 14. Add Development Tooling Dependencies

Source: CR-14

Make linting/static checks reproducible for contributors.

Acceptance criteria:
- `ruff` is listed in an optional dev dependency group or documented install path.
- Consider `mypy` or `pyright` after the current type hints are cleaned up.
- README includes the command for running tests and lint checks.

## Discussion / Later Deliverables

### 15. Detection Configuration Object

Source: Architectural note / Product backlog

`detect_events` is accumulating parameters. A `DetectionConfig` dataclass would make defaults and per-game tuning easier.

Reason to defer:
- Current parameter count is still manageable.
- This is more valuable after one or two more detection knobs are proven necessary.

### 16. Correction Log Format

Source: Architectural note / Product backlog

CSV corrections are simple and practical today. JSONL correction events could be better for collaborative review later.

Reason to defer:
- CSV is currently easy to paste, diff, and explain.
- JSONL would add complexity before multi-reviewer workflows exist.

### 17. Package/Product Naming

Source: Architectural note / Product backlog

The current name is SidelineHD-specific, while the architecture could eventually support other overlays.

Reason to defer:
- The MVP is intentionally SidelineHD-focused.
- Renaming package/module paths too early creates churn without improving today’s workflow.

### 18. Half-Inning Progression Policy

Source: Architectural note / Product backlog

The current progression logic rejects skipped innings after an established previous half-inning. That is probably right for clean data, but it can hide chapters if OCR misses an entire inning.

Reason to defer:
- The current behavior prevents many false chapter jumps.
- This should be revisited with real examples where an inning is skipped mid-stream.

Potential future acceptance criteria:
- Add a documented policy for skipped innings.
- Optionally expose a strict/permissive chapter progression mode.
