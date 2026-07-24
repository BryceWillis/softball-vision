"""FastAPI application factory and routes for the local web UI.

Loopback-only, single-user, no auth: run it with ``sidelinehd-extractor serve``
which binds ``127.0.0.1`` by default. Results/copy-kit pages show jersey
numbers and timestamps only; the review page (item 49) may display OCR'd or
roster names because it is local-only — nothing here writes names to anything
that leaves the machine (that egress path is item 38 / phase 39e exclusively).
All assets are vendored (``static/htmx.min.js``) so the app works fully
offline.
"""

from __future__ import annotations

import json
import re
from functools import partial
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sidelinehd_extractor.calibration import parse_timestamp_value
from sidelinehd_extractor.config import (
    load_configured_roster,
    load_roster_csv,
    set_default_roster_config,
)
from sidelinehd_extractor.corrections import (
    EventCorrection,
    apply_event_corrections,
    load_event_corrections,
    remove_event_correction,
    upsert_event_correction,
    write_event_corrections,
)
from sidelinehd_extractor.events import load_events
from sidelinehd_extractor.exports import PROJECT_URL, format_timestamp
from sidelinehd_extractor.feedback import (
    build_name_sanitizer,
    load_feedback_data,
    render_feedback_log,
    sanitize_feedback,
)
from sidelinehd_extractor.models import EventType, HalfInning, Roster, RosterPlayer
from sidelinehd_extractor.ocr import warm_tesserocr_import
from sidelinehd_extractor.preflight import preflight_dependencies
from sidelinehd_extractor.publish import PUBLISH_KIT_COPY_SCRIPT, render_publish_kit_fragment
from sidelinehd_extractor.review import collect_event_review_rows
from sidelinehd_extractor.review_triage import summarize_triage, triage_review_rows
from sidelinehd_extractor.roster import (
    UnknownRoster,
    configured_roster_path,
    default_roster_path,
    existing_roster_path,
    is_configured_default,
    parse_team_list,
    rosters_directory,
    write_roster_csv,
)
from sidelinehd_extractor.review_report import summarize_review_report_text
from sidelinehd_extractor.webapp.history import rehydrate_jobs_from_runs
from sidelinehd_extractor.webapp.jobs import (
    Job,
    JobRunner,
    JobStore,
    default_pipeline_kwargs,
)
from sidelinehd_extractor.webapp.lifecycle import footer_runtime_label
from sidelinehd_extractor.workflow import NO_SCOREBOARD_WARNING, finalize_run_exports
from sidelinehd_extractor.youtube import youtube_watch_url

_PACKAGE_DIR = Path(__file__).resolve().parent

_VALID_KINDS = ("single", "playlist")

REVIEW_REPORT_FILENAME = "review_report.md"
CORRECTIONS_FILENAME = "corrections.csv"
EVENTS_FILENAME = "events.jsonl"
FEEDBACK_ISSUE_TITLE = "SidelineHD Extractor Feedback"

# Item 54c: the primary UI speaks coach, not pipeline. Internal status/stage/
# kind codes stay stable (CSS classes, tests, the manifest) — only the words a
# non-technical user reads are mapped here. Unknown codes fall through raw so
# a new pipeline stage is still visible, just not yet translated.
STATUS_LABELS = {
    "queued": "Waiting to start",
    "running": "Working",
    "done": "Done",
    "error": "Something went wrong",
}

STAGE_LABELS = {
    "download": "Downloading the video",
    "probe": "Checking the video",
    "process": "Reading the scoreboard",
    "parse-states": "Making sense of the scoreboard",
    "detect-events": "Finding at-bats and innings",
    "export": "Writing the timestamps",
    "review-report": "Checking the results",
}

KIND_LABELS = {"single": "game", "playlist": "playlist"}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


EDIT_FIELDS = (
    "label",
    "timestamp_seconds",
    "player_number",
    "player_name",
    "inning",
    "half",
    "event_type",
)


def _validate_submission(url: str, kind: str) -> Optional[str]:
    """Return an error message for a bad submission, or None if valid."""

    if kind not in _VALID_KINDS:
        return f"Unknown job kind: {kind!r}."
    if not url:
        return "Enter a YouTube video or playlist URL."
    if not (url.startswith("http://") or url.startswith("https://")):
        return "The URL must start with http:// or https://."
    return None


def _error_block(label: str, error: str) -> dict:
    return {"kind": "error", "label": label, "error": error}


def _game_block(index: int, label: str, result: dict) -> dict:
    """Build one results-page game block from a per-game result summary.

    Pure view over the run-dir artifacts the pipeline already wrote (item 47):
    exports are read from the summarized paths and the flagged count / run
    warnings are parsed out of ``review_report.md`` — nothing is recomputed.
    """

    chapters_path = result.get("chapters_path")
    at_bats_path = result.get("at_bats_path")
    if not chapters_path or not at_bats_path:
        return _error_block(label, "Export paths are missing from the job result.")
    try:
        chapters_text = Path(chapters_path).read_text(encoding="utf-8")
        at_bats_text = Path(at_bats_path).read_text(encoding="utf-8")
    except OSError as exc:
        return _error_block(label, f"Could not read export files: {exc}")

    fragment = render_publish_kit_fragment(
        game_name=label,
        chapters_text=chapters_text,
        at_bats_text=at_bats_text,
        chapters_path=Path(chapters_path),
        at_bats_path=Path(at_bats_path),
        element_id_prefix=f"game-{index}-",
    )

    flagged_count = None
    warnings: list = []
    run_dir = result.get("run_dir")
    health_warning = result.get("health_warning") or (
        _run_health_warning(Path(run_dir)) if run_dir else None
    )
    report_path = Path(run_dir) / REVIEW_REPORT_FILENAME if run_dir else None
    if report_path is not None and report_path.exists():
        try:
            summary = summarize_review_report_text(report_path.read_text(encoding="utf-8"))
        except OSError:
            summary = None
        if summary is not None:
            flagged_count = summary.flagged_count
            warnings = summary.warnings

    return {
        "kind": "game",
        "label": label,
        "fragment": fragment,
        "flagged_count": flagged_count,
        "warnings": warnings,
        "health_warning": health_warning,
        "report_path": str(report_path) if report_path is not None else None,
    }


def _run_health_warning(run_dir: Path) -> Optional[str]:
    """The item 54 P2 no-scoreboard message from the run manifest, if any.

    Playlist entries do not carry ``health_warning`` in the job summary, so the
    results page falls back to the ``health`` section ``run_game`` wrote.
    """

    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    health = manifest.get("health")
    if isinstance(health, dict) and health.get("no_scoreboard_detected"):
        return str(health.get("message") or NO_SCOREBOARD_WARNING)
    return None


def _run_source_video_id(run_dir: Path) -> Optional[str]:
    """The source YouTube video id from the run manifest, if recorded.

    Item 63: local-file runs and manifests written before the ``youtube``
    section existed simply return None — the review page then renders plain
    timestamps instead of deep links.
    """

    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    youtube = manifest.get("youtube")
    if not isinstance(youtube, dict):
        return None
    video_id = str(youtube.get("video_id") or "").strip()
    return video_id or None


def _entry_label(job: Job, index: int, result: dict) -> str:
    """Human label for one game entry (playlist title or video/run name)."""

    if job.kind == "playlist":
        return result.get("title") or result.get("video_id") or f"Entry {index + 1}"
    # Item 57: rehydrated runs carry a display title recovered from the run
    # dir, which beats the raw video filename or timestamped dir name.
    title = result.get("title")
    if title:
        return title
    video_path = result.get("video_path")
    run_dir = result.get("run_dir")
    return Path(video_path).name if video_path else Path(run_dir).name if run_dir else job.url


def build_result_blocks(job: Job) -> list:
    """Build the per-game blocks for a done job's results page, in batch order."""

    result = job.result or {}
    if job.kind == "playlist":
        blocks = []
        for index, entry in enumerate(result.get("entries") or []):
            label = f"{index + 1}. {_entry_label(job, index, entry)}"
            if entry.get("status") == "failed":
                blocks.append(_error_block(label, entry.get("error") or "Processing failed."))
            else:
                blocks.append(_game_block(index, label, entry))
        return blocks

    return [_game_block(0, _entry_label(job, 0, result), result)]


def _review_entries(job: Job) -> list:
    """Per-game result dicts for a done job, in batch order (single job → one)."""

    result = job.result or {}
    if job.kind == "playlist":
        return list(result.get("entries") or [])
    return [result]


def _run_dir_for_entry(job: Job, entry: int) -> Path:
    entries = _review_entries(job)
    if entry < 0 or entry >= len(entries):
        raise HTTPException(status_code=404, detail="Unknown results entry")
    run_dir = entries[entry].get("run_dir")
    if not run_dir:
        raise HTTPException(status_code=404, detail="This entry has no run directory")
    return Path(run_dir)


def _render_feedback_markdown(run_dir: Path, note: Optional[str]) -> str:
    """Return item 38's post-redaction Markdown and nothing else.

    This route is the one sanctioned egress surface: do not read roster names,
    raw event labels, or samples directly into a response here. The browser only
    receives the Markdown produced by the feedback sanitizer pipeline.
    """

    data = load_feedback_data(run_dir, note=note)
    sanitizer = build_name_sanitizer(data)
    log = sanitize_feedback(data, sanitizer)
    return render_feedback_log(log)


# The GitHub and mailto handoffs carry the whole feedback log in the URL query
# string. A full game's log runs to tens of KB, which overruns GitHub's
# issues/new prefill limit (a 414) and, before that, the browser's own maximum
# URL length — Safari rejects the over-long link as an invalid address rather
# than opening it. Cap the encoded URL to a length every target accepts; the
# complete log stays available through the page's "Copy for email" button and
# the visible preview. urlencode's expansion ratio depends on the content, so
# the body is trimmed against the *measured* encoded length, not a raw guess.
_HANDOFF_URL_MAX_CHARS = 7000
_HANDOFF_TRUNCATION_NOTICE = (
    "\n\n_[Feedback log truncated to fit this link. Use the “Copy for email” "
    "button on the feedback page to paste the complete log.]_"
)


def _github_issue_url(body: str) -> str:
    return f"{PROJECT_URL.rstrip('/')}/issues/new?" + urlencode(
        {"title": FEEDBACK_ISSUE_TITLE, "body": body}
    )


def _body_within_url_budget(markdown: str) -> str:
    """Trim ``markdown`` so its GitHub issue URL stays under the length cap.

    Returns the body unchanged when it already fits. The GitHub URL has the
    longer prefix, so a body that fits it also fits the shorter mailto URL.
    """

    if len(_github_issue_url(markdown)) <= _HANDOFF_URL_MAX_CHARS:
        return markdown
    low, high = 0, len(markdown)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = markdown[:mid].rstrip() + _HANDOFF_TRUNCATION_NOTICE
        if len(_github_issue_url(candidate)) <= _HANDOFF_URL_MAX_CHARS:
            low = mid
        else:
            high = mid - 1
    return markdown[:low].rstrip() + _HANDOFF_TRUNCATION_NOTICE


def _feedback_handoff_links(markdown: str) -> dict:
    body = _body_within_url_budget(markdown)
    return {
        "github_issue_url": _github_issue_url(body),
        "mailto_url": "mailto:?"
        + urlencode({"subject": FEEDBACK_ISSUE_TITLE, "body": body}),
    }


def _feedback_context(job: Job, entry: int, note: str) -> dict:
    run_dir = _run_dir_for_entry(job, entry)
    markdown = _render_feedback_markdown(run_dir, note=note if note else None)
    return {
        "job": job,
        "entry": entry,
        "pending": False,
        "note": note,
        "markdown": markdown,
        **_feedback_handoff_links(markdown),
    }


def _load_run_corrections(run_dir: Path) -> list:
    corrections_path = run_dir / CORRECTIONS_FILENAME
    if not corrections_path.exists():
        return []
    return load_event_corrections(corrections_path)


#: Pages that embed the corrections partial; the show-all/flagged links and the
#: correction forms round-trip which one they live on so a swap stays in place.
_REVIEW_PAGES = ("review", "game")


def build_review_context(
    job: Job,
    entry: int,
    run_dir: Path,
    show_all: bool,
    page: str = "review",
    data_root: Optional[Path] = None,
) -> dict:
    """Rows + applied corrections for the review page/partial.

    Flags are recomputed on the *corrected* events so a saved correction shows
    up as resolved. If the corrections file no longer applies cleanly (e.g. a
    hand-edited row lost its target), the page degrades to uncorrected events
    with the error shown instead of failing.
    """

    events_path = run_dir / EVENTS_FILENAME
    events = load_events(events_path) if events_path.exists() else []
    corrections = _load_run_corrections(run_dir)
    corrections_error = None
    corrected = events
    if corrections:
        try:
            corrected = apply_event_corrections(events, corrections)
        except ValueError as exc:
            corrections_error = str(exc)
    # Item 58: flags are triaged into needs-action/review/informational and
    # rendered in plain language; the default view shows only action-worthy
    # plays, with informational flags collapsed behind the show-all toggle.
    rows = triage_review_rows(
        collect_event_review_rows(corrected, roster=load_configured_roster(cwd=data_root))
    )
    attention = [row for row in rows if row.needs_attention]
    triage = summarize_triage(rows)
    return {
        "job": job,
        "entry": entry,
        "show_all": show_all,
        "page": page if page in _REVIEW_PAGES else "review",
        "rows": rows if show_all else attention,
        "triage": triage,
        "flagged_count": triage["attention"],
        "total_count": triage["total"],
        "corrections": [
            {
                "event_type": correction.event_type.value if correction.event_type else "",
                "timestamp": correction.timestamp_seconds,
                "time_label": format_timestamp(correction.timestamp_seconds),
                "field": correction.field_name,
                "value": correction.value,
            }
            for correction in corrections
        ],
        "corrections_error": corrections_error,
        "edit_fields": EDIT_FIELDS,
        "event_types": [event_type.value for event_type in EventType],
        "halves": [half.value for half in HalfInning],
        "format_timestamp": format_timestamp,
        # Item 63: deep-link row times to the source video when the run's
        # manifest recorded a YouTube video id; None keeps plain text.
        "source_video_id": _run_source_video_id(run_dir),
        "youtube_watch_url": youtube_watch_url,
    }


def _correction_from_form(
    timestamp: str,
    field: str,
    value: str,
    event_type: str,
    match_window_seconds: str,
    reason: str,
    label: str,
    player_number: str,
    player_name: str,
    inning: str,
    half: str,
) -> EventCorrection:
    """Build an EventCorrection from form fields; raises ValueError like the CSV reader."""

    field_name = field.strip()
    if not field_name:
        raise ValueError("correction requires a field")
    event_type_text = event_type.strip()
    inning_text = inning.strip()
    half_text = half.strip()
    window_text = match_window_seconds.strip()
    return EventCorrection(
        timestamp_seconds=parse_timestamp_value(timestamp),
        field_name=field_name,
        value=value.strip(),
        event_type=EventType(event_type_text) if event_type_text else None,
        match_window_seconds=float(window_text) if window_text else 0.5,
        reason=reason.strip() or None,
        label=label.strip() or None,
        player_number=player_number.strip() or None,
        player_name=player_name.strip() or None,
        inning=int(inning_text) if inning_text else None,
        half=HalfInning(half_text) if half_text else None,
    )


_ROSTER_ROW_KEY_PATTERN = re.compile(r"^number_(\d+)$")


def _existing_roster_path(slug: str, base: Optional[Path] = None) -> Path:
    """Resolve a slug to an existing roster CSV, 404-ing on the shared guard.

    The slug validation and path resolution live in ``roster`` so the CLI's
    ``delete-roster`` / ``set-default-roster`` share exactly this guard (70e);
    the route keeps its 404 by translating the plain error at the boundary.
    ``base`` is the data root the ``rosters/`` directory resolves under (70f).
    """

    try:
        return existing_roster_path(slug, base=base)
    except UnknownRoster:
        raise HTTPException(status_code=404, detail="Unknown roster")


def list_roster_summaries(base: Optional[Path] = None) -> list:
    """One display dict per CSV under ``rosters/``, sorted by filename.

    A CSV that fails to load still gets an entry (with its error) so a corrupt
    file is visible in the UI rather than silently missing. ``base`` is the
    data root the ``rosters/`` directory resolves under (70f).
    """

    directory = rosters_directory(base)
    if not directory.is_dir():
        return []
    summaries = []
    for csv_path in sorted(directory.glob("*.csv")):
        summary = {"slug": csv_path.stem, "error": None}
        try:
            roster = load_roster_csv(csv_path)
        except (OSError, ValueError) as exc:
            summary.update(team_name=csv_path.stem, player_count=0, is_default=False)
            summary["error"] = str(exc)
        else:
            summary.update(
                team_name=roster.team_name,
                player_count=len(roster.players),
                is_default=is_configured_default(csv_path, cwd=base),
            )
        summaries.append(summary)
    return summaries


def _roster_row_dicts(players: list) -> list:
    """RosterPlayer objects -> the flat dicts roster_edit.html renders."""

    return [
        {
            "number": player.number,
            "full_name": player.full_name,
            "preferred_name": player.preferred_name or "",
            "display_name": player.display_name or "",
            "aliases": "; ".join(player.aliases),
        }
        for player in players
    ]


def _roster_form_rows(form) -> list:
    """The submitted edit-table rows, in index order, as display dicts."""

    indices = sorted(
        int(match.group(1))
        for key in form
        if (match := _ROSTER_ROW_KEY_PATTERN.match(key)) is not None
    )
    return [
        {
            "number": str(form.get(f"number_{index}") or ""),
            "full_name": str(form.get(f"full_name_{index}") or ""),
            "preferred_name": str(form.get(f"preferred_name_{index}") or ""),
            "display_name": str(form.get(f"display_name_{index}") or ""),
            "aliases": str(form.get(f"aliases_{index}") or ""),
            "delete": bool(form.get(f"delete_{index}")),
        }
        for index in indices
    ]


def _players_from_rows(rows: list) -> list:
    """Validate submitted rows into RosterPlayer objects.

    Mirrors ``parse_team_list``'s guarantees for the row-edit path: unique
    jersey numbers, non-empty names, at least one player. Raises ValueError
    naming the offending row so the page can show it inline.
    """

    players = []
    seen_numbers = set()
    for position, row in enumerate(rows, start=1):
        if row["delete"]:
            continue
        number = row["number"].strip().lstrip("#")
        full_name = re.sub(r"\s+", " ", row["full_name"]).strip()
        preferred_name = row["preferred_name"].strip()
        display_name = row["display_name"].strip()
        aliases = [alias.strip() for alias in row["aliases"].split(";") if alias.strip()]
        if not number and not full_name and not preferred_name and not aliases:
            continue  # untouched blank add-player row
        if not number:
            raise ValueError(f"row {position} is missing a jersey number")
        if not full_name:
            raise ValueError(f"row {position} (#{number}) is missing a player name")
        if number in seen_numbers:
            raise ValueError(f"duplicate jersey number: {number}")
        seen_numbers.add(number)
        players.append(
            RosterPlayer(
                number=number,
                full_name=full_name,
                preferred_name=preferred_name or None,
                display_name=display_name or None,
                aliases=aliases,
            )
        )
    if not players:
        raise ValueError("roster must contain at least one player")
    return players


def create_app(
    store: Optional[JobStore] = None,
    runner: Optional[JobRunner] = None,
    runs_dir: Optional[Path] = None,
    data_root: Optional[Path] = None,
) -> FastAPI:
    """Build the web application. Zero-arg call works as a uvicorn factory.

    Item 57: completed runs found under ``runs_dir`` (default: the runner's
    output dir) are rehydrated into the store at startup so past results
    survive a server restart.

    ``data_root`` (M7 / 70f) is the base ``rosters/``, ``runs/``, ``videos/``,
    and ``sidelinehd.cfg`` resolve against. ``None`` keeps the CWD-relative
    behaviour the CLI's ``serve``/``start`` factory relies on — byte for byte;
    the desktop app passes its data dir so the same paths resolve under it
    without an ``os.chdir``. A caller that supplies its own ``runner`` (the
    desktop launcher does) has already pointed it at ``data_root``; ``data_root``
    then only governs the roster/config routes.
    """

    store = store or JobStore()
    if runner is None:
        runner = (
            JobRunner(store)
            if data_root is None
            else JobRunner(
                store,
                video_dir=data_root / "videos",
                output_dir=data_root / "runs",
                pipeline_kwargs=partial(default_pipeline_kwargs, data_root),
            )
        )
    rehydrate_jobs_from_runs(store, runs_dir if runs_dir is not None else runner.output_dir)
    # tesserocr must be first-imported from the main thread (cysignals
    # installs signal handlers on import); request handlers and job threads
    # would otherwise race to be that first import and crash.
    warm_tesserocr_import()

    app = FastAPI(title="SidelineHD Extractor")
    app.state.store = store
    app.state.runner = runner
    app.state.data_root = data_root
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))
    templates.env.globals.update(
        status_label=status_label,
        stage_label=stage_label,
        kind_label=kind_label,
        server_runtime_label=footer_runtime_label(),
    )

    def _get_job_or_404(job_id: str) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        return job

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        # Item 54a: surface missing external dependencies as an actionable
        # setup card. A healthy install renders nothing.
        missing = [status for status in preflight_dependencies() if not status["ok"]]
        jobs = store.list()
        # Item 54c: roster-first prompt. Runs snapshot the configured roster at
        # run time, so a roster added afterward does not backfill names — the
        # submit page must say so *before* the run and offer a one-click add.
        roster = load_configured_roster(cwd=data_root)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "jobs": jobs,
                "missing_dependencies": missing,
                "roster_configured": roster is not None,
                "roster_team_name": roster.team_name if roster else None,
                "roster_player_count": len(roster.players) if roster else 0,
                "has_rosters": bool(list_roster_summaries(data_root)),
                "how_open": not jobs,
            },
        )

    @app.post("/jobs", response_class=HTMLResponse)
    def submit_job(
        request: Request,
        url: str = Form(default=""),
        kind: str = Form(default="single"),
    ) -> HTMLResponse:
        cleaned_url = url.strip()
        error = _validate_submission(cleaned_url, kind)
        if error is not None:
            return templates.TemplateResponse(
                request, "_form_error.html", {"error": error}, status_code=400
            )
        job = store.create(kind=kind, url=cleaned_url)
        runner.submit(job)
        return templates.TemplateResponse(request, "_job_row.html", {"job": job})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        return templates.TemplateResponse(request, "job_detail.html", {"job": job})

    @app.get("/jobs/{job_id}/status", response_class=HTMLResponse)
    def job_status(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        return templates.TemplateResponse(request, "_job_status.html", {"job": job})

    @app.get("/jobs/{job_id}/detail", response_class=HTMLResponse)
    def job_detail_body(request: Request, job_id: str) -> HTMLResponse:
        """The live-updating body of the detail page (item 54 P3 HTMX poll)."""

        job = _get_job_or_404(job_id)
        return templates.TemplateResponse(request, "_job_detail_body.html", {"job": job})

    @app.get("/jobs/{job_id}/results", response_class=HTMLResponse)
    def job_results(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        blocks = build_result_blocks(job) if job.status == "done" else []
        return templates.TemplateResponse(
            request,
            "results.html",
            {"job": job, "blocks": blocks, "copy_script": PUBLISH_KIT_COPY_SCRIPT},
        )

    def _roster_panel() -> dict:
        """Configured-roster summary for the game page's roster panel."""

        roster = load_configured_roster(cwd=data_root)
        path = configured_roster_path(cwd=data_root)
        edit_url = None
        if (
            path is not None
            and path.suffix == ".csv"
            and path.parent == rosters_directory(data_root)
        ):
            edit_url = f"/rosters/{path.stem}"
        return {
            "team_name": roster.team_name if roster else None,
            "player_count": len(roster.players) if roster else 0,
            "configured": roster is not None,
            "edit_url": edit_url,
        }

    @app.get("/jobs/{job_id}/game", response_class=HTMLResponse)
    def job_game(
        request: Request, job_id: str, entry: int = 0, show: str = "flagged"
    ) -> HTMLResponse:
        """Item 54 P4: one page to manage a game — copy kits, exceptions,
        roster panel, and re-export, without hopping between routes."""

        job = _get_job_or_404(job_id)
        if job.status != "done":
            return templates.TemplateResponse(
                request, "game.html", {"job": job, "pending": True, "entry": entry}
            )
        run_dir = _run_dir_for_entry(job, entry)
        entries = _review_entries(job)
        block = _game_block(entry, _entry_label(job, entry, entries[entry]), entries[entry])
        context = build_review_context(
            job, entry, run_dir, show_all=(show == "all"), page="game", data_root=data_root
        )
        context.update(
            pending=False,
            block=block,
            entry_count=len(entries),
            copy_script=PUBLISH_KIT_COPY_SCRIPT,
            roster_panel=_roster_panel(),
        )
        return templates.TemplateResponse(request, "game.html", context)

    @app.post("/jobs/{job_id}/reexport", response_class=HTMLResponse)
    def reexport_game(job_id: str, entry: int = Form(default=0)) -> RedirectResponse:
        """Re-run the export tail (corrections + current roster) for one game."""

        job = _get_job_or_404(job_id)
        run_dir = _run_dir_for_entry(job, entry)
        finalize_run_exports(
            run_dir,
            corrections=_load_run_corrections(run_dir),
            roster=load_configured_roster(cwd=data_root),
        )
        return RedirectResponse(url=f"/jobs/{job_id}/game?entry={entry}", status_code=303)

    @app.get("/jobs/{job_id}/feedback", response_class=HTMLResponse)
    def job_feedback(request: Request, job_id: str, entry: int = 0) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        if job.status != "done":
            return templates.TemplateResponse(
                request,
                "feedback.html",
                {"job": job, "entry": entry, "pending": True, "note": ""},
            )
        return templates.TemplateResponse(
            request, "feedback.html", _feedback_context(job, entry, note="")
        )

    @app.post("/jobs/{job_id}/feedback/preview", response_class=HTMLResponse)
    def preview_feedback(
        request: Request,
        job_id: str,
        entry: int = Form(default=0),
        note: str = Form(default=""),
    ) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        if job.status != "done":
            return templates.TemplateResponse(
                request,
                "feedback.html",
                {"job": job, "entry": entry, "pending": True, "note": note},
            )
        return templates.TemplateResponse(
            request, "feedback.html", _feedback_context(job, entry, note=note)
        )

    @app.get("/jobs/{job_id}/review", response_class=HTMLResponse)
    def job_review(
        request: Request, job_id: str, entry: int = 0, show: str = "flagged"
    ) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        if job.status != "done":
            return templates.TemplateResponse(
                request, "review.html", {"job": job, "pending": True, "entry": entry}
            )
        run_dir = _run_dir_for_entry(job, entry)
        context = build_review_context(
            job, entry, run_dir, show_all=(show == "all"), data_root=data_root
        )
        context["pending"] = False
        return templates.TemplateResponse(request, "review.html", context)

    def _apply_and_refresh(
        request: Request, job: Job, entry: int, show: str, corrections: list, page: str
    ) -> HTMLResponse:
        """Persist the corrections list, re-export via the shared helper, refresh."""

        run_dir = _run_dir_for_entry(job, entry)
        write_event_corrections(run_dir / CORRECTIONS_FILENAME, corrections)
        finalize_run_exports(
            run_dir, corrections=corrections, roster=load_configured_roster(cwd=data_root)
        )
        context = build_review_context(
            job, entry, run_dir, show_all=(show == "all"), page=page, data_root=data_root
        )
        return templates.TemplateResponse(request, "_review_rows.html", context)

    @app.post("/jobs/{job_id}/corrections", response_class=HTMLResponse)
    def submit_correction(
        request: Request,
        job_id: str,
        entry: int = Form(default=0),
        show: str = Form(default="flagged"),
        page: str = Form(default="review"),
        timestamp: str = Form(default=""),
        field: str = Form(default=""),
        value: str = Form(default=""),
        event_type: str = Form(default=""),
        match_window_seconds: str = Form(default=""),
        reason: str = Form(default=""),
        label: str = Form(default=""),
        player_number: str = Form(default=""),
        player_name: str = Form(default=""),
        inning: str = Form(default=""),
        half: str = Form(default=""),
    ) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        run_dir = _run_dir_for_entry(job, entry)

        def _error(message: str) -> HTMLResponse:
            return templates.TemplateResponse(
                request, "_form_error.html", {"error": message}, status_code=400
            )

        try:
            correction = _correction_from_form(
                timestamp=timestamp,
                field=field,
                value=value,
                event_type=event_type,
                match_window_seconds=match_window_seconds,
                reason=reason,
                label=label,
                player_number=player_number,
                player_name=player_name,
                inning=inning,
                half=half,
            )
            candidate = upsert_event_correction(_load_run_corrections(run_dir), correction)
            # Validate against the run's events before touching the file.
            events_path = run_dir / EVENTS_FILENAME
            events = load_events(events_path) if events_path.exists() else []
            apply_event_corrections(events, candidate)
        except ValueError as exc:
            return _error(str(exc))
        return _apply_and_refresh(request, job, entry, show, candidate, page)

    @app.post("/jobs/{job_id}/corrections/clear", response_class=HTMLResponse)
    def clear_correction(
        request: Request,
        job_id: str,
        entry: int = Form(default=0),
        show: str = Form(default="flagged"),
        page: str = Form(default="review"),
        timestamp: str = Form(default=""),
        field: str = Form(default=""),
        event_type: str = Form(default=""),
    ) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        run_dir = _run_dir_for_entry(job, entry)
        try:
            key = (
                event_type.strip(),
                round(parse_timestamp_value(timestamp), 3),
                field.strip(),
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request, "_form_error.html", {"error": str(exc)}, status_code=400
            )
        remaining = remove_event_correction(_load_run_corrections(run_dir), key)
        return _apply_and_refresh(request, job, entry, show, remaining, page)

    # --- Roster management (item 50 / phase 39d). Rosters hold real player
    # names but are strictly local files under rosters/ (gitignored); these
    # routes render and rewrite them in place and write nothing to any egress
    # surface (job results, feedback log, shared output).

    def _rosters_page(
        request: Request,
        error: Optional[str] = None,
        form_team_name: str = "",
        form_team_list: str = "",
        status_code: int = 200,
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "rosters.html",
            {
                "rosters": list_roster_summaries(data_root),
                "error": error,
                "form_team_name": form_team_name,
                "form_team_list": form_team_list,
            },
            status_code=status_code,
        )

    def _load_roster_or_400(path: Path) -> Roster:
        # A hand-edited CSV can be unloadable; surface that as a 400 (the list
        # page already shows the load error inline) instead of a 500.
        try:
            return load_roster_csv(path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"could not load roster: {exc}")

    def _roster_edit_page(
        request: Request,
        slug: str,
        path: Path,
        rows: Optional[list] = None,
        error: Optional[str] = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        roster = _load_roster_or_400(path)
        return templates.TemplateResponse(
            request,
            "roster_edit.html",
            {
                "slug": slug,
                "team_name": roster.team_name,
                "rows": rows if rows is not None else _roster_row_dicts(roster.players),
                "is_default": is_configured_default(path, cwd=data_root),
                "error": error,
            },
            status_code=status_code,
        )

    @app.get("/rosters", response_class=HTMLResponse)
    def rosters_index(request: Request) -> HTMLResponse:
        return _rosters_page(request)

    @app.post("/rosters", response_class=HTMLResponse)
    def create_roster(
        request: Request,
        team_name: str = Form(default=""),
        team_list: str = Form(default=""),
        set_default: str = Form(default=""),
        next: str = Form(default=""),
    ) -> HTMLResponse:
        # Item 54c: the submit page's roster-first prompt posts here with
        # set_default=1 and next=/ so one click creates the roster, makes it
        # the one runs use, and returns to the submit flow. Both fields are
        # optional; the /rosters page's own form is unchanged.
        cleaned_name = team_name.strip()

        def _error(message: str) -> HTMLResponse:
            return _rosters_page(
                request,
                error=message,
                form_team_name=team_name,
                form_team_list=team_list,
                status_code=400,
            )

        if not cleaned_name:
            return _error("Enter a team name.")
        path = default_roster_path(cleaned_name, base=data_root)
        if path.exists():
            return _error(
                f"A roster already exists at {path} — edit it instead of creating a new one."
            )
        try:
            roster = parse_team_list(team_list, team_name=cleaned_name)
        except ValueError as exc:
            return _error(str(exc))
        write_roster_csv(roster, path)
        if set_default:
            _write_default_roster_config(path, team_name=cleaned_name)
        # Only same-app paths are honored so the redirect cannot leave the UI.
        if next.startswith("/") and not next.startswith("//"):
            return RedirectResponse(url=next, status_code=303)
        return RedirectResponse(url=f"/rosters/{path.stem}", status_code=303)

    @app.get("/rosters/{slug}", response_class=HTMLResponse)
    def roster_edit(request: Request, slug: str) -> HTMLResponse:
        path = _existing_roster_path(slug, data_root)
        return _roster_edit_page(request, slug, path)

    @app.post("/rosters/{slug}", response_class=HTMLResponse)
    async def save_roster(request: Request, slug: str) -> HTMLResponse:
        path = _existing_roster_path(slug, data_root)
        form = await request.form()
        current_team_name = _load_roster_or_400(path).team_name
        submitted_rows = _roster_form_rows(form)
        try:
            if form.get("mode") == "paste":
                # Bulk replace goes through the same parser as the CLI paste flow.
                roster = parse_team_list(
                    str(form.get("team_list") or ""), team_name=current_team_name
                )
            else:
                roster = Roster(
                    team_name=current_team_name, players=_players_from_rows(submitted_rows)
                )
        except ValueError as exc:
            # 400 inline: re-render with the submitted rows so edits are not
            # lost; the CSV on disk is untouched.
            return _roster_edit_page(
                request,
                slug,
                path,
                rows=submitted_rows or None,
                error=str(exc),
                status_code=400,
            )
        write_roster_csv(roster, path)
        return RedirectResponse(url=f"/rosters/{slug}", status_code=303)

    @app.post("/rosters/{slug}/delete", response_class=HTMLResponse)
    def delete_roster(slug: str) -> RedirectResponse:
        # The confirm guard (stronger when this is the configured default) is
        # the onsubmit prompt rendered by the templates.
        path = _existing_roster_path(slug, data_root)
        path.unlink()
        return RedirectResponse(url="/rosters", status_code=303)

    def _write_default_roster_config(path: Path, team_name: Optional[str] = None) -> None:
        # The one config-writing path CLI set-default-roster also uses (70e):
        # preserves the template and any unmanaged key, and only overrides the
        # team name when the 54c one-click path passes the just-typed one (so
        # the pretty name survives; the CSV stores only the stem until item 52).
        set_default_roster_config(path, team_name=team_name, cwd=data_root)

    @app.post("/rosters/{slug}/set-default", response_class=HTMLResponse)
    def set_default_roster(slug: str) -> RedirectResponse:
        _write_default_roster_config(_existing_roster_path(slug, data_root))
        return RedirectResponse(url="/rosters", status_code=303)

    return app
