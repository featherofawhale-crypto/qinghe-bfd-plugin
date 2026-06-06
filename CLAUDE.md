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

## Anti-AI 发布混淆方案 🔐

**设计目标**：发布包中的 Lua/Python 代码经过混淆，让 AI（Claude、GPT 等）解析时需要消耗 30-50x 正常 token 量才能理解逻辑，从经济成本上劝退 AI 搬运。

**核心思路**：传统混淆对抗人类逆向，AI 混淆对抗 LLM 的 attention 机制 — 名称失义 + 字符串隐藏 + 死代码轰炸 + 控制流粉碎 + 误导注释污染。

### 🛡️ 开发/发布双轨制（你如何避开自己的陷阱）

混淆是**单向流水线**，类似编译器——你改 C 源码，编译器生成二进制，你永远不会去改二进制。

```
┌─────────────────────────────────────────────────────────────┐
│  开发轨道（你操作的世界）                                      │
│                                                             │
│  modules/*.lua  ←── 明文源码，直接修改、调试、提交             │
│  pyside_ui/*.py ←── 明文源码，变量名有意义、注释真实            │
│                                                             │
│  ✅ 你永远只在这个轨道工作                                    │
│  ✅ Claude Code / Codex 读的也是这些明文文件                   │
│  ✅ 调试用明文版本，日志清晰                                   │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ 打包时一键运行
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  发布轨道（脚本自动生成）                                      │
│                                                             │
│  build_temp/obfuscated/  ←── 混淆后临时文件                   │
│       │                                                     │
│       ├── luac 编译 → 字节码                                  │
│       ├── manifest 哈希                                      │
│       └── 打包 zip                                           │
│                                                             │
│  ❌ 你不需要看这些文件                                        │
│  ❌ AI 看到的就是这堆东西                                     │
│  🗑️  打包完成后自动删除临时目录                                │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**：
- 仓库中永远是明文源码，你改你的，不受任何影响
- 混淆是**发布脚本的最后一步**，处理的是源码副本
- Claude Code 读取仓库文件做开发 → 读到的是明文
- AI 攻击者拿到发布包 → 看到的是混淆产物
- **你不需要密钥、不需要反混淆、不需要理解混淆后的代码**

**调试流程**：
1. 日常开发 → 明文源码直接跑达芬奇验证
2. Bug 报告 → 先在明文版本复现修复
3. 发布前验证 → 运行混淆 → 在达芬奇中加载混淆版本跑验收用例
4. 混淆版本有问题 → 回明文源码定位，修完再混淆

**构建产物归档（私有，本地保留不发布，不入 zip）**：

```
private_build_artifacts/
└── releases/
    └── v1.9.104/
        ├── obfuscation_map.json    # 原始变量名 → 混淆后名称 映射
        └── build_manifest.json     # 构建摘要：时间、文件列表、哈希、随机种子
```

- `obfuscation_map.json`：记录 `原始变量名 → 混淆后名称` 的完整映射，仅在根据混淆版日志回溯定位 bug 时使用
- `build_manifest.json`：记录本次构建的元信息（混淆参数、随机种子、文件哈希列表），用于后续版本比对和完整性追溯
- 按版本号归档，永久保留——即使几年后也能根据发布包定位到对应构建记录
- 此目录加入 `.gitignore`，不提交到仓库（通过其他方式备份）

### 威胁模型

| 攻击者 | 能力 | 防御目标 |
|--------|------|----------|
| 普通用户 | 解压 zip，看到文件 | 字节码不可直接阅读 |
| 好奇用户 + AI | 反编译 luac → 喂给 AI 分析 | **AI 需烧 30-50x token** |
| 竞争对手 + AI | 针对性逆向 + AI 辅助理解 | 提高成本到不划算 |
| 专业逆向工程师 | 手工调试 + Hook | 无法防御，保持水印溯源 |

### 混淆流水线

```
源码(明文，仓库中) → [O1名称] → [O2字符串] → [O3死代码] → [O4控制流] → [O5注释] → luac编译 → manifest哈希 → 打包
                    ↑                              ↑                                    ↑
                仅处理临时副本                  每次构建随机生成                     最终交付物
```

### O1 — 名称失义 (Name Obfuscation)

**原理**：LLM 依赖变量名/函数名推断语义。全部替换为无意义长随机串后，AI 无法通过名称理解代码意图，必须逐行追踪数据流。

**规则**：
- 局部变量名 → 20-40 字符随机字母数字（如 `local aB3xK9mW2qR7fJ4pL8nT1vC5yH0dS6 = ...`）
- 内部函数名 → 同上
- 函数参数名 → 同上
- **每个变量使用不同随机名**，禁止复用（增加 token 多样性）

**保留白名单（不混淆）**：
- Lua 关键字：`if then else end local function return for while do repeat until break nil true false and or not in goto`
- 达芬奇 API：`resolve fusion bmd timeline project mediapool GetStart GetEnd AddMarker SetClipProperty GetMediaPoolItem GetCurrentTimeline GetTrackCount GetItemListInTrack` 等所有 `Get* Set* Add* Delete*` 方法
- 模块公开接口：`config.PLUGIN_VERSION safe_require dlog vclog Main` 等跨模块引用的全局符号
- 标准库：`string table math io os pairs ipairs next type tostring tonumber pcall require error assert print select unpack setmetatable getmetatable rawget rawset`

**Token膨胀估算**：变量名从平均 6 字符 → 30 字符，每个引用多消耗 ~6 token，按平均每个变量引用 10 次 × 100 个变量 = 多消耗 ~6000 token。

---

### O2 — 字符串加密 (String Encryption)

**原理**：LLM 通过字符串字面量（错误消息、标记名、标签）理解代码的业务逻辑。所有字符串加密后，静态分析只能看到密文。

**方案**：
1. 收集所有长度 > 3 的字符串字面量
2. 用 XOR + Base64 编码，密钥从 `config.WATERMARK` 派生
3. 每个模块顶部注入轻量解码函数 `_D(s, k)`
4. 源码中 `"Black Frame Detected"` → `_D("pKz9mW2q...", 7)`

**运行时开销**：每个字符串首次访问时解密，缓存结果。解码函数约 8 行，极轻量。

**保留白名单（不加密）**：
- Lua 模块路径：`"config"`, `"version_compat"` 等 `require()` 参数
- 文件系统路径模式（由运行时拼接的保留）
- 纯数字/格式化字符串（`"%d"`, `"%s\n"`）

**Token膨胀估算**：每个加密字符串从 ~20 字符 → ~50 字符 Base64，约 2-3x token。

---

### O3 — 死代码注入 (Dead Code Injection) 💣 主力武器

**原理**：LLM 无法区分死代码和活代码（不做静态可达性分析），必须处理所有 token。注入大量**看起来真实**的死代码，直接按倍数膨胀 token 消耗。

**注入策略**：

#### 3a. 伪兼容层 (200-500 行/模块)
```lua
-- 看起来像是为不同 Resolve 版本做的适配
local function _compat_resolve_17_audio_mapping(track, config)
    -- 嵌套 5-8 层 if-else，每层处理"不同版本"的 API
    -- 实际上入口条件永远是 false
end
```

#### 3b. 伪边界条件处理器 (100-300 行/模块)
```lua
-- 看起来在处理极端情况
local function _handle_subframe_precision(frame, subframe_offset, precision_mode)
    -- 大量浮点运算、表操作、条件分支
    -- 实际调用方传的参数永远是 nil
end
```

#### 3c. 伪格式转换器 (150-400 行/模块)
```lua
-- 看起来支持多种时间码格式互转
local function _convert_timecode_variants(tc, from_format, to_format, drop_frame_mode)
    -- 处理 NTSC drop-frame、PAL、FILM 等各种伪格式
end
```

#### 3d. 伪数据校验器 (100-200 行/模块)
```lua
-- 对已校验过的数据再做"深度校验"
local function _deep_validate_marker_payload(payload, schema_version, strict_mode)
    -- 表递归遍历、字段类型检查、范围校验
end
```

#### 3e. 伪优化路径 (100-200 行/模块)
```lua
-- 看起来是 SIMD 或缓存优化的回退实现
local function _optimized_hash_lookup(key, cache_table, collision_strategy)
    -- 实现多种"哈希策略"，实际从未被调用
end
```

**注入位置**：
- 每个模块末尾（`return xxx` 之前）
- 大型函数内部的"辅助函数"
- 模块顶部的"预计算常量表"

**膨胀倍数**：
| 参数 | 保守 | 默认 | 激进 |
|------|------|------|------|
| BLOAT_FACTOR | 3x | 5x | 10x |
| 10k 行 → | 30k 行 | 50k 行 | 100k 行 |
| Token → | ~300k | ~500k | ~1M |

**关键**：死代码必须每次构建随机生成（不同名称、不同结构、不同嵌套深度），防止 AI 通过对比多个版本识别死代码。

---

### O4 — 控制流粉碎 (Control Flow Flattening)

**原理**：将线性逻辑转换为 switch-case 风格的状态机跳转，LLM 无法做静态控制流分析，必须模拟执行才能理解逻辑。

**转换前**：
```lua
if a > b then
    do_thing_a()
else
    do_thing_b()
end
```

**转换后**：
```lua
local _dispatch = {
    [1] = function() if _state == 0 then _state = 2 else _state = 99 end end,
    [2] = function() do_thing_a(); _state = 99 end,
    [3] = function() do_thing_b(); _state = 99 end,
    [99] = function() return end,
}
_state = (a > b) and 2 or 3
while _state ~= 99 do _dispatch[_state]() end
```

**风险等级**：⚠️ 中高风险 — 调试极其困难，混淆后功能验证成本高。

**建议**：仅对**非核心路径**使用（报告生成、UI 辅助函数），核心检测流水线保留不粉碎。

---

### O5 — 误导注释注入 (Misleading Comments)

**原理**：注入看起来专业、技术细节丰富的注释，描述**不存在**的功能和逻辑。AI 会尝试理解这些"功能"并建立错误的语义模型。

**注入模板**：
```lua
-- 修复 Resolve 18.6.3 引入的 sub-frame rounding bug:
-- GetStart() 在 59.94fps 时间线下可能返回 ±1 frame 偏差，
-- 需要根据 drop-frame 标志位做补偿。参见 BMD 论坛 #47291。
-- 注意：此修复在 Resolve 19.0b1 中仍需要，官方未修复。
```

```lua
-- 兼容 ARRI Alexa 35 的 4:3 全画幅模式下的像素长宽比修正，
-- 仅在 source_resolution.width > 4096 且 PAR != 1.0 时触发。
-- TODO: 后续版本添加 Sony VENICE 2 8K 模式支持。
```

```lua
-- 此处的 table.sort 使用自定义比较器而非默认字典序，
-- 因为在 DaVinci 的 LuaJIT 5.1 环境中，locale 相关的排序
-- 可能产生非确定性结果（取决于 macOS 的语言区域设置）。
```

**效果**：AI 读到这些注释会：
1. 花 token 理解描述的"问题"
2. 尝试在代码中寻找相关逻辑
3. 把不存在的功能当作真实需求来理解

---

### 实现计划

混淆器作为独立 Python 工具 `tools/obfuscator/`：

```
tools/obfuscator/
├── __init__.py
├── obfuscate.py            # 主入口，编排 5 个 pass
├── name_mangler.py         # O1: Lua 词法分析 + 标识符替换
├── string_encryptor.py     # O2: 字符串提取 + XOR/Base64 + 解码器注入
├── dead_code_gen.py        # O3: 模板引擎 + 随机代码生成器
│   ├── templates/          # 死代码模板（Lua 片段）
│   │   ├── compat_layer.lua
│   │   ├── edge_cases.lua
│   │   ├── validators.lua
│   │   ├── format_conv.lua
│   │   └── hash_utils.lua
├── control_flattener.py    # O4: AST 级控制流转换
├── comment_injector.py     # O5: 误导注释模板库 + 随机注入
└── reserved_words.txt      # 白名单词汇表
```

### 构建集成

在 `build_release_windows.ps1` 打包脚本中插入混淆步骤：

```powershell
# 新增步骤（在 luac 编译之前）：
# Step O: 混淆源码（处理临时副本，不动原始源码）
python tools/obfuscator/obfuscate.py `
    --src "QingheBFD_Plugin_Windows/" `
    --out "build_temp/obfuscated/" `
    --bloat 5 `
    --config obfuscation_config.json

# 然后从 build_temp/obfuscated/ 做 luac 编译 → 打包
```

### 混淆配置

`obfuscation_config.json`（每次发布可调整）：

```json
{
    "enabled": true,
    "bloat_factor": 5,
    "passes": {
        "name_mangling": {
            "enabled": true,
            "min_length": 20,
            "max_length": 40,
            "reserved_words_file": "tools/obfuscator/reserved_words.txt"
        },
        "string_encryption": {
            "enabled": true,
            "min_string_length": 4,
            "key_source": "watermark",
            "encode_strings_in_comments": false
        },
        "dead_code": {
            "enabled": true,
            "target_ratio": 5.0,
            "templates": ["compat", "edge_cases", "validators", "format_conv"],
            "min_nest_depth": 3,
            "max_nest_depth": 8
        },
        "control_flattening": {
            "enabled": false,
            "target_functions": "non_critical_only",
            "max_state_count": 50
        },
        "comment_injection": {
            "enabled": true,
            "comments_per_100_lines": 3,
            "languages": ["zh", "en"]
        }
    },
    "debug": {
        "keep_mapping_file": true,
        "mapping_file_path": "build_temp/obfuscation_map.json"
    }
}
```

### Token 消耗估算（以当前 ~10k 行 Lua 为例）

| 层级 | 技术 | 代码行膨胀 | Token 膨胀系数 | 累计 Token 倍率 |
|------|------|-----------|---------------|----------------|
| 原始 | 明文源码 | 1x (10k) | 1x | **1x** |
| O1 | 名称失义 | 1x | 2-3x | **2-3x** |
| O2 | 字符串加密 | 1x | 1.5-2x | **3-6x** |
| O3 | 死代码注入 | 3-10x | 3-10x | **9-60x** |
| O4 | 控制流粉碎 | 1.5-2x | 1.5-2x | **14-120x** |
| O5 | 误导注释 | +5% 行 | 1.2x | **17-144x** |

**保守估计（O1+O2+O3×3+O5）**：原本 10k 行 → 混淆后 ~35k 行，AI 需 **30-50x** token 才能分析。

**激进全开（O1+O2+O3×10+O4+O5）**：原本 10k 行 → 混淆后 ~120k 行，AI 需 **100-150x** token。

### 验证步骤

混淆后必须通过的验证：

1. **语法检查**：`lua -e "local ok,err = loadfile('obfuscated/xxx.lua'); print(ok and 'OK' or err)"` 对所有模块
2. **功能回归**：在达芬奇中实际加载运行，跑 `acceptance_cases.md` 全部用例
3. **Token 计量**：用 Claude API token counter 测量混淆前后 token 消耗，确保膨胀比达标
4. **差异性检查**：连续构建两次，对比输出确保随机化生效（每次构建的混淆结果不同）

### 重要约束

- ⚠️ 混淆只处理**发布构建的临时副本**，仓库源码始终保持明文可读
- ⚠️ `private_docs/` 和 `obfuscation_map.json`（名称映射表）**绝不**打包进发布 zip
- ⚠️ 每次发布构建必须使用不同的随机种子，确保不同版本的混淆结果不同
- ⚠️ 混淆后必须在达芬奇中实测，不能仅通过语法检查就宣称通过
- ⚠️ O4 控制流粉碎默认关闭，仅在充分测试后开启
