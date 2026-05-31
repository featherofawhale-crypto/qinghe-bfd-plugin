from __future__ import annotations

import sys
import time
from dataclasses import asdict

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from resolve_bridge import ResolveBridge, TimelineInfo, read_progress_file


APP_VERSION = "1.9.53"


APP_STYLE = """
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
QLabel#Title {
    font-size: 24px;
    font-weight: 700;
    color: #f5f7fa;
}
QLabel#Subtitle { color: #93a4b5; }
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
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
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
QPushButton {
    min-height: 38px;
    border-radius: 7px;
    border: 1px solid #344252;
    background: #202832;
    color: #eaf1f8;
    padding: 7px 14px;
    font-weight: 700;
}
QPushButton:hover { background: #2a3542; border-color: #4a5c70; }
QPushButton#Primary {
    background: #2f7dd3;
    border-color: #4394ed;
    color: white;
}
QPushButton#Primary:hover { background: #388be8; }
QPushButton#Primary:disabled { background: #324457; color: #8290a0; }
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
    background: #35c4a1;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
    background: #d9f7ef;
    border: 1px solid #55d6b8;
}
QTextEdit {
    background: #0c0f13;
    border: 1px solid #2a3440;
    border-radius: 8px;
    color: #b7c5d1;
    padding: 8px;
}
"""


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
            self.progress.emit(70, "正在尝试通过 fuscript 触发 Lua 入口")
            ok, message = self.bridge.run_lua_entry_with_fuscript(params_path)
            self.progress.emit(100, "已提交给 Resolve" if ok else "已写入参数，自动触发失败")
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("清何黑帧夹帧检测 - Pro Control")
        self.resize(980, 720)
        self.bridge = ResolveBridge()
        self.timelines: list[TimelineInfo] = []
        self.worker: SubmitWorker | None = None
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(700)
        self.progress_timer.timeout.connect(self.poll_detection_progress)

        shell = QFrame()
        shell.setObjectName("Shell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(18)

        title = QLabel("清何黑帧夹帧检测")
        title.setObjectName("Title")
        subtitle = QLabel(f"独立参数控制台 v{APP_VERSION} / PySide6 + DaVinci Resolve Bridge")
        subtitle.setObjectName("Subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._build_timeline_group())
        root.addWidget(self._build_detection_group())
        root.addWidget(self._build_threshold_group())
        root.addWidget(self._build_action_group())

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        root.addWidget(self.log)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(18, 18, 18, 18)
        wrapper_layout.addWidget(shell)
        self.setCentralWidget(wrapper)

        self.refresh_timelines()
        self._log("Resolve API: " + ("已连接" if self.bridge.is_connected() else "未连接，使用离线参数模式"))

    def _build_timeline_group(self) -> QGroupBox:
        box = QGroupBox("时间线")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.timeline_combo = QComboBox()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_timelines)

        self.io_in = QLineEdit()
        self.io_in.setPlaceholderText("可选，例如 01:00:00:00")
        self.io_out = QLineEdit()
        self.io_out.setPlaceholderText("可选，例如 01:02:30:00")

        layout.addWidget(QLabel("目标时间线"), 0, 0)
        layout.addWidget(self.timeline_combo, 0, 1)
        layout.addWidget(refresh, 0, 2)
        layout.addWidget(QLabel("手动入点"), 1, 0)
        layout.addWidget(self.io_in, 1, 1)
        layout.addWidget(QLabel("手动出点"), 2, 0)
        layout.addWidget(self.io_out, 2, 1)
        return box

    def _build_detection_group(self) -> QGroupBox:
        box = QGroupBox("检测项目")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(22)
        layout.setVerticalSpacing(12)

        self.chk_error = QCheckBox("夹帧异常")
        self.chk_error.setChecked(True)
        self.chk_suspect = QCheckBox("可疑黑帧")
        self.chk_suspect.setChecked(True)
        self.chk_gap = QCheckBox("时间线空位")
        self.chk_opacity = QCheckBox("透明度遮挡")
        self.chk_duplicate = QCheckBox("重复素材")
        self.chk_duplicate.setChecked(True)
        self.chk_content_dup = QCheckBox("内容重复")
        self.chk_corrupt = QCheckBox("坏帧检测 signalstats")
        self.chk_html = QCheckBox("生成 HTML 报告")
        self.chk_clear = QCheckBox("检测前清理旧标记")
        self.chk_complex = QCheckBox("复杂模式 / 整段渲染")
        self.chk_auto_run = QCheckBox("点击开始后尝试自动触发 Lua")

        checks = [
            self.chk_error,
            self.chk_suspect,
            self.chk_gap,
            self.chk_opacity,
            self.chk_duplicate,
            self.chk_content_dup,
            self.chk_corrupt,
            self.chk_html,
            self.chk_clear,
            self.chk_complex,
            self.chk_auto_run,
        ]
        for i, check in enumerate(checks):
            layout.addWidget(check, i // 3, i % 3)
        return box

    def _build_threshold_group(self) -> QGroupBox:
        box = QGroupBox("阈值")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        self.severity = QComboBox()
        self.severity.addItems(["标准", "严格", "极严"])
        self.severity.currentIndexChanged.connect(self.apply_severity)

        self.stuck_frames = QSpinBox()
        self.stuck_frames.setRange(1, 999)
        self.stuck_frames.setValue(2)
        self.stuck_slider = self._make_slider(1, 999, 2, self.stuck_frames)

        self.suspect_frames = QSpinBox()
        self.suspect_frames.setRange(1, 9999)
        self.suspect_frames.setValue(8)
        self.suspect_slider = self._make_slider(1, 9999, 8, self.suspect_frames)

        self.pixel_threshold = QDoubleSpinBox()
        self.pixel_threshold.setRange(0.001, 1.0)
        self.pixel_threshold.setSingleStep(0.01)
        self.pixel_threshold.setDecimals(3)
        self.pixel_threshold.setValue(0.100)
        self.pixel_slider = self._make_float_slider(1, 1000, 100, self.pixel_threshold, 1000.0)

        self.min_duration = QDoubleSpinBox()
        self.min_duration.setRange(0.001, 60.0)
        self.min_duration.setSingleStep(0.01)
        self.min_duration.setDecimals(3)
        self.min_duration.setValue(0.040)
        self.min_duration_slider = self._make_float_slider(1, 60000, 40, self.min_duration, 1000.0)

        self.content_sample_interval = QSpinBox()
        self.content_sample_interval.setRange(1, 9999)
        self.content_sample_interval.setValue(8)
        self.content_sample_slider = self._make_slider(1, 9999, 8, self.content_sample_interval)

        layout.addWidget(QLabel("严重程度"), 0, 0)
        layout.addWidget(self.severity, 0, 1)
        layout.addWidget(QLabel("夹帧阈值 / 帧"), 0, 2)
        layout.addWidget(self.stuck_frames, 0, 3)
        layout.addWidget(self.stuck_slider, 0, 4)
        layout.addWidget(QLabel("可疑阈值 / 帧"), 1, 0)
        layout.addWidget(self.suspect_frames, 1, 1)
        layout.addWidget(self.suspect_slider, 1, 2, 1, 3)
        layout.addWidget(QLabel("像素阈值"), 2, 0)
        layout.addWidget(self.pixel_threshold, 2, 1)
        layout.addWidget(self.pixel_slider, 2, 2, 1, 3)
        layout.addWidget(QLabel("最短黑帧 / 秒"), 3, 0)
        layout.addWidget(self.min_duration, 3, 1)
        layout.addWidget(self.min_duration_slider, 3, 2, 1, 3)
        layout.addWidget(QLabel("指纹采样 / 帧"), 4, 0)
        layout.addWidget(self.content_sample_interval, 4, 1)
        layout.addWidget(self.content_sample_slider, 4, 2, 1, 3)
        return box

    def _make_slider(self, minimum: int, maximum: int, value: int, spinbox: QSpinBox) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)
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
        return slider

    def _build_action_group(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.progress_label = QLabel("待机")
        self.progress_label.setMinimumWidth(160)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")
        self.start_btn = QPushButton("开始检测")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start_detection)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress, 1)
        layout.addWidget(self.start_btn)
        return panel

    def refresh_timelines(self) -> None:
        self.timelines = self.bridge.list_timelines()
        self.timeline_combo.clear()
        for tl in self.timelines:
            self.timeline_combo.addItem(f"{tl.index}. {tl.name}  /  {tl.fps:g} fps", asdict(tl))

    def apply_severity(self) -> None:
        level = self.severity.currentText()
        if level == "标准":
            self.stuck_frames.setValue(2)
            self.suspect_frames.setValue(8)
            self.pixel_threshold.setValue(0.100)
        elif level == "严格":
            self.stuck_frames.setValue(3)
            self.suspect_frames.setValue(10)
            self.pixel_threshold.setValue(0.080)
        else:
            self.stuck_frames.setValue(4)
            self.suspect_frames.setValue(12)
            self.pixel_threshold.setValue(0.060)

    def collect_params(self) -> dict:
        selected = self.timeline_combo.currentData() or {"index": 1, "name": "当前时间线", "fps": 24.0}
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
                "gap": self.chk_gap.isChecked(),
                "opacity": self.chk_opacity.isChecked(),
                "duplicate": self.chk_duplicate.isChecked(),
                "content_dup": self.chk_content_dup.isChecked(),
            },
            "detect_duplicate": self.chk_duplicate.isChecked(),
            "detect_content_dup": self.chk_content_dup.isChecked(),
            "detect_corrupt": self.chk_corrupt.isChecked(),
            "html_report": self.chk_html.isChecked(),
            "clear_existing": self.chk_clear.isChecked(),
            "complex_mode": self.chk_complex.isChecked(),
            "merge_mode": self.chk_complex.isChecked(),
            "mark_hidden_clips": False,
            "mark_partial_opacity": True,
            "png_as_opaque": False,
        }

    def start_detection(self) -> None:
        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress_label.setText("提交中")
        params = self.collect_params()
        self._log("开始提交参数")
        self.progress_timer.start()
        self.worker = SubmitWorker(self.bridge, params, self.chk_auto_run.isChecked())
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.start()

    def on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.progress_label.setText(message[:18])
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
        self.progress_label.setText(stage[:18] if stage else state)
        if stage:
            self._log(f"检测进度 {percent}%：{stage}")
        if state in {"complete", "failed", "cancelled"} or percent >= 100:
            self.progress_timer.stop()

    def _log(self, message: str) -> None:
        self.log.append(message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
