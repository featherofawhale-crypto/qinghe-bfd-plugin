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

from PySide6.QtWidgets import QApplication, QCheckBox, QListWidget, QPushButton, QSlider, QTabWidget  # noqa: E402

import app as ui_app  # noqa: E402
import resolve_bridge  # noqa: E402
from app import MainWindow  # noqa: E402
from resolve_bridge import TimelineInfo, read_progress_file, write_lua_params  # noqa: E402


class PySideUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_threshold_controls_have_sliders_and_compact_ranges(self) -> None:
        window = MainWindow()
        sliders = window.findChildren(QSlider)

        self.assertGreaterEqual(len(sliders), 4)
        self.assertEqual(window.stuck_frames.maximum(), 100)
        self.assertEqual(window.suspect_frames.maximum(), 100)
        self.assertEqual(window.content_sample_interval.maximum(), 100)
        self.assertEqual(window.min_black_frames.maximum(), 100)
        self.assertEqual(window.progress.format(), "%p%")
        self.assertEqual(window.progress_label.text(), "待机")

    def test_threshold_defaults_can_be_restored_without_mode_combo(self) -> None:
        with patch.object(
            ui_app.ResolveBridge,
            "list_timelines",
            return_value=[
                TimelineInfo(1, "25fps 主时间线  (当前)", 25.0),
                TimelineInfo(2, "60fps 发布会", 60.0),
            ],
        ):
            window = MainWindow()

        self.assertFalse(hasattr(window, "severity"))

        window.stuck_frames.setValue(40)
        window.suspect_frames.setValue(70)
        window.min_black_frames.setValue(9)
        window.pixel_threshold.setValue(3.5)
        window.content_sample_interval.setValue(20)
        window.reset_threshold_defaults()
        self.assertEqual(window.stuck_frames.value(), 3)
        self.assertEqual(window.suspect_frames.value(), 12)
        self.assertEqual(window.min_black_frames.value(), 1)
        self.assertEqual(window.content_sample_interval.value(), 3)
        self.assertAlmostEqual(window.pixel_threshold.value(), 1.0)
        self.assertIn("25fps", window.stuck_frames.toolTip())

    def test_collect_params_includes_extended_detection_options(self) -> None:
        window = MainWindow()
        window.content_sample_interval.setValue(60)
        window.stuck_frames.setValue(80)
        window.min_black_frames.setValue(5)
        window.chk_scene.setChecked(True)
        window.chk_mark_hidden.setChecked(True)
        window.chk_png_opaque.setChecked(True)
        window.chk_partial_opacity.setChecked(False)
        window.chk_merge.setChecked(True)
        window.chk_complex.setChecked(False)
        params = window.collect_params()

        self.assertEqual(params["stuck_frames"], 80)
        self.assertEqual(params["content_sample_interval"], 60)
        self.assertEqual(params["min_black_frames"], 5)
        self.assertAlmostEqual(params["min_duration"], 5 / params["timeline_fps"], places=5)
        self.assertIn("detect_content_dup", params)
        self.assertIn("detect_corrupt", params)
        self.assertTrue(params["marker_types"]["scene"])
        self.assertTrue(params["mark_hidden_clips"])
        self.assertTrue(params["png_as_opaque"])
        self.assertFalse(params["mark_partial_opacity"])
        self.assertTrue(params["merge_mode"])
        self.assertFalse(params["complex_mode"])
        self.assertTrue(params["detect_mixed_cut"])
        self.assertTrue(params["marker_types"]["mixed_cut"])

    def test_collect_params_uses_selected_timeline_fps_for_thresholds(self) -> None:
        with patch.object(
            ui_app.ResolveBridge,
            "list_timelines",
            return_value=[
                TimelineInfo(1, "25fps 主时间线", 25.0),
                TimelineInfo(2, "60fps 发布会", 60.0),
            ],
        ):
            window = MainWindow()

        window.timeline_combo.setCurrentIndex(1)
        window.reset_threshold_defaults()

        params = window.collect_params()

        self.assertEqual(params["timeline_index"], 2)
        self.assertEqual(params["timeline_fps"], 60.0)
        self.assertEqual(params["stuck_frames"], 8)
        self.assertEqual(params["suspect_frames"], 29)
        self.assertEqual(params["min_black_frames"], 3)
        self.assertAlmostEqual(params["min_duration"], 3 / 60.0, places=5)

    def test_bad_frame_detection_requires_complex_mode(self) -> None:
        window = MainWindow()

        self.assertTrue(window.chk_corrupt.isEnabled())
        self.assertIn("复杂模式", window.chk_corrupt.toolTip())

        window.chk_complex.setChecked(True)
        window.on_complex_mode_changed(True)
        window.chk_corrupt.setChecked(True)
        params = window.collect_params()

        self.assertTrue(params["complex_mode"])
        self.assertTrue(params["detect_corrupt"])

        window.chk_complex.setChecked(False)
        window.on_complex_mode_changed(False)
        params = window.collect_params()

        self.assertFalse(window.chk_corrupt.isChecked())
        self.assertFalse(params["detect_corrupt"])

    def test_feedback_controls_and_tooltips_are_present(self) -> None:
        window = MainWindow()
        controls = [
            window.chk_error,
            window.chk_suspect,
            window.chk_scene,
            window.chk_gap,
            window.chk_duplicate,
            window.chk_content_dup,
            window.chk_opacity,
            window.chk_mixed_cut,
            window.chk_complex,
            window.chk_merge,
            window.feedback_btn,
            window.clear_markers_btn,
        ]

        self.assertEqual(window.feedback_btn.text(), "反馈")
        self.assertEqual(window.clear_markers_btn.text(), "清除标记")
        visible_text = " ".join(check.text() for check in window.findChildren(QCheckBox))
        visible_text += " ".join(button.text() for button in window.findChildren(QPushButton))
        self.assertNotIn("Lua", visible_text)
        self.assertNotIn("自动触发", visible_text)
        for control in controls:
            self.assertTrue(control.toolTip(), f"{control.text()} missing tooltip")

    def test_marker_options_are_neutral_and_buttons_have_motion_feedback(self) -> None:
        window = MainWindow()
        marker_checks = [
            window.chk_error,
            window.chk_suspect,
            window.chk_scene,
            window.chk_gap,
            window.chk_duplicate,
            window.chk_content_dup,
            window.chk_opacity,
            window.chk_mixed_cut,
            window.chk_corrupt,
        ]

        for check in marker_checks:
            self.assertNotIn("●", check.text())
            self.assertEqual(check.objectName(), "MarkerCheck")
            self.assertNotIn("#ff5b5b", check.styleSheet().lower())

        buttons = window.findChildren(QPushButton)
        self.assertTrue(buttons)
        for button in buttons:
            self.assertEqual(button.property("motion"), "press-fade")

    def test_default_window_is_compact_with_complementary_accent(self) -> None:
        window = MainWindow()

        self.assertLessEqual(window.size().width(), 980)
        self.assertLessEqual(window.size().height(), 680)
        self.assertEqual(window.progress_label.minimumWidth(), 138)
        self.assertEqual(window.result_list.minimumHeight(), 190)
        self.assertEqual(window.audio_list.minimumHeight(), 230)
        self.assertEqual(window.log.minimumHeight(), 300)
        self.assertIn("#f59e0b", ui_app.APP_STYLE.lower())
        self.assertIn("#2563eb", ui_app.APP_STYLE.lower())
        self.assertIn("qpushbutton#primary", ui_app.APP_STYLE.lower())

    def test_visible_ui_labels_are_readable_chinese(self) -> None:
        window = MainWindow()
        text = " ".join(check.text() for check in window.findChildren(QCheckBox))

        self.assertIn("夹帧", text)
        self.assertIn("坏帧", text)
        self.assertNotIn("娓", text)
        self.assertNotIn("榛", text)

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

    def test_packaged_release_can_find_lua_entry_next_to_installer_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "release" / "pyside_ui" / "QingheBFDControl" / "QingheBFDControl.exe"
            plugin = root / "release" / "QingheBFD_Plugin_Windows"
            exe.parent.mkdir(parents=True)
            plugin.mkdir(parents=True)
            lua = plugin / "清何黑帧夹帧检测.lua"
            lua.write_text("-- smoke", encoding="utf-8")

            had_frozen = hasattr(sys, "frozen")
            old_frozen = getattr(sys, "frozen", None)
            sys.frozen = True
            try:
                with patch.object(sys, "executable", str(exe)):
                    self.assertEqual(resolve_bridge.find_lua_entry(), lua)
            finally:
                if had_frozen:
                    sys.frozen = old_frozen
                else:
                    delattr(sys, "frozen")

    def test_resolve_menu_entry_launches_external_pyside_ui(self) -> None:
        lua_entry = ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "清何黑帧夹帧检测.lua"
        source = lua_entry.read_text(encoding="utf-8")
        self.assertIn("ui_launcher_path.txt", source)
        self.assertIn("BFD_PARAMS_FILE", source)
        self.assertIn("try_launch_external_ui", source)

        installer = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("ui_launcher_path.txt", installer)
        self.assertIn("UTF8Encoding $false", installer)
        self.assertIn("pyside_ui", installer)
        self.assertIn("InstalledUiDir", installer)
        self.assertIn("run_ui_hidden.vbs", installer)
        self.assertIn("wscript.exe //B", source)
        self.assertNotIn("cmd.exe /C start", source)

        hidden_launcher = (ROOT / "pyside_ui" / "run_ui_hidden.vbs").read_text(encoding="utf-8")
        self.assertIn("pyw.exe", hidden_launcher)
        self.assertNotIn("powershell", hidden_launcher.lower())
        self.assertNotIn("ExecutionPolicy", hidden_launcher)

    def test_settings_cache_roundtrip_restores_options_but_defaults_to_full_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "ui_settings.json"
            with patch.object(ui_app, "settings_path", return_value=settings_file, create=True):
                first = MainWindow()
                first.io_in.setText("01:00:01:00")
                first.io_out.setText("01:00:05:12")
                first.chk_scene.setChecked(True)
                first.chk_content_dup.setChecked(True)
                first.chk_mixed_cut.setChecked(False)
                first.content_sample_interval.setValue(24)
                first.min_black_frames.setValue(7)
                first.pixel_threshold.setValue(1.2)
                first.save_settings()

                second = MainWindow()
                second.load_settings()

        self.assertEqual(second.io_in.text(), "")
        self.assertEqual(second.io_out.text(), "")
        self.assertTrue(second.chk_scene.isChecked())
        self.assertTrue(second.chk_content_dup.isChecked())
        self.assertFalse(second.chk_mixed_cut.isChecked())
        self.assertEqual(second.content_sample_interval.value(), 24)
        self.assertEqual(second.min_black_frames.value(), 7)
        self.assertAlmostEqual(second.pixel_threshold.value(), 1.2, places=2)

    def test_legacy_pixel_threshold_cache_is_converted_to_percent_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "ui_settings.json"
            settings_file.write_text('{"pix_th": 0.01}', encoding="utf-8")
            with patch.object(ui_app, "settings_path", return_value=settings_file, create=True):
                legacy = MainWindow()
                legacy.load_settings()

            settings_file.write_text('{"pix_th": 1.0}', encoding="utf-8")
            with patch.object(ui_app, "settings_path", return_value=settings_file, create=True):
                percent = MainWindow()
                percent.load_settings()

        self.assertAlmostEqual(legacy.pixel_threshold.value(), 1.0, places=2)
        self.assertAlmostEqual(percent.pixel_threshold.value(), 1.0, places=2)

    def test_results_tab_is_visible_and_completion_switches_to_results(self) -> None:
        window = MainWindow()
        tabs = window.findChildren(QTabWidget)

        self.assertTrue(tabs)
        self.assertIs(window.side_tabs, tabs[0])
        self.assertIn("结果", [window.side_tabs.tabText(i) for i in range(window.side_tabs.count())])
        self.assertIn("音频", [window.side_tabs.tabText(i) for i in range(window.side_tabs.count())])

        window.side_tabs.setCurrentWidget(window.log_tab)
        with patch.object(
            ui_app,
            "read_progress_file",
            return_value={
                "percent": 100,
                "stage": "检测完成",
                "state": "complete",
                "counts": {"total": 2, "error": 1, "duplicate": 1},
                "records": [
                    {
                        "timecode": "01:00:01:00",
                        "classification": "error",
                        "name": "[BFD-ERR] 夹帧错误",
                        "color": "Red",
                    }
                ],
            },
        ):
            window.poll_detection_progress()

        self.assertIs(window.side_tabs.currentWidget(), window.results_tab)
        self.assertEqual(window.result_values["total"].text(), "2")
        self.assertIn("01:00:01:00", window.result_list.toPlainText())

    def test_result_records_are_sorted_by_timeline_time(self) -> None:
        window = MainWindow()
        window.render_result_records(
            [
                {"timecode": "01:00:10:00", "classification": "error", "name": "late"},
                {"timecode": "01:00:01:00", "classification": "error", "name": "early"},
                {"frame": 86450, "timecode": "01:00:02:02", "classification": "error", "name": "middle"},
            ]
        )

        lines = window.result_list.toPlainText().splitlines()
        self.assertIn("early", lines[0])
        self.assertIn("middle", lines[1])
        self.assertIn("late", lines[2])

    def test_result_records_filter_unjumpable_rows(self) -> None:
        window = MainWindow()
        window.render_result_records(
            [
                {"classification": "info", "name": "no marker"},
                {"timecode": "01:00:01:00", "classification": "error", "name": "[BFD-ERR] ok"},
                {"marker_frame": "", "classification": "gap", "name": "[BFD-GAP] empty"},
            ]
        )

        text = window.result_list.toPlainText()
        self.assertIn("[BFD-ERR] ok", text)
        self.assertNotIn("no marker", text)
        self.assertNotIn("[BFD-GAP] empty", text)
        self.assertEqual(len(window.result_records), 1)

    def test_frame_only_result_rows_are_jumpable(self) -> None:
        window = MainWindow()
        jumps = []
        window.bridge.jump_to_timecode = lambda timeline_index, timecode: jumps.append((timeline_index, timecode)) or (True, "ok")

        window.render_result_records([{"frame": 1500, "fps": 25, "classification": "error", "name": "[BFD-ERR] frame only"}])
        window.jump_to_result_row(0)

        self.assertIn("00:01:00:00", window.result_list.toPlainText())
        self.assertEqual(jumps, [(1, "00:01:00:00")])

    def test_zero_result_progress_shows_in_out_hint_once(self) -> None:
        window = MainWindow()

        with patch.object(
            ui_app,
            "read_progress_file",
            return_value={
                "percent": 100,
                "stage": "complete",
                "state": "complete",
                "counts": {"total": 0},
                "records": [],
            },
        ), patch.object(ui_app.QMessageBox, "information") as info:
            window.poll_detection_progress()
            window.poll_detection_progress()

        self.assertEqual(info.call_count, 1)
        self.assertIn("入出点", window.log.toPlainText())
        self.assertIn("入出点", window.result_list.toPlainText())

    def test_current_timeline_marks_fill_manual_in_out(self) -> None:
        window = MainWindow()
        window.bridge.current_timeline_marks = lambda timeline_index: {
            "ok": True,
            "in_tc": "01:00:00:00",
            "out_tc": "01:00:08:12",
            "message": "已读取当前时间线入出点。",
        }

        window.fill_in_out_from_current_timeline_marks()

        self.assertEqual(window.io_in.text(), "01:00:00:00")
        self.assertEqual(window.io_out.text(), "01:00:08:12")

    def test_audio_mono_is_audio_page_only_and_mixed_cut_is_main_option(self) -> None:
        window = MainWindow()
        buttons = {button.text(): button for button in window.findChildren(QPushButton)}
        check_text = " ".join(check.text() for check in window.findChildren(QCheckBox))

        self.assertIn("混剪夹帧", check_text)
        self.assertNotIn("单声道音频", check_text)
        self.assertIn("扫描单声道", buttons)
        self.assertIn("标记单声道", buttons)
        self.assertIn("修正声道映射", buttons)
        self.assertTrue(window.scan_audio_btn.toolTip())
        self.assertTrue(window.fix_audio_btn.toolTip())
        self.assertTrue(window.collect_params()["detect_mixed_cut"])
        self.assertNotIn("detect_mono_audio", window.collect_params())

    def test_audio_mapping_helper_identifies_mono_sources(self) -> None:
        mono_mapping = {
            "embedded_audio_channels": 1,
            "track_mapping": {"1": {"type": "mono", "channel_idx": [1]}},
        }
        stereo_mapping = {
            "embedded_audio_channels": 2,
            "track_mapping": {"1": {"type": "stereo", "channel_idx": [1, 2]}},
        }

        self.assertTrue(resolve_bridge.is_mono_audio_mapping(mono_mapping))
        self.assertFalse(resolve_bridge.is_mono_audio_mapping(stereo_mapping))
        self.assertEqual(resolve_bridge.frames_to_timecode(1500, 25), "00:01:00:00")

    def test_batch_timeline_selection_builds_multiple_detection_jobs(self) -> None:
        with patch.object(
            ui_app.ResolveBridge,
            "list_timelines",
            return_value=[
                TimelineInfo(1, "发布会 A  (当前)", 25.0),
                TimelineInfo(2, "纪录片 B", 50.0),
                TimelineInfo(3, "交付 C", 60.0),
            ],
        ):
            window = MainWindow()

        lists = window.findChildren(QListWidget)
        self.assertTrue(lists)
        self.assertEqual(window.batch_timeline_list.count(), 3)

        window.chk_batch_timelines.setChecked(True)
        window.timeline_combo.setCurrentIndex(0)
        window.reset_threshold_defaults()
        for index in range(window.batch_timeline_list.count()):
            item = window.batch_timeline_list.item(index)
            item.setCheckState(ui_app.Qt.Checked if index in {0, 2} else ui_app.Qt.Unchecked)

        jobs = window.collect_batch_params()

        self.assertEqual([job["timeline_index"] for job in jobs], [1, 3])
        self.assertEqual(jobs[0]["timeline_fps"], 25.0)
        self.assertEqual(jobs[1]["timeline_fps"], 60.0)
        self.assertEqual(jobs[0]["stuck_frames"], 3)
        self.assertEqual(jobs[1]["stuck_frames"], 8)
        self.assertEqual(jobs[1]["suspect_frames"], 29)
        self.assertEqual(jobs[1]["min_black_frames"], 3)
        self.assertIn("批量", window.chk_batch_timelines.toolTip())


if __name__ == "__main__":
    unittest.main()
