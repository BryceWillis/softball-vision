"""Video probing and hashing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple

from sidelinehd_extractor.models import PathLike, Video


def _cv2():
    import cv2

    return cv2


def sha256_file(path: PathLike, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 hex digest for a local file."""

    source = Path(path).expanduser()
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(path: PathLike, *, compute_hash: bool = False) -> Video:
    """Read basic video metadata with OpenCV."""

    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(source)

    cv2 = _cv2()
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError(f"Could not open video: {source}")

        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or None
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or None
        duration_seconds = None
        if fps and frame_count:
            duration_seconds = frame_count / fps

        return Video(
            path=source,
            sha256=sha256_file(source) if compute_hash else None,
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
        )
    finally:
        capture.release()


def read_frame_at(path: PathLike, timestamp_seconds: float):
    """Return a frame from a video at approximately ``timestamp_seconds``."""

    if timestamp_seconds < 0:
        raise ValueError("timestamp_seconds must be non-negative")

    source = Path(path).expanduser()
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError(f"Could not open video: {source}")

        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError(
                _frame_read_error(
                    source,
                    timestamp_seconds,
                    _capture_duration_seconds(capture, cv2),
                )
            )
        return frame
    finally:
        capture.release()


def read_frames_at(path: PathLike, timestamps_seconds: Iterable[float]) -> Iterator[Tuple[float, object]]:
    """Yield frames at approximate timestamps while keeping the video open."""

    source = Path(path).expanduser()
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise ValueError(f"Could not open video: {source}")

        for timestamp_seconds in timestamps_seconds:
            if timestamp_seconds < 0:
                raise ValueError("timestamps_seconds must be non-negative")
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise ValueError(
                    _frame_read_error(
                        source,
                        timestamp_seconds,
                        _capture_duration_seconds(capture, cv2),
                    )
                )
            yield timestamp_seconds, frame
    finally:
        capture.release()


def _capture_duration_seconds(capture, cv2) -> Optional[float]:
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or None
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or None
    if fps and frame_count:
        return frame_count / fps
    return None


def _frame_read_error(
    source: Path,
    timestamp_seconds: float,
    duration_seconds: Optional[float],
) -> str:
    message = f"Could not read frame at {timestamp_seconds:.3f}s from {source}"
    if duration_seconds is not None:
        message += f" (duration: {duration_seconds:.3f}s)"
    return message
