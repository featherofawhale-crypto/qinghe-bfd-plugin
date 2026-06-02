from __future__ import annotations

import json
import math
import re
import sys
import time
import ctypes
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
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
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QGraphicsOpacityEffect,
    QProgressBar,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from resolve_bridge import BRIDGE_WORKER_ARG, ResolveBridge, TimelineInfo, read_progress_file, run_resolve_bridge_worker


APP_VERSION = "1.9.86"
FEEDBACK_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/c533d532-4041-4e58-abd5-6f9eb924d58c"

DEFAULT_STUCK_FRAMES = 3
DEFAULT_SUSPECT_FRAMES = 12
DEFAULT_MIN_BLACK_FRAMES = 1
BASELINE_FPS = 25.0
DEFAULT_PIXEL_THRESHOLD = 1.0
DEFAULT_CONTENT_SAMPLE_INTERVAL = 3
MAX_FRAME_THRESHOLD = 100
ICON_PATH = Path(__file__).resolve().with_name("icon.svg")
WINDOWS_APP_ID = "Qinghe.BFD.Control"


def set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


APP_STYLE = """
QToolTip {
    background: #111827;
    color: #f8fafc;
    border: 1px solid #94a3b8;
    padding: 8px;
    border-radius: 7px;
}
QWidget {
    background: #f6f8fb;
    color: #1f2937;
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI";
    font-size: 12px;
}
QLabel, QCheckBox, QSlider {
    background: transparent;
}
QMainWindow { background: #eef3f7; }
QFrame#Shell {
    background: #fbfcfe;
    border: 1px solid #d6e0ea;
    border-radius: 10px;
}
QFrame#Panel {
    background: #ffffff;
    border: 1px solid #d9e1ea;
    border-radius: 7px;
}
QFrame#StatCard {
    background: #fbfcfe;
    border: 1px solid #d8e0ea;
    border-top: 3px solid #f59e0b;
    border-radius: 7px;
}
QLabel#Title {
    font-size: 20px;
    font-weight: 700;
    color: #172033;
}
QLabel#Subtitle, QLabel#Muted { color: #64748b; }
QLabel#BadgeOk {
    color: #047857;
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
    border-radius: 7px;
    padding: 4px 9px;
    font-weight: 700;
}
QLabel#BadgeWarn {
    color: #92400e;
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 7px;
    padding: 4px 9px;
    font-weight: 700;
}
QGroupBox {
    border: 1px solid #d9e1ea;
    border-radius: 7px;
    margin-top: 17px;
    padding: 12px 10px 10px 10px;
    background: #ffffff;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #475569;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit {
    min-height: 29px;
    border-radius: 7px;
    border: 1px solid #cad5e2;
    background: #ffffff;
    color: #172033;
    padding: 3px 7px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #f59e0b;
}
QCheckBox { spacing: 8px; color: #253244; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid #94a3b8;
    background: #ffffff;
}
QCheckBox::indicator:checked { background: #f59e0b; border-color: #d97706; }
QCheckBox:disabled { color: #9aa8b7; }
QCheckBox#MarkerCheck { color: #253244; font-weight: 600; }
QPushButton {
    min-height: 29px;
    border-radius: 7px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
    color: #1f2937;
    padding: 4px 10px;
    font-weight: 700;
}
QPushButton:hover { background: #fff7ed; border-color: #f59e0b; }
QPushButton:pressed { background: #ffedd5; padding-top: 5px; padding-bottom: 3px; }
QPushButton#Primary {
    min-height: 36px;
    background: #f59e0b;
    border-color: #d97706;
    color: #111827;
}
QPushButton#Primary:hover { background: #fbbf24; }
QPushButton#Primary:pressed { background: #d97706; }
QPushButton#Primary:disabled { background: #ead4ad; color: #8a6b36; }
QTabWidget::pane {
    border: 1px solid #d9e1ea;
    border-radius: 8px;
    background: #ffffff;
}
QTabBar::tab {
    min-width: 64px;
    min-height: 26px;
    padding: 4px 10px;
    margin-right: 4px;
    border: 1px solid #d9e1ea;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    background: #eef2f7;
    color: #526175;
    font-weight: 700;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #d97706;
    border-top: 2px solid #2563eb;
}
QProgressBar {
    min-height: 14px;
    border-radius: 7px;
    background: #e6edf5;
    border: 1px solid #cfd8e3;
    text-align: center;
    color: #22364f;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: #f59e0b;
}
QSlider::groove:horizontal {
    height: 6px;
    border-radius: 3px;
    background: #d9e2ec;
}
QSlider::sub-page:horizontal {
    border-radius: 3px;
    background: #2563eb;
}
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: #ffffff;
    border: 1px solid #d97706;
}
QTextEdit {
    background: #ffffff;
    border: 1px solid #d9e1ea;
    border-radius: 7px;
    color: #31445d;
    padding: 6px;
}
"""


MARKER_COLORS = {
    "error": "#B42318",
    "suspect": "#A16207",
    "scene": "#2563EB",
    "gap": "#6D5BD0",
    "duplicate": "#B83280",
    "content_dup": "#8F3F71",
    "opacity": "#047857",
    "corrupt": "#0369A1",
    "audio": "#0F766E",
}


def settings_path() -> Path:
    return Path.home() / ".qinghe_bfd" / "ui_settings.json"


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

    def __init__(self, bridge: ResolveBridge, jobs: dict | list[dict]) -> None:
        super().__init__()
        self.bridge = bridge
        self.jobs = jobs if isinstance(jobs, list) else [jobs]

    def run(self) -> None:
        total = len(self.jobs)
        messages: list[str] = []
        for index, params in enumerate(self.jobs, 1):
            timeline_name = str(params.get("timeline_name", f"时间线 {index}"))
            base = int(((index - 1) / max(1, total)) * 90)
            self.progress.emit(base + 8, f"准备 {timeline_name}")
            time.sleep(0.12)
            params_path = self.bridge.submit_params(params)
            self.progress.emit(base + 25, f"打开时间线：{timeline_name}")
            if self.bridge.is_connected():
                ok, message = self.bridge.activate_timeline(int(params.get("timeline_index", 1)))
                if not ok:
                    self.done.emit(False, f"{timeline_name} 打开失败：{message}")
                    return
            else:
                self.bridge.open_resolve_page()
            self.progress.emit(base + 48, f"检测 {timeline_name}")
            ok, message = self.bridge.run_lua_entry_with_fuscript(params_path)
            if not ok:
                self.done.emit(False, f"{timeline_name} 检测启动失败：{message}")
                return
            messages.append(f"{timeline_name}: {message or '已完成'}")
        self.progress.emit(100, "检测已提交")
        self.done.emit(True, "\n".join(messages) if messages else "检测已提交。")


class ResultTextEdit(QTextEdit):
    rowDoubleClicked = Signal(int)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        cursor = self.cursorForPosition(point)
        self.setTextCursor(cursor)
        self.rowDoubleClicked.emit(cursor.blockNumber())
        event.accept()


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
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(960, 660)
        self.bridge = ResolveBridge()
        self.timelines: list[TimelineInfo] = []
        self.worker: SubmitWorker | None = None
        self.result_values: dict[str, QLabel] = {}
        self.result_records: list[dict] = []
        self.result_index = 0
        self.text_records: list[dict] = []
        self.text_index = -1
        self._zero_result_notice_shown = False
        self._marker_refresh_after_complete = False
        self._tab_animation: QPropertyAnimation | None = None
        self._active_animations: list[QPropertyAnimation] = []
        self._loading_timelines = False
        self._loading_settings = False
        self._control_fps = BASELINE_FPS
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(700)
        self.progress_timer.timeout.connect(self.poll_detection_progress)

        shell = QFrame()
        shell.setObjectName("Shell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        root.addLayout(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(9)

        controls = QVBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self._build_timeline_group())

        main_grid = QGridLayout()
        main_grid.setHorizontalSpacing(9)
        main_grid.setVerticalSpacing(8)
        main_grid.addWidget(self._build_detection_group(), 0, 0)
        main_grid.addWidget(self._build_threshold_group(), 0, 1)
        main_grid.addWidget(self._build_advanced_group(), 1, 0, 1, 2)
        controls.addLayout(main_grid)
        controls.addWidget(self._build_action_group())
        controls.addStretch(1)

        body.addLayout(controls, 2)
        body.addWidget(self._build_side_tabs(), 1)
        root.addLayout(body, 1)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(8, 8, 8, 8)
        wrapper_layout.addWidget(shell)
        self.setCentralWidget(wrapper)
        self.install_button_motion()

        self.refresh_timelines()
        self.load_settings()
        self.update_fps_hint()
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
        set_tip(self.connection_badge, "已连接表示控制台能读到当前 Resolve 工程；离线时仍可保存参数，稍后由检测引擎读取。")

        layout.addLayout(title_box, 1)
        layout.addWidget(self.connection_badge)
        return layout

    def _build_timeline_group(self) -> QGroupBox:
        box = QGroupBox("时间线")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(9)
        layout.setVerticalSpacing(8)

        self.timeline_combo = QComboBox()
        set_tip(self.timeline_combo, "选择要检测的 Resolve 时间线；默认会优先当前打开的时间线。")
        self.timeline_combo.currentIndexChanged.connect(self.on_timeline_changed)
        refresh = QPushButton("刷新")
        refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        set_tip(refresh, "重新读取 DaVinci Resolve 当前工程内的时间线列表。")
        refresh.clicked.connect(self.refresh_timelines)
        self.read_marks_btn = QPushButton("读取入出点")
        self.read_marks_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        set_tip(self.read_marks_btn, "读取 Resolve 当前时间线的入点/出点，自动填入复杂模式需要的检测范围。")
        self.read_marks_btn.clicked.connect(self.fill_in_out_from_current_timeline_marks)

        self.io_in = QLineEdit()
        self.io_in.setPlaceholderText("可选，例如 01:00:00:00")
        set_tip(self.io_in, "限制检测起点。复杂模式必须填写入点，因为它会先渲染指定范围再分析。")
        self.io_out = QLineEdit()
        self.io_out.setPlaceholderText("可选，例如 01:02:30:00")
        set_tip(self.io_out, "限制检测终点。复杂模式必须填写出点，避免渲染整条时间线导致过慢。")

        self.chk_batch_timelines = QCheckBox("批量检测时间线")
        set_tip(self.chk_batch_timelines, "批量检测：勾选后可以选择多条时间线。开始检测会按列表顺序让 Resolve 自动切到每条时间线并写入对应标记。")
        self.chk_batch_timelines.toggled.connect(self.on_batch_toggled)

        self.batch_timeline_list = QListWidget()
        self.batch_timeline_list.setMinimumHeight(58)
        self.batch_timeline_list.setMaximumHeight(92)
        self.batch_timeline_list.setEnabled(False)
        set_tip(self.batch_timeline_list, "勾选要批量检测的时间线；每条时间线会使用自己的帧率换算阈值。")

        layout.addWidget(QLabel("目标时间线"), 0, 0)
        layout.addWidget(self.timeline_combo, 0, 1, 1, 3)
        layout.addWidget(refresh, 0, 4)
        layout.addWidget(QLabel("手动入点"), 1, 0)
        layout.addWidget(self.io_in, 1, 1)
        layout.addWidget(QLabel("手动出点"), 1, 2)
        layout.addWidget(self.io_out, 1, 3)
        layout.addWidget(self.read_marks_btn, 1, 4)
        layout.addWidget(self.chk_batch_timelines, 2, 0)
        layout.addWidget(self.batch_timeline_list, 2, 1, 1, 4)
        return box

    def _build_detection_group(self) -> QGroupBox:
        box = QGroupBox("检测与标记")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)

        self.chk_error = self._marker_check("夹帧错误", "error", True, "片段或黑场持续帧数小于等于夹帧阈值，会打红色 [BFD-ERR] 标记。")
        self.chk_suspect = self._marker_check("可疑黑帧", "suspect", True, "黑场超过夹帧阈值但不超过可疑阈值，会打黄色 [BFD-SUS] 标记，建议人工确认。")
        self.chk_scene = self._marker_check("转场黑场", "scene", False, "超过可疑阈值的黑场更像正常转场，默认不标，避免时间线太乱。")
        self.chk_gap = self._marker_check("时间线空位", "gap", True, "检测片段之间的空洞，适合找不小心漏剪出的空白。")
        self.chk_duplicate = self._marker_check("重复素材", "duplicate", True, "按源文件、轨道距离和时间距离找近距/远距重复，适合发布会多机位、纪录片素材误复制排查。")
        self.chk_content_dup = self._marker_check("内容重复", "content_dup", False, "用帧指纹比较画面内容，可找不同文件但画面重复的片段，耗时会增加。")
        self.chk_opacity = self._marker_check("透明度/禁用", "opacity", True, "直接读取时间线属性，找不透明度为 0、低透明、禁用和非标准合成。")
        self.chk_corrupt = self._marker_check("渲染坏帧", "corrupt", False, "必须先开启复杂模式：坏帧检测依赖渲染后的最终像素，再用 signalstats/熵/亮度离群分析。")
        self.chk_corrupt.toggled.connect(self.on_corrupt_toggled)

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
        layout.setHorizontalSpacing(9)
        layout.setVerticalSpacing(8)

        self.stuck_frames = QSpinBox()
        self.stuck_frames.setRange(1, MAX_FRAME_THRESHOLD)
        self.stuck_frames.setValue(DEFAULT_STUCK_FRAMES)
        set_tip(self.stuck_frames, "按帧判断硬错误。25fps 默认 3 帧；切到 60fps 会按时长自动换算到约 8 帧，避免高帧率下误判。")
        self.stuck_slider = self._make_slider(1, MAX_FRAME_THRESHOLD, DEFAULT_STUCK_FRAMES, self.stuck_frames)

        self.suspect_frames = QSpinBox()
        self.suspect_frames.setRange(1, MAX_FRAME_THRESHOLD)
        self.suspect_frames.setValue(DEFAULT_SUSPECT_FRAMES)
        set_tip(self.suspect_frames, "按帧判断可疑黑场。大于夹帧阈值且小于等于此值会标为可疑；更长的黑场通常是转场或正常段落。")
        self.suspect_slider = self._make_slider(1, MAX_FRAME_THRESHOLD, DEFAULT_SUSPECT_FRAMES, self.suspect_frames)

        self.pixel_threshold = QDoubleSpinBox()
        self.pixel_threshold.setRange(0.1, 100.0)
        self.pixel_threshold.setSingleStep(0.1)
        self.pixel_threshold.setDecimals(1)
        self.pixel_threshold.setSuffix("%")
        self.pixel_threshold.setValue(DEFAULT_PIXEL_THRESHOLD)
        set_tip(self.pixel_threshold, "黑色亮度容差。1% 表示只有接近纯黑的像素才算黑；发布会投影或暗场素材可提高到 2%-4%。")
        self.pixel_slider = self._make_float_slider(1, 1000, 10, self.pixel_threshold, 10.0)

        self.min_black_frames = QSpinBox()
        self.min_black_frames.setRange(1, MAX_FRAME_THRESHOLD)
        self.min_black_frames.setValue(DEFAULT_MIN_BLACK_FRAMES)
        set_tip(self.min_black_frames, "FFmpeg 黑场 d 参数按实际时间线帧率换算成秒；控件始终显示当前时间线帧数。")
        self.min_black_slider = self._make_slider(1, MAX_FRAME_THRESHOLD, DEFAULT_MIN_BLACK_FRAMES, self.min_black_frames)

        self.content_sample_interval = QSpinBox()
        self.content_sample_interval.setRange(1, MAX_FRAME_THRESHOLD)
        self.content_sample_interval.setValue(DEFAULT_CONTENT_SAMPLE_INTERVAL)
        set_tip(self.content_sample_interval, "内容重复检测每隔多少帧取一次指纹。数值越小越准，但越慢。")
        self.content_sample_slider = self._make_slider(
            1, MAX_FRAME_THRESHOLD, DEFAULT_CONTENT_SAMPLE_INTERVAL, self.content_sample_interval
        )

        self.reset_thresholds_btn = QPushButton("还原默认")
        self.reset_thresholds_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        set_tip(self.reset_thresholds_btn, "恢复默认阈值：夹帧 3 帧、可疑 12 帧、最短黑场 1 帧、黑色阈值 1%、指纹采样 3 帧。")
        self.reset_thresholds_btn.clicked.connect(self.reset_threshold_defaults)

        layout.addWidget(QLabel("夹帧阈值/帧"), 0, 0)
        layout.addWidget(self.stuck_frames, 0, 1)
        layout.addWidget(self.stuck_slider, 0, 2)
        layout.addWidget(QLabel("可疑阈值/帧"), 1, 0)
        layout.addWidget(self.suspect_frames, 1, 1)
        layout.addWidget(self.suspect_slider, 1, 2)
        layout.addWidget(QLabel("黑场像素阈值"), 2, 0)
        layout.addWidget(self.pixel_threshold, 2, 1)
        layout.addWidget(self.pixel_slider, 2, 2)
        layout.addWidget(QLabel("最短黑场/帧"), 3, 0)
        layout.addWidget(self.min_black_frames, 3, 1)
        layout.addWidget(self.min_black_slider, 3, 2)
        layout.addWidget(QLabel("指纹采样/帧"), 4, 0)
        layout.addWidget(self.content_sample_interval, 4, 1)
        layout.addWidget(self.content_sample_slider, 4, 2)
        layout.addWidget(self.reset_thresholds_btn, 5, 0, 1, 3)
        self.fps_hint = QLabel("当前按 25fps 基准换算。")
        self.fps_hint.setObjectName("Muted")
        set_tip(self.fps_hint, "所有帧数阈值都会按当前时间线帧率换算；你看到和修改的始终是当前时间线下的帧数。")
        layout.addWidget(self.fps_hint, 6, 0, 1, 3)
        for widget in [self.stuck_frames, self.suspect_frames, self.min_black_frames]:
            widget.valueChanged.connect(lambda _value: self.update_fps_hint())
        return box

    def _build_advanced_group(self) -> QGroupBox:
        box = QGroupBox("高级选项")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)

        self.chk_clear = self._check("检测前清理旧 BFD 标记", True, "只清理 [BFD] 前缀的旧标记，不删除用户手动标记。")
        self.chk_mark_hidden = self._check("标记隐藏/禁用素材", False, "默认跳过隐藏/禁用素材；开启后会把这类素材也作为问题打标。")
        self.chk_partial_opacity = self._check("标记半透明素材", True, "开启后不透明度低于 100% 的素材会被提示；用于排查意外透明。")
        self.chk_png_opaque = self._check("PNG/PSD 视为遮挡层", False, "多轨叠加检测时，把静态图层也当作上层遮挡，适合字幕贴纸很多的工程。")
        self.chk_merge = self._check("成片模式（合并分析）", True, "把时间线片段合并成连续流做 blackdetect，适合最终成片复查，通常更快。")
        self.chk_complex = self._check("复杂模式（渲染后分析）", False, "先渲染入出点范围，再分析最终画面。调色/OFX/Fusion/叠加后的最终像素异常需要它；混剪夹帧和时间线结构检测不需要。")
        self.chk_html = self._check("生成 HTML 报告", False, "检测完成后输出可阅读报告，适合发给协作者复核。")

        self.chk_complex.toggled.connect(self.on_complex_mode_changed)

        options = [
            self.chk_clear,
            self.chk_mark_hidden,
            self.chk_partial_opacity,
            self.chk_png_opaque,
            self.chk_merge,
            self.chk_complex,
            self.chk_html,
        ]
        for index, check in enumerate(options):
            layout.addWidget(check, index // 2, index % 2)

        self.complex_hint = QLabel("坏帧检测依赖复杂模式：需要入点和出点。")
        self.complex_hint.setObjectName("Muted")
        set_tip(self.complex_hint, "复杂模式会产生临时渲染文件，用最终画面做检测；调色后的坏帧要看最终像素，所以必须依赖它。")
        layout.addWidget(self.complex_hint, 4, 0, 1, 2)
        return box

    def _build_action_group(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.progress_label = QLabel("待机")
        self.progress_label.setMinimumWidth(138)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")

        self.start_btn = QPushButton("开始检测")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        set_tip(self.start_btn, "按当前设置开始检测。单条时间线会直接检测；勾选批量后会按列表顺序逐条检测并写入 Resolve 标记。")
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

    def _build_side_tabs(self) -> QTabWidget:
        self.side_tabs = QTabWidget()
        self.side_tabs.setObjectName("SideTabs")
        self.results_tab = self._build_results_tab()
        self.audio_tab = self._build_audio_tab()
        self.text_tab = self._build_text_tab()
        self.log_tab = self._build_log_tab()
        self.side_tabs.addTab(self.results_tab, "结果")
        self.side_tabs.addTab(self.audio_tab, "音频")
        self.side_tabs.addTab(self.log_tab, "日志")
        self.side_tabs.addTab(self.text_tab, "文字")
        self.side_tabs.setCurrentWidget(self.results_tab)
        self.side_tabs.currentChanged.connect(self.animate_current_tab)
        set_tip(self.side_tabs, "结果、音频扫描和执行日志会一直留在主界面右侧，检测完成后自动回到结果页。")
        return self.side_tabs

    def _build_results_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_result_group())
        self.result_list = ResultTextEdit()
        self.result_list.setReadOnly(True)
        self.result_list.setMinimumHeight(190)
        self.result_list.setPlaceholderText("检测完成后，这里会显示所有问题、颜色标签、时间码和跳转顺序。")
        set_tip(self.result_list, "结果按时间线顺序显示；颜色名对应 Resolve 时间线标记颜色。")
        self.result_list.rowDoubleClicked.connect(self.jump_to_result_row)
        layout.addWidget(self.result_list, 1)

        nav = QHBoxLayout()
        self.prev_result_btn = QPushButton("上一条")
        self.prev_result_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.next_result_btn = QPushButton("下一条")
        self.next_result_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.result_position_label = QLabel("0 / 0")
        self.result_position_label.setObjectName("Muted")
        self.refresh_results_btn = QPushButton("刷新标记")
        self.refresh_results_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        set_tip(self.refresh_results_btn, "从当前 Resolve 时间线重新读取 [BFD] 标记，并显示到结果列表。")
        set_tip(self.prev_result_btn, "定位到上一条结果，配合 Resolve 标记快捷键复核。")
        set_tip(self.next_result_btn, "定位到下一条结果，配合 Resolve 标记快捷键复核。")
        self.prev_result_btn.clicked.connect(lambda: self.move_result_cursor(-1))
        self.next_result_btn.clicked.connect(lambda: self.move_result_cursor(1))
        self.refresh_results_btn.clicked.connect(self.refresh_results_from_markers)
        nav.addWidget(self.prev_result_btn)
        nav.addWidget(self.next_result_btn)
        nav.addWidget(self.refresh_results_btn)
        nav.addWidget(self.result_position_label)
        nav.addStretch(1)
        layout.addLayout(nav)
        return tab

    def _build_text_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        self.text_search = QLineEdit()
        self.text_search.setPlaceholderText("搜索 SRT / 字幕 / 文字层")
        self.text_scan_btn = QPushButton("查找")
        self.text_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.text_scan_btn.clicked.connect(self.scan_text_layers)
        self.text_search.returnPressed.connect(self.scan_text_layers)
        search_row.addWidget(self.text_search, 1)
        search_row.addWidget(self.text_scan_btn)
        layout.addLayout(search_row)

        self.text_list = QListWidget()
        self.text_list.setMinimumHeight(180)
        self.text_list.itemDoubleClicked.connect(self.jump_to_selected_text_item)
        layout.addWidget(self.text_list, 1)

        edit_row = QHBoxLayout()
        self.text_replace = QLineEdit()
        self.text_replace.setPlaceholderText("替换为")
        self.text_replace_btn = QPushButton("替换")
        self.text_replace_btn.clicked.connect(self.replace_selected_text_item)
        self.text_delete_btn = QPushButton("删除")
        self.text_delete_btn.clicked.connect(self.delete_selected_text_item)
        self.text_filler_btn = QPushButton("去语气词")
        self.text_filler_btn.clicked.connect(self.remove_fillers_from_selected_text_item)
        edit_row.addWidget(self.text_replace, 1)
        edit_row.addWidget(self.text_replace_btn)
        edit_row.addWidget(self.text_filler_btn)
        edit_row.addWidget(self.text_delete_btn)
        layout.addLayout(edit_row)

        self.text_status = QLabel("未扫描文字层。")
        self.text_status.setObjectName("Muted")
        layout.addWidget(self.text_status)
        return tab

    def _build_audio_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.audio_summary = QLabel("未扫描音频。")
        self.audio_summary.setObjectName("Muted")
        self.audio_summary.setWordWrap(True)
        self.audio_summary.setMaximumHeight(48)
        self.audio_summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        set_tip(self.audio_summary, "扫描会读取音频轨道类型和片段源声道映射，识别 mono 音轨或 mono 素材。")
        layout.addWidget(self.audio_summary)

        actions = QHBoxLayout()
        self.scan_audio_btn = QPushButton("扫描单声道")
        self.scan_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        set_tip(self.scan_audio_btn, "只读取时间线并列出单声道轨道/片段，不修改工程。")
        self.scan_audio_btn.clicked.connect(self.scan_mono_audio)

        self.mark_audio_btn = QPushButton("标记单声道")
        self.mark_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        set_tip(self.mark_audio_btn, "把识别出的单声道音频片段改为醒目的 Orange 颜色，便于人工复核。")
        self.mark_audio_btn.clicked.connect(self.mark_mono_audio)

        self.fix_audio_btn = QPushButton("修正声道映射")
        self.fix_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_DriveHDIcon))
        set_tip(self.fix_audio_btn, "尝试把片段源声道映射写回 stereo；如果 Resolve 拒绝该接口，会保留标记和报告，避免误报已修复。")
        self.fix_audio_btn.clicked.connect(self.fix_mono_audio)
        actions.addWidget(self.scan_audio_btn)
        actions.addWidget(self.mark_audio_btn)
        actions.addWidget(self.fix_audio_btn)
        layout.addLayout(actions)

        self.audio_list = QTextEdit()
        self.audio_list.setReadOnly(True)
        self.audio_list.setMinimumHeight(230)
        self.audio_list.setMaximumHeight(230)
        self.audio_list.setLineWrapMode(QTextEdit.WidgetWidth)
        self.audio_list.setPlaceholderText("扫描结果会列出轨道、片段、起止帧和识别原因。")
        set_tip(self.audio_list, "单声道识别依据：音轨 subtype=mono、源文件 embedded_audio_channels=1、或 source channel mapping 为 mono。")
        layout.addWidget(self.audio_list, 1)
        return tab

    def _build_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(300)
        set_tip(self.log, "这里显示参数提交、Resolve 执行和进度文件回传的信息。")
        layout.addWidget(self.log)
        return tab

    def _build_result_group(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QGridLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(7)
        layout.setVerticalSpacing(7)

        items = [
            ("total", "总数", "所有已回传的问题数量。", "#35c4a1"),
            ("error", "夹帧", "红色标记，通常需要修复。", MARKER_COLORS["error"]),
            ("suspect", "可疑", "黄色标记，需要人工确认。", MARKER_COLORS["suspect"]),
            ("scene", "转场", "蓝色标记，通常是正常转场黑场。", MARKER_COLORS["scene"]),
            ("gap", "空位", "紫色标记，时间线片段间隙。", MARKER_COLORS["gap"]),
            ("duplicate", "重复", "重复素材或内容指纹重复。", MARKER_COLORS["duplicate"]),
            ("content_dup", "指纹", "不同文件或跨片段的画面指纹重复。", MARKER_COLORS["content_dup"]),
            ("opacity", "透明", "透明度、禁用或合成问题。", MARKER_COLORS["opacity"]),
            ("corrupt", "坏帧", "复杂模式下 signalstats/熵分析发现的渲染异常。", MARKER_COLORS["corrupt"]),
        ]
        for index, (key, title, tip, color) in enumerate(items):
            card = QFrame()
            card.setObjectName("StatCard")
            card.setStyleSheet(
                "QFrame#StatCard {"
                "background: #fbfcfe; border: 1px solid #d8e0ea;"
                f"border-top: 3px solid {color}; border-radius: 7px;"
                "}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            value = QLabel("0")
            value.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
            name = QLabel(title)
            name.setObjectName("Muted")
            card_layout.addWidget(value)
            card_layout.addWidget(name)
            set_tip(card, tip)
            self.result_values[key] = value
            layout.addWidget(card, index // 2, index % 2)
        return panel

    def _check(self, text: str, checked: bool, tooltip: str) -> QCheckBox:
        check = QCheckBox(text)
        check.setChecked(checked)
        set_tip(check, tooltip)
        return check

    def _marker_check(self, text: str, color_key: str, checked: bool, tooltip: str) -> QCheckBox:
        check = self._check(text, checked, tooltip)
        check.setObjectName("MarkerCheck")
        check.setProperty("markerRole", color_key)
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
        self._loading_timelines = True
        self.timelines = self.bridge.list_timelines()
        self.timeline_combo.clear()
        self.batch_timeline_list.clear()
        for tl in self.timelines:
            data = asdict(tl)
            label = f"{tl.index}. {tl.name}  /  {tl.fps:g} fps"
            self.timeline_combo.addItem(label, data)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, data)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if "当前" in tl.name else Qt.Unchecked)
            self.batch_timeline_list.addItem(item)
        self.connection_badge.setText("已连接" if self.bridge.is_connected() else "离线参数")
        self.connection_badge.setObjectName("BadgeOk" if self.bridge.is_connected() else "BadgeWarn")
        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)
        if self.batch_timeline_list.count() > 0 and not any(
            self.batch_timeline_list.item(i).checkState() == Qt.Checked for i in range(self.batch_timeline_list.count())
        ):
            self.batch_timeline_list.item(0).setCheckState(Qt.Checked)
        self._loading_timelines = False
        self._rescale_threshold_controls(self._control_fps, self.selected_fps())
        self.update_fps_hint()

    def on_timeline_changed(self) -> None:
        if self._loading_timelines or self._loading_settings:
            return
        self._rescale_threshold_controls(self._control_fps, self.selected_fps())
        self.update_fps_hint()

    def on_batch_toggled(self, checked: bool) -> None:
        self.batch_timeline_list.setEnabled(checked)

    def selected_timeline_data(self) -> dict:
        return self.timeline_combo.currentData() or {"index": 1, "name": "当前时间线", "fps": 25.0}

    def selected_fps(self) -> float:
        selected = self.selected_timeline_data()
        try:
            return float(selected.get("fps", 25.0))
        except Exception:
            return 25.0

    @staticmethod
    def scaled_frames(base_frames_at_25fps: int, fps: float) -> int:
        return max(1, int(math.ceil(base_frames_at_25fps * float(fps or BASELINE_FPS) / BASELINE_FPS)))

    def _frames_between_fps(self, frames: int, source_fps: float, target_fps: float) -> int:
        source = max(1.0, float(source_fps or BASELINE_FPS))
        base_frames = max(1, int(round(frames * BASELINE_FPS / source)))
        return self.scaled_frames(base_frames, target_fps)

    def _rescale_threshold_controls(self, source_fps: float, target_fps: float) -> None:
        target = max(1.0, float(target_fps or BASELINE_FPS))
        source = max(1.0, float(source_fps or BASELINE_FPS))
        if abs(target - source) < 0.001:
            self._control_fps = target
            return
        for widget in (self.stuck_frames, self.suspect_frames, self.min_black_frames):
            widget.blockSignals(True)
            widget.setValue(self._frames_between_fps(widget.value(), source, target))
            widget.blockSignals(False)
        self._control_fps = target

    def frames_for_timeline(self, current_frames: int, target_fps: float) -> int:
        source_fps = max(1.0, float(getattr(self, "_control_fps", self.selected_fps()) or BASELINE_FPS))
        if abs(float(target_fps or BASELINE_FPS) - source_fps) < 0.001:
            return current_frames
        return self._frames_between_fps(current_frames, source_fps, target_fps)

    def min_duration_seconds(self, fps: float | None = None) -> float:
        fps = fps or self.selected_fps()
        return self.min_black_frames.value() / max(1.0, float(fps))

    def update_fps_hint(self) -> None:
        if not hasattr(self, "fps_hint"):
            return
        fps = self.selected_fps()
        self.fps_hint.setText(
            f"当前 {fps:g}fps：夹帧≤{self.stuck_frames.value()}帧，可疑≤{self.suspect_frames.value()}帧，"
            f"最短黑场 {self.min_black_frames.value()}帧≈{self.min_duration_seconds(fps):.3f}秒。"
        )

    def selected_batch_timelines(self) -> list[dict]:
        if not self.chk_batch_timelines.isChecked():
            return [self.selected_timeline_data()]
        selected: list[dict] = []
        for index in range(self.batch_timeline_list.count()):
            item = self.batch_timeline_list.item(index)
            if item.checkState() == Qt.Checked:
                data = item.data(Qt.UserRole)
                if isinstance(data, dict):
                    selected.append(data)
        return selected or [self.selected_timeline_data()]

    def save_settings(self) -> None:
        data = {
            "timeline_index": self.timeline_combo.currentIndex(),
            "stuck_frames": self.stuck_frames.value(),
            "suspect_frames": self.suspect_frames.value(),
            "pix_th": self.pixel_threshold.value(),
            "pix_th_unit": "percent",
            "min_black_frames": self.min_black_frames.value(),
            "content_sample_interval": self.content_sample_interval.value(),
            "batch_enabled": self.chk_batch_timelines.isChecked(),
            "batch_timeline_indices": [
                int((self.batch_timeline_list.item(i).data(Qt.UserRole) or {}).get("index", 0))
                for i in range(self.batch_timeline_list.count())
                if self.batch_timeline_list.item(i).checkState() == Qt.Checked
            ],
            "checks": {
                "error": self.chk_error.isChecked(),
                "suspect": self.chk_suspect.isChecked(),
                "scene": self.chk_scene.isChecked(),
                "gap": self.chk_gap.isChecked(),
                "duplicate": self.chk_duplicate.isChecked(),
                "content_dup": self.chk_content_dup.isChecked(),
                "opacity": self.chk_opacity.isChecked(),
                "corrupt": self.chk_corrupt.isChecked(),
                "clear": self.chk_clear.isChecked(),
                "mark_hidden": self.chk_mark_hidden.isChecked(),
                "partial_opacity": self.chk_partial_opacity.isChecked(),
                "png_opaque": self.chk_png_opaque.isChecked(),
                "merge": self.chk_merge.isChecked(),
                "html": self.chk_html.isChecked(),
            },
        }
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_settings(self) -> None:
        path = settings_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._log(f"设置缓存读取失败：{exc}")
            return

        self._loading_settings = True
        try:
            if isinstance(data.get("timeline_index"), int) and self.timeline_combo.count() > 0:
                self.timeline_combo.setCurrentIndex(max(0, min(self.timeline_combo.count() - 1, data["timeline_index"])))
            for name, widget in [
                ("stuck_frames", self.stuck_frames),
                ("suspect_frames", self.suspect_frames),
                ("min_black_frames", self.min_black_frames),
                ("content_sample_interval", self.content_sample_interval),
            ]:
                if isinstance(data.get(name), int):
                    widget.setValue(data[name])
            if "min_black_frames" not in data and isinstance(data.get("min_duration"), (int, float)):
                self.min_black_frames.setValue(max(1, int(math.ceil(float(data["min_duration"]) * self.selected_fps()))))
            for name, widget in [
                ("pix_th", self.pixel_threshold),
            ]:
                if isinstance(data.get(name), (int, float)):
                    value = float(data[name])
                    if name == "pix_th" and data.get("pix_th_unit") != "percent" and value < 1.0:
                        value *= 100.0
                    widget.setValue(value)

            checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
            check_map = {
                "error": self.chk_error,
                "suspect": self.chk_suspect,
                "scene": self.chk_scene,
                "gap": self.chk_gap,
                "duplicate": self.chk_duplicate,
                "content_dup": self.chk_content_dup,
                "opacity": self.chk_opacity,
                "clear": self.chk_clear,
                "mark_hidden": self.chk_mark_hidden,
                "partial_opacity": self.chk_partial_opacity,
                "png_opaque": self.chk_png_opaque,
                "merge": self.chk_merge,
                "html": self.chk_html,
            }
            for key, widget in check_map.items():
                if isinstance(checks.get(key), bool):
                    widget.setChecked(checks[key])
            if isinstance(checks.get("corrupt"), bool) and self.chk_complex.isChecked():
                self.chk_corrupt.setChecked(checks["corrupt"])
            self.chk_batch_timelines.setChecked(bool(data.get("batch_enabled", False)))
            batch_indices = data.get("batch_timeline_indices")
            if isinstance(batch_indices, list):
                selected = {int(value) for value in batch_indices if isinstance(value, int)}
                for index in range(self.batch_timeline_list.count()):
                    item = self.batch_timeline_list.item(index)
                    item_data = item.data(Qt.UserRole) or {}
                    item.setCheckState(Qt.Checked if int(item_data.get("index", 0)) in selected else Qt.Unchecked)
        finally:
            self._loading_settings = False
            self.update_fps_hint()

    def reset_threshold_defaults(self) -> None:
        fps = self.selected_fps()
        self.stuck_frames.setValue(self.scaled_frames(DEFAULT_STUCK_FRAMES, fps))
        self.suspect_frames.setValue(self.scaled_frames(DEFAULT_SUSPECT_FRAMES, fps))
        self.min_black_frames.setValue(self.scaled_frames(DEFAULT_MIN_BLACK_FRAMES, fps))
        self._control_fps = fps
        self.pixel_threshold.setValue(DEFAULT_PIXEL_THRESHOLD)
        self.content_sample_interval.setValue(DEFAULT_CONTENT_SAMPLE_INTERVAL)
        self.update_fps_hint()

    def on_complex_mode_changed(self, checked: bool) -> None:
        if not checked:
            self.chk_corrupt.setChecked(False)
            self.complex_hint.setText("坏帧检测依赖复杂模式：需要入点和出点。")
        else:
            self.complex_hint.setText("复杂模式会先渲染入出点范围，再分析最终画面；调色/OFX/Fusion 后的坏帧检测现在可选。")

    def on_corrupt_toggled(self, checked: bool) -> None:
        if not checked or self.chk_complex.isChecked():
            return
        answer = QMessageBox.question(
            self,
            "开启复杂模式",
            "渲染坏帧检测必须先开启复杂模式并填写入出点。是否自动勾选复杂模式？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.chk_complex.setChecked(True)
        else:
            self.chk_corrupt.setChecked(False)

    def collect_params(self, selected: dict | None = None) -> dict:
        selected = selected or self.selected_timeline_data()
        complex_mode = self.chk_complex.isChecked()
        timeline_fps = float(selected.get("fps", 25.0))
        return {
            "timeline_index": int(selected.get("index", 1)),
            "timeline_name": str(selected.get("name", "当前时间线")).replace("  (当前)", ""),
            "timeline_fps": timeline_fps,
            "severity": "默认阈值",
            "stuck_frames": self.frames_for_timeline(self.stuck_frames.value(), timeline_fps),
            "suspect_frames": self.frames_for_timeline(self.suspect_frames.value(), timeline_fps),
            "pix_th": self.pixel_threshold.value() / 100.0,
            "min_black_frames": self.frames_for_timeline(self.min_black_frames.value(), timeline_fps),
            "min_duration": self.frames_for_timeline(self.min_black_frames.value(), timeline_fps) / max(1.0, timeline_fps),
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
                "mixed_cut": True,
            },
            "detect_duplicate": self.chk_duplicate.isChecked(),
            "detect_content_dup": self.chk_content_dup.isChecked(),
            "detect_mixed_cut": True,
            "detect_corrupt": complex_mode and self.chk_corrupt.isChecked(),
            "html_report": self.chk_html.isChecked(),
            "clear_existing": self.chk_clear.isChecked(),
            "complex_mode": complex_mode,
            "merge_mode": self.chk_merge.isChecked(),
            "mark_hidden_clips": self.chk_mark_hidden.isChecked(),
            "mark_partial_opacity": self.chk_partial_opacity.isChecked(),
            "png_as_opaque": self.chk_png_opaque.isChecked(),
            "headless": True,
        }

    def collect_batch_params(self) -> list[dict]:
        return [self.collect_params(selected) for selected in self.selected_batch_timelines()]

    def start_detection(self) -> None:
        jobs = self.collect_batch_params()
        if self.prompt_complex_mode_for_risky_timelines(jobs):
            return
        if any(job["complex_mode"] and (not job["manual_io_in"] or not job["manual_io_out"]) for job in jobs):
            QMessageBox.warning(self, "复杂模式需要入出点", "复杂模式会先渲染检测范围，请填写手动入点和出点。")
            return

        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress_label.setText("检测中")
        self._zero_result_notice_shown = False
        self._log(f"开始检测 {len(jobs)} 条时间线")
        self._marker_refresh_after_complete = False
        self.save_settings()
        self.animate_widget(self.start_btn)
        self.progress_timer.start()
        self.worker = SubmitWorker(self.bridge, jobs)
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def prompt_complex_mode_for_risky_timelines(self, jobs: list[dict]) -> bool:
        if self.chk_complex.isChecked() or any(job.get("complex_mode") for job in jobs):
            return False
        for job in jobs:
            result = self.bridge.detect_complex_timeline_risk(int(job.get("timeline_index", 1)))
            if not result.get("ok") or int(result.get("count", 0) or 0) <= 0:
                continue
            message = str(result.get("message") or "检测到疑似混剪/多镜头成片。")
            detail_lines = []
            for item in (result.get("candidates") or [])[:4]:
                if isinstance(item, dict):
                    detail_lines.append(f"- {item.get('name', '未命名')}：{item.get('reason', '需要复杂模式复核')}")
            detail = "\n".join(detail_lines)
            prompt = (
                f"{message}\n\n普通模式不会再对这类成片做慢速深扫；建议启用复杂模式渲染最终画面检测。"
                f"{chr(10) + detail if detail else ''}\n\n是否现在切换到复杂模式？"
            )
            answer = QMessageBox.question(
                self,
                "建议启用复杂模式",
                prompt,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self.chk_complex.setChecked(True)
                self.fill_in_out_from_current_timeline_marks()
                self._log("已切换到复杂模式，请确认入出点后再次开始检测。")
                return True
            self._log("用户选择继续普通模式；疑似混剪成片不会执行慢速深扫。")
            return False
        return False

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

    def fill_in_out_from_current_timeline_marks(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.current_timeline_marks(int(selected.get("index", 1)))
        if not result.get("ok"):
            self._log(str(result.get("message", "未读取到入出点。")))
            return
        self.io_in.setText(str(result.get("in_tc", "")))
        self.io_out.setText(str(result.get("out_tc", "")))
        self.save_settings()
        self._log(str(result.get("message", "已读取当前时间线入出点。")))

    def scan_mono_audio(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.scan_mono_audio(int(selected.get("index", 1)))
        self.render_audio_scan(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)

    def mark_mono_audio(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.mark_mono_audio(int(selected.get("index", 1)))
        self.render_audio_scan(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)

    def fix_mono_audio(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.fix_mono_audio_to_stereo(int(selected.get("index", 1)))
        self.render_audio_scan(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)

    def refresh_results_from_markers(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.bfd_marker_records(int(selected.get("index", 1)))
        records = result.get("records") if isinstance(result.get("records"), list) else []
        counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
        if counts:
            self._update_result_cards({"counts": counts, "records": records})
        else:
            self.render_result_records(records)
        self.side_tabs.setCurrentWidget(self.results_tab)
        self._log(str(result.get("message", "已刷新时间线标记。")))

    def scan_text_layers(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.scan_text_items(int(selected.get("index", 1)), self.text_search.text().strip())
        self.text_records = result.get("items") if isinstance(result.get("items"), list) else []
        self.text_list.clear()
        for idx, item in enumerate(self.text_records, 1):
            text = str(item.get("text", "")).replace("\n", " ")
            if len(text) > 80:
                text = text[:77] + "..."
            label = (
                f"{idx:03d}  {item.get('timecode', '')}  "
                f"{str(item.get('track_type', '')).upper()}{item.get('track_index', '')}  {text}"
            )
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, idx - 1)
            self.text_list.addItem(row)
        self.text_status.setText(str(result.get("message", f"找到 {len(self.text_records)} 条文字/字幕素材。")))
        self.side_tabs.setCurrentWidget(self.text_tab)
        self._log(self.text_status.text())

    def selected_text_item_record(self) -> dict | None:
        row = self.text_list.currentItem()
        if not row:
            return None
        index = int(row.data(Qt.UserRole))
        if index < 0 or index >= len(self.text_records):
            return None
        self.text_index = index
        return self.text_records[index]

    def jump_to_selected_text_item(self, *_args) -> None:
        item = self.selected_text_item_record()
        if not item:
            return
        result = self.bridge.jump_to_text_item(item)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())

    def replace_selected_text_item(self) -> None:
        item = self.selected_text_item_record()
        if not item:
            return
        new_text = self.text_replace.text()
        result = self.bridge.replace_text_item(item, new_text)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())
        if result.get("ok"):
            self.scan_text_layers()

    def delete_selected_text_item(self) -> None:
        item = self.selected_text_item_record()
        if not item:
            return
        if QMessageBox.question(self, "删除文字层", "确认删除选中的字幕/文字层吗？") != QMessageBox.Yes:
            return
        result = self.bridge.delete_text_item(item)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())
        if result.get("ok"):
            self.scan_text_layers()

    def remove_fillers_from_selected_text_item(self) -> None:
        item = self.selected_text_item_record()
        if not item:
            return
        source_text = str(item.get("text", ""))
        cleaned = self.remove_filler_words(source_text)
        self.text_replace.setText(cleaned)
        if cleaned == source_text:
            self.text_status.setText("未发现可去除的语气词。")
            return
        result = self.bridge.replace_text_item(item, cleaned)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())
        if result.get("ok"):
            self.scan_text_layers()

    @staticmethod
    def remove_filler_words(text: str) -> str:
        fillers = [
            r"\buh+\b",
            r"\bum+\b",
            r"\ber+\b",
            r"\bah+\b",
            r"嗯+",
            r"呃+",
            r"额+",
            r"啊+",
            r"这个",
            r"那个",
            r"就是",
            r"然后",
        ]
        cleaned = text
        for pattern in fillers:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+([，。！？、,.!?])", r"\1", cleaned)
        return cleaned.strip()

    def render_audio_scan(self, result: dict) -> None:
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        clips = result.get("clips") if isinstance(result.get("clips"), list) else []
        tracks = result.get("tracks") if isinstance(result.get("tracks"), list) else []
        message = str(result.get("message", "音频扫描完成。"))
        self.audio_summary.setText(
            f"{message}  单声道片段 {summary.get('mono_clips', len(clips))} 个 / "
            f"单声道轨道 {summary.get('mono_tracks', 0)} 条 / "
            f"轨道修正 {summary.get('track_format_fixed', 0)}/{summary.get('track_format_fix_attempts', 0)} / "
            f"映射修正 {summary.get('mapping_fixed', 0)}/{summary.get('mapping_fix_attempts', 0)}"
        )
        lines = []
        if tracks:
            lines.append("轨道")
            for track in tracks:
                lines.append(
                    f"  A{track.get('index')}  {track.get('name', '')}  "
                    f"{track.get('format', track.get('subtype', 'unknown'))}  clips={track.get('item_count', 0)}"
                    f"{'  已改双声道' if track.get('format_fixed') else ''}"
                )
        if clips:
            lines.append("")
            lines.append("单声道片段")
            for idx, clip in enumerate(clips, 1):
                lines.append(
                    f"{idx:03d}  A{clip.get('track_index')}  "
                    f"{clip.get('start_frame')}->{clip.get('end_frame')}  "
                    f"{clip.get('name', '未命名')}  [{clip.get('reason', 'mono')}]"
                    f"{'  已写回映射' if clip.get('mapping_fixed') else ''}"
                )
        if not lines:
            lines.append(message)
        self.audio_list.setPlainText("\n".join(lines))
        self._log(message)

    def on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.progress_label.setText(message[:20])
        self._log(message)

    def on_done(self, ok: bool, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress_label.setText("已提交" if ok else "失败")
        self._log(message)
        if ok:
            self.side_tabs.setCurrentWidget(self.results_tab)
            QApplication.beep()
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
            if state == "complete" or percent >= 100:
                self.side_tabs.setCurrentWidget(self.results_tab)
                progress_records = progress.get("records")
                needs_marker_refresh = not isinstance(progress_records, list) or not progress_records
                if needs_marker_refresh and not self._marker_refresh_after_complete:
                    self._marker_refresh_after_complete = True
                    self.refresh_results_from_markers()
                QApplication.beep()
                if self._progress_has_zero_results(progress) and not self._zero_result_notice_shown:
                    self._zero_result_notice_shown = True
                    message = "检测完成，但当前入出点范围内没有采集到可分析片段。请清空手动入出点，或确认入出点覆盖时间线素材。"
                    self._log(message)
                    QMessageBox.information(self, "没有可分析片段", message)

    def _update_result_cards(self, progress: dict) -> None:
        counts = progress.get("counts")
        if isinstance(counts, dict):
            for key, label in self.result_values.items():
                if key in counts:
                    label.setText(str(counts[key]))
        records = progress.get("records")
        if isinstance(records, list):
            self.render_result_records(records)

    def _progress_has_zero_results(self, progress: dict) -> bool:
        counts = progress.get("counts")
        records = progress.get("records")
        total = counts.get("total") if isinstance(counts, dict) else None
        return total == 0 and isinstance(records, list) and not records

    @staticmethod
    def result_sort_key(record: dict) -> tuple[int, str]:
        timecode = str(record.get("timecode") or record.get("timeline_start_tc") or "")
        parts = timecode.split(":")
        if len(parts) == 4:
            try:
                hh, mm, ss, ff = [int(part) for part in parts]
                fps = int(round(float(record.get("fps") or record.get("timeline_fps") or BASELINE_FPS)))
                fps = max(1, fps)
                return (((hh * 60 + mm) * 60 + ss) * fps + ff), timecode
            except Exception:
                pass
        for key in ("frame", "timeline_start_frame", "marker_frame"):
            try:
                value = record.get(key)
                if value is not None and value != "":
                    return int(float(value)), str(record.get("timecode") or record.get("timeline_start_tc") or "")
            except Exception:
                pass
        return 10**12, timecode

    @staticmethod
    def result_has_jump_target(record: dict) -> bool:
        timecode = str(record.get("timecode") or record.get("timeline_start_tc") or "").strip()
        if timecode and timecode != "??:??:??:??":
            return True
        for key in ("frame", "timeline_start_frame", "marker_frame"):
            value = record.get(key)
            if value is None or value == "":
                continue
            try:
                int(float(value))
                return True
            except Exception:
                pass
        return False

    @staticmethod
    def frame_to_timecode(frame: int | float, fps: int | float) -> str:
        fps_int = max(1, int(round(float(fps or BASELINE_FPS))))
        total_frames = max(0, int(round(float(frame or 0))))
        ff = total_frames % fps_int
        total_seconds = total_frames // fps_int
        ss = total_seconds % 60
        mm = (total_seconds // 60) % 60
        hh = total_seconds // 3600
        return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    def normalize_result_record(self, record: dict, default_timeline_index: int) -> dict:
        normalized = dict(record)
        normalized.setdefault("timeline_index", default_timeline_index)
        if not (normalized.get("timecode") or normalized.get("timeline_start_tc")):
            for key in ("frame", "timeline_start_frame", "marker_frame"):
                value = normalized.get(key)
                if value is None or value == "":
                    continue
                try:
                    fps = float(normalized.get("fps") or normalized.get("timeline_fps") or self.selected_fps())
                    normalized["timecode"] = self.frame_to_timecode(float(value), fps)
                    break
                except Exception:
                    pass
        return normalized

    def render_result_records(self, records: list) -> None:
        default_timeline_index = int(self.selected_timeline_data().get("index", 1))
        self.result_records = []
        for record in records:
            if isinstance(record, dict):
                normalized = self.normalize_result_record(record, default_timeline_index)
                if self.result_has_jump_target(normalized):
                    self.result_records.append(normalized)
        self.result_records.sort(key=self.result_sort_key)
        lines = []
        for idx, record in enumerate(self.result_records, 1):
            timecode = record.get("timecode") or record.get("timeline_start_tc") or "??:??:??:??"
            classification = record.get("classification") or "info"
            name = record.get("name") or record.get("marker_name") or classification
            color = record.get("color") or record.get("marker_color") or "-"
            lines.append(f"{idx:03d}  {timecode}  {color}  {classification}  {name}")
        if not lines:
            lines.append("未检测到问题；如果没有标记，请确认入出点覆盖时间线素材。")
        self.result_list.setPlainText("\n".join(lines))
        self.result_index = 0 if self.result_records else -1
        self.update_result_position()

    def move_result_cursor(self, offset: int) -> None:
        if not self.result_records:
            self.update_result_position()
            return
        self.result_index = max(0, min(len(self.result_records) - 1, self.result_index + offset))
        self.jump_to_result_row(self.result_index)

    def jump_to_result_row(self, row: int) -> None:
        if row < 0 or row >= len(self.result_records):
            return
        self.result_index = row
        self.update_result_position()
        record = self.result_records[row]
        timecode = str(record.get("timecode") or record.get("timeline_start_tc") or "")
        if not timecode:
            self._log("该结果没有可跳转时间码。")
            return
        timeline_index = int(record.get("timeline_index") or self.selected_timeline_data().get("index", 1))
        ok, message = self.bridge.jump_to_timecode(timeline_index, timecode)
        self._log(message)
        if not ok:
            QMessageBox.warning(self, "跳转失败", message)

    def update_result_position(self) -> None:
        total = len(self.result_records)
        current = 0 if total == 0 else self.result_index + 1
        self.result_position_label.setText(f"{current} / {total}")

    def animate_current_tab(self) -> None:
        widget = self.side_tabs.currentWidget()
        if widget:
            self.animate_widget(widget, 180)

    def install_button_motion(self) -> None:
        for button in self.findChildren(QPushButton):
            self.wire_button_motion(button)

    def wire_button_motion(self, button: QPushButton) -> None:
        if button.property("motion") == "press-fade":
            return
        button.setProperty("motion", "press-fade")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, btn=button: self.animate_widget(btn, 120, 0.86))

    def animate_widget(self, widget: QWidget, duration: int = 220, start_opacity: float = 0.72) -> None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(start_opacity)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._active_animations.append(animation)

        def finish_animation() -> None:
            widget.setGraphicsEffect(None)
            if animation in self._active_animations:
                self._active_animations.remove(animation)

        animation.finished.connect(finish_animation)
        self._tab_animation = animation
        animation.start()

    def _log(self, message: str) -> None:
        self.log.append(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.save_settings()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    if BRIDGE_WORKER_ARG in argv[1:]:
        return run_resolve_bridge_worker()

    set_windows_app_user_model_id()
    app = QApplication(argv)
    font_family = install_cjk_font()
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont(font_family, 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
