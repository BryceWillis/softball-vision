"""Contract tests for ``DetectionConfig`` (M4 / CR-47).

The milestone's done-when is structural: adding a detection knob is a one-line
edit to one dataclass, and the batch path provably cannot drift from the
single-game path because neither declares a knob of its own. These tests are
that proof, and are meant to stay green forever — a failure here means the
fan-out is growing back, not that a test needs relaxing.
"""

import inspect
import unittest

from sidelinehd_extractor.batch import run_playlist_batch
from sidelinehd_extractor.events import DetectionConfig, detect_events, detect_events_file
from sidelinehd_extractor.models import HalfInning
from sidelinehd_extractor.workflow import run_game, run_youtube_game

#: The five hops the knobs used to fan across. ``detect_events`` names its
#: parameter ``config`` (it is the only config it takes); the run entry points
#: name theirs ``detection`` because 22b adds export/download/sampling beside it.
_THREADED_FUNCTIONS = (
    (detect_events, "config"),
    (detect_events_file, "config"),
    (run_game, "detection"),
    (run_youtube_game, "detection"),
    (run_playlist_batch, "detection"),
)


class DetectionConfigDefaultsTests(unittest.TestCase):
    def test_defaults_are_the_measured_tuning_values(self):
        # These constants are measured against real game footage, not
        # arbitrary. A refactor that nudges one must fail here, not in a game.
        config = DetectionConfig()

        self.assertIsNone(config.batting_half)
        self.assertFalse(config.auto_detect_batting_half)
        self.assertEqual(config.min_at_bat_spacing_seconds, 45.0)
        self.assertEqual(config.min_at_bat_spacing_roster_confirmed_seconds, 20.0)
        self.assertEqual(config.batter_confirmation_window, 4)
        self.assertEqual(config.min_batter_observations, 2)
        self.assertEqual(config.half_inning_confirmation_window, 12)
        self.assertEqual(config.min_half_inning_observations, 4)
        self.assertEqual(config.min_game_final_observations, 3)
        self.assertTrue(config.order_validation)

    def test_config_is_frozen(self):
        # The shared ``DetectionConfig()`` default instance is evaluated once
        # at import and handed to every caller; mutability would leak a knob
        # change from one run into the next.
        config = DetectionConfig()

        with self.assertRaises(Exception):
            config.min_at_bat_spacing_seconds = 10.0  # type: ignore[misc]

    def test_negative_tuning_values_are_rejected(self):
        # A negative spacing today silently disables the gate. Rejecting an
        # impossible config at construction is the fix.
        for name in (
            "min_at_bat_spacing_seconds",
            "min_at_bat_spacing_roster_confirmed_seconds",
            "batter_confirmation_window",
            "min_batter_observations",
            "half_inning_confirmation_window",
            "min_half_inning_observations",
            "min_game_final_observations",
        ):
            with self.subTest(field=name):
                with self.assertRaises(ValueError) as raised:
                    DetectionConfig(**{name: -1})
                self.assertIn(name, str(raised.exception))

    def test_zero_tuning_values_are_allowed(self):
        # Zero disables a gate deliberately; only negatives are impossible.
        self.assertEqual(DetectionConfig(min_at_bat_spacing_seconds=0).min_at_bat_spacing_seconds, 0)
        self.assertEqual(
            DetectionConfig(min_game_final_observations=0).min_game_final_observations, 0
        )


class DetectionConfigHandshakeTests(unittest.TestCase):
    """The two-phase auto-detect handshake, named so it cannot be mis-inlined."""

    def test_initial_batting_half_is_unfiltered_while_auto_detecting(self):
        auto = DetectionConfig(auto_detect_batting_half=True, batting_half=HalfInning.TOP)

        # Inference compares roster-name match counts across both halves, so
        # the first pass must not have filtered one of them away.
        self.assertIsNone(auto.initial_batting_half())

    def test_initial_batting_half_honors_an_explicit_half(self):
        explicit = DetectionConfig(batting_half=HalfInning.BOTTOM)

        self.assertEqual(explicit.initial_batting_half(), HalfInning.BOTTOM)
        self.assertIsNone(DetectionConfig().initial_batting_half())

    def test_initial_order_validation_is_deferred_while_auto_detecting(self):
        # Validation re-runs after inference has filtered to the inferred
        # half; running it on the unfiltered pass would flag the other team.
        self.assertFalse(
            DetectionConfig(auto_detect_batting_half=True).initial_order_validation()
        )
        self.assertTrue(DetectionConfig().initial_order_validation())
        self.assertFalse(DetectionConfig(order_validation=False).initial_order_validation())
        self.assertFalse(
            DetectionConfig(
                auto_detect_batting_half=True, order_validation=False
            ).initial_order_validation()
        )


class DetectionConfigManifestTests(unittest.TestCase):
    def test_existing_manifest_keys_keep_their_names_and_formats(self):
        section = DetectionConfig().to_manifest()

        self.assertEqual(section["min_at_bat_spacing_seconds"], 45.0)
        self.assertEqual(section["min_at_bat_spacing_roster_confirmed_seconds"], 20.0)
        self.assertEqual(section["min_game_final_observations"], 3)
        self.assertEqual(section["batting_half"], "both")
        self.assertTrue(section["order_validation_requested"])
        # Runtime information, merged in by run_game — not configuration.
        self.assertNotIn("order_validation_ran", section)

    def test_batting_half_renders_auto_top_bottom_and_both(self):
        # test_feedback.py round-trips ``detection.batting_half == "auto"``.
        self.assertEqual(
            DetectionConfig(auto_detect_batting_half=True).to_manifest()["batting_half"], "auto"
        )
        self.assertEqual(
            DetectionConfig(batting_half=HalfInning.TOP).to_manifest()["batting_half"], "top"
        )
        self.assertEqual(
            DetectionConfig(batting_half=HalfInning.BOTTOM).to_manifest()["batting_half"], "bottom"
        )
        self.assertEqual(DetectionConfig().to_manifest()["batting_half"], "both")
        # An explicit half is reported as "auto" while inferring, because the
        # inference is what actually decides the half for the run.
        self.assertEqual(
            DetectionConfig(
                auto_detect_batting_half=True, batting_half=HalfInning.TOP
            ).to_manifest()["batting_half"],
            "auto",
        )

    def test_window_knobs_are_surfaced_additively(self):
        section = DetectionConfig().to_manifest()

        self.assertEqual(section["batter_confirmation_window"], 4)
        self.assertEqual(section["min_batter_observations"], 2)
        self.assertEqual(section["half_inning_confirmation_window"], 12)
        self.assertEqual(section["min_half_inning_observations"], 4)


class DetectionFanOutTests(unittest.TestCase):
    """The fan-out cannot come back."""

    def test_no_hop_redeclares_a_detection_knob(self):
        field_names = set(DetectionConfig.__dataclass_fields__)

        for function, _parameter in _THREADED_FUNCTIONS:
            with self.subTest(function=function.__name__):
                parameters = set(inspect.signature(function).parameters)
                self.assertEqual(
                    parameters & field_names,
                    set(),
                    f"{function.__name__} re-declares a DetectionConfig field as a loose "
                    "parameter — two sources of truth for the same knob (CR-47)",
                )

    def test_every_hop_threads_one_config_defaulting_to_the_dataclass(self):
        for function, parameter_name in _THREADED_FUNCTIONS:
            with self.subTest(function=function.__name__):
                parameters = inspect.signature(function).parameters
                self.assertIn(parameter_name, parameters)
                self.assertEqual(parameters[parameter_name].default, DetectionConfig())

    def test_no_hop_accepts_kwargs_passthrough(self):
        # A ``**kwargs`` hop would let a stale knob keep flowing silently,
        # which is the failure mode this milestone removes.
        for function, _parameter in _THREADED_FUNCTIONS:
            with self.subTest(function=function.__name__):
                kinds = [
                    parameter.kind
                    for parameter in inspect.signature(function).parameters.values()
                ]
                self.assertNotIn(inspect.Parameter.VAR_KEYWORD, kinds)


if __name__ == "__main__":
    unittest.main()
