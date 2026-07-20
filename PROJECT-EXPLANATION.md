# SidelineHD Chapter and At-Bat Extractor

## Plain-English Summary

This project turns a completed SidelineHD-overlaid softball or baseball video into
clean YouTube timestamps.

Given a local video file, or a YouTube URL that can be downloaded locally, the
tool reads the burned-in SidelineHD scoreboard and player overlay, figures out
when innings and our team's at-bats start, and writes copy/paste-ready text for:

- YouTube description chapters.
- A pinned YouTube comment listing player at-bat jump links.

The first goal is simple: make a full game video easier for families, players,
and coaches to navigate.

## The Problem It Solves

SidelineHD game videos are useful, but long. A parent looking for one player's
at-bats may need to scrub through 90 minutes of video. YouTube chapters help, but
creating them by hand is tedious.

This tool automates most of that indexing work by reading the same scorebug and
player cards that are already visible in the video.

Instead of manually writing:

```text
10:15 Maya R. (#22)
11:15 Olivia M. (#3)
12:00 Emma B. (#2)
```

the tool extracts that list from the video overlay.

## What It Produces

### YouTube Description Chapters

These go in the video description. YouTube turns them into chapter markers on the
video timeline.

Example:

```text
0:00 Top 1
8:55 Bottom 1
14:10 Top 2
20:30 Bottom 2
33:10 Top 3
```

### Pinned Comment At-Bats

These go in a pinned YouTube comment. YouTube automatically turns the timestamps
into clickable video links.

Example:

```text
1st Inning
10:15 Maya R. (#22)
11:15 Olivia M. (#3)
12:00 Emma B. (#2)
13:05 Mia K. (#10)

2nd Inning
21:15 Amelia V. (#26)
22:35 Nora F. (#15)
23:20 Ava T. (#5)
```

### Review Report

The tool also writes a Markdown review report for anything suspicious, such as:

- OCR read `#28`, but the roster says the player is Amelia V. `#26`.
- Two at-bat changes are very close together.
- A player name was detected but the jersey number was blank or noisy.

This gives a human reviewer a small list of things to check instead of forcing
them to audit the whole game.

## How It Works

The tool is intentionally deterministic and local-first.

It does not use a cloud AI model by default. It does not try to understand the
whole game like a human scorekeeper. Instead, it reads fixed areas of the video
where SidelineHD already displays structured information.

High-level pipeline:

```text
YouTube URL or local video
        |
        v
Download video locally, if needed
        |
        v
Sample video frames every few seconds
        |
        v
Crop fixed SidelineHD overlay regions
        |
        v
OCR inning, count, player name, player number
        |
        v
Parse OCR into a smoothed state timeline
        |
        v
Detect half-inning changes and our team's at-bats
        |
        v
Export YouTube-ready text and review reports
```

## Why OCR Works Here

Most computer vision problems in sports video are hard because the camera moves,
players overlap, and the action is visually ambiguous.

This project avoids that hard problem for the MVP.

The SidelineHD overlay is:

- Synthetic text, not handwriting.
- Burned into the video.
- Mostly fixed in the same location.
- Repeated across the whole game.

That makes it a good fit for deterministic cropping plus OCR.

## Roster Matching

The tool uses a roster CSV so it can correct OCR mistakes.

For example, if the overlay name reads `Amelia V.` but the tiny jersey-number crop
reads `#28`, the roster can still map Amelia to `#26`.

Roster example:

```csv
number,full_name,preferred_name,display_name,aliases
26,Amelia V.,Amelia,Amelia V.,Amelia
22,Maya R.,Maya,Maya R.,Maya
```

This is especially useful because player names are often easier for OCR to read
than small jersey numbers.

## Home vs. Away Matters

The tool can be told which half of each inning our team bats in:

- `--batting-half top` for away-team games.
- `--batting-half bottom` for home-team games.

This matters because SidelineHD may show defensive player cards, such as the
pitcher, during the other half-inning. Filtering to the correct batting half
removes many false positives.

As a rough title convention:

- `Team @ Opponent` often means away, use top.
- `Team vs Opponent` often means home, use bottom.

The user should still verify this for each game.

## What This Is Not

This is not a full scorekeeping system.

It does not try to determine:

- Hits versus errors.
- RBIs.
- Pitch-by-pitch results.
- Defensive plays.
- Official stats.
- Recruiting-grade highlights.

It is an overlay extractor and video indexer.

The goal is to make already-recorded game video easier to navigate, not to replace
GameChanger or a human scorekeeper.

## Current Workflow

Typical command:

```sh
PYTHONPATH=src python3 -m sidelinehd_extractor.cli run-youtube \
  'YOUTUBE_URL' \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster examples/roster.example.csv \
  --batting-half bottom \
  --start 0:00 \
  --ocr tesseract
```

Then review:

```sh
PYTHONPATH=src python3 -m sidelinehd_extractor.cli review-events runs/YOUR_RUN --kind at-bats
PYTHONPATH=src python3 -m sidelinehd_extractor.cli review-report runs/YOUR_RUN --kind at-bats
PYTHONPATH=src python3 -m sidelinehd_extractor.cli publish-helper runs/YOUR_RUN
```

The paste kit is written under `scratch/publish/` and contains the text blocks to
paste into YouTube.

## Privacy and Cost

The pipeline is local-first:

- The video is downloaded to the user's machine.
- OCR runs locally with Tesseract.
- Outputs are local text files.
- No cloud processing is required by default.

This keeps the workflow private, debuggable, and inexpensive.

## Current Limitations

The tool still needs human review.

Known limitations:

- OCR can misread tiny jersey numbers.
- Some games require `--batting-half top`; others require `--batting-half bottom`.
- Overlay layout changes may require a new crop template.
- If the scorekeeper is late updating the overlay, timestamps can be delayed.
- The tool currently indexes at-bats and innings, not full statistical outcomes.

The review report is designed to make these limitations manageable.

## Why This Is Useful

For a parent or team videographer, the tool can turn a long game video into
something immediately navigable:

- Families can jump to their player's at-bats.
- Coaches can quickly scan innings.
- Players can share direct links.
- The person uploading the video saves a lot of manual timestamp work.

The first useful version does not need to be perfect. It needs to be fast,
private, auditable, and good enough that reviewing one game is easier than doing
everything by hand.

## Project Direction

Near-term improvements are tracked in a private documentation vault alongside
this repository; the historical in-repo roadmap and review findings are
preserved under [docs/archive/](docs/archive/).

Possible future work:

- Better auto-detection of home/away batting half.
- More overlay templates.
- A friendlier local review UI.
- Clip generation for selected at-bats.
- Optional scoring-play detection.
- Optional AI-assisted review, while keeping the default pipeline local.
