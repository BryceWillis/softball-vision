# SidelineHD Chapter and At-Bat Extractor

Local-first tooling for extracting useful YouTube timestamps from completed softball or
baseball videos with a burned-in SidelineHD overlay.

The deterministic CLI pipeline can download a completed game, crop/OCR the fixed
SidelineHD overlay, detect inning chapters and player at-bats, then generate a
YouTube paste kit.

For a non-technical overview of what this project does and why it exists, see
[PROJECT-EXPLANATION.md](PROJECT-EXPLANATION.md).

## Quickstart (Mac — no Terminal)

Everything in this section is downloads and clicks. No Terminal, no commands.

> **Apple Silicon only:** the download below is built for Apple Silicon Macs
> (M1 or later). On an Intel Mac — or on Windows or Linux — use
> [Run from source (any platform)](#run-from-source-any-platform) instead.

**1. Download the app.** Go to the project's
[Releases page](https://github.com/BryceWillis/softball-vision/releases/latest)
and download `SidelineHD-Extractor-macos-arm64.zip`.

**2. Unzip it.** Double-click the zip in your Downloads folder. You get an
app called **SidelineHD Extractor**.

**3. Drag it into your Applications folder** — do this now, before opening it
for the first time.

**4. Open it.** Double-click **SidelineHD Extractor** in Applications. macOS
shows its ordinary "downloaded from the internet" confirmation — click
**Open**, and that's the only question it asks. Releases are signed and
notarized with Apple, so macOS can verify who built the app and that Apple
has checked it.

   (Releases **before v0.6.0** were not notarized, so those older zips only
   get a scarier warning with no Open button at all. It looks like a dead
   end, but it isn't: close the dialog, then right-click the app and choose
   **Open**, then **Open** again in the dialog.)

**5. That's it.** The app's icon appears in your Dock and the app's own window
opens on the first page. That page explains the rest: add your team's roster,
paste the YouTube link to your game, and wait — a full game takes roughly
30–45 minutes to read. When it's done, copy the timestamps into your video's
YouTube description.

Closed the window? Click the Dock icon to bring it back. **Closing the window
does not stop the app** — if it was part-way through reading a game, it keeps
reading. You can also work in your normal browser instead at any time: choose
**Open in Browser** from the app menu, or right-click the Dock icon and choose
it there.

To stop the app, quit it like any Mac app: right-click its Dock icon and
choose **Quit**, or press `Cmd+Q` while it's active.

If something doesn't work, use the app's **Send feedback** button (player
names are removed automatically) or open a GitHub issue.

### Handing the app to another coach

Send the **zip file**, not the unpacked app. Re-zipping the app with Finder
(right-click → **Compress**) is fine; emailing the raw `.app` is not — mail
programs mangle app bundles, and the copy that arrives will not open. The
other coach then follows the same steps above: unzip, drag to Applications,
double-click, and click **Open** on the one-time confirmation.

### Updating

Each time it launches, the app asks GitHub **once** whether a newer release
exists — a single anonymous request to `api.github.com` that carries nothing
about you or your games, gives up after 3 seconds, and does nothing at all
when you're offline. When you're up to date, nothing appears.

When a newer version **is** available, the app offers to install it for you:

- A one-time prompt asks **Update Now** or **Not Now**. Choosing **Update
  Now** downloads the new version in the background — the app stays usable —
  and when it finishes, the app quits and **reopens by itself** as the new
  version. Nothing is downloaded or replaced until you say so.
- If you dismiss the prompt, an **Update to …** item stays in the app's menus
  (the **SidelineHD Extractor** menu at the top of the screen, and the Dock
  icon's right-click menu) so you can start it whenever you like. While it
  downloads, that item shows the progress; once it's ready it becomes
  **Restart to finish updating**.
- If you're in the middle of reading a game, the update waits — it never
  interrupts a read. It finishes the next time you quit the app.

The app only ever replaces its **own** copy, in place, and only with a build
that carries the same Apple signature as the one you're running — a download
that doesn't verify is discarded and nothing changes. If anything goes wrong,
the app tells you plainly that nothing was changed and points you at the
Releases page.

**The manual path still works, and is the command-line equivalent.** You can
always update by hand instead: open the
[Releases page](https://github.com/BryceWillis/softball-vision/releases/latest),
download `SidelineHD-Extractor-macos-arm64.zip`, and replace the app in your
Applications folder (the same drag you did when you first installed it). This
is the same thing a `git pull` does for a source install, and it's the only
way to update the **very first** notarized release onto the auto-update track —
one last manual swap, after which the app keeps itself current.

To turn the check off entirely, add this to `sidelinehd.cfg` in the app's
data folder — in Finder, press `Cmd+Shift+G` and go to
`~/Library/Application Support/SidelineHD Extractor/` (create the file if it
doesn't exist):

```ini
[defaults]
check_for_updates = false
```

(For developers and CI: the `SIDELINEHD_CHECK_FOR_UPDATES` environment
variable overrides the config file — `0` suppresses the check, `1` forces it
on even when running from source, where it is otherwise skipped.)

### Uninstalling

The app keeps everything in two places and touches nothing else on your
Mac — it installs no helpers, changes no settings, and needs no admin
password. Removing it completely is two steps:

1. Drag **SidelineHD Extractor** from Applications to the Trash.
2. Delete its data folder: in Finder press `Cmd+Shift+G` and go to
   `~/Library/Application Support/SidelineHD Extractor/`, then move that
   folder to the Trash. (This holds your rosters, downloaded game videos,
   and results — skip this step if you might reinstall later.)

That's the whole uninstall.

The Quickstart above is for Apple Silicon Macs. Intel Mac, Windows, and Linux
users: start with [Run from source (any platform)](#run-from-source-any-platform)
in Developer Setup below. The sections after that cover the developer/CLI
workflow.

## Developer Setup

Python 3.10 or newer is required.

### Run from source (any platform)

The walkthrough below is the Mac Terminal path, kept intact for anyone running
from a source checkout. Windows and Linux users: the platform-labelled steps in
the rest of Developer Setup below cover the same ground for your OS.

You need to do this once. Afterward, starting the app is a single command.

**1. Open the Terminal app** (press `Cmd+Space`, type `Terminal`, press Enter).

**2. Install the two helpers** — copy each line into the Terminal and press
Enter. The first installs [Homebrew](https://brew.sh) if you don't have it
(skip if you do); the second installs the text reader the app uses:

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install tesseract
```

**3. Download this project**: click the green **Code** button on the GitHub
page, choose **Download ZIP**, and double-click the ZIP to unpack it (or use
`git clone` if you're comfortable with that).

**4. Install the app** — in the Terminal, go into the unpacked folder and
install (copy all four lines together):

```sh
cd ~/Downloads/softball-vision-main
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[web]"
```

**5. Start it:**

```sh
sidelinehd-extractor start
```

Your browser opens the app automatically. The first page explains the rest:
add your team's roster, paste the YouTube link to your game, and wait — a
full game takes roughly 30–45 minutes to read. When it's done, copy the
timestamps into your video's YouTube description.

To stop the app, go back to the Terminal window and press `Ctrl+C` (or just
close the window). You can also check or stop it from any activated Terminal:

```sh
sidelinehd-extractor status
sidelinehd-extractor stop
```

To start it again later:

```sh
cd ~/Downloads/softball-vision-main && source .venv/bin/activate && sidelinehd-extractor start
```

After updating this project, run `sidelinehd-extractor restart` so the running
app loads the new code. A server that is already running does not pick up code
changes on its own.

**If something doesn't work:**

- `command not found: sidelinehd-extractor` — run
  `source .venv/bin/activate` first (step 4 put the app inside that folder).
- "Port 8000 is already in use" — if the message says this app is already
  running, use `sidelinehd-extractor restart` or `sidelinehd-extractor stop`.
  If it is another program, run `sidelinehd-extractor start --port 8001`.
- A yellow "One-time setup needed" card in the app — it shows the exact
  install command to copy; run it in the Terminal, then click Re-check.
- Anything else: use the app's **Send feedback** button (player names are
  removed automatically) or open a GitHub issue.

### External dependencies

Two system tools are used at runtime:

- **Tesseract OCR** — required by the primary `run-game` and `run-youtube`
  commands; it reads the scoreboard overlay.
- **ffmpeg** — recommended for reliable, best-quality YouTube downloads.
  `yt-dlp` needs it to merge YouTube's separate audio and video streams;
  without it, downloads silently fall back to lower-quality single-stream
  formats. (A bundled fallback via `imageio-ffmpeg` is installed with the
  package, so this is a recommendation, not a hard requirement.)

macOS:

```sh
brew install tesseract
brew install ffmpeg
```

Linux (Debian/Ubuntu):

```sh
sudo apt-get install tesseract-ocr ffmpeg
```

Windows:

- Tesseract: install the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki)
  and ensure `tesseract.exe` is on your `PATH`.
- ffmpeg: `winget install Gyan.FFmpeg`, or download it from
  <https://ffmpeg.org/download.html>.

### Create a virtual environment and install

macOS / Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Windows (PowerShell — use the `py -3` launcher instead of `python3`):

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Windows (cmd.exe):

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
```

For contributor tooling, install the optional development dependencies:

```sh
python -m pip install -e ".[dev]"
```

For the local web UI (`sidelinehd-extractor serve`), install the optional web
dependencies:

```sh
python -m pip install -e ".[web]"
```

Then start the app and open the printed URL (loopback only; the app has no
auth and must not be exposed beyond `127.0.0.1`):

```sh
sidelinehd-extractor serve
```

Use `sidelinehd-extractor status`, `sidelinehd-extractor stop`, and
`sidelinehd-extractor restart` to manage the local web server. After pulling or
installing updated code, run `restart`; an already-running server keeps the code
it loaded at startup.

These see the desktop app too: a running `.app` shows up in `status` as
`running (desktop app)`, along with the folder it is serving, and `stop` shuts
it down gracefully. `restart` is the exception — it cannot relaunch an app it
did not start, so it says so and leaves the app alone; quit it from the Dock
and open it again instead.

Install the external OCR engine per the
[External dependencies](#external-dependencies) steps above. The primary
`run-game` and `run-youtube` commands use Tesseract OCR by default; pass
`--ocr none` only when you are running a non-OCR/debug workflow.

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

On Windows the `PYTHONPATH` prefix is `$env:PYTHONPATH = "src";` in PowerShell,
or `set PYTHONPATH=src &&` in cmd.exe.

## CLI Quick Start

For a fresh game, use the checklist in [NEW_GAME_CHECKLIST.md](NEW_GAME_CHECKLIST.md).

Create a private roster from a pasted team list:

```sh
sidelinehd-extractor setup-roster
```

Interactive setup can also create `sidelinehd.cfg` in this directory with your
roster and template defaults. Once that file exists, normal runs can be as short
as:

```sh
sidelinehd-extractor run-youtube 'https://www.youtube.com/live/YOUR_VIDEO_ID'
```

For scripted use, `make-roster` still accepts a text file or stdin.

Download a completed YouTube game, process it locally, and write both YouTube text
exports:

```sh
sidelinehd-extractor run-youtube \
  'https://www.youtube.com/live/YOUR_VIDEO_ID' \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster rosters/your_team.csv \
  --start 10:00 \
  --ocr tesseract
```

Review and publish:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN --kind at-bats
sidelinehd-extractor review-events runs/YOUR_RUN --kind chapters
sidelinehd-extractor publish-helper runs/YOUR_RUN
```

`publish-helper` creates game-named Markdown and HTML paste-kit files under the
run's `exports/` folder with:

- Description chapters for the YouTube description.
- Pinned-comment at-bats grouped by inning.
- One-click copy buttons in the HTML file.
- A short posting checklist.

To send a diagnostic log for help without sharing player names, generate and
preview a sanitized Markdown feedback file:

```sh
sidelinehd-extractor feedback runs/YOUR_RUN --note "Home score looked empty"
```

The feedback log keeps jersey numbers and OCR confidence details, but redacts
player/team names and omits URLs, video IDs, and crop images.

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
that marker or `--no-chapter-intro` to disable it. When score OCR is available,
half-inning chapters include the score as away-home, such as `10:00 Top 1 (2-0)`.
Use `--no-inning-score` to export chapter labels without score snapshots.

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

Process a curated YouTube playlist one game at a time:

```sh
sidelinehd-extractor run-playlist \
  'https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID' \
  --template examples/sidelinehd_640x360_active.example.json \
  --roster examples/roster.example.csv \
  --start 10:00 \
  --ocr tesseract
```

`run-playlist` first enumerates the playlist without downloading video media,
then runs the same local pipeline used by `run-youtube` for each entry. It writes
`runs/playlist_state.jsonl` so interrupted batches can resume and
`runs/batch_summary.md` as a human-readable index of each video's title, URL,
chapter file, and at-bat file. Completed entries are skipped on the next run
unless you pass `--force`. Use `--limit N`, `--start-index N`, and `--retries N`
for smaller or retry-friendly batches.

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

When a roster is provided, roster-confirmed at-bats use a lower 20-second minimum
spacing so fast innings with short plate appearances are not missed. Override with
`--min-at-bat-spacing-roster-confirmed 15` if needed.

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

The easiest way is to run the interactive setup command and paste a team list:

```sh
sidelinehd-extractor setup-roster
```

Paste lines in this format, then press Enter twice:

```text
#2 Emma B.
#3 Olivia M.
#10 Mia K.
#26 Amelia V.
```

This writes a private CSV under `rosters/`, which is ignored by git so real
player names are not accidentally committed.

In interactive mode, `setup-roster` also offers to create or update
`sidelinehd.cfg`. That local file is ignored by git and can store your roster and
template paths so `run-youtube 'URL'` works without repeating those flags.
`examples/sidelinehd.example.cfg` is a copyable starting point.

For scripted use, generate the CSV from a text file:

```sh
sidelinehd-extractor make-roster examples/team-list.example.txt \
  --output rosters/your_team.csv
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

To make a roster the default `run-youtube 'URL'` uses, or to delete one, refer to
it by its slug — the `rosters/<slug>.csv` filename stem (not a path):

```sh
sidelinehd-extractor set-default-roster your_team
sidelinehd-extractor delete-roster old_team --yes
```

`set-default-roster` updates `sidelinehd.cfg`, keeping your template and other
settings. `delete-roster` confirms first (or takes `--yes`); deleting the
configured default warns that runs stop matching roster names until you set a new
one. These are the command-line forms of the roster-management buttons in the web
app, and reject any slug that is not a plain roster name.

## OCR

The primary end-to-end commands, `run-game` and `run-youtube`, default to
`--ocr tesseract` because OCR is required to extract overlay state and at-bat
events. Install the Tesseract CLI before using those commands:

- macOS: `brew install tesseract`
- Linux (Debian/Ubuntu): `sudo apt-get install tesseract-ocr`
- Windows: install the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki)
  and ensure `tesseract.exe` is on your `PATH`.

End-to-end runs parallelize crop OCR across worker threads by default. Use
`--ocr-workers 1` when debugging serially, or `--ocr-workers N` to cap CPU use.
Crop PNGs are no longer written during normal `run-game`, `run-youtube`, or
`run-playlist` runs unless you opt in with `--save-crops`.

An optional in-process backend is available as `--ocr tesserocr`; install it with
`python -m pip install -e ".[ocr]"`. If `tesserocr` is not installed, that backend
falls back to the regular Tesseract subprocess path.

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
sidelinehd-extractor review-events runs/YOUR_RUN --kind at-bats \
  --roster rosters/your_team.csv
```

The review table includes lightweight flags such as close at-bats, missing player
data, and OCR jersey-number mismatches. Pass `--roster` to enable additional
roster-aware flags: `unrostered-card-number` (card read a number not in the roster),
`garbled-card-name` (OCR produced noise with no recognizable name), and
`lineup-had-rostered-candidate` (the lineup strip contained a rostered number while
the card read a different one).

Export pasteable text:

```sh
sidelinehd-extractor export runs/YOUR_RUN --kind chapters
sidelinehd-extractor export runs/YOUR_RUN --kind at-bats
```

YouTube requires description chapters to start at `0:00`. Chapter export adds
`0:00 Pregame` automatically if needed:

```text
0:00 Pregame
10:00 Top 1 (0-0)
19:20 Top 2 (3-1)
```

## Corrections

Manual corrections are CSV rows applied to `events.jsonl` at review/export time.
They do not require rerunning OCR.

For a Markdown report of only questionable events, including raw OCR and copyable
correction examples:

```sh
sidelinehd-extractor review-report runs/YOUR_RUN --kind at-bats \
  --roster rosters/your_team.csv
```

By default, this writes `runs/YOUR_RUN/review_report.md`. Adding `--roster` enables
the same roster-aware flags described under `review-events` above.

```csv
event_type,timestamp,field,value,match_window_seconds,reason
at_bat_start,1:33:40,label,Olivia M. (#3),1,Correct exported at-bat label
at_bat_start,1:33:40,player_name,Olivia M.,1,Keep structured player name in sync
```

Supported correction fields are `label`, `timestamp_seconds`, `player_number`,
`player_name`, `inning`, `half`, `event_type`, `delete`, and `add`. Use
`delete` to remove a false event from exports. Use `add` to insert a missing
event; add rows can include `label`, `player_number`, `player_name`, `inning`,
and `half` columns:

```csv
event_type,timestamp,field,value,inning,half,player_number,player_name,label,reason
at_bat_start,18:48,add,,2,top,26,Amelia V.,Amelia V. (#26),Add missing at-bat
```

Preview or export with corrections:

```sh
sidelinehd-extractor review-events runs/YOUR_RUN \
  --corrections examples/corrections.example.csv

sidelinehd-extractor export runs/YOUR_RUN \
  --kind at-bats \
  --corrections examples/corrections.example.csv \
  --output scratch/full_at_bats.txt
```

Corrections saved for a run live in `runs/YOUR_RUN/corrections.csv`. To clear one
(matching the web app's per-correction clear) or all of them and re-export the run
in one step:

```sh
# Clear one correction, by its event type, timestamp, and field:
sidelinehd-extractor clear-corrections --run runs/YOUR_RUN \
  --event-type at_bat_start --timestamp 1:33:40 --field label

# Clear every saved correction for the run:
sidelinehd-extractor clear-corrections --run runs/YOUR_RUN --all
```

Clearing rewrites `corrections.csv` and re-runs the export tail, so the exported
timestamps always agree with what corrections remain. Clearing a correction that
does not exist (or a run with none) is a no-op, not an error.

## Publishing

Create a local paste kit for YouTube:

```sh
sidelinehd-extractor publish-helper runs/YOUR_RUN \
  --chapters scratch/full_chapters.txt \
  --at-bats scratch/full_at_bats.txt
```

By default, this writes game-named Markdown and HTML files beside the run
exports, such as:

```text
runs/YOUR_RUN/exports/your_team_game_name_12u_2026_06_24/youtube_paste_kit.md
runs/YOUR_RUN/exports/your_team_game_name_12u_2026_06_24/youtube_paste_kit.html
```

Use `--output-dir scratch/publish` if you prefer one central publish folder.
Use `--no-html` if you only want the Markdown file.

The paste kit contains:

- Description chapters to paste into the YouTube description.
- Pinned-comment at-bats to paste as a YouTube comment.
- HTML copy buttons for each section.
- A short project credit with the GitHub repo and MIT license.
- A short publishing checklist.

## Project Tracking

The roadmap and review workflow are maintained in a private documentation
vault alongside this repository. The historical in-repo tracking files —
`Roadmap.md` (item designs) and `CODE-REVIEW.md` (review findings, `CR-XX`) —
are preserved under [docs/archive/](docs/archive/) for reference; see
[docs/archive/README.md](docs/archive/README.md) for what moved where.

## Development Checks

Install the development and web extras, then run the two checks. These commands
are identical on macOS, Linux, and Windows:

```sh
python -m pip install -e ".[dev,web]"
python -m pytest tests/
python -m ruff check .
```

Both must be clean before a change is ready.

Run the suite under `pytest`, not `unittest discover`. The suite mixes
`unittest.TestCase` classes with pytest fixture and function-style tests, so
`unittest discover` silently collects only part of it and skips the entire
web-app surface — it reports green on a web-app regression. The web extra is
installed alongside dev for the same reason: the web-app test modules import
`fastapi` and `uvicorn` at module scope.

Installing the package with `-e` also removes the need for `PYTHONPATH=src`.

Continuous integration (`.github/workflows/ci.yml`) runs the same test suite
and ruff on Ubuntu, macOS, and Windows for every push and pull request.

## Prior Art and Independence

A related MIT-licensed project exists: [`jcspeegs/loups`](https://github.com/jcspeegs/loups),
which also generates YouTube chapters from fastpitch softball video. This
project was built independently — no loups code was referenced or reused —
and the designs differ substantially: we sample fixed SidelineHD scorebug
regions on a time grid and drive a state machine over parsed field values
(loups template-matches frames against a user image); we resolve batter
identity through a roster CSV keyed on jersey number (loups OCRs text
straight off the frame); we use Tesseract with per-field configs (loups uses
EasyOCR); and we persist re-exportable run state with a corrections layer
(loups is stateless). The full comparison and per-point rationale live in
[docs/prior-art-loups.md](docs/prior-art-loups.md).

## License

MIT — see [LICENSE](LICENSE).
