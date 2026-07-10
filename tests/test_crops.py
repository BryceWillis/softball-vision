import unittest

import numpy as np

from sidelinehd_extractor.crops import (
    PixelRegion,
    fraction_to_pixel_region,
    normalize_frame_to_template,
)
from sidelinehd_extractor.models import OverlayTemplate, RegionFraction


class RegionConversionTests(unittest.TestCase):
    def test_fraction_to_pixel_region_converts_normalized_rect(self):
        region = RegionFraction(x=0.10, y=0.20, width=0.30, height=0.25)

        self.assertEqual(
            fraction_to_pixel_region(region, 1920, 1080),
            PixelRegion(x=192, y=216, width=576, height=270),
        )

    def test_fraction_to_pixel_region_keeps_tiny_regions_at_least_one_pixel(self):
        region = RegionFraction(x=0.0, y=0.0, width=0.0001, height=0.0001)

        self.assertEqual(
            fraction_to_pixel_region(region, 10, 10),
            PixelRegion(x=0, y=0, width=1, height=1),
        )

    def test_fraction_to_pixel_region_rejects_invalid_dimensions(self):
        region = RegionFraction(x=0.0, y=0.0, width=1.0, height=1.0)

        with self.assertRaises(ValueError):
            fraction_to_pixel_region(region, 0, 1080)


class NormalizeFrameToTemplateTests(unittest.TestCase):
    def _template(self, width=640, height=360):
        return OverlayTemplate(name="test", video_width=width, video_height=height)

    def test_matching_frame_passes_through_unchanged(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)

        result = normalize_frame_to_template(frame, self._template())

        self.assertIs(result, frame)

    def test_higher_resolution_frame_is_downscaled_to_template_dimensions(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        result = normalize_frame_to_template(frame, self._template())

        self.assertEqual(result.shape[:2], (360, 640))

    def test_lower_resolution_frame_is_upscaled_to_template_dimensions(self):
        frame = np.zeros((240, 426, 3), dtype=np.uint8)

        result = normalize_frame_to_template(frame, self._template())

        self.assertEqual(result.shape[:2], (360, 640))

    def test_template_without_dimensions_passes_frame_through(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        template = OverlayTemplate(name="test", video_width=None, video_height=None)

        result = normalize_frame_to_template(frame, template)

        self.assertIs(result, frame)

    def test_none_frame_passes_through(self):
        self.assertIsNone(normalize_frame_to_template(None, self._template()))

    def test_downscale_preserves_fractional_region_content(self):
        # A digit-like bright block at fractions (0.375, 0.033, 0.05, 0.064)
        # must land in the same fractional region after normalization.
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[24:70, 480:544] = 255  # left_score region at 720p

        result = normalize_frame_to_template(frame, self._template())

        region = RegionFraction(x=0.375, y=0.033, width=0.05, height=0.064)
        pixel = fraction_to_pixel_region(region, 640, 360)
        crop = result[pixel.y : pixel.y2, pixel.x : pixel.x2]
        self.assertGreater(crop.mean(), 200)


if __name__ == "__main__":
    unittest.main()
