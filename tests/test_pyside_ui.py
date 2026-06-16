from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYSIDE_DIR = ROOT / "pyside_ui"
WINDOWS_PLUGIN_DIR = ROOT / "\u6e05\u4f55\u9ed1\u5e27\u5939\u5e27\u68c0\u6d4b_v2.0.1-beta.14_Windows"
WINDOWS_LUA_ENTRY = WINDOWS_PLUGIN_DIR / "\u6e05\u4f55\u9ed1\u5e27\u5939\u5e27\u68c0\u6d4b.lua"

sys.path.insert(0, str(PYSIDE_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class PySideUiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.qt_app = QApplication.instance() or QApplication([])
        import app as pyside_app

        cls.pyside_app = pyside_app

    def test_version_matches_supplied_source(self) -> None:
        self.assertEqual(self.pyside_app.APP_VERSION, "2.0.1-beta.14")

    def test_pyside_resources_required_by_windows_package_exist(self) -> None:
        required = [
            PYSIDE_DIR / "app.py",
            PYSIDE_DIR / "resolve_bridge.py",
            PYSIDE_DIR / "icon.svg",
            PYSIDE_DIR / "icon.ico",
            PYSIDE_DIR / "donate",
            PYSIDE_DIR / "templates" / "caption-bin.drb",
            PYSIDE_DIR / "data" / "font_probe_rules.json",
            PYSIDE_DIR / "data" / "font_style_library.json",
        ]
        for path in required:
            self.assertTrue(path.exists(), f"missing required UI resource: {path}")

        self.assertGreater((PYSIDE_DIR / "icon.ico").stat().st_size, 10_000)
        self.assertTrue(any((PYSIDE_DIR / "donate").glob("*.jpg")), "donation QR jpg files must be bundled")

    def test_windows_plugin_tree_uses_supplied_v2_source(self) -> None:
        self.assertTrue(WINDOWS_LUA_ENTRY.exists())
        self.assertTrue((WINDOWS_PLUGIN_DIR / "black_frame_detector").is_dir())
        self.assertTrue((WINDOWS_PLUGIN_DIR / "modules").is_dir())

        entry_source = WINDOWS_LUA_ENTRY.read_text(encoding="utf-8")
        bridge_source = (WINDOWS_PLUGIN_DIR / "black_frame_detector" / "py_params_bridge.lua").read_text(encoding="utf-8")
        analyzer_source = (WINDOWS_PLUGIN_DIR / "black_frame_detector" / "black_frame_analyzer.lua").read_text(encoding="utf-8")

        self.assertIn("Recent PySide params found; skip launching UI and run detection", entry_source)
        self.assertIn('cmd.exe /C start "" "', entry_source)
        self.assertIn('lower_launcher:sub(-4) == ".vbs"', entry_source)
        self.assertIn('"pyside_ui" .. sep .. "QingheBFDControl"', entry_source)
        self.assertIn("PySide UI launcher inferred from module dir", entry_source)
        self.assertIn("tl_dur > stuck_frames and tl_dur > 0 and not clip.skip_stuck", entry_source)
        self.assertNotIn("tl_dur > stuck_frames and tl_dur > 0 and Analyzer.is_fully_opaque(clip, overlay_config)", entry_source)
        self.assertIn("detect_mixed_cut = false", bridge_source)
        self.assertIn("MARK_COMPOSITE_NONORMAL", (WINDOWS_PLUGIN_DIR / "black_frame_detector" / "config.lua").read_text(encoding="utf-8"))
        self.assertNotIn("clip.timeline_end_frame", analyzer_source)

    def test_resolve_bridge_points_at_windows_lua_entry(self) -> None:
        bridge_source = (PYSIDE_DIR / "resolve_bridge.py").read_text(encoding="utf-8")

        self.assertIn('REPO_ROOT / "\u6e05\u4f55\u9ed1\u5e27\u5939\u5e27\u68c0\u6d4b_v2.0.1-beta.14_Windows"', bridge_source)
        self.assertIn('"\u6e05\u4f55\u9ed1\u5e27\u5939\u5e27\u68c0\u6d4b.lua"', bridge_source)
        self.assertIn("def list_caption_templates", bridge_source)
        self.assertIn("def _estimate_bpm_with_ffmpeg", bridge_source)
        self.assertIn("caption-bin.drb", bridge_source)
        self.assertIn("qinghe_resolve_bridge_", bridge_source)
        self.assertIn("last_bridge_error.json", bridge_source)
        self.assertIn('root / "ffmpeg" / "windows" / "ffmpeg.exe"', bridge_source)
        self.assertIn('root / "ffmpeg" / "windows" / "ffprobe.exe"', bridge_source)
        self.assertIn('"black_frame_detector"', bridge_source)
        self.assertIn("if root == root.parent:", bridge_source)
        self.assertIn('platform.system().lower() == "windows"', bridge_source)
        self.assertIn("def find_bundled_python_runtime", bridge_source)
        self.assertIn('"python_runtime" / "python.exe"', bridge_source)
        self.assertIn('env["PYTHONHOME"] = str(python_home)', bridge_source)
        self.assertIn("[sys.executable, BRIDGE_WORKER_ARG]", bridge_source)

    def test_marker_refresh_bridge_builds_without_fstring_regression(self) -> None:
        from resolve_bridge import ResolveBridge

        bridge = ResolveBridge()
        bridge._run_resolve_python = lambda _body, timeout=5: {  # type: ignore[method-assign]
            "ok": True,
            "records": [],
            "counts": {"total": 0},
            "message": "ok",
        }

        result = bridge.bfd_marker_records(1)

        self.assertTrue(result["ok"])
        self.assertEqual(result["records"], [])

    def test_update_manifest_does_not_offer_macos_package_on_windows(self) -> None:
        app_source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn("def allowed_update_package_suffixes", app_source)
        self.assertIn("return {\".exe\", \".msi\", \".zip\"}", app_source)
        self.assertIn("def is_update_package_compatible", app_source)
        self.assertIn("if platforms and not platform_info:", app_source)
        self.assertIn("download_url = \"\"", app_source)

        original_update_platform_key = self.pyside_app.update_platform_key
        try:
            self.pyside_app.update_platform_key = lambda: "windows"
            info = self.pyside_app.update_info_from_manifest(
                {
                    "version": "9.9.9",
                    "download_url": "https://example.com/QingheBFD.dmg",
                    "package_type": "dmg",
                    "platforms": {
                        "mac": {
                            "version": "9.9.9",
                            "download_url": "https://example.com/QingheBFD.dmg",
                            "package_type": "dmg",
                        }
                    },
                }
            )
            self.assertEqual(info["platform"], "windows")
            self.assertEqual(info["latest_version"], "")
            self.assertEqual(info["download_url"], "")

            fallback_info = self.pyside_app.update_info_from_manifest(
                {
                    "version": "9.9.9",
                    "download_url": "https://example.com/QingheBFD.dmg",
                    "package_type": "dmg",
                }
            )
            self.assertEqual(fallback_info["latest_version"], "9.9.9")
            self.assertEqual(fallback_info["download_url"], "")

            win_info = self.pyside_app.update_info_from_manifest(
                {
                    "version": "9.9.9",
                    "download_url": "https://example.com/QingheBFD_v9.9.9_Windows_Setup.exe",
                    "package_type": "exe",
                }
            )
            self.assertTrue(win_info["download_url"].endswith("_Windows_Setup.exe"))
        finally:
            self.pyside_app.update_platform_key = original_update_platform_key

    def test_timeline_cache_no_longer_overrides_current_resolve_timeline(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")
        save_body = source[source.index("    def save_settings") : source.index("    def load_settings")]
        load_body = source[source.index("    def load_settings") : source.index("    def choose_complex_cache_dir")]

        self.assertNotIn('"timeline_index"', save_body)
        self.assertNotIn("self.timeline_combo.setCurrentIndex", load_body)
        self.assertIn("self.refresh_timelines()", source)
        self.assertIn("self._capture_current_timeline_uid()", source)
        self.assertIn("or (current_uid and tl.uid == current_uid)", source)

    def test_ui_keeps_required_v2_features(self) -> None:
        source = (PYSIDE_DIR / "app.py").read_text(encoding="utf-8")

        required_markers = [
            "DEFAULT_STUCK_FRAMES = 3",
            '"stuck_frames": self.stuck_frames.value()',
            '"min_black_frames": self.min_black_frames.value()',
            "def convert_srt_to_textplus",
            "self.caption_template_combo = QComboBox()",
            "def refresh_caption_templates",
            "def estimate_selected_audio_bpm",
            "def mark_selected_audio_beats",
            "def font_style_library_path",
            "def plugin_data_dir",
            'Path(__file__).resolve().parent / "data"',
            "font_style_library.json",
        ]
        for marker in required_markers:
            self.assertIn(marker, source)

    def test_build_script_bundles_runtime_assets_and_ffmpeg(self) -> None:
        source = (ROOT / "build_release_windows.ps1").read_text(encoding="utf-8")

        self.assertIn('$Version = "2.0.1-beta.14"', source)
        self.assertIn("black_frame_detector", source)
        self.assertIn('Join-Path $SourceFfmpeg "windows"', source)
        self.assertIn('Join-Path $Root "ffmpeg\\bin"', source)
        self.assertIn("ffprobe.exe", source)
        self.assertIn("--icon", source)
        self.assertIn("icon.ico", source)
        self.assertIn("donate", source)
        self.assertIn("templates", source)
        self.assertIn("data", source)
        self.assertIn('Copy-Item (Join-Path $Root "pyside_ui\\data") $StageUi -Recurse -Force', source)
        self.assertIn('Copy-Item (Join-Path $Root "pyside_ui\\templates") $StageUi -Recurse -Force', source)
        self.assertIn("test_resolve_api_bridge.ps1", source)
        self.assertIn("QingheBFDControl", source)
        self.assertIn("python_runtime", source)
        self.assertIn("Bundled Python runtime is missing python.exe", source)
        self.assertNotIn("private_docs", source)

    def test_installer_is_one_click_and_installs_icons_ui_and_ffmpeg(self) -> None:
        source = (ROOT / "install_windows.ps1").read_text(encoding="utf-8")

        self.assertIn("black_frame_detector", source)
        self.assertIn('ffmpeg\\windows', source)
        self.assertIn("ffprobe.exe", source)
        self.assertIn("Missing bundled Windows FFmpeg", source)
        self.assertIn("ui_launcher_path.txt", source)
        self.assertIn("QingheBFDControl.exe", source)
        self.assertIn("must not rely on system Python", source)
        self.assertIn("legacyDesktopShortcut", source)
        self.assertIn("cmd.exe /c del /f /q", source)
        self.assertIn("Move-Item -LiteralPath $TempLauncherPath", source)
        self.assertIn("Resolve Lua entry will infer the bundled UI path", source)
        self.assertNotIn("WScript.Shell", source)
        self.assertNotIn("pip install", source)
        self.assertNotIn("Get-Command py", source)
        self.assertNotIn("Get-Command python", source)
        self.assertNotIn(".cache\\codex-runtimes", source)
        self.assertNotIn("run_ui_hidden.vbs", source)
        self.assertNotIn("run_ui.bat", source)

    def test_windows_exe_installer_and_uninstaller_are_defined(self) -> None:
        build_source = (ROOT / "build_installer_windows.ps1").read_text(encoding="utf-8")
        iss_source = (ROOT / "installer_windows.iss").read_text(encoding="utf-8")
        uninstall_source = (ROOT / "uninstall_windows.ps1").read_text(encoding="utf-8")

        self.assertIn('$Version = "2.0.1-beta.14"', build_source)
        self.assertIn("ISCC.exe", build_source)
        self.assertIn("QingheBFD_v${Version}_Windows_Setup.exe", build_source)
        self.assertIn("LicenseFile=", iss_source)
        self.assertIn("installer_disclaimer.txt", iss_source)
        self.assertIn('#define MyAppName "Qinghe BFD"', iss_source)
        self.assertNotIn("娓", iss_source)
        self.assertNotIn("鍏", iss_source)
        self.assertIn("install_windows.ps1", iss_source)
        self.assertIn("uninstall_windows.ps1", iss_source)
        self.assertIn("UninstallRun", iss_source)
        self.assertIn("RunOnceId", iss_source)
        self.assertIn("ExistingUninstaller", iss_source)
        self.assertIn("MB_YESNOCANCEL", iss_source)
        self.assertIn("覆盖安装/更新到当前版本", iss_source)
        self.assertIn("先卸载旧版本", iss_source)
        self.assertIn("Exec(Uninstaller, '/SILENT'", iss_source)
        self.assertNotIn("Desktop", iss_source)
        self.assertIn("Remove-Item -LiteralPath $ModulesDir -Recurse -Force", uninstall_source)
        self.assertIn("Qinghe BFD Control.lnk", uninstall_source)

    def test_component_checker_covers_windows_release_requirements(self) -> None:
        source = (ROOT / "check_components.ps1").read_text(encoding="utf-8")
        smoke_source = (ROOT / "tools" / "test_resolve_api_bridge.ps1").read_text(encoding="utf-8")

        self.assertIn("Project FFmpeg", source)
        self.assertIn("Project FFprobe", source)
        self.assertIn("Packaged PySide UI", source)
        self.assertIn("Packaged Python Runtime", source)
        self.assertIn("ffmpeg\\windows\\ffmpeg.exe", source)
        self.assertIn("ffprobe.exe", source)
        self.assertIn("MutateTempMarker", smoke_source)
        self.assertIn("current_timeline_marks", smoke_source)
        self.assertIn("bfd_marker_records", smoke_source)
        self.assertIn("current_timeline_clip_snapshot", smoke_source)
        self.assertIn("scan_mono_audio", smoke_source)
        self.assertIn("probe_media_pool_api", smoke_source)
        self.assertIn("list_caption_templates", smoke_source)
        self.assertIn("scan_font_items", smoke_source)
        self.assertIn("check_font_available", smoke_source)
        self.assertIn("font_style_library.json", smoke_source)
        self.assertIn("estimate_selected_audio_bpm", smoke_source)
        self.assertIn("_find_ffmpeg_binary", smoke_source)
        self.assertIn("BFD_SMOKE_TEST_ONLY_DELETE_ME", smoke_source)

        release_verify = (ROOT / "tools" / "verify_windows_release.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-Isolated $BundledFfmpeg", release_verify)
        self.assertIn("Invoke-Isolated $BundledFfprobe", release_verify)
        self.assertIn("Invoke-Isolated $BundledPython", release_verify)
        self.assertIn("Invoke-Isolated $PackagedExe", release_verify)
        self.assertIn("Assert-NotContains $InstallScript", release_verify)

    def test_duplicate_detection_and_ffmpeg_runner_are_windows_ready(self) -> None:
        entry_source = WINDOWS_LUA_ENTRY.read_text(encoding="utf-8")
        duplicate_source = (WINDOWS_PLUGIN_DIR / "black_frame_detector" / "duplicate_detector.lua").read_text(encoding="utf-8")
        ffmpeg_sources = [
            (WINDOWS_PLUGIN_DIR / "black_frame_detector" / "ffmpeg_runner.lua").read_text(encoding="utf-8"),
            (WINDOWS_PLUGIN_DIR / "modules" / "ffmpeg_runner.lua").read_text(encoding="utf-8"),
        ]

        self.assertIn("pcall(function() left_offset = item:GetLeftOffset() end)", entry_source)
        self.assertIn("pcall(function() source_dur = item:GetDuration() end)", entry_source)
        self.assertIn("local function clip_timeline_duration", duplicate_source)
        self.assertIn("short_duplicate_side", duplicate_source)
        for ffmpeg_source in ffmpeg_sources:
            self.assertIn("raw_file_exists", ffmpeg_source)
            self.assertIn("Windows must prefer packaged FFmpeg", ffmpeg_source)
            self.assertIn('self.os ~= "macos" and self:_test_ffmpeg("ffmpeg")', ffmpeg_source)
            bundled_idx = ffmpeg_source.index("Windows must prefer packaged FFmpeg")
            path_idx = ffmpeg_source.index('self.os ~= "macos" and self:_test_ffmpeg("ffmpeg")')
            self.assertLess(bundled_idx, path_idx)


if __name__ == "__main__":
    unittest.main()
