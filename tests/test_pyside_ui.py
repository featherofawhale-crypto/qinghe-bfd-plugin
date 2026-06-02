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
from resolve_bridge import TimelineInfo, read_progress_file, read_timeline_state, write_lua_params  # noqa: E402


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
        self.assertLessEqual(window.audio_list.maximumHeight(), 260)
        self.assertTrue(window.audio_summary.wordWrap())
        self.assertEqual(window.log.minimumHeight(), 300)
        self.assertIn("#f59e0b", ui_app.APP_STYLE.lower())
        self.assertIn("#2563eb", ui_app.APP_STYLE.lower())
        self.assertIn("qpushbutton#primary", ui_app.APP_STYLE.lower())
        self.assertEqual(ui_app.WINDOWS_APP_ID, "Qinghe.BFD.Control")

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

    def test_timeline_state_cache_is_used_before_slow_resolve_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "current_timeline_state.json"
            state_path.write_text(
                '{"ok":true,"timelines":[{"index":1,"name":"方法  (当前)","fps":24,"uid":"abc"}]}',
                encoding="utf-8",
            )
            with patch.object(resolve_bridge, "timeline_state_path", return_value=state_path):
                bridge = resolve_bridge.ResolveBridge()
                with patch.object(bridge, "_run_resolve_python", return_value=None) as run_bridge:
                    timelines = bridge.list_timelines()

            self.assertEqual(timelines[0].name, "方法  (当前)")
            self.assertEqual(timelines[0].fps, 24.0)
            self.assertTrue(bridge.is_connected())
            self.assertFalse(run_bridge.called)

    def test_stale_timeline_state_is_used_when_resolve_bridge_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "current_timeline_state.json"
            state_path.write_text(
                '{"ok":true,"timelines":[{"index":1,"name":"方法  (当前)","fps":24,"uid":"abc"}]}',
                encoding="utf-8",
            )
            old_time = 1_700_000_000
            os.utime(state_path, (old_time, old_time))

            with patch.object(resolve_bridge, "timeline_state_path", return_value=state_path):
                bridge = resolve_bridge.ResolveBridge()
                with patch.object(bridge, "_run_resolve_python", return_value=None) as run_bridge:
                    timelines = bridge.list_timelines()

            self.assertEqual(timelines[0].name, "方法  (当前)")
            self.assertEqual(timelines[0].fps, 24.0)
            self.assertFalse(bridge.is_connected())
            self.assertFalse(run_bridge.called)

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
        self.assertIn("current_timeline_state.json", source)
        self.assertIn("write_timeline_state_snapshot", source)

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
                first.chk_complex.setChecked(True)
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
        self.assertFalse(second.chk_complex.isChecked())
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

    def test_mixed_timeline_risk_prompts_for_complex_without_auto_start(self) -> None:
        window = MainWindow()
        window.bridge.is_connected = lambda: True
        window.bridge.detect_complex_timeline_risk = lambda timeline_index: {
            "ok": True,
            "count": 1,
            "message": "发现 1 个疑似混剪/多镜头成片。",
            "candidates": [{"reason": "同一源文件多次引用", "name": "成片.mp4"}],
        }
        window.bridge.current_timeline_marks = lambda timeline_index: {
            "ok": True,
            "in_tc": "01:00:00:00",
            "out_tc": "01:00:41:00",
        }

        with patch.object(ui_app.QMessageBox, "question", return_value=ui_app.QMessageBox.Yes), patch.object(
            ui_app.SubmitWorker, "start"
        ) as worker_start:
            window.start_detection()

        self.assertTrue(window.chk_complex.isChecked())
        self.assertEqual(window.io_in.text(), "01:00:00:00")
        self.assertEqual(window.io_out.text(), "01:00:41:00")
        self.assertFalse(worker_start.called)

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

    def test_resolve_bridge_has_fast_complex_timeline_risk_scan(self) -> None:
        source = (ROOT / "pyside_ui" / "resolve_bridge.py").read_text(encoding="utf-8")

        self.assertIn("detect_complex_timeline_risk", source)
        self.assertIn("same_source", source)
        self.assertNotIn("file_scene", source)

    def test_audio_mono_is_audio_page_only_and_mixed_cut_is_main_option(self) -> None:
        window = MainWindow()
        buttons = {button.text(): button for button in window.findChildren(QPushButton)}
        check_text = " ".join(check.text() for check in window.findChildren(QCheckBox))

        self.assertNotIn("混剪夹帧", check_text)
        self.assertNotIn("单声道音频", check_text)
        self.assertIn("扫描单声道", buttons)
        self.assertIn("标记单声道", buttons)
        self.assertNotIn("修正声道映射", buttons)
        self.assertTrue(window.scan_audio_btn.toolTip())
        self.assertTrue(window.collect_params()["detect_mixed_cut"])
        self.assertNotIn("detect_mono_audio", window.collect_params())

    def test_mixed_cut_is_not_user_filtered_and_uses_source_fps(self) -> None:
        lua_entry = ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "清何黑帧夹帧检测.lua"
        source = lua_entry.read_text(encoding="utf-8")

        self.assertNotIn("marker_types.mixed_cut == false", source)
        self.assertIn("source_fps", source)
        self.assertIn("mixed_cut_single_scene_score", source)
        self.assertIn("0.55", source)
        self.assertIn("tl_cut - 1", source)
        self.assertIn("raw_rel", source)
        self.assertIn("candidates", source)
        self.assertIn("raw_rel - start_sec", source)
        self.assertNotIn("rel > scan_duration + 1", source)
        self.assertIn("rel_cut * timeline_fps", source)
        self.assertIn("rel_start * timeline_fps", source)
        self.assertIn("left_offset / source_fps", source)
        self.assertIn("dur_frames / source_fps", source)
        self.assertNotIn("rel_cut * source_to_timeline", source)
        self.assertIn("matched_visible", source)
        self.assertIn("single_fallback", source)
        self.assertIn("tl_cut >= clip_start and tl_cut <= clip_end", source)
        self.assertIn("ipairs(all_clips or ffmpeg_clips or {})", source)
        marker_manager = (ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "black_frame_detector" / "marker_manager.lua").read_text(encoding="utf-8")
        self.assertIn("marker_priority", marker_manager)
        self.assertIn("is_mixed_cut", marker_manager)

    def test_audio_marking_uses_chocolate_and_reports_track_format_fixing(self) -> None:
        source = (ROOT / "pyside_ui" / "resolve_bridge.py").read_text(encoding="utf-8")

        self.assertIn('AUDIO_MARK_COLOR = "Chocolate"', source)
        self.assertIn("first_mono_channel", source)
        self.assertIn("mono_channel_label", source)
        self.assertIn('"channel_idx": [channel, channel]', source)
        self.assertIn("track_format_fix_attempts", source)
        self.assertIn("try_set_track_stereo", source)
        self.assertIn("SetClipColor(clip_color)", source)
        self.assertIn("source_mapping", source)
        self.assertIn("media_mapping", source)
        self.assertNotIn("timeline.AddMarker", source)
        self.assertNotIn('SetClipColor("Orange")', source)

    def test_detection_launch_is_hidden_and_io_out_can_default_in_to_start(self) -> None:
        source = (ROOT / "pyside_ui" / "resolve_bridge.py").read_text(encoding="utf-8")
        app_source = (ROOT / "pyside_ui" / "app.py").read_text(encoding="utf-8")

        self.assertIn("hidden_subprocess_kwargs", source)
        self.assertIn("CREATE_NO_WINDOW", source)
        self.assertIn("subprocess.Popen", source)
        self.assertIn("stdout=subprocess.DEVNULL", source)
        self.assertIn("if in_frame is None and out_frame is not None:", source)
        self.assertIn("in_frame = start_frame", source)
        self.assertIn("跳过启动前混剪风险扫描", app_source)

    def test_complex_mode_cache_dir_and_leading_gap_are_wired(self) -> None:
        app_source = (ROOT / "pyside_ui" / "app.py").read_text(encoding="utf-8")
        lua_source = (
            ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "清何黑帧夹帧检测.lua"
        ).read_text(encoding="utf-8")
        analyzer_source = (
            ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "black_frame_detector" / "black_frame_analyzer.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("complex_cache_dir", app_source)
        self.assertIn("QFileDialog.getExistingDirectory", app_source)
        self.assertIn("params.complex_cache_dir", lua_source)
        self.assertIn("VideoQuality", lua_source)
        self.assertIn("os.remove(params.complex_render_path)", lua_source)
        self.assertIn("timeline_start_frame", analyzer_source)
        self.assertIn("coverage_table[1].start_frame > first_frame", analyzer_source)
        self.assertIn("Analyzer.compute_gap_ranges(coverage_table, timeline_fps, params.start_offset)", analyzer_source)

    def test_watermark_is_written_to_markers_reports_and_logs(self) -> None:
        module_root = ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "black_frame_detector"
        config_source = (module_root / "config.lua").read_text(encoding="utf-8")
        marker_source = (module_root / "marker_manager.lua").read_text(encoding="utf-8")
        version_source = (module_root / "version_compat.lua").read_text(encoding="utf-8")
        report_source = (module_root / "report_generator.lua").read_text(encoding="utf-8")
        lua_source = (
            ROOT / "清何黑帧夹帧检测_v1.9.48_Windows" / "清何黑帧夹帧检测.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("config.WATERMARK", config_source)
        self.assertIn("QH-BFD", config_source)
        self.assertIn("config.build_watermark_payload", config_source)
        self.assertIn("build_watermark_payload", marker_source)
        self.assertIn("safe_add_marker(", marker_source)
        self.assertIn("custom_data", version_source)
        self.assertIn("AddMarker(frame, color, name, note, duration or 1, custom_data", version_source)
        self.assertIn("watermark", report_source)
        self.assertIn("get_watermark_label", report_source)
        self.assertIn("Watermark: ", lua_source)

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
