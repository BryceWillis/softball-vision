"""Shared metadata keys and values used across the extraction pipeline."""

BATTER_SOURCE_BATTER_CARD = "batter_card"
BATTER_SOURCE_LINEUP_NUMBER = "lineup_number"
BATTER_SOURCE_LINEUP_STRIP = "lineup_strip"

LINEUP_SOURCE_FULL_STRIP = "lineup_full_strip"
LINEUP_SOURCE_HIGHLIGHT = "lineup_highlight"
LINEUP_STRIP_CONFIDENCE_KEY = "lineup_strip_confidence"

# Pixel-detected direction of the SidelineHD inning arrow, carried on the
# inning OCR sample's source_detail. More reliable than the OCR text, where
# the arrow glyph fuses into the inning digit ("4"/"7" prefixes).
INNING_ARROW_UP = "inning_arrow_up"
INNING_ARROW_DOWN = "inning_arrow_down"

# Scores above this are treated as OCR noise, not values (item 60). Softball
# blowouts can reach the 20s; 50 leaves generous headroom while rejecting
# glyph-fusion artifacts like "164".
MAX_PLAUSIBLE_SCORE = 50
