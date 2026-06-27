from __future__ import annotations

import copy
from html import escape as html_escape
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import ctypes
import platform
import uuid
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QFontInfo, QGuiApplication, QIcon, QPainter, QPixmap, QTextDocument
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
    QProgressDialog,
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


APP_VERSION = "2.0.1-beta.19"
APP_NAME = "清何剪辑工具箱"
FEEDBACK_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/c533d532-4041-4e58-abd5-6f9eb924d58c"
ANALYTICS_ENDPOINT_URL = "https://qinghe-bfd-analytics.featherofawhale.workers.dev/collect"
ANALYTICS_USER_AGENT = f"QingheToolbox/{APP_VERSION} (DaVinci Resolve Plugin)"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/featherofawhale-crypto/qinghe-bfd-plugin/main/release/latest.json"
CNB_UPDATE_MANIFEST_URL = "https://cnb.cool/featherofawhale-crypto/qinghe-bfd-plugin/-/releases/download/latest/latest.json"
UPDATE_USER_AGENT = f"QingheToolboxUpdate/{APP_VERSION}"

DEFAULT_STUCK_FRAMES = 3
DEFAULT_SUSPECT_FRAMES = 12
DEFAULT_MIN_BLACK_FRAMES = 1
BASELINE_FPS = 25.0
DEFAULT_PIXEL_THRESHOLD = 1.0
DEFAULT_BLACK_BORDER_PX = 3
DEFAULT_CONTENT_SAMPLE_INTERVAL = 5
BLACK_BORDER_ASPECT_PRESETS = [
    ("不指定遮幅", 0.0),
    ("1.33", 1.33),
    ("1.66", 1.66),
    ("1.77", 1.77),
    ("1.85", 1.85),
    ("2.00", 2.00),
    ("2.35", 2.35),
    ("2.39", 2.39),
    ("2.40", 2.40),
    ("自定义", -1.0),
]
MAX_FRAME_THRESHOLD = 100
ICON_PATH = Path(__file__).resolve().with_name("icon.svg")
DONATION_DIR = Path(__file__).resolve().with_name("donate")
DONATION_AMOUNTS = (1, 2, 3, 5)
WINDOWS_APP_ID = "Qinghe.BFD.Control"
SINGLE_INSTANCE_NAME = "Qinghe.BFD.Control.SingleInstance"
DISCLAIMER_TEXT = (
    "清何剪辑工具箱是一款免费工具，供 DaVinci Resolve 用户自愿使用。\n"
    "本插件按“现状”提供，不作任何明示或默示保证，包括但不限于适销性、特定用途适用性。\n"
    "作者不对因使用本插件产生的直接、间接、偶然、特殊或后果性损害承担责任，包括项目文件损坏或丢失、数据丢失、时间线标记异常、软件崩溃或其他 Resolve 操作问题。\n"
    "使用者应自行评估适用性，并在使用前做好项目备份。\n"
    "本插件仅用于辅助视频剪辑工作流程，检测结果仅作辅助参考，不保证 100% 检测所有问题，最终判断仍需人工确认。\n"
    "捐赠为自愿支持开发，不构成功能购买、服务承诺、抽奖返利或收益承诺。"
)


def analytics_platform_label() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    if system == "Windows":
        return "Windows"
    if system == "Linux":
        return "Linux"
    return system or "unknown"


def update_platform_key() -> str:
    system = platform.system()
    if system == "Darwin":
        return "mac"
    if system == "Windows":
        return "windows"
    return system.lower() or "unknown"


def update_manifest_urls() -> list[str]:
    urls: list[str] = []
    override = os.environ.get("QINGHE_UPDATE_MANIFEST_URL", "").strip()
    for url in (override, CNB_UPDATE_MANIFEST_URL, UPDATE_MANIFEST_URL):
        clean = str(url or "").strip()
        if clean and clean not in urls:
            urls.append(clean)
    return urls


def version_sort_key(version: str) -> tuple:
    text = str(version or "").strip().lower()
    text = text.lstrip("v")
    text = text.replace("内测版", "beta").replace("测试版", "beta")
    main, sep, suffix = text.partition("-")
    nums = []
    for part in main.split("."):
        match = re.search(r"\d+", part)
        nums.append(int(match.group(0)) if match else 0)
    while len(nums) < 4:
        nums.append(0)
    prerelease_rank = 3
    prerelease_num = 0
    if sep:
        prerelease_rank = 1
        if "alpha" in suffix:
            prerelease_rank = 0
        elif "beta" in suffix:
            prerelease_rank = 1
        elif "rc" in suffix:
            prerelease_rank = 2
        match = re.search(r"(\d+)$", suffix)
        prerelease_num = int(match.group(1)) if match else 0
    return (*nums[:4], prerelease_rank, prerelease_num, text)


def fetch_update_manifest_url(url: str) -> tuple[dict | None, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": UPDATE_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read(512 * 1024).decode("utf-8", errors="replace")
        data = json.loads(body)
        if not isinstance(data, dict):
            return None, "更新清单格式错误。"
        return data, ""
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and "raw.githubusercontent.com" in url:
            return None, "检查更新失败：GitHub 更新清单未公开或尚未发布。私有仓库里的 raw 文件，插件用户端不能直接读取。"
        return None, f"检查更新失败：HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"检查更新失败：{exc}"
    except Exception as exc:
        return None, f"检查更新失败：{exc}"


def fetch_update_manifest() -> tuple[dict | None, str]:
    urls = update_manifest_urls()
    if not urls:
        return None, "未配置更新清单地址。"
    errors: list[str] = []
    for url in urls:
        manifest, error = fetch_update_manifest_url(url)
        if manifest:
            manifest["_manifest_url"] = url
            return manifest, ""
        if error:
            errors.append(f"{url}: {error}")
    return None, "检查更新失败：所有更新源都不可用。\n" + "\n".join(errors[:3])


def update_info_from_manifest(manifest: dict) -> dict:
    platform_key = update_platform_key()
    platforms = manifest.get("platforms") if isinstance(manifest.get("platforms"), dict) else {}
    platform_info = platforms.get(platform_key) if isinstance(platforms.get(platform_key), dict) else {}
    latest_version = str(platform_info.get("version") or manifest.get("version") or "").strip()
    return {
        "platform": platform_key,
        "latest_version": latest_version,
        "download_url": str(platform_info.get("download_url") or manifest.get("download_url") or "").strip(),
        "package_type": str(platform_info.get("package_type") or manifest.get("package_type") or "").strip().lower(),
        "sha256": str(platform_info.get("sha256") or manifest.get("sha256") or "").strip().lower(),
        "release_url": str(platform_info.get("release_url") or manifest.get("release_url") or "").strip(),
        "notes": str(platform_info.get("notes") or manifest.get("notes") or "").strip(),
        "manifest_url": str(manifest.get("_manifest_url") or "").strip(),
        "mandatory": bool(platform_info.get("mandatory") or manifest.get("mandatory") or False),
    }


def update_cache_dir() -> Path:
    path = Path.home() / ".qinghe_bfd" / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path

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


def apply_macos_window_level(widget: QWidget, floating: bool = True) -> None:
    if platform.system() != "Darwin":
        return
    try:
        native_id = int(widget.winId())
        import objc  # type: ignore
        from AppKit import NSFloatingWindowLevel, NSNormalWindowLevel  # type: ignore

        view = objc.objc_object(c_void_p=ctypes.c_void_p(native_id))
        window = view.window() if view is not None and hasattr(view, "window") else None
        if window is not None:
            window.setLevel_(NSFloatingWindowLevel if floating else NSNormalWindowLevel)
            if floating:
                window.setCollectionBehavior_(window.collectionBehavior() | (1 << 7))
    except Exception:
        pass


def macos_frontmost_app_label() -> str:
    if platform.system() != "Darwin":
        return ""
    try:
        from AppKit import NSWorkspace  # type: ignore

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        name = str(app.localizedName() or "") if app is not None else ""
        bundle = str(app.bundleIdentifier() or "") if app is not None else ""
        return f"{name} {bundle}".lower()
    except Exception:
        return ""


def macos_resolve_is_frontmost() -> bool:
    label = macos_frontmost_app_label()
    return "davinci" in label or "resolve" in label or "blackmagic" in label


def bring_window_to_front(window: QWidget) -> None:
    window.show()
    if hasattr(window, "showNormal"):
        window.showNormal()
    window.raise_()
    window.activateWindow()


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
QTableWidget, QListWidget {
    background: #ffffff;
    color: #172033;
    alternate-background-color: #f8fafc;
    gridline-color: #e2e8f0;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
QTableWidget::item, QListWidget::item {
    padding: 2px 4px;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: #dbeafe;
    color: #0f172a;
}
QHeaderView::section, QTableCornerButton::section {
    background: #eef2f7;
    color: #334155;
    border: 1px solid #d9e1ea;
    padding: 4px 5px;
    font-weight: 700;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #172033;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
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
QTableWidget, QListWidget {
    background: #fffff8;
    color: #243024;
    alternate-background-color: #f4f8eb;
    gridline-color: #d7e2c8;
    selection-background-color: #dcecc9;
    selection-color: #172417;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: #dcecc9;
    color: #172417;
}
QHeaderView::section, QTableCornerButton::section {
    background: #e9f0df;
    color: #334229;
    border-color: #cbd8ba;
}
QComboBox QAbstractItemView {
    background: #fffff8;
    color: #243024;
    selection-background-color: #dcecc9;
    selection-color: #172417;
}
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
QTableWidget, QListWidget {
    background: #020617;
    color: #f8fafc;
    alternate-background-color: #0f172a;
    gridline-color: #334155;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QTableWidget::item, QListWidget::item {
    color: #f8fafc;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: #2563eb;
    color: #ffffff;
}
QHeaderView::section, QTableCornerButton::section {
    background: #1f2937;
    color: #e5e7eb;
    border-color: #334155;
}
QComboBox QAbstractItemView {
    background: #020617;
    color: #e5e7eb;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
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
    "black_border": "#EA580C",
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


def basic_font_rules_path() -> Path:
    return plugin_data_dir() / "basic_font_rules.json"


def fallback_font_rules_path() -> Path:
    return plugin_data_dir() / "fallback_probe_rules.json"


def font_probe_report_path() -> Path:
    return plugin_data_dir() / "font_probe_report.json"


def media_pool_probe_path() -> Path:
    return plugin_data_dir() / "media_pool_probe.json"


def install_id_path() -> Path:
    return Path.home() / ".qinghe_bfd" / "install_id"


def analytics_log_path() -> Path:
    return Path.home() / ".qinghe_bfd" / "analytics.log"


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


def startup_trace(message: str) -> None:
    if os.environ.get("QINGHE_BFD_STARTUP_TRACE") != "1":
        return
    try:
        root = Path.home() / ".qinghe_bfd"
        root.mkdir(parents=True, exist_ok=True)
        with (root / "startup_trace.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {time.time():.3f} {message}\n")
    except Exception:
        pass


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


def write_font_probe_report_cache(result: dict) -> None:
    try:
        path = font_probe_report_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def read_font_probe_report_summary(max_chars: int = 14000) -> str:
    path = font_probe_report_path()
    if not path.exists():
        return "暂无字体探针报告。"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"读取字体探针报告失败: {exc}"
    if len(text) > max_chars:
        return text[: max_chars // 2] + "\n...<已截断>...\n" + text[-max_chars // 2 :]
    return text


def write_media_pool_probe_cache(result: dict) -> None:
    try:
        path = media_pool_probe_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def read_media_pool_probe_summary(max_chars: int = 14000) -> str:
    path = media_pool_probe_path()
    if not path.exists():
        return "暂无媒体池/API 探针缓存。"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"读取媒体池/API 探针失败: {exc}"
    if len(text) > max_chars:
        return text[: max_chars // 2] + "\n...<已截断>...\n" + text[-max_chars // 2 :]
    return text


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
                "--- 字体探针报告 ---\n"
                f"{read_font_probe_report_summary()}\n\n"
                "--- 媒体池/API 探针 ---\n"
                f"{read_media_pool_probe_summary()}\n\n"
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
        ok = False
        error_text = ""
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": ANALYTICS_USER_AGENT,
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                response.read(256)
                ok = 200 <= int(getattr(response, "status", 200)) < 300
        except Exception as exc:
            error_text = str(exc)
        if not ok:
            try:
                path = analytics_log_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                line = (
                    datetime.utcnow().isoformat(timespec="seconds")
                    + "Z "
                    + str(payload.get("event", "unknown"))
                    + " "
                    + (error_text or "non_2xx_response")
                    + "\n"
                )
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
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
            timeline_index = int(params.get("timeline_index", 1) or 1)
            base = int(((index - 1) / max(1, total)) * 90)
            span = max(8, int(90 / max(1, total)))
            self.progress.emit(base + 8, f"准备 {timeline_name}")
            time.sleep(0.12)
            self.progress.emit(base + 25, f"打开时间线：{timeline_name}")
            if self.bridge.is_connected():
                ok, message = self.bridge.activate_timeline(timeline_index)
                if not ok:
                    self.done.emit(False, f"{timeline_name} 打开失败：{message}")
                    return
            else:
                self.bridge.open_resolve_page()
            if params.get("batch_read_io"):
                io_ok, io_message = self.refresh_job_io(params, timeline_name, timeline_index, base, span)
                if not io_ok:
                    self.done.emit(False, io_message)
                    return
            params_path = self.bridge.submit_params(params)
            job_id = str(params_path.stem).replace("params_", "", 1)
            self.progress.emit(base + 48, f"检测 {timeline_name}")
            ok, message = self.bridge.run_lua_entry_with_fuscript(params_path)
            if not ok:
                self.done.emit(False, f"{timeline_name} 检测启动失败：{message}")
                return
            wait_ok, wait_message, progress_payload = self.wait_for_job_completion(
                timeline_name,
                base,
                span,
                bool(params.get("complex_mode")),
                job_id,
            )
            if not wait_ok:
                self.done.emit(False, wait_message)
                return
            sync_ok, sync_message = self.wait_for_timeline_marker_sync(params, progress_payload, base, span)
            if not sync_ok:
                self.done.emit(False, sync_message)
                return
            messages.append(f"{timeline_name}: {message or '已完成'}")
        self.progress.emit(100, "检测已提交")
        self.done.emit(True, "\n".join(messages) if messages else "检测已提交。")

    def refresh_job_io(
        self,
        params: dict,
        timeline_name: str,
        timeline_index: int,
        base: int,
        span: int,
    ) -> tuple[bool, str]:
        self.progress.emit(min(99, base + max(1, int(span * 0.32))), f"读取IO：{timeline_name}")
        result = self.bridge.current_timeline_marks(timeline_index)
        if not result.get("ok"):
            params["manual_io_in"] = ""
            params["manual_io_out"] = ""
            message = str(result.get("message", "未读取到入出点。") or "未读取到入出点。")
            if params.get("complex_mode"):
                return False, f"{timeline_name} 读取IO失败：{message}"
            params["io_source"] = "none"
            return True, message
        params["manual_io_in"] = str(result.get("in_tc", "") or "")
        params["manual_io_out"] = str(result.get("out_tc", "") or "")
        params["io_source"] = str(result.get("source", "timeline_marks") or "timeline_marks")
        try:
            params["timeline_fps"] = float(result.get("fps") or params.get("timeline_fps") or 25.0)
        except Exception:
            pass
        if not params["manual_io_in"] or not params["manual_io_out"]:
            if params.get("complex_mode"):
                return False, f"{timeline_name} 读取IO失败：Resolve 未返回完整入出点。"
            params["io_source"] = "none"
        return True, "已读取IO"

    def wait_for_job_completion(
        self,
        timeline_name: str,
        base: int,
        span: int,
        complex_mode: bool,
        job_id: str,
    ) -> tuple[bool, str, dict]:
        timeout = 1800 if complex_mode else 600
        started = time.time()
        last_stage = ""
        last_percent = 0
        while time.time() - started < timeout:
            progress = read_progress_file()
            if isinstance(progress, dict):
                progress_job_id = str(progress.get("job_id") or "")
                if progress_job_id and progress_job_id != job_id:
                    time.sleep(0.5)
                    continue
                state = str(progress.get("state", ""))
                stage = str(progress.get("stage", "检测中"))
                try:
                    pct = int(float(progress.get("percent", 0) or 0))
                except Exception:
                    pct = 0
                pct = max(0, min(100, pct))
                mapped = min(99, base + max(1, int((pct / 100.0) * span)))
                if stage != last_stage or pct != last_percent:
                    self.progress.emit(mapped, f"{timeline_name}：{stage}")
                    last_stage = stage
                    last_percent = pct
                if state in {"complete", "failed", "cancelled"} or pct >= 100:
                    if state == "failed":
                        return False, f"{timeline_name} 检测失败：{stage}", progress
                    if state == "cancelled":
                        return False, f"{timeline_name} 检测已取消。", progress
                    return True, stage or "检测完成", progress
            time.sleep(0.5)
        return False, f"{timeline_name} 检测超时，已等待 {timeout} 秒。", {}

    def wait_for_timeline_marker_sync(
        self,
        params: dict,
        progress_payload: dict,
        base: int,
        span: int,
    ) -> tuple[bool, str]:
        timeline_index = int(params.get("timeline_index", 1))
        timeline_name = str(params.get("timeline_name", f"时间线 {timeline_index}"))
        records = progress_payload.get("records") if isinstance(progress_payload, dict) else None
        expected_count = len(records) if isinstance(records, list) else 0
        if expected_count <= 0:
            self.progress.emit(min(99, base + span), f"{timeline_name}：确认无标记结果")
            time.sleep(0.8)
            return True, "检测完成"

        self.progress.emit(min(99, base + span), f"{timeline_name}：确认标记写入")
        deadline = time.time() + 45
        last_count = -1
        while time.time() < deadline:
            result = self.bridge.bfd_marker_records(timeline_index)
            if result.get("ok"):
                counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
                marker_count = int(counts.get("total") or 0)
                if marker_count != last_count:
                    self.progress.emit(
                        min(99, base + span),
                        f"{timeline_name}：已读回 {marker_count}/{expected_count} 个标记",
                    )
                    last_count = marker_count
                if marker_count >= expected_count:
                    return True, "标记已写入"
            time.sleep(1.0)
        return False, f"{timeline_name} 检测已完成，但未能在 Resolve 里确认全部标记写入。"


class StartupSyncWorker(QThread):
    done = Signal(dict)

    def run(self) -> None:
        bridge = ResolveBridge()
        payload: dict = {
            "ok": False,
            "connected": False,
            "timelines": [],
            "current_identity": {},
            "resolve_version": "",
            "message": "",
        }
        try:
            timelines = bridge.list_timelines()
            current_identity = bridge.current_timeline_identity()
            connected = bridge.is_connected()
            resolve_version = bridge.resolve_version_string() if connected else ""
            payload.update(
                {
                    "ok": True,
                    "connected": bool(connected),
                    "timelines": [asdict(timeline) for timeline in timelines],
                    "current_identity": current_identity if isinstance(current_identity, dict) else {},
                    "resolve_version": resolve_version,
                }
            )
        except Exception as exc:  # noqa: BLE001
            payload["message"] = str(exc)
        self.done.emit(payload)


class UpdateInstallWorker(QThread):
    progress = Signal(int, str)
    done = Signal(bool, str, str)

    def __init__(self, info: dict) -> None:
        super().__init__()
        self.info = dict(info or {})

    def run(self) -> None:
        url = str(self.info.get("download_url") or "").strip()
        if not url:
            self.done.emit(False, "更新清单没有 download_url，无法一键更新。", "")
            return
        try:
            package_path = self.download_package(url)
            package_type = str(self.info.get("package_type") or package_path.suffix.lstrip(".")).lower()
            expected_sha = str(self.info.get("sha256") or "").strip().lower()
            if expected_sha:
                actual = self.file_sha256(package_path)
                if actual.lower() != expected_sha:
                    self.done.emit(False, "安装包校验失败：SHA256 不一致，已停止安装。", str(package_path))
                    return
            if platform.system() == "Darwin":
                self.install_macos_package(package_path, package_type)
                return
            self.done.emit(True, f"安装包已下载：{package_path}\n当前平台暂不自动安装，请手动运行安装包。", str(package_path))
        except Exception as exc:
            self.done.emit(False, f"一键更新失败：{exc}", "")

    def download_package(self, url: str) -> Path:
        self.progress.emit(5, "连接更新源")
        request = urllib.request.Request(url, headers={"User-Agent": UPDATE_USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            total = int(response.headers.get("Content-Length") or 0)
            name = Path(urllib.parse.urlparse(url).path).name or "qinghe_update.pkg"
            target = update_cache_dir() / f"{int(time.time())}_{name}"
            read = 0
            with target.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    handle.write(chunk)
                    read += len(chunk)
                    if total > 0:
                        percent = 8 + int(min(1.0, read / total) * 62)
                        self.progress.emit(percent, f"下载更新包 {read // 1024 // 1024}MB / {max(1, total // 1024 // 1024)}MB")
        self.progress.emit(72, "下载完成")
        return target

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def install_macos_package(self, package_path: Path, package_type: str) -> None:
        lower_name = package_path.name.lower()
        if package_type == "dmg" or lower_name.endswith(".dmg"):
            self.progress.emit(100, "DMG 已下载，等待手动安装")
            self.done.emit(True, f"DMG 已下载：{package_path}\n已为你打开安装包，请按界面完成安装。", str(package_path))
            return
        install_script = None
        work_dir = None
        if package_type == "zip" or lower_name.endswith(".zip"):
            self.progress.emit(78, "解压更新包")
            work_dir = update_cache_dir() / f"extracted_{int(time.time())}"
            work_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(package_path, "r") as archive:
                archive.extractall(work_dir)
            scripts = list(work_dir.rglob("install_macos.command"))
            install_script = scripts[0] if scripts else None
        elif lower_name.endswith(".command") or package_type == "command":
            install_script = package_path
            work_dir = package_path.parent

        if not install_script or not install_script.exists():
            self.done.emit(False, f"更新包里没有找到 install_macos.command，请手动安装：{package_path}", str(package_path))
            return

        self.progress.emit(86, "执行安装脚本")
        install_script.chmod(install_script.stat().st_mode | 0o111)
        env = os.environ.copy()
        env["QINGHE_AUTO_UPDATE"] = "1"
        result = subprocess.run(
            ["bash", str(install_script)],
            cwd=str(install_script.parent if work_dir else package_path.parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            self.done.emit(False, "安装脚本执行失败：\n" + (result.stdout or "")[-2000:], str(package_path))
            return
        self.progress.emit(100, "更新完成")
        self.done.emit(True, "更新完成。请重新打开插件，让新版本完全生效。", str(package_path))


class TextPlusStyleApplyWorker(QThread):
    progress = Signal(int, int, int, str)
    done = Signal(dict)

    def __init__(self, bridge: ResolveBridge, records: list[dict], style: dict) -> None:
        super().__init__()
        self.bridge = bridge
        self.records = [dict(record) for record in records]
        self.style = copy.deepcopy(style or {})

    def run(self) -> None:
        ok_count = 0
        fail_count = 0
        skipped = 0
        total = len(self.records)
        for processed, record in enumerate(self.records, 1):
            member_count = max(1, int(record.get("member_count", 1) or 1))
            self.progress.emit(processed, total, member_count, "正在应用 Text+ 样式")
            try:
                result = self.bridge.apply_textplus_style(record, self.style)
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "message": str(exc)}
            if result.get("ok"):
                ok_count += 1
            else:
                fail_count += 1
        self.done.emit({"ok_count": ok_count, "fail_count": fail_count, "skipped": skipped})


class FontLayerScanWorker(QThread):
    done = Signal(dict, bool, object)

    def __init__(self, timeline_index: int, silent: bool, selected_keys: object) -> None:
        super().__init__()
        self.timeline_index = int(timeline_index or 1)
        self.silent = bool(silent)
        self.selected_keys = selected_keys

    def run(self) -> None:
        try:
            result = ResolveBridge().scan_font_items(self.timeline_index)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "items": [], "message": f"扫描字体层失败：{exc}"}
        self.done.emit(result, self.silent, self.selected_keys)


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
            "感谢支持清何剪辑工具箱。捐赠完全自愿，不对应功能解锁、抽奖、"
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


class BlackBorderOptionsDialog(QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.setWindowTitle("画面黑边检测")
        self.resize(520, 260)

        layout = QVBoxLayout(self)
        title = QLabel("画面黑边设置")
        title.setObjectName("Title")
        layout.addWidget(title)

        note = QLabel(
            "没有加遮幅时选“不指定遮幅”，插件会用普通模式快速几何检测。\n"
            "如果用了达芬奇输出遮幅或图片遮幅，选择对应比例，本次会临时复杂渲染最终画面，避免正常遮幅误报。"
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel("遮幅预设"))
        self.preset = QComboBox()
        for label, value in BLACK_BORDER_ASPECT_PRESETS:
            self.preset.addItem(label, value)
        row.addWidget(self.preset, 1)
        row.addWidget(QLabel("自定义"))
        self.custom = QDoubleSpinBox()
        self.custom.setRange(0.0, 9.99)
        self.custom.setDecimals(2)
        self.custom.setSingleStep(0.01)
        self.custom.setValue(0.0)
        self.custom.setEnabled(False)
        row.addWidget(self.custom)
        layout.addLayout(row)

        help_text = QLabel("常用值：1.33 / 1.66 / 1.77 / 1.85 / 2.00 / 2.35 / 2.39 / 2.40。特殊比例选“自定义”。")
        help_text.setWordWrap(True)
        help_text.setObjectName("Muted")
        layout.addWidget(help_text)

        self.preset.currentIndexChanged.connect(self.on_preset_changed)
        self.set_aspect(parent.current_black_border_aspect())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_aspect(self, value: float) -> None:
        value = max(0.0, float(value or 0.0))
        for index, (_label, preset_value) in enumerate(BLACK_BORDER_ASPECT_PRESETS):
            if preset_value >= 0 and abs(preset_value - value) < 0.005:
                self.preset.setCurrentIndex(index)
                self.custom.setValue(value)
                self.custom.setEnabled(False)
                return
        custom_index = self.preset.findText("自定义")
        if custom_index >= 0:
            self.preset.setCurrentIndex(custom_index)
        self.custom.setValue(value)
        self.custom.setEnabled(True)

    def on_preset_changed(self, *_args) -> None:
        try:
            value = float(self.preset.currentData())
        except Exception:
            value = 0.0
        custom = value < 0
        self.custom.setEnabled(custom)
        if not custom:
            self.custom.setValue(max(0.0, value))

    def aspect(self) -> float:
        try:
            value = float(self.preset.currentData())
        except Exception:
            value = 0.0
        if value < 0:
            return max(0.0, float(self.custom.value()))
        return max(0.0, value)


class MainWindow(QMainWindow):
    update_check_finished = Signal(dict, bool, str)

    def __init__(self) -> None:
        startup_trace("MainWindow init enter")
        super().__init__()
        startup_trace("MainWindow after super")
        font_family = install_cjk_font()
        startup_trace(f"MainWindow after install_cjk_font family={font_family}")
        app = QApplication.instance()
        if app:
            app.setFont(QFont(font_family, 10))
        self.setWindowTitle(f"{APP_NAME} - Pro Control")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self.bridge = ResolveBridge()
        startup_trace("MainWindow after bridge")
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
        self.font_file_aliases: dict[str, list[str]] = {}
        self.font_family_styles: dict[str, list[str]] = {}
        self.font_probe_rules: dict[str, list[str]] = {}
        self.font_probe_rule_items: list[dict] = []
        self._font_delivery_rules_loaded = False
        self._qt_application_font_paths: set[str] = set()
        self.font_fusion_availability_cache: dict[str, dict] = {}
        self.font_inventory_consent = False
        self.donation_prompt_seen = False
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
        self._checking_updates = False
        self._update_notice_shown = False
        self.startup_sync_worker: StartupSyncWorker | None = None
        self.font_scan_worker: FontLayerScanWorker | None = None
        self.update_worker: UpdateInstallWorker | None = None
        self.update_progress_dialog: QProgressDialog | None = None
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
        self.window_level_timer = QTimer(self)
        self.window_level_timer.setInterval(1000)
        self.window_level_timer.timeout.connect(self.enforce_resolve_window_level)
        self.update_check_finished.connect(self.on_update_check_finished)

        shell = QFrame()
        shell.setObjectName("Shell")
        root = QVBoxLayout(shell)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)

        root.addLayout(self._build_header())
        startup_trace("MainWindow after header")
        body = QVBoxLayout()
        body.setSpacing(9)

        self.controls_panel = QWidget()
        controls = QVBoxLayout(self.controls_panel)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(self._build_timeline_group())
        controls.addWidget(self._build_analysis_mode_group())

        main_grid = QGridLayout()
        main_grid.setHorizontalSpacing(9)
        main_grid.setVerticalSpacing(8)
        main_grid.addWidget(self._build_detection_group(), 0, 0)
        main_grid.addWidget(self._build_threshold_group(), 0, 1)
        main_grid.addWidget(self._build_advanced_section(), 1, 0, 1, 2)
        main_grid.setColumnStretch(0, 0)
        main_grid.setColumnStretch(1, 1)
        controls.addLayout(main_grid)
        controls.addStretch(1)

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setFrameShape(QFrame.NoFrame)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.controls_scroll.setWidget(self.controls_panel)

        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(0)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.controls_scroll, 1)
        left_layout.addWidget(self._build_action_group())

        self.detection_tab = QWidget()
        self.detection_layout = QVBoxLayout(self.detection_tab)
        self.detection_layout.setContentsMargins(8, 8, 8, 8)
        self.detection_layout.setSpacing(8)

        body.addWidget(self._build_side_tabs(), 1)
        startup_trace("MainWindow after side tabs")
        root.addLayout(body, 1)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(8, 8, 8, 8)
        wrapper_layout.addWidget(shell)
        self.setCentralWidget(wrapper)
        self.install_button_motion()
        startup_trace("MainWindow after central widget")

        self.set_timeline_loading_state("正在同步 Resolve 时间线...")
        self.load_settings()
        self.load_font_favorites()
        self.load_font_style_library()
        self.load_font_probe_rules()
        startup_trace("MainWindow after settings/rules")
        self.update_fps_hint()
        startup_trace("MainWindow after update_fps_hint")
        self.on_complex_mode_changed(self.chk_complex.isChecked())
        startup_trace("MainWindow after complex mode")
        self.resolve_watch_timer.start()
        self.timeline_poll_timer.start()
        self.font_auto_scan_timer.start()
        # Do not poll macOS foreground/window level. On some systems this blocks
        # AppKit for seconds and makes the plugin feel frozen during launch.
        startup_trace("MainWindow after timers start")
        QTimer.singleShot(160, self.start_startup_sync)
        QTimer.singleShot(350, self.initialize_font_inventory)
        QTimer.singleShot(1200, lambda: self.track_usage_event("app_start"))
        QTimer.singleShot(1600, self.show_first_run_donation_dialog)
        QTimer.singleShot(2600, lambda: self.check_for_updates(manual=False))
        startup_trace("MainWindow after schedule timers")
        self._log("插件界面已打开，正在后台同步 Resolve 时间线。")
        startup_trace("MainWindow init leave")

    def initialize_font_inventory(self) -> None:
        self.load_available_fonts()
        self.refresh_font_list()
        self.refresh_font_style_library_list()

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(APP_NAME)
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

        self.connection_badge = QLabel("连接中")
        self.connection_badge.setObjectName("BadgeWarn")
        self.connection_badge.setFixedHeight(34)
        self.connection_badge.setAlignment(Qt.AlignCenter)
        set_tip(self.connection_badge, "已连接：插件当前能通过 Resolve 脚本 API 读取工程和时间线；离线：只能改界面参数，检测/扫描类功能会失败。")

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

        self.update_btn = QPushButton("更新")
        self.update_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.update_btn.setFixedHeight(34)
        set_tip(self.update_btn, "检查 GitHub 公开发布仓库里的最新安装包。会区分 macOS 和 Windows 版本。")
        self.update_btn.clicked.connect(lambda: self.check_for_updates(manual=True))

        self.theme_combo = QComboBox()
        self.theme_combo.setFixedHeight(34)
        self.theme_combo.setMinimumWidth(82)
        for key, label in THEME_LABELS.items():
            self.theme_combo.addItem(label, key)
        set_tip(self.theme_combo, "切换界面配色：默认、护眼、黑夜。只影响插件外观，不会修改 Resolve 工程。")
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)

        layout.addLayout(title_box, 1)
        layout.addWidget(self.theme_combo, 0, Qt.AlignTop)
        layout.addWidget(self.update_btn, 0, Qt.AlignTop)
        layout.addWidget(self.donate_btn, 0, Qt.AlignTop)
        layout.addWidget(self.connection_badge, 0, Qt.AlignTop)
        return layout

    def _build_timeline_group(self) -> QGroupBox:
        box = QGroupBox("时间线")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        io_row = QHBoxLayout()
        io_row.setSpacing(8)
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)

        self.timeline_combo = QComboBox()
        self.timeline_combo.setMinimumWidth(220)
        self.timeline_combo.setMaximumWidth(430)
        self.timeline_combo.setMinimumContentsLength(22)
        self.timeline_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.timeline_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        set_tip(self.timeline_combo, "选择目标 Resolve 时间线；刷新后会优先选中当前打开的时间线。检测、字幕、字体和音频工具都以这里的时间线为准。")
        self.timeline_combo.currentIndexChanged.connect(self.on_timeline_changed)
        refresh = QPushButton("刷新")
        refresh.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh.setFixedWidth(76)
        set_tip(refresh, "重新读取当前 Resolve 工程的时间线列表；切换或新建时间线后点这里同步插件。")
        refresh.clicked.connect(self.refresh_timelines)
        self.read_marks_btn = QPushButton("读取入出点")
        self.read_marks_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.read_marks_btn.setFixedWidth(112)
        set_tip(self.read_marks_btn, "读取 Resolve 当前时间线的入点/出点并填到手动范围。Resolve 19 在部分 macOS 环境可能读不到，需要手动输入。")
        self.read_marks_btn.clicked.connect(self.fill_in_out_from_current_timeline_marks)
        self.full_timeline_btn = QPushButton("全时间线")
        self.full_timeline_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.full_timeline_btn.setFixedWidth(104)
        set_tip(self.full_timeline_btn, "清空手动入点/出点，让检测覆盖整条时间线。复杂模式会渲染画面，长时间线请谨慎使用。")
        self.full_timeline_btn.clicked.connect(self.use_full_timeline_range)

        self.io_in = QLineEdit()
        self.io_in.setMinimumWidth(112)
        self.io_in.setMaximumWidth(154)
        self.io_in.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.io_in.setPlaceholderText("01:00:00:00")
        set_tip(self.io_in, "限制检测起点。Resolve 19 API无法读取IO，请手动输入。复杂模式必须填写。")
        self.io_out = QLineEdit()
        self.io_out.setMinimumWidth(112)
        self.io_out.setMaximumWidth(154)
        self.io_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.io_out.setPlaceholderText("01:02:30:00")
        set_tip(self.io_out, "限制检测终点。复杂模式必须填写出点，避免渲染整条时间线导致过慢。")

        self.chk_batch_timelines = QCheckBox("批量检测时间线")
        self.chk_batch_timelines.setFixedWidth(132)
        set_tip(self.chk_batch_timelines, "批量检测：勾选后可以选择多条时间线。开始检测会按列表顺序让 Resolve 自动切到每条时间线并写入对应标记。")
        self.chk_batch_timelines.toggled.connect(self.on_batch_toggled)
        self.chk_batch_read_io = QCheckBox("读IO")
        self.chk_batch_read_io.setEnabled(False)
        self.chk_batch_read_io.setFixedWidth(68)
        set_tip(
            self.chk_batch_read_io,
            "批量检测时，为每条勾选的时间线分别读取 Resolve 入点/出点。\n\n"
            "适合每条时间线都已设置自己的 IO 范围。读取成功后，每条 job 会使用自己的 in/out；读取失败才回退到上方手动输入。\n"
            "Resolve 19 macOS 会用临时渲染队列探测 IO，过程会短暂切换到 Deliver 页面并自动返回。",
        )

        self.batch_timeline_list = QListWidget()
        self.batch_timeline_list.setMinimumHeight(44)
        self.batch_timeline_list.setMaximumHeight(64)
        self.batch_timeline_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.batch_timeline_list.setEnabled(False)
        set_tip(self.batch_timeline_list, "勾选要批量检测的时间线；每条时间线会使用自己的帧率换算阈值。")

        target_label = QLabel("目标时间线")
        target_label.setFixedWidth(64)

        in_label = QLabel("入点")
        out_label = QLabel("出点")
        in_label.setFixedWidth(42)
        out_label.setFixedWidth(42)

        target_row.addWidget(target_label)
        target_row.addWidget(self.timeline_combo)
        target_row.addWidget(refresh)
        target_row.addWidget(self.read_marks_btn)
        target_row.addStretch(1)

        io_row.addWidget(in_label)
        io_row.addWidget(self.io_in)
        io_row.addWidget(out_label)
        io_row.addWidget(self.io_out)
        io_row.addWidget(self.full_timeline_btn)
        io_row.addStretch(1)

        batch_row.addWidget(self.chk_batch_timelines)
        batch_row.addWidget(self.chk_batch_read_io)
        batch_row.addWidget(self.batch_timeline_list, 1)

        layout.addLayout(target_row)
        layout.addLayout(io_row)
        layout.addLayout(batch_row)
        return box

    def _build_detection_group(self) -> QGroupBox:
        box = QGroupBox("检测与标记")
        box.setMaximumWidth(440)
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        layout.setContentsMargins(12, 14, 12, 12)

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
        self.chk_black_border = self._marker_check(
            "画面黑边",
            "black_border",
            False,
            "检测画面边缘露出的黑边。\n\n"
            "没有加遮幅：遮幅预设选“不指定遮幅”，可用普通模式快速检测。\n"
            "加了达芬奇输出遮幅或图片遮幅：选择对应遮幅比例，本次会临时复杂渲染最终画面，避免把正常遮幅误报成黑边。",
        )
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
            self.chk_black_border,
            self.chk_corrupt,
        ]
        for index, check in enumerate(checks):
            layout.addWidget(check, index // 2, index % 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        return box

    def _build_threshold_group(self) -> QGroupBox:
        box = QGroupBox("阈值")
        box.setMinimumWidth(520)
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

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

        self.black_border_px = QSpinBox()
        self.black_border_px.setRange(1, 100)
        self.black_border_px.setValue(DEFAULT_BLACK_BORDER_PX)
        set_tip(self.black_border_px, "黑边最小像素宽度。默认 3px；只在勾选“画面黑边”时生效。")
        self.black_border_slider = self._make_slider(1, 100, DEFAULT_BLACK_BORDER_PX, self.black_border_px)

        self.black_border_aspect_preset = QComboBox()
        for label, value in BLACK_BORDER_ASPECT_PRESETS:
            self.black_border_aspect_preset.addItem(label, value)
        set_tip(
            self.black_border_aspect_preset,
            "选择当前时间线使用的遮幅比例。\n\n"
            "不指定遮幅：适合没有加上下/左右遮幅的项目，普通模式会用源素材内容框 + 缩放/位移几何快速判断。\n"
            "1.33、1.66、1.77、1.85、2.00、2.35、2.39、2.40：对应达芬奇“输出加遮幅”的常见预设。\n"
            "自定义：特殊项目比例可在旁边手动填写。",
        )
        self.black_border_aspect_preset.currentIndexChanged.connect(self.on_black_border_preset_changed)

        self.black_border_aspect = QDoubleSpinBox()
        self.black_border_aspect.setRange(0.0, 9.99)
        self.black_border_aspect.setDecimals(2)
        self.black_border_aspect.setSingleStep(0.01)
        self.black_border_aspect.setValue(0.0)
        self.black_border_aspect.setSpecialValueText("不忽略")
        set_tip(
            self.black_border_aspect,
            "自定义遮幅比例。只有遮幅预设选“自定义”时需要填写。\n\n"
            "例子：16:9 时间线加了 2.35 遮幅，就填 2.35；加了 1.33 竖幅遮幅，就填 1.33。\n"
            "填写比例后，画面黑边检测会临时复杂渲染最终画面，先识别预期遮幅，再判断有效画面里是否还有额外露黑。",
        )
        self.black_border_aspect.setEnabled(False)

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
            self.black_border_px,
            self.black_border_aspect_preset,
            self.black_border_aspect,
            self.min_black_frames,
            self.content_sample_interval,
        ):
            spin.setFixedWidth(96)

        self.reset_thresholds_btn = QPushButton("还原默认")
        self.reset_thresholds_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        set_tip(self.reset_thresholds_btn, "恢复默认阈值：夹帧 3 帧、可疑 12 帧、最短黑场 1 帧、黑色阈值 1%、黑边 3px、指纹采样 5 帧。")
        self.reset_thresholds_btn.clicked.connect(self.reset_threshold_defaults)

        def add_threshold_row(row: int, text: str, field: QWidget, slider: QSlider) -> None:
            label = QLabel(text)
            label.setFixedWidth(126)
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            slider.setMinimumWidth(180)
            slider.setMaximumWidth(300)
            layout.addWidget(label, row, 0, Qt.AlignLeft)
            layout.addWidget(field, row, 1, Qt.AlignLeft)
            layout.addWidget(slider, row, 2, Qt.AlignLeft)

        add_threshold_row(0, "夹帧阈值/帧", self.stuck_frames, self.stuck_slider)
        add_threshold_row(1, "可疑阈值/帧", self.suspect_frames, self.suspect_slider)
        add_threshold_row(2, "黑场像素阈值", self.pixel_threshold, self.pixel_slider)
        add_threshold_row(3, "黑边阈值/像素", self.black_border_px, self.black_border_slider)
        self.black_border_aspect_preset.hide()
        self.black_border_aspect.hide()
        add_threshold_row(4, "最短黑场/帧", self.min_black_frames, self.min_black_slider)
        add_threshold_row(5, "指纹采样/帧", self.content_sample_interval, self.content_sample_slider)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)
        self.fps_hint = QLabel("当前按 25fps 基准换算。")
        self.fps_hint.setObjectName("Muted")
        self.fps_hint.setWordWrap(True)
        self.fps_hint.setMinimumHeight(36)
        self.fps_hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        set_tip(self.fps_hint, "帧数阈值固定按当前填写值使用；切换时间线不会自动改数值。")
        layout.addWidget(self.fps_hint, 6, 0, 1, 3)
        layout.addWidget(self.reset_thresholds_btn, 7, 0, 1, 3)
        for widget in [self.stuck_frames, self.suspect_frames, self.min_black_frames]:
            widget.valueChanged.connect(lambda _value: self.update_fps_hint())
        return box

    def _build_analysis_mode_group(self) -> QGroupBox:
        box = QGroupBox("分析方式")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        self.chk_nested_render = self._check(
            "复合/Fusion 片段精查",
            False,
            "默认关闭。开启后只把顶层可见的复合片段、Fusion片段或嵌套时间线小区间临时渲染，再加入普通成片分析；适合复合片段里可能有黑帧/夹帧的情况。会调用 Resolve 渲染，速度比纯普通模式慢，检测后会清理本次临时文件。",
        )
        self.chk_complex = self._check(
            "复杂模式（整段渲染后分析）",
            False,
            "默认关闭。先渲染入点到出点范围，再分析最终画面；用于调色、OFX、Fusion、叠加、不透明度之后的最终像素复查。长时间线会明显变慢，建议先设置入出点。",
        )
        self.chk_complex.toggled.connect(self.on_complex_mode_changed)

        for check in [self.chk_nested_render, self.chk_complex]:
            layout.addWidget(check)
        layout.addStretch(1)
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
        self.chk_png_opaque = self._check("PNG/PSD 视为遮挡层", True, "多轨叠加检测时，把静态图层也当作上层遮挡，适合字幕贴纸很多的工程。")
        self.chk_html = self._check("生成 HTML 报告", False, "检测完成后输出可阅读报告，适合发给协作者复核。")
        self.chk_analytics = QCheckBox("匿名使用统计")
        self.chk_analytics.setChecked(True)

        options = [
            self.chk_clear,
            self.chk_mark_hidden,
            self.chk_partial_opacity,
            self.chk_png_opaque,
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

        self.chk_keep_complex_cache = self._check(
            "保存复杂模式缓存视频",
            False,
            "默认关闭。开启后，复杂模式渲染出的成片会保留在缓存目录，并写入清何匹配文件；以后可选择该视频跳过重复渲染。",
        )
        layout.addWidget(self.chk_keep_complex_cache, 5, 0, 1, 2)

        self.imported_complex_render = QLineEdit("")
        self.imported_complex_render.setMinimumWidth(260)
        self.imported_complex_render.setPlaceholderText("选择清何保存过的复杂模式成片；匹配当前时间线 IO 才会使用")
        set_tip(self.imported_complex_render, "只接受带清何匹配文件的缓存成片。时间线、入出点、帧率或时长不一致会拒绝检测，避免用错视频。")
        self.browse_imported_render_btn = QPushButton("选择视频")
        self.browse_imported_render_btn.clicked.connect(self.choose_imported_complex_render)
        set_tip(self.browse_imported_render_btn, "选择之前由“保存复杂模式缓存视频”生成的成片。")
        layout.addWidget(QLabel("使用已保存成片"), 6, 0)
        import_row = QHBoxLayout()
        import_row.addWidget(self.imported_complex_render, 1)
        import_row.addWidget(self.browse_imported_render_btn)
        layout.addLayout(import_row, 6, 1)

        self.reset_all_defaults_btn = QPushButton("一键还原全部默认设置")
        self.reset_all_defaults_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        set_tip(self.reset_all_defaults_btn, "恢复检测勾选、分析方式、批量检测、阈值、黑边遮幅、音频 BPM 标记和高级选项到插件默认值。不会删除字体收藏、样式库、捐赠记录或统计开关。")
        self.reset_all_defaults_btn.clicked.connect(self.reset_all_defaults)
        layout.addWidget(self.reset_all_defaults_btn, 7, 0, 1, 2)

        self.complex_hint.setObjectName("Muted")
        set_tip(self.complex_hint, "复杂模式会产生临时渲染文件，用最终画面做检测；调色后的坏帧要看最终像素，所以必须依赖它。")
        layout.addWidget(self.complex_hint, 8, 0, 1, 2)
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

        self.detection_splitter = QSplitter(Qt.Horizontal)
        self.detection_splitter.setChildrenCollapsible(False)
        self.detection_splitter.setHandleWidth(8)
        self.detection_splitter.addWidget(self.left_panel)
        self.detection_splitter.addWidget(self.results_tab)
        self.detection_splitter.setStretchFactor(0, 3)
        self.detection_splitter.setStretchFactor(1, 2)
        self.detection_splitter.setSizes([680, 440])
        self.detection_layout.addWidget(self.detection_splitter, 1)

        self.side_tabs.addTab(self.detection_tab, "黑帧夹帧检测")
        self.side_tabs.addTab(self.text_tab, "字幕")
        self.side_tabs.addTab(self.font_tab, "字体")
        self.side_tabs.addTab(self.audio_tab, "音频")
        self.side_tabs.setCurrentWidget(self.detection_tab)
        self.side_tabs.currentChanged.connect(self.animate_current_tab)
        set_tip(self.side_tabs, "像 DaVinci 页面一样切换：黑帧夹帧检测、字幕、字体和音频工具并列显示；检测结果留在检测页内。")
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
            self.text_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
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
            self.setMinimumSize(1120, 700)
            self.side_tabs.setCurrentWidget(self.font_tab)
            self.left_panel.hide()
            self.side_tabs.tabBar().hide()
            self.font_list.setMaximumHeight(360)
            self.font_preview_image.setMinimumHeight(130)
            self.font_preview_image.setMaximumHeight(150)
            self.font_table.setColumnWidth(2, 360)
            self.font_table.setColumnWidth(3, 92)
            self.font_table.setColumnWidth(4, 160)
            self.font_table.setColumnWidth(5, 76)
            self.compact_restore_btn.show()
            self.resize(1360, 820)
        else:
            self.setMinimumSize(960, 640)
            self.left_panel.show()
            self.side_tabs.tabBar().show()
            self.font_list.setMaximumHeight(260)
            self.font_preview_image.setMinimumHeight(86)
            self.font_preview_image.setMaximumHeight(112)
            self.font_table.setColumnWidth(2, 340)
            self.font_table.setColumnWidth(3, 84)
            self.font_table.setColumnWidth(4, 140)
            self.font_table.setColumnWidth(5, 76)
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
        self.text_initial_panel.setMaximumHeight(126)
        initial_layout = QHBoxLayout(self.text_initial_panel)
        initial_layout.setContentsMargins(18, 14, 18, 14)
        initial_layout.setSpacing(18)
        initial_copy = QVBoxLayout()
        initial_copy.setContentsMargins(0, 0, 0, 0)
        initial_copy.setSpacing(6)
        initial_title = QLabel("检测时间线文字")
        initial_title.setObjectName("SectionTitle")
        initial_hint = QLabel("先选择要读取的文字类型：SRT 字幕轨、Text+ Fusion 文本；检测完成后再进入搜索、替换和表格编辑。")
        initial_hint.setObjectName("Muted")
        initial_hint.setWordWrap(True)
        initial_hint.setMaximumWidth(760)
        initial_copy.addWidget(initial_title)
        initial_copy.addWidget(initial_hint)
        initial_copy.addStretch(1)
        initial_row = QHBoxLayout()
        initial_row.setContentsMargins(0, 0, 0, 0)
        initial_row.setSpacing(10)
        self.text_scan_srt = QCheckBox("SRT")
        self.text_scan_srt.setChecked(True)
        self.text_scan_text = QCheckBox("TXT")
        self.text_scan_text.setChecked(False)
        self.text_scan_text.hide()
        set_tip(self.text_scan_text, "Resolve 19 暂未公开普通 TXT 文本内容读写接口，先隐藏该类型；后续新版 API 支持后再开放。")
        self.text_scan_textplus = QCheckBox("Text+")
        for checkbox in (self.text_scan_srt, self.text_scan_text, self.text_scan_textplus):
            checkbox.toggled.connect(self.update_text_scan_type_hint)
        self.text_initial_scan_btn = QPushButton("重新检测")
        self.text_initial_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        set_tip(self.text_initial_scan_btn, "按当前勾选类型重新扫描：SRT 字幕轨、Text+ Fusion 文本。普通 TXT 暂不开放，等 Resolve 新版 API 支持后再开发。")
        self.text_initial_scan_btn.clicked.connect(self.scan_text_layers)
        initial_row.addWidget(self.text_scan_srt)
        initial_row.addWidget(self.text_scan_text)
        initial_row.addWidget(self.text_scan_textplus)
        self.text_scan_type_hint = QLabel("当前扫描：SRT")
        self.text_scan_type_hint.setObjectName("Muted")
        initial_row.addWidget(self.text_scan_type_hint)
        initial_row.addWidget(self.text_initial_scan_btn)
        initial_layout.addStretch(1)
        initial_layout.addLayout(initial_copy, 2)
        initial_layout.addLayout(initial_row, 0)
        initial_layout.addStretch(1)
        layout.addWidget(self.text_initial_panel)

        self.text_search_panel = QFrame()
        self.text_search_panel.setObjectName("Panel")
        text_tools = QGridLayout(self.text_search_panel)
        text_tools.setContentsMargins(12, 10, 12, 10)
        text_tools.setHorizontalSpacing(8)
        text_tools.setVerticalSpacing(8)
        self.text_search = QLineEdit()
        self.text_search.setPlaceholderText("搜索 SRT / Text+ 文字层")
        self.text_scan_btn = QPushButton("查找")
        self.text_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        set_tip(self.text_scan_btn, "只在当前文字列表里查找关键词，不重新读取 Resolve；要重新读取 SRT/Text+，请点上方“重新检测”。")
        self.text_scan_btn.clicked.connect(self.filter_text_table_matches)
        self.text_search.returnPressed.connect(self.filter_text_table_matches)
        self.text_next_match_btn = QPushButton("\u4e0b\u4e00\u4e2a\u5339\u914d")
        set_tip(self.text_next_match_btn, "跳到当前搜索词的下一个匹配项，并尝试把 Resolve 播放头定位到对应字幕/文字层。")
        self.text_next_match_btn.clicked.connect(self.jump_to_next_text_match)
        self.text_replace = QLineEdit()
        self.text_replace.setPlaceholderText("\u66ff\u6362\u4e3a")
        self.text_replace_all_btn = QPushButton("\u6279\u91cf\u66ff\u6362")
        set_tip(self.text_replace_all_btn, "把当前搜索命中的文字批量替换为输入内容。SRT 支持写回；Text+ 写回取决于当前 Resolve/Fusion API 返回结果。")
        self.text_replace_all_btn.clicked.connect(self.replace_matched_text_items)
        self.text_undo_btn = QPushButton("撤回修改")
        self.text_undo_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.text_undo_btn.setEnabled(False)
        set_tip(self.text_undo_btn, "撤回插件最近一次文字修改。SRT 走插件缓存；Text+ 删除建议优先使用 Resolve 自带撤回。")
        self.text_undo_btn.clicked.connect(self.undo_last_text_change)
        self.text_delete_btn = QPushButton("\u5220\u9664")
        set_tip(self.text_delete_btn, "删除当前选中的文字项。SRT 删除可通过插件撤回；Text+ 删除更依赖 Resolve 自带撤回。")
        self.text_delete_btn.clicked.connect(self.delete_selected_text_item)
        self.text_search_scan_type_hint = QLabel("当前扫描：SRT")
        self.text_search_scan_type_hint.setObjectName("Muted")
        text_tools.addWidget(QLabel("查找"), 0, 0)
        text_tools.addWidget(self.text_search, 0, 1, 1, 3)
        text_tools.addWidget(self.text_scan_btn, 0, 4)
        text_tools.addWidget(self.text_next_match_btn, 0, 5)
        text_tools.addWidget(self.text_search_scan_type_hint, 0, 6)
        text_tools.addWidget(QLabel("替换"), 1, 0)
        text_tools.addWidget(self.text_replace, 1, 1, 1, 3)
        text_tools.addWidget(self.text_replace_all_btn, 1, 4)
        text_tools.addWidget(self.text_undo_btn, 1, 5)
        text_tools.addWidget(self.text_delete_btn, 1, 6)
        text_tools.setColumnStretch(1, 2)
        text_tools.setColumnStretch(2, 1)
        text_tools.setColumnStretch(3, 1)
        layout.addWidget(self.text_search_panel)
        self.text_replace_panel = self.text_search_panel

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
        self.text_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.text_highlight_delegate = SearchHighlightDelegate(self.text_table)
        self.text_table.setItemDelegateForColumn(3, self.text_highlight_delegate)
        self.text_table.cellDoubleClicked.connect(self.on_text_cell_double_clicked)
        self.text_table.cellChanged.connect(self.on_text_cell_changed)
        text_table_layout.addWidget(self.text_table, 1)
        layout.addWidget(text_table_panel, 1)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        self.text_status = QLabel("未扫描文字层。")
        self.text_status.setObjectName("Muted")
        self.text_status.setWordWrap(True)
        status_row.addWidget(self.text_status, 1)
        layout.addLayout(status_row)

        self.text_table_panel = text_table_panel
        for widget in (self.text_search_panel, self.text_table_panel, self.text_status):
            widget.hide()
        self.update_text_scan_type_hint()
        return tab

    def _build_font_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        top_panel = QFrame()
        top_panel.setObjectName("Panel")
        top = QGridLayout(top_panel)
        top.setContentsMargins(10, 8, 10, 8)
        top.setHorizontalSpacing(8)
        top.setVerticalSpacing(8)
        self.font_search = QLineEdit()
        self.font_search.setPlaceholderText("搜索字体 / 中文 / PostScript 名称")
        set_tip(self.font_search, "按中文名、英文名、PostScript 名或别名筛选本机字体；只筛选插件字体库，不修改时间线。")
        self.font_search.textChanged.connect(self.refresh_font_list)
        self.font_target = QLineEdit()
        self.font_target.setPlaceholderText("目标字体名称")
        set_tip(self.font_target, "最终写入 Text+ 的字体名。插件会优先使用已验证的 Resolve 可用名称；预览提示不可用时，不建议直接替换。")
        self.font_style_combo = QComboBox()
        self.font_style_combo.setMinimumWidth(128)
        set_tip(self.font_style_combo, "选择字体粗细/样式。这里显示系统字体样式；Resolve 能否实际应用，以预览和替换后的画面为准。")
        self.font_style_combo.currentIndexChanged.connect(self.on_font_style_changed)
        self.font_scan_btn = QPushButton("扫描时间线字体")
        self.font_scan_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        set_tip(self.font_scan_btn, "读取目标时间线里的 Text+ 字体层，并列出时间码、文字内容、当前字体和可替换状态。字幕很多时可能需要等待。")
        self.font_scan_btn.clicked.connect(self.scan_font_layers)
        top.addWidget(QLabel("字体库"), 0, 0)
        top.addWidget(self.font_search, 0, 1, 1, 3)
        top.addWidget(self.font_scan_btn, 0, 4)
        top.addWidget(QLabel("目标字体"), 1, 0)
        top.addWidget(self.font_target, 1, 1, 1, 2)
        top.addWidget(QLabel("粗细"), 1, 3)
        top.addWidget(self.font_style_combo, 1, 4)
        top.setColumnStretch(1, 2)
        top.setColumnStretch(2, 1)
        layout.addWidget(top_panel)

        main_split = QSplitter(Qt.Horizontal)
        main_split.setChildrenCollapsible(False)
        browser_panel = QFrame()
        browser_panel.setObjectName("Panel")
        browser_panel.setMinimumWidth(330)
        browser_panel.setMaximumWidth(560)
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(10, 8, 10, 8)
        browser_layout.setSpacing(7)
        browser_title_row = QHBoxLayout()
        browser_title = QLabel("字体库")
        browser_title.setObjectName("SectionTitle")
        fav_row = QHBoxLayout()
        self.font_favorite_only = QCheckBox("收藏")
        set_tip(self.font_favorite_only, "只显示已收藏字体；收藏记录保存在本机插件配置里。")
        self.font_favorite_only.toggled.connect(self.refresh_font_list)
        self.font_add_favorite_btn = QPushButton("收藏")
        set_tip(self.font_add_favorite_btn, "把当前选中的字体加入收藏，方便常用字体快速筛选。")
        self.font_add_favorite_btn.clicked.connect(self.add_selected_font_favorite)
        self.font_remove_favorite_btn = QPushButton("取消")
        set_tip(self.font_remove_favorite_btn, "把当前选中的字体从收藏列表移除，不会删除系统字体。")
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
        self.font_list.itemDoubleClicked.connect(lambda _item: self.apply_font_to_selected_layer(check_fusion_first=True))
        browser_layout.addWidget(self.font_list, 1)

        self.font_preview_image = QLabel()
        self.font_preview_image.setMinimumHeight(122)
        self.font_preview_image.setMaximumHeight(168)
        self.font_preview_image.setAlignment(Qt.AlignCenter)
        self.font_preview_image.setObjectName("Panel")
        set_tip(self.font_preview_image, "切换字体时生成本地图片预览；如果系统实际 fallback 到别的字体，会显示 Font Not Found 提示。")
        browser_layout.addWidget(self.font_preview_image)

        right_panel = QWidget()
        right_panel.setMinimumWidth(620)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        layers_panel = QFrame()
        layers_panel.setObjectName("Panel")
        layers_layout = QVBoxLayout(layers_panel)
        layers_layout.setContentsMargins(10, 8, 10, 8)
        layers_layout.setSpacing(7)
        layers_title = QLabel("时间线文字层")
        layers_title.setObjectName("SectionTitle")
        layers_layout.addWidget(layers_title)

        self.font_table = QTableWidget(0, 6)
        self.font_table.setHorizontalHeaderLabels(["#", "Timecode", "文字 / 说明", "层", "当前字体", "状态"])
        self.font_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.font_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.font_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.font_table.setWordWrap(False)
        self.font_table.setTextElideMode(Qt.ElideRight)
        self.font_table.verticalHeader().setVisible(False)
        self.font_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.font_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.font_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.font_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.font_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.font_table.setColumnWidth(2, 360)
        self.font_table.setColumnWidth(3, 84)
        self.font_table.setColumnWidth(4, 150)
        self.font_table.setColumnWidth(5, 76)
        self.font_table.cellDoubleClicked.connect(lambda _row, _col: self.jump_to_selected_font_item())
        self.font_table.itemSelectionChanged.connect(lambda: self.update_font_preview(self.selected_font_name()))
        set_tip(self.font_table, "时间线文字层列表：按时间码选择一个或多个 Text+；双击可跳转，Shift/Cmd 多选后可批量应用字体或样式。")
        layers_layout.addWidget(self.font_table, 1)

        layer_actions = QHBoxLayout()
        layer_actions.setSpacing(8)
        self.font_jump_btn = QPushButton("跳转")
        set_tip(self.font_jump_btn, "把 Resolve 播放头跳到选中文字层所在时间码，方便确认画面。")
        self.font_jump_btn.clicked.connect(self.jump_to_selected_font_item)
        self.font_copy_style_btn = QPushButton("复制")
        set_tip(self.font_copy_style_btn, "复制选中 Text+ 的外观样式，不复制文字内容，也不复制位置/布局。适合把颜色、描边、阴影等套到其他字幕。")
        self.font_copy_style_btn.clicked.connect(self.copy_selected_textplus_style)
        self.font_copy_position_btn = QPushButton("复制位置")
        set_tip(self.font_copy_position_btn, "只复制选中 Text+ 的位置/变换信息。用于统一字幕位置；不会复制文字、字体、颜色。")
        self.font_copy_position_btn.clicked.connect(self.copy_selected_textplus_position)
        self.font_apply_style_btn = QPushButton("应用到选中")
        set_tip(self.font_apply_style_btn, "把最近复制的样式、位置或字体应用到选中的 Text+。支持多选；应用前请确认右侧列表选中的是目标层。")
        self.font_apply_style_btn.clicked.connect(self.apply_copied_textplus_style_to_selected)
        self.font_copy_font_btn = QPushButton("只复制字体")
        set_tip(self.font_copy_font_btn, "只复制选中 Text+ 的字体和粗细。之后点“应用到选中”时，不改字号、颜色、字距、位置、描边、阴影。")
        self.font_copy_font_btn.clicked.connect(self.copy_selected_textplus_font_only)
        layer_actions.addWidget(self.font_jump_btn)
        layer_actions.addWidget(self.font_copy_style_btn)
        layer_actions.addWidget(self.font_copy_position_btn)
        layer_actions.addWidget(self.font_apply_style_btn)
        layer_actions.addWidget(self.font_copy_font_btn)
        layer_actions.addStretch(1)
        layers_layout.addLayout(layer_actions)

        right_layout.addWidget(layers_panel, 1)
        main_split.addWidget(browser_panel)

        self.font_aux_tabs = QTabWidget()
        self.font_aux_tabs.setObjectName("FontAuxTabs")
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
        set_tip(self.font_style_library_list, "本地 Text+ 样式库列表。样式保存在插件目录，换项目也能继续使用。")
        library_buttons = QVBoxLayout()
        self.font_save_style_btn = QPushButton("保存样式")
        set_tip(self.font_save_style_btn, "把当前已复制的 Text+ 样式保存到本地样式库；没有复制时会先尝试读取当前选中 Text+。")
        self.font_save_style_btn.clicked.connect(self.save_copied_textplus_style_to_library)
        self.font_load_style_btn = QPushButton("载入样式")
        set_tip(self.font_load_style_btn, "把样式库选中项载入为当前样式，等待你点“应用到选中”。载入本身不会修改时间线。")
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
        set_tip(self.font_style_preview_image, "样式库 16:9 预览：只用于看大概字号、颜色和位置，不代表 Resolve 最终渲染完全一致。")
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
            "提示：这里只显示媒体池里可识别为 Text+ / Fusion Title 的素材；模板帧率最好和目标时间线一致。",
        )
        self.refresh_caption_templates_btn = QPushButton("刷新模板")
        set_tip(self.refresh_caption_templates_btn, "扫描当前项目媒体池，只列出可识别为 Text+ / Fusion Title 的模板；列表会显示媒体池素材名、类型和 fps。")
        self.refresh_caption_templates_btn.clicked.connect(self.refresh_caption_templates)
        template_row.addWidget(QLabel("SRT模板"))
        template_row.addWidget(self.caption_template_combo, 1)
        template_row.addWidget(self.refresh_caption_templates_btn)
        srt_layout.addLayout(template_row)

        srt_actions = QHBoxLayout()
        self.srt2text_marker_checkbox = QCheckBox("写入转换标记")
        self.srt2text_marker_checkbox.setChecked(False)
        set_tip(
            self.srt2text_marker_checkbox,
            "默认关闭。\n\n"
            "开启后，每条由 SRT 转成的 Text+ 会写入一个 [QH-SRT2TEXT] 内部片段标记，之后字体面板能更稳地把同批字幕折叠成一组。\n\n"
            "缺点：字幕很多时，达芬奇逐条写 marker 会明显变慢，甚至看起来像卡死；只想先快速转换字幕时请保持关闭。",
        )
        self.font_convert_srt_btn = QPushButton("SRT转Text+")
        set_tip(
            self.font_convert_srt_btn,
            "把当前时间线启用的 SRT 字幕转换成 Text+。\n\n"
            "怎么用：\n"
            "1. 先确认目标时间线是当前要转换的时间线。\n"
            "2. 默认可直接用“内置默认 Text+ 模板”。\n"
            "3. 想要自己的字幕样式，就先在达芬奇里做好一个 Text+ 模板，点“刷新模板”后选择它。\n"
            "4. 点击本按钮后，插件会在最上层新建视频轨，按 SRT 原时间码生成 Text+，并写入每条字幕文字。\n\n"
            "速度提示：默认不会写 [QH-SRT2TEXT] 内部标记，因为上千条字幕逐条 AddMarker 会非常慢；需要后续稳定折叠成组时，再勾选“写入转换标记”。\n\n"
            "注意：如果模板 fps 和时间线 fps 不同，会先弹窗提示；直接继续会自动补偿时长。",
        )
        self.font_convert_srt_btn.clicked.connect(self.convert_srt_to_textplus)
        srt_actions.addWidget(self.srt2text_marker_checkbox)
        srt_actions.addWidget(self.font_convert_srt_btn)
        srt_actions.addStretch(1)
        srt_layout.addLayout(srt_actions)
        self.font_aux_tabs.addTab(style_panel, "样式库")
        self.font_aux_tabs.addTab(srt_panel, "SRT 转 Text+")
        self.font_aux_tabs.setMaximumHeight(245)
        right_layout.addWidget(self.font_aux_tabs)

        main_split.addWidget(right_panel)
        main_split.setStretchFactor(0, 0)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([440, 900])
        layout.addWidget(main_split, 1)

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
        set_tip(self.audio_summary, "这里显示音频扫描、单声道标记或 BPM 识别的最新结果。失败时会说明是 API 不支持、没有选中音频，还是找不到源文件。")
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
        set_tip(self.audio_copy_tutorial_btn, "复制当前教程卡的 Fairlight 参数到剪贴板。插件不会自动添加音频效果器，需要你在 Resolve 里手动操作。")
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
        set_tip(self.scan_audio_btn, "读取目标时间线音频轨道和片段声道信息，列出疑似单声道；不会写标记、不会改片段。")
        self.scan_audio_btn.clicked.connect(self.scan_mono_audio)

        self.mark_audio_btn = QPushButton("标记单声道")
        self.mark_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        set_tip(self.mark_audio_btn, "把单声道音频片段做可视标记：统一尝试修改片段颜色，并写音频片段自身中点标记；Resolve 不接受片段标记时才退到时间线中点。")
        self.mark_audio_btn.clicked.connect(self.mark_mono_audio)

        self.clear_mono_audio_btn = QPushButton("清除单声道标记")
        self.clear_mono_audio_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        set_tip(self.clear_mono_audio_btn, "只清除插件生成的 [BFD-AUDIO] 单声道音频标记，不会清除 BPM 标记、黑帧标记或你手动打的普通标记。")
        self.clear_mono_audio_btn.clicked.connect(self.clear_mono_audio_markers)

        self.audio_bpm_btn = QPushButton("识别选中BPM")
        self.audio_bpm_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        set_tip(self.audio_bpm_btn, "识别音乐 BPM：优先读取鼠标选中的音频；Resolve 没返回选中对象时，会改用播放头所在音频，播放头下多条音频时再让你选择。")
        self.audio_bpm_btn.clicked.connect(self.estimate_selected_audio_bpm)

        bpm_options = QHBoxLayout()
        self.bpm_start_spin = QDoubleSpinBox()
        self.bpm_start_spin.setRange(40.0, 240.0)
        self.bpm_start_spin.setDecimals(1)
        self.bpm_start_spin.setValue(120.0)
        self.bpm_start_spin.setSingleStep(1.0)
        set_tip(self.bpm_start_spin, "内部保留参数：当前不会改变 BPM 识别结果，只会写进节拍标记说明。")
        self.bpm_tightness_spin = QDoubleSpinBox()
        self.bpm_tightness_spin.setRange(0.0, 400.0)
        self.bpm_tightness_spin.setDecimals(0)
        self.bpm_tightness_spin.setValue(100.0)
        self.bpm_tightness_spin.setSingleStep(10.0)
        set_tip(self.bpm_tightness_spin, "内部保留参数：当前不会影响本地 BPM 估算。")
        self.bpm_hop_spin = QSpinBox()
        self.bpm_hop_spin.setRange(128, 4096)
        self.bpm_hop_spin.setValue(512)
        self.bpm_hop_spin.setSingleStep(128)
        set_tip(self.bpm_hop_spin, "内部保留参数：当前不会改变分析精度。")
        for text, widget in (("起始BPM", self.bpm_start_spin), ("紧度", self.bpm_tightness_spin), ("步长", self.bpm_hop_spin)):
            label = QLabel(text)
            label.setObjectName("Muted")
            label.setVisible(False)
            widget.setVisible(False)
            bpm_options.addWidget(label)
            bpm_options.addWidget(widget)
        self.bpm_marker_scope_combo = QComboBox()
        self.bpm_marker_scope_combo.addItem("标到音频片段", "clip")
        self.bpm_marker_scope_combo.addItem("标到时间线", "timeline")
        set_tip(self.bpm_marker_scope_combo, "选择节拍标记写入位置。音频片段标记会跟着音乐片段移动；时间线标记固定在时间线上，适合全局对拍参考。")
        scope_label = QLabel("标记位置")
        scope_label.setObjectName("Muted")
        bpm_options.addWidget(scope_label)
        bpm_options.addWidget(self.bpm_marker_scope_combo)
        self.bpm_marker_every_spin = QSpinBox()
        self.bpm_marker_every_spin.setRange(1, 32)
        self.bpm_marker_every_spin.setValue(4)
        self.bpm_marker_every_spin.setSingleStep(1)
        set_tip(self.bpm_marker_every_spin, "控制节拍标记密度：1 表示每拍都标；4 表示每 4 拍标一次。插件会从播放头确认的重拍出发，保持完整拍号结构，并吸附附近可信的实际 beat 点。")
        marker_every_label = QLabel("每几拍")
        marker_every_label.setObjectName("Muted")
        bpm_options.addWidget(marker_every_label)
        bpm_options.addWidget(self.bpm_marker_every_spin)
        self.bpm_marker_phase_spin = QSpinBox()
        self.bpm_marker_phase_spin.setRange(1, 32)
        self.bpm_marker_phase_spin.setValue(1)
        self.bpm_marker_phase_spin.setSingleStep(1)
        set_tip(self.bpm_marker_phase_spin, "内部保留参数：当前节拍锚点由播放头决定，不需要手动设置起始拍。")
        self.bpm_marker_every_spin.valueChanged.connect(self.update_bpm_marker_phase_range)
        marker_phase_label = QLabel("起始拍")
        marker_phase_label.setObjectName("Muted")
        marker_phase_label.setVisible(False)
        self.bpm_marker_phase_spin.setVisible(False)
        bpm_options.addWidget(marker_phase_label)
        bpm_options.addWidget(self.bpm_marker_phase_spin)
        bpm_options.addStretch(1)

        self.audio_bpm_mark_btn = QPushButton("生成节拍标记")
        self.audio_bpm_mark_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        set_tip(self.audio_bpm_mark_btn, "先选中音乐片段，再把播放头放到你确认的重拍锚点上。选中对象读不到时，会回到播放头音频/候选列表逻辑。")
        self.audio_bpm_mark_btn.clicked.connect(self.mark_selected_audio_beats)
        self.audio_bpm_clear_btn = QPushButton("清除节拍标记")
        self.audio_bpm_clear_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        set_tip(self.audio_bpm_clear_btn, "按“标记位置”清除插件生成的 [QH-BPM] 节拍标记，不会清除黑帧检测标记或你手动打的普通标记。")
        self.audio_bpm_clear_btn.clicked.connect(self.clear_audio_bpm_markers)
        self.audio_bpm_clear_current_btn = QPushButton("清除当前音频节拍")
        self.audio_bpm_clear_current_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        set_tip(self.audio_bpm_clear_current_btn, "清除 Resolve 当前返回的音频片段 [QH-BPM] 标记：能读到鼠标选中音频就清选中片段；读不到选中对象时，清播放头所在音频片段。")
        self.audio_bpm_clear_current_btn.clicked.connect(self.clear_current_audio_bpm_markers)

        self.media_pool_probe_btn = QPushButton("媒体池探针")
        self.media_pool_probe_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogInfoView))
        set_tip(self.media_pool_probe_btn, "探测 MediaPool / Folder / MediaPoolItem / TimelineItem 可用 API、样本属性和选中素材信息；结果会写入反馈，方便后续补脚本规则。")
        self.media_pool_probe_btn.clicked.connect(self.run_media_pool_probe)
        self.media_pool_probe_btn.setVisible(False)

        actions.addWidget(self.scan_audio_btn)
        actions.addWidget(self.mark_audio_btn)
        actions.addWidget(self.clear_mono_audio_btn)
        actions.addWidget(self.audio_bpm_btn)
        actions.addWidget(self.audio_bpm_mark_btn)
        actions.addWidget(self.audio_bpm_clear_btn)
        actions.addWidget(self.audio_bpm_clear_current_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addLayout(bpm_options)

        self.audio_list = QTextEdit()
        self.audio_list.setReadOnly(True)
        self.audio_list.setMinimumHeight(150)
        self.audio_list.setMaximumHeight(210)
        self.audio_list.setLineWrapMode(QTextEdit.WidgetWidth)
        self.audio_list.setPlaceholderText("扫描结果会列出轨道、片段、起止帧和识别原因。")
        set_tip(self.audio_list, "音频结果明细：会列出轨道、片段、起止帧、识别依据，以及 BPM 候选值或失败原因。")
        layout.addWidget(self.audio_list, 1)
        self.update_bpm_marker_phase_range()
        return tab

    def update_bpm_marker_phase_range(self) -> None:
        if not hasattr(self, "bpm_marker_every_spin") or not hasattr(self, "bpm_marker_phase_spin"):
            return
        maximum = max(1, int(self.bpm_marker_every_spin.value()))
        current = int(self.bpm_marker_phase_spin.value())
        self.bpm_marker_phase_spin.setRange(1, maximum)
        self.bpm_marker_phase_spin.setValue(min(current, maximum))

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
            ("black_border", "黑边", "画面边缘露出的黑边。", MARKER_COLORS["black_border"]),
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

    def set_connection_state(self, connected: bool | None, text: str | None = None) -> None:
        if connected is None:
            label = text or "连接中"
            object_name = "BadgeWarn"
        else:
            label = text or ("已连接" if connected else "离线参数")
            object_name = "BadgeOk" if connected else "BadgeWarn"
        self.connection_badge.setText(label)
        self.connection_badge.setObjectName(object_name)
        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)

    def set_timeline_loading_state(self, message: str) -> None:
        self._loading_timelines = True
        self.timeline_combo.clear()
        self.timeline_combo.addItem(message, {"index": 1, "name": "当前时间线", "fps": BASELINE_FPS})
        self.timeline_combo.setEnabled(False)
        self.batch_timeline_list.clear()
        self.batch_timeline_list.setEnabled(False)
        self._loading_timelines = False
        self.set_connection_state(None, "连接中")

    def start_startup_sync(self) -> None:
        if self.startup_sync_worker is not None and self.startup_sync_worker.isRunning():
            return
        self.set_timeline_loading_state("正在同步 Resolve 时间线...")
        self.startup_sync_worker = StartupSyncWorker()
        self.startup_sync_worker.done.connect(self.on_startup_sync_done)
        self.startup_sync_worker.finished.connect(self.startup_sync_worker.deleteLater)
        self.startup_sync_worker.start()

    def on_startup_sync_done(self, payload: dict) -> None:
        timelines: list[TimelineInfo] = []
        for item in payload.get("timelines") or []:
            if not isinstance(item, dict):
                continue
            try:
                timelines.append(
                    TimelineInfo(
                        int(item.get("index", len(timelines) + 1)),
                        str(item.get("name") or f"Timeline {len(timelines) + 1}"),
                        float(item.get("fps") or BASELINE_FPS),
                        str(item.get("uid") or ""),
                    )
                )
            except Exception:
                continue
        self.apply_timeline_snapshot(
            timelines,
            payload.get("current_identity") if isinstance(payload.get("current_identity"), dict) else {},
            bool(payload.get("connected")),
        )
        self.resolve_version_text = str(payload.get("resolve_version") or "")
        self._capture_current_timeline_uid()
        if payload.get("ok"):
            self._log("Resolve API: " + ("已连接" if payload.get("connected") else "未连接，使用离线参数模式"))
        else:
            self._log("Resolve API 同步失败：" + str(payload.get("message") or "未知错误"))
        self.startup_sync_worker = None

    def apply_timeline_snapshot(
        self,
        timelines: list[TimelineInfo],
        current_identity: dict | None = None,
        connected: bool | None = None,
    ) -> None:
        current_identity = current_identity or {}
        current_uid = str(current_identity.get("uid", "")) if current_identity.get("ok") else ""
        current_name = str(current_identity.get("name", "")) if current_identity.get("ok") else ""
        current_combo_index = 0
        self._loading_timelines = True
        self.timelines = timelines
        self.timeline_combo.clear()
        self.timeline_combo.setEnabled(True)
        self.batch_timeline_list.clear()
        for tl in self.timelines:
            data = asdict(tl)
            label = f"{tl.index}. {tl.name}  /  {tl.fps:g} fps"
            self.timeline_combo.addItem(label, data)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, data)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            name_marks_current = "当前" in tl.name
            plain_name = tl.name.replace("  (当前)", "").replace("(当前)", "").strip()
            item.setCheckState(Qt.Checked if name_marks_current else Qt.Unchecked)
            is_current = bool(
                name_marks_current
                or (current_uid and tl.uid == current_uid)
                or (current_name and plain_name == current_name)
            )
            if is_current:
                current_combo_index = self.timeline_combo.count() - 1
                item.setCheckState(Qt.Checked)
            elif current_uid or current_name:
                item.setCheckState(Qt.Unchecked)
            self.batch_timeline_list.addItem(item)
        if not self.timelines:
            self.timeline_combo.addItem("未读取到 Resolve 时间线", {"index": 1, "name": "当前时间线", "fps": BASELINE_FPS})
        if connected is not None:
            self.set_connection_state(bool(connected))
        if self.batch_timeline_list.count() > 0 and not any(
            self.batch_timeline_list.item(i).checkState() == Qt.Checked for i in range(self.batch_timeline_list.count())
        ):
            self.batch_timeline_list.item(0).setCheckState(Qt.Checked)
        if self.timeline_combo.count() > 0:
            self.timeline_combo.setCurrentIndex(current_combo_index)
        self.batch_timeline_list.setEnabled(self.chk_batch_timelines.isChecked())
        self._loading_timelines = False
        self._control_fps = self.selected_fps()
        self.update_fps_hint()

    def refresh_timelines(self) -> None:
        timelines = self.bridge.list_timelines()
        current_identity = self.bridge.current_timeline_identity()
        connected = self.bridge.is_connected()
        self.apply_timeline_snapshot(timelines, current_identity, connected)

    def on_timeline_changed(self) -> None:
        if self._loading_timelines or self._loading_settings:
            return
        self._control_fps = self.selected_fps()
        self.update_fps_hint()

    def on_batch_toggled(self, checked: bool) -> None:
        self.batch_timeline_list.setEnabled(checked)
        self.chk_batch_read_io.setEnabled(checked)

    def selected_timeline_data(self) -> dict:
        return self.timeline_combo.currentData() or {"index": 1, "name": "当前时间线", "fps": 25.0}

    def current_resolve_timeline_data(self) -> dict:
        self.refresh_timelines()
        return self.selected_timeline_data()

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
            "donation_prompt_seen": bool(self.donation_prompt_seen),
            "timeline_index": self.timeline_combo.currentIndex(),
            "stuck_frames": self.stuck_frames.value(),
            "suspect_frames": self.suspect_frames.value(),
            "pix_th": self.pixel_threshold.value(),
            "pix_th_unit": "percent",
            "black_border_px": self.black_border_px.value(),
            "black_border_aspect_preset": self.black_border_aspect_preset.currentData(),
            "black_border_matte_aspect": self.current_black_border_aspect(),
            "min_black_frames": self.min_black_frames.value(),
            "content_sample_interval": self.content_sample_interval.value(),
            "content_sample_default_v7": True,
            "bpm_marker_every": self.bpm_marker_every_spin.value(),
            "bpm_marker_phase": self.bpm_marker_phase_spin.value(),
            "complex_cache_dir": self.complex_cache_dir.text().strip(),
            "keep_complex_cache": self.chk_keep_complex_cache.isChecked(),
            "imported_complex_render": self.imported_complex_render.text().strip(),
            "batch_enabled": self.chk_batch_timelines.isChecked(),
            "batch_read_io": self.chk_batch_read_io.isChecked(),
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
                "black_border": self.chk_black_border.isChecked(),
                "corrupt": self.chk_corrupt.isChecked(),
                "clear": self.chk_clear.isChecked(),
                "mark_hidden": self.chk_mark_hidden.isChecked(),
                "partial_opacity": self.chk_partial_opacity.isChecked(),
                "png_opaque": self.chk_png_opaque.isChecked(),
                "png_opaque_default_v2": True,
                "nested_render": (not complex_mode) and self.chk_nested_render.isChecked(),
                "complex": self.chk_complex.isChecked(),
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
            if isinstance(data.get("donation_prompt_seen"), bool):
                self.donation_prompt_seen = bool(data.get("donation_prompt_seen"))
            if isinstance(data.get("theme"), str):
                self.apply_theme(str(data.get("theme") or "default"), update_combo=True, persist=False)
            else:
                self.apply_theme("default", update_combo=True, persist=False)
            has_current_timeline = any(
                "当前" in self.timeline_combo.itemText(index)
                for index in range(self.timeline_combo.count())
            )
            if (
                self.timeline_combo.count() > 0
                and self.timeline_combo.isEnabled()
                and not self.bridge.is_connected()
                and not has_current_timeline
                and isinstance(data.get("timeline_index"), int)
            ):
                self.timeline_combo.setCurrentIndex(max(0, min(self.timeline_combo.count() - 1, data["timeline_index"])))
            for name, widget in [
                ("content_sample_interval", self.content_sample_interval),
                ("black_border_px", self.black_border_px),
                ("bpm_marker_every", self.bpm_marker_every_spin),
                ("bpm_marker_phase", self.bpm_marker_phase_spin),
            ]:
                if isinstance(data.get(name), int):
                    value = int(data[name])
                    if name == "content_sample_interval" and value == 3 and data.get("content_sample_default_v7") is not True:
                        value = DEFAULT_CONTENT_SAMPLE_INTERVAL
                    widget.setValue(value)
            if isinstance(data.get("complex_cache_dir"), str) and data["complex_cache_dir"].strip():
                self.complex_cache_dir.setText(data["complex_cache_dir"].strip())
            if isinstance(data.get("keep_complex_cache"), bool):
                self.chk_keep_complex_cache.setChecked(bool(data.get("keep_complex_cache")))
            if isinstance(data.get("imported_complex_render"), str):
                self.imported_complex_render.setText(data.get("imported_complex_render", "").strip())
            if isinstance(data.get("black_border_matte_aspect"), (int, float)):
                self.set_black_border_aspect_from_value(float(data.get("black_border_matte_aspect") or 0.0))
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
                "black_border": self.chk_black_border,
                "clear": self.chk_clear,
                "mark_hidden": self.chk_mark_hidden,
                "partial_opacity": self.chk_partial_opacity,
                "png_opaque": self.chk_png_opaque,
                "nested_render": self.chk_nested_render,
                "complex": self.chk_complex,
                "html": self.chk_html,
                "analytics": self.chk_analytics,
            }
            if checks.get("png_opaque_default_v2") is not True:
                checks["png_opaque"] = True
            for key, widget in check_map.items():
                if isinstance(checks.get(key), bool):
                    widget.setChecked(checks[key])
            if self.chk_complex.isChecked():
                self.chk_nested_render.setChecked(False)
                self.chk_nested_render.setEnabled(False)
            if isinstance(checks.get("font_inventory_consent"), bool):
                self.font_inventory_consent = bool(checks.get("font_inventory_consent"))
            if isinstance(checks.get("corrupt"), bool) and self.chk_complex.isChecked():
                self.chk_corrupt.setChecked(checks["corrupt"])
            self.chk_batch_timelines.setChecked(bool(data.get("batch_enabled", False)))
            if isinstance(data.get("batch_read_io"), bool):
                self.chk_batch_read_io.setChecked(bool(data.get("batch_read_io")))
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

    def table_muted_colors(self) -> tuple[QColor, QColor]:
        theme = getattr(self, "theme_name", "default")
        if theme == "dark":
            return QColor("#1e293b"), QColor("#cbd5e1")
        if theme == "eye":
            return QColor("#edf4df"), QColor("#526247")
        return QColor("#f1f5f9"), QColor("#475569")

    def table_match_colors(self) -> tuple[QColor, QColor]:
        theme = getattr(self, "theme_name", "default")
        if theme == "dark":
            return QColor("#713f12"), QColor("#fef3c7")
        if theme == "eye":
            return QColor("#e3efbd"), QColor("#334229")
        return QColor("#fff3bf"), QColor("#172033")

    def ask_enable_complex_mode(self, title: str, message: str, confirm_text: str = "启用复杂模式") -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        cancel_btn = box.addButton("继续普通模式 / 取消", QMessageBox.RejectRole)
        confirm_btn = box.addButton(confirm_text, QMessageBox.AcceptRole)
        confirm_btn.setStyleSheet(
            "QPushButton { color: #64748b; background: #e5e7eb; border-color: #cbd5e1; }"
            "QPushButton:hover { background: #dbe1ea; }"
        )
        box.setDefaultButton(cancel_btn)
        box.setEscapeButton(cancel_btn)
        box.exec()
        return box.clickedButton() is confirm_btn

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
        self.black_border_px.setValue(DEFAULT_BLACK_BORDER_PX)
        self.set_black_border_aspect_from_value(0.0)
        self.content_sample_interval.setValue(DEFAULT_CONTENT_SAMPLE_INTERVAL)
        self.update_fps_hint()
        self.save_settings()

    def reset_all_defaults(self) -> None:
        answer = QMessageBox.question(
            self,
            "还原全部默认设置",
            "这会恢复检测勾选、分析方式、批量检测、阈值、黑边遮幅和高级选项到默认值。\n\n"
            "不会删除字体收藏、样式库、捐赠记录或统计开关。继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.chk_error.setChecked(True)
        self.chk_suspect.setChecked(True)
        self.chk_scene.setChecked(False)
        self.chk_gap.setChecked(True)
        self.chk_duplicate.setChecked(True)
        self.chk_content_dup.setChecked(False)
        self.chk_opacity.setChecked(True)
        self.chk_black_border.setChecked(False)
        self.chk_corrupt.setChecked(False)
        self.chk_nested_render.setChecked(False)
        self.chk_complex.setChecked(False)
        self.chk_clear.setChecked(True)
        self.chk_mark_hidden.setChecked(False)
        self.chk_partial_opacity.setChecked(True)
        self.chk_png_opaque.setChecked(True)
        self.chk_html.setChecked(False)
        self.chk_batch_timelines.setChecked(False)
        self.chk_batch_read_io.setChecked(False)
        for index in range(self.batch_timeline_list.count()):
            self.batch_timeline_list.item(index).setCheckState(Qt.Unchecked)
        selected = self.timeline_combo.currentIndex()
        if 0 <= selected < self.batch_timeline_list.count():
            self.batch_timeline_list.item(selected).setCheckState(Qt.Checked)
        self.complex_cache_dir.setText(str(default_complex_cache_dir()))
        self.chk_keep_complex_cache.setChecked(False)
        self.imported_complex_render.clear()
        if hasattr(self, "bpm_marker_scope_combo"):
            self.bpm_marker_scope_combo.setCurrentIndex(0)
        if hasattr(self, "bpm_marker_every_spin"):
            self.bpm_marker_every_spin.setValue(4)
        if hasattr(self, "bpm_marker_phase_spin"):
            self.bpm_marker_phase_spin.setValue(1)
        self.reset_threshold_defaults()
        self.save_settings()
        self._log("已还原全部默认设置。")

    def current_black_border_aspect(self) -> float:
        data = self.black_border_aspect_preset.currentData()
        try:
            preset_value = float(data)
        except Exception:
            preset_value = 0.0
        if preset_value < 0:
            return max(0.0, float(self.black_border_aspect.value()))
        return max(0.0, preset_value)

    def set_black_border_aspect_from_value(self, value: float) -> None:
        value = max(0.0, float(value or 0.0))
        for index, (_, preset_value) in enumerate(BLACK_BORDER_ASPECT_PRESETS):
            if preset_value >= 0 and abs(preset_value - value) < 0.005:
                self.black_border_aspect_preset.setCurrentIndex(index)
                self.black_border_aspect.setValue(value)
                self.black_border_aspect.setEnabled(False)
                return
        custom_index = self.black_border_aspect_preset.findText("自定义")
        if custom_index >= 0:
            self.black_border_aspect_preset.setCurrentIndex(custom_index)
        self.black_border_aspect.setValue(value)
        self.black_border_aspect.setEnabled(True)

    def on_black_border_preset_changed(self, *_args) -> None:
        data = self.black_border_aspect_preset.currentData()
        try:
            preset_value = float(data)
        except Exception:
            preset_value = 0.0
        custom = preset_value < 0
        self.black_border_aspect.setEnabled(custom)
        if not custom:
            self.black_border_aspect.setValue(max(0.0, preset_value))

    def choose_complex_cache_dir(self) -> None:
        current = self.complex_cache_dir.text().strip() or str(default_complex_cache_dir())
        selected = QFileDialog.getExistingDirectory(self, "选择复杂模式缓存目录", current)
        if selected:
            self.complex_cache_dir.setText(selected)

    def choose_imported_complex_render(self) -> None:
        current = self.imported_complex_render.text().strip() or self.complex_cache_dir.text().strip() or str(default_complex_cache_dir())
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择已保存复杂模式成片",
            current,
            "视频文件 (*.mp4 *.mov *.m4v);;所有文件 (*)",
        )
        if selected:
            self.imported_complex_render.setText(selected)

    def on_complex_mode_changed(self, checked: bool) -> None:
        if not checked:
            self.chk_nested_render.setEnabled(True)
            self.chk_corrupt.setChecked(False)
            self.complex_hint.setText("坏帧检测依赖复杂模式：需要入点和出点。")
        else:
            self.chk_nested_render.setChecked(False)
            self.chk_nested_render.setEnabled(False)
            self.complex_hint.setText("复杂模式会先渲染入出点范围，再分析最终画面；调色/OFX/Fusion 后的坏帧检测现在可选。")

    def on_corrupt_toggled(self, checked: bool) -> None:
        if not checked or self.chk_complex.isChecked():
            return
        answer = self.ask_enable_complex_mode(
            "开启复杂模式",
            "渲染坏帧检测必须先开启复杂模式并填写入出点。是否自动勾选复杂模式？",
        )
        if answer:
            self.chk_complex.setChecked(True)
        else:
            self.chk_corrupt.setChecked(False)

    def collect_params(self, selected: dict | None = None) -> dict:
        selected = selected or self.selected_timeline_data()
        black_border_aspect = self.current_black_border_aspect()
        black_border_forces_complex = self.chk_black_border.isChecked() and black_border_aspect > 0 and not self.chk_complex.isChecked()
        imported_render = self.imported_complex_render.text().strip()
        complex_mode = self.chk_complex.isChecked() or black_border_forces_complex or bool(imported_render)
        render_nested_segments = (not complex_mode) and self.chk_nested_render.isChecked()
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
            "batch_read_io": False,
            "complex_cache_dir": self.complex_cache_dir.text().strip() or str(default_complex_cache_dir()),
            "keep_complex_cache": self.chk_keep_complex_cache.isChecked(),
            "imported_complex_render_path": imported_render,
            "complex_mode_from_import": bool(imported_render),
            "marker_types": {
                "error": self.chk_error.isChecked(),
                "suspect": self.chk_suspect.isChecked(),
                "scene": self.chk_scene.isChecked(),
                "gap": self.chk_gap.isChecked(),
                "opacity": self.chk_opacity.isChecked(),
                "black_border": self.chk_black_border.isChecked(),
                "duplicate": self.chk_duplicate.isChecked(),
                "content_dup": self.chk_content_dup.isChecked(),
                "mixed_cut": False,
            },
            "detect_duplicate": self.chk_duplicate.isChecked(),
            "detect_content_dup": self.chk_content_dup.isChecked(),
            "detect_black_border": self.chk_black_border.isChecked(),
            "black_border_px": self.black_border_px.value(),
            "black_border_matte_aspect": black_border_aspect,
            "black_border_forces_complex": black_border_forces_complex,
            "detect_mixed_cut": False,
            "detect_corrupt": complex_mode and self.chk_corrupt.isChecked(),
            "html_report": self.chk_html.isChecked(),
            "clear_existing": self.chk_clear.isChecked(),
            "complex_mode": complex_mode,
            "merge_mode": True,
            "render_nested_segments": render_nested_segments,
            "mark_hidden_clips": self.chk_mark_hidden.isChecked(),
            "mark_partial_opacity": self.chk_partial_opacity.isChecked(),
            "png_as_opaque": self.chk_png_opaque.isChecked(),
            "headless": True,
        }

    def collect_batch_params(self) -> list[dict]:
        jobs: list[dict] = []
        use_per_timeline_io = self.chk_batch_timelines.isChecked() and self.chk_batch_read_io.isChecked()
        for selected in self.selected_batch_timelines():
            job = self.collect_params(selected)
            if use_per_timeline_io:
                job["batch_read_io"] = True
                job["manual_io_in"] = ""
                job["manual_io_out"] = ""
                job["io_source"] = "pending_after_activate"
            jobs.append(job)
        return jobs

    def track_usage_event(self, event_name: str, extra: dict | None = None) -> None:
        if not hasattr(self, "chk_analytics") or not self.chk_analytics.isChecked():
            return
        payload = {
            "event": event_name,
            "install_id": self.install_id,
            "app_version": APP_VERSION,
            "resolve_version": self.resolve_version_text,
            "platform": analytics_platform_label(),
            "platform_release": platform.release(),
            "session_seconds": int(max(0, time.time() - self.session_started_at)),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        if extra:
            payload["extra"] = extra
        send_analytics_event_async(payload)

    def check_for_updates(self, manual: bool = False) -> None:
        if getattr(self, "_checking_updates", False):
            if manual:
                self._log("正在检查更新，请稍等。")
            return
        self._checking_updates = True
        if manual:
            self.update_btn.setEnabled(False)
            self.update_btn.setText("检查中")
        self._log("正在检查插件更新。")

        def worker() -> None:
            manifest, error = fetch_update_manifest()
            info = update_info_from_manifest(manifest or {}) if manifest else {}
            self.update_check_finished.emit(info, manual, error)

        threading.Thread(target=worker, daemon=True).start()

    def on_update_check_finished(self, info: dict, manual: bool, error: str) -> None:
        self._checking_updates = False
        self.update_btn.setEnabled(True)
        self.update_btn.setText("更新")
        if error:
            self._log(error)
            if manual:
                QMessageBox.warning(self, "检查更新失败", error)
            return

        latest = str((info or {}).get("latest_version") or "").strip()
        if not latest:
            message = "更新清单里没有当前平台的版本号。"
            self._log(message)
            if manual:
                QMessageBox.information(self, "检查更新", message)
            return

        has_update = version_sort_key(latest) > version_sort_key(APP_VERSION)
        if not has_update:
            message = f"当前已是最新版本：v{APP_VERSION}"
            self._log(message)
            if manual:
                QMessageBox.information(self, "检查更新", message)
            return

        if not manual and self._update_notice_shown:
            return
        self._update_notice_shown = True
        notes = str((info or {}).get("notes") or "").strip()
        platform_label = "macOS" if (info or {}).get("platform") == "mac" else str((info or {}).get("platform") or "当前平台")
        download_url = str((info or {}).get("download_url") or "").strip()
        release_url = str((info or {}).get("release_url") or download_url).strip()
        manifest_url = str((info or {}).get("manifest_url") or "").strip()
        text = f"发现 {platform_label} 新版本：v{latest}\n当前版本：v{APP_VERSION}"
        if notes:
            text += f"\n\n{notes}"
        box = QMessageBox(self)
        box.setWindowTitle("发现新版本")
        box.setText(text)
        source_text = f"更新源：{manifest_url}" if manifest_url else "更新源：自动选择国内源，失败后再尝试备用源。"
        if download_url:
            box.setInformativeText(source_text + "\n\n一键更新会下载新安装包，并保留本机样式库与用户设置。")
        else:
            box.setInformativeText(source_text + "\n\n当前清单没有直接安装包地址，只能打开发布页。")
        one_click_btn = box.addButton("一键更新", QMessageBox.AcceptRole) if download_url else None
        open_btn = box.addButton("打开发布页", QMessageBox.ActionRole) if release_url else None
        later_btn = box.addButton("稍后", QMessageBox.RejectRole)
        box.setDefaultButton(one_click_btn or open_btn or later_btn)
        box.exec()
        clicked = box.clickedButton()
        if one_click_btn is not None and clicked == one_click_btn:
            self.start_one_click_update(info)
        elif open_btn is not None and clicked == open_btn:
            QDesktopServices.openUrl(QUrl(release_url))

    def start_one_click_update(self, info: dict) -> None:
        if self.update_worker and self.update_worker.isRunning():
            self._log("正在执行一键更新，请稍等。")
            return
        download_url = str((info or {}).get("download_url") or "").strip()
        if not download_url:
            QMessageBox.warning(self, "一键更新", "更新清单没有直接安装包地址，无法一键更新。")
            return
        progress = QProgressDialog(self)
        progress.setWindowTitle("一键更新")
        progress.setLabelText("准备下载更新包...")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 100)
        progress.setValue(1)
        progress.show()
        self.update_progress_dialog = progress

        worker = UpdateInstallWorker(info)
        self.update_worker = worker
        worker.progress.connect(self.on_update_install_progress)
        worker.done.connect(self.on_update_install_done)
        worker.start()

    def on_update_install_progress(self, percent: int, message: str) -> None:
        if self.update_progress_dialog:
            self.update_progress_dialog.setValue(max(0, min(100, int(percent))))
            self.update_progress_dialog.setLabelText(message or "正在更新...")
            QApplication.processEvents()
        self._log(message or "正在更新...")

    def on_update_install_done(self, ok: bool, message: str, path: str) -> None:
        if self.update_progress_dialog:
            self.update_progress_dialog.setValue(100)
            self.update_progress_dialog.close()
            self.update_progress_dialog = None
        self._log(message)
        package_path = Path(path) if path else None
        if ok and package_path and package_path.exists() and package_path.suffix.lower() == ".dmg":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(package_path)))
        if ok:
            QMessageBox.information(self, "一键更新", message)
        else:
            QMessageBox.warning(self, "一键更新失败", message)
        self.update_worker = None

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
            if self.chk_black_border.isChecked() and self.prompt_black_border_options():
                return
            jobs = self.collect_batch_params()
            if self.prompt_black_border_complex_mode(jobs):
                return
            if self.prompt_complex_mode_for_risky_timelines(jobs):
                return
            if any(
                job["complex_mode"]
                and not job.get("batch_read_io")
                and (not job["manual_io_in"] or not job["manual_io_out"])
                for job in jobs
            ):
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

    def prompt_black_border_options(self) -> bool:
        dialog = BlackBorderOptionsDialog(self)
        if dialog.exec() != QDialog.Accepted:
            self._log("用户取消画面黑边设置。")
            return True
        self.set_black_border_aspect_from_value(dialog.aspect())
        self.save_settings()
        aspect = self.current_black_border_aspect()
        if aspect > 0:
            self._log(f"画面黑边：遮幅比例 {aspect:.2f}，本次将临时复杂渲染最终画面。")
        else:
            self._log("画面黑边：不指定遮幅，使用普通模式几何检测。")
        return False

    def prompt_black_border_complex_mode(self, jobs: list[dict]) -> bool:
        if not any(job.get("black_border_forces_complex") for job in jobs):
            return False
        aspect = self.current_black_border_aspect()
        formula = (
            f"当前遮幅比例为 {aspect:.2f}。\n"
            "插件会按这个比例识别预期遮幅区域，再检查有效画面里是否还有额外露黑。"
        )
        answer = self.ask_enable_complex_mode(
            "画面黑边需要最终画面检测",
            "你勾选了“画面黑边”，并指定了遮幅比例。为了避免把正常遮幅误报成黑边，"
            "本次会临时启用复杂模式，先渲染当前 IO 范围的最终画面。\n\n"
            f"{formula}\n\n"
            "如果当前项目没有加遮幅，请把遮幅预设改成“不指定遮幅”，就可以走普通模式快速检测。\n\n"
            "继续本次遮幅黑边检测吗？",
            "启用复杂模式检测黑边",
        )
        if not answer:
            self._log("用户取消画面黑边最终画面检测。")
            return True
        if any(
            job.get("black_border_forces_complex")
            and not job.get("batch_read_io")
            and (not job.get("manual_io_in") or not job.get("manual_io_out"))
            for job in jobs
        ):
            self.fill_in_out_from_current_timeline_marks()
        for job in jobs:
            if job.get("black_border_forces_complex"):
                job["complex_mode"] = True
                job["render_nested_segments"] = False
                if job.get("batch_read_io"):
                    continue
                if not job.get("manual_io_in"):
                    job["manual_io_in"] = self.io_in.text().strip()
                if not job.get("manual_io_out"):
                    job["manual_io_out"] = self.io_out.text().strip()
        self._log("画面黑边：本次临时启用复杂模式渲染最终画面；复杂模式开关不会被永久勾选。")
        return False

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
        for job in jobs:
            timeline_name = str(job.get("timeline_name") or job.get("name") or "当前时间线")
            risk_message = ""
            risk_kind = ""
            timeline_index = int(job.get("timeline_index", 1) or 1)
            if timeline_index < 1:
                timeline_index = 1
            result = self.bridge.detect_complex_timeline_risk(timeline_index)
            if result and result.get("ok"):
                complex_count = int(result.get("complex_count", 0) or 0)
                nested_count = int(result.get("nested_count", 0) or 0)
                if complex_count > 0:
                    risk_kind = "complex"
                    risk_message = f"检测到 {complex_count} 个源内切点密集的疑似混剪成片。"
                elif nested_count > 0 and not self.chk_nested_render.isChecked() and not job.get("render_nested_segments"):
                    risk_kind = "nested"
                    risk_message = f"检测到 {nested_count} 个复合/Fusion 片段。"
            elif result and result.get("message"):
                self._log("复杂模式风险扫描失败：" + str(result.get("message")))
            if not risk_message:
                continue
            if risk_kind == "complex":
                prompt = (
                    f"时间线“{timeline_name}”{risk_message}\n\n"
                    "普通模式不会渲染最终画面；如果要检查调色、OFX、叠加后的最终像素，请启用复杂模式。\n\n"
                    "是否现在切换到复杂模式？"
                )
                title = "建议启用复杂模式"
            else:
                prompt = (
                    f"时间线“{timeline_name}”{risk_message}\n\n"
                    "普通模式不会进入复合片段/Fusion片段内部；如果要检查这些片段内部的黑帧、夹帧和短空隙，请启用复合/Fusion 片段精查。\n\n"
                    "是否现在启用复合/Fusion 片段精查？"
                )
                title = "建议启用复合/Fusion 片段精查"
            answer = self.ask_enable_complex_mode(
                title,
                prompt,
                "启用复合/Fusion 精查" if risk_kind == "nested" else "启用复杂模式",
            )
            if answer == QMessageBox.Yes or answer is True:
                if risk_kind == "complex":
                    job["complex_mode"] = True
                    job["render_nested_segments"] = False
                    job["detect_content_dup"] = self.chk_content_dup.isChecked()
                    job["detect_corrupt"] = self.chk_corrupt.isChecked()
                    if not job.get("batch_read_io"):
                        self.fill_in_out_from_current_timeline_marks()
                        job["manual_io_in"] = self.io_in.text().strip()
                        job["manual_io_out"] = self.io_out.text().strip()
                    self._log("本次检测临时启用复杂模式；高级选项里的复杂模式不会被永久勾选。")
                else:
                    job["render_nested_segments"] = True
                    self._log("本次检测临时启用复合/Fusion 片段精查；高级选项里的开关不会被永久勾选。")
                continue
            self._log("用户选择继续普通模式；相关片段不会执行渲染深扫。")
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
        try:
            self.run_media_pool_probe(silent=True)
        except Exception:
            pass
        FeedbackDialog(self).exec()

    def open_donation_dialog(self) -> None:
        DonationDialog(self).exec()

    def show_first_run_donation_dialog(self) -> None:
        if self.donation_prompt_seen:
            return
        self.donation_prompt_seen = True
        self.save_settings()
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
        if not result.get("ok"):
            QMessageBox.warning(self, "单声道标记受限", str(result.get("message", "当前 Resolve 版本不支持单声道音频标记。")))

    def clear_mono_audio_markers(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.clear_mono_audio_markers(int(selected.get("index", 1)))
        self.audio_summary.setText(str(result.get("message", "单声道标记已清除。")))
        self.audio_list.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "单声道标记清除完成。")))

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

    def _resolve_audio_bpm_result(
        self,
        timeline_index: int,
        status_text: str,
        prefer_playhead_clip: bool = False,
        require_selected_audio: bool = False,
    ) -> dict:
        self.audio_summary.setText(status_text)
        QApplication.processEvents()
        result = self.bridge.estimate_selected_audio_bpm(
            timeline_index,
            prefer_playhead_clip=prefer_playhead_clip,
            require_selected_audio=require_selected_audio,
        )
        if result.get("needs_selection"):
            candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
            choices: list[str] = []
            selector_by_choice: dict[str, str] = {}
            for idx, clip in enumerate(candidates, 1):
                if not isinstance(clip, dict):
                    continue
                try:
                    source_duration = max(0, int(clip.get("source_end_frame") or 0) - int(clip.get("source_start_frame") or 0))
                except Exception:
                    source_duration = 0
                try:
                    timeline_duration = max(0, int(clip.get("end_frame") or 0) - int(clip.get("start_frame") or 0))
                except Exception:
                    timeline_duration = 0
                duration_hint = f"源{source_duration}帧 / 段{timeline_duration}帧"
                label = (
                    f"A{clip.get('track_index', '?')}  "
                    f"{clip.get('start_frame', '')}->{clip.get('end_frame', '')}  "
                    f"{duration_hint}  "
                    f"{clip.get('name', '未命名音频')}"
                )
                label = f"{idx}. {label}"
                choices.append(label)
                selector_by_choice[label] = str(clip.get("selector", ""))
            if choices:
                choice, ok = QInputDialog.getItem(self, "选择 BPM 音频", "播放头下有多条音频，请选择音乐片段：", choices, 0, False)
                if ok and choice:
                    selector = selector_by_choice.get(choice, "")
                    self.audio_summary.setText(status_text)
                    QApplication.processEvents()
                    result = self.bridge.estimate_selected_audio_bpm(
                        timeline_index,
                        selector,
                        prefer_playhead_clip=prefer_playhead_clip,
                        require_selected_audio=require_selected_audio,
                    )
        return result

    def estimate_selected_audio_bpm(self) -> None:
        selected = self.current_resolve_timeline_data()
        result = self._resolve_audio_bpm_result(
            int(selected.get("index", 1)),
            "正在识别选中音乐 BPM...",
        )
        self.render_audio_bpm(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "BPM 识别完成。")))

    def mark_selected_audio_beats(self) -> None:
        selected = self.current_resolve_timeline_data()
        timeline_index = int(selected.get("index", 1))
        result = self._resolve_audio_bpm_result(
            timeline_index,
            "正在识别 BPM 并生成节拍标记...",
        )
        if result.get("ok") and result.get("bpm"):
            clip = result.get("clip") if isinstance(result.get("clip"), dict) else {}
            try:
                playhead_frame = int(float(clip.get("playhead_frame")))
                clip_start = int(float(clip.get("start_frame") or 0))
                clip_end = int(float(clip.get("end_frame") or 0))
            except Exception:
                playhead_frame = None
                clip_start = 0
                clip_end = 0
            if playhead_frame is None or not (clip_start <= playhead_frame < clip_end):
                result["ok"] = False
                result["message"] = "生成节拍标记前，请选中音乐片段，并把播放头放到你确认的节拍第一帧/重拍锚点上；插件会用这个锚点校准实际 beat 点。"
                QMessageBox.information(self, "需要节拍锚点", result["message"])
                self.render_audio_bpm(result)
                self.side_tabs.setCurrentWidget(self.audio_tab)
                self._log(str(result.get("message", "节拍标记已取消。")))
                return
            anchor_tc = str(clip.get("playhead_timecode") or playhead_frame)
            anchor_delta = playhead_frame - clip_start
            confirm = QMessageBox.question(
                self,
                "确认节拍锚点",
                (
                    "当前播放头会作为节拍锚点：\n"
                    f"{anchor_tc}（距片段起点 {anchor_delta} 帧）\n\n"
                    "请确认播放头已经放在你听到的第一拍/重拍的准确帧上。\n"
                    "继续后，插件会优先生成稳定 BPM 网格；只有在 beat 点足够可信时才使用真实鼓点辅助校准。"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if confirm != QMessageBox.Yes:
                result["message"] = "已取消生成节拍标记。"
                self.render_audio_bpm(result)
                self.side_tabs.setCurrentWidget(self.audio_tab)
                self._log(result["message"])
                return
            marker_scope = str(self.bpm_marker_scope_combo.currentData() or "clip")
            beat_source_start_frame = 0 if result.get("beat_times_relative_to_clip") else int(float(clip.get("source_start_frame") or 0))
            confidence = 0.0
            jitter = 1.0
            try:
                confidence = float(result.get("confidence") or 0)
            except Exception:
                confidence = 0.0
            try:
                jitter = float(result.get("beat_interval_jitter") or 1.0)
            except Exception:
                jitter = 1.0
            beat_times_for_markers = result.get("beat_times_seconds") if isinstance(result.get("beat_times_seconds"), list) else None
            stable_grid_reason = ""
            try:
                source_start_frame = int(float(clip.get("source_start_frame") or 0))
                source_end_frame = int(float(clip.get("source_end_frame") or 0))
            except Exception:
                source_start_frame = 0
                source_end_frame = 0
            source_range_known = source_end_frame > source_start_frame or bool(result.get("beat_times_relative_to_clip"))
            if confidence < 0.55:
                stable_grid_reason = f"Essentia 置信度偏低({confidence:.2f})"
            elif jitter > 0.12:
                stable_grid_reason = f"beat 间隔抖动偏大({jitter:.2%})"
            elif not source_range_known:
                stable_grid_reason = "Resolve 未返回音频切段源入点"
            if stable_grid_reason:
                result["force_grid_markers"] = True
                result["marker_mode_note"] = stable_grid_reason + "，已改用播放头锚点+BPM稳定网格。"
            if not source_range_known:
                beat_times_for_markers = None
            marker_result = self.bridge.add_bpm_grid_markers(
                timeline_index,
                float(result.get("bpm") or 0),
                int(float(clip.get("start_frame") or 0)),
                int(float(clip.get("end_frame") or 0)),
                str(clip.get("name", "未命名音频")),
                float(self.bpm_start_spin.value()),
                float(self.bpm_tightness_spin.value()),
                int(self.bpm_hop_spin.value()),
                marker_scope,
                int(clip.get("track_index") or 0),
                int(clip.get("item_index") or -1),
                str(clip.get("unique_id") or ""),
                0.0,
                beat_source_start_frame,
                beat_times_for_markers,
                int(self.bpm_marker_every_spin.value()),
                1,
                playhead_frame,
                bool(result.get("force_grid_markers")),
            )
            result["marker_result"] = marker_result
            if marker_result.get("ok"):
                result["message"] = str(marker_result.get("message", result.get("message", "节拍标记完成。")))
                if result.get("marker_mode_note"):
                    result["message"] += " " + str(result.get("marker_mode_note"))
            else:
                result["ok"] = False
                result["message"] = str(marker_result.get("message", "节拍标记失败。"))
        self.render_audio_bpm(result)
        self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "节拍标记完成。")))

    def clear_audio_bpm_markers(self) -> None:
        selected = self.current_resolve_timeline_data()
        marker_scope = str(self.bpm_marker_scope_combo.currentData() or "clip")
        result = self.bridge.clear_bpm_markers(int(selected.get("index", 1)), marker_scope)
        self.audio_summary.setText(str(result.get("message", "节拍标记已清除。")))
        self.audio_list.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "节拍标记清除完成。")))

    def clear_current_audio_bpm_markers(self) -> None:
        selected = self.current_resolve_timeline_data()
        result = self.bridge.clear_current_audio_bpm_markers(int(selected.get("index", 1)))
        self.audio_summary.setText(str(result.get("message", "当前音频节拍标记已清除。")))
        self.audio_list.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "当前音频节拍标记清除完成。")))

    def run_media_pool_probe(self, silent: bool = False) -> dict:
        selected = self.timeline_combo.currentData() or {"index": 1}
        if not silent:
            self.audio_summary.setText("正在探测媒体池/API...")
            QApplication.processEvents()
        result = self.bridge.probe_media_pool_api(int(selected.get("index", 1)))
        write_media_pool_probe_cache(result)
        if not silent:
            self.audio_summary.setText(str(result.get("message", "媒体池/API 探针完成。")))
            self.audio_list.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            self.side_tabs.setCurrentWidget(self.audio_tab)
        self._log(str(result.get("message", "媒体池/API 探针完成。")))
        return result

    def refresh_results_from_markers(self) -> None:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.bfd_marker_records(int(selected.get("index", 1)))
        records = result.get("records") if isinstance(result.get("records"), list) else []
        counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
        if counts:
            self._update_result_cards({"counts": counts, "records": records})
        else:
            self.render_result_records(records)
        self.side_tabs.setCurrentWidget(self.detection_tab)
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

    def add_font_file_alias(self, name: str, file_path: str) -> None:
        clean_name = str(name or "").strip()
        clean_path = str(file_path or "").strip()
        if not clean_name or not clean_path:
            return
        bucket = self.font_file_aliases.setdefault(clean_name, [])
        if clean_path not in bucket:
            bucket.append(clean_path)

    def font_candidate_family_part(self, value: str) -> str:
        text = str(value or "").strip()
        if "|||" in text:
            return str(text.split("|||", 1)[0] or "").strip()
        family, _style = self.split_font_style(text)
        return family or text

    def parse_font_candidate(self, value: str) -> tuple[str, str, str]:
        text = str(value or "").strip()
        if "|||" in text:
            parts = text.split("|||", 2)
            while len(parts) < 3:
                parts.append("")
            return parts[0].strip(), parts[1].strip(), parts[2].strip()
        family, style = self.split_font_style(text)
        return family, style, ""

    def ensure_qt_font_candidate_loaded(self, candidate: str) -> list[str]:
        family, _style, path_text = self.parse_font_candidate(candidate)
        paths = self.font_file_path_variants(path_text)
        loaded_families: list[str] = []
        for path in paths:
            if path in self._qt_application_font_paths:
                continue
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id < 0:
                continue
            self._qt_application_font_paths.add(path)
            for loaded_family in QFontDatabase.applicationFontFamilies(font_id):
                loaded = str(loaded_family or "").strip()
                if not loaded:
                    continue
                loaded_families.append(loaded)
                if family and loaded != family:
                    self.add_font_alias(family, [loaded])
                    self.add_font_alias(loaded, [family])
                    self.add_font_file_alias(loaded, path)
                try:
                    self._font_qt_family_set.add(loaded)
                except Exception:
                    pass
        return loaded_families

    def is_corrupt_font_candidate(self, value: str) -> bool:
        family = self.font_candidate_family_part(value)
        if not family:
            return False
        question_count = family.count("?")
        if question_count < 3:
            return False
        meaningful = re.sub(r"[?\s._\\/|-]+", "", family)
        has_cjk = any("\u4e00" <= char <= "\u9fff" for char in meaningful)
        has_alnum = any(char.isalnum() for char in meaningful)
        if not meaningful or (not has_cjk and not has_alnum):
            return True
        return question_count >= max(3, len(family) // 2)

    def clean_font_probe_candidate(self, value: str) -> str:
        text = str(value or "").strip()
        if not text or self.is_corrupt_font_candidate(text):
            return ""
        return text

    def font_file_path_variants(self, file_name_or_path: str) -> list[str]:
        text = str(file_name_or_path or "").strip()
        if not text:
            return []
        candidates: list[str] = []

        def add(path_text: str) -> None:
            path = Path(str(path_text or "")).expanduser()
            try:
                resolved = str(path) if path.exists() else ""
            except Exception:
                resolved = ""
            if resolved and resolved not in candidates:
                candidates.append(resolved)

        add(text)
        basename = Path(text).name
        if basename and basename != text:
            add(basename)
        if basename:
            for root in (
                Path.home() / "Library" / "Fonts",
                Path("/Library/Fonts"),
                Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental"),
            ):
                add(str(root / basename))
        return candidates

    def font_name_variants(self, name: str) -> list[str]:
        clean_name = " ".join(str(name or "").replace("_", " ").split()).strip()
        raw_name = str(name or "").strip()
        variants: list[str] = []

        def add(value: str) -> None:
            text = str(value or "").strip()
            if text and text not in variants:
                variants.append(text)

        add(raw_name)
        add(clean_name)
        compact = re.sub(r"[\s_\-.]+", "", raw_name)
        add(compact)
        if raw_name:
            add(raw_name.replace("-", " "))
            add(raw_name.replace("_", " "))
            add(raw_name.replace(" ", ""))
        return variants

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
        cache = getattr(self, "_font_system_family_cache", None)
        if cache is None:
            cache = {}
            self._font_system_family_cache = cache
        if clean_family in cache:
            return cache[clean_family]
        try:
            family_set = getattr(self, "_font_qt_family_set", None)
            if family_set is None:
                family_set = set(QFontDatabase.families())
                self._font_qt_family_set = family_set
        except Exception:
            family_set = set()
        if clean_family in family_set:
            cache[clean_family] = clean_family
            return clean_family
        for alias in self.font_aliases.get(clean_family, []):
            alias_family, _alias_style = self.split_font_style(alias)
            if alias_family in family_set:
                cache[clean_family] = alias_family
                return alias_family
            if alias in family_set:
                cache[clean_family] = alias
                return alias
        cache[clean_family] = clean_family
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
        if not getattr(self, "_font_delivery_rules_loaded", False):
            self.load_basic_font_delivery_rules()
        cache = getattr(self, "_font_candidates_cache", None)
        if cache is None:
            cache = {}
            self._font_candidates_cache = cache
        if clean_name in cache:
            return list(cache[clean_name])
        candidates: list[str] = []
        family, style = self.split_font_style(clean_name)
        probe_rules = getattr(self, "font_probe_rules", {})

        def candidate_declared_style(value: str) -> str:
            text = str(value or "").strip()
            if "|||" in text:
                parts = text.split("|||")
                return str(parts[1] if len(parts) > 1 else "").strip()
            _family, parsed_style = self.split_font_style(text)
            return parsed_style

        def learned_matches_selected_style(value: str) -> bool:
            if not style:
                return True
            learned_style = candidate_declared_style(value)
            return not learned_style or learned_style == style

        for learned in probe_rules.get(clean_name, []):
            learned = self.clean_font_probe_candidate(learned)
            if learned and learned not in candidates:
                candidates.append(learned)
        for learned in probe_rules.get(family, []):
            learned = self.clean_font_probe_candidate(learned)
            if learned and learned not in candidates and learned_matches_selected_style(learned):
                candidates.append(learned)
        aliases = [
            *self.font_aliases.get(clean_name, []),
            *self.font_aliases.get(family, []),
        ]
        for variant in self.font_name_variants(clean_name) + self.font_name_variants(family):
            aliases.extend(self.font_aliases.get(variant, []))
        deduped_aliases: list[str] = []
        seen_aliases: set[str] = set()
        for alias in aliases:
            clean_alias = str(alias or "").strip()
            if not clean_alias or clean_alias in seen_aliases:
                continue
            seen_aliases.add(clean_alias)
            deduped_aliases.append(clean_alias)
            if len(deduped_aliases) >= 48:
                break
        aliases = deduped_aliases
        selected_style = style
        family_set = getattr(self, "_font_qt_family_set", None)
        if family_set is None:
            try:
                family_set = set(QFontDatabase.families())
            except Exception:
                family_set = set()
            self._font_qt_family_set = family_set
        system_family = self.font_system_family(family)
        clean_is_direct = bool(family and (family in family_set or system_family in family_set))

        def candidate_priority(value: str) -> tuple[int, str]:
            candidate_family, candidate_style, _candidate_path = self.parse_font_candidate(value)
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

        def known_styles_for(source_names: list[str]) -> list[str]:
            styles: list[str] = []
            for source in source_names:
                if not source:
                    continue
                source_family, source_style = self.split_font_style(source)
                for value in (source_style, style, selected_style):
                    if value and value not in styles:
                        styles.append(value)
                for key in {source, source_family, self.font_system_family(source_family)}:
                    for value in self.font_family_styles.get(key, []):
                        if value and value not in styles:
                            styles.append(value)
                for alias in (self.font_aliases.get(source, []) + self.font_aliases.get(source_family, []))[:8]:
                    alias_family, alias_style = self.split_font_style(alias)
                    if alias_style and alias_style not in styles:
                        styles.append(alias_style)
                    for key in {alias, alias_family, self.font_system_family(alias_family)}:
                        for value in self.font_family_styles.get(key, []):
                            if value and value not in styles:
                                styles.append(value)
            for fallback in ("Regular", "常规体"):
                if fallback not in styles:
                    styles.append(fallback)
            return styles

        direct_source_names = [clean_name, family, system_family]
        for source_name in direct_source_names:
            if not source_name:
                continue
            for candidate_style in known_styles_for([source_name]):
                if candidate_style:
                    packed = f"{source_name}|||{candidate_style}"
                    if packed not in candidates and not self.is_corrupt_font_candidate(packed):
                        candidates.append(packed)

        for source_name in [clean_name, family, system_family, *aliases[:24]]:
            candidate_styles = known_styles_for([source_name, *self.font_aliases.get(source_name, [])[:8]])
            for variant in self.font_name_variants(source_name):
                for path in self.font_file_aliases.get(variant, []):
                    for candidate_style in candidate_styles:
                        if candidate_style:
                            packed = f"{variant}|||{candidate_style}|||{path}"
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
            for known_style in known_styles_for([candidate, family, resolved_family]):
                if known_style not in styles:
                    styles.append(known_style)
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
        for alias in sorted_aliases:
            for raw_variant in self.font_name_variants(alias):
                if selected_style:
                    packed = f"{raw_variant}|||{selected_style}"
                    if packed not in candidates:
                        candidates.append(packed)
                if raw_variant and raw_variant not in candidates:
                    candidates.append(raw_variant)
            alias_family, alias_style = self.split_font_style(alias)
            for variant in self.font_name_variants(alias_family or alias):
                if selected_style or alias_style:
                    for candidate_style in known_styles_for([alias, alias_family, variant]):
                        if candidate_style:
                            packed = f"{variant}|||{candidate_style}"
                            if packed not in candidates:
                                candidates.append(packed)
                if variant and variant not in candidates:
                    candidates.append(variant)
        cache[clean_name] = list(candidates)
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
        self._font_candidates_cache = {}
        for item in self.font_probe_rule_items:
            source = str(item.get("source", "")).strip()
            accepted_candidate = self.clean_font_probe_candidate(
                str(item.get("local_accepted_candidate") or item.get("accepted_candidate") or "").strip()
            )
            accepted_plain = self.clean_font_probe_candidate(str(item.get("accepted", "")).strip())
            accepted = accepted_candidate or accepted_plain
            registered_file = str(item.get("registered_font_file") or "").strip()
            registered_paths = self.font_file_path_variants(registered_file)
            registered_name = self.clean_font_probe_candidate(str(item.get("registered_font_name") or "").strip())
            if source and accepted:
                for key in self.font_rule_source_keys(source):
                    bucket = self.font_probe_rules.setdefault(key, [])
                    if accepted not in bucket:
                        bucket.append(accepted)
                    family = self.clean_font_probe_candidate(self.font_candidate_family_part(accepted))
                    _unused_family, style = self.split_font_style(accepted)
                    if "|||" in str(accepted or ""):
                        parts = str(accepted).split("|||")
                        style = str(parts[1] if len(parts) > 1 else style).strip()
                    if not style:
                        style = "Regular"
                    for path in registered_paths:
                        for candidate_family in (family, registered_name, accepted_plain, source):
                            candidate_family = self.clean_font_probe_candidate(candidate_family)
                            if not candidate_family:
                                continue
                            packed = f"{candidate_family}|||{style}|||{path}"
                            if packed not in bucket:
                                bucket.append(packed)
        self._font_delivery_rules_loaded = False

    def add_font_probe_candidate_rule(self, source: str, candidate: str) -> None:
        clean_source = str(source or "").strip()
        clean_candidate = self.clean_font_probe_candidate(candidate)
        if not clean_source or not clean_candidate:
            return
        for key in self.font_rule_source_keys(clean_source):
            bucket = self.font_probe_rules.setdefault(key, [])
            if clean_candidate not in bucket:
                bucket.append(clean_candidate)

    def load_basic_font_delivery_rules(self) -> None:
        if self._font_delivery_rules_loaded:
            return
        self._font_delivery_rules_loaded = True
        path = basic_font_rules_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            return
        rules = data.get("rules", []) if isinstance(data, dict) else []
        if not isinstance(rules, list):
            return
        self.font_delivery_rule_count = len(rules)
        for item in rules:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "").strip()
            accepted = self.clean_font_probe_candidate(str(item.get("accepted") or "").strip())
            accepted_candidate = self.clean_font_probe_candidate(str(item.get("accepted_candidate") or "").strip())
            style = str(item.get("style") or "").strip()
            registered_file = str(item.get("registered_font_file") or "").strip()
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            if not source:
                continue
            source_keys = [source]
            for group in ("families", "full_names", "postscript_names"):
                values = metadata.get(group) if isinstance(metadata, dict) else None
                if isinstance(values, list):
                    for value in values:
                        text = str(value or "").strip()
                        if text and text not in source_keys:
                            source_keys.append(text)
            candidate_values = []
            for value in (accepted_candidate, accepted):
                if value and value not in candidate_values:
                    candidate_values.append(value)
            if accepted and style:
                packed = f"{accepted}|||{style}"
                if packed not in candidate_values:
                    candidate_values.append(packed)
            for path_variant in self.font_file_path_variants(registered_file):
                for value in (accepted, accepted_candidate.split("|||", 1)[0] if accepted_candidate else ""):
                    value = self.clean_font_probe_candidate(value)
                    if not value:
                        continue
                    packed = f"{value}|||{style or 'Regular'}|||{path_variant}"
                    if packed not in candidate_values:
                        candidate_values.append(packed)
            for key in source_keys:
                for candidate in candidate_values:
                    self.add_font_probe_candidate_rule(key, candidate)

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
        accepted_candidate_raw = str(result.get("accepted_candidate") or "").strip()
        source = str(source_name or "").strip()
        if not source:
            return
        ok = bool(result.get("ok"))
        if ok and accepted == source and not candidates:
            return

        def scrub_candidate(value: str) -> str:
            text = str(value or "").strip()
            if self.is_corrupt_font_candidate(text):
                return ""
            parts = text.split("|||")
            if len(parts) >= 3:
                parts[2] = Path(parts[2]).name
                return "|||".join(parts[:3])
            return text

        def scrub_trace_item(value: dict) -> dict:
            clean = dict(value)
            if clean.get("path"):
                clean["path"] = Path(str(clean.get("path"))).name
            if clean.get("candidate"):
                clean["candidate"] = scrub_candidate(str(clean.get("candidate")))
            return clean

        clean_candidates = []
        for candidate in candidates:
            text = scrub_candidate(str(candidate or ""))
            if text and text not in clean_candidates:
                clean_candidates.append(text)
        local_accepted_candidate = self.clean_font_probe_candidate(accepted_candidate_raw)
        export_accepted_candidate = scrub_candidate(accepted_candidate_raw)
        if accepted and not local_accepted_candidate:
            accepted_family, accepted_style = self.split_font_style(accepted)
            if accepted_family and accepted_style:
                local_accepted_candidate = f"{accepted_family}|||{accepted_style}"
                export_accepted_candidate = local_accepted_candidate
        source_keys = self.font_rule_source_keys(source)
        raw_candidate_trace = result.get("candidate_trace") if isinstance(result.get("candidate_trace"), list) else []
        candidate_trace = [scrub_trace_item(item) for item in raw_candidate_trace if isinstance(item, dict)]
        registered_font_file = Path(str(result.get("registered_font_path") or "")).name
        proof = {
            "direct_before": bool(result.get("direct_before")) if "direct_before" in result else None,
            "textplus_ok": ok,
            "textplus_font": str(result.get("font") or ""),
            "textplus_style": str(result.get("style") or ""),
            "accepted_candidate": export_accepted_candidate,
            "candidate_attempts": int(result.get("candidate_attempts") or 0),
            "registered": bool(result.get("registered_font_path") or result.get("registered_font_name")),
            "visual_ok": bool(result.get("visual_ok")) if "visual_ok" in result else False,
            "visible": bool(result.get("visible")) if "visible" in result else False,
            "tofu_suspect": bool(result.get("tofu_suspect")) if "tofu_suspect" in result else False,
            "error_frame_suspect": bool(result.get("error_frame_suspect")) if "error_frame_suspect" in result else False,
        }
        report_item = {
            "ok": ok,
            "source": source,
            "accepted": accepted,
            "accepted_candidate": export_accepted_candidate,
            "local_accepted_candidate": local_accepted_candidate,
            "registered_font_file": registered_font_file,
            "registered_font_name": str(result.get("registered_font_name") or ""),
            "candidate_attempts": int(result.get("candidate_attempts") or 0),
            "candidate_trace": candidate_trace[:24],
            "proof": proof,
            "probe_warning": str(result.get("probe_warning") or ""),
            "message": str(result.get("message") or "")[:500],
            "resolve_version": self.resolve_version_text,
            "platform": analytics_platform_label(),
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        write_font_probe_report_cache(report_item)
        rejected = []
        if not ok:
            for candidate in clean_candidates:
                if candidate != accepted and candidate not in rejected:
                    rejected.append(candidate)
        duplicate = any(
            str(item.get("source", "")) == source
            and str(item.get("accepted", "")) == accepted
            and str(item.get("local_accepted_candidate") or item.get("accepted_candidate") or "") in {local_accepted_candidate, export_accepted_candidate}
            and bool(item.get("ok", True)) == ok
            for item in self.font_probe_rule_items
        )
        if duplicate:
            return
        item = {
            "ok": ok,
            "source": source,
            "accepted": accepted,
            "candidates": clean_candidates[:16],
            "source_keys": source_keys[:12],
            "rejected": rejected[:16],
            "actual_font": str(result.get("font") or ""),
            "accepted_candidate": export_accepted_candidate,
            "local_accepted_candidate": local_accepted_candidate,
            "registered_font_file": registered_font_file,
            "registered_font_name": str(result.get("registered_font_name") or ""),
            "candidate_attempts": int(result.get("candidate_attempts") or 0),
            "candidate_trace": candidate_trace[:24],
            "proof": proof,
            "probe_warning": str(result.get("probe_warning") or ""),
            "message": str(result.get("message") or "")[:300],
            "resolve_version": self.resolve_version_text,
            "platform": analytics_platform_label(),
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        self.font_probe_rule_items.append(item)
        if accepted:
            learned_value = local_accepted_candidate or accepted
            for key in source_keys:
                self.font_probe_rules.setdefault(key, [])
                if learned_value not in self.font_probe_rules[key]:
                    self.font_probe_rules[key].insert(0, learned_value)
        self.save_font_probe_rules()
        self.track_usage_event("font_rule_learned" if ok else "font_rule_failed", {"rule": item})
        if self.font_inventory_consent and not self._font_inventory_sent_this_session:
            self.track_usage_event("font_inventory", self.build_font_rules_export_payload(include_inventory=True))
            self._font_inventory_sent_this_session = True

    def font_rule_source_keys(self, source_name: str) -> list[str]:
        source = str(source_name or "").strip()
        if not source:
            return []
        family, style = self.split_font_style(source)
        keys: list[str] = []

        def add(value: str) -> None:
            text = str(value or "").strip()
            if text and text not in keys:
                keys.append(text)

        add(source)
        if family and not style:
            add(family)
        if family and style:
            add(f"{family} {style}")
            system_family = self.font_system_family(family)
            add(f"{system_family} {style}")
        for base in (source, family):
            for alias in self.font_aliases.get(base, []):
                alias_family, alias_style = self.split_font_style(alias)
                if not style:
                    add(alias)
                    add(alias_family)
                elif alias_style == style:
                    add(alias)
                if alias_family and (alias_style or style):
                    add(f"{alias_family} {alias_style or style}")
                system_family = self.font_system_family(alias_family)
                if system_family and not style:
                    add(system_family)
                if system_family and (alias_style or style):
                    add(f"{system_family} {alias_style or style}")
        return keys

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
            "platform": analytics_platform_label(),
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
        self.font_file_aliases = {}
        self.font_family_styles = {}
        self.font_postscript_styles = {}
        self._font_qt_family_set = set()
        self._font_system_family_cache = {}
        self._font_candidates_cache = {}
        mapped_postscript_fonts: set[str] = set()
        try:
            self._font_qt_family_set = {str(name) for name in QFontDatabase.families()}
            fonts.update(self._font_qt_family_set)
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
        try:
            fc_output = subprocess.check_output(
                ["fc-list", "--format", "%{family}\t%{style}\t%{fullname}\t%{postscriptname}\t%{file}\n"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
        except Exception:
            fc_output = ""
        for line in fc_output.splitlines():
            parts = line.split("\t")
            while len(parts) < 5:
                parts.append("")
            families, styles, fullnames, postscript_names, file_path = parts[:5]
            family_names = [item.strip() for item in families.split(",") if item.strip()]
            style_names = [item.strip() for item in styles.split(",") if item.strip()]
            fullname_items = [item.strip() for item in fullnames.split(",") if item.strip()]
            postscript_items = [item.strip() for item in postscript_names.split(",") if item.strip()]
            file_stem = Path(file_path).stem.strip() if file_path else ""
            all_names: list[str] = []
            for value in [*family_names, *fullname_items, *postscript_items, file_stem]:
                for variant in self.font_name_variants(value):
                    if variant and variant not in all_names:
                        all_names.append(variant)
            for name in all_names:
                self.add_font_file_alias(name, file_path)
            for family_name in family_names:
                fonts.add(family_name)
                self.add_font_file_alias(family_name, file_path)
                for style_name in style_names:
                    self.font_family_styles.setdefault(family_name, [])
                    if style_name not in self.font_family_styles[family_name]:
                        self.font_family_styles[family_name].append(style_name)
                    self.font_postscript_styles.setdefault(f"{family_name} {style_name}", (family_name, style_name))
                self.add_font_alias(family_name, all_names)
                for alias_name in all_names:
                    self.add_font_alias(alias_name, [family_name, *all_names])
                    if style_names:
                        self.font_family_styles.setdefault(alias_name, [])
                        for style_name in style_names:
                            if style_name not in self.font_family_styles[alias_name]:
                                self.font_family_styles[alias_name].append(style_name)
            for postscript_name in postscript_items:
                if family_names and style_names:
                    self.font_postscript_styles.setdefault(postscript_name, (family_names[0], style_names[0]))
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
        self._font_delivery_rules_loaded = False

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
        self.schedule_font_fusion_preview_check(font_name)

    def on_font_selection_changed(self) -> None:
        family = self.selected_font_family()
        self.refresh_font_style_combo(family)
        font_name = self.selected_font_name()
        if font_name:
            self.font_target.setText(font_name)
        self.update_font_preview(font_name)
        self.schedule_font_fusion_preview_check(font_name)

    @staticmethod
    def font_fusion_cache_key(font_name: str) -> str:
        return " ".join(str(font_name or "").split()).casefold()

    def schedule_font_fusion_preview_check(self, font_name: str) -> None:
        clean_name = str(font_name or "").strip()
        if not clean_name:
            return
        key = self.font_fusion_cache_key(clean_name)
        if key in self.font_fusion_availability_cache:
            return
        QTimer.singleShot(80, lambda name=clean_name: self.refresh_font_fusion_preview_status(name))

    def refresh_font_fusion_preview_status(self, font_name: str) -> None:
        clean_name = str(font_name or "").strip()
        if not clean_name:
            return
        if self.font_fusion_cache_key(self.selected_font_name()) != self.font_fusion_cache_key(clean_name):
            return
        key = self.font_fusion_cache_key(clean_name)
        if key in self.font_fusion_availability_cache:
            return
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.check_font_available(int(selected.get("index", 1)), clean_name, self.font_candidates(clean_name))
        self.font_fusion_availability_cache[key] = result
        self.learn_font_probe_rule(clean_name, self.font_candidates(clean_name), result)
        if self.font_fusion_cache_key(self.selected_font_name()) == key:
            self.update_font_preview(clean_name)

    def selected_font_preview_text(self) -> str:
        record = self.selected_font_record()
        if (
            record
            and str(record.get("kind", "")).lower() in {"text+", "text+组"}
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
                family, style, _path_text = self.parse_font_candidate(candidate)
                loaded_families = self.ensure_qt_font_candidate_loaded(candidate)
                wanted_keys.update(loaded.casefold() for loaded in loaded_families if loaded)
                resolved_family = self.font_system_family(family)
                if loaded_families and resolved_family not in set(QFontDatabase.families()):
                    resolved_family = loaded_families[0]
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
            fusion_status = self.font_fusion_availability_cache.get(self.font_fusion_cache_key(name))
            if fusion_status and not fusion_status.get("ok"):
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(127, 29, 29, 190))
                painter.drawRect(pixmap.rect())
                painter.setPen(QColor("#ef4444"))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(3, 3, width - 6, height - 6), 8, 8)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(220, 38, 38, 235))
                banner = QRectF(10, 8, width - 20, 42)
                painter.drawRoundedRect(banner, 6, 6)
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont(install_cjk_font(), 13, QFont.Bold))
                message = str(fusion_status.get("message") or "当前 Fusion 不可用：该字体未被 Resolve/Fusion 识别。")
                message = painter.fontMetrics().elidedText(message, Qt.ElideRight, max(120, width - 42))
                painter.drawText(banner.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, message)
                painter.setFont(QFont(install_cjk_font(), 10, QFont.Bold))
                painter.setPen(QColor("#fecaca"))
                hint = "本地预览能显示不代表 Resolve 可用；请换 Fusion 字体下拉列表中可用的字体。"
                hint = painter.fontMetrics().elidedText(hint, Qt.ElideRight, max(120, width - 42))
                painter.drawText(QRectF(16, height - 32, width - 32, 22), Qt.AlignVCenter | Qt.AlignLeft, hint)
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
        if len(getattr(self, "font_records", []) or []) >= 300:
            return
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
        selected = self.timeline_combo.currentData() or {"index": 1}
        if self.font_scan_worker is not None and self.font_scan_worker.isRunning():
            self.font_status.setText("正在扫描字体层，请稍候...")
            return
        if not silent:
            self.side_tabs.setCurrentWidget(self.font_tab)
        self.font_status.setText("正在后台扫描当前时间线文字层...")
        self.font_scan_worker = FontLayerScanWorker(int(selected.get("index", 1)), silent, selected_keys)
        self.font_scan_worker.done.connect(self.on_font_scan_done)
        self.font_scan_worker.finished.connect(self.font_scan_worker.deleteLater)
        self.font_scan_worker.start()

    def on_font_scan_done(self, result: dict, silent: bool, selected_keys_obj: object) -> None:
        try:
            selected_keys = set(selected_keys_obj or set())
        except Exception:
            selected_keys = set()
        self.render_font_scan_result(result, bool(silent), selected_keys)
        self.font_scan_worker = None

    def render_font_scan_result(self, result: dict, silent: bool, selected_keys: set) -> None:
        self.font_records = result.get("items") if isinstance(result.get("items"), list) else []
        self.font_table.setRowCount(0)
        unsupported_bg, unsupported_fg = self.table_muted_colors()
        rows_to_restore: list[int] = []
        for idx, record in enumerate(self.font_records, 1):
            row = self.font_table.rowCount()
            self.font_table.insertRow(row)
            kind = str(record.get("kind", ""))
            if kind.lower() == "srt":
                kind_label = "SRT轨道"
            elif kind.lower() == "text+组":
                kind_label = "字幕Text+组"
            elif kind.lower() == "text+":
                kind_label = "Text+"
            elif kind.lower() == "text":
                kind_label = "Text"
            else:
                kind_label = kind
            supported = bool(record.get("supported"))
            reason = str(record.get("reason", "")).strip()
            status = "组可写" if bool(record.get("group")) and supported else ("Text+可写" if supported else "不可替换")
            raw_font_value = str(record.get("font", "")).strip()
            font_value = self.font_display_name(raw_font_value) if supported else "--"
            text_value_full = str(record.get("text", "")).replace("\n", " ").strip()
            if reason and not supported:
                text_value_full = f"{text_value_full} | {reason}" if text_value_full else reason
            text_value = self.compact_cell_text(text_value_full)
            values = [
                f"{idx:03d}",
                str(record.get("timecode", "")),
                text_value,
                f"{kind_label} · {str(record.get('track_type', '')).upper()}{record.get('track_index', '')}",
                font_value,
                status,
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, idx - 1)
                if column == 4 and raw_font_value:
                    cell.setToolTip(self.font_display_name(raw_font_value))
                if column == 2:
                    cell.setToolTip(text_value_full)
                elif reason:
                    cell.setToolTip(reason)
                if not supported:
                    cell.setBackground(unsupported_bg)
                    cell.setForeground(unsupported_fg)
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

    def check_target_font_available_in_fusion(self, font_name: str, candidates: list[str]) -> dict:
        selected = self.timeline_combo.currentData() or {"index": 1}
        result = self.bridge.check_font_available(int(selected.get("index", 1)), font_name, candidates)
        if not result.get("ok"):
            message = str(result.get("message") or "当前 Fusion 不可用：所选字体未被 Resolve/Fusion 识别。")
            self.font_status.setText(message)
            self._log(message)
        return result

    def apply_font_to_selected_layer(self, check_fusion_first: bool = False) -> None:
        font_name = self.font_target.text().strip() or self.selected_font_name()
        if not font_name:
            self.font_status.setText("请选择字体。")
            return
        candidates = self.font_candidates(font_name)
        if check_fusion_first:
            availability = self.check_target_font_available_in_fusion(font_name, candidates)
            if not availability.get("ok"):
                self.learn_font_probe_rule(font_name, candidates, availability)
                return
        records = self.selected_font_records()
        if not records:
            supported_records = [record for record in self.font_records if record.get("supported")]
            if len(supported_records) == 1:
                records = supported_records
            else:
                self.font_status.setText("字体可用，请选择要替换的字体层。")
                return
        ok_count = 0
        fail_count = 0
        skipped = 0
        last_message = ""
        selected_rows = sorted({index.row() for index in self.font_table.selectionModel().selectedRows()})
        row_by_record_id = {id(record): row for record, row in zip(records, selected_rows)}
        for record in records:
            QApplication.processEvents()
            if not record.get("supported"):
                skipped += 1
                continue
            result = self.bridge.replace_font_item(record, font_name, candidates)
            last_message = str(result.get("message", ""))
            if result.get("ok") and result.get("probe_warning"):
                last_message = f"{last_message} {result.get('probe_warning')}"
            self.learn_font_probe_rule(font_name, candidates, result)
            if result.get("ok"):
                ok_count += 1
                actual_font = str(result.get("accepted_font") or result.get("font") or font_name)
                record["font"] = actual_font
                row = row_by_record_id.get(id(record), self.font_table.currentRow())
                if row >= 0 and self.font_table.item(row, 4):
                    self.font_table.item(row, 4).setText(self.font_display_name(actual_font))
                    self.font_table.item(row, 4).setToolTip(self.font_display_name(actual_font))
            else:
                fail_count += 1
        if len(records) == 1 and (ok_count or fail_count) and last_message:
            self.font_status.setText(last_message)
        else:
            self.font_status.setText(f"替换完成：成功 {ok_count} 个，失败 {fail_count} 个，跳过 {skipped} 个。")
        self._log(self.font_status.text())

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
            self.learn_font_probe_rule(font_name, candidates, result)
            if result.get("ok"):
                ok_count += 1
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
        if str(record.get("kind", "")).lower() not in {"text+", "text+组"} or not record.get("supported"):
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
            if hasattr(self, "font_style_library_list"):
                self.font_style_library_list.clearSelection()
            self.update_font_style_preview()
        self.font_status.setText(str(result.get("message", "Text+ 样式复制失败。")))
        self._log(self.font_status.text())

    def copy_selected_textplus_position(self) -> None:
        record = self._selected_textplus_style_record()
        if not record:
            self._log(self.font_status.text())
            return
        result = self.bridge.copy_textplus_position(record)
        if result.get("ok") and isinstance(result.get("style"), dict):
            self.font_style_clipboard = result.get("style")
            if hasattr(self, "font_style_library_list"):
                self.font_style_library_list.clearSelection()
            self.update_font_style_preview()
        self.font_status.setText(str(result.get("message", "Text+ 位置复制失败。")))
        self._log(self.font_status.text())

    def copy_selected_textplus_font_only(self) -> None:
        record = self._selected_textplus_style_record()
        if not record:
            self._log(self.font_status.text())
            return
        family = str(record.get("font_family") or "").strip()
        style = str(record.get("font_style") or "").strip()
        if not family:
            family, guessed_style = self.split_font_style(str(record.get("font") or ""))
            style = style or guessed_style
        if not family:
            self.font_status.setText("未读取到当前 Text+ 的字体。")
            self._log(self.font_status.text())
            return
        self.font_style_clipboard = {"Font": family}
        if style:
            self.font_style_clipboard["Style"] = style
        if hasattr(self, "font_style_library_list"):
            self.font_style_library_list.clearSelection()
        self.update_font_style_preview()
        label = f"{family} {style}".strip()
        self.font_status.setText(f"已只复制字体：{self.font_display_name(label)}。应用样式时只会改 Font/Style。")
        self._log(self.font_status.text())

    def apply_copied_textplus_style_to_selected(self) -> None:
        worker = getattr(self, "_font_apply_worker", None)
        if worker is not None and worker.isRunning():
            self.font_status.setText("Text+ 样式正在应用中，请等当前进度完成。")
            return
        if not self.font_style_clipboard:
            self.font_status.setText("请先选中一个做好的 Text+，点击“复制样式”。")
            return
        records = self.selected_font_records()
        if not records:
            self.font_status.setText("请选择一个或多个 Text+ 字体层。")
            return
        supported_records = [
            record for record in records
            if str(record.get("kind", "")).lower() in {"text+", "text+组"} and record.get("supported")
        ]
        skipped = len(records) - len(supported_records)
        if not supported_records:
            self.font_status.setText(f"没有可应用样式的 Text+ 字体层，跳过 {skipped} 个。")
            return
        estimated_items = sum(max(1, int(record.get("member_count", 1) or 1)) for record in supported_records)
        has_large_group = any(int(record.get("member_count", 1) or 1) >= 20 for record in supported_records)
        use_animated_progress = estimated_items >= 20 or has_large_group
        if use_animated_progress:
            self.apply_textplus_style_with_progress(supported_records, skipped, estimated_items)
            return

        ok_count = 0
        fail_count = 0
        processed = 0
        for record in supported_records:
            QApplication.processEvents()
            processed += 1
            result = self.bridge.apply_textplus_style(record, self.font_style_clipboard)
            if result.get("ok"):
                ok_count += 1
            else:
                fail_count += 1
        self.font_status.setText(f"样式应用完成：成功 {ok_count} 个，失败 {fail_count} 个，跳过 {skipped} 个。")
        self._log(self.font_status.text())
        if ok_count:
            self.scan_font_layers()

    def apply_textplus_style_with_progress(self, records: list[dict], skipped: int, estimated_items: int) -> None:
        estimated_seconds = max(4.0, min(120.0, estimated_items * 0.055 + len(records) * 0.45))
        progress = QProgressDialog(self)
        progress.setWindowTitle("正在应用 Text+ 样式")
        progress.setLabelText(f"正在应用到约 {estimated_items} 条 Text+，预计 {int(estimated_seconds)} 秒...")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 100)
        progress.setValue(1)
        progress.show()

        state = {"started_at": time.monotonic(), "floor": 1, "label": progress.labelText()}
        timer = QTimer(self)
        timer.setInterval(120)

        def update_fake_progress() -> None:
            elapsed = max(0.01, time.monotonic() - state["started_at"])
            remaining = max(1, int(round(estimated_seconds - elapsed)))
            curve = min(1.0, elapsed / max(1.0, estimated_seconds))
            target = min(92, int(2 + curve * 88))
            value = max(progress.value(), state["floor"], target)
            progress.setValue(min(92, value))
            progress.setLabelText(f"{state['label']}，预计剩余 {remaining} 秒。")

        def on_worker_progress(processed: int, total: int, member_count: int, message: str) -> None:
            completed_before_current = max(0, processed - 1)
            state["floor"] = min(70, max(state["floor"], int((completed_before_current / max(1, total)) * 70)))
            state["label"] = f"{message}：{processed}/{total} 组，本组约 {member_count} 条"
            update_fake_progress()

        def on_worker_done(result: dict) -> None:
            timer.stop()
            progress.setValue(96)
            progress.setLabelText("样式已应用，正在刷新时间线文字层...")
            QApplication.processEvents()
            ok_count = int(result.get("ok_count", 0) or 0)
            fail_count = int(result.get("fail_count", 0) or 0)
            total_skipped = skipped + int(result.get("skipped", 0) or 0)
            self.font_status.setText(f"样式应用完成：成功 {ok_count} 个，失败 {fail_count} 个，跳过 {total_skipped} 个。")
            self._log(self.font_status.text())
            if ok_count:
                self.scan_font_layers()
            progress.setValue(100)
            progress.close()
            self._font_apply_worker = None
            self._font_apply_progress = None
            self._font_apply_timer = None

        worker = TextPlusStyleApplyWorker(self.bridge, records, self.font_style_clipboard)
        worker.progress.connect(on_worker_progress)
        worker.done.connect(on_worker_done)
        worker.finished.connect(worker.deleteLater)
        self._font_apply_worker = worker
        self._font_apply_progress = progress
        self._font_apply_timer = timer
        timer.timeout.connect(update_fake_progress)
        timer.start()
        worker.start()

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
            if str(record.get("kind", "")).lower() not in {"text+", "text+组"} or not record.get("supported"):
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
        write_markers = bool(getattr(self, "srt2text_marker_checkbox", None) and self.srt2text_marker_checkbox.isChecked())
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
        result = self.bridge.convert_srt_to_textplus(int(selected.get("index", 1)), template_uid, write_markers)
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
            kind_text = str(template.get("kind", ""))
            fps_text = str(template.get("fps", "") or "")
            label = name
            if kind_text:
                label += f"  ·  {kind_text}"
            if type_text:
                label += f"  ·  {type_text}"
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
        match_bg, match_fg = self.table_match_colors()
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
                    cell.setBackground(match_bg)
                    cell.setForeground(match_fg)
                self.text_table.setItem(row_index, column, cell)
        self._updating_text_table = False
        self.text_table.resizeRowsToContents()
        base_message = str(result.get("message", f"找到 {len(self.text_records)} 条文字/字幕素材。"))
        if not self.text_records:
            scan_types = " / ".join(self.selected_text_scan_type_labels())
            base_message = f"{base_message}  未找到时可切换类型后点“重新检测”。当前类型：{scan_types}。"
        if query:
            total = len(self.text_match_indices)
            base_message += f"  匹配 {total} 处。"
            self._set_match_button(0, total)
        else:
            self.text_next_match_btn.setText("下一个匹配")
        self.text_status.setText(base_message)
        self.text_initial_panel.show()
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

    def selected_text_scan_type_labels(self) -> list[str]:
        labels: list[str] = []
        if self.text_scan_srt.isChecked():
            labels.append("SRT字幕")
        if self.text_scan_text.isChecked():
            labels.append("TXT文本")
        if self.text_scan_textplus.isChecked():
            labels.append("Text+")
        return labels or ["SRT"]

    def update_text_scan_type_hint(self, *_args) -> None:
        text = "当前扫描：" + " / ".join(self.selected_text_scan_type_labels())
        if hasattr(self, "text_scan_type_hint"):
            self.text_scan_type_hint.setText(text)
        if hasattr(self, "text_search_scan_type_hint"):
            self.text_search_scan_type_hint.setText(text)

    def filter_text_table_matches(self) -> None:
        if not self.text_records:
            self.scan_text_layers()
            return
        query = self.text_search.text().strip()
        self.text_highlight_delegate.set_query(query)
        self.text_match_indices = []
        self.text_match_cursor = -1
        for row in range(self.text_table.rowCount()):
            first_cell = self.text_table.item(row, 0)
            record_index = int(first_cell.data(Qt.UserRole)) if first_cell else row
            item = self.text_records[record_index] if 0 <= record_index < len(self.text_records) else {}
            text = str(item.get("text", ""))
            haystack = (text + " " + str(item.get("name", ""))).lower()
            is_match = bool(query and query.lower() in haystack)
            self.text_table.setRowHidden(row, bool(query) and not is_match)
            if is_match:
                self.text_match_indices.append(row)
        if query:
            total = len(self.text_match_indices)
            self._set_match_button(0, total)
            self.text_status.setText(f"当前列表匹配 {total} 处。")
        else:
            self._set_match_button(0, 0)
            self.text_status.setText(f"当前列表共 {len(self.text_records)} 条。")
        self.text_table.viewport().update()

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
        restored_delete = False
        for change in reversed(changes):
            QApplication.processEvents()
            old_text = str(change.get("old_text", ""))
            action = str(change.get("action", "replace"))
            item = copy.deepcopy(change.get("item") or {})
            if action != "delete":
                try:
                    record_index = int(change.get("record_index"))
                except Exception:
                    record_index = -1
                if 0 <= record_index < len(self.text_records):
                    item = copy.deepcopy(self.text_records[record_index])
            if not item:
                fail_count += 1
                continue
            if action == "delete":
                if str(item.get("track_type", "")) != "subtitle":
                    result = self.native_resolve_undo_deleted_text_item()
                    if not result.get("ok"):
                        result = {
                            "ok": False,
                            "message": str(result.get("message", "原生撤回触发失败。")) + " 请切到达芬奇后手动按 Cmd+Z 撤回删除。",
                        }
                else:
                    result = self.bridge.restore_deleted_text_item(item)
                restored_delete = bool(result.get("ok")) or restored_delete
            else:
                result = self.bridge.replace_text_item(item, old_text)
            if result.get("ok"):
                ok_count += 1
                if action != "delete":
                    self.restore_text_record_row_from_undo(change, old_text)
            else:
                fail_count += 1
        self.text_undo_btn.setEnabled(bool(self.text_undo_stack))
        if restored_delete:
            self.scan_text_layers()
        self.text_status.setText(f"撤回完成：成功 {ok_count} 条，失败 {fail_count} 条。")
        self._log(self.text_status.text())

    def native_resolve_undo_deleted_text_item(self) -> dict:
        if platform.system() != "Darwin":
            return {"ok": False, "message": "当前系统不支持原生快捷键撤回。"}
        script = '''
tell application "DaVinci Resolve" to activate
delay 0.12
tell application "System Events"
    keystroke "z" using command down
end tell
'''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception as exc:
            return {"ok": False, "message": f"达芬奇原生撤回触发失败：{exc}"}
        if result.returncode == 0:
            return {"ok": True, "message": "已调用 DaVinci Resolve 原生撤回。"}
        message = (result.stderr or result.stdout or "").strip()
        return {"ok": False, "message": f"达芬奇原生撤回未成功：{message}"}

    def delete_selected_text_item(self) -> None:
        item = self.selected_text_item_record()
        if not item:
            return
        track_type = str(item.get("track_type", ""))
        if track_type == "subtitle":
            title = "删除字幕"
            question = "确认删除选中的 SRT 字幕吗？删除后可用本面板撤回。"
        else:
            title = "删除 Text+"
            question = "确认删除选中的 Text+ 吗？撤回时会优先调用 DaVinci Resolve 原生撤回；失败时再用插件快照兜底。"
        if QMessageBox.question(self, title, question) != QMessageBox.Yes:
            return
        result = self.bridge.delete_text_item(item)
        self.text_status.setText(str(result.get("message", "")))
        self._log(self.text_status.text())
        if result.get("ok"):
            undo_item = copy.deepcopy(item)
            if isinstance(result.get("restore_style"), dict):
                undo_item["restore_style"] = result.get("restore_style")
            self.push_text_undo([
                self.make_text_undo_change(
                    undo_item,
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
        if result.get("ok") is False:
            self.audio_summary.setText(message)
        else:
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
                    f"{'  片段中点标记' if clip.get('audio_marker_scope') == 'clip' else ''}"
                    f"{'  时间线中点兜底标记' if clip.get('audio_marker_scope') == 'timeline' else ''}"
                )
        if not lines:
            lines.append(message)
            lines.append("")
            fcpxml = summary.get("fcpxml_audio_index") if isinstance(summary.get("fcpxml_audio_index"), dict) else {}
            if fcpxml:
                lines.append(f"FCPXML 兜底：{fcpxml.get('message', '未启用')}，素材 {fcpxml.get('asset_count', 0)} 个。")
            lines.append("识别依据：音轨格式、源音频声道映射、片段/素材属性、FCPXML 素材声道，以及 ffprobe 源文件声道。")
            lines.append("如果只是把已切开的某一小段在达芬奇属性里单独改成单声道，而 Resolve/FCPXML 都不输出这个片段级改动，低版本脚本无法可靠读取。")
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

    def render_audio_bpm(self, result: dict) -> None:
        clip = result.get("clip") if isinstance(result.get("clip"), dict) else {}
        message = str(result.get("message", "BPM 识别完成。"))
        bpm = result.get("bpm", "")
        confidence = result.get("confidence", "")
        source_mode = str(result.get("source_mode", "selected"))
        source_label = "选中音频" if source_mode == "selected" else "播放头所在音频"
        if result.get("ok") and bpm:
            confidence_text = f" / 置信度 {confidence}" if confidence != "" else ""
            self.audio_summary.setText(f"{message}  {source_label} / {bpm} BPM{confidence_text}")
        else:
            self.audio_summary.setText(message)
        lines = [
            "音乐 BPM 识别",
            message,
            "",
            f"来源：{source_label}",
            f"片段：{clip.get('name', '未命名音频')}",
        ]
        if result.get("needs_selection"):
            candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
            lines.append("")
            lines.append("播放头下的音频候选")
            for idx, candidate in enumerate(candidates, 1):
                if isinstance(candidate, dict):
                    lines.append(
                        f"  {idx}. A{candidate.get('track_index', '?')}  "
                        f"{candidate.get('start_frame', '')}->{candidate.get('end_frame', '')}  "
                        f"{candidate.get('name', '未命名音频')}"
                    )
        if clip.get("path"):
            lines.append(f"源文件：{clip.get('path')}")
        if clip.get("start_frame") is not None and clip.get("end_frame") is not None:
            lines.append(f"时间线帧：{clip.get('start_frame')} -> {clip.get('end_frame')}")
        if bpm:
            lines.extend([
                "",
                f"BPM：{bpm}",
                f"方法：{result.get('method', '')}",
            ])
            if confidence != "":
                lines.append(f"置信度：{confidence}")
            if result.get("analyzed_seconds"):
                lines.append(f"分析时长：{float(result.get('analyzed_seconds') or 0):.1f} 秒")
            if isinstance(result.get("beat_times_seconds"), list):
                lines.append(f"Essentia beat 点：{len(result.get('beat_times_seconds') or [])} 个")
            if result.get("median_beat_interval_seconds"):
                lines.append(f"beat 中位间隔：{result.get('median_beat_interval_seconds')} 秒")
            if result.get("beat_interval_jitter") is not None:
                try:
                    lines.append(f"beat 间隔抖动：{float(result.get('beat_interval_jitter') or 0):.2%}")
                except Exception:
                    lines.append(f"beat 间隔抖动：{result.get('beat_interval_jitter')}")
            if result.get("marker_mode_note"):
                lines.append(f"标记策略：{result.get('marker_mode_note')}")
            if result.get("essentia_message"):
                lines.append(f"Essentia：{result.get('essentia_message')}")
        bpm_props = clip.get("bpm_properties") if isinstance(clip.get("bpm_properties"), dict) else {}
        if bpm_props:
            lines.append("")
            lines.append("Resolve 属性里的 BPM/Tempo 字段")
            for key, value in bpm_props.items():
                lines.append(f"  {key}: {value}")
        alternatives = result.get("alternatives") if isinstance(result.get("alternatives"), list) else []
        if alternatives:
            lines.append("")
            lines.append("候选 BPM")
            for item in alternatives:
                if isinstance(item, dict):
                    lines.append(f"  {item.get('bpm')}  score={item.get('score')}")
        marker_result = result.get("marker_result") if isinstance(result.get("marker_result"), dict) else {}
        if marker_result:
            lines.append("")
            lines.append("节拍标记")
            lines.append(str(marker_result.get("message", "")))
            marker_scope = marker_result.get("marker_scope")
            if marker_scope:
                lines.append(f"标记位置：{'音频片段' if marker_scope == 'clip' else '时间线'}")
            if marker_result.get("marker_count") is not None:
                lines.append(f"标记数量：{marker_result.get('marker_count')}")
            if marker_result.get("interval_frames") is not None:
                lines.append(f"单拍间隔：{marker_result.get('interval_frames')} 帧")
            if marker_result.get("marker_spacing_frames") is not None:
                lines.append(f"标记间距：{marker_result.get('marker_spacing_frames')} 帧")
            if marker_result.get("first_marker_delta_frames") is not None:
                lines.append(f"首个标记距片段起点：{marker_result.get('first_marker_delta_frames')} 帧")
            if marker_result.get("first_beat_anchor_delta_frames") is not None:
                lines.append(f"首拍锚点距片段起点：{marker_result.get('first_beat_anchor_delta_frames')} 帧")
            if marker_result.get("anchor_snap_delta_frames"):
                lines.append(f"锚点吸附修正：{marker_result.get('anchor_snap_delta_frames')} 帧")
            if marker_result.get("beat_source"):
                lines.append(f"标记来源：{marker_result.get('beat_source')}")
            if marker_result.get("manual_restart_count") is not None:
                lines.append(f"手动段落锚点：{marker_result.get('manual_restart_count')} 个")
            if marker_result.get("beat_marker_step"):
                lines.append(f"标记间隔：每 {marker_result.get('beat_marker_step')} 拍")
        if not result.get("ok"):
            lines.extend([
                "",
                "说明：DaVinci Resolve 官方脚本 API 没有公开 BPM/Beat 分析入口；插件只能先通过 Resolve 找到选中/播放头音频源文件，再用 FFmpeg 解码后本地估算。",
            ])
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
            self.side_tabs.setCurrentWidget(self.detection_tab)
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
                self.side_tabs.setCurrentWidget(self.detection_tab)
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
        if widget is self.font_tab:
            self.font_status.setText("正在后台扫描当前时间线文字层...")
            QTimer.singleShot(220, lambda: self.scan_font_layers(silent=True))

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

    def enforce_resolve_window_level(self) -> None:
        if platform.system() != "Darwin":
            return
        minimized_or_hidden = self.isMinimized() or not self.isVisible()
        should_float = (not minimized_or_hidden) and (self.isActiveWindow() or macos_resolve_is_frontmost())
        apply_macos_window_level(self, should_float)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        # Keep macOS foreground checks off the hot path. They can block for
        # seconds when Resolve owns focus; showing the window is enough.

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
        self.window_level_timer.stop()
        apply_macos_window_level(self, False)
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
                "CFBundleName": APP_NAME,
                "CFBundleDisplayName": APP_NAME,
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
    startup_trace("main enter")
    if BRIDGE_WORKER_ARG in argv[1:]:
        startup_trace("bridge worker enter")
        return run_resolve_bridge_worker()
    if "--self-test" in argv[1:]:
        print(json.dumps({
            "ok": True,
            "app": APP_NAME,
            "version": APP_VERSION,
            "defaults": {
                "stuck_frames": DEFAULT_STUCK_FRAMES,
                "suspect_frames": DEFAULT_SUSPECT_FRAMES,
                "min_black_frames": DEFAULT_MIN_BLACK_FRAMES,
                "pixel_threshold_percent": DEFAULT_PIXEL_THRESHOLD,
                "black_border_px": DEFAULT_BLACK_BORDER_PX,
                "content_sample_interval": DEFAULT_CONTENT_SAMPLE_INTERVAL,
            },
        }, ensure_ascii=False))
        return 0

    startup_trace("before mac app setup")
    set_windows_app_user_model_id()
    # PyObjC/NSBundle setup can cost several seconds when launched from Resolve.
    # The Qt window can be shown without it, so keep startup on the fast path.
    startup_trace("before QApplication")
    app = QApplication(argv)
    startup_trace("after QApplication")
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    instance_guard = SingleInstanceGuard(SINGLE_INSTANCE_NAME)
    startup_trace(f"single instance already_running={instance_guard.already_running}")
    if instance_guard.already_running:
        return 0
    app._qinghe_single_instance_guard = instance_guard  # type: ignore[attr-defined]
    startup_trace("before install_cjk_font")
    font_family = install_cjk_font()
    startup_trace(f"after install_cjk_font family={font_family}")
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont(font_family, 10))
    startup_trace("before MainWindow")
    window = MainWindow()
    startup_trace("after MainWindow")
    instance_guard.bind_window(window)
    startup_trace("before show")
    bring_window_to_front(window)
    startup_trace(f"after show visible={window.isVisible()} winid={int(window.winId())}")
    QTimer.singleShot(250, lambda: bring_window_to_front(window))
    startup_trace("before app.exec")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
