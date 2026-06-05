from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYSIDE_DIR = ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "pyside_ui"
sys.path.insert(0, str(PYSIDE_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class PySideUiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.qt_app = QApplication.instance() or QApplication([])
        import app as pyside_app

        cls.pyside_app = pyside_app

    def test_version_is_internal_beta(self) -> None:
        self.assertEqual(self.pyside_app.APP_VERSION, "2.0.0-内测版")

    def test_donation_dialog_accepts_jpg_qr_files_and_says_so(self) -> None:
        dialog = self.pyside_app.DonationDialog()
        labels = dialog.findChildren(self.pyside_app.QLabel)
        visible_copy = "\n".join(label.text() for label in labels)

        self.assertIn("捐赠完全自愿", visible_copy)
        self.assertIn("使用前请自行做好项目备份", visible_copy)
        self.assertNotIn("二维码文件命名", visible_copy)
        self.assertNotIn("donate/wechat_1.jpg", visible_copy)

        for amount in self.pyside_app.DONATION_AMOUNTS:
            dialog.set_amount(amount)
            self.assertFalse(dialog.wechat_qr.qr_label.pixmap().isNull())
            self.assertFalse(dialog.alipay_qr.qr_label.pixmap().isNull())

    def test_disclaimer_keeps_no_warranty_and_backup_language(self) -> None:
        text = self.pyside_app.DISCLAIMER_TEXT
        self.assertIn("按“现状”提供", text)
        self.assertIn("做好项目备份", text)
        self.assertIn("检测结果仅作辅助参考", text)
        self.assertIn("捐赠为自愿支持开发", text)

    def test_localized_chinese_font_names_resolve_to_system_families_first(self) -> None:
        window = self.pyside_app.MainWindow.__new__(self.pyside_app.MainWindow)
        window.font_aliases = {}
        window.font_family_styles = {}
        window.available_fonts = []
        self.pyside_app.MainWindow.load_available_fonts(window)

        self.assertEqual(window.font_system_family("兰亭黑-简"), "Lantinghei SC")
        self.assertEqual(window.font_system_family("华文楷体"), "STKaiti")

        lanting_candidates = window.font_candidates("兰亭黑-简 Extralight")
        self.assertGreater(len(lanting_candidates), 0)
        self.assertEqual(lanting_candidates[0], "Lantinghei SC|||Extralight")
        self.assertNotIn("兰亭黑-简|||Extralight", lanting_candidates)

        stkaiti_candidates = window.font_candidates("华文楷体 Regular")
        self.assertGreater(len(stkaiti_candidates), 0)
        self.assertEqual(stkaiti_candidates[0], "STKaiti|||Regular")

    def test_postscript_font_names_map_back_to_textplus_family_and_style(self) -> None:
        window = self.pyside_app.MainWindow.__new__(self.pyside_app.MainWindow)
        window.font_aliases = {}
        window.font_family_styles = {}
        window.available_fonts = []
        self.pyside_app.MainWindow.load_available_fonts(window)

        candidates = window.font_candidates("FZYOUHS_506L--GB1-0")
        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0], "FZYouHeiS|||506L")
        self.assertEqual(window.split_font_style("FZYOUHS_506L--GB1-0"), ("FZYouHeiS", "506L"))
        self.assertNotIn("FZYOUHS_506L--GB1-0", candidates)

    def test_plugin_repo_ignores_local_analytics_backend(self) -> None:
        ignore_path = ROOT / ".gitignore"
        self.assertTrue(ignore_path.exists(), ".gitignore should keep local-only artifacts out of the plugin repo")
        ignored = ignore_path.read_text(encoding="utf-8")
        self.assertIn("analytics_backend/", ignored)

    def test_audio_tab_hides_unsupported_fix_and_fx_probe_buttons(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("修正声道映射")', source)
        self.assertNotIn('QPushButton("探测FX接口")', source)

    def test_clear_marker_button_targets_resolve_current_timeline(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        bridge_source = (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8")

        self.assertIn("def clear_current_bfd_markers", bridge_source)
        self.assertIn("project.GetCurrentTimeline()", bridge_source)
        self.assertIn("timeout=120", bridge_source)
        self.assertIn("self.bridge.clear_current_bfd_markers()", app_source)
        self.assertNotIn("self.bridge.clear_bfd_markers(int(selected.get", app_source)

    def test_timeline_group_has_full_timeline_button(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton("全时间线")', source)
        self.assertIn("layout.addWidget(self.read_marks_btn, 1, 4)", source)
        self.assertIn("layout.addWidget(self.full_timeline_btn, 2, 1)", source)
        self.assertIn("def use_full_timeline_range", source)
        self.assertIn("self.io_in.clear()", source)
        self.assertIn("self.io_out.clear()", source)

    def test_font_status_wording_is_layer_writable_not_font_guarantee(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn('"Text+可写"', source)
        self.assertNotIn('status = "可替换"', source)

    def test_timeline_mixed_cut_deep_scan_stays_disabled_by_default(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        lua_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "清何黑帧夹帧检测.lua").read_text(encoding="utf-8")
        bridge_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "py_params_bridge.lua").read_text(encoding="utf-8")

        self.assertIn('"detect_mixed_cut": False', app_source)
        self.assertIn('"mixed_cut": False', app_source)
        self.assertIn("params.enable_timeline_mixed_cut == true and params.detect_mixed_cut == true", lua_source)
        self.assertIn("detect_mixed_cut = false", bridge_source)
        self.assertIn("def prompt_complex_mode_for_risky_timelines", app_source)
        self.assertIn("def clear_stale_progress_file", app_source)
        self.assertIn("risky_tokens = (", app_source)
        self.assertNotIn("self.bridge.detect_complex_timeline_risk", app_source)

    def test_theme_modes_and_startup_foreground_activation_exist(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn("EYE_CARE_STYLE", source)
        self.assertIn("DARK_STYLE", source)
        self.assertIn('"护眼"', source)
        self.assertIn('"黑夜"', source)
        self.assertIn("def bring_window_to_front", source)
        self.assertIn("makeKeyAndOrderFront_", source)
        self.assertIn("activateIgnoringOtherApps_", source)
        self.assertIn("QTimer.singleShot(250, lambda: bring_window_to_front(window))", source)
        self.assertIn("def stat_card_style", source)
        self.assertIn("self.refresh_result_card_styles()", source)

    def test_existing_instance_is_raised_and_current_timeline_wins_over_cache(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn('socket.write(b"raise")', source)
        self.assertIn("def bind_window", source)
        self.assertIn("instance_guard.bind_window(window)", source)
        self.assertIn("not self.bridge.is_connected()", source)
        self.assertIn("self.refresh_timelines()\n        self._capture_current_timeline_uid()", source)

    def test_font_panel_removes_batch_replace_button_and_text_table_allows_edit_undo(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("self.font_apply_all_btn", source)
        self.assertIn("QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed", source)
        self.assertIn("self.push_text_undo", source)
        self.assertIn("self.text_undo_stack = self.text_undo_stack[-10:]", source)
        self.assertIn("def make_text_undo_change", source)
        self.assertIn("self.make_text_undo_change(item, source_text, new_text, record_index=index)", source)

    def test_content_fingerprint_and_timeline_gap_detection_are_conservative(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        bridge_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "py_params_bridge.lua").read_text(encoding="utf-8")
        analyzer_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "black_frame_analyzer.lua").read_text(encoding="utf-8")
        entry_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "清何黑帧夹帧检测.lua").read_text(encoding="utf-8")

        self.assertIn('"detect_content_dup": complex_mode and self.chk_content_dup.isChecked()', app_source)
        self.assertIn("detect_content_dup = raw.complex_mode == true and raw.detect_content_dup == true", bridge_source)
        self.assertIn("clip.timeline_end_frame", analyzer_source)
        self.assertIn("duration_frames <= 0 and clip.item", analyzer_source)
        self.assertIn("display_tc_to_timeline_frame", entry_source)
        self.assertIn("timeline_start_display_frame", entry_source)

    def test_duplicate_detection_requires_reliable_source_ranges(self) -> None:
        entry_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "清何黑帧夹帧检测.lua").read_text(encoding="utf-8")
        duplicate_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "duplicate_detector.lua").read_text(encoding="utf-8")

        self.assertIn("left_offset_ok = true", entry_source)
        self.assertIn("source_range_reliable = left_offset_ok and source_dur > 0", entry_source)
        self.assertIn("timeline_end_frame = end_frame", entry_source)

        self.assertIn("local function source_range_reliable", duplicate_source)
        self.assertIn("local overlap_frames = source_overlap_frames(clip_a, clip_b)", duplicate_source)
        self.assertIn("overlap_frames == nil or overlap_frames <= 0", duplicate_source)
        self.assertIn('match_type == "same_name_duration"', duplicate_source)
        self.assertIn("path_a and path_b and path_a == path_b", duplicate_source)
        self.assertIn("local d = clip_timeline_duration(c)", duplicate_source)
        self.assertIn("local end_a = clip_timeline_end(dup.clip_a)", duplicate_source)

    def test_srt_to_textplus_uses_drb_template_and_audio_mark_marks_clips_only(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        bridge_source = (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8")
        template_path = PYSIDE_DIR / "templates" / "caption-bin.drb"

        self.assertTrue(template_path.exists())
        self.assertIn('QPushButton("SRT转Text+")', app_source)
        self.assertIn("def convert_srt_to_textplus", app_source)
        self.assertIn("self.chk_analytics.setChecked(True)", app_source)
        self.assertIn("caption-bin.drb", bridge_source)
        self.assertIn("ImportFolderFromFile(CAPTION_TEMPLATE_PATH)", bridge_source)
        self.assertIn("AppendToTimeline(payload)", bridge_source)
        self.assertIn('"convert_srt_textplus"', bridge_source)
        self.assertIn("tool.GetInputList()", bridge_source)
        self.assertIn("should_skip_textplus_style_key", bridge_source)
        self.assertIn('"CharacterSpacing"', bridge_source)
        self.assertIn('"LineSpacing"', bridge_source)
        self.assertIn('"Red1"', bridge_source)
        self.assertIn('"LayoutType"', bridge_source)
        self.assertIn('return normalized in ("styledtext", "text", "name", "clipname", "comments")', bridge_source)
        self.assertIn("item.SetClipColor(clip_color)", bridge_source)
        self.assertIn("prefer_clip_color = resolve_major == 0 or resolve_major >= 20", bridge_source)
        self.assertIn('name = "[BFD-AUDIO] 单声道音频"', bridge_source)
        self.assertIn("item.AddMarker(0, AUDIO_CLIP_MARKER_COLOR", bridge_source)
        self.assertIn('"clip_markers_added": clip_markers_added', bridge_source)
        self.assertNotIn("timeline.AddMarker", bridge_source)


if __name__ == "__main__":
    unittest.main()
