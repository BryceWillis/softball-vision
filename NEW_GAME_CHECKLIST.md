# New Game Checklist

Use this after cloning the repo and installing dependencies.

## One-Time Setup

- [ ] Install Python 3.10 or newer.
- [ ] Install Tesseract:
  - macOS: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr` or your distribution's equivalent
  - Windows: install from `https://github.com/UB-Mannheim/tesseract/wiki` and
    ensure `tesseract.exe` is on your `PATH`
- [ ] Install ffmpeg (recommended — best-quality YouTube downloads; without it
      `yt-dlp` falls back to lower-quality single-stream formats):
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` or your distribution's equivalent
  - Windows: `winget install Gyan.FFmpeg` or download from `https://ffmpeg.org/download.html`
- [ ] Create a virtual environment:
  - macOS/Linux: `python3 -m venv .venv`
  - Windows: `py -3 -m venv .venv`
- [ ] Activate it:
  - macOS/Linux: `source .venv/bin/activate`
  - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
  - Windows (cmd.exe): `.venv\Scripts\activate.bat`
- [ ] Install the tool: `python -m pip install -e .`
- [ ] Confirm the CLI works: `sidelinehd-extractor --help`

## Per-Team Setup

- [ ] Generate a private roster:

```sh
sidelinehd-extractor setup-roster
```

- [ ] Paste the team list when prompted, one player per line:

```text
#2 Emma B.
#3 Olivia M.
#10 Mia K.
```

- [ ] Press Enter twice to finish. The roster is written under `rosters/`, which
      is ignored by git.

- [ ] If prompted, create/update `sidelinehd.cfg` and enter the template path:

```text
examples/sidelinehd_640x360_active.example.json
```

After `sidelinehd.cfg` exists, `run-youtube 'YOUTUBE_URL'` can use the saved
roster and template defaults.

- [ ] For scripted/non-interactive setup, use:

```sh
sidelinehd-extractor make-roster team-list.txt --output rosters/your_team.csv
```

## Per-Game Workflow

- [ ] Download and process the completed YouTube game:

```sh
sidelinehd-extractor run-youtube 'YOUTUBE_URL' \
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
`runs/YOUR_RUN/exports/GAME_SLUG/` as both `youtube_paste_kit.md` and
`youtube_paste_kit.html`. Open the HTML file for one-click copy buttons, or use
the Markdown file as a plain-text fallback. Add `--output-dir scratch/publish`
if you want all paste kits in one shared folder.

## YouTube Posting

- [ ] Open `youtube_paste_kit.html`.
- [ ] Copy the chapter block into the YouTube description.
- [ ] Save the description and confirm chapters appear on the progress bar.
- [ ] Copy the at-bat block as a YouTube comment.
- [ ] Pin the at-bat comment.
