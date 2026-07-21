"""Batch orchestration for playlist-sized game processing runs."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from sidelinehd_extractor.corrections import EventCorrection
from sidelinehd_extractor.events import DetectionConfig
from sidelinehd_extractor.models import OverlayTemplate, Roster
from sidelinehd_extractor.naming import slugify
from sidelinehd_extractor.ocr import OCRCallable, no_ocr
from sidelinehd_extractor.processing import (
    SamplingOptions,
    read_jsonl,
    write_jsonl_atomic,
)
from sidelinehd_extractor.workflow import (
    ExportOptions,
    RunYoutubeGameResult,
    record_youtube_source,
    run_youtube_game,
)
from sidelinehd_extractor.youtube import (
    DownloadOptions,
    PlaylistEntry,
    YTDLPError,
    list_playlist_videos,
)


@dataclass(frozen=True)
class PlaylistBatchItemResult:
    """One playlist entry's batch outcome."""

    video_id: str
    url: str
    title: str
    index: int
    status: str
    attempts: int = 0
    run_dir: Optional[Path] = None
    chapters_path: Optional[Path] = None
    at_bats_path: Optional[Path] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class PlaylistBatchResult:
    """Summary of a playlist batch run."""

    playlist_url: str
    state_path: Path
    summary_path: Path
    summary: str
    total: int
    processed: int
    skipped: int
    failed: int
    entries: List[PlaylistBatchItemResult]


def run_playlist_batch(
    playlist_url: str,
    video_dir: Path,
    output_dir: Path,
    template: Optional[OverlayTemplate] = None,
    roster: Optional[Roster] = None,
    ocr: OCRCallable = no_ocr,
    progress: Optional[Callable[[int, int, float, int, int], None]] = None,
    output_prefix: Optional[Path] = None,
    corrections: Optional[Iterable[EventCorrection]] = None,
    stage_progress: Optional[Callable[[str], None]] = None,
    sampling: SamplingOptions = SamplingOptions(),
    export_options: ExportOptions = ExportOptions(),
    detection: DetectionConfig = DetectionConfig(),
    download_options: DownloadOptions = DownloadOptions(),
    batting_half_inference_progress: Optional[Callable[[object], None]] = None,
    auto_detect_template: bool = True,
    force: bool = False,
    limit: Optional[int] = None,
    start_index: int = 0,
    retries: int = 2,
    state_path: Optional[Path] = None,
    list_videos: Callable[..., List[PlaylistEntry]] = list_playlist_videos,
    run_youtube: Callable[..., RunYoutubeGameResult] = run_youtube_game,
    sleep: Callable[[float], None] = time.sleep,
    batch_progress: Optional[Callable[[str], None]] = None,
) -> PlaylistBatchResult:
    """Process every video in a YouTube playlist with resumable state."""

    if start_index < 0:
        raise ValueError("start_index must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    if retries < 0:
        raise ValueError("retries must be non-negative")

    destination = output_dir.expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    state = state_path.expanduser() if state_path else destination / "playlist_state.jsonl"
    summary_path = destination / "batch_summary.md"
    state.parent.mkdir(parents=True, exist_ok=True)
    previous = _load_playlist_state(state)
    state_snapshot = dict(previous)
    entries = _slice_entries(
        list_videos(playlist_url, youtube_client=download_options.youtube_client),
        start_index=start_index,
        limit=limit,
    )

    results = []
    total = len(entries)
    for position, entry in enumerate(entries, start=1):
        prior = previous.get(entry.video_id)
        if not force and prior and _is_complete_prior_result(prior):
            result = _skipped_result(entry, prior)
            results.append(result)
            _write_playlist_state(state, state_snapshot)
            _batch_progress(batch_progress, position, total, result)
            continue

        result = _run_playlist_entry(
            entry=entry,
            video_dir=video_dir,
            output_dir=output_dir,
            template=template,
            roster=roster,
            ocr=ocr,
            progress=progress,
            output_prefix=_entry_output_prefix(output_prefix, entry),
            corrections=corrections,
            stage_progress=stage_progress,
            sampling=sampling,
            export_options=export_options,
            detection=detection,
            download_options=download_options,
            batting_half_inference_progress=batting_half_inference_progress,
            auto_detect_template=auto_detect_template,
            retries=retries,
            run_youtube=run_youtube,
            sleep=sleep,
        )
        results.append(result)
        state_snapshot[entry.video_id] = result
        _write_playlist_state(state, state_snapshot)
        _batch_progress(batch_progress, position, total, result)

    counts = Counter(item.status for item in results)
    processed = counts["done"]
    skipped = counts["skipped"]
    failed = counts["failed"]
    summary = _batch_summary_line(total, processed, skipped, failed)
    _write_batch_summary(
        summary_path,
        playlist_url=playlist_url,
        results=results,
        summary=summary,
    )

    return PlaylistBatchResult(
        playlist_url=playlist_url,
        state_path=state,
        summary_path=summary_path,
        summary=summary,
        total=total,
        processed=processed,
        skipped=skipped,
        failed=failed,
        entries=results,
    )


def _run_playlist_entry(
    *,
    entry: PlaylistEntry,
    video_dir: Path,
    output_dir: Path,
    template: Optional[OverlayTemplate],
    roster: Optional[Roster],
    ocr: OCRCallable,
    progress: Optional[Callable[[int, int, float, int, int], None]],
    output_prefix: Optional[Path],
    corrections: Optional[Iterable[EventCorrection]],
    stage_progress: Optional[Callable[[str], None]],
    sampling: SamplingOptions,
    export_options: ExportOptions,
    detection: DetectionConfig,
    download_options: DownloadOptions,
    batting_half_inference_progress: Optional[Callable[[object], None]],
    auto_detect_template: bool,
    retries: int,
    run_youtube: Callable[..., RunYoutubeGameResult],
    sleep: Callable[[float], None],
) -> PlaylistBatchItemResult:
    # Each playlist entry is downloaded as a single video, whatever the caller
    # asked for: the batch already walked the playlist, so letting
    # ``no_playlist=False`` through would re-download the whole list per entry.
    entry_download_options = replace(download_options, no_playlist=True)
    for attempt in range(1, retries + 2):
        try:
            result = run_youtube(
                url=entry.url,
                video_dir=video_dir,
                output_dir=output_dir,
                template=template,
                roster=roster,
                ocr=ocr,
                progress=progress,
                output_prefix=output_prefix,
                corrections=corrections,
                stage_progress=stage_progress,
                sampling=sampling,
                export_options=export_options,
                detection=detection,
                download_options=entry_download_options,
                batting_half_inference_progress=batting_half_inference_progress,
                auto_detect_template=auto_detect_template,
            )
            record_youtube_source(
                result.run.manifest_path,
                entry.video_id,
                entry.url,
                playlist_index=entry.index,
                title=entry.title,
            )
            return _result_from_entry(
                entry,
                status="done",
                attempts=attempt,
                run_dir=result.run.run_dir,
                chapters_path=result.run.chapters_path,
                at_bats_path=result.run.at_bats_path,
            )
        except YTDLPError as exc:
            if attempt >= retries + 1:
                return _result_from_entry(
                    entry,
                    status="failed",
                    attempts=attempt,
                    error=str(exc),
                )
            sleep(min(2 ** (attempt - 1), 30))
        except Exception as exc:
            return _result_from_entry(
                entry,
                status="failed",
                attempts=attempt,
                error=str(exc),
            )

    return _result_from_entry(
        entry,
        status="failed",
        attempts=0,
        error="retry loop did not run",
    )


def _slice_entries(
    entries: List[PlaylistEntry],
    start_index: int,
    limit: Optional[int],
) -> List[PlaylistEntry]:
    selected = entries[start_index:]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _load_playlist_state(path: Path) -> Dict[str, PlaylistBatchItemResult]:
    if not path.exists():
        return {}
    latest: Dict[str, PlaylistBatchItemResult] = {}
    for row in read_jsonl(path):
        if not isinstance(row, dict):
            continue
        video_id = str(row.get("video_id") or "")
        if not video_id:
            continue
        latest[video_id] = PlaylistBatchItemResult(
            video_id=video_id,
            url=str(row.get("url") or ""),
            title=str(row.get("title") or video_id),
            index=int(row.get("index") or 0),
            status=str(row.get("status") or ""),
            attempts=int(row.get("attempts") or 0),
            run_dir=Path(row["run_dir"]) if row.get("run_dir") else None,
            chapters_path=Path(row["chapters_path"]) if row.get("chapters_path") else None,
            at_bats_path=Path(row["at_bats_path"]) if row.get("at_bats_path") else None,
            error=row.get("error"),
        )
    return latest


def _write_playlist_state(
    path: Path,
    state: Dict[str, PlaylistBatchItemResult],
) -> None:
    write_jsonl_atomic(
        path,
        sorted(state.values(), key=lambda item: (item.index, item.video_id)),
    )


def _write_batch_summary(
    path: Path,
    playlist_url: str,
    results: List[PlaylistBatchItemResult],
    summary: str,
) -> None:
    lines = [
        "# Playlist Batch Summary",
        "",
        f"Playlist: {playlist_url}",
        "",
        summary,
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result.index}. {result.title}",
                "",
                f"- Status: {result.status}",
                f"- URL: {result.url}",
                f"- Attempts: {result.attempts}",
            ]
        )
        if result.run_dir is not None:
            lines.append(f"- Run directory: {result.run_dir}")
        if result.chapters_path is not None:
            lines.append(f"- Chapters: {result.chapters_path}")
        if result.at_bats_path is not None:
            lines.append(f"- At-bats: {result.at_bats_path}")
        if result.error:
            lines.append(f"- Error: {result.error}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _batch_summary_line(total: int, processed: int, skipped: int, failed: int) -> str:
    return (
        f"Playlist batch complete: {processed} processed, {skipped} skipped, "
        f"{failed} failed out of {total}."
    )


def _skipped_result(
    entry: PlaylistEntry,
    prior: PlaylistBatchItemResult,
) -> PlaylistBatchItemResult:
    return _result_from_entry(
        entry,
        status="skipped",
        attempts=0,
        run_dir=prior.run_dir,
        chapters_path=prior.chapters_path,
        at_bats_path=prior.at_bats_path,
    )


def _entry_output_prefix(output_prefix: Optional[Path], entry: PlaylistEntry) -> Optional[Path]:
    if output_prefix is None:
        return None
    slug = slugify(entry.title or entry.video_id, fallback=entry.video_id or "game")
    base = output_prefix.expanduser()
    return base / slug / slug


def _is_complete_prior_result(result: PlaylistBatchItemResult) -> bool:
    if result.status != "done":
        return False
    required_paths = [result.run_dir, result.chapters_path, result.at_bats_path]
    return all(path is not None and path.exists() for path in required_paths)


def _result_from_entry(
    entry: PlaylistEntry,
    status: str,
    attempts: int = 0,
    run_dir: Optional[Path] = None,
    chapters_path: Optional[Path] = None,
    at_bats_path: Optional[Path] = None,
    error: Optional[str] = None,
) -> PlaylistBatchItemResult:
    return PlaylistBatchItemResult(
        video_id=entry.video_id,
        url=entry.url,
        title=entry.title,
        index=entry.index,
        status=status,
        attempts=attempts,
        run_dir=run_dir,
        chapters_path=chapters_path,
        at_bats_path=at_bats_path,
        error=error,
    )


def _batch_progress(
    callback: Optional[Callable[[str], None]],
    position: int,
    total: int,
    result: PlaylistBatchItemResult,
) -> None:
    if callback is None:
        return
    if result.status == "failed":
        callback(f"[{position}/{total}] Failed {result.title}: {result.error}")
    elif result.status == "skipped":
        callback(f"[{position}/{total}] Skipped {result.title}")
    else:
        callback(f"[{position}/{total}] Processed {result.title}")
