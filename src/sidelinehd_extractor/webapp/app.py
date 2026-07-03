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

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sidelinehd_extractor.calibration import parse_timestamp_value
from sidelinehd_extractor.config import (
    ProjectConfig,
    load_project_config,
    load_project_config_values,
    load_roster,
    load_roster_csv,
    write_project_config,
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
from sidelinehd_extractor.publish import PUBLISH_KIT_COPY_SCRIPT, render_publish_kit_fragment
from sidelinehd_extractor.review import collect_event_review_rows
from sidelinehd_extractor.roster import default_roster_path, parse_team_list, write_roster_csv
from sidelinehd_extractor.review_report import summarize_review_report_text
from sidelinehd_extractor.webapp.jobs import Job, JobRunner, JobStore
from sidelinehd_extractor.workflow import finalize_run_exports

_PACKAGE_DIR = Path(__file__).resolve().parent

_VALID_KINDS = ("single", "playlist")

REVIEW_REPORT_FILENAME = "review_report.md"
CORRECTIONS_FILENAME = "corrections.csv"
EVENTS_FILENAME = "events.jsonl"
FEEDBACK_ISSUE_TITLE = "SidelineHD Extractor Feedback"

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
        "report_path": str(report_path) if report_path is not None else None,
    }


def build_result_blocks(job: Job) -> list:
    """Build the per-game blocks for a done job's results page, in batch order."""

    result = job.result or {}
    if job.kind == "playlist":
        blocks = []
        for index, entry in enumerate(result.get("entries") or []):
            label = entry.get("title") or entry.get("video_id") or f"Entry {index + 1}"
            label = f"{index + 1}. {label}"
            if entry.get("status") == "failed":
                blocks.append(_error_block(label, entry.get("error") or "Processing failed."))
            else:
                blocks.append(_game_block(index, label, entry))
        return blocks

    video_path = result.get("video_path")
    run_dir = result.get("run_dir")
    label = Path(video_path).name if video_path else Path(run_dir).name if run_dir else job.url
    return [_game_block(0, label, result)]


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


def _feedback_handoff_links(markdown: str) -> dict:
    return {
        "github_issue_url": f"{PROJECT_URL.rstrip('/')}/issues/new?"
        + urlencode({"title": FEEDBACK_ISSUE_TITLE, "body": markdown}),
        "mailto_url": "mailto:?"
        + urlencode({"subject": FEEDBACK_ISSUE_TITLE, "body": markdown}),
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


def load_configured_roster() -> Optional[Roster]:
    """The roster the job ran with, re-derived from the project config.

    Assumption (flagged in the item 49 design): jobs load the roster via the
    same project config, so re-deriving here matches what the run used unless
    the config changed in between. Any failure degrades to roster-less flags.
    """

    try:
        config = load_project_config()
        if not config.roster:
            return None
        return load_roster(config.roster, team_name=config.team_name)
    except Exception:  # noqa: BLE001 - review must work without a config
        return None


def _load_run_corrections(run_dir: Path) -> list:
    corrections_path = run_dir / CORRECTIONS_FILENAME
    if not corrections_path.exists():
        return []
    return load_event_corrections(corrections_path)


def build_review_context(job: Job, entry: int, run_dir: Path, show_all: bool) -> dict:
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
    rows = collect_event_review_rows(corrected, roster=load_configured_roster())
    flagged = [row for row in rows if row.flags]
    return {
        "job": job,
        "entry": entry,
        "show_all": show_all,
        "rows": rows if show_all else flagged,
        "flagged_count": len(flagged),
        "total_count": len(rows),
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


ROSTERS_DIRNAME = "rosters"

# Slugs are produced by ``slugify`` (lowercase alphanumerics and underscores),
# so anything else in the URL is not a roster we wrote — reject it before it
# can name a path outside ``rosters/``.
_ROSTER_SLUG_PATTERN = re.compile(r"^[a-z0-9_]+$")

_ROSTER_ROW_KEY_PATTERN = re.compile(r"^number_(\d+)$")


def _roster_csv_path(slug: str) -> Path:
    if not _ROSTER_SLUG_PATTERN.match(slug):
        raise HTTPException(status_code=404, detail="Unknown roster")
    return Path(ROSTERS_DIRNAME) / f"{slug}.csv"


def _existing_roster_path(slug: str) -> Path:
    path = _roster_csv_path(slug)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Unknown roster")
    return path


def _configured_roster_path() -> Optional[Path]:
    """The raw roster path from ``sidelinehd.cfg``, unvalidated."""

    value = load_project_config_values().get("roster")
    if not value:
        return None
    return Path(value).expanduser()


def _is_configured_default(path: Path) -> bool:
    configured = _configured_roster_path()
    if configured is None:
        return False
    try:
        return configured.resolve() == path.resolve()
    except OSError:
        return False


def list_roster_summaries() -> list:
    """One display dict per CSV under ``rosters/``, sorted by filename.

    A CSV that fails to load still gets an entry (with its error) so a corrupt
    file is visible in the UI rather than silently missing.
    """

    directory = Path(ROSTERS_DIRNAME)
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
                is_default=_is_configured_default(csv_path),
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


def create_app(store: Optional[JobStore] = None, runner: Optional[JobRunner] = None) -> FastAPI:
    """Build the web application. Zero-arg call works as a uvicorn factory."""

    store = store or JobStore()
    runner = runner or JobRunner(store)

    app = FastAPI(title="SidelineHD Extractor")
    app.state.store = store
    app.state.runner = runner
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))

    def _get_job_or_404(job_id: str) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        return job

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", {"jobs": store.list()})

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

    @app.get("/jobs/{job_id}/results", response_class=HTMLResponse)
    def job_results(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        blocks = build_result_blocks(job) if job.status == "done" else []
        return templates.TemplateResponse(
            request,
            "results.html",
            {"job": job, "blocks": blocks, "copy_script": PUBLISH_KIT_COPY_SCRIPT},
        )

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
        context = build_review_context(job, entry, run_dir, show_all=(show == "all"))
        context["pending"] = False
        return templates.TemplateResponse(request, "review.html", context)

    def _apply_and_refresh(
        request: Request, job: Job, entry: int, show: str, corrections: list
    ) -> HTMLResponse:
        """Persist the corrections list, re-export via the shared helper, refresh."""

        run_dir = _run_dir_for_entry(job, entry)
        write_event_corrections(run_dir / CORRECTIONS_FILENAME, corrections)
        finalize_run_exports(
            run_dir, corrections=corrections, roster=load_configured_roster()
        )
        context = build_review_context(job, entry, run_dir, show_all=(show == "all"))
        return templates.TemplateResponse(request, "_review_rows.html", context)

    @app.post("/jobs/{job_id}/corrections", response_class=HTMLResponse)
    def submit_correction(
        request: Request,
        job_id: str,
        entry: int = Form(default=0),
        show: str = Form(default="flagged"),
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
        return _apply_and_refresh(request, job, entry, show, candidate)

    @app.post("/jobs/{job_id}/corrections/clear", response_class=HTMLResponse)
    def clear_correction(
        request: Request,
        job_id: str,
        entry: int = Form(default=0),
        show: str = Form(default="flagged"),
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
        return _apply_and_refresh(request, job, entry, show, remaining)

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
                "rosters": list_roster_summaries(),
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
                "is_default": _is_configured_default(path),
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
    ) -> HTMLResponse:
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
        path = default_roster_path(cleaned_name)
        if path.exists():
            return _error(
                f"A roster already exists at {path} — edit it instead of creating a new one."
            )
        try:
            roster = parse_team_list(team_list, team_name=cleaned_name)
        except ValueError as exc:
            return _error(str(exc))
        write_roster_csv(roster, path)
        return RedirectResponse(url=f"/rosters/{path.stem}", status_code=303)

    @app.get("/rosters/{slug}", response_class=HTMLResponse)
    def roster_edit(request: Request, slug: str) -> HTMLResponse:
        path = _existing_roster_path(slug)
        return _roster_edit_page(request, slug, path)

    @app.post("/rosters/{slug}", response_class=HTMLResponse)
    async def save_roster(request: Request, slug: str) -> HTMLResponse:
        path = _existing_roster_path(slug)
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
        path = _existing_roster_path(slug)
        path.unlink()
        return RedirectResponse(url="/rosters", status_code=303)

    @app.post("/rosters/{slug}/set-default", response_class=HTMLResponse)
    def set_default_roster(slug: str) -> RedirectResponse:
        path = _existing_roster_path(slug)
        # Reuse the item 28 config writer; preserve the other keys verbatim.
        values = load_project_config_values()
        write_project_config(
            ProjectConfig(
                roster=path,
                template=Path(values["template"]) if values.get("template") else None,
                team_name=values.get("team_name"),
            )
        )
        return RedirectResponse(url="/rosters", status_code=303)

    return app
