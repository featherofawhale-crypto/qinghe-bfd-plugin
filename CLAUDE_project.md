# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Address the user as `清何大大` and keep replies concise.

## 项目概述

达芬奇黑帧夹帧检测插件 — DaVinci Resolve Lua 脚本 + PySide6 控制面板，自动检测视频时间线上的黑帧/夹帧/转场/空位/重复片段/透明度异常/渲染坏帧/混剪夹帧/音频通道异常/字幕文字，打彩色标记辅助定位修复。

## Product Boundary

本项目发布 Windows / macOS DaVinci Resolve 脚本，包含：
- **Lua 插件**：`清何黑帧夹帧检测.lua` + `modules/` — 核心检测引擎
- **PySide6 控制面板**：`pyside_ui/` — 独立 UI，通过 resolve_bridge 与达芬奇通信
- **文档**：`docs/` — 公开开发和打包说明，随发布包分发
- **私有文档**：`private_docs/` — 仅限开发者的验收用例，**绝不**打包进公开发布包
- **测试**：`tests/` — Python 回归测试

## Rules Before Editing

- **禁止硬编码时间线帧率**：始终使用达芬奇当前时间线的 FPS
- **保留时间线起始时间码和 IO 点**：检测、打标记、跳转、渲染、文字列表等操作都必须尊重 IO 范围
- **IO 点适用范围**：视频检测、复杂模式、音频检测、文字导航均需遵守 IO 范围，除非某个功能明确声明忽略
- **复杂模式**：必须将标记/结果数据返回给 UI，并在运行结束后清理临时缓存文件
- **混剪夹帧检测**：必须捕获未切割混剪素材内部的一帧插入和复合类型片段，不能只检测手动切割的时间线片段
- **音频通道检查**：禁止将真立体声误标为单声道。如果达芬奇 API 无法安全修改通道映射，需记录具体的 API 限制并保持 UI 诚实
- **文字工具**：优先扫描 SRT/字幕轨道，然后才是达芬奇文本图层/Text+。搜索高亮匹配词不筛选掉行

## Required Version Bump

修改发布代码或文档时，同步更新以下文件中的版本号：

- `pyside_ui/app.py` — `APP_VERSION`
- `build_release_windows.ps1` — 版本引用
- `modules/config.lua` — `PLUGIN_VERSION`
- `black_frame_detector.lua` — 头部版本注释
- 公开文档中提及版本的 `.md` 文件

当前版本：`1.9.104`

## Packaging

从仓库根目录构建 Windows 发布包：

```powershell
.\build_release_windows.ps1
```

zip 包必须包含：
- `install_windows.bat` / `install_windows.ps1`
- `check_components.ps1`
- `QingheBFD_Plugin_Windows`
- `pyside_ui/QingheBFDControl/QingheBFDControl.exe`
- 捆绑的 PyInstaller Python 运行时
- 捆绑的 FFmpeg 二进制文件
- `black_frame_detector/bytecode_manifest.json`

**禁止**将 `private_docs/` 打包进公开 zip。

## Verification

声明构建就绪前必须通过：

```powershell
py -3 -m compileall pyside_ui
py -3 -m unittest tests.test_pyside_ui
.\install_windows.ps1
.\build_release_windows.ps1
```

对于达芬奇面对的功能，尽可能在实际达芬奇项目中验证。仅通过本地测试不足以证明插件能正确打开、读取时间线、放置标记。

## 命令

```bash
# 语法检查
lua -e "local ok,err = loadfile('black_frame_detector.lua'); print(ok and 'OK' or err)"

# 同步到安装目录（macOS）
MOD_DIR=~/Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Modules/black_frame_detector
cp modules/*.lua "$MOD_DIR/"
cp black_frame_detector.lua ~/Library/Application\ Support/Blackmagic\ Design/DaVinci\ Resolve/Fusion/Scripts/Edit/清何黑帧夹帧检测.lua

# 查看调试日志
tail -50 ~/bfd_debug.log

# 通过MCP Python API调试时间线
/Users/qinghe/Library/Application\ Support/davinci-resolve-mcp/venv/bin/python3.12 -c "
import sys; sys.path.insert(0, '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules')
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp('Resolve')
tl = resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
# 查看标记: tl.GetMarkers()
# 查看片段: tl.GetItemListInTrack('video', 1)
"
```

## 架构

```
black_frame_detector.lua         # 主入口：Main() 11阶段流水线
modules/
  config.lua                     # 版本号、阈值、标记颜色/名称、预设、webhook、水印
  version_compat.lua             # Resolve版本检测 + API兼容适配（17/18/19/20）
  ffmpeg_runner.lua              # FFmpeg路径查找 + blackdetect调用
  black_frame_analyzer.lua       # 分类算法 + 帧号/时间码映射 + 覆盖表
  marker_manager.lua             # 时间线标记：批量添加(含帧去重)/清除
  ui_bridge.lua                  # UI抽象层：UIManager / AskUser / 纯脚本 + 反馈按钮
  duplicate_detector.lua         # 重复检测：路径+源范围重叠 + 跨文件帧指纹
  report_generator.lua           # TXT/HTML报告生成
  progress_bridge.lua            # 进度桥接（文件轮询）
  py_params_bridge.lua           # PySide参数桥接
pyside_ui/
  app.py                         # PySide6 主窗口 (QMainWindow)
  resolve_bridge.py              # 达芬奇通信桥接
  run_ui.sh / run_ui.bat         # 启动脚本
```

### 检测流水线

1. 版本检测 → 2. 时间线列表 → 3. UI参数 → 3.5 IO出入点 → 4. 收集视频片段 → 4.5 透明度/合成扫描 → 4.6 夹帧(时长) → 4.7 叠加夹帧 → 5. FFmpeg检查 → 6. blackdetect(成片/逐文件) → **8a. 路径重复 + 8b. 帧指纹内容重复** → 9. 标记管理 → 10. 结果窗口 → 11. HTML报告

### 阶段8 重复检测策略（v1.9.40+）

| 子阶段 | 模式 | 方法 | 检测什么 |
|--------|------|------|----------|
| 8a 路径重复 | 普通/复杂 | 同一文件 + 源时间码范围重叠 | 同一源文件的相同片段被多次使用 |
| 8b 帧指纹 | 普通 | 逐文件双哈希 + **跨文件边缘哈希比对** | 不同文件但画面内容相同（含调色后） |
| 8b 帧指纹 | 复杂 | 渲染文件全量指纹 | IO范围内的画面重复（最准确） |

- **双哈希算法**：块均值哈希(bm_hash)精确匹配 + 边缘哈希(edge_hash)汉明距离≤20调色免疫
- **跨文件比对**：全局指纹池 → 边缘哈希前缀分桶 → 汉明距离匹配，至少2帧命中
- **源范围重叠判断**：两片段在源文件中的使用范围 `[left_offset, left_offset+dur]` 有重叠才算重复，完全不重叠=正常场景切割
- 隐藏/禁用素材（opacity=0或is_enabled=false）不参与阶段8a路径重复检测

### 帧指纹FFmpeg注意事项

- **必须用 `-t` 不是 `-to`**：FFmpeg 8.x中 `-ss X -to Y -i file` 的 `-to` 被解释为绝对结束位置，`X>Y` 时报错。用 `-t`（时长）替代。
- **必须用完整ffmpeg路径**：达芬奇Lua环境PATH可能不含ffmpeg。阶段5缓存 `config._cached_ffmpeg_path`，`_extract_fingerprints` 优先使用。
- **`2>/dev/null` 会吞错误**：调试时去掉可看到FFmpeg的实际报错。

## 关键约定

- **版本号**：`config.PLUGIN_VERSION` 是唯一来源，其他模块通过 `require("config")` 读取。禁止在其他地方硬编码。
- **模块加载**：`safe_require()` 包裹 `require`，失败时 dlog 记录并返 nil。
- **API防护**：所有达芬奇API调用必须 `pcall` 包裹。Resolve 19 API方法可能不存在或返 nil。
- **Resolve 19限制**：`AddWindow` 返回的 win 无 `FindGUI` 方法，UI状态通过事件回调局部变量追踪。**无法程序化更新已创建的控件**。
- **帧号体系**：`GetStart()` 返回绝对帧号。`AddMarker` 需要显示相对帧号 = 绝对帧号 - start_offset。start_offset = timeline起始时间码转帧数。
- **IO范围**：Resolve 19所有IO API均返nil，必须用户手动输入。`full_timeline=true` 时跳过IO过滤。
- **调试日志**：`~/bfd_debug.log`，`dlog()` 每次写入后 `f:close()` 落盘。`version_compat.lua` 用 `vclog()`（`[VC]`前缀）。`config._trace()` 用 `[CFG]`前缀。
- **IO缓存**：`~/.bfd_io_cache.lua`（Lua格式），`loadfile()` 加载。**绝不用JSON格式**。
- **同帧单标记**：达芬奇 `AddMarker` 同一帧只能有一个标记，`marker_manager.lua` 按帧去重，后续记录跳过并计数。

### has_problems 守门条件

阶段7-11的守门条件检查：FFmpeg/透明度/夹帧/叠加全为空时，如果启用了重复检测（`params.detect_duplicate~=false and config.DUPLICATE.ENABLED`）则继续，否则跳过。新增检测类型时需同步更新此条件。

### 结果窗口双数据源

结果窗口从两个来源构建显示列表：
1. 传统 `analyzed_results`（errors/suspects/gaps/scenes）
2. `selected_records`（含重复/透明度/内容重复）
两者合并去重（按timeline_start_frame+marker_name），O(n+m)哈希表。

### 水印和完整性

- 发布包包含字节码保护和完整性校验（`bytecode_manifest.json`）
- 启动时比对核心模块哈希，不匹配则显示 `非官方构建` 并禁用核心检测
- 保持水印可追溯性，但禁止添加破坏性陷阱或资源浪费行为

## 达芬奇 MCP / Python API 注意事项

### AddMarker 颜色兼容性

有效15色: Red, Yellow, Green, Blue, Purple, Cyan, Pink, Fuchsia, Mint, Lavender, Rose, Cocoa, Sky, Sand, Cream  
无效: Orange, Tan, White, Black, Teal, Lime, Stone

**当前颜色分配（v1.9.104）**：

| 颜色 | 标记类型 |
|------|----------|
| Red | 夹帧错误 |
| Yellow | 可疑黑帧 / 半透明遮挡夹帧 |
| Blue | 场景转场 |
| Purple | 时间线空位 |
| Rose | 近距重复 |
| Sand | 远距重复 |
| Fuchsia | 内容重复(跨文件) |
| Mint | 隐藏素材 |
| Cocoa | 低透明度 |
| Lavender | 部分透明 |
| Cyan | 已禁用 / 远距复用 / 信息 |
| Green | 非标准合成 |
| Pink | 叠加夹帧(完全可见) |
| Sky | 渲染坏帧 |

### safe_add_marker 双重校验

pcall只捕获Lua异常，不检查AddMarker布尔返回值。v1.9.30修复为 `pcall_ok and result` 双重检查，失败时记录 `config._trace`。

### 禁止操作

- **绝不修改媒体池 `SetClipProperty('In'/'Out')`**：影响时间线上所有引用该素材的片段
- TimelineItem的 `SetLeftOffset`/`SetRightOffset` 不可调用
- Python API不支持索引号设置标记颜色（必须用字符串）
- TimelineItem没有 `GetClipProperty` 方法，必须通过 `GetMediaPoolItem()` 获取MediaPoolItem再调用

## 反馈功能

主界面"反馈"按钮 → 两步操作（避免阻塞UI）：
1. 首次点击 → 打开系统文本编辑器（非阻塞`open`），写入模板文件 `~/bfd_feedback.txt`
2. 用户编辑保存关闭后 → 再次点击 → 读取内容 + 最近200行调试日志 → POST到飞书webhook

Webhook URL: `config.FEISHU_WEBHOOK_URL`
