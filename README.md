# SidelineHD Chapter and At-Bat Extractor

Local-first tooling for extracting useful YouTube timestamps from completed softball or
baseball videos with a burned-in SidelineHD overlay.

The deterministic CLI pipeline can download a completed game, crop/OCR the fixed
SidelineHD overlay, detect inning chapters and player at-bats, then generate a
YouTube paste kit.

For a non-technical overview of what this project does and why it exists, see
[PROJECT-EXPLANATION.md](PROJECT-EXPLANATION.md).

## Setup

Python 3.10 or newer is recommended. Python 3.9 may work, but recent `yt-dlp`
versions warn that Python 3.9 support is deprecated.

Create a virtual environment and install the local package:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For contributor tooling, install the optional development dependencies:

```sh
python -m pip install -e ".[dev]"
```

Install the external OCR engine. The primary `run-game` and `run-youtube`
commands use Tesseract OCR by default; pass `--ocr none` only when you are
running a non-OCR/debug workflow:

```sh
brew install tesseract
```

Confirm the CLI is available:

```sh
sidelinehd-extractor --help
```

If you do not want to install the package, you can run from the repo with
`PYTHONPATH=src python3 -m sidelinehd_extractor.cli ...` after installing runtime
dependencies:

```sh
python -m pip install -r requirements.txt
```

## Quick Start

For a fresh game, use the checklist in [NEW_GAME_CHECKLIST.md](NEW_GAME_CHECKLIST.md).

Create a roster from a pasted team list:

```sh
sidelinehd-extractor make-roster examples/team-list.example.txt --output roster.csv
```

Download a completed YouTube game, process it locally, and write both YouTube text
exports:

```sh
sidelinehd-extractor run-youtube \
  'https://www.youtube.com/live/YOUR_VIDEO_ID' \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster roster.csv \
  --start 10:00 \
  --ocr tesseract
```

Review and publish:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN --kind at-bats
sidelinehd-extractor review-events runs/YOUR_RUN --kind chapters
sidelinehd-extractor publish-helper runs/YOUR_RUN
```

`publish-helper` creates a game-named Markdown file under `scratch/publish/` with:

- Description chapters for the YouTube description.
- Pinned-comment at-bats grouped by inning.
- A short posting checklist.

## YouTube Download Notes

The downloader defaults to `--extractor-args youtube:player_client=android` because
YouTube sometimes returns 403 errors for the default web client. If that stops
working, try `--youtube-client ios` or `--youtube-client web_safari`.

Download a completed YouTube/SidelineHD game locally without processing:

```sh
sidelinehd-extractor download \
  'https://www.youtube.com/live/YOUR_VIDEO_ID'
```

Or download and immediately extract calibration frames:

```sh
sidelinehd-extractor prepare-youtube \
  'https://www.youtube.com/live/YOUR_VIDEO_ID' \
  --timestamp 2:00 --timestamp 5:00 --timestamp 10:00
```

## Calibration

Extract one calibration crop:

```sh
sidelinehd-extractor extract-frame path/to/game.mp4 scratch/overlay.png \
  --timestamp 60 --x 0.0 --y 0.0 --width 1.0 --height 0.25
```

Extract full frames from an already-local video for overlay fraction tuning:

```sh
sidelinehd-extractor calibration-frames path/to/game.mp4 \
  --timestamp 2:00,5:00,10:00
```

Draw a template guide over a frame:

```sh
sidelinehd-extractor template-guide path/to/game.mp4 scratch/template_guide.png \
  --template examples/sidelinehd_640x360_active.example.json \
  --timestamp 10:00
```

Process a game end-to-end and write both YouTube text exports:

```sh
sidelinehd-extractor run-game path/to/game.mp4 \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster examples/roster.example.csv \
  --start 10:00 \
  --ocr tesseract \
  --output-prefix scratch/full
```

This creates a new run directory, writes `states.jsonl` and `events.jsonl`, then
writes `scratch/full_chapters.txt` and `scratch/full_at_bats.txt`. It prints
progress while OCR is running and finishes with suggested review commands.
Chapter exports automatically include `0:00 Pregame` when the first detected
inning starts later in the video. Use `--chapter-intro-label Warmups` to rename
that marker or `--no-chapter-intro` to disable it.

If `--output-prefix` is omitted, export files are written inside the run directory
under a game-named folder such as:

```text
runs/YOUR_RUN/exports/your_team_game_name/your_team_game_name_chapters.txt
runs/YOUR_RUN/exports/your_team_game_name/your_team_game_name_at_bats.txt
```

Or download a completed YouTube game and process it in one command:

```sh
sidelinehd-extractor run-youtube \
  'https://www.youtube.com/live/YOUR_VIDEO_ID' \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster examples/roster.example.csv \
  --start 10:00 \
  --ocr tesseract \
  --output-prefix scratch/full
```

`run-youtube` downloads the video once with `yt-dlp`; OCR, state parsing, event
detection, review, corrections, and export are all local after that.

By default, processing records video metadata but skips full-file SHA-256 hashing
so large game videos start faster. Add `--hash-video` when you want audit-grade
file identity in `manifest.json`.

`run-game` and `run-youtube` default to `--batting-half auto`. With a roster, the
tool detects both halves, infers which half contains roster-matched batter-card
names, logs that decision, and exports only that team's at-bats. Use
`--batting-half top` or `--batting-half bottom` when you want to override
inference. Use `--batting-half both` while calibrating or debugging raw detector
behavior.

At-bat starts closer than 45 seconds apart are ignored by default because they are
usually scorekeeper-delay or transition-card artifacts. Adjust with
`--min-at-bat-spacing 30` if a specific workflow needs a different threshold.

Create an auditable processing run:

```sh
sidelinehd-extractor process path/to/game.mp4 \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster examples/roster.example.csv \
  --start 10:00 \
  --end 10:20 \
  --sample-every 5
```

The run folder contains:

- `manifest.json`: video metadata, template, roster, and processing settings.
- `samples.jsonl`: one record per sampled crop, with placeholder OCR text for now.
- `crops/`: saved crop images for audit and OCR tuning.

## Roster

Provide a simple CSV roster so OCR names can be corrected to official jersey
numbers. This is especially useful when the overlay number is tiny or ambiguous.

The easiest way is to paste a team list into a text file:

```text
#2 Emma B.
#3 Olivia M.
#10 Mia K.
#26 Amelia V.
```

Then generate the CSV:

```sh
sidelinehd-extractor make-roster examples/team-list.example.txt \
  --output roster.csv
```

This writes the roster format used by `run-game` and `detect-events`:

```csv
number,full_name,preferred_name,display_name,aliases
26,Amelia V.,Amelia,Amelia V.,Amelia
22,Maya R.,Maya,Maya R.,Maya
```

If you edit CSV by hand, required columns are `number` and `full_name`. Optional
columns:

- `display_name`: label to use in exports.
- `preferred_name`: fallback name.
- `aliases`: semicolon-separated OCR/name variants.

When `detect-events --roster` is used, roster name-to-number lookup wins over OCR
jersey-number guesses. Raw OCR jersey numbers are still kept in `events.jsonl`
metadata as `ocr_player_number` for audit.

## OCR

The primary end-to-end commands, `run-game` and `run-youtube`, default to
`--ocr tesseract` because OCR is required to extract overlay state and at-bat
events. Install the Tesseract CLI before using those commands:

```sh
brew install tesseract
```

The lower-level `process` command can still run without OCR for crop/template
debugging, but those placeholder samples are not enough to detect real events.
Use `--ocr none` explicitly when you want that mode.

Test OCR on one crop before running a larger process pass:

```sh
sidelinehd-extractor ocr-image \
  runs/YOUR_RUN/crops/000600p000_count.png \
  --field count \
  --preprocessed-output scratch/count_preprocessed.png
```

Run a short OCR-enabled processing pass:

```sh
sidelinehd-extractor process path/to/game.mp4 \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster examples/roster.example.csv \
  --start 10:00 \
  --end 10:20 \
  --sample-every 5 \
  --ocr tesseract \
  --progress-every 25 \
  --field inning,count,batter_card_name,batter_card_number
```

Once the one-crop OCR checks look sane, run a longer tuning window such as
`--start 10:00 --end 20:00`. The event detector debounces intermittent jersey-number
OCR noise, but longer windows are the fastest way to spot template or OCR drift.
Use `--progress-every N` to print progress every N sampled timestamps, or `--quiet`
to suppress progress output.

For normal use, prefer `run-game`. The lower-level commands below are useful when
debugging one stage or rerunning only part of the pipeline.

Parse OCR samples into structured overlay states:

```sh
sidelinehd-extractor parse-states runs/YOUR_RUN
```

This writes `states.jsonl` next to `samples.jsonl`.

Detect inning and at-bat events:

```sh
sidelinehd-extractor detect-events runs/YOUR_RUN \
  --roster examples/roster.example.csv
```

Review detected events before posting:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN
sidelinehd-extractor review-events runs/YOUR_RUN --kind at-bats
```

The review table includes lightweight flags such as close at-bats, missing player
data, and OCR jersey-number mismatches.

Export pasteable text:

```sh
sidelinehd-extractor export runs/YOUR_RUN --kind chapters
sidelinehd-extractor export runs/YOUR_RUN --kind at-bats
```

YouTube requires description chapters to start at `0:00`. Chapter export adds
`0:00 Pregame` automatically if needed:

```text
0:00 Pregame
10:00 Top 1
19:20 Top 2
```

## Corrections

Manual corrections are CSV rows applied to `events.jsonl` at review/export time.
They do not require rerunning OCR.

For a Markdown report of only questionable events, including raw OCR and copyable
correction examples:

```sh
sidelinehd-extractor review-report runs/YOUR_RUN --kind at-bats
```

By default, this writes `runs/YOUR_RUN/review_report.md`.

```csv
event_type,timestamp,field,value,match_window_seconds,reason
at_bat_start,1:33:40,label,Olivia M. (#3),1,Correct exported at-bat label
at_bat_start,1:33:40,player_name,Olivia M.,1,Keep structured player name in sync
```

Supported correction fields are `label`, `timestamp_seconds`, `player_number`,
`player_name`, `inning`, `half`, `event_type`, and `delete`. Use `delete` to
remove a false event from exports.

Preview or export with corrections:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN \
  --corrections examples/corrections.example.csv

sidelinehd-extractor export runs/YOUR_RUN \
  --kind at-bats \
  --corrections examples/corrections.example.csv \
  --output scratch/full_at_bats.txt
```

## Publishing

Create a local paste kit for YouTube:

```sh
sidelinehd-extractor publish-helper runs/YOUR_RUN \
  --chapters scratch/full_chapters.txt \
  --at-bats scratch/full_at_bats.txt
```

By default, this writes a game-named Markdown file under `scratch/publish/`, such
as:

```text
scratch/publish/your_team_game_name_12u_2026_06_24/youtube_paste_kit.md
```

The paste kit contains:

- Description chapters to paste into the YouTube description.
- Pinned-comment at-bats to paste as a YouTube comment.
- A short project credit with the GitHub repo and MIT license.
- A short publishing checklist.

## Project Tracking

Use [CODE-REVIEW.md](CODE-REVIEW.md) for reviewed engineering findings and their
approval lifecycle. Code review items use IDs like `CR-10a`; after implementation,
Codex may mark an item `Ready for Review`, but the reviewer/user owns moving it
to `Resolved`.

Use [Roadmap.md](Roadmap.md) for the implementation queue and product backlog.
Roadmap items from code review include `Source: CR-XX`; feature ideas that are
not review findings use `Source: Product backlog`.

## Development Checks

Run the local test suite:

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

Run lint checks after installing the development dependencies:

```sh
ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
