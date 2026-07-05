"""Coordinate regression tests for the packaged SidelineHD template (item 56).

Live-fire evidence (2026-07-05, three real 640x360 SidelineHD streams): the
``inning`` region previously started at x=0.424 while ``left_score`` extends
to x=0.425, so the inning crop clipped the score's right edge and produced
junk reads ("17", "71-") including wrong inning values. These tests pin the
recalibrated coordinates and the no-overlap invariant so a future template
edit cannot silently reintroduce the bleed.
"""

import json
import unittest
from pathlib import Path

from sidelinehd_extractor.config import builtin_overlay_template

EXAMPLE_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "sidelinehd_640x360_active.example.json"
)


class PackagedTemplateCoordinateTests(unittest.TestCase):
    def test_inning_region_matches_item_56_recalibration(self):
        region = builtin_overlay_template().regions["inning"]
        self.assertAlmostEqual(region.x, 0.428)
        self.assertAlmostEqual(region.y, 0.033)
        self.assertAlmostEqual(region.width, 0.040)
        self.assertAlmostEqual(region.height, 0.064)

    def test_inning_does_not_overlap_left_score(self):
        regions = builtin_overlay_template().regions
        left_score = regions["left_score"]
        inning = regions["inning"]
        self.assertGreaterEqual(
            inning.x,
            left_score.x + left_score.width,
            "inning region must start at or right of left_score's right edge "
            "(item 56: overlap produced junk inning reads on real streams)",
        )

    def test_example_template_regions_match_packaged_copy(self):
        packaged = builtin_overlay_template().regions
        example_data = json.loads(EXAMPLE_TEMPLATE.read_text(encoding="utf-8"))
        example_regions = example_data["regions"]
        self.assertEqual(set(example_regions), set(packaged))
        for name, region in packaged.items():
            for attribute in ("x", "y", "width", "height"):
                self.assertAlmostEqual(
                    example_regions[name][attribute],
                    getattr(region, attribute),
                    msg=f"{name}.{attribute} drifted between example and packaged copies",
                )


if __name__ == "__main__":
    unittest.main()
