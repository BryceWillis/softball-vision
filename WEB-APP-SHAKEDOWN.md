# Web App Live-Fire Shakedown

A manual end-to-end test of the local web app (item 39) against a **real game**.
Run it as the release gate before calling the web app done, and again before each
release. It validates the real **download → OCR → browser → feedback** path that
the unit suite deliberately stubs (`TestClient` + fake OCR). Mechanical plumbing
(routes, job runner, roster CRUD, static assets, 404/pending paths) is already
covered by 342 unit tests and a live-server boot smoke — so focus here on what
only a real game can exercise.

---

## Security gate — read first

Real games carry **real player names**. This test is the highest-risk moment for a
name leak, so:

- **It all stays local.** `runs/`, `videos/`, `rosters/`, `calibration_frames/`,
  and `sidelinehd.cfg` are gitignored (verified) — real artifacts cannot be
  committed from a clean checkout. Do **not** override that.
- **Never paste raw output outward.** Terminal logs, screenshots showing the
  scorebug, `review_report.md`, `samples.jsonl`, or a roster are all
  name-bearing. Do not put them in a GitHub issue, a commit, or a chat.
- **If you report results back**, use the **sanitized feedback log** (stage 5,
  item 51) — names are already redacted to `Player X`, numbers kept — or redact
  names/team by hand first.

---

## Prerequisites

- `pip install -e ".[web]"` — installs the web stack **and** the core deps,
  including `yt-dlp` and `opencv-python`. No separate yt-dlp step: it is a
  declared dependency and lands on PATH with the install (item 53 also adds a
  `python -m yt_dlp` fallback so it works even where the console script isn't on
  PATH). Only needed for the YouTube path; a local video file needs neither.
- **Tesseract** on PATH (5.x recommended; item 42 warns non-fatally if old/missing).
- A **real game**: a YouTube URL (single or playlist) or a local video file.
- A **template** matching the scorebug (the default `640x360 active`, or a
  calibrated one) — a mismatched region is the usual cause of empty OCR.
- Optional: a roster for the batting team (improves review flags + name resolution).

---

## The loop — run each stage, mark pass / fail

**0. Start.** `sidelinehd serve` → open http://127.0.0.1:8000 (loopback only, no auth).
   - [ ] Home page loads; the "Manage rosters" link is present.

**1. Roster (item 50, `/rosters`).**
   - [ ] Create the batting team's roster by pasting a `#NN Name` list, or verify an
         existing one; set it as the config default.
   - [ ] Edit a player (number/name) and save — the change round-trips.
   - Known papercut (item 52): the reloaded team name may show as the file stem
     (e.g. `st_mary_s_12u`) rather than the pretty name — expected for now.

**2. Submit + live status (item 46).**
   - [ ] Paste the game URL (pick single vs playlist) and submit; a job row appears.
   - [ ] Status streams `queued → running → done` via HTMX polling (no manual reload);
         stage labels advance (download → process → parse-states → detect-events →
         export → review-report).
   - [ ] Any `field-never-read` warnings surface (item 45) — note which field, if any.

**3. Results + copy kits (item 47).**
   - [ ] Chapters and at-bats copy kits render; one-click **Copy** works.
   - [ ] Review summary shows a **flagged count** and any run warnings (item 48 —
         `review_report.md` is generated during the run).
   - [ ] Spot-check 2–3 chapters against the actual video: inning/half and timestamp
         line up.
   - [ ] Chapter score suffixes render as `(a-b)` with a real home score — validates
         the item 45 `right_score` recalibration on real frames.

**4. Review + corrections (item 49, `/jobs/{id}/review`).**
   - [ ] Flagged events are listed with their flags.
   - [ ] Make an **edit** (fix a wrong number/label), a **delete** (a false-positive
         event), and an **add** (a missing at-bat).
   - [ ] After each, the copy kits (stage 3) reflect the change — re-export ran with
         no re-download/OCR, and `<run_dir>/corrections.csv` now holds the rows.
   - [ ] Flags recompute on the corrected events.

**5. Feedback (item 51, `/jobs/{id}/feedback`) — the egress gate.**
   - [ ] Preview renders the sanitized log. **Verify by eye:** player names appear as
         `Player A/B/…`, **jersey numbers are kept**, team is pseudonymized, and no
         YouTube URL / video id appears.
   - [ ] Add a note; it shows in the preview and in the hand-off bodies.
   - [ ] "Open GitHub issue" opens a prefilled issue with the **sanitized** body;
         copy/email carry the same. (The app makes no outbound request — you submit.)

**6. Cross-cutting.**
   - [ ] OCR throughput feels acceptable on a full game (item 41 worker pool).
   - [ ] `manifest.json` records the Tesseract version (item 42).
   - [ ] No `crops/` written by default (item 41 `save_crops=False`); re-run with a
         crop-saving path only if you need to debug a region.

---

## Recording results

For each stage: **pass / fail + a one-line note**. If a stage fails, the run dir
(`runs/<...>/` — local, name-bearing) has `manifest.json`, `samples.jsonl`,
`states.jsonl`, `events.jsonl`, and `review_report.md` for diagnosis. Bring
findings back as **sanitized** descriptions; the architect files them as Roadmap
items or CRs. Do not attach raw artifacts.

## Likely failure modes (and where they point)

- Empty score/field OCR across the whole run → template region miscalibration
  (item 45 class of bug) — recalibrate that region.
- Early/false `Top 1` at 0:00 → game-start detection (items 34/44).
- Missing at-bats or duplicated chapters → detection thresholds / spacing gate
  (items 31/32) — capture the corrected version via stage 4.
- A name visible in the stage-5 preview → **stop and report immediately**
  (sanitized): that's a PII-boundary regression, highest priority.
