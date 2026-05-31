# 清何黑帧检测 UI 优化和加密

当前 Windows 插件版本：`1.9.53`

## Windows 一键安装

双击 `install_windows.bat`，或在 PowerShell 中运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1
```

安装器会复制 Resolve 脚本、模块、内置 FFmpeg，安装 PySide6 依赖，生成核心 Lua 字节码，并创建 PySide6 控制台桌面快捷方式。

## PySide6 控制台

```powershell
.\pyside_ui\run_ui.bat
```

点击“开始检测”后，PySide6 会把参数写到 `~/.qinghe_bfd/last_params.lua`。随后在 Resolve 中运行原 Lua 脚本时，插件会优先读取这些参数并把进度写回 `~/.qinghe_bfd/progress.json`。
