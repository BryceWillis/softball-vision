"""Calibration-frame extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from sidelinehd_extractor.crops import fraction_to_pixel_region
from sidelinehd_extractor.models import OverlayTemplate
from sidelinehd_extractor.video import probe_video, read_frames_at


@dataclass(frozen=True)
class CalibrationFrame:
    """One extracted full-frame image for overlay calibration."""

    timestamp_seconds: float
    path: Path


@dataclass(frozen=True)
class CalibrationResult:
    """Summary of calibration-frame extraction."""

    video_path: Path
    output_dir: Path
    frames: List[CalibrationFrame]


def parse_timestamp_value(value: str) -> float:
    """Parse seconds, M:SS, or H:MM:SS into seconds."""

    text = value.strip()
    if not text:
        raise ValueError("timestamp cannot be empty")
    if ":" not in text:
        seconds = float(text)
        if seconds < 0:
            raise ValueError("timestamp must be non-negative")
        return seconds

    parts = text.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError(f"invalid timestamp: {value}")

    numbers = [float(part) for part in parts]
    if any(part < 0 for part in numbers):
        raise ValueError("timestamp must be non-negative")
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds

    hours, minutes, seconds = numbers
    return hours * 3600 + minutes * 60 + seconds


def parse_timestamp_list(values: Iterable[str]) -> List[float]:
    """Parse CLI timestamp values into sorted unique seconds."""

    timestamps = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                timestamps.append(parse_timestamp_value(item))
    return sorted(set(round(timestamp, 3) for timestamp in timestamps))


def default_calibration_timestamps(duration_seconds: Optional[float]) -> List[float]:
    """Pick a few timestamps likely to show the steady-state scorebug."""

    if duration_seconds is None or duration_seconds <= 0:
        return [30.0, 120.0, 300.0]

    candidates = [
        30.0,
        120.0,
        300.0,
        duration_seconds * 0.25,
        duration_seconds * 0.50,
        duration_seconds * 0.75,
    ]
    return sorted(set(round(min(candidate, max(duration_seconds - 1, 0)), 3) for candidate in candidates))


def extract_calibration_frames(
    video_path: Path,
    output_dir: Path,
    timestamps_seconds: Optional[List[float]] = None,
) -> CalibrationResult:
    """Extract full-frame PNGs for visually tuning overlay template fractions."""

    import cv2

    video = probe_video(video_path)
    timestamps = timestamps_seconds or default_calibration_timestamps(video.duration_seconds)
    destination = output_dir.expanduser()
    destination.mkdir(parents=True, exist_ok=True)

    frames = []
    for timestamp_seconds, frame in read_frames_at(video.path, timestamps):
        token = f"{timestamp_seconds:010.3f}".replace(".", "p")
        frame_path = destination / f"frame_{token}.png"
        ok = cv2.imwrite(str(frame_path), frame)
        if not ok:
            raise ValueError(f"Could not write calibration frame: {frame_path}")
        frames.append(CalibrationFrame(timestamp_seconds=timestamp_seconds, path=frame_path))

    return CalibrationResult(video_path=Path(video.path), output_dir=destination, frames=frames)


def render_template_guide(frame, template: OverlayTemplate, output_path: Path) -> Path:
    """Render template regions over a frame for visual calibration."""

    import cv2

    if frame is None or len(frame.shape) < 2:
        raise ValueError("frame must be an image array")

    image = frame.copy()
    frame_height, frame_width = image.shape[:2]
    for index, (name, region) in enumerate(template.regions.items()):
        pixel_region = fraction_to_pixel_region(region, frame_width, frame_height)
        color = _guide_color(index)
        cv2.rectangle(
            image,
            (pixel_region.x, pixel_region.y),
            (pixel_region.x2 - 1, pixel_region.y2 - 1),
            color,
            2,
        )
        label_y = max(pixel_region.y - 5, 12)
        cv2.putText(
            image,
            name,
            (pixel_region.x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            color,
            1,
            cv2.LINE_AA,
        )

    destination = output_path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(destination), image)
    if not ok:
        raise ValueError(f"Could not write template guide image: {destination}")
    return destination


def _guide_color(index: int) -> tuple:
    colors = [
        (0, 255, 255),
        (0, 180, 255),
        (255, 120, 0),
        (80, 255, 80),
        (255, 80, 255),
        (255, 255, 80),
        (80, 160, 255),
    ]
    return colors[index % len(colors)]
