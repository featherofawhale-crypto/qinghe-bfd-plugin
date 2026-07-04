# beta25 本地插件说明

- 版本：`2.0.1-beta.25`
- 本地插件目录：`dist/protected_release/QingheEditingToolbox_v2.0.1-beta.25_mac`
- 发布状态：已生成 beta25 macOS 完整安装 DMG，并更新 GitHub、CNB、官网与插件更新清单。

## 字体面板修复

- 字体列表只展示干净的字体 family，不再把中文别名、原始 PostScript 名、粗细样式拼成一行。
- 疑似 name table 解码错误的乱码别名会被过滤，不进入 UI 列表和别名 tooltip。
- macOS 中文字体会在字体列表首次显示前补充系统本地化名称，并以 `中文 / English` 形式展示，例如 `Baoli SC` 显示为 `报隶-简 / Baoli SC`，`BiauKaiHK` 显示为 `標楷體-港澳 / BiauKaiHK`。
- 中文/英文字体标签不再用 Qt writingSystems 兜底，避免 `BMW Type Global Pro`、`Brush Script MT` 这类英文字体被误标成 `[中]`。
- `Bold`、`Light`、`Medium`、`Heavy`、`Oblique` 等粗细/样式会归一到字体粗细下拉里。
- 目标字体输入框保持 family，实际应用到 Resolve/Fusion 时再与当前粗细下拉组合。

## 字体加载优化

- 打开字体面板时优先使用缓存；缓存命中后不再自动后台刷新，避免每次打开都重新加载半天。
- 缓存命中后只读取 `font_inventory_cache.json` 并刷新界面列表，不再重复执行字体归一化和 macOS 本地化字体名扫描。
- 没有缓存时才读取系统字体并生成一次缓存。
- 字体面板新增 `刷新字体库` 按钮；用户安装新字体后主动点击，插件会绕过缓存重新读取系统字体并更新缓存。
- 本机 beta25 已预生成字体缓存，运行目录和 PyInstaller `_internal/data` 中都包含 `font_inventory_cache.json`。

## 启动修复

- macOS beta25 正式包默认通过 `./QingheBFDControl/QingheBFDControl` 启动打包 GUI，用户机器不需要安装 Python/PySide6。
- 源码 GUI 只作为开发调试入口：设置 `QINGHE_PREFER_SOURCE_GUI=1` 且本机存在 PySide6 时才会使用 `python3 app.py`。
- 已用 `/usr/bin/python3 -m PyInstaller` 重打 `QingheBFDControl`，构建日志确认包含 `PySide6.QtCore`、`PySide6.QtGui`、`PySide6.QtWidgets`、`PySide6.QtNetwork`。
- 本机安装目录已验证启动日志为 `exec pyinstaller gui: ./QingheBFDControl/QingheBFDControl`。
- 打包 GUI 会跳过 PyObjC/AppKit 的前台探测路径，避免用户机器缺少 PyObjC 时点击后卡在启动或窗口显示前；窗口置前改用 Qt 临时置顶兜底。
- 新覆盖的 PyInstaller 可执行文件第一次运行可能有一次 macOS 冷启动验证，本机已通过 `--self-test` 预热；预热后正常 GUI 已验证到 `after show visible=True`。
- 启动补丁：`patches/beta25_launch_source_gui.patch`

## 字体失败数据收集

- `font_rule_failed` 事件会附带更多失败上下文，包括 source family/style、候选 family/style、已知别名、Qt family 识别情况、Resolve 返回字段和候选 trace。
- 本机字体路径仍只保留文件名，避免上传完整本地路径。

## 补丁记录

- 可追踪补丁：`patches/beta25_font_ui_analytics.patch`
- 版本/安装补丁：`patches/beta25_install_version_metadata.patch`

## 本机安装状态

- Resolve 用户插件目录已覆盖为 beta25：`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector`
- Resolve 菜单脚本已覆盖为 beta25：`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/清何黑帧夹帧检测.lua`
- 覆盖前备份目录：`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Modules/black_frame_detector_backup_before_beta25_20260704_154120`
- 字体库存缓存已预生成；下一次打开字体面板会直接使用缓存。安装新字体后请点 `刷新字体库` 主动重建缓存。
- 注意：界面版本号来自 PyInstaller 打包后的 `QingheBFDControl`，只改 `app.py` 不会让已安装插件自动显示 beta25；本次已重打并覆盖该可执行文件。
