# Code Review

**Reviewer:** Claude (Senior Software Architect)
**Last updated:** 2026-06-28
**Review passes:** 3 (Pass 3: documentation review)

This document is the running record of architectural observations, bugs, and improvement recommendations for the `sidelinehd-extractor` codebase. It is updated after each review pass. Items move to **Resolved** once confirmed fixed.

## Status Workflow

- **Open**: reviewed finding is accepted as work to do.
- **Ready for Review**: Codex has implemented the change and verified tests; awaiting reviewer/user confirmation.
- **Resolved**: reviewer/user has confirmed the implementation and moved the item to the Resolved section.
- **Deferred**: valid finding, but intentionally postponed.

Codex may update an Open item to **Ready for Review** after implementing it and should include a short implementation note. The reviewer/user owns moving items from Open to Resolved after reviewing the diff and behavior.

---

## Open Items

### Medium Priority

#### CR-15 — README misstates OCR default for primary commands
**File:** [README.md](README.md) — OCR section
**Status:** Open
**Added:** Pass 3

The README OCR section opens with:

> OCR is optional and off by default.

This is only true for the lower-level `process` command. The two primary commands `run-game` and `run-youtube` both default to `--ocr tesseract`. A user who follows the Quick Start without Tesseract installed will get a confusing `OCRBackendUnavailable` error that the README did not prepare them for.

The statement should be scoped to `process`, and the setup section should make clear that `run-game`/`run-youtube` require Tesseract unless `--ocr none` is passed.

**Acceptance:** README accurately describes which commands require Tesseract and which default to no OCR.

---

### Critical

#### CR-01 — No license file
**File:** repo root
**Status:** Ready for Review
**Added:** Pass 1

No `LICENSE` file exists. This is the only remaining blocker for any public release (open-source or commercial). MIT is recommended — maximally permissive, simplest, and the most adoption-friendly choice for a local CLI tool targeting other videographers.

**Implementation note:** `LICENSE` (MIT, copyright Ryan Moore 2026) created at repo root. README already references the license implicitly via the open-source publication plan; a brief explicit mention in README can be added at reviewer discretion.

**Acceptance:** `LICENSE` file exists at repo root; README references the license.

---

### Low Priority

#### CR-16 — README pre-release cleanup: specific URLs and team names in examples
**File:** [README.md](README.md)
**Status:** Ready for Review
**Added:** Pass 3

Three places in the README will read as confusing or personal to a first-time user who isn't on the author's team:

1. **Quick Start uses a real YouTube URL** (`j4At63cNpkc`) from an actual recorded game. New users won't recognize it as an example. Replace with `'YOUR_YOUTUBE_URL'` or a clearly labeled placeholder.

2. **`run-game` output path example** contains `smash_it_sports_12u_flx_ice` — a specific team slug. Replace with something like `your_team_name/your_team_name_chapters.txt`.

3. **Publishing section example path** contains `smash_it_sports_12u_flx_ice_12u_2026_06_24`. Same fix — use a generic game name.

4. **"Current State" section** at the bottom reads like an in-progress developer status note ("The local pipeline *can* download a game..."). It should either be removed or rewritten as a stable description of what the tool does, without the WIP tone.

None of these affect correctness; they are all pre-release polish but collectively give the README a "personal project" feel that would discourage adoption.

**Implementation note:** Items 1–3 resolved: the real YouTube video ID (`j4At63cNpkc`) has been replaced with `YOUR_VIDEO_ID` (all occurrences), and the team-specific run slug (`smash_it_sports_12u_flx_ice`) has been replaced with `your_team_game_name` throughout README. Item 4 (rewrite "Current State") is deferred to reviewer discretion — the section is still in place.

**Acceptance:** README examples use generic placeholders; "Current State" section is removed or rewritten as a stable feature summary.

---

#### CR-10a — `export_paths` return type is untyped
**File:** [workflow.py:202](src/sidelinehd_extractor/workflow.py#L202)
**Status:** Open
**Added:** Pass 1

```python
def export_paths(run_dir: Path, output_prefix: Optional[Path] = None) -> tuple:
```

Should be `-> Tuple[Path, Path]` (or `tuple[Path, Path]` on Python 3.10+). All other functions in the codebase use precise return types.

---

#### CR-10b — `PathLike` alias defined in two modules
**Files:** [video.py:12](src/sidelinehd_extractor/video.py#L12), [crops.py:12](src/sidelinehd_extractor/crops.py#L12)
**Status:** Open
**Added:** Pass 1

`PathLike = Union[str, Path]` is duplicated. Could live in `models.py` or `video.py` with `crops.py` importing it. Low-churn fix but worth doing before the module count grows.

---

#### CR-10c — `format_inning_header` type annotation disagrees with implementation
**File:** [exports.py:72-76](src/sidelinehd_extractor/exports.py#L72-L76)
**Status:** Open
**Added:** Pass 1

```python
def format_inning_header(inning: int) -> str:
    if inning is None:       # unreachable per the annotation
        return "Unknown Inning"
```

Either change the annotation to `Optional[int]` to match the guard, or remove the guard if callers can guarantee non-None. The current state is a latent type error that mypy/pyright would flag.

---

#### CR-13 — Frame read errors omit video duration
**File:** [video.py:82, 104](src/sidelinehd_extractor/video.py#L82)
**Status:** Open
**Added:** Pass 1

When `read_frame_at` or `read_frames_at` fails because a timestamp is past the end of the video, the error message is:

```
Could not read frame at X.XXXs from /path/to/video.mp4
```

Including the video duration in the message would immediately tell the user what went wrong:

```
Could not read frame at X.XXXs from video.mp4 (duration: Y.Ys)
```

This requires probing the video first or threading the duration in from the caller. The caller path in `process_video` already has `video.duration_seconds` available.

---

#### CR-14 — `ruff` not listed as a dev dependency
**File:** [pyproject.toml](pyproject.toml)
**Status:** Open
**Added:** Pass 1

`ruff` is configured under `[tool.ruff]` but is not listed in `[project.optional-dependencies] dev`. A new contributor would configure their editor's ruff integration or run `ruff check` without knowing to install it first.

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
]
```

---

## Resolved Items

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
