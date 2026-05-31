from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pyside_ui"))

from PySide6.QtWidgets import QApplication, QSlider  # noqa: E402

from app import MainWindow  # noqa: E402
from resolve_bridge import read_progress_file, write_lua_params  # noqa: E402


class PySideUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_threshold_controls_have_sliders_and_large_ranges(self) -> None:
        window = MainWindow()
        sliders = window.findChildren(QSlider)

        self.assertGreaterEqual(len(sliders), 4)
        self.assertGreaterEqual(window.stuck_frames.maximum(), 999)
        self.assertGreaterEqual(window.suspect_frames.maximum(), 999)
        self.assertGreaterEqual(window.content_sample_interval.maximum(), 999)
        self.assertGreaterEqual(window.min_duration.maximum(), 60.0)
        self.assertEqual(window.progress.format(), "%p%")
        self.assertEqual(window.progress_label.text(), "待机")

    def test_collect_params_includes_extended_detection_options(self) -> None:
        window = MainWindow()
        window.content_sample_interval.setValue(120)
        window.stuck_frames.setValue(123)
        params = window.collect_params()

        self.assertEqual(params["stuck_frames"], 123)
        self.assertEqual(params["content_sample_interval"], 120)
        self.assertIn("detect_content_dup", params)
        self.assertIn("detect_corrupt", params)

    def test_lua_param_writer_and_progress_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            params_path = Path(tmp) / "params.lua"
            progress_path = Path(tmp) / "progress.json"

            write_lua_params({"enabled": True, "stuck_frames": 123, "headless": True}, params_path)
            self.assertIn("stuck_frames = 123", params_path.read_text(encoding="utf-8"))
            self.assertIn("headless = true", params_path.read_text(encoding="utf-8"))

            progress_path.write_text(
                '{"percent": 64, "stage": "FFmpeg 3/5", "state": "running"}',
                encoding="utf-8",
            )
            progress = read_progress_file(progress_path)
            self.assertEqual(progress["percent"], 64)
            self.assertEqual(progress["stage"], "FFmpeg 3/5")


if __name__ == "__main__":
    unittest.main()
