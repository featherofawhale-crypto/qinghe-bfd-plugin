# macOS Release Notes

Version: 2.0.0-内测版

This package is built from the current Qinghe BFD source and the original macOS package's bundled `ffmpeg/macos` runtime.

## What The macOS Zip Contains

- `install_macos.command`: one-click macOS installer.
- `uninstall_macos.command`: uninstaller.
- `check_components_macos.sh`: local diagnostics.
- `QingheBFD_Plugin_macOS/清何黑帧夹帧检测.lua`: Resolve entry script.
- `QingheBFD_Plugin_macOS/modules`: latest Lua modules.
- `QingheBFD_Plugin_macOS/ffmpeg/macos`: bundled macOS FFmpeg and dylibs from the original DMG.
- `QingheBFD_Plugin_macOS/pyside_ui`: PySide UI source launcher for macOS.

## Install

On macOS, unzip the package, right-click `install_macos.command`, choose Open, and follow the terminal prompts.

The installer copies files to:

```text
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector
```

It also writes:

```text
ui_launcher_path.txt
```

pointing to the installed `pyside_ui/run_ui.sh`.

## Manual Install

Copy:

- `QingheBFD_Plugin_macOS/清何黑帧夹帧检测.lua` to `Fusion/Scripts/Edit/`.
- `QingheBFD_Plugin_macOS/modules/*.lua` to `Fusion/Scripts/Modules/black_frame_detector/`.
- `QingheBFD_Plugin_macOS/ffmpeg` to `Fusion/Scripts/Modules/black_frame_detector/ffmpeg`.
- `QingheBFD_Plugin_macOS/pyside_ui` to `Fusion/Scripts/Modules/black_frame_detector/pyside_ui`.

Then create `Fusion/Scripts/Modules/black_frame_detector/ui_launcher_path.txt` with the full path to `pyside_ui/run_ui.sh`.

## DMG Note

Windows 不能原生生成可签名的 macOS .app/.dmg. This repo can build a macOS-ready zip on Windows. To make a real DMG on a Mac, run:

```bash
hdiutil create -volname "Qinghe BFD v2.0.0-内测版" -srcfolder "QingheBFD_v1.9.104_macOS" -ov -format UDZO "QingheBFD_v2.0.0-beta_macOS.dmg"
```

If a signed `.app` is required, build it on macOS with PyInstaller or py2app, then sign/notarize it with an Apple Developer certificate before creating the DMG.
