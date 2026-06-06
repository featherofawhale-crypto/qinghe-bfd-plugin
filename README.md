# 清何黑帧夹帧检测小工具

一个 DaVinci Resolve Lua 插件，自动检测视频中的**黑帧**和**夹帧错误**，在时间线上打彩色标记以便快速定位修复。支持帧指纹内容重复检测。

## 功能特性

- **自动黑帧检测** — 基于 FFmpeg blackdetect 滤镜，分析时间线上所有视频片段
- **智能分类** — 自动区分夹帧错误（红）、可疑黑帧（黄）、正常转场（蓝）
- **跨版本兼容** — 支持 DaVinci Resolve 17 / 18 / 19 / 20（Studio + Free）
- **跨平台** — macOS / Windows / Linux 均可使用
- **一键安装** — 提供自动化安装脚本，3 步完成
- **检测报告** — 自动生成 TXT 报告，HTML 可选
- **多轨道** — 支持扫描视频轨道上的所有片段

## 检测原理

使用 FFmpeg 的 `blackdetect` 滤镜逐帧分析每个视频片段，根据检测到的黑帧持续时间进行分类：

| 黑帧时长 | 分类 | 时间线标记 |
|---------|------|-----------|
| ≤ 0.12s (约3帧@24fps) | **夹帧错误** | 🔴 红色 |
| 0.12s ~ 0.50s | **可疑黑帧** | 🟡 黄色 |
| > 0.50s | **场景转场** | 🔵 蓝色 |

> 基于**秒数**判定，兼容 24fps / 25fps / 30fps / 60fps 等不同帧率。

## 依赖要求

- **DaVinci Resolve** 17.0 或更高版本（Studio 或 Free 均可）
- **FFmpeg**（包含 blackdetect 滤镜，通常默认编译）

## 快速安装

### macOS / Linux

```bash
chmod +x install/install.sh
./install/install.sh
```

### Windows

双击运行 `install/install.bat`，或在命令提示符中执行：

```cmd
install.bat
```

如需强制覆盖已安装的版本：

```bash
./install/install.sh --force    # macOS/Linux
install.bat --force             # Windows
```

## 使用方法

1. 启动 DaVinci Resolve，打开项目和包含视频素材的时间线
2. 菜单栏 → **工作区** → **脚本** → **black_frame_detector**
3. 在弹出的对话框中配置参数（或使用默认值），点击**开始检测**
4. 等待分析完成，时间线上会自动出现红色/黄色/蓝色标记
5. 检测报告自动保存到桌面

## 参数说明

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| 最小黑帧时长 | 0.04s | 0.01-0.10s | FFmpeg d 参数，低于此值的黑帧不检测 |
| 像素阈值 | 0.01 | 0.001-0.05 | 黑色亮度阈值，值越小越严格 |
| 画面占比 | 0.95 | 0.80-1.00 | 画面中黑像素占比达到此值才认定为黑帧 |
| 夹帧判定上限 | 0.12s | 0.04-0.25s | ≤此值的黑帧判定为夹帧错误（红色） |
| 可疑帧上限 | 0.50s | 0.20-1.00s | ≤此值的黑帧判定为可疑（黄色），超出为转场（蓝色） |

### 灵敏度预设

| 预设 | 适用场景 | 特点 |
|------|---------|------|
| 高灵敏度 | 精检，逐帧排查 | 可检测到 1 帧的极短夹帧，误报可能稍多 |
| 标准（推荐） | 日常检测 | 平衡检测率与误报率 |
| 低灵敏度 | 快速扫描 | 仅检测明显夹帧（约3帧以上） |

## 文件结构

```
black_frame_detector/
├── black_frame_detector.lua    # 主入口
├── modules/
│   ├── config.lua              # 全局配置
│   ├── version_compat.lua      # 版本兼容适配
│   ├── ffmpeg_runner.lua       # FFmpeg 调用封装
│   ├── black_frame_analyzer.lua # 分类算法
│   ├── marker_manager.lua      # 标记管理
│   ├── ui_bridge.lua           # UI 抽象层
│   └── report_generator.lua    # 报告生成
├── install/
│   ├── install.sh              # macOS/Linux 安装
│   ├── install.bat             # Windows 安装
│   └── uninstall.sh            # 卸载脚本
└── README.md
```

## 卸载

### macOS / Linux

```bash
./install/uninstall.sh
```

### Windows

手动删除安装目录 `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\black_frame_detector\`

## 兼容性说明

- **Resolve 17**: 使用兼容 API（`GetItemsInTrack`）
- **Resolve 18/19/20**: 使用新版 API（`GetItemListInTrack`）
- **Resolve Free (免费版)**: UI 降级为简化对话框模式
- **Resolve Studio**: 使用完整 UI 界面
- 免费版 Resolve 19.1+ 移除了 UIManager，本插件会自动降级

## 常见问题

### Q: 提示"未找到 FFmpeg"

macOS: `brew install ffmpeg`
Windows: `winget install ffmpeg` 或从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载
Linux: `sudo apt install ffmpeg` (Ubuntu/Debian)

### Q: 检测不到黑帧

- 尝试提高灵敏度（降低像素阈值参数）
- 检查视频文件路径是否可访问
- 确认素材中确实存在黑帧

### Q: 误报太多

- 降低灵敏度（提高像素阈值或夹帧判定上限）
- 提高画面占比阈值到 0.98

### Q: FFmpeg 分析速度慢

这是正常的。blackdetect 需要解码整个视频文件，长视频或高分辨率素材会较慢。建议先用低分辨率代理文件检测。

## 版本

v1.0.0 — 首个正式版本

## License

MIT License
