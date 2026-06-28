"""Run-directory processing for the initial local pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from sidelinehd_extractor.config import default_overlay_template
from sidelinehd_extractor.crops import crop_frame, save_crop
from sidelinehd_extractor.models import OCRSample, OverlayTemplate, Roster
from sidelinehd_extractor.ocr import OCRCallable, no_ocr
from sidelinehd_extractor.serialization import to_plain_data
from sidelinehd_extractor.video import probe_video, read_frames_at


@dataclass(frozen=True)
class ProcessResult:
    """Summary of a process run."""

    run_dir: Path
    manifest_path: Path
    samples_path: Path
    sample_count: int
    crop_count: int


def sample_timestamps(
    duration_seconds: float,
    sample_every_seconds: float,
    start_seconds: float = 0.0,
    end_seconds: Optional[float] = None,
) -> List[float]:
    """Generate bounded sample timestamps for a video."""

    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")
    if sample_every_seconds <= 0:
        raise ValueError("sample_every_seconds must be positive")
    if start_seconds < 0:
        raise ValueError("start_seconds must be non-negative")

    stop_seconds = duration_seconds if end_seconds is None else min(end_seconds, duration_seconds)
    if stop_seconds < start_seconds:
        raise ValueError("end_seconds must be >= start_seconds")

    timestamps = []
    current = start_seconds
    while current <= stop_seconds:
        timestamps.append(round(current, 3))
        current += sample_every_seconds
    return timestamps


def select_template_regions(
    template: OverlayTemplate,
    selected_fields: Optional[Iterable[str]] = None,
) -> Dict[str, object]:
    """Return the template regions requested by the user."""

    if selected_fields is None:
        return dict(template.regions)

    fields = [field.strip() for field in selected_fields if field.strip()]
    if not fields:
        return dict(template.regions)

    missing = [field for field in fields if field not in template.regions]
    if missing:
        raise ValueError(f"template does not include field(s): {', '.join(missing)}")

    return {field: template.regions[field] for field in fields}


def create_run_dir(output_dir: Path, video_path: Path, created_at: Optional[datetime] = None) -> Path:
    """Create a unique run directory under ``output_dir``."""

    timestamp = (created_at or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir.expanduser() / f"{video_path.stem}-{timestamp}"
    suffix = 1
    candidate = run_dir
    while candidate.exists():
        suffix += 1
        candidate = output_dir.expanduser() / f"{video_path.stem}-{timestamp}-{suffix}"
    candidate.mkdir(parents=True)
    return candidate


def write_json(path: Path, value: object) -> None:
    """Write JSON with project-native dataclass serialization."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_plain_data(value), handle, indent=2)
        handle.write("\n")


def write_jsonl(path: Path, values: Iterable[object]) -> int:
    """Write JSON lines and return the number of records written."""

    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(to_plain_data(value)))
            handle.write("\n")
            count += 1
    return count


def process_video(
    video_path: Path,
    output_dir: Path,
    template: Optional[OverlayTemplate] = None,
    roster: Optional[Roster] = None,
    sample_every_seconds: float = 5.0,
    start_seconds: float = 0.0,
    end_seconds: Optional[float] = None,
    save_crops: bool = True,
    ocr: OCRCallable = no_ocr,
    fields: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[int, int, float, int, int], None]] = None,
    compute_video_hash: bool = False,
) -> ProcessResult:
    """Sample a local video, crop configured overlay regions, and persist OCR samples."""

    overlay_template = template or default_overlay_template()
    video = probe_video(video_path, compute_hash=compute_video_hash)
    if video.duration_seconds is None:
        raise ValueError("video duration is unavailable")

    run_dir = create_run_dir(output_dir, Path(video.path))
    crops_dir = run_dir / "crops"
    samples_path = run_dir / "samples.jsonl"
    manifest_path = run_dir / "manifest.json"
    selected_regions = select_template_regions(overlay_template, fields)

    samples = []
    crop_count = 0
    timestamps = sample_timestamps(
        video.duration_seconds,
        sample_every_seconds,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    )
    total_timestamps = len(timestamps)
    total_expected_samples = total_timestamps * len(selected_regions)
    for timestamp_index, (timestamp_seconds, frame) in enumerate(
        read_frames_at(video.path, timestamps),
        start=1,
    ):
        for field_name, region in selected_regions.items():
            crop = crop_frame(frame, region)
            crop_path = None
            if save_crops:
                safe_field_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", field_name).strip("_")
                safe_field_name = safe_field_name or "field"
                timestamp_token = f"{timestamp_seconds:010.3f}".replace(".", "p")
                crop_name = f"{timestamp_token}_{safe_field_name}.png"
                crop_path = Path("crops") / crop_name
                save_crop(crop, run_dir / crop_path)
                crop_count += 1

            ocr_result = ocr(crop, field_name)
            samples.append(
                OCRSample(
                    video_sha256=video.sha256,
                    timestamp_seconds=timestamp_seconds,
                    field_name=field_name,
                    raw_text=ocr_result.text,
                    normalized_text=ocr_result.normalized_text,
                    confidence=ocr_result.confidence,
                    crop_path=crop_path,
                )
            )
        if progress is not None:
            progress(
                timestamp_index,
                total_timestamps,
                timestamp_seconds,
                len(samples),
                total_expected_samples,
            )

    write_jsonl(samples_path, samples)
    write_json(
        manifest_path,
        {
            "created_at": datetime.now(timezone.utc),
            "video": video,
            "template": overlay_template,
            "roster": roster,
            "sample_every_seconds": sample_every_seconds,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "save_crops": save_crops,
            "ocr_backend": getattr(ocr, "__name__", ocr.__class__.__name__),
            "compute_video_hash": compute_video_hash,
            "fields": list(selected_regions.keys()),
            "samples_path": samples_path.relative_to(run_dir),
            "crops_dir": crops_dir.relative_to(run_dir),
        },
    )

    return ProcessResult(
        run_dir=run_dir,
        manifest_path=manifest_path,
        samples_path=samples_path,
        sample_count=len(samples),
        crop_count=crop_count,
    )
