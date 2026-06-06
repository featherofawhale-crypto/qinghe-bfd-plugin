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

    def test_version_is_test_build(self) -> None:
        self.assertEqual(self.pyside_app.APP_VERSION, "2.0.01-测试版")

    def test_threshold_defaults_stay_frame_based(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertEqual(self.pyside_app.DEFAULT_STUCK_FRAMES, 3)
        self.assertIn('"stuck_frames": self.stuck_frames.value()', source)
        self.assertIn('"min_black_frames": self.min_black_frames.value()', source)
        self.assertIn("self.stuck_frames.setValue(DEFAULT_STUCK_FRAMES)", source)
        self.assertIn("切换时间线不自动改阈值", source)
        self.assertNotIn("def _rescale_threshold_controls", source)
        self.assertNotIn('("stuck_frames", self.stuck_frames)', source)

    def test_save_settings_defines_complex_mode_before_content_duplicate_gate(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn("def save_settings(self) -> None:\n        complex_mode = self.chk_complex.isChecked()", source)
        self.assertIn('"content_dup": complex_mode and self.chk_content_dup.isChecked()', source)

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

    def test_timeline_row_keeps_refresh_and_io_visible(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.timeline_combo.setMaximumWidth(520)", source)
        self.assertIn("self.timeline_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)", source)
        self.assertIn("timeline_grid.addWidget(self.read_marks_btn", source)
        self.assertIn("timeline_grid.setColumnStretch(1, 3)", source)
        self.assertIn("timeline_grid.setColumnMinimumWidth(5, 86)", source)

    def test_text_tab_auto_enters_compact_mode_without_header_small_window_button(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("文字小窗")', source)
        self.assertIn('QPushButton("完整面板")', source)
        self.assertIn("def restore_full_panel", source)
        self.assertIn("widget is self.text_tab and not self._text_compact_mode", source)
        self.assertIn("QTimer.singleShot(0, lambda: self.set_text_compact_mode(True))", source)

    def test_audio_fx_cards_are_tutorial_only(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn('QGroupBox("音频效果教程")', source)
        self.assertIn('QPushButton("复制教程参数")', source)
        self.assertIn("def copy_audio_tutorial", source)
        self.assertIn("教程参数参考，不会自动写入工程，也不是一键音频效果", source)
        self.assertIn("请在达芬奇 Fairlight 里手动添加效果器", source)
        self.assertNotIn('QPushButton("应用预设")', source)
        self.assertNotIn("def apply_audio_preset", source)

    def test_clear_marker_button_targets_resolve_current_timeline(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        bridge_source = (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8")

        self.assertIn("def clear_current_bfd_markers", bridge_source)
        self.assertIn("project.GetCurrentTimeline()", bridge_source)
        self.assertIn("timeout=120", bridge_source)
        self.assertIn("resolve is not None", bridge_source)
        self.assertIn("self.bridge.clear_current_bfd_markers()", app_source)
        self.assertNotIn("self.bridge.clear_bfd_markers(int(selected.get", app_source)

    def test_timeline_group_has_full_timeline_button(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton("全时间线")', source)
        self.assertIn('QPushButton("入出点")', source)
        self.assertIn("timeline_grid.addWidget(refresh", source)
        self.assertIn("timeline_grid.addWidget(self.read_marks_btn", source)
        self.assertIn("timeline_grid.addWidget(self.full_timeline_btn", source)
        self.assertIn("self.io_in.setMaximumWidth(190)", source)
        self.assertIn("slider.setMaximumWidth(180)", source)
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
        compat_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "version_compat.lua").read_text(encoding="utf-8")

        self.assertIn('"detect_mixed_cut": False', app_source)
        self.assertIn('"mixed_cut": False', app_source)
        self.assertIn("params.enable_timeline_mixed_cut == true and params.detect_mixed_cut == true", lua_source)
        self.assertIn("detect_mixed_cut = false", bridge_source)
        self.assertIn("def prompt_complex_mode_for_risky_timelines", app_source)
        self.assertIn("def clear_stale_progress_file", app_source)
        self.assertIn("risky_tokens = (", app_source)
        self.assertIn("self.bridge.detect_complex_timeline_risk", app_source)
        self.assertNotIn("same_source", (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8"))
        self.assertNotIn("同一源文件在时间线出现", (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8"))
        self.assertLess(compat_source.index("bmd.scriptapp('Resolve')"), compat_source.index("global Resolve()"))
        self.assertIn("Skipping global Resolve() on macOS/Linux", compat_source)

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
        self.assertIn('name_marks_current = "当前" in tl.name', source)
        self.assertIn("or (current_uid and tl.uid == current_uid)", source)
        self.assertIn("has_current_timeline = any(", source)
        self.assertIn("and not has_current_timeline", source)

    def test_font_panel_removes_batch_replace_button_and_text_table_allows_edit_undo(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("self.font_apply_all_btn", source)
        self.assertIn("QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed", source)
        self.assertIn("self.push_text_undo", source)
        self.assertIn("self.text_undo_stack = self.text_undo_stack[-10:]", source)
        self.assertIn("def make_text_undo_change", source)
        self.assertIn("self.make_text_undo_change(item, source_text, new_text, record_index=index)", source)

    def test_font_style_library_and_16x9_preview_exist(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn("def font_style_library_path", source)
        self.assertIn("def plugin_data_dir", source)
        self.assertIn('Path(__file__).resolve().parent / "data"', source)
        self.assertIn("def legacy_font_style_library_path", source)
        self.assertIn("font_style_library.json", source)
        self.assertEqual(
            self.pyside_app.font_style_library_path(),
            self.pyside_app.plugin_data_dir() / "font_style_library.json",
        )
        self.assertNotEqual(
            self.pyside_app.font_style_library_path(),
            self.pyside_app.legacy_font_style_library_path(),
        )
        self.assertIn("self.font_style_library_list = QListWidget()", source)
        self.assertIn('QPushButton("保存样式")', source)
        self.assertIn('QPushButton("载入样式")', source)
        self.assertIn('QPushButton("删除样式")', source)
        self.assertIn("self.font_style_preview_image", source)
        self.assertIn("self.font_style_preview_image.setMaximumHeight(88)", source)
        self.assertIn("main_split = QSplitter(Qt.Horizontal)", source)
        self.assertIn('QLabel("时间线文字层")', source)
        self.assertIn('QLabel("本地 Text+ 样式库")', source)
        self.assertIn('QLabel("SRT 转 Text+")', source)
        self.assertIn("height * 16 / 9", source)
        self.assertIn("def save_copied_textplus_style_to_library", source)
        self.assertIn("self.font_style_clipboard = dict(library_item.get", source)

    def test_content_fingerprint_and_timeline_gap_detection_are_conservative(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        resolve_bridge_source = (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8")
        bridge_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "py_params_bridge.lua").read_text(encoding="utf-8")
        analyzer_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "black_frame_analyzer.lua").read_text(encoding="utf-8")
        entry_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "清何黑帧夹帧检测.lua").read_text(encoding="utf-8")
        config_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "config.lua").read_text(encoding="utf-8")

        self.assertIn('"detect_content_dup": complex_mode and self.chk_content_dup.isChecked()', app_source)
        self.assertIn("detect_content_dup = raw.complex_mode == true and raw.detect_content_dup == true", bridge_source)
        self.assertNotIn("clip.timeline_end_frame", analyzer_source)
        self.assertNotIn("display_tc_to_timeline_frame", entry_source)
        self.assertIn("def current_timeline_clip_snapshot", resolve_bridge_source)
        submit_body = resolve_bridge_source[
            resolve_bridge_source.index("    def submit_params") : resolve_bridge_source.index("    def current_timeline_clip_snapshot")
        ]
        self.assertNotIn("clip_snapshot_file", submit_body)
        self.assertIn("clip_snapshot_file = raw.clip_snapshot_file or", bridge_source)
        self.assertNotIn("使用PySide片段快照", entry_source)
        self.assertIn('"submitted_at"', resolve_bridge_source)
        self.assertIn("click menu item \"清何黑帧夹帧检测\"", resolve_bridge_source)
        self.assertIn("age <= 120", bridge_source)
        self.assertIn("Recent PySide params found; skip launching UI and run detection", entry_source)
        self.assertIn("disable_pending_params", bridge_source)
        self.assertIn("MARK_COMPOSITE_NONORMAL = true", config_source)
        self.assertIn("opacity_config.MARK_COMPOSITE_NONORMAL == true", entry_source)
        self.assertIn("tonumber(clip.composite_mode) ~= nil", entry_source)

    def test_duplicate_detection_requires_reliable_source_ranges(self) -> None:
        entry_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "清何黑帧夹帧检测.lua").read_text(encoding="utf-8")
        duplicate_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "duplicate_detector.lua").read_text(encoding="utf-8")
        ffmpeg_source = (ROOT / "QingheBFD_v1.9.104_macOS" / "QingheBFD_Plugin_macOS" / "modules" / "ffmpeg_runner.lua").read_text(encoding="utf-8")

        self.assertIn("pcall(function() left_offset = item:GetLeftOffset() end)", entry_source)
        self.assertIn("pcall(function() source_dur = item:GetDuration() end)", entry_source)
        self.assertNotIn("source_range_reliable = left_offset_ok and source_dur > 0", entry_source)

        self.assertNotIn("local function source_range_reliable", duplicate_source)
        self.assertNotIn("source_overlap_frames", duplicate_source)
        self.assertIn("local lo_a = clip_a.left_offset or 0", duplicate_source)
        self.assertIn("local overlap_frames = overlap_end - overlap_start", duplicate_source)
        self.assertIn("local d = c.source_duration_frames or 0", duplicate_source)
        self.assertIn("local function clip_timeline_duration", duplicate_source)
        self.assertIn("short_duplicate_side = dur_a <= dur_b and \"a\" or \"b\"", duplicate_source)
        self.assertIn("重复短切片", duplicate_source)
        self.assertIn("if duration <= 0 then", duplicate_source)
        self.assertIn('self.os ~= "macos" and self:_test_ffmpeg("ffmpeg")', ffmpeg_source)
        self.assertIn('self.os == "macos" and self:_test_ffmpeg("ffmpeg")', ffmpeg_source)
        self.assertIn("raw_file_exists", ffmpeg_source)

    def test_srt_to_textplus_uses_drb_template_and_audio_mark_marks_clips_only(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        bridge_source = (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8")
        template_path = PYSIDE_DIR / "templates" / "caption-bin.drb"

        self.assertTrue(template_path.exists())
        self.assertIn('QPushButton("SRT转Text+")', app_source)
        self.assertIn("def convert_srt_to_textplus", app_source)
        self.assertIn("self.chk_analytics.setChecked(True)", app_source)
        self.assertIn("caption-bin.drb", bridge_source)
        self.assertIn("def list_caption_templates", bridge_source)
        self.assertIn('"list_caption_templates"', bridge_source)
        self.assertIn("caption_template_uid", bridge_source)
        self.assertIn("find_caption_template_by_uid", bridge_source)
        self.assertIn("list_caption_template_items", bridge_source)
        self.assertIn("ImportFolderFromFile(CAPTION_TEMPLATE_PATH)", bridge_source)
        self.assertIn("使用媒体池模板：", bridge_source)
        self.assertIn("AppendToTimeline(payload)", bridge_source)
        self.assertIn('"convert_srt_textplus"', bridge_source)
        self.assertIn("tool.GetInputList()", bridge_source)
        self.assertIn("should_skip_textplus_style_key", bridge_source)
        self.assertIn("self.caption_template_combo = QComboBox()", app_source)
        self.assertIn('QPushButton("刷新模板")', app_source)
        self.assertIn("def refresh_caption_templates", app_source)
        self.assertIn("template_uid = str(self.caption_template_combo.currentData()", app_source)
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
        self.assertIn("current_timeline = project.GetCurrentTimeline()", bridge_source)
        self.assertIn("timeline = current_timeline or indexed_timeline", bridge_source)
        self.assertIn("timeline_audio_mapping_supported = resolve_major > 19", bridge_source)
        self.assertIn("resolve_major == 19 and (resolve_minor > 0 or resolve_patch >= 1)", bridge_source)
        self.assertIn("resolve_version_label", bridge_source)
        self.assertIn("Resolve {{resolve_version_label}} 不支持读取时间线单个音频片段的声道映射", bridge_source)
        self.assertIn("Resolve 19.0.1 起才有相关 API", bridge_source)
        self.assertIn("已尝试读取当前 Resolve 的轨道、片段和素材声道字段", bridge_source)
        self.assertIn("未写入任何标记", bridge_source)
        self.assertNotIn('"[BFD-AUDIO] 音频待复核"', bridge_source)
        self.assertNotIn("timeline.AddMarker(start_frame", bridge_source)
        self.assertNotIn("fallback_current_markers", bridge_source)
        self.assertNotIn("当前待复核", app_source)
        self.assertIn("def read_properties", bridge_source)
        self.assertIn("def properties_say_mono", bridge_source)
        self.assertIn("item_props_is_mono", bridge_source)
        self.assertIn("片段/素材属性里的 mono/1.0/单声道", app_source)


if __name__ == "__main__":
    unittest.main()
