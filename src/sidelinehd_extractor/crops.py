"""Frame crop helpers for overlay regions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

from sidelinehd_extractor.models import RegionFraction
from sidelinehd_extractor.video import read_frame_at

PathLike = Union[str, Path]


@dataclass(frozen=True)
class PixelRegion:
    """A rectangular pixel region in an image."""

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height


def fraction_to_pixel_region(
    region: RegionFraction,
    frame_width: int,
    frame_height: int,
) -> PixelRegion:
    """Convert normalized region fractions into bounded pixel coordinates."""

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame dimensions must be positive")

    x = round(region.x * frame_width)
    y = round(region.y * frame_height)
    x2 = round((region.x + region.width) * frame_width)
    y2 = round((region.y + region.height) * frame_height)

    x = min(max(x, 0), frame_width)
    y = min(max(y, 0), frame_height)
    x2 = min(max(x2, x + 1), frame_width)
    y2 = min(max(y2, y + 1), frame_height)

    return PixelRegion(x=x, y=y, width=x2 - x, height=y2 - y)


def crop_frame(frame, region: RegionFraction):
    """Extract a crop from an OpenCV frame using normalized coordinates."""

    if frame is None or len(frame.shape) < 2:
        raise ValueError("frame must be an image array")

    frame_height, frame_width = frame.shape[:2]
    pixel_region = fraction_to_pixel_region(region, frame_width, frame_height)
    return frame[pixel_region.y : pixel_region.y2, pixel_region.x : pixel_region.x2]


def extract_crop_from_video(path: PathLike, timestamp_seconds: float, region: RegionFraction):
    """Read a frame at a timestamp and return the requested crop."""

    frame = read_frame_at(path, timestamp_seconds)
    return crop_frame(frame, region)


def save_crop(image, output_path: PathLike) -> Path:
    """Write a crop image to disk."""

    import cv2

    destination = Path(output_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(destination), image)
    if not ok:
        raise ValueError(f"Could not write crop image: {destination}")
    return destination
