from __future__ import annotations

import copy
from html import escape as html_escape
import json
import math
import re
import subprocess
import sys
import threading
import time
import ctypes
import platform
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QGuiApplication, QIcon, QPainter, QPixmap, QTextDocument
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from resolve_bridge import (
    BRIDGE_WORKER_ARG,
    ResolveBridge,
    TimelineInfo,
    hidden_subprocess_kwargs,
    progress_path,
    read_progress_file,
    run_resolve_bridge_worker,
)


APP_VERSION = "2.0.01-测试版"
FEEDBACK_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/c533d532-4041-4e58-abd5-6f9eb924d58c"
ANALYTICS_ENDPOINT_URL = "https://qinghe-bfd-analytics.featherofawhale.workers.dev/collect"

DEFAULT_STUCK_FRAMES = 3
DEFAULT_SUSPECT_FRAMES = 12
DEFAULT_MIN_BLACK_FRAMES = 1
BASELINE_FPS = 25.0
DEFAULT_PIXEL_THRESHOLD = 1.0
DEFAULT_CONTENT_SAMPLE_INTERVAL = 3
MAX_FRAME_THRESHOLD = 100
ICON_PATH = Path(__file__).resolve().with_name("icon.svg")
DONATION_DIR = Path(__file__).resolve().with_name("donate")
DONATION_AMOUNTS = (1, 2, 3, 5)
WINDOWS_APP_ID = "Qinghe.BFD.Control"
SINGLE_INSTANCE_NAME = "Qinghe.BFD.Control.SingleInstance"
DISCLAIMER_TEXT = (
    "清何黑帧夹帧检测是一款免费工具，供 DaVinci Resolve 用户自愿使用。\n"
    "本插件按“现状”提供，不作任何明示或默示保证，包括但不限于适销性、特定用途适用性。\n"
    "作者不对因使用本插件产生的直接、间接、偶然、特殊或后果性损害承担责任，包括项目文件损坏或丢失、数据丢失、时间线标记异常、软件崩溃或其他 Resolve 操作问题。\n"
    "使用者应自行评估适用性，并在使用前做好项目备份。\n"
    "本插件仅用于辅助视频剪辑工作流程，检测结果仅作辅助参考，不保证 100% 检测所有问题，最终判断仍需人工确认。\n"
    "捐赠为自愿支持开发，不构成功能购买、服务承诺、抽奖返利或收益承诺。"
)

AUDIO_EFFECT_PRESETS = [
    {
        "name": "人声清晰",
        "type": "Dialogue",
        "summary": "采访、口播、同期声提亮清晰度。",
        "params": "EQ: 80Hz 高通；2.5kHz +2dB；De-Esser 轻度；Compressor 2:1；Limiter -1dB。",
    },
    {
        "name": "降噪采访",
        "type": "Dialogue",
        "summary": "空调声、底噪较明显的人声素材。",
        "params": "Noise Reduction 轻/中；Voice Isolation 20-40；EQ 低切；保留自然齿音。",
    },
    {
        "name": "播客电台",
        "type": "Voice",
        "summary": "厚一点、近一点的电台/播客质感。",
        "params": "EQ: 120Hz +1dB, 3kHz +1.5dB；Compressor 3:1；Soft Clip/Limiter。",
    },
    {
        "name": "电话音",
        "type": "Effect",
        "summary": "手机通话、对讲机、回忆音效。",
        "params": "Band Pass 300Hz-3.4kHz；少量 Distortion；可加轻微 Noise。",
    },
    {
        "name": "空间混响",
        "type": "Reverb",
        "summary": "大厅、房间、空旷空间感。",
        "params": "Reverb Room/Hall；Pre-delay 10-25ms；Wet 8-18%；低频混响削减。",
    },
    {
        "name": "音乐压低",
        "type": "Mix",
        "summary": "有人声时音乐自动让位的混音方向。",
        "params": "Music -10~-18dB；Sidechain/Ducker；人声频段 1-4kHz 轻让位。",
    },
    {
        "name": "短视频人声",
        "type": "Voice",
        "summary": "信息流、口播、带背景音乐的短视频。",
        "params": "Voice Isolation 15-30；Compressor 2.5:1；Limiter -1dB；音乐 -14dB 左右。",
    },
    {
        "name": "纪录片旁白",
        "type": "Voice",
        "summary": "稳、厚、清楚，不抢环境声。",
        "params": "EQ 低切 70Hz；200Hz 轻减；3kHz +1dB；Compressor 2:1；Reverb 极轻。",
    },
    {
        "name": "采访救急",
        "type": "Repair",
        "summary": "现场采访声音薄、远、底噪偏高。",
        "params": "Noise Reduction 轻；Voice Isolation 30；Presence +2dB；Limiter -1dB。",
    },
    {
        "name": "去齿音",
        "type": "Repair",
        "summary": "s、sh、z、c 刺耳的人声。",
        "params": "De-Esser 5kHz-8kHz；Threshold 中等；避免过度导致口齿发闷。",
    },
    {
        "name": "低频清理",
        "type": "Repair",
        "summary": "风噪、桌面震动、脚步低频。",
        "params": "High Pass 80-120Hz；必要时 200Hz 轻减；保留人声厚度。",
    },
    {
        "name": "响度统一",
        "type": "Loudness",
        "summary": "多段素材音量忽大忽小。",
        "params": "Normalize/Clip Gain；Compressor 2:1；Limiter -1dB；目标 -16~-14 LUFS。",
    },
    {
        "name": "轻压缩",
        "type": "Dynamics",
        "summary": "让人声更稳定但保留自然动态。",
        "params": "Ratio 2:1；Attack 10-20ms；Release 80-150ms；Gain Reduction 2-4dB。",
    },
    {
        "name": "强压缩",
        "type": "Dynamics",
        "summary": "直播、广告、强存在感人声。",
        "params": "Ratio 4:1；Attack 5-10ms；Release 60-120ms；Limiter 防爆。",
    },
    {
        "name": "低沉男声",
        "type": "Voice",
        "summary": "男声厚度加强，避免糊。",
        "params": "120Hz +1dB；250Hz -1dB；3kHz +1.5dB；低切 60Hz。",
    },
    {
        "name": "明亮女声",
        "type": "Voice",
        "summary": "女声更亮、更靠前。",
        "params": "低切 90Hz；4kHz +1.5dB；8kHz +1dB；De-Esser 轻。",
    },
    {
        "name": "远距离收音",
        "type": "Repair",
        "summary": "相机机顶麦、距离远、房间感重。",
        "params": "Voice Isolation 40-60；De-Reverb 轻；2kHz-4kHz 提升；压缩轻。",
    },
    {
        "name": "室内回声",
        "type": "Repair",
        "summary": "空房间、会议室混响偏多。",
        "params": "De-Reverb 中低；低频混响削减；Presence 小幅提升。",
    },
    {
        "name": "户外风噪",
        "type": "Repair",
        "summary": "户外采访、风吹麦克风。",
        "params": "High Pass 120Hz；Noise Reduction 轻；不要过度损伤人声。",
    },
    {
        "name": "会议清理",
        "type": "Dialogue",
        "summary": "多人会议、会议室录音。",
        "params": "Voice Isolation 20；低切 80Hz；Compressor 2:1；响度统一。",
    },
    {
        "name": "电影对白",
        "type": "Dialogue",
        "summary": "自然、不过度压缩的对白。",
        "params": "低切 60-80Hz；轻 EQ；Compressor 1.5-2:1；保留环境声。",
    },
    {
        "name": "广告人声",
        "type": "Voice",
        "summary": "更响、更亮、更贴脸。",
        "params": "Presence +2dB；Compressor 3:1；Limiter -0.8dB；轻饱和。",
    },
    {
        "name": "Vlog环境",
        "type": "Mix",
        "summary": "人声清楚，环境声不过分突出。",
        "params": "人声低切；环境声 -6~-12dB；必要时轻降噪。",
    },
    {
        "name": "BGM柔化",
        "type": "Music",
        "summary": "背景音乐不抢人声。",
        "params": "1kHz-4kHz 轻减；整体 -12dB；淡入淡出更长。",
    },
    {
        "name": "脚步增强",
        "type": "SFX",
        "summary": "脚步、动作声更明显。",
        "params": "中高频 +2dB；低频按素材补一点；短混响贴空间。",
    },
    {
        "name": "冲击增强",
        "type": "SFX",
        "summary": "转场、撞击、鼓点更有力量。",
        "params": "Transient 强化；低频 80-120Hz +2dB；Limiter 防爆。",
    },
    {
        "name": "梦境回忆",
        "type": "Effect",
        "summary": "回忆、梦境、主观听感。",
        "params": "Reverb Wet 20%；High Cut 6kHz；轻 Chorus/Delay。",
    },
    {
        "name": "广播喇叭",
        "type": "Effect",
        "summary": "商场广播、校园广播、扩音器。",
        "params": "Band Pass 250Hz-5kHz；轻 Distortion；短 Room Reverb。",
    },
    {
        "name": "水下闷声",
        "type": "Effect",
        "summary": "水下、耳鸣、主观压迫。",
        "params": "Low Pass 800Hz-1.5kHz；低频轻增强；Reverb/Delay 低反馈。",
    },
    {
        "name": "耳鸣压迫",
        "type": "Effect",
        "summary": "爆炸后、眩晕、失真听感。",
        "params": "High Tone 轻；主体低通；环境声压低；短暂自动化。",
    },
]

AUDIO_BUILTIN_FX_CARDS = {
    "人声清晰": [
        ("Voice Isolation", "语音隔离", "Amount 20-35；Mode 默认；先开小，听到水声/金属声就退。"),
        ("Channel EQ", "通道均衡器", "HPF 80Hz 24dB/oct；250Hz -2dB Q1.2；3.2kHz +2dB Q0.9；10kHz +1dB。"),
        ("Compressor", "压缩器", "Ratio 2:1；Threshold -20dB；Attack 12ms；Release 110ms；Makeup +2dB。"),
        ("Limiter", "限制器", "Ceiling -1.0dB；Release 50ms。"),
    ],
    "降噪采访": [
        ("Voice Isolation", "语音隔离", "Amount 35-55；只处理人声底噪，过量会发闷。"),
        ("De-Esser", "齿音消除器", "Freq 6.5kHz；Threshold -28dB；Reduction 3-5dB。"),
        ("Channel EQ", "通道均衡器", "HPF 90Hz；200Hz -2dB；4kHz +1dB。"),
        ("Compressor", "压缩器", "Ratio 2:1；Threshold -22dB；Attack 15ms；Release 120ms。"),
    ],
    "播客电台": [
        ("Channel EQ", "通道均衡器", "HPF 70Hz；120Hz +1.5dB；280Hz -1.5dB；3kHz +1.5dB；12kHz +1dB。"),
        ("Compressor", "压缩器", "Ratio 3:1；Threshold -24dB；Attack 8ms；Release 90ms；Makeup +3dB。"),
        ("Limiter", "限制器", "Ceiling -1dB；Input/Makeup 到峰值不红。"),
    ],
    "电话音": [
        ("Channel EQ", "通道均衡器", "HPF 300Hz；LPF 3.4kHz；1.5kHz +3dB；Q 1.0。"),
        ("Distortion", "失真", "Drive 5-10%；Mix 15-25%。"),
        ("Compressor", "压缩器", "Ratio 4:1；Threshold -26dB；Attack 5ms；Release 80ms。"),
    ],
    "空间混响": [
        ("Reverb", "混响", "Room/Hall；Pre-delay 18ms；Decay 1.2s；Wet 10-16%；Low Cut 180Hz。"),
        ("Channel EQ", "通道均衡器", "Send/Return 上削低频：HPF 180Hz；LPF 8kHz。"),
    ],
    "音乐压低": [
        ("Channel EQ", "通道均衡器", "音乐轨 1.5-4kHz -2dB；低频按画面保留。"),
        ("Compressor", "压缩器", "音乐轨 Ratio 2:1；Threshold -24dB；Attack 30ms；Release 250ms。"),
        ("Mixer Fader", "混音器推子", "有人声时 BGM 通常 -18 到 -12dB；无人声可回到 -10 到 -8dB。"),
    ],
    "短视频人声": [
        ("Voice Isolation", "语音隔离", "Amount 20-40。"),
        ("Dialogue Leveler", "对白均衡器", "Amount 30-50；Output 目标 -14 LUFS 左右。"),
        ("Channel EQ", "通道均衡器", "HPF 85Hz；3.5kHz +2dB；10kHz +1dB。"),
        ("Limiter", "限制器", "Ceiling -1dB。"),
    ],
    "纪录片旁白": [
        ("Channel EQ", "通道均衡器", "HPF 70Hz；220Hz -1.5dB；3kHz +1dB；8kHz +0.5dB。"),
        ("Compressor", "压缩器", "Ratio 2:1；Threshold -23dB；Attack 18ms；Release 160ms。"),
        ("Reverb", "混响", "Room 极轻；Wet 4-7%；Decay 0.7s。"),
    ],
    "采访救急": [
        ("Voice Isolation", "语音隔离", "Amount 40-65。"),
        ("Channel EQ", "通道均衡器", "HPF 100Hz；300Hz -3dB；2.8kHz +2.5dB。"),
        ("Compressor", "压缩器", "Ratio 2.5:1；Threshold -25dB；Attack 10ms；Release 130ms。"),
        ("Limiter", "限制器", "Ceiling -1dB。"),
    ],
    "去齿音": [
        ("De-Esser", "齿音消除器", "Freq 男声 5.5-6.5kHz / 女声 6.5-8kHz；Threshold -30dB；Reduction 4-7dB。"),
        ("Channel EQ", "通道均衡器", "如果仍刺耳，7kHz 附近 -1.5dB Q2。"),
    ],
    "低频清理": [
        ("Channel EQ", "通道均衡器", "HPF 男声 70Hz / 女声 90Hz / 风噪 120Hz；200Hz -2dB。"),
        ("Expander/Gate", "扩展器/噪声门", "Threshold -45dB；Range 8-12dB；Attack 5ms；Release 180ms。"),
    ],
    "响度统一": [
        ("Dialogue Leveler", "对白均衡器", "Amount 35-55；减少忽大忽小。"),
        ("Compressor", "压缩器", "Ratio 2:1；Threshold -22dB；Attack 12ms；Release 120ms。"),
        ("Limiter", "限制器", "Ceiling -1dB；最终目标短视频 -14 LUFS，播客 -16 LUFS。"),
    ],
    "轻压缩": [
        ("Compressor", "压缩器", "Ratio 2:1；Threshold -20dB；Attack 15ms；Release 120ms；Gain Reduction 2-4dB。"),
    ],
    "强压缩": [
        ("Compressor", "压缩器", "Ratio 4:1；Threshold -26dB；Attack 5ms；Release 80ms；Gain Reduction 5-8dB。"),
        ("Limiter", "限制器", "Ceiling -1dB。"),
    ],
    "低沉男声": [
        ("Channel EQ", "通道均衡器", "HPF 60Hz；120Hz +1.5dB；250Hz -2dB；3kHz +1.5dB。"),
        ("Compressor", "压缩器", "Ratio 2.2:1；Threshold -22dB；Attack 12ms；Release 120ms。"),
    ],
    "明亮女声": [
        ("Channel EQ", "通道均衡器", "HPF 90Hz；300Hz -1.5dB；4kHz +2dB；10kHz +1.5dB。"),
        ("De-Esser", "齿音消除器", "Freq 7kHz；Reduction 3-5dB。"),
    ],
    "远距离收音": [
        ("Voice Isolation", "语音隔离", "Amount 45-70。"),
        ("Channel EQ", "通道均衡器", "HPF 100Hz；500Hz -2dB；3kHz +3dB。"),
        ("De-Reverb", "去混响", "若当前版本/Studio 有该内置项：Amount 15-30；没有就用 EQ：250Hz -2dB、6kHz -1dB 减房间感。"),
    ],
    "室内回声": [
        ("De-Reverb", "去混响", "若当前版本/Studio 有该内置项：Amount 20-40；没有就用 EQ：250Hz -2dB、6kHz -1dB。"),
        ("Channel EQ", "通道均衡器", "HPF 90Hz；250Hz -2dB；6kHz -1dB。"),
    ],
    "户外风噪": [
        ("Channel EQ", "通道均衡器", "HPF 120Hz，严重风噪可到 160Hz；250Hz -2dB。"),
        ("Voice Isolation", "语音隔离", "Amount 25-45；不要过量。"),
    ],
    "会议清理": [
        ("Voice Isolation", "语音隔离", "Amount 20-35。"),
        ("Dialogue Leveler", "对白均衡器", "Amount 35-50。"),
        ("Channel EQ", "通道均衡器", "HPF 80Hz；300Hz -1.5dB；3kHz +1dB。"),
    ],
    "电影对白": [
        ("Channel EQ", "通道均衡器", "HPF 60-80Hz；250Hz 轻减；3kHz +0.8dB。"),
        ("Compressor", "压缩器", "Ratio 1.5-2:1；Threshold -24dB；Attack 20ms；Release 180ms。"),
    ],
    "广告人声": [
        ("Channel EQ", "通道均衡器", "HPF 80Hz；3.5kHz +2.5dB；10kHz +1.5dB。"),
        ("Compressor", "压缩器", "Ratio 3:1；Threshold -24dB；Attack 6ms；Release 90ms。"),
        ("Limiter", "限制器", "Ceiling -0.8dB。"),
    ],
    "Vlog环境": [
        ("Channel EQ", "通道均衡器", "人声 HPF 85Hz；环境轨 LPF 10kHz 轻柔化。"),
        ("Compressor", "压缩器", "人声 Ratio 2:1；环境声只轻压 1.5:1。"),
        ("Mixer Fader", "混音器推子", "环境声通常压到 -18 到 -12dB。"),
    ],
    "BGM柔化": [
        ("Channel EQ", "通道均衡器", "BGM 1.5-4kHz -2到-4dB；HPF 50Hz；10kHz -1dB。"),
        ("Compressor", "压缩器", "Ratio 1.5:1；Threshold -18dB；Release 250ms。"),
    ],
    "脚步增强": [
        ("Channel EQ", "通道均衡器", "120Hz +2dB；2.5kHz +2dB；8kHz +1dB。"),
        ("Compressor", "压缩器", "Ratio 3:1；Attack 3ms；Release 60ms。"),
    ],
    "冲击增强": [
        ("Channel EQ", "通道均衡器", "80Hz +3dB；120Hz +2dB；3kHz +2dB。"),
        ("Compressor", "压缩器", "Ratio 4:1；Attack 2ms；Release 80ms。"),
        ("Limiter", "限制器", "Ceiling -1dB。"),
    ],
    "梦境回忆": [
        ("Reverb", "混响", "Hall；Pre-delay 25ms；Decay 2.0s；Wet 20-30%。"),
        ("Delay", "延迟", "Time 1/8 或 250ms；Feedback 12-20%；Mix 8-15%。"),
        ("Channel EQ", "通道均衡器", "LPF 6kHz；HPF 120Hz。"),
    ],
    "广播喇叭": [
        ("Channel EQ", "通道均衡器", "HPF 250Hz；LPF 5kHz；2kHz +4dB。"),
        ("Distortion", "失真", "Drive 8-15%；Mix 20-30%。"),
        ("Reverb", "混响", "Room；Wet 8-12%；Decay 0.8s。"),
    ],
    "水下闷声": [
        ("Channel EQ", "通道均衡器", "LPF 800Hz-1.5kHz；120Hz +2dB；HPF 40Hz。"),
        ("Reverb", "混响", "Wet 18-25%；Decay 1.5s。"),
    ],
    "耳鸣压迫": [
        ("Channel EQ", "通道均衡器", "主体 LPF 1.2kHz；同时加 6-8kHz 窄带轻响。"),
        ("Limiter", "限制器", "Ceiling -1dB，防止耳鸣音刺破。"),
    ],
}

AUDIO_INTENSITY_GUIDE = [
    ("轻度", "干净素材/怕毁声音", "Voice Isolation 取建议下限；EQ 增减减半；Compressor Ratio 1.5-2:1；De-Esser Reduction 2-3dB。"),
    ("标准", "大多数口播/采访", "按卡片参数直接做；Limiter Ceiling -1dB；听到齿音、发闷、抽吸再微调。"),
    ("重度", "救急/短视频强处理", "Voice Isolation 取建议上限但别超过水声；EQ 增减可到 1.5倍；Compressor Ratio 3-4:1；Limiter 更积极。"),
]

AUDIO_TROUBLESHOOTING_GUIDE = [
    "发闷：降低 Voice Isolation / De-Reverb，少切 3kHz 以上，高频 8-10kHz +0.5到+1dB。",
    "刺耳：De-Esser 增加 1-2dB Reduction，或 6-8kHz -1dB。",
    "太薄：HPF 频率降低 10-20Hz，120-180Hz +0.5到+1.5dB。",
    "忽大忽小：先 Dialogue Leveler，再 Compressor；不要只靠 Limiter 硬顶。",
]


def resolve_major_from_text(text: str) -> int:
    match = re.search(r"\d+", str(text or ""))
    return int(match.group(0)) if match else 0


def apply_macos_window_level(widget: QWidget) -> None:
    if platform.system() != "Darwin":
        return
    try:
        native_id = int(widget.winId())
        import objc  # type: ignore
        from AppKit import NSFloatingWindowLevel  # type: ignore

        view = objc.objc_object(c_void_p=native_id)
        window = view.window() if view is not None and hasattr(view, "window") else None
        if window is not None:
            window.setLevel_(NSFloatingWindowLevel)
            window.setCollectionBehavior_(window.collectionBehavior() | (1 << 7))
    except Exception:
        pass


def bring_window_to_front(window: QWidget) -> None:
    window.show()
    if hasattr(window, "showNormal"):
        window.showNormal()
    window.raise_()
    window.activateWindow()
    if platform.system() == "Darwin":
        try:
            native_id = int(window.winId())
            import objc  # type: ignore
            from AppKit import NSApplication  # type: ignore

            view = objc.objc_object(c_void_p=native_id)
            ns_window = view.window() if view is not None and hasattr(view, "window") else None
            if ns_window is not None:
                ns_window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass


def set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


class SingleInstanceGuard:
    def __init__(self, name: str) -> None:
        self.server: QLocalServer | None = None
        self.already_running = False

        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(120):
            socket.write(b"raise")
            socket.flush()
            socket.waitForBytesWritten(120)
            self.already_running = True
            socket.disconnectFromServer()
            return

        QLocalServer.removeServer(name)
        self.server = QLocalServer()
        if not self.server.listen(name):
            self.already_running = True

    def bind_window(self, window: QWidget) -> None:
        if not self.server:
            return

        def on_new_connection() -> None:
            while self.server and self.server.hasPendingConnections():
                socket = self.server.nextPendingConnection()
                socket.readyRead.connect(lambda s=socket: s.readAll())
                socket.disconnected.connect(socket.deleteLater)
            bring_window_to_front(window)
            QTimer.singleShot(120, lambda: bring_window_to_front(window))

        self.server.newConnection.connect(on_new_connection)


def is_resolve_process_running() -> bool:
    if sys.platform != "win32":
        return True
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=1.5,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        return False
    stdout = result.stdout or ""
    return '"Resolve.exe"' in stdout or "Resolve.exe" in stdout


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
QLabel#SectionTitle {
    color: #334155;
    font-weight: 700;
    padding: 0 0 2px 0;
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


EYE_CARE_STYLE = APP_STYLE + """
QWidget {
    background: #f3f6ec;
    color: #243024;
}
QMainWindow { background: #e7eddc; }
QFrame#Shell, QFrame#Panel, QFrame#StatCard, QGroupBox, QTabWidget::pane {
    background: #fbfcf4;
    border-color: #cbd8ba;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {
    background: #fffff8;
    color: #243024;
    border-color: #bfceb0;
}
QPushButton {
    background: #fffff8;
    color: #243024;
    border-color: #bfceb0;
}
QPushButton:hover { background: #eef6dc; border-color: #7aa35a; }
QTabBar::tab { background: #e9f0df; color: #526247; border-color: #cbd8ba; }
QTabBar::tab:selected { background: #fbfcf4; color: #4d7c0f; border-top-color: #65a30d; }
QProgressBar { background: #dfe8d2; border-color: #c4d4b4; color: #334229; }
QProgressBar::chunk, QSlider::sub-page:horizontal { background: #65a30d; }
QCheckBox::indicator:checked { background: #84cc16; border-color: #4d7c0f; }
QLabel#Title { color: #172417; }
QLabel#SectionTitle { color: #334229; }
QLabel#Subtitle, QLabel#Muted { color: #62715c; }
"""


DARK_STYLE = APP_STYLE + """
QToolTip {
    background: #020617;
    color: #e5e7eb;
    border-color: #475569;
}
QWidget {
    background: #111827;
    color: #e5e7eb;
}
QMainWindow { background: #020617; }
QFrame#Shell {
    background: #0f172a;
    border-color: #334155;
}
QFrame#Panel, QFrame#StatCard, QGroupBox, QTabWidget::pane {
    background: #111827;
    border-color: #334155;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {
    background: #020617;
    color: #e5e7eb;
    border-color: #475569;
}
QPushButton {
    background: #1f2937;
    color: #f8fafc;
    border-color: #475569;
}
QPushButton:hover { background: #334155; border-color: #f59e0b; }
QTabBar::tab { background: #1f2937; color: #cbd5e1; border-color: #334155; }
QTabBar::tab:selected { background: #0f172a; color: #fbbf24; border-top-color: #60a5fa; }
QProgressBar { background: #1e293b; border-color: #334155; color: #e5e7eb; }
QProgressBar::chunk { background: #f59e0b; }
QSlider::groove:horizontal { background: #334155; }
QSlider::sub-page:horizontal { background: #60a5fa; }
QSlider::handle:horizontal { background: #0f172a; border-color: #f59e0b; }
QCheckBox { color: #e5e7eb; }
QCheckBox::indicator { background: #020617; border-color: #64748b; }
QCheckBox::indicator:checked { background: #f59e0b; border-color: #fbbf24; }
QLabel#Title { color: #f8fafc; }
QLabel#SectionTitle { color: #e2e8f0; }
QLabel#Subtitle, QLabel#Muted { color: #94a3b8; }
QLabel#BadgeOk { color: #a7f3d0; background: #064e3b; border-color: #047857; }
QLabel#BadgeWarn { color: #fde68a; background: #78350f; border-color: #d97706; }
QHeaderView::section { background: #1f2937; color: #e5e7eb; border-color: #334155; }
QTableWidget, QListWidget { background: #020617; color: #e5e7eb; gridline-color: #334155; }
"""


THEME_STYLES = {
    "default": APP_STYLE,
    "eye": EYE_CARE_STYLE,
    "dark": DARK_STYLE,
}

THEME_LABELS = {
    "default": "默认",
    "eye": "护眼",
    "dark": "黑夜",
}


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


def font_favorites_path() -> Path:
    return Path.home() / ".qinghe_bfd" / "font_favorites.json"


def plugin_data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def legacy_font_style_library_path() -> Path:
    return Path.home() / ".qinghe_bfd" / "font_style_library.json"


def font_style_library_path() -> Path:
    return plugin_data_dir() / "font_style_library.json"


def font_probe_rules_path() -> Path:
    return plugin_data_dir() / "font_probe_rules.json"


def install_id_path() -> Path:
    return Path.home() / ".qinghe_bfd" / "install_id"


def get_or_create_install_id() -> str:
    path = install_id_path()
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        path.parent.mkdir(parents=True, exist_ok=True)
        value = uuid.uuid4().hex
        path.write_text(value, encoding="utf-8")
        return value
    except Exception:
        return uuid.uuid4().hex


def default_complex_cache_dir() -> Path:
    return Path.home() / ".qinghe_bfd" / "render_cache"


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


def read_font_probe_rules_summary(max_items: int = 80) -> str:
    path = font_probe_rules_path()
    if not path.exists():
        return "暂无新增字体规则。"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"读取字体规则失败: {exc}"
    rules = data.get("rules") if isinstance(data, dict) else []
    if not isinstance(rules, list) or not rules:
        return "暂无新增字体规则。"
    lines = []
    for item in rules[-max_items:]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        accepted = str(item.get("accepted", "")).strip()
        candidates = item.get("candidates") if isinstance(item.get("candidates"), list) else []
        candidate_text = " / ".join(str(value) for value in candidates[:4] if str(value).strip())
        if source and accepted:
            suffix = f" | 候选: {candidate_text}" if candidate_text else ""
            lines.append(f"- {source} => {accepted}{suffix}")
    return "\n".join(lines) if lines else "暂无新增字体规则。"


def build_feedback_payload(message: str) -> dict:
    return {
        "msg_type": "text",
        "content": {
            "text": (
                "【BFD 用户反馈】\n"
                f"版本: v{APP_VERSION}\n"
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"反馈内容:\n{message.strip()}\n\n"
                "--- 新增字体规则 ---\n"
                f"{read_font_probe_rules_summary()}\n\n"
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


def send_analytics_event_async(payload: dict) -> None:
    endpoint = ANALYTICS_ENDPOINT_URL.strip()
    if not endpoint:
        return

    def worker() -> None:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read(256)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


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


class SearchHighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.query = ""

    def set_query(self, query: str) -> None:
        self.query = query.strip()

    def _html(self, text: str) -> str:
        escaped = html_escape(text)
        if not self.query:
            return escaped
        pattern = re.compile(re.escape(self.query), re.IGNORECASE)
        return pattern.sub(
            lambda match: (
                '<span style="background-color:#fde68a; color:#b91c1c; '
                'font-weight:700;">' + html_escape(match.group(0)) + "</span>"
            ),
            escaped,
        )

    def paint(self, painter, option, index) -> None:  # noqa: ANN001
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        doc = QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setHtml(self._html(text))
        doc.setTextWidth(max(10, opt.rect.width() - 8))

        painter.save()
        painter.translate(opt.rect.left() + 4, opt.rect.top() + 2)
        doc.drawContents(painter, QRectF(0, 0, opt.rect.width() - 8, opt.rect.height() - 4))
        painter.restore()

    def sizeHint(self, option, index):  # noqa: ANN001, N802
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 24))
        return size


class DoubleClickLabel(QLabel):
    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802, ANN001
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


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


class DonationDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("捐赠支持")
        self.resize(640, 520)
        self.amount = DONATION_AMOUNTS[0]

        layout = QVBoxLayout(self)
        title = QLabel("自愿捐赠支持开发")
        title.setObjectName("Title")
        layout.addWidget(title)

        note = QLabel(
            "感谢支持清何黑帧夹帧检测。捐赠完全自愿，不对应功能解锁、抽奖、"
            "返利、投资权益或售后承诺。"
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)

        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel("金额"))
        self.amount_buttons: list[QPushButton] = []
        for amount in DONATION_AMOUNTS:
            button = QPushButton(f"{amount} 元")
            button.setCheckable(True)
            button.setChecked(amount == self.amount)
            button.clicked.connect(lambda checked=False, value=amount: self.set_amount(value))
            self.amount_buttons.append(button)
            amount_row.addWidget(button)
        amount_row.addStretch(1)
        layout.addLayout(amount_row)

        qr_row = QHBoxLayout()
        self.wechat_qr = self._build_qr_panel("微信", "wechat")
        self.alipay_qr = self._build_qr_panel("支付宝", "alipay")
        qr_row.addWidget(self.wechat_qr)
        qr_row.addWidget(self.alipay_qr)
        layout.addLayout(qr_row, 1)

        disclaimer = QLabel("使用前请自行做好项目备份；检测结果仅作辅助参考，最终判断仍需人工确认。")
        disclaimer.setWordWrap(True)
        disclaimer.setObjectName("Muted")
        layout.addWidget(disclaimer)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_qr()

    def _build_qr_panel(self, title: str, provider: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Panel")
        frame.provider = provider  # type: ignore[attr-defined]
        box = QVBoxLayout(frame)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: 700;")
        qr = QLabel()
        qr.setFixedSize(220, 220)
        qr.setAlignment(Qt.AlignCenter)
        qr.setObjectName("Muted")
        qr.setStyleSheet("border: 1px dashed #cad5e2; border-radius: 7px; background: #fbfcfe;")
        frame.qr_label = qr  # type: ignore[attr-defined]
        box.addWidget(label)
        box.addWidget(qr, 0, Qt.AlignCenter)
        return frame

    def set_amount(self, amount: int) -> None:
        self.amount = amount
        for button in self.amount_buttons:
            button.setChecked(button.text().startswith(f"{amount} "))
        self.refresh_qr()

    def refresh_qr(self) -> None:
        for frame in (self.wechat_qr, self.alipay_qr):
            provider = str(frame.provider)  # type: ignore[attr-defined]
            label: QLabel = frame.qr_label  # type: ignore[attr-defined]
            path = next(
                (candidate for candidate in (
                    DONATION_DIR / f"{provider}_{self.amount}.png",
                    DONATION_DIR / f"{provider}_{self.amount}.jpg",
                    DONATION_DIR / f"{provider}_{self.amount}.jpeg",
                ) if candidate.exists()),
                DONATION_DIR / f"{provider}_{self.amount}.png",
            )
            if path.exists():
                pixmap = QPixmap(str(path)).scaled(210, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label.setPixmap(pixmap)
                label.setText("")
            else:
                label.setPixmap(QPixmap())
                label.setText(f"{self.amount} 元\n待放置收款码")


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
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self.bridge = ResolveBridge()
        self.timelines: list[TimelineInfo] = []
        self.worker: SubmitWorker | None = None
        self.result_values: dict[str, QLabel] = {}
        self.result_records: list[dict] = []
        self.result_index = 0
        self.text_records: list[dict] = []
        self.text_index = -1
        self.text_match_indices: list[int] = []
        self.text_match_cursor = -1
        self.text_undo_stack: list[list[dict]] = []
        self.font_records: list[dict] = []
        self.available_fonts: list[str] = []
        self.font_aliases: dict[str, list[str]] = {}
        self.font_family_styles: dict[str, list[str]] = {}
        self.font_probe_rules: dict[str, list[str]] = {}
        self.font_probe_rule_items: list[dict] = []
        self.font_inventory_consent = False
        self._font_inventory_sent_this_session = False
        self.font_style_clipboard: dict | None = None
        self.font_style_library: list[dict] = []
        self.favorite_fonts: set[str] = set()
        self.resolve_version_text = ""
        self.install_id = get_or_create_install_id()
        self.session_started_at = time.time()
        self._updating_text_table = False
        self._zero_result_notice_shown = False
        self._marker_refresh_after_complete = False
        self._tab_animation: QPropertyAnimation | None = None
        self._active_animations: list[QPropertyAnimation] = []
        self._loading_timelines = False
        self._loading_settings = False
        self._control_fps = BASELINE_FPS
        self._resolve_seen_running = is_resolve_process_running()
        self._resolve_missing_ticks = 0
        self._last_timeline_uid = ""
        self._last_timeline_name = ""
        self._text_compact_mode = False
        self._font_compact_mode = False
        self._normal_geometry = None
        self.theme_name = "default"
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(700)
        self.progress_timer.timeout.connect(self.poll_detection_progress)
        self.resolve_watch_timer = QTimer(self)
        self.resolve_watch_timer.setInterval(1500)
        self.resolve_watch_timer.timeout.connect(self.close_when_resolve_exits)
        self.timeline_poll_timer = QTimer(self)
        self.timeline_poll_timer.setInterval(3000)
        self.timeline_poll_timer.timeout.connect(self.poll_timeline_change)
        self.font_auto_scan_timer = QTimer(self)
        self.font_auto_scan_timer.setInterval(6000)
        self.font_auto_scan_timer.timeout.connect(self.auto_scan_font_layers)

        shell = QFrame()
        shell.setObjectName("Shell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        root.addLayout(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(9)

        self.controls_panel = QWidget()
        controls = QVBoxLayout(self.controls_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(self._build_timeline_group())

        main_grid = QGridLayout()
        main_grid.setHorizontalSpacing(9)
        main_grid.setVerticalSpacing(8)
        main_grid.addWidget(self._build_detection_group(), 0, 0)
        main_grid.addWidget(self._build_threshold_group(), 0, 1)
        main_grid.addWidget(self._build_advanced_section(), 1, 0, 1, 2)
        controls.addLayout(main_grid)
        controls.addStretch(1)

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setFrameShape(QFrame.NoFrame)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.controls_scroll.setWidget(self.controls_panel)

        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(560)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.controls_scroll, 1)
        left_layout.addWidget(self._build_action_group())

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self._build_side_tabs())
        self.side_tabs.setMinimumWidth(340)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([680, 440])
        body.addWidget(self.main_splitter)
        root.addLayout(body, 1)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(8, 8, 8, 8)
        wrapper_layout.addWidget(shell)
        self.setCentralWidget(wrapper)
        self.install_button_motion()

        self.refresh_timelines()
        self.load_settings()
        self.refresh_timelines()
        self._capture_current_timeline_uid()
        self.resolve_version_text = self.bridge.resolve_version_string()
        self.load_font_favorites()
        self.load_font_style_library()
        self.load_font_probe_rules()
        self.load_available_fonts()
        self.refresh_font_list()
        self.refresh_font_style_library_list()
        self.update_fps_hint()
        self.on_complex_mode_changed(self.chk_complex.isChecked())
        self.resolve_watch_timer.start()
        self.timeline_poll_timer.start()
        self.font_auto_scan_timer.start()
        QTimer.singleShot(1200, lambda: self.track_usage_event("app_start"))
        self._log("Resolve API: " + ("已连接" if self.bridge.is_connected() else "未连接，使用离线参数模式"))

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("清何黑帧夹帧检测")
        title.setObjectName("Title")
        self.subtitle_label = DoubleClickLabel(f"v{APP_VERSION} / PySide6 参数控制台 / DaVinci Resolve Bridge")
        self.subtitle_label.setObjectName("Subtitle")
        set_tip(self.subtitle_label, "双击打开隐私与统计设置。")
        self.subtitle_label.doubleClicked.connect(self.open_privacy_settings_dialog)
        disclaimer = QLabel("免责声明：免费工具，按现状提供；使用前请备份工程，检测结果仅作辅助参考。")
        disclaimer.setObjectName("Muted")
        disclaimer.setWordWrap(True)
        set_tip(disclaimer, DISCLAIMER_TEXT)
        title_box.addWidget(title)
        title_box.addWidget(self.subtitle_label)
        title_box.addWidget(disclaimer)

        self.connection_badge = QLabel("已连接" if self.bridge.is_connected() else "离线参数")
        self.connection_badge.setObjectName("BadgeOk" if self.bridge.is_connected() else "BadgeWarn")
        self.connection_badge.setFixedHeight(34)
        self.connection_badge.setAlignment(Qt.AlignCenter)
        set_tip(self.connection_badge, "已连接表示控制台能读到当前 Resolve 工程；离线时仍可保存参数，稍后由检测引擎读取。")

        self.compact_restore_btn = QPushButton("完整面板")
        self.compact_restore_btn.setIcon(self.style().standardIcon(QStyle.SP_TitleBarUnshadeButton))
        self.compact_restore_btn.setFixedHeight(34)
        self.compact_restore_btn.hide()
        set_tip(self.compact_restore_btn, "退出文字/字体小窗，恢复完整检测面板。")
        self.compact_restore_btn.clicked.connect(self.restore_full_panel)

        self.donate_btn = QPushButton("捐赠")
        self.donate_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogYesButton))
        self.donate_btn.setFixedHeight(34)
        set_tip(self.donate_btn, "自愿捐赠支持开发；不对应功能解锁、抽奖、返利或投资权益。")
        self.donate_btn.clicked.connect(self.open_donation_dialog)

        self.theme_combo = QComboBox()
        self.theme_combo.setFixedHeight(34)
        self.theme_combo.setMinimumWidth(82)
        for key, label in THEME_LABELS.items():
            self.theme_combo.addItem(label, key)
        set_tip(self.theme_combo, "切换默认、护眼或黑夜主题。")
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)

        layout.addLayout(title_box, 1)
        layout.addWidget(self.theme_combo, 0, Qt.AlignTop)
        layout.addWidget(self.donate_btn, 0, Qt.AlignTop)
        layout.addWidget(self.connection_badge, 0, Qt.AlignTop)
        layout.addWidget(self.compact_restore_btn, 0, Qt.AlignTop)
        return layout

    def _build_timeline_group(self) -> QGroupBox:
        box = QGroupBox("时间线")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        timeline_grid = QGridLayout()
        timeline_grid.setHorizontalSpacing(8)
        timeline_grid.setVerticalSpacing(8)
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)

        self.timeline_combo = QComboBox()
        self.timeline_combo.setMinimumWidth(220)
        self.timeline_combo.setMaximumWidth(520)
        self.timeline_combo.setMinimumContentsLength(22)
        self.timeline_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.timeline_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        set_tip(self.timeline_combo, "选择要检测的 Resolve 时间线；默认会优先当前打开的时间线。")
        self.timeline_combo.currentIndexChanged.connect(self.on_timeline_changed)
        refresh = QPushButton("刷新")
        refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh.setFixedWidth(76)
        set_tip(refresh, "重新读取 DaVinci Resolve 当前工程内的时间线列表。")
        refresh.clicked.connect(self.refresh_timelines)
        self.read_marks_btn = QPushButton("入出点")
        self.read_marks_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.read_marks_btn.setFixedWidth(86)
        set_tip(self.read_marks_btn, "读取 Resolve 当前时间线的入点/出点，自动填入复杂模式需要的检测范围。")
        self.read_marks_btn.clicked.connect(self.fill_in_out_from_current_timeline_marks)
        self.full_timeline_btn = QPushButton("全时间线")
        self.full_timeline_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.full_timeline_btn.setFixedWidth(96)
        set_tip(self.full_timeline_btn, "清空手动入点/出点；普通检测会扫描整条时间线。复杂模式仍建议设置入出点，避免渲染过长。")
        self.full_timeline_btn.clicked.connect(self.use_full_timeline_range)

        self.io_in = QLineEdit()
        self.io_in.setMinimumWidth(128)
        self.io_in.setMaximumWidth(190)
        self.io_in.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.io_in.setPlaceholderText("01:00:00:00")
        set_tip(self.io_in, "限制检测起点。Resolve 19 API无法读取IO，请手动输入。复杂模式必须填写。")
        self.io_out = QLineEdit()
        self.io_out.setMinimumWidth(128)
        self.io_out.setMaximumWidth(190)
        self.io_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.io_out.setPlaceholderText("01:02:30:00")
        set_tip(self.io_out, "限制检测终点。复杂模式必须填写出点，避免渲染整条时间线导致过慢。")

        self.chk_batch_timelines = QCheckBox("批量检测时间线")
        self.chk_batch_timelines.setMaximumWidth(150)
        set_tip(self.chk_batch_timelines, "批量检测：勾选后可以选择多条时间线。开始检测会按列表顺序让 Resolve 自动切到每条时间线并写入对应标记。")
        self.chk_batch_timelines.toggled.connect(self.on_batch_toggled)

        self.batch_timeline_list = QListWidget()
        self.batch_timeline_list.setMinimumHeight(44)
        self.batch_timeline_list.setMaximumHeight(64)
        self.batch_timeline_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.batch_timeline_list.setEnabled(False)
        set_tip(self.batch_timeline_list, "勾选要批量检测的时间线；每条时间线会使用自己的帧率换算阈值。")

        target_label = QLabel("目标时间线")
        target_label.setFixedWidth(72)

        in_label = QLabel("入点")
        out_label = QLabel("出点")
        in_label.setFixedWidth(42)
        out_label.setFixedWidth(42)

        timeline_grid.addWidget(target_label, 0, 0)
        timeline_grid.addWidget(self.timeline_combo, 0, 1, 1, 3)
        timeline_grid.addWidget(refresh, 0, 4)
        timeline_grid.addWidget(self.read_marks_btn, 0, 5)
        timeline_grid.addWidget(in_label, 1, 0)
        timeline_grid.addWidget(self.io_in, 1, 1)
        timeline_grid.addWidget(out_label, 1, 2)
        timeline_grid.addWidget(self.io_out, 1, 3)
        timeline_grid.addWidget(self.full_timeline_btn, 1, 4, 1, 2)
        timeline_grid.setColumnStretch(1, 3)
        timeline_grid.setColumnStretch(3, 3)
        timeline_grid.setColumnMinimumWidth(4, 76)
        timeline_grid.setColumnMinimumWidth(5, 86)

        batch_row.addWidget(self.chk_batch_timelines)
        batch_row.addWidget(self.batch_timeline_list, 1)

        layout.addLayout(timeline_grid)
        layout.addLayout(batch_row)
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
        self.chk_duplicate = self._marker_check(
            "重复素材",
            "duplicate",
            True,
            "快速检测同一个素材文件/同源片段是否在时间线上重复使用；主要看文件路径、源时间段、轨道距离和时间距离，适合找误复制、重复铺轨。",
        )
        self.chk_content_dup = self._marker_check(
            "内容重复",
            "content_dup",
            False,
            "慢速画面比对：抽帧生成指纹后比较画面内容，即使文件名不同、转码过、重新导入过也可能找出重复；长时间线会明显变慢。",
        )
        self.chk_opacity = self._marker_check("透明度/禁用", "opacity", True, "直接读取时间线属性，找不透明度为 0、低透明和禁用素材。")
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
        set_tip(self.stuck_frames, "按帧判断硬错误。默认 3 帧；切换时间线不会自动改这个数值。")
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
        set_tip(self.min_black_frames, "FFmpeg 黑场 d 参数按当前时间线帧率换算成秒；切换时间线不会自动改这个数值。")
        self.min_black_slider = self._make_slider(1, MAX_FRAME_THRESHOLD, DEFAULT_MIN_BLACK_FRAMES, self.min_black_frames)

        self.content_sample_interval = QSpinBox()
        self.content_sample_interval.setRange(1, MAX_FRAME_THRESHOLD)
        self.content_sample_interval.setValue(DEFAULT_CONTENT_SAMPLE_INTERVAL)
        set_tip(self.content_sample_interval, "内容重复检测每隔多少帧取一次指纹。数值越小越准，但越慢。")
        self.content_sample_slider = self._make_slider(
            1, MAX_FRAME_THRESHOLD, DEFAULT_CONTENT_SAMPLE_INTERVAL, self.content_sample_interval
        )
        for spin in (
            self.stuck_frames,
            self.suspect_frames,
            self.pixel_threshold,
            self.min_black_frames,
            self.content_sample_interval,
        ):
            spin.setMaximumWidth(84)

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
        layout.setColumnStretch(2, 0)
        self.fps_hint = QLabel("当前按 25fps 基准换算。")
        self.fps_hint.setObjectName("Muted")
        set_tip(self.fps_hint, "帧数阈值固定按当前填写值使用；切换时间线不会自动改数值。")
        layout.addWidget(self.fps_hint, 6, 0, 1, 3)
        for widget in [self.stuck_frames, self.suspect_frames, self.min_black_frames]:
            widget.valueChanged.connect(lambda _value: self.update_fps_hint())
        return box

    def _build_advanced_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.advanced_toggle_btn = QPushButton("▶ 高级选项")
        self.advanced_toggle_btn.setCheckable(True)
        self.advanced_toggle_btn.setChecked(False)
        self.advanced_toggle_btn.clicked.connect(self.toggle_advanced_options)
        set_tip(self.advanced_toggle_btn, "展开或折叠不常用设置。")
        self.advanced_group = self._build_advanced_group()
        self.advanced_group.setVisible(False)
        layout.addWidget(self.advanced_toggle_btn)
        layout.addWidget(self.advanced_group)
        return section

    def toggle_advanced_options(self, checked: bool) -> None:
        self.advanced_group.setVisible(checked)
        self.advanced_toggle_btn.setText("▼ 高级选项" if checked else "▶ 高级选项")

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
        self.chk_analytics = QCheckBox("匿名使用统计")
        self.chk_analytics.setChecked(True)

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
        self.complex_cache_dir = QLineEdit(str(default_complex_cache_dir()))
        self.complex_cache_dir.setMinimumWidth(260)
        set_tip(self.complex_cache_dir, "复杂模式临时渲染视频的存放位置；检测完成后会自动删除本次缓存视频。")
        self.browse_complex_cache_btn = QPushButton("选择")
        self.browse_complex_cache_btn.clicked.connect(self.choose_complex_cache_dir)
        set_tip(self.browse_complex_cache_btn, "选择复杂模式缓存视频目录。")
        layout.addWidget(QLabel("缓存视频位置"), 4, 0)
        cache_row = QHBoxLayout()
        cache_row.addWidget(self.complex_cache_dir, 1)
        cache_row.addWidget(self.browse_complex_cache_btn)
        layout.addLayout(cache_row, 4, 1)

        self.complex_hint.setObjectName("Muted")
        set_tip(self.complex_hint, "复杂模式会产生临时渲染文件，用最终画面做检测；调色后的坏帧要看最终像素，所以必须依赖它。")
        layout.addWidget(self.complex_hint, 5, 0, 1, 2)
        return box

    def _build_action_group(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.progress_label = QLabel("待机")
        self.progress_label.setMinimumWidth(72)
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
        self.font_tab = self._build_font_tab()
        self.log_tab = self._build_log_tab()
        self.side_tabs.addTab(self.results_tab, "结果")
        self.side_tabs.addTab(self.audio_tab, "音频")
        self.side_tabs.addTab(self.text_tab, "文字")
        self.side_tabs.addTab(self.font_tab, "字体")
        text_tab_index = self.side_tabs.indexOf(self.text_tab)
        if text_tab_index > 2:
            self.side_tabs.removeTab(text_tab_index)
            self.side_tabs.insertTab(2, self.text_tab, "\u6587\u5b57")
        self.side_tabs.setCurrentWidget(self.results_tab)
        self.side_tabs.currentChanged.connect(self.animate_current_tab)
        set_tip(self.side_tabs, "结果、音频扫描、文字和字体工具会一直留在主界面右侧，检测完成后自动回到结果页。")
        return self.side_tabs

    def restore_full_panel(self) -> None:
        if self._font_compact_mode:
            self.set_font_compact_mode(False)
        if self._text_compact_mode:
            self.set_text_compact_mode(False)

    def set_text_compact_mode(self, enabled: bool) -> None:
        if enabled == self._text_compact_mode:
            return
        self._text_compact_mode = enabled
        if enabled:
            if self._font_compact_mode:
                self.set_font_compact_mode(False)
            self._normal_geometry = self.geometry()
            self.setMinimumSize(520, 420)
            self.side_tabs.setCurrentWidget(self.text_tab)
            self.left_panel.hide()
            self.side_tabs.tabBar().hide()
            self.text_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
            self.text_table.setColumnWidth(0, 46)
            self.text_table.setColumnWidth(1, 96)
            self.text_table.setColumnWidth(2, 48)
            self.compact_restore_btn.show()
            self.resize(560, 520)
        else:
            self.setMinimumSize(960, 640)
            self.left_panel.show()
            self.side_tabs.tabBar().show()
            self.text_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
            if not self._font_compact_mode:
                self.compact_restore_btn.hide()
            if self._normal_geometry is not None:
                self.setGeometry(self._normal_geometry)
            else:
                self.resize(1180, 780)

    def set_font_compact_mode(self, enabled: bool) -> None:
        if enabled == self._font_compact_mode:
            return
        self._font_compact_mode = enabled
        if enabled:
            if self._text_compact_mode:
                self.set_text_compact_mode(False)
            self._normal_geometry = self.geometry()
            self.setMinimumSize(980, 680)
            self.side_tabs.setCurrentWidget(self.font_tab)
            self.left_panel.hide()
            self.side_tabs.tabBar().hide()
            self.font_list.setMaximumHeight(190)
            self.font_preview_image.setMinimumHeight(130)
            self.font_preview_image.setMaximumHeight(150)
            self.font_table.setColumnWidth(4, 360)
            self.font_table.setColumnWidth(6, 380)
            self.compact_restore_btn.show()
            self.resize(1180, 780)
        else:
            self.setMinimumSize(960, 640)
            self.left_panel.show()
            self.side_tabs.tabBar().show()
            self.font_list.setMaximumHeight(130)
            self.font_preview_image.setMinimumHeight(86)
            self.font_preview_image.setMaximumHeight(112)
            self.font_table.setColumnWidth(4, 180)
            self.font_table.setColumnWidth(6, 260)
            if not self._text_compact_mode:
                self.compact_restore_btn.hide()
            if self._normal_geometry is not None:
                self.setGeometry(self._normal_geometry)
            else:
                self.resize(1180, 780)

    def _build_results_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_result_group())
        self.result_list = ResultTextEdit()
        self.result_list.setReadOnly(True)
        self.result_list.setMinimumHeight(140)
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

        self.text_initial_panel = QFrame()
        self.text_initial_panel.setObjectName("Panel")
        initial_layout = QVBoxLayout(self.text_initial_panel)
        initial_layout.setContentsMargins(14, 12, 14, 12)
        initial_layout.setSpacing(10)
        initial_title = QLabel("检测时间线文字")
        initial_title.setObjectName("SectionTitle")
        initial_hint = QLabel("先选择要读取的文字类型；检测完成后再进入搜索、替换和表格编辑。")
        initial_hint.setObjectName("Muted")
        initial_hint.setWordWrap(True)
        initial_row = QHBoxLayout()
        initial_row.setContentsMargins(0, 0, 0, 0)
        self.text_scan_srt = QCheckBox("SRT")
        self.text_scan_srt.setChecked(True)
        self.text_scan_text = QCheckBox("Text")
        self.text_scan_textplus = QCheckBox("TXT+")
        self.text_initial_scan_btn = QPushButton("检测时间线文本")
        self.text_initial_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.text_initial_scan_btn.clicked.connect(self.scan_text_layers)
        initial_row.addWidget(self.text_scan_srt)
        initial_row.addWidget(self.text_scan_text)
        initial_row.addWidget(self.text_scan_textplus)
        initial_row.addStretch(1)
        initial_row.addWidget(self.text_initial_scan_btn)
        initial_layout.addWidget(initial_title)
        initial_layout.addWidget(initial_hint)
        initial_layout.addLayout(initial_row)
        layout.addWidget(self.text_initial_panel)

        self.text_search_panel = QFrame()
        self.text_search_panel.setObjectName("Panel")
        search_row = QHBoxLayout(self.text_search_panel)
        search_row.setContentsMargins(10, 8, 10, 8)
        search_row.setSpacing(8)
        self.text_search = QLineEdit()
        self.text_search.setPlaceholderText("搜索 SRT / 字幕 / 文字层")
        self.text_scan_btn = QPushButton("查找")
        self.text_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.text_scan_btn.clicked.connect(self.scan_text_layers)
        self.text_search.returnPressed.connect(self.scan_text_layers)
        self.text_next_match_btn = QPushButton("\u4e0b\u4e00\u4e2a\u5339\u914d")
        self.text_next_match_btn.clicked.connect(self.jump_to_next_text_match)
        search_row.addWidget(self.text_search, 1)
        search_row.addWidget(self.text_scan_btn)
        search_row.addWidget(self.text_next_match_btn)
        layout.addWidget(self.text_search_panel)

        self.text_replace_panel = QFrame()
        self.text_replace_panel.setObjectName("Panel")
        replace_row = QHBoxLayout(self.text_replace_panel)
        replace_row.setContentsMargins(10, 8, 10, 8)
        replace_row.setSpacing(8)
        self.text_replace = QLineEdit()
        self.text_replace.setPlaceholderText("\u66ff\u6362\u4e3a")
        self.text_replace_all_btn = QPushButton("\u6279\u91cf\u66ff\u6362")
        self.text_replace_all_btn.clicked.connect(self.replace_matched_text_items)
        self.text_undo_btn = QPushButton("撤回修改")
        self.text_undo_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.text_undo_btn.setEnabled(False)
        self.text_undo_btn.clicked.connect(self.undo_last_text_change)
        self.text_delete_btn = QPushButton("\u5220\u9664")
        self.text_delete_btn.clicked.connect(self.delete_selected_text_item)
        replace_row.addWidget(self.text_replace, 1)
        replace_row.addWidget(self.text_replace_all_btn)
        replace_row.addWidget(self.text_undo_btn)
        replace_row.addWidget(self.text_delete_btn)
        layout.addWidget(self.text_replace_panel)

        text_table_panel = QFrame()
        text_table_panel.setObjectName("Panel")
        text_table_layout = QVBoxLayout(text_table_panel)
        text_table_layout.setContentsMargins(10, 8, 10, 8)
        text_table_layout.setSpacing(6)
        text_table_title = QLabel("文字列表")
        text_table_title.setObjectName("SectionTitle")
        text_table_layout.addWidget(text_table_title)
        self.text_table = QTableWidget(0, 4)
        self.text_table.setHorizontalHeaderLabels(["#", "Timecode", "Track", "Text"])
        self.text_table.setMinimumHeight(150)
        self.text_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.text_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.text_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )
        self.text_table.setWordWrap(True)
        self.text_table.verticalHeader().setVisible(False)
        self.text_table.horizontalHeader().setStretchLastSection(False)
        self.text_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.text_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.text_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.text_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.text_highlight_delegate = SearchHighlightDelegate(self.text_table)
        self.text_table.setItemDelegateForColumn(3, self.text_highlight_delegate)
        self.text_table.cellDoubleClicked.connect(self.on_text_cell_double_clicked)
        self.text_table.cellChanged.connect(self.on_text_cell_changed)
        text_table_layout.addWidget(self.text_table, 1)
        layout.addWidget(text_table_panel, 1)

        self.text_status = QLabel("未扫描文字层。")
        self.text_status.setObjectName("Muted")
        layout.addWidget(self.text_status)

        self.text_table_panel = text_table_panel
        for widget in (self.text_search_panel, self.text_replace_panel, self.text_table_panel, self.text_status):
            widget.hide()
        return tab

    def _build_font_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        top_panel = QFrame()
        top_panel.setObjectName("Panel")
        top = QHBoxLayout(top_panel)
        top.setContentsMargins(10, 8, 10, 8)
        top.setSpacing(8)
        self.font_search = QLineEdit()
        self.font_search.setPlaceholderText("搜索字体 / 中文 / PostScript 名称")
        self.font_search.textChanged.connect(self.refresh_font_list)
        self.font_target = QLineEdit()
        self.font_target.setPlaceholderText("目标字体名称")
        set_tip(self.font_target, "Text+ 通常需要字体的英文或 PostScript 名称，例如 TangXianBinSong。")
        self.font_style_combo = QComboBox()
        self.font_style_combo.setMinimumWidth(128)
        set_tip(self.font_style_combo, "选择当前字体家族的粗细/样式，例如 Regular、Bold、502L、506L。")
        self.font_style_combo.currentIndexChanged.connect(self.on_font_style_changed)
        self.font_scan_btn = QPushButton("扫描时间线字体")
        self.font_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        self.font_scan_btn.clicked.connect(self.scan_font_layers)
        top.addWidget(self.font_search, 1)
        top.addWidget(self.font_target, 1)
        top.addWidget(QLabel("粗细"))
        top.addWidget(self.font_style_combo)
        top.addWidget(self.font_scan_btn)
        layout.addWidget(top_panel)

        main_split = QSplitter(Qt.Horizontal)
        main_split.setChildrenCollapsible(False)
        browser_panel = QFrame()
        browser_panel.setObjectName("Panel")
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(10, 8, 10, 8)
        browser_layout.setSpacing(7)
        browser_title_row = QHBoxLayout()
        browser_title = QLabel("字体库")
        browser_title.setObjectName("SectionTitle")
        fav_row = QHBoxLayout()
        self.font_favorite_only = QCheckBox("收藏")
        self.font_favorite_only.toggled.connect(self.refresh_font_list)
        self.font_add_favorite_btn = QPushButton("收藏")
        self.font_add_favorite_btn.clicked.connect(self.add_selected_font_favorite)
        self.font_remove_favorite_btn = QPushButton("取消")
        self.font_remove_favorite_btn.clicked.connect(self.remove_selected_font_favorite)
        browser_title_row.addWidget(browser_title)
        browser_title_row.addStretch(1)
        browser_layout.addLayout(browser_title_row)
        fav_row.addWidget(self.font_favorite_only)
        fav_row.addStretch(1)
        fav_row.addWidget(self.font_add_favorite_btn)
        fav_row.addWidget(self.font_remove_favorite_btn)
        browser_layout.addLayout(fav_row)
        self.font_list = QListWidget()
        self.font_list.setMinimumHeight(150)
        self.font_list.setMaximumHeight(260)
        self.font_list.itemSelectionChanged.connect(self.on_font_selection_changed)
        self.font_list.itemDoubleClicked.connect(lambda _item: self.apply_font_to_selected_layer())
        browser_layout.addWidget(self.font_list, 1)

        self.font_preview_image = QLabel()
        self.font_preview_image.setMinimumHeight(122)
        self.font_preview_image.setMaximumHeight(168)
        self.font_preview_image.setAlignment(Qt.AlignCenter)
        self.font_preview_image.setObjectName("Panel")
        set_tip(self.font_preview_image, "切换字体时生成本地图片预览；如果系统实际 fallback 到别的字体，会显示 Font Not Found 提示。")
        browser_layout.addWidget(self.font_preview_image)

        layers_panel = QFrame()
        layers_panel.setObjectName("Panel")
        layers_layout = QVBoxLayout(layers_panel)
        layers_layout.setContentsMargins(10, 8, 10, 8)
        layers_layout.setSpacing(7)
        layers_title = QLabel("时间线文字层")
        layers_title.setObjectName("SectionTitle")
        layers_layout.addWidget(layers_title)

        self.font_table = QTableWidget(0, 7)
        self.font_table.setHorizontalHeaderLabels(["#", "Timecode", "类型", "轨道", "当前字体", "状态", "文字 / 说明"])
        self.font_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.font_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.font_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.font_table.setWordWrap(False)
        self.font_table.setTextElideMode(Qt.ElideRight)
        self.font_table.verticalHeader().setVisible(False)
        self.font_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.font_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.font_table.setColumnWidth(4, 180)
        self.font_table.setColumnWidth(6, 260)
        self.font_table.cellDoubleClicked.connect(lambda _row, _col: self.jump_to_selected_font_item())
        self.font_table.itemSelectionChanged.connect(lambda: self.update_font_preview(self.selected_font_name()))
        layers_layout.addWidget(self.font_table, 1)
        main_split.addWidget(browser_panel)
        main_split.addWidget(layers_panel)
        main_split.setSizes([430, 690])
        layout.addWidget(main_split, 1)

        lower_split = QSplitter(Qt.Horizontal)
        lower_split.setChildrenCollapsible(False)
        style_panel = QFrame()
        style_panel.setObjectName("Panel")
        style_layout = QVBoxLayout(style_panel)
        style_layout.setContentsMargins(10, 8, 10, 8)
        style_layout.setSpacing(7)
        style_title = QLabel("本地 Text+ 样式库")
        style_title.setObjectName("SectionTitle")
        style_layout.addWidget(style_title)
        library_row = QHBoxLayout()
        self.font_style_library_list = QListWidget()
        self.font_style_library_list.setMaximumHeight(92)
        self.font_style_library_list.itemSelectionChanged.connect(self.on_font_style_library_selection_changed)
        set_tip(self.font_style_library_list, "本地 Text+ 样式库；选择样式后会载入预览，也可直接应用到选中的 Text+。")
        library_buttons = QVBoxLayout()
        self.font_save_style_btn = QPushButton("保存样式")
        set_tip(self.font_save_style_btn, "把当前复制的 Text+ 样式保存到本地样式库；没有复制时会先尝试复制当前选中 Text+。")
        self.font_save_style_btn.clicked.connect(self.save_copied_textplus_style_to_library)
        self.font_load_style_btn = QPushButton("载入样式")
        set_tip(self.font_load_style_btn, "把样式库选中项载入为当前样式剪贴板，并刷新 16:9 预览。")
        self.font_load_style_btn.clicked.connect(self.load_selected_textplus_style_from_library)
        self.font_delete_style_btn = QPushButton("删除样式")
        set_tip(self.font_delete_style_btn, "删除样式库选中项，只影响本地样式库，不会修改时间线。")
        self.font_delete_style_btn.clicked.connect(self.delete_selected_textplus_style_from_library)
        library_buttons.addWidget(self.font_save_style_btn)
        library_buttons.addWidget(self.font_load_style_btn)
        library_buttons.addWidget(self.font_delete_style_btn)
        library_row.addWidget(self.font_style_library_list, 1)
        library_row.addLayout(library_buttons)
        style_layout.addLayout(library_row)

        self.font_style_preview_image = QLabel()
        self.font_style_preview_image.setMinimumHeight(54)
        self.font_style_preview_image.setMaximumHeight(88)
        self.font_style_preview_image.setAlignment(Qt.AlignCenter)
        self.font_style_preview_image.setObjectName("Panel")
        set_tip(self.font_style_preview_image, "16:9 标题安全区预览；用于快速判断样式在画幅中的大概位置、字号和颜色。")
        style_layout.addWidget(self.font_style_preview_image)

        srt_panel = QFrame()
        srt_panel.setObjectName("Panel")
        srt_layout = QVBoxLayout(srt_panel)
        srt_layout.setContentsMargins(10, 8, 10, 8)
        srt_layout.setSpacing(7)
        srt_title = QLabel("SRT 转 Text+")
        srt_title.setObjectName("SectionTitle")
        srt_layout.addWidget(srt_title)
        template_row = QHBoxLayout()
        self.caption_template_combo = QComboBox()
        self.caption_template_combo.addItem("内置默认 Text+ 模板", "")
        set_tip(
            self.caption_template_combo,
            "SRT 转 Text+ 使用的模板。\n\n"
            "新手做自定义模板：\n"
            "1. 在当前时间线新建一个 Text+，调好字体、字号、颜色、描边、阴影和位置。\n"
            "2. 把这个 Text+ 做成媒体池素材/模板，放在当前项目媒体池里，名字建议带“字幕模板”。\n"
            "3. 回到插件点“刷新模板”，在这里选择你的模板。\n"
            "4. 点“SRT转Text+”，插件会把 SRT 的文字和时间码铺到最上层新视频轨。\n\n"
            "提示：模板帧率最好和目标时间线一致；不一致时插件会提醒并自动补偿，但同帧率模板最稳。",
        )
        self.refresh_caption_templates_btn = QPushButton("刷新模板")
        set_tip(self.refresh_caption_templates_btn, "扫描当前项目媒体池，列出可能的 Text+ / 字幕模板；列表里会显示模板帧率，优先选和当前时间线相同 fps 的模板。")
        self.refresh_caption_templates_btn.clicked.connect(self.refresh_caption_templates)
        template_row.addWidget(QLabel("SRT模板"))
        template_row.addWidget(self.caption_template_combo, 1)
        template_row.addWidget(self.refresh_caption_templates_btn)
        srt_layout.addLayout(template_row)

        actions = QHBoxLayout()
        self.font_jump_btn = QPushButton("跳转")
        self.font_jump_btn.clicked.connect(self.jump_to_selected_font_item)
        self.font_apply_selected_btn = QPushButton("替换选中层")
        set_tip(self.font_apply_selected_btn, "只修改状态为可替换的 Text+；SRT 和普通 Text 会明确跳过。")
        self.font_apply_selected_btn.clicked.connect(self.apply_font_to_selected_layer)
        self.font_copy_style_btn = QPushButton("复制样式")
        set_tip(self.font_copy_style_btn, "复制选中 Text+ 的 Fusion 外观参数，不复制文字内容。Resolve 21+ 自带“粘贴属性”增强了部分剪辑属性复制；本插件在 Resolve 19/20/21 也能复制 Text+ 样式，用于向下兼容和批量处理。")
        self.font_copy_style_btn.clicked.connect(self.copy_selected_textplus_style)
        self.font_apply_style_btn = QPushButton("应用样式")
        set_tip(self.font_apply_style_btn, "把已复制样式应用到选中的一个或多个 Text+，保留每层原来的文字。适合批量同步字体、字号、颜色、描边、阴影、位置等 Text+ Fusion 参数。支持 Shift/Cmd 多选。")
        self.font_apply_style_btn.clicked.connect(self.apply_copied_textplus_style_to_selected)
        self.font_convert_srt_btn = QPushButton("SRT转Text+")
        set_tip(
            self.font_convert_srt_btn,
            "把当前时间线启用的 SRT 字幕转换成 Text+。\n\n"
            "怎么用：\n"
            "1. 先确认目标时间线是当前要转换的时间线。\n"
            "2. 默认可直接用“内置默认 Text+ 模板”。\n"
            "3. 想要自己的字幕样式，就先在达芬奇里做好一个 Text+ 模板，点“刷新模板”后选择它。\n"
            "4. 点击本按钮后，插件会在最上层新建视频轨，按 SRT 原时间码生成 Text+，并写入每条字幕文字。\n\n"
            "注意：如果模板 fps 和时间线 fps 不同，会先弹窗提示；直接继续会自动补偿时长。",
        )
        self.font_convert_srt_btn.clicked.connect(self.convert_srt_to_textplus)
        actions.addWidget(self.font_jump_btn)
        actions.addWidget(self.font_apply_selected_btn)
        actions.addWidget(self.font_copy_style_btn)
        actions.addWidget(self.font_apply_style_btn)
        actions.addWidget(self.font_convert_srt_btn)
        actions.addStretch(1)
        srt_layout.addLayout(actions)
        lower_split.addWidget(style_panel)
        lower_split.addWidget(srt_panel)
        lower_split.setSizes([560, 560])
        layout.addWidget(lower_split)

        self.font_style_note = QLabel("提示：Resolve 21+ 自带粘贴属性支持部分属性复制；本插件向下兼容 Resolve 19/20/21，可批量复制/应用 Text+ 字体、描边、阴影等样式。")
        self.font_style_note.setObjectName("Muted")
        self.font_style_note.setWordWrap(True)
        set_tip(self.font_style_note, "官方 Resolve 21 新功能指南提到 Paste Attributes 增强了片段颜色、标记、旗标等复制项；本插件通过 Fusion Text+ 参数读写实现旧版也可用的 Text+ 样式复制。")
        layout.addWidget(self.font_style_note)

        self.font_status = QLabel("未扫描字体层。")
        self.font_status.setObjectName("Muted")
        layout.addWidget(self.font_status)
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

        preset_box = QGroupBox("音频效果教程")
        preset_layout = QVBoxLayout(preset_box)
        preset_layout.setContentsMargins(10, 8, 10, 8)
        preset_layout.setSpacing(8)
        preset_top = QHBoxLayout()
        self.audio_preset_combo = QComboBox()
        for preset in AUDIO_EFFECT_PRESETS:
            self.audio_preset_combo.addItem(f"{preset['name']}  ·  {preset['type']}", preset)
        self.audio_preset_combo.currentIndexChanged.connect(self.on_audio_preset_changed)
        self.audio_copy_tutorial_btn = QPushButton("复制教程参数")
        self.audio_copy_tutorial_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        set_tip(self.audio_copy_tutorial_btn, "复制教程参数到剪贴板；需要在达芬奇 Fairlight 中手动添加效果器和填写参数。")
        self.audio_copy_tutorial_btn.clicked.connect(self.copy_audio_tutorial)
        preset_top.addWidget(self.audio_preset_combo, 1)
        preset_top.addWidget(self.audio_copy_tutorial_btn)
        preset_layout.addLayout(preset_top)
        self.audio_preset_detail = QTextEdit()
        self.audio_preset_detail.setReadOnly(True)
        self.audio_preset_detail.setMinimumHeight(150)
        self.audio_preset_detail.setMaximumHeight(210)
        self.audio_preset_detail.setLineWrapMode(QTextEdit.WidgetWidth)
        preset_layout.addWidget(self.audio_preset_detail)
        layout.addWidget(preset_box)
        QTimer.singleShot(0, self.on_audio_preset_changed)

        actions = QHBoxLayout()
        self.scan_audio_btn = QPushButton("扫描单声道")
        self.scan_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        set_tip(self.scan_audio_btn, "只读取时间线并列出单声道轨道/片段，不修改工程。")
        self.scan_audio_btn.clicked.connect(self.scan_mono_audio)

        self.mark_audio_btn = QPushButton("标记单声道")
        self.mark_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        set_tip(self.mark_audio_btn, "把识别出的单声道音频片段改为醒目的 Orange 颜色，便于人工复核。")
        self.mark_audio_btn.clicked.connect(self.mark_mono_audio)

        actions.addWidget(self.scan_audio_btn)
        actions.addWidget(self.mark_audio_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.audio_list = QTextEdit()
        self.audio_list.setReadOnly(True)
        self.audio_list.setMinimumHeight(150)
        self.audio_list.setMaximumHeight(210)
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
        self.log.setMinimumHeight(170)
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
            card.setProperty("accentColor", color)
            card.setStyleSheet(self.stat_card_style(color))
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

    def stat_card_style(self, color: str) -> str:
        if getattr(self, "theme_name", "default") == "dark":
            return (
                "QFrame#StatCard {"
                "background: #111827; border: 1px solid #334155;"
                f"border-top: 3px solid {color}; border-radius: 7px;"
                "}"
            )
        return (
            "QFrame#StatCard {"
            "background: #fbfcfe; border: 1px solid #d8e0ea;"
            f"border-top: 3px solid {color}; border-radius: 7px;"
            "}"
        )

    def refresh_result_card_styles(self) -> None:
        if not hasattr(self, "result_values"):
            return
        for label in self.result_values.values():
            card = label.parentWidget()
            if card is not None:
                color = str(card.property("accentColor") or "#35c4a1")
                card.setStyleSheet(self.stat_card_style(color))

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
        slider.setMinimumWidth(80)
        slider.setMaximumWidth(180)
        slider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
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
        slider.setMinimumWidth(80)
        slider.setMaximumWidth(180)
        slider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        set_tip(slider, spinbox.toolTip())
        return slider

    def refresh_timelines(self) -> None:
        self._loading_timelines = True
        self.timelines = self.bridge.list_timelines()
        current_identity = self.bridge.current_timeline_identity()
        current_uid = str(current_identity.get("uid", "")) if current_identity.get("ok") else ""
        current_name = str(current_identity.get("name", "")) if current_identity.get("ok") else ""
        current_combo_index = 0
        self.timeline_combo.clear()
        self.batch_timeline_list.clear()
        for tl in self.timelines:
            data = asdict(tl)
            label = f"{tl.index}. {tl.name}  /  {tl.fps:g} fps"
            self.timeline_combo.addItem(label, data)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, data)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            name_marks_current = "当前" in tl.name
            item.setCheckState(Qt.Checked if name_marks_current else Qt.Unchecked)
            is_current = bool(
                name_marks_current
                or (current_uid and tl.uid == current_uid)
                or (current_name and current_name in tl.name)
            )
            if is_current:
                current_combo_index = self.timeline_combo.count() - 1
                item.setCheckState(Qt.Checked)
            elif current_uid or current_name:
                item.setCheckState(Qt.Unchecked)
            self.batch_timeline_list.addItem(item)
        self.connection_badge.setText("已连接" if self.bridge.is_connected() else "离线参数")
        self.connection_badge.setObjectName("BadgeOk" if self.bridge.is_connected() else "BadgeWarn")
        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)
        if self.batch_timeline_list.count() > 0 and not any(
            self.batch_timeline_list.item(i).checkState() == Qt.Checked for i in range(self.batch_timeline_list.count())
        ):
            self.batch_timeline_list.item(0).setCheckState(Qt.Checked)
        if self.timeline_combo.count() > 0:
            self.timeline_combo.setCurrentIndex(current_combo_index)
        self._loading_timelines = False
        self._control_fps = self.selected_fps()
        self.update_fps_hint()

    def on_timeline_changed(self) -> None:
        if self._loading_timelines or self._loading_settings:
            return
        self._control_fps = self.selected_fps()
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

    def min_duration_seconds(self, fps: float | None = None) -> float:
        fps = fps or self.selected_fps()
        return self.min_black_frames.value() / max(1.0, float(fps))

    def update_fps_hint(self) -> None:
        if not hasattr(self, "fps_hint"):
            return
        fps = self.selected_fps()
        self.fps_hint.setText(
            f"当前 {fps:g}fps：夹帧≤{self.stuck_frames.value()}帧，可疑≤{self.suspect_frames.value()}帧，"
            f"最短黑场 {self.min_black_frames.value()}帧≈{self.min_duration_seconds(fps):.3f}秒；切换时间线不自动改阈值。"
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
        complex_mode = self.chk_complex.isChecked()
        data = {
            "theme": self.theme_name,
            "timeline_index": self.timeline_combo.currentIndex(),
            "stuck_frames": self.stuck_frames.value(),
            "suspect_frames": self.suspect_frames.value(),
            "pix_th": self.pixel_threshold.value(),
            "pix_th_unit": "percent",
            "min_black_frames": self.min_black_frames.value(),
            "content_sample_interval": self.content_sample_interval.value(),
            "complex_cache_dir": self.complex_cache_dir.text().strip(),
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
                "content_dup": complex_mode and self.chk_content_dup.isChecked(),
                "opacity": self.chk_opacity.isChecked(),
                "corrupt": self.chk_corrupt.isChecked(),
                "clear": self.chk_clear.isChecked(),
                "mark_hidden": self.chk_mark_hidden.isChecked(),
                "partial_opacity": self.chk_partial_opacity.isChecked(),
                "png_opaque": self.chk_png_opaque.isChecked(),
                "merge": self.chk_merge.isChecked(),
                "html": self.chk_html.isChecked(),
                "analytics": self.chk_analytics.isChecked(),
                "font_inventory_consent": bool(self.font_inventory_consent),
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
            if isinstance(data.get("theme"), str):
                self.apply_theme(str(data.get("theme") or "default"), update_combo=True, persist=False)
            has_current_timeline = any(
                "当前" in self.timeline_combo.itemText(index)
                for index in range(self.timeline_combo.count())
            )
            if (
                not self.bridge.is_connected()
                and not has_current_timeline
                and isinstance(data.get("timeline_index"), int)
                and self.timeline_combo.count() > 0
            ):
                self.timeline_combo.setCurrentIndex(max(0, min(self.timeline_combo.count() - 1, data["timeline_index"])))
            for name, widget in [
                ("content_sample_interval", self.content_sample_interval),
            ]:
                if isinstance(data.get(name), int):
                    widget.setValue(data[name])
            if isinstance(data.get("complex_cache_dir"), str) and data["complex_cache_dir"].strip():
                self.complex_cache_dir.setText(data["complex_cache_dir"].strip())
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
                "analytics": self.chk_analytics,
            }
            for key, widget in check_map.items():
                if isinstance(checks.get(key), bool):
                    widget.setChecked(checks[key])
            if isinstance(checks.get("font_inventory_consent"), bool):
                self.font_inventory_consent = bool(checks.get("font_inventory_consent"))
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

    def apply_theme(self, theme_name: str, update_combo: bool = True, persist: bool = True) -> None:
        theme = theme_name if theme_name in THEME_STYLES else "default"
        self.theme_name = theme
        app = QApplication.instance()
        if app:
            app.setStyleSheet(THEME_STYLES[theme])
        if update_combo and hasattr(self, "theme_combo"):
            index = self.theme_combo.findData(theme)
            if index >= 0 and self.theme_combo.currentIndex() != index:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(index)
                self.theme_combo.blockSignals(False)
        if persist and not self._loading_settings:
            self.save_settings()
        self.refresh_result_card_styles()

    def on_theme_changed(self, *_args) -> None:
        if not hasattr(self, "theme_combo"):
            return
        self.apply_theme(str(self.theme_combo.currentData() or "default"), update_combo=False, persist=True)

    def reset_threshold_defaults(self) -> None:
        fps = self.selected_fps()
        self.stuck_frames.setValue(DEFAULT_STUCK_FRAMES)
        self.suspect_frames.setValue(DEFAULT_SUSPECT_FRAMES)
        self.min_black_frames.setValue(DEFAULT_MIN_BLACK_FRAMES)
        self._control_fps = fps
        self.pixel_threshold.setValue(DEFAULT_PIXEL_THRESHOLD)
        self.content_sample_interval.setValue(DEFAULT_CONTENT_SAMPLE_INTERVAL)
        self.update_fps_hint()

    def choose_complex_cache_dir(self) -> None:
        current = self.complex_cache_dir.text().strip() or str(default_complex_cache_dir())
        selected = QFileDialog.getExistingDirectory(self, "选择复杂模式缓存目录", current)
        if selected:
            self.complex_cache_dir.setText(selected)

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
            "stuck_frames": self.stuck_frames.value(),
            "suspect_frames": self.suspect_frames.value(),
            "pix_th": self.pixel_threshold.value() / 100.0,
            "min_black_frames": self.min_black_frames.value(),
            "min_duration": self.min_black_frames.value() / max(1.0, timeline_fps),
            "content_sample_interval": self.content_sample_interval.value(),
            "manual_io_in": self.io_in.text().strip(),
            "manual_io_out": self.io_out.text().strip(),
            "complex_cache_dir": self.complex_cache_dir.text().strip() or str(default_complex_cache_dir()),
            "marker_types": {
                "error": self.chk_error.isChecked(),
                "suspect": self.chk_suspect.isChecked(),
                "scene": self.chk_scene.isChecked(),
                "gap": self.chk_gap.isChecked(),
                "opacity": self.chk_opacity.isChecked(),
                "duplicate": self.chk_duplicate.isChecked(),
                "content_dup": self.chk_content_dup.isChecked(),
                "mixed_cut": False,
            },
            "detect_duplicate": self.chk_duplicate.isChecked(),
            "detect_content_dup": complex_mode and self.chk_content_dup.isChecked(),
            "detect_mixed_cut": False,
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

    def track_usage_event(self, event_name: str, extra: dict | None = None) -> None:
        if not hasattr(self, "chk_analytics") or not self.chk_analytics.isChecked():
            return
        payload = {
            "event": event_name,
            "install_id": self.install_id,
            "app_version": APP_VERSION,
            "resolve_version": self.resolve_version_text,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "session_seconds": int(max(0, time.time() - self.session_started_at)),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        if extra:
            payload["extra"] = extra
        send_analytics_event_async(payload)

    def on_audio_preset_changed(self) -> None:
        if not hasattr(self, "audio_preset_combo"):
            return
        preset = self.audio_preset_combo.currentData() or {}
        if not isinstance(preset, dict):
            return
        self.audio_preset_detail.setPlainText(self.audio_preset_card_text(preset))

    def audio_fx_display_name(self, english_name: str, chinese_name: str) -> str:
        major = resolve_major_from_text(self.resolve_version_text)
        if major >= 20:
            return f"{chinese_name} / {english_name}"
        return f"{english_name} / {chinese_name}"

    def audio_preset_card_text(self, preset: dict) -> str:
        name = str(preset.get("name", "音频预设"))
        effects = AUDIO_BUILTIN_FX_CARDS.get(name, [])
        version = self.resolve_version_text or "未知版本"
        lines = [
            str(preset.get("summary", "")),
            "",
            f"Resolve {version}：{'中文效果器名优先' if resolve_major_from_text(version) >= 20 else '英文效果器名优先'}",
            "性质：教程参数参考，不会自动写入工程，也不是一键音频效果。",
            "操作：Fairlight 页 > Mixer > 对应轨道/片段 > Effects/FX 插槽；EQ/Dynamics 可直接用通道条手动设置。",
            "",
            "强度三档：",
        ]
        for label, scene, rule in AUDIO_INTENSITY_GUIDE:
            lines.append(f"- {label}：{scene}；{rule}")
        lines.extend([
            "",
            "内置效果器参数：",
        ])
        if not effects:
            lines.append(str(preset.get("params", "")))
        for index, (english_name, chinese_name, params) in enumerate(effects, 1):
            lines.append(f"{index}. {self.audio_fx_display_name(english_name, chinese_name)}")
            lines.append(f"   {params}")
        lines.extend([
            "",
            "听感校准：先关掉 Limiter 以外的红灯；人声峰值通常压到 -6~-3dB，最后 Limiter Ceiling -1dB。",
            *AUDIO_TROUBLESHOOTING_GUIDE,
        ])
        return "\n".join(lines)

    def copy_audio_tutorial(self) -> None:
        preset = self.audio_preset_combo.currentData() if hasattr(self, "audio_preset_combo") else {}
        name = str((preset or {}).get("name", "音频教程")) if isinstance(preset, dict) else "音频教程"
        if isinstance(preset, dict):
            text = self.audio_preset_card_text(preset)
            self.audio_preset_detail.setPlainText(text)
            QApplication.clipboard().setText(text)
        self.audio_summary.setText(
            f"{name}：已复制教程参数。请在达芬奇 Fairlight 里手动添加效果器，不会自动写入工程。"
        )
        self._log(self.audio_summary.text())

    def start_detection(self) -> None:
        try:
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
            self.clear_stale_progress_file()
            self._log(f"开始检测 {len(jobs)} 条时间线")
            self.track_usage_event(
                "detect_start",
                {
                    "job_count": len(jobs),
                    "batch": len(jobs) > 1,
                    "complex_mode": any(bool(job.get("complex_mode")) for job in jobs),
                    "content_dup": any(bool(job.get("detect_content_dup")) for job in jobs),
                    "corrupt": any(bool(job.get("detect_corrupt")) for job in jobs),
                },
            )
            self._marker_refresh_after_complete = False
            self.save_settings()
            self.animate_widget(self.start_btn)
            self.progress_timer.start()
            self.worker = SubmitWorker(self.bridge, jobs)
            self.worker.progress.connect(self.on_progress)
            self.worker.done.connect(self.on_done)
            self.worker.start()
        except Exception as exc:
            self.start_btn.setEnabled(True)
            self.progress_timer.stop()
            self.progress_label.setText("启动失败")
            message = f"启动检测失败：{exc}"
            self._log(message)
            QMessageBox.warning(self, "启动检测失败", message)

    def clear_stale_progress_file(self) -> None:
        try:
            path = progress_path()
            if path.exists():
                path.unlink()
        except Exception as exc:
            self._log(f"清理旧进度文件失败：{exc}")

    def prompt_complex_mode_for_risky_timelines(self, jobs: list[dict]) -> bool:
        if self.chk_complex.isChecked() or any(job.get("complex_mode") for job in jobs):
            return False
        risky_tokens = ("mix", "final", "output", "成片", "混剪", "合集")
        for job in jobs:
            timeline_name = str(job.get("timeline_name") or job.get("name") or "当前时间线")
            risk_message = ""
            risk_count = 0
            if self.bridge.is_connected():
                result = self.bridge.detect_complex_timeline_risk(int(job.get("timeline_index", 1)))
                if result and result.get("ok"):
                    risk_count = int(result.get("count", 0) or 0)
                    if risk_count > 0:
                        risk_message = f"检测到 {risk_count} 个疑似成片/Fusion/复合片段风险。"
            if not risk_message and any(token in timeline_name.lower() for token in risky_tokens):
                risk_message = "时间线命名疑似混剪/成片。"
            if not risk_message:
                continue
            prompt = (
                f"时间线“{timeline_name}”{risk_message}\n\n"
                "普通模式只做时间线结构和源素材检测，不会渲染最终画面；如果要检查调色、OFX、Fusion、叠加后的最终画面，请启用复杂模式。\n\n"
                "是否现在切换到复杂模式？"
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
            self._log("用户选择继续普通模式；疑似成片/Fusion/复合片段不会执行渲染深扫。")
            return False
        return False

    def clear_markers(self) -> None:
        if QMessageBox.question(self, "清除标记", "只清除当前时间线上的 [BFD] 检测标记，继续吗？") != QMessageBox.Yes:
            return
        ok, message = self.bridge.clear_current_bfd_markers()
        self._log(message)
        if ok:
            QMessageBox.information(self, "清除标记", message)
        else:
            QMessageBox.warning(self, "清除标记", message)

    def open_feedback_dialog(self) -> None:
        FeedbackDialog(self).exec()

    def open_donation_dialog(self) -> None:
        DonationDialog(self).exec()

    def open_privacy_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("隐私与统计")
        dialog.resize(520, 320)
        layout = QVBoxLayout(dialog)
        title = QLabel("匿名使用统计")
        title.setObjectName("Title")
        layout.addWidget(title)
        info = QLabel(
            "开启后会发送插件版本、Resolve版本、系统、启动次数、检测次数、会话时长和粗略地区。"
            "字体替换成功时，会发送新增字体映射规则，方便后续版本增强中文字体兼容。"
            "不会上传工程名、素材名、时间线内容、文件路径或原始IP。"
        )
        info.setWordWrap(True)
        info.setObjectName("Muted")
        layout.addWidget(info)
        check = QCheckBox("允许匿名使用统计")
        check.setChecked(self.chk_analytics.isChecked())
        layout.addWidget(check)
        font_inventory_check = QCheckBox("参与字体规则贡献：上传完整字体清单")
        font_inventory_check.setChecked(bool(self.font_inventory_consent))
        set_tip(font_inventory_check, "默认关闭。开启后会上传本机可见字体名称、别名和样式列表，用于整理公共字体规则库；不上传工程、素材或文件路径。")
        layout.addWidget(font_inventory_check)
        export_btn = QPushButton("导出字体规则数据")
        set_tip(export_btn, "导出 JSON：包含本机可见字体、别名、样式和已学习到的 Resolve 字体映射，方便手动汇总进新版本。")
        export_btn.clicked.connect(self.export_font_rules_data)
        layout.addWidget(export_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.Accepted:
            was_consent = bool(self.font_inventory_consent)
            self.chk_analytics.setChecked(check.isChecked())
            self.font_inventory_consent = bool(font_inventory_check.isChecked())
            self.save_settings()
            self._log("匿名使用统计：" + ("已开启" if check.isChecked() else "已关闭"))
            self._log("完整字体清单贡献：" + ("已开启" if self.font_inventory_consent else "已关闭"))
            if self.chk_analytics.isChecked() and self.font_inventory_consent and not was_consent:
                self.track_usage_event("font_inventory", self.build_font_rules_export_payload(include_inventory=True))
                self._font_inventory_sent_this_session = True

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

    def use_full_timeline_range(self) -> None:
        self.io_in.clear()
        self.io_out.clear()
        self.save_settings()
        self._log("已切换为全时间线检测：手动入点/出点已清空。")

    def scan_mono_audio(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.scan_mono_audio(
            int(selected.get("index", 1)),
            self.io_in.text().strip(),
            self.io_out.text().strip(),
        )
        self.render_audio_scan(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)

    def mark_mono_audio(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.mark_mono_audio(
            int(selected.get("index", 1)),
            self.io_in.text().strip(),
            self.io_out.text().strip(),
        )
        self.render_audio_scan(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)

    def fix_mono_audio(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.fix_mono_audio_to_stereo(
            int(selected.get("index", 1)),
            self.io_in.text().strip(),
            self.io_out.text().strip(),
        )
        self.render_audio_scan(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)

    def probe_audio_fx_api(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        self.audio_summary.setText("正在探测音频/Fairlight FX API...")
        QApplication.processEvents()
        result = self.bridge.probe_audio_fx_api(int(selected.get("index", 1)))
        self.render_audio_fx_probe(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "音频 FX API 探测完成。")))

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

    @staticmethod
    def font_language_tag(name: str) -> str:
        if any("\u4e00" <= char <= "\u9fff" for char in name):
            return "中"
        try:
            writing_systems = QFontDatabase.writingSystems(name)
            if any("Chinese" in str(system) for system in writing_systems):
                return "中"
        except Exception:
            pass
        lowered = name.lower()
        chinese_hints = (
            "hei",
            "song",
            "kai",
            "fang",
            "yuan",
            "ming",
            "cjk",
            "noto sans cjk",
            "pingfang",
            "songti",
            "heiti",
            "kaiti",
            "lanting",
            "hanzipen",
            "fz",
            "fangzheng",
            "founder",
            "hanyi",
            "zcool",
            "zihun",
            "tsanger",
            "maoken",
            "youshe",
            "cang er",
            "canger",
            "sanjigetang",
            "sanjizhu",
            "sanjibang",
            "shangshou",
            "nangou",
            "zaozigongfang",
            "reeji",
            "ruizi",
            "huakang",
            "dfkai",
            "dffangsong",
            "wenyue",
            "wenquanyi",
            "siyuan",
            "source han",
            "stsong",
            "stheiti",
            "stkaiti",
            "simsun",
            "simhei",
            "microsoft yahei",
            "microsoft jhenghei",
            "msyh",
            "msjh",
        )
        return "中" if any(hint in lowered for hint in chinese_hints) else "英"

    def font_sort_key(self, name: str) -> tuple[int, str]:
        has_cjk = any("\u4e00" <= char <= "\u9fff" for char in name)
        return (0 if self.font_language_tag(name) == "中" else 1, 0 if has_cjk else 1, name.casefold())

    def add_font_alias(self, name: str, aliases: list[str]) -> None:
        clean_name = str(name or "").strip()
        if not clean_name:
            return
        bucket = self.font_aliases.setdefault(clean_name, [])
        for alias in aliases:
            clean_alias = str(alias or "").strip()
            if clean_alias and clean_alias != clean_name and clean_alias not in bucket:
                bucket.append(clean_alias)

    def split_font_style(self, name: str) -> tuple[str, str]:
        text = str(name or "").strip()
        if not text:
            return "", ""
        postscript_map = getattr(self, "font_postscript_styles", {})
        if text in postscript_map:
            family, style = postscript_map[text]
            return str(family or "").strip(), str(style or "").strip()
        try:
            families = set(QFontDatabase.families())
        except Exception:
            families = set()
        families.update(getattr(self, "available_fonts", []))
        if text in families:
            return text, ""
        for family in sorted(families, key=len, reverse=True):
            prefix = family + " "
            if text.startswith(prefix):
                style = text[len(prefix) :].strip()
                if style:
                    return family, style
        return text, ""

    def font_system_family(self, family: str) -> str:
        clean_family = str(family or "").strip()
        if not clean_family:
            return ""
        try:
            family_set = set(QFontDatabase.families())
        except Exception:
            family_set = set()
        if clean_family in family_set:
            return clean_family
        for alias in self.font_aliases.get(clean_family, []):
            alias_family, _alias_style = self.split_font_style(alias)
            if alias_family in family_set:
                return alias_family
            if alias in family_set:
                return alias
        return clean_family

    def font_known_names(self, name: str) -> set[str]:
        clean_name = str(name or "").strip()
        family, _style = self.split_font_style(clean_name)
        names = {clean_name, family, self.font_system_family(family)}
        for key in (clean_name, family):
            for alias in self.font_aliases.get(key, []):
                alias_family, _alias_style = self.split_font_style(alias)
                names.add(alias)
                names.add(alias_family)
                names.add(self.font_system_family(alias_family))
        return {value.casefold() for value in names if value}

    def font_candidates(self, name: str) -> list[str]:
        clean_name = str(name or "").strip()
        candidates: list[str] = []
        family, style = self.split_font_style(clean_name)
        probe_rules = getattr(self, "font_probe_rules", {})
        for key in (clean_name, family):
            for learned in probe_rules.get(key, []):
                if learned and learned not in candidates:
                    candidates.append(learned)
        aliases = [
            *self.font_aliases.get(clean_name, []),
            *self.font_aliases.get(family, []),
        ]
        selected_style = style
        family_set = set(QFontDatabase.families())
        system_family = self.font_system_family(family)
        clean_is_direct = bool(family and (family in family_set or system_family in family_set))

        def candidate_priority(value: str) -> tuple[int, str]:
            candidate_family, candidate_style = self.split_font_style(value)
            resolved_family = self.font_system_family(candidate_family)
            if resolved_family in family_set and candidate_style:
                return (0, resolved_family.casefold(), candidate_style.casefold())
            if resolved_family in family_set:
                return (1, resolved_family.casefold(), value.casefold())
            if candidate_style:
                return (2, value.casefold(), "")
            return (3, value.casefold(), "")

        sorted_aliases = sorted(aliases, key=candidate_priority)
        ordered_names = [clean_name, *sorted_aliases] if family in family_set else [*sorted_aliases, clean_name]
        if system_family and style and system_family in family_set:
            packed = f"{system_family}|||{style}"
            if packed not in candidates:
                candidates.append(packed)
        for alias in sorted_aliases:
            alias_family, alias_style = self.split_font_style(alias)
            resolved_family = self.font_system_family(alias_family)
            is_known_family = resolved_family in family_set or alias_family in getattr(self, "available_fonts", [])
            if resolved_family and selected_style and not alias_style and is_known_family:
                packed = f"{resolved_family}|||{selected_style}"
                if packed not in candidates:
                    candidates.append(packed)
        for candidate in ordered_names:
            if not candidate:
                continue
            family, style_from_name = self.split_font_style(candidate)
            resolved_family = self.font_system_family(family)
            styles = []
            if style_from_name:
                styles.append(style_from_name)
            elif selected_style:
                styles.append(selected_style)
            try:
                styles.extend(str(font_style) for font_style in QFontDatabase.styles(resolved_family))
            except Exception:
                pass
            for candidate_style in styles:
                packed_family = resolved_family if resolved_family in family_set else family
                packed = f"{packed_family}|||{candidate_style}"
                if packed not in candidates:
                    candidates.append(packed)
            for plain_family in (resolved_family, family):
                if plain_family and plain_family not in candidates:
                    candidates.append(plain_family)
        return candidates

    def load_font_probe_rules(self) -> None:
        path = font_probe_rules_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            data = {}
        rules = data.get("rules", []) if isinstance(data, dict) else []
        if not isinstance(rules, list):
            rules = []
        self.font_probe_rule_items = [item for item in rules if isinstance(item, dict)]
        self.font_probe_rules = {}
        for item in self.font_probe_rule_items:
            source = str(item.get("source", "")).strip()
            accepted = str(item.get("accepted", "")).strip()
            if source and accepted:
                bucket = self.font_probe_rules.setdefault(source, [])
                if accepted not in bucket:
                    bucket.append(accepted)

    def save_font_probe_rules(self) -> None:
        path = font_probe_rules_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "rules": self.font_probe_rule_items,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def learn_font_probe_rule(self, source_name: str, candidates: list[str], result: dict) -> None:
        accepted = str(result.get("accepted_font") or result.get("font") or "").strip()
        source = str(source_name or "").strip()
        if not source or not accepted:
            return
        if accepted == source and not candidates:
            return
        clean_candidates = []
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text and text not in clean_candidates:
                clean_candidates.append(text)
        duplicate = any(
            str(item.get("source", "")) == source and str(item.get("accepted", "")) == accepted
            for item in self.font_probe_rule_items
        )
        if duplicate:
            return
        item = {
            "source": source,
            "accepted": accepted,
            "candidates": clean_candidates[:16],
            "resolve_version": self.resolve_version_text,
            "platform": platform.system(),
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        self.font_probe_rule_items.append(item)
        self.font_probe_rules.setdefault(source, [])
        if accepted not in self.font_probe_rules[source]:
            self.font_probe_rules[source].insert(0, accepted)
        self.save_font_probe_rules()
        self.track_usage_event("font_rule_learned", {"rule": item})
        if self.font_inventory_consent and not self._font_inventory_sent_this_session:
            self.track_usage_event("font_inventory", self.build_font_rules_export_payload(include_inventory=True))
            self._font_inventory_sent_this_session = True

    def build_font_rules_export_payload(self, include_inventory: bool = True) -> dict:
        def unique_texts(values: list | tuple | set, limit: int) -> list[str]:
            seen = set()
            result = []
            for value in values:
                text = " ".join(str(value or "").split())
                key = text.casefold()
                if not text or key in seen:
                    continue
                seen.add(key)
                result.append(text)
                if len(result) >= limit:
                    break
            return result

        def compact_font_key(value: str) -> str:
            clean = " ".join(str(value or "").split()).casefold()
            for token in (" ", "-", "_", ".", "regular", "normal", "常规", "標準", "标准"):
                clean = clean.replace(token, "")
            return clean

        def preferred_font_name(names: list[str]) -> str:
            clean_names = unique_texts(names, 32)
            if not clean_names:
                return ""
            chinese = [name for name in clean_names if self.font_language_tag(name) == "中"]
            if chinese:
                return sorted(chinese, key=lambda name: (len(name), name.casefold()))[0]
            return sorted(clean_names, key=lambda name: (len(name), name.casefold()))[0]

        def compact_font_inventory(font_names: list[str], limit: int) -> list[str]:
            groups: dict[str, list[str]] = {}
            for name in font_names:
                clean_name = " ".join(str(name or "").split())
                if not clean_name:
                    continue
                alias_names = [clean_name, *getattr(self, "font_aliases", {}).get(clean_name, [])]
                family, _style = self.split_font_style(clean_name)
                if family != clean_name:
                    alias_names.extend([family, *getattr(self, "font_aliases", {}).get(family, [])])
                keys = [compact_font_key(item) for item in alias_names if item]
                keys = [key for key in keys if key]
                group_key = sorted(keys, key=len)[0] if keys else compact_font_key(clean_name)
                groups.setdefault(group_key, [])
                groups[group_key].extend(alias_names)
            compacted = [preferred_font_name(names) for names in groups.values()]
            compacted = [name for name in compacted if name]
            return sorted(unique_texts(compacted, limit), key=self.font_sort_key)

        payload = {
            "app_version": APP_VERSION,
            "resolve_version": self.resolve_version_text,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "learned_rules": list(self.font_probe_rule_items),
        }
        if include_inventory:
            fonts = compact_font_inventory(list(getattr(self, "available_fonts", [])), 2500)
            aliases = {}
            seen_alias_keys = set()
            for key, values in getattr(self, "font_aliases", {}).items():
                clean_key = " ".join(str(key or "").split())
                folded_key = compact_font_key(clean_key)
                if not clean_key or folded_key in seen_alias_keys:
                    continue
                clean_values = unique_texts(list(values), 12)
                if not clean_values:
                    continue
                seen_alias_keys.add(folded_key)
                aliases[clean_key] = clean_values
                if len(aliases) >= 2500:
                    break
            family_styles = {}
            seen_style_keys = set()
            for key, values in getattr(self, "font_family_styles", {}).items():
                clean_key = " ".join(str(key or "").split())
                folded_key = compact_font_key(clean_key)
                if not clean_key or folded_key in seen_style_keys:
                    continue
                clean_values = unique_texts(list(values), 24)
                if not clean_values:
                    continue
                seen_style_keys.add(folded_key)
                family_styles[clean_key] = clean_values
                if len(family_styles) >= 2500:
                    break
            payload["fonts"] = fonts
            payload["aliases"] = aliases
            payload["family_styles"] = family_styles
        return payload

    def export_font_rules_data(self) -> None:
        default_path = Path.home() / "Desktop" / f"qinghe_font_rules_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path_text, _filter = QFileDialog.getSaveFileName(self, "导出字体规则数据", str(default_path), "JSON (*.json)")
        if not path_text:
            return
        payload = self.build_font_rules_export_payload(include_inventory=True)
        Path(path_text).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        QMessageBox.information(self, "导出完成", f"已导出字体规则数据：\n{path_text}")

    def font_display_name(self, name: str) -> str:
        clean_name = str(name or "").strip()
        if not clean_name:
            return ""
        family, style = self.split_font_style(clean_name)
        aliases = self.font_aliases.get(clean_name, []) or self.font_aliases.get(family, [])
        chinese_alias = next((alias for alias in aliases if self.font_language_tag(alias) == "中"), "")
        if chinese_alias and chinese_alias != clean_name:
            style_suffix = f" {style}" if style and not chinese_alias.endswith(f" {style}") else ""
            return f"{chinese_alias}{style_suffix} / {clean_name}"
        return clean_name

    @staticmethod
    def compact_cell_text(text: str, limit: int = 48) -> str:
        clean = " ".join(str(text or "").replace("\n", " ").split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 1)] + "…"

    def load_available_fonts(self) -> None:
        fonts = set()
        self.font_aliases = {}
        self.font_family_styles = {}
        self.font_postscript_styles = {}
        mapped_postscript_fonts: set[str] = set()
        try:
            fonts.update(str(name) for name in QFontDatabase.families())
        except Exception:
            pass
        for family in list(fonts):
            try:
                styles = [str(style) for style in QFontDatabase.styles(family) if str(style).strip()]
            except Exception:
                styles = []
            if styles:
                self.font_family_styles[family] = styles
        if sys.platform == "darwin":
            try:
                import AppKit  # type: ignore

                manager = AppKit.NSFontManager.sharedFontManager()
                appkit_fonts = [str(name) for name in list(manager.availableFonts())]
                appkit_families = [str(name) for name in list(manager.availableFontFamilies())]
                fonts.update(appkit_families)
                for family in appkit_families:
                    localized = str(manager.localizedNameForFamily_face_(family, None) or "").strip()
                    if localized:
                        fonts.add(localized)
                        self.add_font_alias(localized, [family])
                        self.add_font_alias(family, [localized])
                    members = manager.availableMembersOfFontFamily_(family)
                    if members:
                        display_family = localized or family
                        for member in list(members):
                            try:
                                postscript_name = str(member[0] or "").strip()
                                style_name = str(member[1] or "").strip()
                            except Exception:
                                continue
                            if not postscript_name or not style_name:
                                continue
                            mapped_postscript_fonts.add(postscript_name)
                            previous_mapping = self.font_postscript_styles.get(postscript_name)
                            if (
                                not previous_mapping
                                or (previous_mapping[1].lower() in {"regular", "normal"} and style_name.lower() not in {"regular", "normal"})
                            ):
                                self.font_postscript_styles[postscript_name] = (family, style_name)
                            styled_display = f"{display_family} {style_name}"
                            styled_family = f"{family} {style_name}"
                            self.font_family_styles.setdefault(display_family, [])
                            if style_name not in self.font_family_styles[display_family]:
                                self.font_family_styles[display_family].append(style_name)
                            self.font_family_styles.setdefault(family, [])
                            if style_name not in self.font_family_styles[family]:
                                self.font_family_styles[family].append(style_name)
                            self.add_font_alias(display_family, [family, styled_display, styled_family, postscript_name])
                            self.add_font_alias(family, [display_family, styled_display, styled_family, postscript_name])
                            self.add_font_alias(styled_display, [display_family, family, styled_family, postscript_name])
                            self.add_font_alias(styled_family, [display_family, family, styled_display, postscript_name])
                            self.add_font_alias(postscript_name, [styled_display, styled_family, family, display_family])
            except Exception:
                pass
        expanded_fonts = set(
            font for font in fonts
            if font and not font.startswith(".") and font not in mapped_postscript_fonts
        )
        for family in list(expanded_fonts):
            try:
                styles = [str(style) for style in QFontDatabase.styles(family)]
            except Exception:
                styles = []
            for style in styles:
                if not style:
                    continue
                styled_name = f"{family} {style}"
                self.font_family_styles.setdefault(family, [])
                if style not in self.font_family_styles[family]:
                    self.font_family_styles[family].append(style)
                self.add_font_alias(styled_name, [family, *self.font_aliases.get(family, [])])
        self.available_fonts = sorted(expanded_fonts, key=self.font_sort_key)

    def load_font_favorites(self) -> None:
        path = font_favorites_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.favorite_fonts = {str(item) for item in data if str(item).strip()}
        except Exception:
            self.favorite_fonts = set()

    def save_font_favorites(self) -> None:
        path = font_favorites_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(self.favorite_fonts), ensure_ascii=False, indent=2), encoding="utf-8")

    def load_font_style_library(self) -> None:
        path = font_style_library_path()
        legacy_path = legacy_font_style_library_path()
        if not path.exists() and legacy_path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except Exception:
            data = []
        self.font_style_library = [item for item in data if isinstance(item, dict) and isinstance(item.get("style"), dict)]

    def save_font_style_library(self) -> None:
        path = font_style_library_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.font_style_library, ensure_ascii=False, indent=2), encoding="utf-8")

    def refresh_font_style_library_list(self) -> None:
        if not hasattr(self, "font_style_library_list"):
            return
        current_name = self.selected_font_style_library_name()
        self.font_style_library_list.blockSignals(True)
        self.font_style_library_list.clear()
        for index, item in enumerate(self.font_style_library):
            style = item.get("style") if isinstance(item.get("style"), dict) else {}
            name = str(item.get("name") or f"样式 {index + 1}")
            font_name = str(style.get("Font") or "")
            font_style = str(style.get("Style") or "")
            label = name
            if font_name:
                label += f"  ·  {font_name}{(' ' + font_style) if font_style else ''}"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, index)
            self.font_style_library_list.addItem(row)
            if name == current_name:
                row.setSelected(True)
        self.font_style_library_list.blockSignals(False)
        if self.font_style_library_list.currentRow() < 0 and self.font_style_library_list.count() > 0:
            self.font_style_library_list.setCurrentRow(0)
        self.update_font_style_preview()

    def selected_font_style_library_name(self) -> str:
        if not hasattr(self, "font_style_library_list"):
            return ""
        item = self.font_style_library_list.currentItem()
        if not item:
            return ""
        try:
            index = int(item.data(Qt.UserRole))
        except Exception:
            return ""
        if 0 <= index < len(self.font_style_library):
            return str(self.font_style_library[index].get("name") or "")
        return ""

    def selected_font_style_library_item(self) -> dict | None:
        if not hasattr(self, "font_style_library_list"):
            return None
        item = self.font_style_library_list.currentItem()
        if not item:
            return None
        try:
            index = int(item.data(Qt.UserRole))
        except Exception:
            return None
        if 0 <= index < len(self.font_style_library):
            return self.font_style_library[index]
        return None

    def style_preview_payload(self) -> dict:
        item = self.selected_font_style_library_item()
        if item and isinstance(item.get("style"), dict):
            return dict(item.get("style") or {})
        return dict(self.font_style_clipboard or {})

    def style_color(self, style: dict) -> QColor:
        def channel(key: str, default: float) -> int:
            try:
                value = float(style.get(key, default))
            except Exception:
                value = default
            if value <= 1.0:
                value *= 255.0
            return max(0, min(255, int(round(value))))
        return QColor(channel("Red1", 0.9), channel("Green1", 0.9), channel("Blue1", 0.9), channel("Alpha1", 1.0))

    def update_font_style_preview(self) -> None:
        if not hasattr(self, "font_style_preview_image"):
            return
        height = max(54, min(72, self.font_style_preview_image.height() or 72))
        width = int(height * 16 / 9)
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#0f172a"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#334155"))
        painter.drawRect(0, 0, width - 1, height - 1)
        safe_rect = pixmap.rect().adjusted(int(width * 0.08), int(height * 0.10), -int(width * 0.08), -int(height * 0.10))
        painter.setPen(QColor("#1e293b"))
        painter.drawRect(safe_rect)

        style = self.style_preview_payload()
        family = str(style.get("Font") or self.selected_font_family() or install_cjk_font())
        font_style = str(style.get("Style") or "")
        try:
            normalized_size = float(style.get("Size", 0.075) or 0.075)
        except Exception:
            normalized_size = 0.075
        point_size = max(12, min(28, int(round(normalized_size * height * 4.2))))
        if font_style:
            font = QFontDatabase.font(self.font_system_family(family) or family, font_style, point_size)
        else:
            font = QFont(self.font_system_family(family) or family, point_size)
        painter.setFont(font)
        painter.setPen(self.style_color(style))
        sample = self.selected_font_preview_text()
        sample = painter.fontMetrics().elidedText(sample, Qt.ElideRight, max(120, safe_rect.width() - 24))
        painter.drawText(safe_rect, Qt.AlignCenter, sample)
        painter.setFont(QFont(install_cjk_font(), 7))
        painter.setPen(QColor("#94a3b8"))
        label = self.selected_font_style_library_name() or "当前复制样式"
        painter.drawText(pixmap.rect().adjusted(8, height - 18, -8, -4), Qt.AlignRight | Qt.AlignVCenter, label)
        painter.end()
        self.font_style_preview_image.setPixmap(pixmap)

    def on_font_style_library_selection_changed(self) -> None:
        self.update_font_style_preview()

    def load_selected_textplus_style_from_library(self) -> None:
        item = self.selected_font_style_library_item()
        if not item or not isinstance(item.get("style"), dict):
            self.font_status.setText("请选择一个本地样式。")
            return
        self.font_style_clipboard = dict(item.get("style") or {})
        self.update_font_style_preview()
        self.font_status.setText(f"已载入样式：{item.get('name', '未命名样式')}")

    def save_copied_textplus_style_to_library(self) -> None:
        if not self.font_style_clipboard:
            record = self._selected_textplus_style_record()
            if record:
                result = self.bridge.copy_textplus_style(record)
                if result.get("ok") and isinstance(result.get("style"), dict):
                    self.font_style_clipboard = result.get("style")
                    self.font_status.setText(str(result.get("message", "已复制 Text+ 样式。")))
        if not self.font_style_clipboard:
            self.font_status.setText("请先复制一个 Text+ 样式，或选中 Text+ 后再保存。")
            return
        default_name = f"Text+ 样式 {len(self.font_style_library) + 1}"
        name, ok = QInputDialog.getText(self, "保存 Text+ 样式", "样式名称：", text=default_name)
        if not ok:
            return
        clean_name = str(name or "").strip()
        if not clean_name:
            self.font_status.setText("样式名称不能为空。")
            return
        entry = {
            "name": clean_name,
            "style": dict(self.font_style_clipboard),
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        self.font_style_library = [item for item in self.font_style_library if str(item.get("name")) != clean_name]
        self.font_style_library.append(entry)
        self.save_font_style_library()
        self.refresh_font_style_library_list()
        for row in range(self.font_style_library_list.count()):
            item = self.font_style_library_list.item(row)
            idx = int(item.data(Qt.UserRole))
            if self.font_style_library[idx].get("name") == clean_name:
                self.font_style_library_list.setCurrentRow(row)
                break
        self.font_status.setText(f"已保存本地样式：{clean_name}")

    def delete_selected_textplus_style_from_library(self) -> None:
        item = self.selected_font_style_library_item()
        if not item:
            self.font_status.setText("请选择要删除的样式。")
            return
        name = str(item.get("name") or "未命名样式")
        self.font_style_library = [entry for entry in self.font_style_library if entry is not item]
        self.save_font_style_library()
        self.refresh_font_style_library_list()
        self.font_status.setText(f"已删除本地样式：{name}")

    def refresh_font_list(self) -> None:
        if not hasattr(self, "font_list"):
            return
        query = self.font_search.text().strip().lower() if hasattr(self, "font_search") else ""
        favorite_only = self.font_favorite_only.isChecked() if hasattr(self, "font_favorite_only") else False
        selected = self.selected_font_family()
        self.font_list.clear()
        for font in self.available_fonts:
            aliases = self.font_aliases.get(font, [])
            haystack = " ".join([font, *aliases]).lower()
            if query and query not in haystack:
                continue
            if favorite_only and font not in self.favorite_fonts:
                continue
            prefix = "* " if font in self.favorite_fonts else "  "
            alias_hint = f" / {aliases[0]}" if aliases else ""
            item = QListWidgetItem(f"{prefix}[{self.font_language_tag(font)}] {font}{alias_hint}")
            item.setData(Qt.UserRole, font)
            item.setToolTip(" / ".join([font, *aliases]))
            if font in self.favorite_fonts:
                item.setBackground(QColor("#fff3bf"))
            self.font_list.addItem(item)
            if selected and selected == font:
                self.font_list.setCurrentItem(item)
        if self.font_list.count() and self.font_list.currentRow() < 0:
            self.font_list.setCurrentRow(0)
        self.update_font_preview(self.selected_font_name())

    def selected_font_family(self) -> str:
        if not hasattr(self, "font_list"):
            return ""
        item = self.font_list.currentItem()
        if item:
            value = item.data(Qt.UserRole)
            if value:
                return str(value)
        if hasattr(self, "font_target"):
            family, _style = self.split_font_style(self.font_target.text().strip())
            return family
        return ""

    def selected_font_style(self) -> str:
        if not hasattr(self, "font_style_combo"):
            return ""
        value = self.font_style_combo.currentData()
        return str(value or "").strip()

    def selected_font_name(self) -> str:
        family = self.selected_font_family()
        style = self.selected_font_style()
        if family and style:
            return f"{family} {style}"
        if family:
            return family
        return self.font_target.text().strip() if hasattr(self, "font_target") else ""

    def refresh_font_style_combo(self, family: str) -> None:
        if not hasattr(self, "font_style_combo"):
            return
        styles = list(self.font_family_styles.get(family, []))
        aliases = self.font_aliases.get(family, [])
        for alias in aliases:
            alias_family, alias_style = self.split_font_style(alias)
            if alias_style and (alias_family == family or alias_family in aliases or alias.startswith(family + " ")):
                styles.append(alias_style)
        deduped: list[str] = []
        for style in styles:
            clean = str(style or "").strip()
            if clean and clean not in deduped:
                deduped.append(clean)
        deduped = sorted(deduped, key=lambda value: (0 if value.lower() in {"regular", "normal"} else 1, value.casefold()))
        if not deduped:
            deduped = [""]
        previous = self.selected_font_style()
        self.font_style_combo.blockSignals(True)
        self.font_style_combo.clear()
        for style in deduped:
            self.font_style_combo.addItem(style or "默认", style)
        selected_index = self.font_style_combo.findData(previous)
        if selected_index < 0:
            selected_index = 0
        self.font_style_combo.setCurrentIndex(selected_index)
        self.font_style_combo.blockSignals(False)

    def on_font_style_changed(self, *_args) -> None:
        font_name = self.selected_font_name()
        if font_name:
            self.font_target.setText(font_name)
        self.update_font_preview(font_name)

    def on_font_selection_changed(self) -> None:
        family = self.selected_font_family()
        self.refresh_font_style_combo(family)
        font_name = self.selected_font_name()
        if font_name:
            self.font_target.setText(font_name)
        self.update_font_preview(font_name)

    def selected_font_preview_text(self) -> str:
        record = self.selected_font_record()
        if (
            record
            and str(record.get("kind", "")).lower() == "text+"
            and bool(record.get("supported"))
        ):
            text = " ".join(str(record.get("text", "")).replace("\n", " ").split())
            if text:
                return text
        return "清何字体预览  夹帧检测  ABC 123"

    def update_font_preview(self, font_name: str = "") -> None:
        if not hasattr(self, "font_preview_image"):
            return
        name = str(font_name or self.selected_font_name()).strip()
        width = max(520, self.font_preview_image.width() or 760)
        height = 96
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#0f172a"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#e5e7eb"))
        if not name:
            font = QFont(install_cjk_font(), 18)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "选择字体后显示预览")
        else:
            font = None
            actual_family = ""
            actual_style = ""
            actual_ok = False
            chosen_display = name
            wanted_keys = self.font_known_names(name)
            preview_candidates = self.font_candidates(name) or [name]
            for candidate in preview_candidates:
                family, style = self.split_font_style(candidate)
                resolved_family = self.font_system_family(family)
                if style:
                    candidate_font = QFontDatabase.font(resolved_family or family, style, 30)
                else:
                    candidate_font = QFont(resolved_family or family or candidate, 30)
                info = QFontInfo(candidate_font)
                candidate_actual = str(info.family() or "")
                candidate_style = str(info.styleName() or "")
                fallback_family = candidate_actual.startswith(".") or candidate_actual.lower() in {"sans serif", "sans-serif"}
                if not fallback_family and (candidate_actual.casefold() in wanted_keys or (resolved_family or family or candidate) in QFontDatabase.families()):
                    font = candidate_font
                    actual_family = candidate_actual
                    actual_style = candidate_style
                    actual_ok = True
                    chosen_display = candidate
                    break
            if not actual_ok:
                painter.setFont(QFont(install_cjk_font(), 20, QFont.Bold))
                painter.drawText(pixmap.rect(), Qt.AlignCenter, f"Font Not Found: {name}")
            else:
                assert font is not None
                painter.setFont(font)
                sample = self.selected_font_preview_text()
                sample = painter.fontMetrics().elidedText(sample, Qt.ElideRight, max(120, width - 56))
                painter.drawText(pixmap.rect().adjusted(18, 4, -18, -22), Qt.AlignCenter, sample)
                painter.setFont(QFont(install_cjk_font(), 10))
                painter.setPen(QColor("#94a3b8"))
                display = self.font_display_name(name)
                if chosen_display != name:
                    display = f"{display} -> {chosen_display.replace('|||', ' ')}"
                style_hint = f" {actual_style}" if actual_style else ""
                painter.drawText(pixmap.rect().adjusted(18, 70, -18, -6), Qt.AlignCenter, f"{display}  |  系统实际: {actual_family}{style_hint}")
        painter.end()
        self.font_preview_image.setPixmap(pixmap)

    def add_selected_font_favorite(self) -> None:
        font_name = self.selected_font_family()
        if not font_name:
            return
        self.favorite_fonts.add(font_name)
        self.save_font_favorites()
        self.refresh_font_list()
        self.font_status.setText(f"已收藏字体：{font_name}")

    def remove_selected_font_favorite(self) -> None:
        font_name = self.selected_font_family()
        if not font_name:
            return
        self.favorite_fonts.discard(font_name)
        self.save_font_favorites()
        self.refresh_font_list()
        self.font_status.setText(f"已取消收藏：{font_name}")

    def selected_font_record(self) -> dict | None:
        row = self.font_table.currentRow()
        if row < 0:
            return None
        first = self.font_table.item(row, 0)
        if not first:
            return None
        index = int(first.data(Qt.UserRole))
        if index < 0 or index >= len(self.font_records):
            return None
        return self.font_records[index]

    def selected_font_records(self) -> list[dict]:
        if not hasattr(self, "font_table"):
            return []
        rows = sorted({index.row() for index in self.font_table.selectionModel().selectedRows()})
        records: list[dict] = []
        for row in rows:
            first = self.font_table.item(row, 0)
            if not first:
                continue
            try:
                index = int(first.data(Qt.UserRole))
            except Exception:
                continue
            if 0 <= index < len(self.font_records):
                records.append(self.font_records[index])
        if not records:
            record = self.selected_font_record()
            if record:
                records.append(record)
        return records

    def auto_scan_font_layers(self) -> None:
        if (
            hasattr(self, "side_tabs")
            and self.side_tabs.currentWidget() is self.font_tab
            and self.isVisible()
        ):
            self.scan_font_layers(silent=True)

    def scan_font_layers(self, silent: bool = False) -> None:
        selected_keys = {
            (
                str(record.get("track_type", "")),
                int(record.get("track_index", 0) or 0),
                int(record.get("item_index", -1) or -1),
                str(record.get("font_key", "")),
            )
            for record in self.selected_font_records()
        } if silent else set()
        self.refresh_timelines()
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.scan_font_items(int(selected.get("index", 1)))
        self.font_records = result.get("items") if isinstance(result.get("items"), list) else []
        self.font_table.setRowCount(0)
        unsupported_color = QColor("#f1f5f9")
        rows_to_restore: list[int] = []
        for idx, record in enumerate(self.font_records, 1):
            row = self.font_table.rowCount()
            self.font_table.insertRow(row)
            kind = str(record.get("kind", ""))
            if kind.lower() == "srt":
                kind_label = "SRT轨道"
            elif kind.lower() == "text+":
                kind_label = "Text+"
            elif kind.lower() == "text":
                kind_label = "Text"
            else:
                kind_label = kind
            supported = bool(record.get("supported"))
            reason = str(record.get("reason", "")).strip()
            status = "Text+可写" if supported else "不可替换"
            raw_font_value = str(record.get("font", "")).strip()
            font_value = self.font_display_name(raw_font_value) if supported else "--"
            text_value_full = str(record.get("text", "")).replace("\n", " ").strip()
            if reason and not supported:
                text_value_full = f"{text_value_full} | {reason}" if text_value_full else reason
            text_value = self.compact_cell_text(text_value_full)
            values = [
                f"{idx:03d}",
                str(record.get("timecode", "")),
                kind_label,
                f"{str(record.get('track_type', '')).upper()}{record.get('track_index', '')}",
                font_value,
                status,
                text_value,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, idx - 1)
                if column == 4 and raw_font_value:
                    cell.setToolTip(self.font_display_name(raw_font_value))
                if column == 6:
                    cell.setToolTip(text_value_full)
                elif reason:
                    cell.setToolTip(reason)
                if not supported:
                    cell.setBackground(unsupported_color)
                self.font_table.setItem(row, column, cell)
            key = (
                str(record.get("track_type", "")),
                int(record.get("track_index", 0) or 0),
                int(record.get("item_index", -1) or -1),
                str(record.get("font_key", "")),
            )
            if key in selected_keys:
                rows_to_restore.append(row)
        self.font_table.resizeRowsToContents()
        if rows_to_restore:
            self.font_table.clearSelection()
            for row in rows_to_restore:
                for column in range(self.font_table.columnCount()):
                    cell = self.font_table.item(row, column)
                    if cell:
                        cell.setSelected(True)
            self.font_table.setCurrentCell(rows_to_restore[0], 0)
        self.font_status.setText(str(result.get("message", f"找到 {len(self.font_records)} 个字体层。")))
        if not silent:
            self.side_tabs.setCurrentWidget(self.font_tab)
            self._log(self.font_status.text())

    def jump_to_selected_font_item(self) -> None:
        record = self.selected_font_record()
        if not record:
            return
        result = self.bridge.jump_to_font_item(record)
        self.font_status.setText(str(result.get("message", "")))
        self._log(self.font_status.text())

    def apply_font_to_selected_layer(self) -> None:
        record = self.selected_font_record()
        font_name = self.font_target.text().strip() or self.selected_font_name()
        if not record or not font_name:
            self.font_status.setText("请选择字体和字体层。")
            return
        if not record.get("supported"):
            reason = str(record.get("reason", "")).strip()
            if not reason:
                kind = str(record.get("kind", ""))
                reason = f"{kind} 在当前 Resolve 版本不支持通过脚本直接替换字体。"
            self.font_status.setText(f"未修改时间线：{reason}")
            self._log(self.font_status.text())
            return
        candidates = self.font_candidates(font_name)
        result = self.bridge.replace_font_item(record, font_name, candidates)
        self.font_status.setText(str(result.get("message", "")))
        self._log(self.font_status.text())
        if result.get("ok"):
            self.learn_font_probe_rule(font_name, candidates, result)
            actual_font = str(result.get("accepted_font") or result.get("font") or font_name)
            record["font"] = actual_font
            row = self.font_table.currentRow()
            if row >= 0 and self.font_table.item(row, 4):
                self.font_table.item(row, 4).setText(self.font_display_name(actual_font))
                self.font_table.item(row, 4).setToolTip(self.font_display_name(actual_font))

    def apply_font_to_all_supported_layers(self) -> None:
        font_name = self.font_target.text().strip() or self.selected_font_name()
        if not font_name:
            self.font_status.setText("请选择目标字体。")
            return
        if not self.font_records:
            self.scan_font_layers()
        ok_count = 0
        fail_count = 0
        skipped = 0
        for record in list(self.font_records):
            QApplication.processEvents()
            if not record.get("supported"):
                skipped += 1
                continue
            candidates = self.font_candidates(font_name)
            result = self.bridge.replace_font_item(record, font_name, candidates)
            if result.get("ok"):
                ok_count += 1
                self.learn_font_probe_rule(font_name, candidates, result)
                record["font"] = str(result.get("accepted_font") or result.get("font") or font_name)
            else:
                fail_count += 1
        self.scan_font_layers()
        self.font_status.setText(f"批量替换完成：成功 {ok_count} 个，失败 {fail_count} 个，不支持 {skipped} 个。")
        self._log(self.font_status.text())

    def _selected_textplus_style_record(self) -> dict | None:
        record = self.selected_font_record()
        if not record:
            self.font_status.setText("请选择一个 Text+ 字体层。")
            return None
        if str(record.get("kind", "")).lower() != "text+" or not record.get("supported"):
            self.font_status.setText("请选择状态为可替换的 Text+；SRT 和普通 Text 暂不支持复制 Text+ 样式。")
            return None
        return record

    def copy_selected_textplus_style(self) -> None:
        record = self._selected_textplus_style_record()
        if not record:
            self._log(self.font_status.text())
            return
        result = self.bridge.copy_textplus_style(record)
        if result.get("ok") and isinstance(result.get("style"), dict):
            self.font_style_clipboard = result.get("style")
            self.update_font_style_preview()
        self.font_status.setText(str(result.get("message", "Text+ 样式复制失败。")))
        self._log(self.font_status.text())

    def apply_copied_textplus_style_to_selected(self) -> None:
        library_item = self.selected_font_style_library_item()
        if library_item and isinstance(library_item.get("style"), dict):
            self.font_style_clipboard = dict(library_item.get("style") or {})
        if not self.font_style_clipboard:
            self.font_status.setText("请先选中一个做好的 Text+，点击“复制样式”。")
            return
        records = self.selected_font_records()
        if not records:
            self.font_status.setText("请选择一个或多个 Text+ 字体层。")
            return
        ok_count = 0
        fail_count = 0
        skipped = 0
        for record in records:
            QApplication.processEvents()
            if str(record.get("kind", "")).lower() != "text+" or not record.get("supported"):
                skipped += 1
                continue
            result = self.bridge.apply_textplus_style(record, self.font_style_clipboard)
            if result.get("ok"):
                ok_count += 1
            else:
                fail_count += 1
        self.font_status.setText(f"样式应用完成：成功 {ok_count} 个，失败 {fail_count} 个，跳过 {skipped} 个。")
        self._log(self.font_status.text())
        if ok_count:
            self.scan_font_layers()

    def apply_copied_textplus_style_to_all(self) -> None:
        if not self.font_style_clipboard:
            self.font_status.setText("请先选中一个做好的 Text+，点击“复制样式”。")
            return
        if not self.font_records:
            self.scan_font_layers()
        ok_count = 0
        fail_count = 0
        skipped = 0
        for record in list(self.font_records):
            QApplication.processEvents()
            if str(record.get("kind", "")).lower() != "text+" or not record.get("supported"):
                skipped += 1
                continue
            result = self.bridge.apply_textplus_style(record, self.font_style_clipboard)
            if result.get("ok"):
                ok_count += 1
            else:
                fail_count += 1
        self.scan_font_layers()
        self.font_status.setText(f"批量样式完成：成功 {ok_count} 个，失败 {fail_count} 个，跳过 {skipped} 个。")
        self._log(self.font_status.text())

    def convert_srt_to_textplus(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        template_uid = ""
        if hasattr(self, "caption_template_combo"):
            template_uid = str(self.caption_template_combo.currentData() or "")
        info = self.bridge.caption_conversion_info(int(selected.get("index", 1)), template_uid)
        if info.get("ok") and info.get("fps_mismatch"):
            timeline_fps = info.get("timeline_fps", "")
            template_fps = info.get("template_fps", "")
            template_name = str(info.get("template_name", "当前模板"))
            answer = QMessageBox.question(
                self,
                "SRT 转 Text+ 帧率提示",
                (
                    f"当前时间线是 {timeline_fps} fps，模板「{template_name}」是 {template_fps} fps。\n\n"
                    "插件会自动补偿时长，但最稳妥的方式是用当前时间线相同帧率自己做一个 Text+ 模板。\n\n"
                    "是否直接启用自动补偿并继续转换？"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                self.font_status.setText("已取消转换。请在媒体池选择同帧率 Text+ 模板后再试。")
                self._log(self.font_status.text())
                return
        self.font_status.setText("正在把 SRT 转成 Text+，请稍等...")
        QApplication.processEvents()
        result = self.bridge.convert_srt_to_textplus(int(selected.get("index", 1)), template_uid)
        self.font_status.setText(str(result.get("message", "SRT 转 Text+ 失败。")))
        self._log(self.font_status.text())
        if result.get("ok"):
            self.scan_font_layers()

    def refresh_caption_templates(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.list_caption_templates(int(selected.get("index", 1)))
        templates = result.get("templates") if isinstance(result.get("templates"), list) else []
        current_uid = str(self.caption_template_combo.currentData() or "") if hasattr(self, "caption_template_combo") else ""
        self.caption_template_combo.blockSignals(True)
        self.caption_template_combo.clear()
        self.caption_template_combo.addItem("内置默认 Text+ 模板", "")
        restore_index = 0
        for template in templates:
            if not isinstance(template, dict):
                continue
            uid = str(template.get("uid", ""))
            name = str(template.get("name", "未命名模板"))
            type_text = str(template.get("type", ""))
            fps_text = str(template.get("fps", "") or "")
            label = name + (f"  ·  {type_text}" if type_text else "")
            if fps_text:
                label += f"  ·  {fps_text}fps"
            self.caption_template_combo.addItem(label, uid)
            if uid and uid == current_uid:
                restore_index = self.caption_template_combo.count() - 1
        self.caption_template_combo.setCurrentIndex(restore_index)
        self.caption_template_combo.blockSignals(False)
        self.font_status.setText(str(result.get("message", f"找到 {len(templates)} 个模板。")))
        self._log(self.font_status.text())

    def scan_text_layers(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        query = self.text_search.text().strip()
        self.text_highlight_delegate.set_query(query)
        result = self.bridge.scan_text_items(int(selected.get("index", 1)), "", self.selected_text_scan_types())
        self.text_records = result.get("items") if isinstance(result.get("items"), list) else []
        self.text_match_indices = []
        self.text_match_cursor = -1
        self._updating_text_table = True
        self.text_table.setRowCount(0)
        match_color = QColor("#fff3bf")
        for idx, item in enumerate(self.text_records, 1):
            text = str(item.get("text", "")).replace("\n", " ")
            haystack = (text + " " + str(item.get("name", ""))).lower()
            is_match = bool(query and query.lower() in haystack)
            if is_match:
                self.text_match_indices.append(idx - 1)
            row_index = self.text_table.rowCount()
            self.text_table.insertRow(row_index)
            values = [
                f"{idx:03d}",
                str(item.get("timecode", "")),
                f"{str(item.get('track_type', '')).upper()}{item.get('track_index', '')}",
                text,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, idx - 1)
                if column == 3:
                    cell.setFlags(cell.flags() | Qt.ItemIsEditable)
                else:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if is_match:
                    cell.setBackground(match_color)
                self.text_table.setItem(row_index, column, cell)
        self._updating_text_table = False
        self.text_table.resizeRowsToContents()
        base_message = str(result.get("message", f"找到 {len(self.text_records)} 条文字/字幕素材。"))
        if query:
            total = len(self.text_match_indices)
            base_message += f"  匹配 {total} 处。"
            self._set_match_button(0, total)
        else:
            self.text_next_match_btn.setText("下一个匹配")
        self.text_status.setText(base_message)
        self.text_initial_panel.hide()
        for widget in (self.text_search_panel, self.text_replace_panel, self.text_table_panel, self.text_status):
            widget.show()
        self.side_tabs.setCurrentWidget(self.text_tab)
        self._log(self.text_status.text())

    def selected_text_scan_types(self) -> list[str]:
        types: list[str] = []
        if self.text_scan_srt.isChecked():
            types.append("srt")
        if self.text_scan_text.isChecked():
            types.append("text")
        if self.text_scan_textplus.isChecked():
            types.append("text_plus")
        return types or ["srt"]

    def selected_text_item_record(self) -> dict | None:
        row = self.text_table.currentRow()
        if row < 0:
            return None
        first_cell = self.text_table.item(row, 0)
        if not first_cell:
            return None
        index = int(first_cell.data(Qt.UserRole))
        if index < 0 or index >= len(self.text_records):
            return None
        self.text_index = index
        return self.text_records[index]

    def push_text_undo(self, changes: list[dict]) -> None:
        valid = [
            change
            for change in changes
            if change.get("action") == "delete" or change.get("old_text") != change.get("new_text")
        ]
        if not valid:
            return
        self.text_undo_stack.append(valid)
        self.text_undo_stack = self.text_undo_stack[-10:]
        self.text_undo_btn.setEnabled(True)

    def make_text_undo_change(
        self,
        item: dict,
        old_text: str,
        new_text: str,
        *,
        action: str = "replace",
        record_index: int | None = None,
    ) -> dict:
        change_item = copy.deepcopy(item)
        if record_index is not None:
            change_item["_record_index"] = record_index
        return {
            "action": action,
            "item": change_item,
            "old_text": old_text,
            "new_text": new_text,
            "record_index": record_index,
            "track_type": change_item.get("track_type"),
            "track_index": change_item.get("track_index"),
            "item_index": change_item.get("item_index"),
            "start_frame": change_item.get("start_frame"),
            "end_frame": change_item.get("end_frame"),
            "unique_id": change_item.get("unique_id"),
        }

    def update_text_record_row(self, index: int, new_text: str) -> None:
        if index < 0 or index >= len(self.text_records):
            return
        self.text_records[index]["text"] = new_text
        self.text_records[index]["name"] = new_text
        text_cell = self.text_table.item(index, 3)
        if not text_cell:
            return
        self._updating_text_table = True
        text_cell.setText(new_text)
        self._updating_text_table = False

    def restore_text_record_row_from_undo(self, change: dict, text: str) -> None:
        index = change.get("record_index")
        try:
            index = int(index)
        except Exception:
            index = None
        if index is not None and 0 <= index < len(self.text_records):
            self.update_text_record_row(index, text)

    def on_text_cell_double_clicked(self, row: int, column: int) -> None:
        if column == 3:
            self.text_table.editItem(self.text_table.item(row, column))
            return
        self.jump_to_selected_text_item()

    def on_text_cell_changed(self, row: int, column: int) -> None:
        if self._updating_text_table or column != 3:
            return
        first_cell = self.text_table.item(row, 0)
        text_cell = self.text_table.item(row, 3)
        if not first_cell or not text_cell:
            return
        index = int(first_cell.data(Qt.UserRole))
        if index < 0 or index >= len(self.text_records):
            return
        item = self.text_records[index]
        new_text = text_cell.text()
        old_text = str(item.get("text", ""))
        if new_text == old_text:
            return
        result = self.bridge.replace_text_item(item, new_text)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())
        if result.get("ok"):
            self.push_text_undo([self.make_text_undo_change(item, old_text, new_text, record_index=index)])
            item["text"] = new_text
            item["name"] = new_text
            return
        self._updating_text_table = True
        text_cell.setText(old_text)
        self._updating_text_table = False

    def jump_to_next_text_match(self) -> None:
        if not self.text_match_indices:
            self.text_status.setText("没有可跳转的文字匹配。")
            return
        self.text_match_cursor = (self.text_match_cursor + 1) % len(self.text_match_indices)
        total = len(self.text_match_indices)
        current = self.text_match_cursor + 1
        self._set_match_button(current, total)
        record_index = self.text_match_indices[self.text_match_cursor]
        self.text_table.selectRow(record_index)
        item = self.text_table.item(record_index, 0)
        if item:
            self.text_table.scrollToItem(item)
        self.jump_to_selected_text_item()

    def _set_match_button(self, current: int, total: int) -> None:
        if total > 0:
            self.text_next_match_btn.setText(f"下一个匹配 ({current}/{total})")
        else:
            self.text_next_match_btn.setText("下一个匹配")

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
        query = self.text_search.text().strip()
        replacement = self.text_replace.text()
        source_text = str(item.get("text", ""))
        if not query:
            self.text_status.setText("请先输入要查找的文字。")
            return
        if query not in source_text:
            self.text_status.setText("选中行没有匹配的查找词。")
            return
        new_text = source_text.replace(query, replacement)
        result = self.bridge.replace_text_item(item, new_text)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())
        if result.get("ok"):
            row = self.text_table.currentRow()
            if 0 <= row < len(self.text_records):
                self.push_text_undo([self.make_text_undo_change(item, source_text, new_text, record_index=row)])
                self.update_text_record_row(row, new_text)

    def replace_matched_text_items(self) -> None:
        query = self.text_search.text().strip()
        replacement = self.text_replace.text()
        if not query:
            self.text_status.setText("请先输入要查找的文字。")
            return
        if not self.text_match_indices:
            self.scan_text_layers()
        targets = list(self.text_match_indices)
        if not targets:
            self.text_status.setText("没有匹配项可批量替换。")
            return
        ok_count = 0
        fail_count = 0
        undo_changes: list[dict] = []
        self._updating_text_table = True
        for index in targets:
            QApplication.processEvents()
            if index < 0 or index >= len(self.text_records):
                continue
            item = self.text_records[index]
            source_text = str(item.get("text", ""))
            new_text = source_text.replace(query, replacement)
            if new_text == source_text:
                continue
            result = self.bridge.replace_text_item(item, new_text)
            if result.get("ok"):
                ok_count += 1
                undo_changes.append(self.make_text_undo_change(item, source_text, new_text, record_index=index))
                item["text"] = new_text
                item["name"] = new_text
                text_cell = self.text_table.item(index, 3)
                if text_cell:
                    text_cell.setText(new_text)
            else:
                fail_count += 1
        self._updating_text_table = False
        self.push_text_undo(undo_changes)
        self.scan_text_layers()
        self.text_status.setText(f"批量替换完成：成功 {ok_count} 条，失败 {fail_count} 条。")
        self._log(self.text_status.text())

    def undo_last_text_change(self) -> None:
        if not self.text_undo_stack:
            self.text_status.setText("没有可撤回的文字修改。")
            self.text_undo_btn.setEnabled(False)
            return
        changes = self.text_undo_stack.pop()
        ok_count = 0
        fail_count = 0
        for change in reversed(changes):
            QApplication.processEvents()
            item = copy.deepcopy(change.get("item") or {})
            old_text = str(change.get("old_text", ""))
            if not item:
                fail_count += 1
                continue
            if str(change.get("action", "replace")) == "delete":
                result = self.bridge.restore_deleted_text_item(item)
            else:
                result = self.bridge.replace_text_item(item, old_text)
            if result.get("ok"):
                ok_count += 1
                if str(change.get("action", "replace")) != "delete":
                    self.restore_text_record_row_from_undo(change, old_text)
            else:
                fail_count += 1
        self.text_undo_btn.setEnabled(bool(self.text_undo_stack))
        self.scan_text_layers()
        self.text_status.setText(f"撤回完成：成功 {ok_count} 条，失败 {fail_count} 条。")
        self._log(self.text_status.text())

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
            self.push_text_undo([
                self.make_text_undo_change(
                    item,
                    str(item.get("text", "")),
                    "",
                    action="delete",
                    record_index=self.text_index,
                )
            ])
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
            self.push_text_undo([self.make_text_undo_change(item, source_text, cleaned, record_index=self.text_index)])
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
            f"标记 {summary.get('clip_color_changed', 0) + summary.get('clip_markers_added', 0)} 个 / "
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
                    f"{'  片段标记' if clip.get('clip_marker_added') else ''}"
                )
        if not lines:
            lines.append(message)
            lines.append("")
            lines.append("识别依据：音轨格式、源音频声道映射、片段/素材属性里的 mono/1.0/单声道。")
            lines.append("如果只是把已切开的某一小段在达芬奇属性里单独改成单声道，Resolve 可能不会把这个片段级改动暴露给脚本 API。")
        self.audio_list.setPlainText("\n".join(lines))
        self._log(message)

    def render_audio_fx_probe(self, result: dict) -> None:
        probe = result.get("probe") if isinstance(result.get("probe"), dict) else {}
        self.audio_summary.setText(str(result.get("message", "音频 FX API 探测完成。")))
        lines = [
            "音频/Fairlight FX API 探测",
            f"Resolve: {probe.get('resolve_version', '')} / 当前页面: {probe.get('current_page', '')}",
            f"音频轨道: {probe.get('audio_track_count', 0)}；样本片段: {'有' if probe.get('has_sample_audio_item') else '无'}",
            "",
        ]
        write_candidates = probe.get("write_candidates") if isinstance(probe.get("write_candidates"), dict) else {}
        any_write = False
        lines.append("疑似可写 FX 方法")
        for label, methods in write_candidates.items():
            methods = methods if isinstance(methods, list) else []
            if methods:
                any_write = True
                lines.append(f"  {label}: {', '.join(str(name) for name in methods[:20])}")
        if not any_write:
            lines.append("  未发现 Add/Apply/Insert/Set + FX/OFX/Effect/Fairlight 等公开方法。")
        lines.append("")

        methods_report = probe.get("methods") if isinstance(probe.get("methods"), dict) else {}
        lines.append("相关可见方法")
        for label, methods in methods_report.items():
            methods = methods if isinstance(methods, list) else []
            if methods:
                lines.append(f"  {label}: {', '.join(str(name) for name in methods[:28])}")
        lines.append("")

        for title, key in (
            ("时间线音频设置键", "timeline_audio_setting_keys"),
            ("项目音频设置键", "project_audio_setting_keys"),
            ("音频片段属性键", "audio_item_property_keys"),
            ("媒体池音频属性键", "media_clip_audio_property_keys"),
        ):
            values = probe.get(key) if isinstance(probe.get(key), list) else []
            lines.append(title)
            lines.append(", ".join(str(value) for value in values[:80]) if values else "无")
            lines.append("")

        self.audio_list.setPlainText("\n".join(lines))

    def on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.progress_label.setText(message[:20])
        self._log(message)

    def on_done(self, ok: bool, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress_label.setText("已提交" if ok else "失败")
        self._log(message)
        self.track_usage_event("detect_done", {"ok": bool(ok)})
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
        if widget is self.text_tab and not self._text_compact_mode and not self._font_compact_mode:
            QTimer.singleShot(0, lambda: self.set_text_compact_mode(True))
        if widget is self.font_tab and not self._font_compact_mode and not self._text_compact_mode:
            QTimer.singleShot(0, lambda: self.set_font_compact_mode(True))
        if widget is self.font_tab:
            QTimer.singleShot(0, lambda: self.scan_font_layers(silent=True))

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

    def close_when_resolve_exits(self) -> None:
        running = is_resolve_process_running()
        if running:
            self._resolve_seen_running = True
            self._resolve_missing_ticks = 0
            return
        self._resolve_missing_ticks += 1
        if self._resolve_seen_running or self._resolve_missing_ticks >= 2:
            self.close()

    def _capture_current_timeline_uid(self) -> None:
        """Store the current timeline identity for change detection."""
        if not self.timelines:
            return
        idx = self.timeline_combo.currentIndex()
        if 0 <= idx < len(self.timelines):
            self._last_timeline_uid = self.timelines[idx].uid or ""
            self._last_timeline_name = self.timelines[idx].name.replace("  (当前)", "")
        elif self.timelines:
            self._last_timeline_uid = self.timelines[0].uid or ""
            self._last_timeline_name = self.timelines[0].name.replace("  (当前)", "")

    def poll_timeline_change(self) -> None:
        """Detect when user switches timeline in DaVinci Resolve and auto-refresh."""
        if self._loading_timelines or self.worker is not None:
            return
        identity = self.bridge.current_timeline_identity()
        current_uid = str(identity.get("uid", "")) if identity.get("ok") else ""
        current_name = str(identity.get("name", "")) if identity.get("ok") else ""
        if not current_uid and not current_name:
            return
        uid_changed = bool(current_uid and self._last_timeline_uid and current_uid != self._last_timeline_uid)
        name_changed = bool(current_name and self._last_timeline_name and current_name != self._last_timeline_name)
        if uid_changed or name_changed:
            self._log("检测到 Resolve 当前时间线切换，自动同步目标时间线...")
            self.refresh_timelines()
            self._capture_current_timeline_uid()
            self._log("目标时间线已同步为当前 Resolve 时间线。")
        elif not self._last_timeline_uid and not self._last_timeline_name:
            self._last_timeline_uid = current_uid
            self._last_timeline_name = current_name

    def closeEvent(self, event) -> None:  # noqa: N802
        self.track_usage_event("app_close", {"session_seconds": int(max(0, time.time() - self.session_started_at))})
        self.resolve_watch_timer.stop()
        self.timeline_poll_timer.stop()
        self.font_auto_scan_timer.stop()
        self.save_settings()
        super().closeEvent(event)


def _ensure_macos_dock_icon() -> None:
    """macOS: transform Python process to a proper foreground GUI app with Dock icon."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import objc
        from Foundation import NSBundle
        info = NSBundle.mainBundle().infoDictionary()
        if not info or "CFBundleName" not in info:
            NSBundle.mainBundle().infoDictionary().update({
                "CFBundleName": "清何黑帧夹帧检测",
                "CFBundleDisplayName": "清何黑帧夹帧检测",
                "CFBundleIdentifier": "com.qinghe.bfd.control",
                "CFBundleVersion": APP_VERSION,
                "CFBundleShortVersionString": APP_VERSION,
                "NSHighResolutionCapable": True,
            })
    except Exception:
        pass
    try:
        # TransformProcessType: make us a foreground app with Dock icon
        app_services = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        kProcessTransformToForegroundApplication = 1
        app_services.TransformProcessType(
            ctypes.c_void_p(0),
            ctypes.c_void_p(kProcessTransformToForegroundApplication),
        )
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    if BRIDGE_WORKER_ARG in argv[1:]:
        return run_resolve_bridge_worker()

    set_windows_app_user_model_id()
    _ensure_macos_dock_icon()
    app = QApplication(argv)
    app.setApplicationName("清何黑帧夹帧检测")
    app.setApplicationDisplayName("清何黑帧夹帧检测")
    app.setApplicationVersion(APP_VERSION)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    instance_guard = SingleInstanceGuard(SINGLE_INSTANCE_NAME)
    if instance_guard.already_running:
        return 0
    app._qinghe_single_instance_guard = instance_guard  # type: ignore[attr-defined]
    font_family = install_cjk_font()
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont(font_family, 10))
    window = MainWindow()
    instance_guard.bind_window(window)
    bring_window_to_front(window)
    QTimer.singleShot(250, lambda: bring_window_to_front(window))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
