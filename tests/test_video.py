import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.video import read_frame_at, read_frames_at


class FakeCapture:
    def __init__(self, fps=10.0, frame_count=100, ok=False, frame=None):
        self.fps = fps
        self.frame_count = frame_count
        self.ok = ok
        self.frame = frame
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == FakeCV2.CAP_PROP_FPS:
            return self.fps
        if prop == FakeCV2.CAP_PROP_FRAME_COUNT:
            return self.frame_count
        return 0

    def set(self, prop, value):
        return True

    def read(self):
        return self.ok, self.frame

    def release(self):
        self.released = True


class FakeCV2:
    CAP_PROP_POS_MSEC = 0
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2

    def __init__(self, capture):
        self.capture = capture

    def VideoCapture(self, path):
        return self.capture


class VideoReadTests(unittest.TestCase):
    def test_read_frame_error_includes_duration_when_available(self):
        capture = FakeCapture(fps=10.0, frame_count=100)

        with patch("sidelinehd_extractor.video._cv2", return_value=FakeCV2(capture)):
            with self.assertRaisesRegex(
                ValueError,
                r"Could not read frame at 12\.000s from game\.mp4 \(duration: 10\.000s\)",
            ):
                read_frame_at(Path("game.mp4"), 12.0)

        self.assertTrue(capture.released)

    def test_read_frames_error_includes_duration_when_available(self):
        capture = FakeCapture(fps=20.0, frame_count=200)

        with patch("sidelinehd_extractor.video._cv2", return_value=FakeCV2(capture)):
            with self.assertRaisesRegex(
                ValueError,
                r"Could not read frame at 12\.500s from game\.mp4 \(duration: 10\.000s\)",
            ):
                list(read_frames_at(Path("game.mp4"), [12.5]))

        self.assertTrue(capture.released)


if __name__ == "__main__":
    unittest.main()
