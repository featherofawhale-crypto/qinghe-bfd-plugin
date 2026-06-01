from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from resolve_bridge import BRIDGE_WORKER_ARG, ResolveBridge, TimelineInfo, read_progress_file, run_resolve_bridge_worker


APP_VERSION = "1.9.56"
FEEDBACK_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/c533d532-4041-4e58-abd5-6f9eb924d58c"


APP_STYLE = """
QToolTip {
    background: #10151c;
    color: #eef5ff;
    border: 1px solid #3d5164;
    padding: 8px;
    border-radius: 4px;
}
QWidget {
    background: #101317;
    color: #e7edf3;
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI";
    font-size: 13px;
}
QMainWindow { background: #101317; }
QFrame#Shell {
    background: #151a20;
    border: 1px solid #28313b;
    border-radius: 8px;
}
QFrame#Panel {
    background: #171d24;
    border: 1px solid #2a3440;
    border-radius: 8px;
}
QFrame#StatCard {
    background: #121820;
    border: 1px solid #2a3440;
    border-top: 3px solid #35c4a1;
    border-radius: 6px;
}
QLabel#Title {
    font-size: 24px;
    font-weight: 700;
    color: #f5f7fa;
}
QLabel#Subtitle, QLabel#Muted { color: #93a4b5; }
QLabel#BadgeOk {
    color: #bff4d2;
    background: #153323;
    border: 1px solid #2d8a51;
    border-radius: 5px;
    padding: 4px 9px;
    font-weight: 700;
}
QLabel#BadgeWarn {
    color: #ffd48a;
    background: #332817;
    border: 1px solid #8a651f;
    border-radius: 5px;
    padding: 4px 9px;
    font-weight: 700;
}
QGroupBox {
    border: 1px solid #2a3440;
    border-radius: 8px;
    margin-top: 22px;
    padding: 16px 14px 14px 14px;
    background: #171d24;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #cbd8e3;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit {
    min-height: 34px;
    border-radius: 6px;
    border: 1px solid #33404d;
    background: #0e1116;
    color: #f0f4f8;
    padding: 4px 9px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #4d6072;
}
QCheckBox { spacing: 8px; color: #d7e0ea; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox:disabled { color: #667481; }
QPushButton {
    min-height: 34px;
    border-radius: 7px;
    border: 1px solid #344252;
    background: #202832;
    color: #eaf1f8;
    padding: 6px 12px;
    font-weight: 700;
}
QPushButton:hover { background: #2a3542; border-color: #4a5c70; }
QPushButton#Primary {
    min-height: 42px;
    background: #d97925;
    border-color: #f29a3b;
    color: white;
}
QPushButton#Primary:hover { background: #e98731; }
QPushButton#Primary:disabled { background: #4a3a2b; color: #9b8b7a; }
QProgressBar {
    min-height: 16px;
    border-radius: 8px;
    background: #0d1014;
    border: 1px solid #2b3541;
    text-align: center;
    color: #dff8f1;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: #35c4a1;
}
QSlider::groove:horizontal {
    height: 6px;
    border-radius: 3px;
    background: #26313c;
}
QSlider::sub-page:horizontal {
    border-radius: 3px;
    background: #d97925;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
    background: #ffe2c4;
    border: 1px solid #f29a3b;
}
QTextEdit {
    background: #0c0f13;
    border: 1px solid #2a3440;
    border-radius: 8px;
    color: #b7c5d1;
    padding: 8px;
}
"""


MARKER_COLORS = {
    "error": "#ff5b5b",
    "suspect": "#ffd166",
    "scene": "#61a8ff",
    "gap": "#b589ff",
    "duplicate": "#ff8db3",
    "content_dup": "#f15bb5",
    "opacity": "#63d7a4",
    "corrupt": "#72d3ff",
}


def set_tip(widget: QWidget, text: str) -> QWidget:
    widget.setToolTip(text)
    return widget


def install_cjk_font() -> str:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return families[0]
    return "Microsoft YaHei"


def debug_log_path() -> Path:
    return Path.home() / "bfd_debug.log"


def read_debug_log_tail(max_chars: int = 12000) -> str:
    path = debug_log_path()
    if not path.exists():
        return "未找到调试日志。"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"读取调试日志失败: {exc}"
    return text[-max_chars:]


def build_feedback_payload(message: str) -> dict:
    return {
        "msg_type": "text",
        "content": {
            "text": (
                "【BFD 用户反馈】\n"
                f"版本: v{APP_VERSION}\n"
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"反馈内容:\n{message.strip()}\n\n"
                "--- 最近调试日志 ---\n"
                f"{read_debug_log_tail()}"
            )
        },
    }


def send_feedback_message(message: str) -> tuple[bool, str]:
    if not message.strip():
        return False, "反馈内容为空。"
    payload = json.dumps(build_feedback_payload(message), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        FEEDBACK_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return False, f"发送失败: {exc}"
    except Exception as exc:
        return False, f"发送失败: {exc}"
    if '"code":0' in body or '"ok":true' in body or body.strip() == "":
        return True, "反馈已发送。"
    return False, f"服务器返回异常: {body[:300]}"


class SubmitWorker(QThread):
    progress = Signal(int, str)
    done = Signal(bool, str)

    def __init__(self, bridge: ResolveBridge, params: dict, auto_run_lua: bool) -> None:
        super().__init__()
        self.bridge = bridge
        self.params = params
        self.auto_run_lua = auto_run_lua

    def run(self) -> None:
        self.progress.emit(18, "正在序列化检测参数")
        time.sleep(0.15)
        params_path = self.bridge.submit_params(self.params)

        self.progress.emit(45, f"参数已写入 {params_path}")
        self.bridge.open_resolve_page()

        if self.auto_run_lua:
            self.progress.emit(70, "正在通过 fuscript 触发 Lua 入口")
            ok, message = self.bridge.run_lua_entry_with_fuscript(params_path)
            self.progress.emit(100, "已提交给 Resolve" if ok else "参数已写入，自动触发失败")
            if ok:
                self.done.emit(True, message or "检测已提交。")
            else:
                self.done.emit(
                    True,
                    "参数已写入。请在 Resolve 中运行原 Lua 脚本；它会自动读取这次 PySide6 参数。\n"
                    + message,
                )
            return

        self.progress.emit(100, "参数已准备好")
        self.done.emit(
            True,
            "参数已写入。现在到 Resolve 里运行原 Lua 脚本，它会跳过旧 UI 并读取这次配置。",
        )


class FeedbackDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("反馈")
        self.resize(620, 500)

        layout = QVBoxLayout(self)
        title = QLabel("反馈给清何")
        title.setObjectName("Title")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        layout.addWidget(title)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("写清楚：发生了什么、你期望什么、当前工程/素材有什么特点。日志会自动附带。")
        set_tip(self.editor, "反馈会附带最近的 bfd_debug.log，方便定位崩溃、误报和达芬奇版本兼容问题。")
        layout.addWidget(self.editor, 1)

        self.log_preview = QTextEdit()
        self.log_preview.setReadOnly(True)
        self.log_preview.setMinimumHeight(120)
        self.log_preview.setText(read_debug_log_tail(4000))
        set_tip(self.log_preview, "这是将随反馈一起发送的最近调试日志预览。")
        layout.addWidget(self.log_preview)

        buttons = QDialogButtonBox()
        self.send_btn = buttons.addButton("发送反馈", QDialogButtonBox.AcceptRole)
        self.copy_btn = buttons.addButton("复制诊断", QDialogButtonBox.ActionRole)
        buttons.addButton("关闭", QDialogButtonBox.RejectRole)
        self.send_btn.clicked.connect(self.send_feedback)
        self.copy_btn.clicked.connect(self.copy_diagnostics)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def copy_diagnostics(self) -> None:
        QGuiApplication.clipboard().setText(build_feedback_payload(self.editor.toPlainText())["content"]["text"])
        QMessageBox.information(self, "已复制", "反馈内容和日志已复制到剪贴板。")

    def send_feedback(self) -> None:
        ok, message = send_feedback_message(self.editor.toPlainText())
        if ok:
            QMessageBox.information(self, "反馈", message)
            self.accept()
        else:
            QMessageBox.warning(self, "反馈", message)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        font_family = install_cjk_font()
        app = QApplication.instance()
        if app:
            app.setFont(QFont(font_family, 10))
        self.setWindowTitle("清何黑帧夹帧检测 - Pro Control")
        self.resize(1120, 780)
        self.bridge = ResolveBridge()
        self.timelines: list[TimelineInfo] = []
        self.worker: SubmitWorker | None = None
        self.result_values: dict[str, QLabel] = {}
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(700)
        self.progress_timer.timeout.connect(self.poll_detection_progress)

        shell = QFrame()
        shell.setObjectName("Shell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        root.addLayout(self._build_header())
        root.addWidget(self._build_timeline_group())

        main_grid = QGridLayout()
        main_grid.setHorizontalSpacing(12)
        main_grid.setVerticalSpacing(10)
        main_grid.addWidget(self._build_detection_group(), 0, 0)
        main_grid.addWidget(self._build_threshold_group(), 0, 1)
        main_grid.addWidget(self._build_advanced_group(), 1, 0, 1, 2)
        root.addLayout(main_grid)

        root.addWidget(self._build_action_group())
        root.addWidget(self._build_result_group())

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(118)
        set_tip(self.log, "这里显示参数提交、Resolve 执行和进度文件回传的信息。")
        root.addWidget(self.log)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(14, 14, 14, 14)
        wrapper_layout.addWidget(shell)
        self.setCentralWidget(wrapper)

        self.refresh_timelines()
        self.on_complex_mode_changed(self.chk_complex.isChecked())
        self._log("Resolve API: " + ("已连接" if self.bridge.is_connected() else "未连接，使用离线参数模式"))

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("清何黑帧夹帧检测")
        title.setObjectName("Title")
        subtitle = QLabel(f"v{APP_VERSION} / PySide6 参数控制台 / DaVinci Resolve Bridge")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.connection_badge = QLabel("已连接" if self.bridge.is_connected() else "离线参数")
        self.connection_badge.setObjectName("BadgeOk" if self.bridge.is_connected() else "BadgeWarn")
        set_tip(self.connection_badge, "已连接表示 Python 能读到当前 Resolve 工程；离线参数仍可写入，稍后由 Lua 读取。")

        layout.addLayout(title_box, 1)
        layout.addWidget(self.connection_badge)
        return layout

    def _build_timeline_group(self) -> QGroupBox:
        box = QGroupBox("时间线")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.timeline_combo = QComboBox()
        set_tip(self.timeline_combo, "选择要检测的 Resolve 时间线；默认会优先当前打开的时间线。")
        refresh = QPushButton("刷新")
        refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        set_tip(refresh, "重新读取 DaVinci Resolve 当前工程内的时间线列表。")
        refresh.clicked.connect(self.refresh_timelines)

        self.io_in = QLineEdit()
        self.io_in.setPlaceholderText("可选，例如 01:00:00:00")
        set_tip(self.io_in, "限制检测起点。复杂模式必须填写入点，因为它会先渲染指定范围再分析。")
        self.io_out = QLineEdit()
        self.io_out.setPlaceholderText("可选，例如 01:02:30:00")
        set_tip(self.io_out, "限制检测终点。复杂模式必须填写出点，避免渲染整条时间线导致过慢。")

        layout.addWidget(QLabel("目标时间线"), 0, 0)
        layout.addWidget(self.timeline_combo, 0, 1, 1, 3)
        layout.addWidget(refresh, 0, 4)
        layout.addWidget(QLabel("手动入点"), 1, 0)
        layout.addWidget(self.io_in, 1, 1)
        layout.addWidget(QLabel("手动出点"), 1, 2)
        layout.addWidget(self.io_out, 1, 3)
        return box

    def _build_detection_group(self) -> QGroupBox:
        box = QGroupBox("检测与标记")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(10)

        self.chk_error = self._marker_check("夹帧错误", "error", True, "片段或黑场持续帧数小于等于夹帧阈值，会打红色 [BFD-ERR] 标记。")
        self.chk_suspect = self._marker_check("可疑黑帧", "suspect", True, "黑场超过夹帧阈值但不超过可疑阈值，会打黄色 [BFD-SUS] 标记，建议人工确认。")
        self.chk_scene = self._marker_check("转场黑场", "scene", False, "超过可疑阈值的黑场更像正常转场，默认不标，避免时间线太乱。")
        self.chk_gap = self._marker_check("时间线空位", "gap", True, "检测片段之间的空洞，适合找不小心漏剪出的空白。")
        self.chk_duplicate = self._marker_check("重复素材", "duplicate", True, "按源文件、轨道距离和时间距离找近距/远距重复，适合短剧误复制排查。")
        self.chk_content_dup = self._marker_check("内容重复", "content_dup", False, "用帧指纹比较画面内容，可找不同文件但画面重复的片段，耗时会增加。")
        self.chk_opacity = self._marker_check("透明度/禁用", "opacity", True, "直接读取时间线属性，找不透明度为 0、低透明、禁用和非标准合成。")
        self.chk_corrupt = self._marker_check("渲染坏帧", "corrupt", False, "必须先开启复杂模式：坏帧检测依赖渲染后的最终像素，再用 signalstats/熵/亮度离群分析。")

        checks = [
            self.chk_error,
            self.chk_suspect,
            self.chk_scene,
            self.chk_gap,
            self.chk_duplicate,
            self.chk_content_dup,
            self.chk_opacity,
            self.chk_corrupt,
        ]
        for index, check in enumerate(checks):
            layout.addWidget(check, index // 2, index % 2)
        return box

    def _build_threshold_group(self) -> QGroupBox:
        box = QGroupBox("阈值")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.severity = QComboBox()
        self.severity.addItems(["短剧默认", "严格排雷", "极严复查"])
        set_tip(self.severity, "一键调整夹帧阈值、可疑阈值和黑场像素阈值；仍可手动微调下面的数值。")
        self.severity.currentIndexChanged.connect(self.apply_severity)

        self.stuck_frames = QSpinBox()
        self.stuck_frames.setRange(1, 999)
        self.stuck_frames.setValue(3)
        set_tip(self.stuck_frames, "小于等于这个帧数的黑场/露出片段会被视为必须修复的夹帧。")
        self.stuck_slider = self._make_slider(1, 999, 3, self.stuck_frames)

        self.suspect_frames = QSpinBox()
        self.suspect_frames.setRange(1, 9999)
        self.suspect_frames.setValue(12)
        set_tip(self.suspect_frames, "大于夹帧阈值且小于等于该值，会归为可疑黑帧；再长则归为转场。")
        self.suspect_slider = self._make_slider(1, 9999, 12, self.suspect_frames)

        self.pixel_threshold = QDoubleSpinBox()
        self.pixel_threshold.setRange(0.001, 1.0)
        self.pixel_threshold.setSingleStep(0.01)
        self.pixel_threshold.setDecimals(3)
        self.pixel_threshold.setValue(0.010)
        set_tip(self.pixel_threshold, "FFmpeg blackdetect 的 pix_th。越低越严格，越高越容易把暗画面判成黑。")
        self.pixel_slider = self._make_float_slider(1, 1000, 10, self.pixel_threshold, 1000.0)

        self.min_duration = QDoubleSpinBox()
        self.min_duration.setRange(0.001, 60.0)
        self.min_duration.setSingleStep(0.01)
        self.min_duration.setDecimals(3)
        self.min_duration.setValue(0.040)
        set_tip(self.min_duration, "FFmpeg blackdetect 的 d 参数。短于这个时长的黑场会被忽略。")
        self.min_duration_slider = self._make_float_slider(1, 60000, 40, self.min_duration, 1000.0)

        self.content_sample_interval = QSpinBox()
        self.content_sample_interval.setRange(1, 9999)
        self.content_sample_interval.setValue(3)
        set_tip(self.content_sample_interval, "内容重复检测每隔多少帧取一次指纹。数值越小越准，但越慢。")
        self.content_sample_slider = self._make_slider(1, 9999, 3, self.content_sample_interval)

        layout.addWidget(QLabel("模式"), 0, 0)
        layout.addWidget(self.severity, 0, 1, 1, 2)
        layout.addWidget(QLabel("夹帧阈值/帧"), 1, 0)
        layout.addWidget(self.stuck_frames, 1, 1)
        layout.addWidget(self.stuck_slider, 1, 2)
        layout.addWidget(QLabel("可疑阈值/帧"), 2, 0)
        layout.addWidget(self.suspect_frames, 2, 1)
        layout.addWidget(self.suspect_slider, 2, 2)
        layout.addWidget(QLabel("黑场像素阈值"), 3, 0)
        layout.addWidget(self.pixel_threshold, 3, 1)
        layout.addWidget(self.pixel_slider, 3, 2)
        layout.addWidget(QLabel("最短黑帧/秒"), 4, 0)
        layout.addWidget(self.min_duration, 4, 1)
        layout.addWidget(self.min_duration_slider, 4, 2)
        layout.addWidget(QLabel("指纹采样/帧"), 5, 0)
        layout.addWidget(self.content_sample_interval, 5, 1)
        layout.addWidget(self.content_sample_slider, 5, 2)
        return box

    def _build_advanced_group(self) -> QGroupBox:
        box = QGroupBox("高级选项")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(10)

        self.chk_clear = self._check("检测前清理旧 BFD 标记", True, "只清理 [BFD] 前缀的旧标记，不删除用户手动标记。")
        self.chk_mark_hidden = self._check("标记隐藏/禁用素材", False, "默认跳过隐藏/禁用素材；开启后会把这类素材也作为问题打标。")
        self.chk_partial_opacity = self._check("标记半透明素材", True, "开启后不透明度低于 100% 的素材会被提示；用于排查意外透明。")
        self.chk_png_opaque = self._check("PNG/PSD 视为遮挡层", False, "多轨叠加检测时，把静态图层也当作上层遮挡，适合字幕贴纸很多的工程。")
        self.chk_merge = self._check("成片模式（合并分析）", True, "把时间线片段合并成连续流做 blackdetect，适合最终成片复查，通常更快。")
        self.chk_complex = self._check("复杂模式（渲染后分析）", False, "先渲染入出点范围，再分析最终画面。用于多轨、调色、OFX、Fusion、坏帧等普通逐文件模式看不到的问题。")
        self.chk_html = self._check("生成 HTML 报告", False, "检测完成后输出可阅读报告，适合发给协作者复核。")
        self.chk_auto_run = self._check("开始后自动触发 Lua", False, "写入参数后直接调用 fuscript 启动检测；如果失败，仍可手动在 Resolve 里运行脚本。")

        self.chk_complex.toggled.connect(self.on_complex_mode_changed)

        options = [
            self.chk_clear,
            self.chk_mark_hidden,
            self.chk_partial_opacity,
            self.chk_png_opaque,
            self.chk_merge,
            self.chk_complex,
            self.chk_html,
            self.chk_auto_run,
        ]
        for index, check in enumerate(options):
            layout.addWidget(check, index // 2, index % 2)

        self.complex_hint = QLabel("坏帧检测依赖复杂模式：需要入点和出点。")
        self.complex_hint.setObjectName("Muted")
        set_tip(self.complex_hint, "复杂模式会产生临时渲染文件，用最终画面做检测；这就是坏帧检测必须依赖它的原因。")
        layout.addWidget(self.complex_hint, 4, 0, 1, 2)
        return box

    def _build_action_group(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.progress_label = QLabel("待机")
        self.progress_label.setMinimumWidth(180)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")

        self.start_btn = QPushButton("开始检测")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        set_tip(self.start_btn, "提交当前参数。若勾选自动触发，会直接尝试让 Resolve 执行 Lua 检测。")
        self.start_btn.clicked.connect(self.start_detection)

        self.clear_markers_btn = QPushButton("清除标记")
        self.clear_markers_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        set_tip(self.clear_markers_btn, "清除当前时间线上的 [BFD] 检测标记，不会删除普通人工标记。")
        self.clear_markers_btn.clicked.connect(self.clear_markers)

        self.feedback_btn = QPushButton("反馈")
        self.feedback_btn.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        set_tip(self.feedback_btn, "打开反馈窗口；会附带最近调试日志，方便定位误报、漏报和环境问题。")
        self.feedback_btn.clicked.connect(self.open_feedback_dialog)

        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress, 1)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.clear_markers_btn)
        layout.addWidget(self.feedback_btn)
        return panel

    def _build_result_group(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QGridLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        items = [
            ("total", "总数", "所有已回传的问题数量。", "#35c4a1"),
            ("error", "夹帧", "红色标记，通常需要修复。", MARKER_COLORS["error"]),
            ("suspect", "可疑", "黄色标记，需要人工确认。", MARKER_COLORS["suspect"]),
            ("scene", "转场", "蓝色标记，通常是正常转场黑场。", MARKER_COLORS["scene"]),
            ("gap", "空位", "紫色标记，时间线片段间隙。", MARKER_COLORS["gap"]),
            ("duplicate", "重复", "重复素材或内容指纹重复。", MARKER_COLORS["duplicate"]),
            ("opacity", "透明", "透明度、禁用或合成问题。", MARKER_COLORS["opacity"]),
            ("corrupt", "坏帧", "复杂模式下 signalstats/熵分析发现的渲染异常。", MARKER_COLORS["corrupt"]),
        ]
        for index, (key, title, tip, color) in enumerate(items):
            card = QFrame()
            card.setObjectName("StatCard")
            card.setStyleSheet(
                "QFrame#StatCard {"
                "background: #121820; border: 1px solid #2a3440;"
                f"border-top: 3px solid {color}; border-radius: 6px;"
                "}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            value = QLabel("0")
            value.setFont(QFont("Microsoft YaHei", 17, QFont.Bold))
            name = QLabel(title)
            name.setObjectName("Muted")
            card_layout.addWidget(value)
            card_layout.addWidget(name)
            set_tip(card, tip)
            self.result_values[key] = value
            layout.addWidget(card, 0, index)
        return panel

    def _check(self, text: str, checked: bool, tooltip: str) -> QCheckBox:
        check = QCheckBox(text)
        check.setChecked(checked)
        set_tip(check, tooltip)
        return check

    def _marker_check(self, text: str, color_key: str, checked: bool, tooltip: str) -> QCheckBox:
        check = self._check(f"● {text}", checked, tooltip)
        color = MARKER_COLORS[color_key]
        check.setStyleSheet(
            "QCheckBox {"
            f"color: {color};"
            "font-weight: 700;"
            "}"
            "QCheckBox:disabled { color: #667481; }"
        )
        return check

    def _make_slider(self, minimum: int, maximum: int, value: int, spinbox: QSpinBox) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)
        set_tip(slider, spinbox.toolTip())
        return slider

    def _make_float_slider(
        self,
        minimum: int,
        maximum: int,
        value: int,
        spinbox: QDoubleSpinBox,
        scale: float,
    ) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(lambda raw: spinbox.setValue(raw / scale))
        spinbox.valueChanged.connect(
            lambda val: slider.setValue(max(minimum, min(maximum, int(round(val * scale)))))
        )
        set_tip(slider, spinbox.toolTip())
        return slider

    def refresh_timelines(self) -> None:
        self.timelines = self.bridge.list_timelines()
        self.timeline_combo.clear()
        for tl in self.timelines:
            self.timeline_combo.addItem(f"{tl.index}. {tl.name}  /  {tl.fps:g} fps", asdict(tl))

    def apply_severity(self) -> None:
        level = self.severity.currentText()
        if level == "短剧默认":
            self.stuck_frames.setValue(3)
            self.suspect_frames.setValue(12)
            self.pixel_threshold.setValue(0.010)
            self.min_duration.setValue(0.040)
        elif level == "严格排雷":
            self.stuck_frames.setValue(2)
            self.suspect_frames.setValue(8)
            self.pixel_threshold.setValue(0.008)
            self.min_duration.setValue(0.030)
        else:
            self.stuck_frames.setValue(1)
            self.suspect_frames.setValue(6)
            self.pixel_threshold.setValue(0.006)
            self.min_duration.setValue(0.020)

    def on_complex_mode_changed(self, checked: bool) -> None:
        self.chk_corrupt.setEnabled(bool(checked))
        if not checked:
            self.chk_corrupt.setChecked(False)
            self.complex_hint.setText("坏帧检测依赖复杂模式：需要入点和出点。")
        else:
            self.complex_hint.setText("复杂模式会先渲染入出点范围，再分析最终画面；坏帧检测现在可选。")

    def collect_params(self) -> dict:
        selected = self.timeline_combo.currentData() or {"index": 1, "name": "当前时间线", "fps": 24.0}
        complex_mode = self.chk_complex.isChecked()
        return {
            "timeline_index": int(selected.get("index", 1)),
            "timeline_name": str(selected.get("name", "当前时间线")).replace("  (当前)", ""),
            "timeline_fps": float(selected.get("fps", 24.0)),
            "severity": self.severity.currentText(),
            "stuck_frames": self.stuck_frames.value(),
            "suspect_frames": self.suspect_frames.value(),
            "pix_th": self.pixel_threshold.value(),
            "min_duration": self.min_duration.value(),
            "content_sample_interval": self.content_sample_interval.value(),
            "manual_io_in": self.io_in.text().strip(),
            "manual_io_out": self.io_out.text().strip(),
            "marker_types": {
                "error": self.chk_error.isChecked(),
                "suspect": self.chk_suspect.isChecked(),
                "scene": self.chk_scene.isChecked(),
                "gap": self.chk_gap.isChecked(),
                "opacity": self.chk_opacity.isChecked(),
                "duplicate": self.chk_duplicate.isChecked(),
                "content_dup": self.chk_content_dup.isChecked(),
            },
            "detect_duplicate": self.chk_duplicate.isChecked(),
            "detect_content_dup": self.chk_content_dup.isChecked(),
            "detect_corrupt": complex_mode and self.chk_corrupt.isChecked(),
            "html_report": self.chk_html.isChecked(),
            "clear_existing": self.chk_clear.isChecked(),
            "complex_mode": complex_mode,
            "merge_mode": self.chk_merge.isChecked(),
            "mark_hidden_clips": self.chk_mark_hidden.isChecked(),
            "mark_partial_opacity": self.chk_partial_opacity.isChecked(),
            "png_as_opaque": self.chk_png_opaque.isChecked(),
        }

    def start_detection(self) -> None:
        params = self.collect_params()
        if params["complex_mode"] and (not params["manual_io_in"] or not params["manual_io_out"]):
            QMessageBox.warning(self, "复杂模式需要入出点", "复杂模式会先渲染检测范围，请填写手动入点和出点。")
            return

        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress_label.setText("提交中")
        self._log("开始提交参数")
        self.progress_timer.start()
        self.worker = SubmitWorker(self.bridge, params, self.chk_auto_run.isChecked())
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def clear_markers(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        if QMessageBox.question(self, "清除标记", "只清除当前时间线上的 [BFD] 检测标记，继续吗？") != QMessageBox.Yes:
            return
        ok, message = self.bridge.clear_bfd_markers(int(selected.get("index", 1)))
        self._log(message)
        if ok:
            QMessageBox.information(self, "清除标记", message)
        else:
            QMessageBox.warning(self, "清除标记", message)

    def open_feedback_dialog(self) -> None:
        FeedbackDialog(self).exec()

    def on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.progress_label.setText(message[:20])
        self._log(message)

    def on_done(self, ok: bool, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress_label.setText("已提交" if ok else "失败")
        self._log(message)
        if ok:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "失败", message)

    def poll_detection_progress(self) -> None:
        progress = read_progress_file()
        if not progress:
            return
        percent = int(progress.get("percent", 0))
        stage = str(progress.get("stage", ""))
        state = str(progress.get("state", "running"))
        self.progress.setValue(max(0, min(100, percent)))
        self.progress_label.setText(stage[:20] if stage else state)
        self._update_result_cards(progress)
        if stage:
            self._log(f"检测进度 {percent}%：{stage}")
        if state in {"complete", "failed", "cancelled"} or percent >= 100:
            self.progress_timer.stop()

    def _update_result_cards(self, progress: dict) -> None:
        counts = progress.get("counts")
        if not isinstance(counts, dict):
            return
        for key, label in self.result_values.items():
            if key in counts:
                label.setText(str(counts[key]))

    def _log(self, message: str) -> None:
        self.log.append(message)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    if BRIDGE_WORKER_ARG in argv[1:]:
        return run_resolve_bridge_worker()

    app = QApplication(argv)
    font_family = install_cjk_font()
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont(font_family, 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
