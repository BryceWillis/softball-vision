"""FastAPI application factory and routes for the local web UI.

Loopback-only, single-user, no auth: run it with ``sidelinehd-extractor serve``
which binds ``127.0.0.1`` by default. No route renders roster player names;
job results carry run/export paths and jersey numbers only. All assets are
vendored (``static/htmx.min.js``) so the app works fully offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sidelinehd_extractor.webapp.jobs import Job, JobRunner, JobStore

_PACKAGE_DIR = Path(__file__).resolve().parent

_VALID_KINDS = ("single", "playlist")


def _validate_submission(url: str, kind: str) -> Optional[str]:
    """Return an error message for a bad submission, or None if valid."""

    if kind not in _VALID_KINDS:
        return f"Unknown job kind: {kind!r}."
    if not url:
        return "Enter a YouTube video or playlist URL."
    if not (url.startswith("http://") or url.startswith("https://")):
        return "The URL must start with http:// or https://."
    return None


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

    return app
