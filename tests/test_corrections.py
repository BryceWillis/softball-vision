import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.corrections import (
    CORRECTION_CSV_COLUMNS,
    EventCorrection,
    apply_event_corrections,
    correction_key,
    load_event_corrections,
    remove_event_correction,
    upsert_event_correction,
    write_event_corrections,
)
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

    def test_apply_event_corrections_adds_event_and_sorts_by_timestamp(self):
        events = [
            Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
            Event(
                EventType.AT_BAT_START,
                700,
                "Maya R. (#22)",
                inning=1,
                half=HalfInning.TOP,
                player_number="22",
                player_name="Maya R.",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrections.csv"
            path.write_text(
                "event_type,timestamp,field,value,inning,half,player_number,player_name\n"
                "at_bat_start,10:30,add,,1,top,26,Amelia V.\n",
                encoding="utf-8",
            )

            corrected = apply_event_corrections(events, load_event_corrections(path))

        self.assertEqual(
            [(event.timestamp_seconds, event.label) for event in corrected],
            [
                (600, "Top 1"),
                (630, "Amelia V. (#26)"),
                (700, "Maya R. (#22)"),
            ],
        )
        self.assertEqual(corrected[1].player_number, "26")
        self.assertEqual(corrected[1].player_name, "Amelia V.")
        self.assertEqual(corrected[1].inning, 1)
        self.assertEqual(corrected[1].half, HalfInning.TOP)


class CorrectionsWriterTests(unittest.TestCase):
    def test_write_event_corrections_round_trips_through_loader(self):
        corrections = [
            EventCorrection(
                timestamp_seconds=605.0,
                field_name="player_number",
                value="28",
                event_type=EventType.AT_BAT_START,
                reason="Fix OCR misread",
            ),
            EventCorrection(
                timestamp_seconds=630.0,
                field_name="add",
                value="",
                event_type=EventType.AT_BAT_START,
                player_number="26",
                player_name="Amelia V.",
                inning=1,
                half=HalfInning.TOP,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrections.csv"
            write_event_corrections(path, corrections)

            header = path.read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(header, ",".join(CORRECTION_CSV_COLUMNS))
            reloaded = load_event_corrections(path)

        self.assertEqual(reloaded, corrections)

    def test_write_preserves_hand_written_rows_semantically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrections.csv"
            path.write_text(
                "event_type,timestamp,field,value,reason\n"
                "at_bat_start,10:05,label,Maya R. (#22),hand-written row\n",
                encoding="utf-8",
            )

            corrections = load_event_corrections(path)
            corrections = upsert_event_correction(
                corrections,
                EventCorrection(
                    timestamp_seconds=700.0,
                    field_name="delete",
                    value="",
                    event_type=EventType.AT_BAT_START,
                ),
            )
            write_event_corrections(path, corrections)
            reloaded = load_event_corrections(path)

        self.assertEqual(len(reloaded), 2)
        self.assertEqual(reloaded[0].timestamp_seconds, 605.0)
        self.assertEqual(reloaded[0].field_name, "label")
        self.assertEqual(reloaded[0].value, "Maya R. (#22)")
        self.assertEqual(reloaded[0].reason, "hand-written row")

    def test_upsert_replaces_by_key_and_remove_drops_by_key(self):
        first = EventCorrection(
            timestamp_seconds=605.0,
            field_name="player_number",
            value="28",
            event_type=EventType.AT_BAT_START,
        )
        second = EventCorrection(
            timestamp_seconds=605.0,
            field_name="player_number",
            value="26",
            event_type=EventType.AT_BAT_START,
        )
        other = EventCorrection(
            timestamp_seconds=605.0,
            field_name="label",
            value="Maya R. (#26)",
            event_type=EventType.AT_BAT_START,
        )

        corrections = upsert_event_correction([], first)
        corrections = upsert_event_correction(corrections, other)
        corrections = upsert_event_correction(corrections, second)

        self.assertEqual(corrections, [second, other])

        remaining = remove_event_correction(corrections, correction_key(second))
        self.assertEqual(remaining, [other])


if __name__ == "__main__":
    unittest.main()
