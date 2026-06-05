# Pending Codex Tasks

Issues Claude couldn't fully resolve. Reference the working v1.9.48 Lua implementation where noted.

## 1. IO出入点读取 (current_timeline_marks)

**文件**: `resolve_bridge.py` → `ResolveBridge.current_timeline_marks()`

**问题**: Resolve 19 的 IO API 不稳定，简单调用无法读取。当前只试了几个方法就放弃。

**Lua参考** (已实现并工作): `modules/version_compat.lua` → `VersionCompat:get_in_out_range()` (line 317-500+)

Lua版本使用了**穷举探测策略**，按阶段尝试：
- 阶段A: 枚举timeline对象所有方法，找IO相关的
- 阶段B: 直接调用所有已知API: `GetInPoint`, `GetOutPoint`, `GetIn`, `GetOut`, `GetInPointFrame`, `GetOutPointFrame`, `GetRenderIn`, `GetRenderOut`, `GetMarkIn`, `GetMarkOut`, `GetTimelineIn`, `GetTimelineOut`, `GetIOIn`, `GetIOOut`, `GetRangeIn`, `GetRangeOut`
- 阶段C: `GetSetting()` 探测所有可能键名: `timelineIn`, `timelineOut`, `InPoint`, `OutPoint`, `renderIn`, `renderOut`, `markIn`, `markOut`, `ioIn`, `ioOut`, `timelineInFrame`, `timelineOutFrame` 等
- 阶段D: `GetRenderSettings()` 枚举渲染设置
- 阶段E: Project设置探测
- 阶段F: 帧号转换(start_frame + display_frame)

**当前Python代码位置**: `resolve_bridge.py` line 517-648 `current_timeline_marks()`
需要按Lua版本的穷举策略重写。

---

## 2. SRT增量替换位置偏移

**文件**: `resolve_bridge.py` → `ResolveBridge.replace_subtitles_from_srt()`

**问题**: `mp.AppendToTimeline()` 在字幕轨道非空时无视SRT时间码，新字幕追加到末尾。

**当前方案**: 全量删除+全量导入（可工作但用户不满意）

**期望方案**: 只替换修改过的字幕条目，保留未改动的字幕位置和格式

**已知事实**:
- `timeline.DeleteClips([clip], False)` ✅ 可删除指定字幕
- `mp.ImportMedia(srt_file)` ✅ 可导入SRT到媒体池
- `mp.AppendToTimeline([mpi])` ❌ 轨道非空时无视时间码
- `timeline.InsertGeneratorIntoTimeline('Subtitle')` ✅ 创建字幕但文字固定为"Subtitle"
- `timeline.SetCurrentTimecode(tc)` ✅ 可移动播放头
- SRT时间码格式: `00:00:01,000 --> 00:00:02,000`

**可能方向**:
- 创建临时空时间线 → 导入SRT → 读取位置 → 删除 → 切回主时间线操作？
- 或其他API组合

---

## 3. 窗口置顶在macOS可能不稳定

**文件**: `app.py` → `MainWindow.__init__()`

**当前**: `self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)`

**问题**: macOS上`WindowStaysOnTopHint`可能不生效，需要使用macOS原生API:
```python
# macOS原生置顶
import objc
from Foundation import NSWindow
# 或者用 ctypes 调用 CoreGraphics
```

---

## 关键文件路径

```
pyside_ui/
  app.py              # PySide6 主窗口
  resolve_bridge.py   # 达芬奇通信桥接

0603/QingheBFD_v1.9.104_macOS/QingheBFD_Plugin_macOS/
  pyside_ui/app.py
  pyside_ui/resolve_bridge.py

# Lua参考 (v1.9.48 - 工作版本):
modules/version_compat.lua  # IO读取 (line 317-500)
black_frame_detector.lua    # 主脚本 IO读写 (line 294-321)
```

## 当前版本

v1.9.104 (0603目录)
