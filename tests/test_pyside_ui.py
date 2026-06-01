from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pyside_ui"))

from PySide6.QtWidgets import QApplication, QSlider  # noqa: E402

import app as ui_app  # noqa: E402
import resolve_bridge  # noqa: E402
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

    def test_frozen_bridge_process_uses_worker_mode_not_dash_c(self) -> None:
        had_frozen = hasattr(sys, "frozen")
        old_frozen = getattr(sys, "frozen", None)
        sys.frozen = True
        try:
            with patch.object(sys, "executable", r"C:\app\QingheBFDControl.exe"):
                command, stdin_script = resolve_bridge.build_resolve_python_process("print('ok')")
        finally:
            if had_frozen:
                sys.frozen = old_frozen
            else:
                delattr(sys, "frozen")

        self.assertEqual(command, [r"C:\app\QingheBFDControl.exe", "--resolve-bridge"])
        self.assertIn("print('ok')", stdin_script)
        self.assertNotIn("-c", command)

    def test_bridge_worker_arg_runs_without_starting_gui(self) -> None:
        with patch.object(ui_app, "run_resolve_bridge_worker", return_value=23) as worker:
            self.assertEqual(ui_app.main(["QingheBFDControl.exe", "--resolve-bridge"]), 23)

        worker.assert_called_once()


if __name__ == "__main__":
    unittest.main()
