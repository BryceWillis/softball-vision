import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.corrections import apply_event_corrections, load_event_corrections
from sidelinehd_extractor.models import Event, EventType, HalfInning


class CorrectionsTests(unittest.TestCase):
    def test_load_event_corrections_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrections.csv"
            path.write_text(
                "event_type,timestamp,field,value,match_window_seconds,reason\n"
                "at_bat_start,10:00,label,Maya R. (#22),1,clean label\n",
                encoding="utf-8",
            )

            corrections = load_event_corrections(path)

        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0].event_type, EventType.AT_BAT_START)
        self.assertEqual(corrections[0].timestamp_seconds, 600)
        self.assertEqual(corrections[0].field_name, "label")
        self.assertEqual(corrections[0].value, "Maya R. (#22)")
        self.assertEqual(corrections[0].match_window_seconds, 1)

    def test_apply_event_corrections_updates_fields(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Moya R. (#22)",
                player_number="22",
                player_name="Moya R.",
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrections.csv"
            path.write_text(
                "event_type,timestamp_seconds,field,value\n"
                "at_bat_start,600,label,Maya R. (#22)\n"
                "at_bat_start,600,player_name,Maya R.\n",
                encoding="utf-8",
            )

            corrected = apply_event_corrections(events, load_event_corrections(path))

        self.assertEqual(corrected[0].label, "Maya R. (#22)")
        self.assertEqual(corrected[0].player_name, "Maya R.")
        self.assertEqual(events[0].label, "Moya R. (#22)")

    def test_apply_event_corrections_deletes_event(self):
        events = [
            Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
            Event(EventType.AT_BAT_START, 605, "#22", player_number="22"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrections.csv"
            path.write_text(
                "event_type,timestamp_seconds,field,value\n"
                "at_bat_start,605,delete,true\n",
                encoding="utf-8",
            )

            corrected = apply_event_corrections(events, load_event_corrections(path))

        self.assertEqual(len(corrected), 1)
        self.assertEqual(corrected[0].event_type, EventType.HALF_INNING_START)


if __name__ == "__main__":
    unittest.main()
