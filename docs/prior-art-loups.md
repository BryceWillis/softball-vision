# Prior Art and Independence: `sidelinehd-extractor` vs. `jcspeegs/loups`

*Item 30 — originality and differentiation audit. 2026-07-05.*

A closely related project exists: [`jcspeegs/loups`](https://github.com/jcspeegs/loups)
(MIT, on PyPI) — also built for fastpitch softball, also emitting YouTube
chapter timestamps from game video. **This project was built independently:
we never started from, referenced, vendored, or pasted loups source.** This
document records the comparison so the independent derivation is on the
record, resolves each potential convergence point, and captures the one
open architectural decision (OCR backend abstraction).

Sources for the loups side: its public GitHub README and PyPI page as of
2026-07-05. We deliberately did not read loups source code for this audit.

## Side-by-side comparison

| Dimension | sidelinehd-extractor (ours) | loups |
|---|---|---|
| **Ingestion** | Pulls source video via yt-dlp (`run-youtube`, playlist batch queue); local files also supported | Operates on a local video file argument |
| **Frame-of-interest trigger** | Layout-aware: fixed SidelineHD scorebug ROIs sampled on a time grid (every N seconds), state derived from parsed field values changing | Generic OpenCV template *matching* against a user-supplied template image; "match found" = frame matters |
| **OCR layer** | Tesseract (subprocess) or optional tesserocr, per-field PSM/whitelist/preprocess configs, multi-PSM voting, 0–1 confidence capture | EasyOCR with confidence filtering |
| **Reading order** | Reads named sub-regions by position (each field has its own crop); no spatial sorting of a flat OCR result set. (Sample serialization sorts by *field name* for determinism — not left-to-right text sorting.) | Sorts detected text elements left-to-right |
| **Identity resolution** | Roster CSV keyed on jersey number; OCR'd names matched/canonicalized against the roster, with a review/corrections layer | OCRs the name/number straight off the frame; extracted text becomes the chapter title |
| **State** | Persistent run dirs: `samples.jsonl` → `states.jsonl` → `events.jsonl` + `manifest.json`; re-exportable, correctable after the fact | Stateless; writes the chapter file |
| **Output composition** | Two exports: inning chapters (with score at transitions) and an at-bat jump-link comment (inning headers, roster-resolved names); pregame intro marker; project credit | One chapter list: `H:MM:SS <OCR'd text>` |
| **Event/at-bat logic** | State-machine over parsed scorebug fields: batter-number change + dedup window + confidence-tiered minimum spacing + batting-order continuity validation | First template match per frame threshold |
| **CLI** | Subcommand CLI (`run`, `run-youtube`, `run-playlist`, `serve`, `start`, roster/calibration tools); `-o` = `--output-dir`, `-t` = `--timestamp`; no `-q`/`--debug` | Single command + `thumbnail` subcommand; `-t` = `--template`, `-o` = `--output`, `-q` = `--quiet`, `-d` = `--debug` |
| **UI** | Local web app (FastAPI/HTMX): submit, progress, corrections, rosters, feedback | CLI only |
| **Thumbnails** | Not a feature | SSIM first-match extraction |

## Convergence-point resolutions

Each "review for convergence" point from the item 30 scope, resolved:

1. **OCR engine** — *diverged (already).* We use Tesseract/tesserocr, not
   EasyOCR. The layer around it (per-field ROI crops, preprocessing
   strategies, PSM voting, confidence aggregation) is our own, driven by
   measured calibration on real SidelineHD streams (items 40/43/45).
2. **Frame-of-interest trigger** — *diverged (already).* We never template-match
   frames; we sample on a time grid and parse fixed layout-aware ROIs, deciding
   significance from *parsed field-value changes* (state machine), not image
   similarity.
3. **OCR result ordering** — *diverged (already).* We read named sub-regions by
   position; there is no left-to-right sorting of a flat OCR result set
   anywhere in the pipeline. The only sorting is deterministic serialization
   by field name and timestamp.
4. **Chapter title composition** — *diverged (already).* Titles use
   roster-resolved canonical names, inning context, and score at inning
   transitions (item 29); unknown/low-confidence numbers go through the
   review/flag layer rather than being printed raw.
5. **At-bat boundary logic** — *retained as ours, documented.* New at-bat =
   batter-number change with confidence-tiered minimum spacing (item 31),
   half-inning gating, and batting-order continuity validation (item 32).
   This grew out of our own review findings on real games; it has no
   counterpart in a first-match threshold design.
6. **CLI surface** — *verified non-coincident.* Our short flags mean different
   things (`-t` = timestamp, `-o` = output dir), we have no `-q` or `--debug`,
   and the surface is subcommand-structured. No change needed.
7. **Thumbnails** — *not a feature.* If ever added, use an event-driven pick
   (e.g. best frame in a window around a roster-confirmed at-bat), not
   first-match SSIM.

## Decision: OCR backend abstraction

**Status: done in substance; EasyOCR support declined for now.**
`create_ocr_backend(name)` already gives us a pluggable seam (`none`,
`tesseract`, `tesserocr` — the latter with graceful fallback). Adding EasyOCR
as a selectable backend is possible behind the same seam but is *declined*
for now: it would add a ~100 MB model download and a heavy dependency to a
tool whose item 54 goal is zero-friction install, and Tesseract accuracy on
the SidelineHD scorebug is already calibrated and measured. Revisit only if a
concrete accuracy gap appears that preprocessing/voting cannot close.

## Repo hygiene

- No file, function, or comment in this repo reproduces loups naming or
  structure (audited via source grep for `loups`, `easyocr`, `ssim` — no hits).
- No loups source has ever been vendored or pasted; this audit used only its
  README/PyPI documentation.

## Posture

loups accepts custom templates by design. If a friendly upstream gesture is
ever wanted, contributing a SidelineHD template/recipe there is the right
move (optional; noted in item 30, not an acceptance criterion).
