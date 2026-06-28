import unittest

from sidelinehd_extractor.calibration import (
    default_calibration_timestamps,
    parse_timestamp_list,
    parse_timestamp_value,
)


class CalibrationTests(unittest.TestCase):
    def test_parse_timestamp_value_accepts_seconds_minutes_and_hours(self):
        self.assertEqual(parse_timestamp_value("90"), 90)
        self.assertEqual(parse_timestamp_value("1:30"), 90)
        self.assertEqual(parse_timestamp_value("1:02:03"), 3723)

    def test_parse_timestamp_list_accepts_repeated_and_comma_values(self):
        self.assertEqual(parse_timestamp_list(["30,1:00", "0:45"]), [30.0, 45.0, 60.0])

    def test_default_calibration_timestamps_stay_inside_video(self):
        self.assertEqual(default_calibration_timestamps(60), [15.0, 30.0, 45.0, 59])

    def test_parse_timestamp_value_rejects_empty_value(self):
        with self.assertRaises(ValueError):
            parse_timestamp_value("")


if __name__ == "__main__":
    unittest.main()
