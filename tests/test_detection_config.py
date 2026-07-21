"""Contract tests for the M4 pipeline config objects (M4 / CR-47).

Slice 22a introduced ``DetectionConfig``; 22b finished the job with
``ExportOptions`` accepted at the run boundary plus ``SamplingOptions`` and
``DownloadOptions``. The milestone's done-when is structural: adding a
pipeline knob is a one-line edit to one dataclass, and the batch path provably
cannot drift from the single-game path because neither declares a knob of its
own. These tests are that proof, and are meant to stay green forever — a
failure here means the fan-out is growing back, not that a test needs relaxing.
"""

import inspect
import unittest

from sidelinehd_extractor.batch import run_playlist_batch
from sidelinehd_extractor.events import DetectionConfig, detect_events, detect_events_file
from sidelinehd_extractor.models import HalfInning
from sidelinehd_extractor.processing import SamplingOptions, process_video
from sidelinehd_extractor.workflow import ExportOptions, run_game, run_youtube_game
from sidelinehd_extractor.youtube import (
    DEFAULT_FORMAT_SELECTOR,
    DEFAULT_YOUTUBE_CLIENT,
    DownloadOptions,
    download_youtube_video,
)

#: The five hops the detection knobs used to fan across. ``detect_events``
#: names its parameter ``config`` (it is the only config it takes); the run
#: entry points name theirs ``detection`` because 22b puts the export,
#: sampling, and download bundles beside it.
_THREADED_FUNCTIONS = (
    (detect_events, "config"),
    (detect_events_file, "config"),
    (run_game, "detection"),
    (run_youtube_game, "detection"),
    (run_playlist_batch, "detection"),
)

#: Every config bundle, its parameter name, and the hops that must thread it.
#: The two ``DetectionConfig`` rows differ only in parameter name.
_THREADED_CONFIGS = (
    (DetectionConfig, "config", (detect_events, detect_events_file)),
    (DetectionConfig, "detection", (run_game, run_youtube_game, run_playlist_batch)),
    (ExportOptions, "export_options", (run_game, run_youtube_game, run_playlist_batch)),
    (
        SamplingOptions,
        "sampling",
        (run_game, run_youtube_game, run_playlist_batch, process_video),
    ),
    (
        DownloadOptions,
        "download_options",
        (run_youtube_game, run_playlist_batch, download_youtube_video),
    ),
)

#: Every function a bundle passes through, swept against *all* bundle fields:
#: no hop may re-declare any of them, whichever layer it belongs to.
_SWEPT_FUNCTIONS = (
    detect_events,
    detect_events_file,
    process_video,
    download_youtube_video,
    run_game,
    run_youtube_game,
    run_playlist_batch,
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
        for function in _SWEPT_FUNCTIONS:
            with self.subTest(function=function.__name__):
                kinds = [
                    parameter.kind
                    for parameter in inspect.signature(function).parameters.values()
                ]
                self.assertNotIn(inspect.Parameter.VAR_KEYWORD, kinds)


class ConfigBundleFanOutTests(unittest.TestCase):
    """22b: the same proof, for all four bundles at once."""

    def test_no_hop_redeclares_any_bundled_knob(self):
        field_names = set()
        for config_class, _parameter, _functions in _THREADED_CONFIGS:
            field_names |= set(config_class.__dataclass_fields__)

        for function in _SWEPT_FUNCTIONS:
            with self.subTest(function=function.__name__):
                parameters = set(inspect.signature(function).parameters)
                self.assertEqual(
                    parameters & field_names,
                    set(),
                    f"{function.__name__} re-declares a config field as a loose parameter "
                    "— two sources of truth for the same knob (CR-47)",
                )

    def test_every_hop_threads_its_bundles_defaulting_to_the_dataclass(self):
        for config_class, parameter_name, functions in _THREADED_CONFIGS:
            for function in functions:
                with self.subTest(function=function.__name__, config=config_class.__name__):
                    parameters = inspect.signature(function).parameters
                    self.assertIn(parameter_name, parameters)
                    self.assertEqual(parameters[parameter_name].default, config_class())


class SamplingOptionsTests(unittest.TestCase):
    def test_defaults_are_the_run_path_values(self):
        # ``save_crops`` is False because that is what a *run* does; the
        # ``process`` audit command still turns crops on explicitly.
        sampling = SamplingOptions()

        self.assertEqual(sampling.sample_every_seconds, 5.0)
        self.assertEqual(sampling.start_seconds, 0.0)
        self.assertIsNone(sampling.end_seconds)
        self.assertIsNone(sampling.fields)
        self.assertFalse(sampling.save_crops)
        self.assertFalse(sampling.compute_video_hash)
        self.assertIsNone(sampling.ocr_workers)

    def test_is_frozen(self):
        with self.assertRaises(Exception):
            SamplingOptions().sample_every_seconds = 1.0  # type: ignore[misc]

    def test_fields_are_stored_as_a_tuple(self):
        # A caller-owned list could be mutated behind the config's back, and a
        # generator would be consumed once and read as empty the second time —
        # exactly the silent-divergence class this milestone removes.
        from_list = SamplingOptions(fields=["inning", "count"])
        from_generator = SamplingOptions(fields=(name for name in ("inning", "count")))

        self.assertEqual(from_list.fields, ("inning", "count"))
        self.assertEqual(from_generator.fields, ("inning", "count"))
        self.assertEqual(from_list, from_generator)

    def test_impossible_values_are_rejected(self):
        for kwargs, message in (
            ({"sample_every_seconds": 0}, "sample_every_seconds must be > 0"),
            ({"sample_every_seconds": -1}, "sample_every_seconds must be > 0"),
            ({"start_seconds": -1}, "start_seconds must be >= 0"),
            ({"start_seconds": 10, "end_seconds": 10}, "end_seconds must be > start_seconds"),
            ({"start_seconds": 10, "end_seconds": 5}, "end_seconds must be > start_seconds"),
            ({"ocr_workers": 0}, "ocr_workers must be >= 1"),
        ):
            with self.subTest(**kwargs):
                with self.assertRaises(ValueError) as raised:
                    SamplingOptions(**kwargs)
                self.assertEqual(str(raised.exception), message)

    def test_a_window_within_the_video_is_allowed(self):
        sampling = SamplingOptions(start_seconds=10.0, end_seconds=20.0)

        self.assertEqual((sampling.start_seconds, sampling.end_seconds), (10.0, 20.0))


class DownloadOptionsTests(unittest.TestCase):
    def test_defaults_match_the_shipped_yt_dlp_settings(self):
        options = DownloadOptions()

        self.assertEqual(options.format_selector, DEFAULT_FORMAT_SELECTOR)
        self.assertEqual(options.merge_output_format, "mp4")
        self.assertTrue(options.write_info_json)
        # Single video, not a playlist: the batch path walks playlists itself.
        self.assertTrue(options.no_playlist)
        self.assertEqual(options.youtube_client, DEFAULT_YOUTUBE_CLIENT)

    def test_is_frozen(self):
        with self.assertRaises(Exception):
            DownloadOptions().no_playlist = False  # type: ignore[misc]


class ExportOptionsTests(unittest.TestCase):
    def test_defaults_are_pinned(self):
        options = ExportOptions()

        self.assertTrue(options.include_chapter_intro)
        self.assertEqual(options.chapter_intro_label, "Pregame")
        self.assertTrue(options.include_inning_score)
        self.assertTrue(options.include_at_bat_inning_headers)


if __name__ == "__main__":
    unittest.main()
