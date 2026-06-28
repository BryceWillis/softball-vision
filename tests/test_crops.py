import unittest

from sidelinehd_extractor.crops import PixelRegion, fraction_to_pixel_region
from sidelinehd_extractor.models import RegionFraction


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


if __name__ == "__main__":
    unittest.main()
