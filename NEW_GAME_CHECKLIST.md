# New Game Checklist

Use this after cloning the repo and installing dependencies.

## One-Time Setup

- [ ] Install Python 3.10 or newer.
- [ ] Install Tesseract:
  - macOS: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr` or your distribution's equivalent
  - Windows: install from `https://github.com/UB-Mannheim/tesseract/wiki`
- [ ] Create a virtual environment: `python3 -m venv .venv`
- [ ] Activate it: `source .venv/bin/activate`
- [ ] Install the tool: `python -m pip install -e .`
- [ ] Confirm the CLI works: `sidelinehd-extractor --help`

## Per-Team Setup

- [ ] Paste the team list into a text file, one player per line:

```text
#2 Emma B.
#3 Olivia M.
#10 Mia K.
```

- [ ] Generate a roster:

```sh
sidelinehd-extractor make-roster team-list.txt --output roster.csv
```

## Per-Game Workflow

- [ ] Download and process the completed YouTube game:

```sh
sidelinehd-extractor run-youtube 'YOUTUBE_URL' \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster roster.csv \
  --start 0:00 \
  --ocr tesseract
```

The command defaults to `--batting-half auto` and prints the inferred half. Use
`--batting-half top` or `--batting-half bottom` only when you want to override it.

- [ ] Review at-bats:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN --kind at-bats
```

- [ ] Review chapters:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN --kind chapters
```

- [ ] Generate a report for questionable at-bats:

```sh
sidelinehd-extractor review-report runs/YOUR_RUN --kind at-bats
```

- [ ] Generate the paste kit:

```sh
sidelinehd-extractor publish-helper runs/YOUR_RUN
```

By default, the paste kit is written under
`runs/YOUR_RUN/exports/GAME_SLUG/youtube_paste_kit.md`. Add
`--output-dir scratch/publish` if you want all paste kits in one shared folder.

## YouTube Posting

- [ ] Paste the chapter block into the YouTube description.
- [ ] Save the description and confirm chapters appear on the progress bar.
- [ ] Paste the at-bat block as a YouTube comment.
- [ ] Pin the at-bat comment.
