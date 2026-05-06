from __future__ import annotations

import math
import random
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QBrush, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QSizePolicy, QWidget

import json

import os
import platform

import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

try:
    from tools.friday_settings_store import (
        save_gemini_api_key_everywhere,
        bootstrap_environment,
        get_friday_ui_language,
        get_friday_camera_enabled,
        get_friday_camera_disabled_message,
        set_friday_camera_enabled,
    )
except Exception:
    save_gemini_api_key_everywhere = None
    bootstrap_environment = None
    def get_friday_ui_language(): return "en"
    def get_friday_camera_enabled(): return True
    def get_friday_camera_disabled_message(): return "Camera access is currently disabled in FRIDAY settings."
    def set_friday_camera_enabled(enabled): return {}

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QImage, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (


    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget, QProgressBar,
)

try:
    import cv2
except Exception:
    cv2 = None

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1850, 1100
_MIN_W,     _MIN_H     = 1040, 640
_LEFT_W  = 330
_RIGHT_W = 470
_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def _ui_lang() -> str:
    try:
        return str(get_friday_ui_language() or "en").lower().strip()
    except Exception:
        return "en"


def _ui_text(en: str, tr: str | None = None) -> str:
    return tr if _ui_lang() == "tr" and tr is not None else en


class C:
    BG        = "#020711"
    PANEL     = "#061421"
    PANEL2    = "#081b2c"
    BORDER    = "#123a5a"
    BORDER_B  = "#19d7ff"
    BORDER_A  = "#1f5f86"
    PRI       = "#28e9ff"
    PRI_DIM   = "#1685b4"
    PRI_GHO   = "#05263a"
    ACC       = "#ff9f1c"
    ACC2      = "#ffd166"
    GREEN     = "#22f2a8"
    GREEN_D   = "#12845e"
    RED       = "#ff3b6b"
    MUTED_C   = "#ff4d8d"
    TEXT      = "#c8f7ff"
    TEXT_DIM  = "#7aa0ba"
    TEXT_MED  = "#9bdff2"
    WHITE     = "#f5fcff"
    DARK      = "#040b15"
    BAR_BG    = "#0b2032"
    VIOLET    = "#8b5cf6"
    GOLD      = "#ffc857"

def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = temps[name]
                    if entries:
                        return entries[0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class SecuritySynopsisWidget(QFrame):
    """Compact live MEDPOV Security Center synopsis for the left HUD panel."""

    _data_ready = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._last_ok = False
        self.setFixedHeight(216)
        self.setMinimumWidth(160)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(7, 24, 38, 0.96), stop:1 rgba(3, 10, 20, 0.98));
                border: 1px solid rgba(40, 233, 255, 0.28);
                border-radius: 16px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(4)
        self._title = QLabel("SECURITY\nSYNOPSIS")
        self._title.setFont(QFont("Courier New", 7, QFont.Weight.Black))
        self._title.setStyleSheet(f"color: {C.PRI};")
        top.addWidget(self._title, stretch=1)

        self._status = QLabel("SYNC")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFixedWidth(42)
        self._status.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._status.setStyleSheet(
            f"color: {C.ACC2}; background: rgba(255,209,102,0.08); "
            f"border: 1px solid {C.BORDER}; border-radius: 8px; padding: 2px;"
        )
        top.addWidget(self._status)
        lay.addLayout(top)

        self._metric = QLabel("OPEN --  ·  HIGH --")
        self._metric.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._metric.setStyleSheet(f"color: {C.TEXT_MED};")
        lay.addWidget(self._metric)

        self._metric2 = QLabel("24H --  ·  TRAFFIC --")
        self._metric2.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._metric2.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(self._metric2)

        self._ip = QLabel("IP  waiting...")
        self._ip.setFont(QFont("Courier New", 8, QFont.Weight.Black))
        self._ip.setStyleSheet(f"color: {C.ACC2};")
        self._ip.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._ip)

        self._cat = QLabel("Live threat summary loading")
        self._cat.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._cat.setWordWrap(True)
        self._cat.setStyleSheet(f"color: {C.WHITE};")
        lay.addWidget(self._cat)

        self._uri = QLabel("URI  --")
        self._uri.setFont(QFont("Courier New", 7))
        self._uri.setWordWrap(True)
        self._uri.setStyleSheet(f"color: {C.TEXT_DIM};")
        lay.addWidget(self._uri, stretch=1)

        self._action = QLabel("ACTION  --")
        self._action.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._action.setStyleSheet(f"color: {C.GREEN};")
        lay.addWidget(self._action)

        self._data_ready.connect(self._apply_data)

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self.refresh)
        self._tmr.start(60000)
        QTimer.singleShot(700, self.refresh)

    def mousePressEvent(self, event):
        self.refresh()
        super().mousePressEvent(event)

    def refresh(self):
        if self._loading:
            return
        self._loading = True
        self._status.setText("SYNC")
        self._status.setStyleSheet(
            f"color: {C.ACC2}; background: rgba(255,209,102,0.08); "
            f"border: 1px solid {C.BORDER}; border-radius: 8px; padding: 2px;"
        )

        def worker():
            try:
                try:
                    from tools.security_center_client import SecurityCenterClient
                except Exception:
                    from security_center_client import SecurityCenterClient  # type: ignore
                data = SecurityCenterClient(timeout=18).overview()
            except Exception as exc:
                data = {"ok": False, "message": str(exc)}
            self._data_ready.emit(data if isinstance(data, dict) else {"ok": False, "message": "Invalid response"})

        threading.Thread(target=worker, daemon=True).start()

    def _short(self, value, max_len=42):
        txt = str(value or "-").replace("\n", " ").strip()
        return txt if len(txt) <= max_len else txt[:max_len - 1] + "…"

    def _first_event(self, data: dict) -> dict:
        for key in ("latest_high_risk_events", "events", "threats"):
            value = data.get(key)
            if isinstance(value, list) and value:
                return value[0] if isinstance(value[0], dict) else {}
        return {}

    def _apply_data(self, data: dict):
        self._loading = False
        ok = bool(data.get("ok"))
        self._last_ok = ok

        if not ok:
            self._status.setText("ERR")
            self._status.setStyleSheet(
                f"color: {C.RED}; background: rgba(255,59,107,0.08); "
                f"border: 1px solid {C.RED}; border-radius: 8px; padding: 2px;"
            )
            self._metric.setText("REMOTE API OFFLINE")
            self._metric2.setText("click panel to retry")
            self._ip.setText("IP  --")
            self._cat.setText(self._short(data.get("message", "Security Center bağlantısı kurulamadı"), 64))
            self._uri.setText("URI  --")
            self._action.setText("ACTION  check api/key")
            return

        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        ev = self._first_event(data)
        top_ips = data.get("top_ips_24h") if isinstance(data.get("top_ips_24h"), list) else []
        top = top_ips[0] if top_ips and isinstance(top_ips[0], dict) else {}

        open_events = stats.get("open_events", 0)
        high_open = stats.get("high_open", 0)
        critical_open = stats.get("critical_open", 0)
        events_24h = stats.get("events_24h", 0)
        traffic_24h = stats.get("traffic_24h", 0)

        risk = str(ev.get("risk") or top.get("top_risk") or "OK").upper()
        if risk == "CRITICAL":
            color = C.RED
        elif risk == "HIGH":
            color = C.ACC2
        else:
            color = C.GREEN

        self._status.setText(risk[:4])
        self._status.setStyleSheet(
            f"color: {color}; background: rgba(255,255,255,0.035); "
            f"border: 1px solid {color}; border-radius: 8px; padding: 2px;"
        )
        self._metric.setText(f"OPEN {open_events}  ·  HIGH {high_open}/{critical_open}")
        self._metric2.setText(f"24H {events_24h}  ·  TRAFFIC {traffic_24h}")

        ip = ev.get("actor_ip") or top.get("ip") or "-"
        cat = ev.get("category") or top.get("sample_category") or "No active threat synopsis"
        uri = ev.get("uri") or ev.get("path") or "-"
        method = ev.get("method") or ""
        action = ev.get("action") or ev.get("status") or "monitoring"
        score = ev.get("score") or top.get("max_score") or "-"

        self._ip.setText(f"IP  {self._short(ip, 22)}")
        self._cat.setText(f"{risk} · score {score}\n{self._short(cat, 52)}")
        self._uri.setText(f"URI  {self._short((method + ' ' if method else '') + str(uri), 62)}")
        self._action.setText(f"ACTION  {self._short(action, 30)}")

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        col = C.GREEN if self._last_ok else C.ACC2
        if not self._last_ok and not self._loading:
            col = C.RED
        # subtle left energy rail
        p.setPen(Qt.PenStyle.NoPen)
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0, qcol(col, 25))
        grad.setColorAt(0.5, qcol(col, 130 if self._last_ok else 80))
        grad.setColorAt(1, qcol(col, 18))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(1, 10, 3, H - 20), 2, 2)


class HudCanvas(QWidget):
    """MEDPOV F.R.I.D.A.Y status-aware circular command core.

    Ring colors:
    - IDLE / standby: orange
    - LISTENING / speaking / active mic: green
    - MUTED: red
    """

    def __init__(self, face_path: str = "", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(520, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted = False
        self.speaking = False
        self.state = "IDLE"

        # MEDPOV FRIDAY camera / Friday vision mode
        self.camera_mode = False
        self._camera = None
        self._camera_frame: QImage | None = None
        self._camera_error = ""
        self._camera_index = 0
        self._camera_timer = QTimer(self)
        self._camera_timer.timeout.connect(self._camera_tick)
        self._camera_lock = threading.Lock()
        self._camera_snapshot_bytes: bytes | None = None
        self._camera_snapshot_mime = "image/jpeg"
        self._camera_last_snapshot_ts = 0.0

        self._tick = 0
        self._rot_outer = 0.0
        self._rot_inner = 190.0
        self._pulse = 0.0
        self._speech_meter = 0.0
        self._speech_phase = 0.0
        self._speech_flash = 0.0

        random.seed(9141)
        self._stars = [
            (random.random(), random.random(), random.uniform(0.55, 1.8), random.uniform(0, 6.28318))
            for _ in range(56)
        ]
        self._circuit_lines = [
            (
                random.uniform(0.03, 0.94),
                random.uniform(0.04, 0.92),
                random.uniform(36, 145),
                random.choice([0, 90]),
                random.uniform(0.15, 0.65),
            )
            for _ in range(34)
        ]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(33)

    def _mode(self) -> str:
        if bool(getattr(self, "muted", False)):
            return "muted"

        raw = str(getattr(self, "state", "") or "").upper().strip()

        # Friday konuşurken veya mikrofon aktif dinleme durumundayken yeşil.
        active_words = (
            "LISTEN", "LISTENING", "MIC", "MICROPHONE", "VOICE",
            "SPEAK", "SPEAKING", "CONNECTED", "ONLINE", "RECORD",
            "CAMERA", "VISION", "OPTIC", "WEBCAM"
        )
        if bool(getattr(self, "speaking", False)) or any(w in raw for w in active_words):
            return "listening"

        return "idle"

    def _pal(self) -> dict:
        mode = self._mode()

        if mode == "muted":
            return {
                "mode": "muted",
                "primary": "#ff2f2f",
                "secondary": "#ff735c",
                "accent": "#ff1b1b",
                "soft": "#ff9a8a",
                "bg0": "#330606",
                "bg1": "#170404",
                "label": "MICROPHONE MUTED",
                "label_color": "#ff4d3d",
            }

        if mode == "listening":
            return {
                "mode": "listening",
                "primary": "#00f29a",
                "secondary": "#7dffd2",
                "accent": "#00ffc8",
                "soft": "#a9ffe4",
                "bg0": "#05261a",
                "bg1": "#03120d",
                "label": "LISTENING" if not self.speaking else "SPEAKING",
                "label_color": "#00ffa8",
            }

        return {
            "mode": "idle",
            "primary": "#ff7300",
            "secondary": "#ffae35",
            "accent": "#ff9d17",
            "soft": "#ffbd82",
            "bg0": "#351406",
            "bg1": "#140806",
            "label": "STANDBY",
            "label_color": "#ff9d17",
        }

    def _q(self, color: str, alpha: float = 255) -> QColor:
        q = QColor(color)
        q.setAlpha(max(0, min(255, int(alpha))))
        return q

    def _arc(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r: float,
        start: float,
        span: float,
        color: str,
        width: float,
        alpha: float = 255,
        round_cap: bool = False,
    ):
        pen = QPen(self._q(color, alpha), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap if round_cap else Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), int(start * 16), int(span * 16))

    def _line_radial(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        deg: float,
        r1: float,
        r2: float,
        color: str,
        width: float = 1.0,
        alpha: float = 255,
    ):
        a = math.radians(deg)
        p.setPen(QPen(self._q(color, alpha), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(
            QPointF(cx + math.cos(a) * r1, cy + math.sin(a) * r1),
            QPointF(cx + math.cos(a) * r2, cy + math.sin(a) * r2),
        )

    def _animate(self):
        self._tick += 1

        mode = self._mode()
        if mode == "muted":
            speed = 0.72
        elif mode == "listening":
            speed = 1.65
        else:
            speed = 1.0

        if self.speaking:
            speed = 2.15

        self._rot_outer = (self._rot_outer + 0.78 * speed) % 360
        self._rot_inner = (self._rot_inner - 1.16 * speed) % 360

        pulse_speed = 0.105 if mode == "listening" else 0.058
        if mode == "muted":
            pulse_speed = 0.044

        self._pulse = (math.sin(self._tick * pulse_speed) + 1.0) * 0.5

        # Konuşma anında halkalara canlı ses dalgası ver.
        # Gerçek audio amplitude almadan, playback süresince doğal görünen pseudo-meter üretir.
        if bool(getattr(self, "speaking", False)) and not bool(getattr(self, "muted", False)):
            self._speech_phase += 0.34
            wave_a = (math.sin(self._speech_phase * 1.00) + 1.0) * 0.5
            wave_b = (math.sin(self._speech_phase * 2.37 + 1.7) + 1.0) * 0.5
            wave_c = (math.sin(self._speech_phase * 4.13 + 0.4) + 1.0) * 0.5
            target = 0.28 + (wave_a * 0.30) + (wave_b * 0.26) + (wave_c * 0.16)
            self._speech_meter += (min(1.0, target) - self._speech_meter) * 0.34
            self._speech_flash = min(1.0, self._speech_flash + 0.12)
        else:
            self._speech_meter *= 0.86
            self._speech_flash *= 0.82

        self.update()

    def _draw_background(self, p: QPainter, w: float, h: float, cx: float, cy: float):
        pal = self._pal()

        bg = QRadialGradient(QPointF(cx, cy), max(w, h) * 0.74)
        bg.setColorAt(0.00, self._q(pal["bg0"], 255))
        bg.setColorAt(0.42, self._q(pal["bg1"], 255))
        bg.setColorAt(1.00, self._q("#030508", 255))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRect(0, 0, int(w), int(h))

        p.setPen(QPen(self._q(pal["primary"], 18), 1))
        step = 44
        drift = int(self._tick * 0.22) % step

        for x in range(-step + drift, int(w) + step, step):
            p.drawLine(x, 0, x, int(h))

        for y in range(-step + drift // 2, int(h) + step, step):
            p.drawLine(0, y, int(w), y)

        for x, y, length, angle, alpha_mul in self._circuit_lines:
            p.setPen(QPen(self._q(pal["accent"], 22 + 32 * alpha_mul), 1))
            sx = x * w
            sy = y * h

            if angle == 0:
                p.drawLine(QPointF(sx, sy), QPointF(min(w, sx + length), sy))
                p.drawLine(QPointF(min(w, sx + length), sy), QPointF(min(w, sx + length), min(h, sy + 18)))
            else:
                p.drawLine(QPointF(sx, sy), QPointF(sx, min(h, sy + length)))
                p.drawLine(QPointF(sx, min(h, sy + length)), QPointF(min(w, sx + 18), min(h, sy + length)))

        p.setFont(QFont("Arial", 9, QFont.Weight.Medium))
        p.setPen(self._q(pal["soft"], 28))

        labels = ["FRIDAY LAUNCH", "MEDPOV CORE", "SECURITY", "THREAT BUS", "REMOTE ACCESS", "AI COMMAND"]
        for i, txt in enumerate(labels):
            x = (36 + i * 217) % max(1, int(w) - 160)
            y = (32 + i * 103) % max(1, int(h) - 28)
            p.drawText(QRectF(x, y, 180, 24), Qt.AlignmentFlag.AlignLeft, txt)

        p.setPen(Qt.PenStyle.NoPen)
        for sx, sy, size, phase in self._stars:
            a = 22 + 54 * ((math.sin(self._tick * 0.035 + phase) + 1.0) * 0.5)
            p.setBrush(QBrush(self._q(pal["primary"], a)))
            p.drawEllipse(QPointF(sx * w, sy * h), size, size)

    def _draw_outer_rings(self, p: QPainter, cx: float, cy: float, r: float):
        pal = self._pal()
        primary = pal["primary"]
        secondary = pal["secondary"]
        accent = pal["accent"]

        self._arc(p, cx, cy, r * 1.08, 15 + self._rot_outer * 0.08, 292, primary, r * 0.055, 70)
        self._arc(p, cx, cy, r * 1.08, 21 + self._rot_outer * 0.08, 286, primary, r * 0.018, 235)
        self._arc(p, cx, cy, r * 1.08, 320 + self._rot_outer * 0.08, 44, primary, r * 0.072, 245)
        self._arc(p, cx, cy, r * 1.08, 158 + self._rot_outer * 0.07, 48, primary, r * 0.047, 205)

        segments = [
            (28, 70, 0.88, 0.068, 225),
            (112, 50, 0.88, 0.060, 210),
            (188, 60, 0.88, 0.064, 220),
            (263, 58, 0.88, 0.066, 220),
            (340, 35, 0.88, 0.060, 230),
            (36, 112, 0.69, 0.040, 210),
            (188, 116, 0.69, 0.040, 210),
            (323, 43, 0.69, 0.038, 220),
        ]

        for start, span, mul, width_mul, alpha in segments:
            start2 = start - self._rot_outer * 0.17
            self._arc(p, cx, cy, r * mul, start2, span, primary, r * width_mul, alpha)
            self._arc(
                p,
                cx,
                cy,
                r * mul,
                start2 + 1.3,
                max(2, span - 2.6),
                secondary,
                max(2, r * width_mul * 0.16),
                min(255, alpha + 15),
            )

        # Bekleme turuncuda teal küçük aksan kalsın; yeşil/kırmızıda aksan kendi moda uysun.
        accent_ring = "#29d3b2" if pal["mode"] == "idle" else accent
        self._arc(p, cx, cy, r * 0.765, 72 + self._rot_inner * 0.12, 72, accent_ring, r * 0.019, 150)
        self._arc(p, cx, cy, r * 0.765, 160 + self._rot_inner * 0.12, 43, accent_ring, r * 0.009, 92)

        for i in range(72):
            deg = i * 5 + self._rot_outer * 0.025

            if i % 6 == 0:
                self._line_radial(p, cx, cy, deg, r * 0.82, r * 0.965, secondary, 2.2, 150)
            elif i % 2 == 0:
                self._line_radial(p, cx, cy, deg, r * 0.885, r * 0.965, primary, 1.15, 82)
            else:
                self._line_radial(p, cx, cy, deg, r * 0.915, r * 0.965, pal["soft"], 0.75, 42)

        p.setPen(Qt.PenStyle.NoPen)
        for deg in [149, 158, 167, 236, 245, 254]:
            a = math.radians(deg + self._rot_outer * 0.035)
            x = cx + math.cos(a) * r * 1.00
            y = cy + math.sin(a) * r * 1.00

            p.setBrush(QBrush(self._q("#090503", 190)))
            p.drawEllipse(QPointF(x, y), r * 0.019, r * 0.019)

            p.setBrush(QBrush(self._q(secondary, 68)))
            p.drawEllipse(QPointF(x, y), r * 0.009, r * 0.009)

    def _draw_inner_tech(self, p: QPainter, cx: float, cy: float, r: float):
        pal = self._pal()
        primary = pal["primary"]
        secondary = pal["secondary"]
        accent = pal["accent"]

        sweep = self._rot_outer * 1.55
        for off, alpha in [(0, 85), (-4, 45), (-8, 22)]:
            self._line_radial(p, cx, cy, sweep + off, r * 0.08, r * 1.02, accent, 1.25, alpha)

        p.setPen(QPen(self._q(pal["soft"], 56), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)

        for mul in [0.52, 0.43, 0.34, 0.245, 0.155]:
            p.drawEllipse(QPointF(cx, cy), r * mul, r * mul)

        for i in range(28):
            deg = i * (360 / 28) + self._rot_inner * 0.24
            self._line_radial(p, cx, cy, deg, r * 0.18, r * 0.50, secondary, 0.8, 34 if i % 2 else 56)

        core = QRadialGradient(QPointF(cx, cy), r * 0.52)

        if pal["mode"] == "muted":
            core.setColorAt(0.00, self._q("#fff1f1", 105 + self._pulse * 45))
            core.setColorAt(0.18, self._q(primary, 98))
            core.setColorAt(0.57, self._q("#5b0000", 38))
        elif pal["mode"] == "listening":
            core.setColorAt(0.00, self._q("#effff8", 125 + self._pulse * 70))
            core.setColorAt(0.18, self._q(primary, 105))
            core.setColorAt(0.57, self._q("#00482f", 38))
        else:
            core.setColorAt(0.00, self._q("#fff9ef", 125 + self._pulse * 70))
            core.setColorAt(0.18, self._q(primary, 102))
            core.setColorAt(0.57, self._q("#7a2c00", 34))

        core.setColorAt(1.00, self._q("#000000", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), r * 0.54, r * 0.54)

        p.setPen(Qt.PenStyle.NoPen)
        for i in range(20):
            deg = i * 18 + self._rot_inner * 0.32
            a = math.radians(deg)
            rr = r * (0.18 + 0.28 * ((i % 5) / 5))
            x = cx + math.cos(a) * rr
            y = cy + math.sin(a) * rr

            p.setBrush(QBrush(self._q(accent, 48)))
            p.drawRect(QRectF(x - 1.4, y - 1.4, 2.8, 2.8))


    def _draw_speaking_fx(self, p: QPainter, cx: float, cy: float, r: float):
        """FRIDAY konuşurken yeşil halkalara ses dalgası / equalizer animasyonu ekler."""
        if not bool(getattr(self, "speaking", False)):
            return
        if bool(getattr(self, "muted", False)):
            return

        pal = self._pal()
        if pal.get("mode") != "listening":
            return

        secondary = pal["secondary"]
        accent = pal["accent"]
        meter = max(0.0, min(1.0, float(getattr(self, "_speech_meter", 0.0))))
        phase = float(getattr(self, "_speech_phase", 0.0))
        flash = max(0.0, min(1.0, float(getattr(self, "_speech_flash", 0.0))))

        # Merkezden dışarı yayılan konuşma ripple'ları.
        for i in range(4):
            local = (self._tick * 0.025 + i * 0.24) % 1.0
            rr = r * (0.52 + local * 0.78 + meter * 0.08)
            alpha = (1.0 - local) * (48 + 92 * meter) * flash
            width = max(1.0, r * (0.004 + meter * 0.006))
            self._arc(p, cx, cy, rr, 0, 360, accent, width, alpha, True)

        # Dış çemberde konuşma equalizer barları.
        bar_count = 96
        base_inner = r * 0.985
        base_outer = r * 1.035

        for i in range(bar_count):
            deg = i * (360 / bar_count) + self._rot_outer * 0.11

            v1 = (math.sin(phase * 1.55 + i * 0.41) + 1.0) * 0.5
            v2 = (math.sin(phase * 2.70 + i * 0.17 + 1.1) + 1.0) * 0.5
            v3 = (math.sin(phase * 4.20 + i * 0.09 + 2.4) + 1.0) * 0.5
            amp = (v1 * 0.48 + v2 * 0.34 + v3 * 0.18) * meter

            if i % 5 == 0:
                amp *= 1.42
            elif i % 3 == 0:
                amp *= 0.62

            length = r * (0.026 + amp * 0.165)
            alpha = 52 + amp * 190
            width = 1.1 + amp * 3.2
            self._line_radial(
                p,
                cx,
                cy,
                deg,
                base_inner,
                base_outer + length,
                secondary,
                width,
                alpha,
            )

        # Konuşma sırasında takip eden parlak tarama yayları.
        sweep_base = -self._rot_inner * 0.72 + phase * 18.0
        arcs = [
            (sweep_base + 0, 38, r * 0.74, 0.018, 155),
            (sweep_base + 74, 26, r * 0.88, 0.014, 120),
            (sweep_base + 148, 48, r * 1.03, 0.010, 100),
            (sweep_base + 228, 34, r * 0.61, 0.012, 110),
        ]

        for start, span, rr, width_mul, alpha in arcs:
            self._arc(
                p,
                cx,
                cy,
                rr,
                start,
                span,
                "#d9fff2",
                max(2.0, r * width_mul * (0.75 + meter * 0.65)),
                alpha * (0.45 + meter * 0.75),
                True,
            )

        # Alt tarafta küçük audio waveform çizgisi.
        p.setPen(
            QPen(
                self._q(secondary, 115 + meter * 110),
                max(1.0, r * 0.004),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )

        y = cy + r * 0.82
        total_w = r * 0.78
        bars = 34
        gap = total_w / bars
        start_x = cx - total_w / 2

        for i in range(bars):
            x = start_x + i * gap
            v = (math.sin(phase * 2.7 + i * 0.72) + 1.0) * 0.5
            v += (math.sin(phase * 5.1 + i * 0.31) + 1.0) * 0.25
            h = r * (0.012 + meter * 0.050 * v)
            p.drawLine(QPointF(x, y - h), QPointF(x, y + h * 0.35))

    def _draw_title(self, p: QPainter, cx: float, cy: float, r: float):
        pal = self._pal()

        title_rect = QRectF(cx - r * 0.82, cy - r * 0.087, r * 1.64, r * 0.18)
        font = QFont("Arial", max(30, int(r * 0.118)), QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(2.6, r * 0.011))
        p.setFont(font)

        glow = pal["primary"] if pal["mode"] != "idle" else "#ffffff"

        for off, alpha in [(7, 20), (5, 38), (3, 75), (1, 145)]:
            p.setPen(QPen(self._q(glow, alpha), 1))
            for dx, dy in [(-off, 0), (off, 0), (0, -off), (0, off)]:
                p.drawText(title_rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, "F.R.I.D.A.Y")

        p.setPen(QPen(self._q("#ffffff", 250), 1))
        p.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "F.R.I.D.A.Y")

        p.setFont(QFont("Arial", max(8, int(r * 0.030)), QFont.Weight.Bold))
        p.setPen(QPen(self._q(pal["secondary"], 150), 1))
        p.drawText(
            QRectF(cx - r * 0.57, cy + r * 0.112, r * 1.14, 28),
            Qt.AlignmentFlag.AlignCenter,
            "MEDPOV INTELLIGENCE CORE",
        )

    # ------------------------------------------------------------------
    # MEDPOV FRIDAY — Friday style camera vision mode
    # ------------------------------------------------------------------

    def _preferred_camera_index(self) -> int:
        try:
            cfg = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
            return int(cfg.get("camera_index", 0) or 0)
        except Exception:
            return 0

    def _preferred_camera_backend(self) -> int:
        if cv2 is None:
            return 0
        if _OS == "Windows" and hasattr(cv2, "CAP_DSHOW"):
            return cv2.CAP_DSHOW
        if _OS == "Darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
            return cv2.CAP_AVFOUNDATION
        return getattr(cv2, "CAP_ANY", 0)

    def start_camera_mode(self, camera_index: int | None = None) -> bool:
        """
        Kamera açıldığında ana FRIDAY core görünümünü Friday tarzı kamera moduna alır.
        Orta alanda kamera görüntüsü, sağ altta mini FRIDAY halkaları gösterilir.
        """
        self.camera_mode = True
        self.state = "CAMERA"
        self._camera_error = ""
        self._camera_index = self._preferred_camera_index() if camera_index is None else int(camera_index)
        with self._camera_lock:
            self._camera_snapshot_bytes = None
        self._camera_last_snapshot_ts = 0.0
        self._camera_frame = None

        # Show the camera HUD immediately, before the webcam driver finishes opening.
        # This prevents the UI from looking frozen on slower Windows camera drivers.
        self.update()
        try:
            QApplication.processEvents()
        except Exception:
            pass

        if cv2 is None:
            self._camera_error = "opencv-python yüklü değil"
            self._camera_frame = None
            self.update()
            return False

        try:
            # Zaten açık ve frame geliyorsa aynı capture'ı kullanmaya devam et.
            if self._camera is not None and self._camera_timer.isActive():
                self.update()
                return True

            self.stop_camera_capture_only()

            backends = []
            preferred = self._preferred_camera_backend()
            if preferred:
                backends.append(preferred)
            if cv2 is not None:
                for candidate in (getattr(cv2, "CAP_MSMF", 0), getattr(cv2, "CAP_DSHOW", 0), getattr(cv2, "CAP_ANY", 0), 0):
                    if candidate not in backends:
                        backends.append(candidate)

            self._camera = None
            for backend in backends or [0]:
                try:
                    cam = cv2.VideoCapture(self._camera_index, backend) if backend else cv2.VideoCapture(self._camera_index)
                    if cam is not None and cam.isOpened():
                        self._camera = cam
                        break
                    try:
                        if cam is not None:
                            cam.release()
                    except Exception:
                        pass
                except Exception:
                    continue

            if not self._camera or not self._camera.isOpened():
                self._camera_error = f"Kamera açılamadı: index {self._camera_index}"
                self._camera = None
                self.update()
                return False

            try:
                # Lower live HUD resolution keeps FRIDAY responsive while still giving
                # a clean preview and enough data for vision snapshots.
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
                self._camera.set(cv2.CAP_PROP_FPS, 15)
                self._camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            # İlk kamera analizinde worker thread snapshot beklerken frame hazır olsun.
            # Bunu timer'a bırakınca bazen ilk 1 saniyede snapshot gelmiyor ve
            # screen_processor aynı kamerayı ikinci kez açmaya çalışıyordu. Bu da
            # bazı Windows webcam sürücülerinde uygulamayı tamamen kapatabiliyor.
            self._prime_camera_snapshot(max_reads=4)

            # 15 FPS is much lighter than 30 FPS and removes the visible slow-down.
            self._camera_timer.start(66)
            self.update()
            return True

        except Exception as exc:
            self._camera_error = str(exc)
            self._camera = None
            self.update()
            return False

    def stop_camera_capture_only(self):
        try:
            if hasattr(self, "_camera_timer") and self._camera_timer.isActive():
                self._camera_timer.stop()
        except Exception:
            pass

        try:
            if self._camera is not None:
                self._camera.release()
        except Exception:
            pass

        self._camera = None
        self._camera_frame = None
        with self._camera_lock:
            self._camera_snapshot_bytes = None
        self._camera_last_snapshot_ts = 0.0

    def stop_camera_mode(self):
        self.stop_camera_capture_only()
        self.camera_mode = False
        self._camera_error = ""
        self.state = "IDLE"
        self.update()

    def _store_camera_frame(self, frame, force_snapshot: bool = False) -> bool:
        """Convert an OpenCV frame to the HUD image and cached JPEG snapshot."""
        if frame is None or cv2 is None:
            return False

        try:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w

            self._camera_frame = QImage(
                rgb.data,
                w,
                h,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            ).copy()

            # Vision modülü ayrı kamera açmaya çalışmasın diye JPEG snapshot sakla.
            # JPEG encode pahalı olduğu için canlı HUD'da sürekli değil, aralıklı yapılır.
            now = time.time()
            should_snapshot = (
                force_snapshot
                or self._camera_snapshot_bytes is None
                or (now - float(getattr(self, "_camera_last_snapshot_ts", 0.0) or 0.0)) >= 0.85
            )
            if should_snapshot:
                ok_jpg, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 58])
                if ok_jpg:
                    with self._camera_lock:
                        self._camera_snapshot_bytes = jpg.tobytes()
                    self._camera_last_snapshot_ts = now

            self._camera_error = ""
            return True
        except Exception as exc:
            self._camera_error = str(exc)
            return False

    def _prime_camera_snapshot(self, max_reads: int = 8) -> bool:
        """Synchronously read the first frame so camera analysis can start instantly."""
        if self._camera is None or cv2 is None:
            return False

        for _ in range(max(1, int(max_reads or 1))):
            try:
                ok, frame = self._camera.read()
                if ok and frame is not None and self._store_camera_frame(frame, force_snapshot=True):
                    return True
            except Exception as exc:
                self._camera_error = str(exc)
                return False
            time.sleep(0.012)
        return False

    def _camera_tick(self):
        if not self.camera_mode or self._camera is None:
            return

        try:
            ok, frame = self._camera.read()
            if not ok or frame is None:
                self._camera_error = "Kamera görüntüsü alınamadı"
                self.update()
                return

            self._store_camera_frame(frame, force_snapshot=False)
            self.update()

        except Exception as exc:
            self._camera_error = str(exc)
            self.update()

    def camera_snapshot(self, wait_seconds: float = 1.0) -> tuple[bytes, str]:
        """
        screen_processor kamera analizi yaparken aynı kamera cihazını ikinci kez açmasın diye
        canlı HUD tarafından üretilen son JPEG frame'i thread-safe şekilde döndürür.
        """
        deadline = time.time() + max(0.1, float(wait_seconds or 0.1))
        while time.time() < deadline:
            with self._camera_lock:
                data = self._camera_snapshot_bytes
                mime = self._camera_snapshot_mime
            if data:
                return data, mime

            # Kamera Qt tarafında açılıp ilk snapshot üretilene kadar kısa bekle.
            # Buradan doğrudan cv2/QImage üretmek thread güvenli olmadığı için
            # frame hazırlama işi UI thread'indeki start/timer akışında kalır.
            time.sleep(0.02)

        raise RuntimeError(self._camera_error or "Kamera frame hazır değil")

    def camera_snapshot_ready(self) -> bool:
        with self._camera_lock:
            return bool(self._camera_snapshot_bytes)

    def camera_is_open(self) -> bool:
        return bool(self.camera_mode and self._camera is not None and not self._camera_error)

    def _draw_camera_grid(self, p: QPainter, w: float, h: float):
        pal = self._pal()
        p.save()

        p.setPen(QPen(self._q("#8db8d8", 28), 1))
        step = 42
        drift = int(self._tick * 0.18) % step

        for x in range(-step + drift, int(w) + step, step):
            p.drawLine(x, 0, x, int(h))
        for y in range(-step, int(h) + step, step):
            p.drawLine(0, y, int(w), y)

        p.setPen(QPen(self._q(pal["primary"], 15), 1))
        small_step = 14
        for x in range(0, int(w), small_step):
            if x % step != 0:
                p.drawLine(x, 0, x, int(h))
        for y in range(0, int(h), small_step):
            if y % step != 0:
                p.drawLine(0, y, int(w), y)

        p.restore()

    def _draw_camera_corners(self, p: QPainter, rect: QRectF, color: str):
        p.save()
        corner = 46
        pen = QPen(self._q(color, 155), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)

        l, r = rect.left(), rect.right()
        t, b = rect.top(), rect.bottom()

        p.drawLine(QPointF(l, t + corner), QPointF(l, t + 10))
        p.drawLine(QPointF(l + 10, t), QPointF(l + corner, t))
        p.drawLine(QPointF(r - corner, t), QPointF(r - 10, t))
        p.drawLine(QPointF(r, t + 10), QPointF(r, t + corner))
        p.drawLine(QPointF(l, b - corner), QPointF(l, b - 10))
        p.drawLine(QPointF(l + 10, b), QPointF(l + corner, b))
        p.drawLine(QPointF(r - corner, b), QPointF(r - 10, b))
        p.drawLine(QPointF(r, b - 10), QPointF(r, b - corner))

        p.restore()

    def _fit_image_rect(self, image: QImage, bounds: QRectF) -> QRectF:
        if image is None or image.isNull():
            return bounds

        iw = max(1, image.width())
        ih = max(1, image.height())
        image_ratio = iw / ih
        bounds_ratio = bounds.width() / max(1, bounds.height())

        if image_ratio > bounds_ratio:
            target_w = bounds.width()
            target_h = target_w / image_ratio
        else:
            target_h = bounds.height()
            target_w = target_h * image_ratio

        x = bounds.left() + (bounds.width() - target_w) / 2
        y = bounds.top() + (bounds.height() - target_h) / 2
        return QRectF(x, y, target_w, target_h)

    def _draw_mini_friday_core(self, p: QPainter, w: float, h: float):
        pal = self._pal()
        mini_r = max(62.0, min(w, h) * 0.102)

        # Kamera modu acikken FRIDAY core sag alta kuculuyor. Onceki surumde
        # kucuk core sadece normal donus animasyonunu ciziyordu; SPEAKING
        # esnasindaki audio ripple / equalizer efekti burada cagrilmadigi icin
        # konusma aninda halkalar duz donuyor gibi gorunuyordu.
        if bool(getattr(self, "speaking", False)) and not bool(getattr(self, "muted", False)):
            mini_r *= 1.0 + 0.018 * math.sin(self._tick * 0.25)

        cx = w - mini_r * 1.42
        cy = h - mini_r * 1.30

        p.save()
        halo = QRadialGradient(QPointF(cx, cy), mini_r * 2.35)
        halo_alpha = 92
        if bool(getattr(self, "speaking", False)) and not bool(getattr(self, "muted", False)):
            meter = max(0.0, min(1.0, float(getattr(self, "_speech_meter", 0.0))))
            halo_alpha = 105 + int(meter * 70)

        halo.setColorAt(0.00, self._q(pal["primary"], halo_alpha))
        halo.setColorAt(0.42, self._q(pal["primary"], 34))
        halo.setColorAt(1.00, self._q("#000000", 0))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), mini_r * 2.20, mini_r * 2.20)

        self._draw_outer_rings(p, cx, cy, mini_r)
        self._draw_inner_tech(p, cx, cy, mini_r)

        # Ana hologram kapaliyken hangi konusma efekti varsa,
        # kamera modundaki mini core uzerinde de aynisini koru.
        self._draw_speaking_fx(p, cx, cy, mini_r)

        p.setPen(self._q("#f5fcff", 235))
        p.setFont(QFont("Arial", max(10, int(mini_r * 0.17)), QFont.Weight.Black))
        p.drawText(
            QRectF(cx - mini_r * 0.78, cy - 12, mini_r * 1.56, 24),
            Qt.AlignmentFlag.AlignCenter,
            "F.R.I.D.A.Y",
        )

        if bool(getattr(self, "speaking", False)):
            status_text = "SPEAKING"
        elif str(getattr(self, "state", "") or "").upper().strip() == "MAP":
            status_text = "SECURITY MAP"
        else:
            status_text = "VISION CORE"
        p.setPen(self._q(pal["primary"], 210 if status_text == "SPEAKING" else 180))
        p.setFont(QFont("Courier New", max(7, int(mini_r * 0.075)), QFont.Weight.Bold))
        p.drawText(
            QRectF(cx - mini_r * 0.85, cy + mini_r * 0.28, mini_r * 1.70, 18),
            Qt.AlignmentFlag.AlignCenter,
            status_text,
        )

        p.restore()

    def _draw_camera_mode(self, p: QPainter, w: float, h: float):
        pal = self._pal()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._q("#02050c", 255)))
        p.drawRect(0, 0, int(w), int(h))

        margin_x = max(42, int(w * 0.055))
        margin_y = max(38, int(h * 0.075))
        bottom_safe = max(112, int(h * 0.155))
        camera_bounds = QRectF(margin_x, margin_y, w - margin_x * 2, h - margin_y - bottom_safe)

        self._draw_camera_grid(p, w, h)

        video_rect = camera_bounds
        if self._camera_frame is not None and not self._camera_frame.isNull():
            video_rect = self._fit_image_rect(self._camera_frame, camera_bounds)
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(video_rect, 18, 18)
            p.setClipPath(clip)
            p.drawImage(video_rect, self._camera_frame)

            overlay = QLinearGradient(video_rect.left(), video_rect.top(), video_rect.right(), video_rect.bottom())
            overlay.setColorAt(0.00, self._q("#0b1b2c", 70))
            overlay.setColorAt(0.45, self._q("#000000", 18))
            overlay.setColorAt(1.00, self._q("#000000", 88))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(overlay))
            p.drawRoundedRect(video_rect, 18, 18)
            p.restore()
        else:
            p.save()
            p.setPen(QPen(self._q(pal["primary"], 95), 1))
            p.setBrush(QBrush(self._q("#06101d", 150)))
            p.drawRoundedRect(video_rect, 18, 18)
            p.setPen(self._q("#b9f7ff", 180))
            p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
            msg = self._camera_error or "CAMERA FEED WAITING..."
            p.drawText(video_rect, Qt.AlignmentFlag.AlignCenter, msg)
            p.restore()

        vignette = QRadialGradient(QPointF(w * 0.50, h * 0.42), max(w, h) * 0.72)
        vignette.setColorAt(0.00, self._q("#000000", 6))
        vignette.setColorAt(0.56, self._q("#000000", 58))
        vignette.setColorAt(1.00, self._q("#000000", 192))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(vignette))
        p.drawRect(0, 0, int(w), int(h))

        scan_y = video_rect.top() + ((self._tick * 2.4) % max(1, int(video_rect.height())))
        scan = QLinearGradient(video_rect.left(), scan_y, video_rect.right(), scan_y)
        scan.setColorAt(0.00, self._q(pal["primary"], 0))
        scan.setColorAt(0.50, self._q("#b9f7ff", 95))
        scan.setColorAt(1.00, self._q(pal["primary"], 0))
        p.setPen(QPen(QBrush(scan), 2))
        p.drawLine(QPointF(video_rect.left(), scan_y), QPointF(video_rect.right(), scan_y))

        p.setPen(QPen(self._q(pal["primary"], 95), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(video_rect.adjusted(-1, -1, 1, 1), 18, 18)
        self._draw_camera_corners(p, video_rect.adjusted(-8, -8, 8, 8), pal["primary"])

        p.save()
        p.setPen(self._q("#b9f7ff", 210))
        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.drawText(
            QRectF(video_rect.left(), max(8, video_rect.top() - 28), 380, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "CAMERA VISION // LIVE OPTICS",
        )

        p.setPen(self._q(pal["primary"], 170))
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.drawText(
            QRectF(video_rect.right() - 360, max(8, video_rect.top() - 28), 360, 22),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "MEDPOV FRIDAY HOLOGRAPHIC INPUT",
        )
        p.restore()

        p.save()
        icon_y = h - 46
        icon_x = w * 0.5 - 72
        for i, label in enumerate(["◉", "□", "◌", "▣", "♪", "⌁"]):
            x = icon_x + i * 28
            p.setPen(QPen(self._q("#8db8d8", 115), 1))
            p.setBrush(QBrush(self._q("#07111f", 150)))
            p.drawRoundedRect(QRectF(x, icon_y, 18, 18), 5, 5)
            p.setPen(self._q("#d8faff", 155))
            p.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            p.drawText(QRectF(x, icon_y, 18, 18), Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

        p.save()
        p.setPen(self._q(pal["primary"], 210))
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.drawText(QRectF(24, h - 58, 240, 22), Qt.AlignmentFlag.AlignLeft, "● LIVE CAMERA FEED")
        p.restore()

        self._draw_mini_friday_core(p, w, h)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        pal = self._pal()

        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        r = min(w, h) * 0.335

        if self.camera_mode:
            self._draw_camera_mode(p, w, h)
            return

        if self.speaking:
            r *= 1.0 + 0.012 * math.sin(self._tick * 0.25)

        if self.muted:
            r *= 0.985

        self._draw_background(p, w, h, cx, cy)

        aura = QRadialGradient(QPointF(cx, cy), r * 1.42)
        aura.setColorAt(0.00, self._q(pal["primary"], 36 + self._pulse * 24))
        aura.setColorAt(0.55, self._q(pal["accent"], 14))
        aura.setColorAt(1.00, self._q("#000000", 0))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(aura))
        p.drawEllipse(QPointF(cx, cy), r * 1.42, r * 1.42)

        self._draw_outer_rings(p, cx, cy, r)
        self._draw_inner_tech(p, cx, cy, r)
        self._draw_speaking_fx(p, cx, cy, r)
        self._draw_title(p, cx, cy, r)

        p.setFont(QFont("Courier New", max(9, int(r * 0.035)), QFont.Weight.Bold))
        p.setPen(QPen(self._q(pal["label_color"], 215), 1))
        p.drawText(
            QRectF(cx - r * 0.52, cy + r * 0.745, r * 1.04, 30),
            Qt.AlignmentFlag.AlignCenter,
            f"◎ {pal['label']}",
        )

        p.setPen(QPen(self._q(pal["primary"], 76), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(8, 8, w - 16, h - 16))

class AssetIconWidget(QWidget):
    """
    MEDPOV real asset icon widget.
    Used for header logo mark and Security Center badge.
    """

    def __init__(self, asset_name: str = "medpov_ui_shield.png", size: int = 50, glow: bool = True, parent=None):
        super().__init__(parent)
        self.asset_name = asset_name
        self.icon_size = int(size or 50)
        self.glow = bool(glow)
        self.setFixedSize(self.icon_size, self.icon_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _asset_path(self) -> Path:
        try:
            return BASE_DIR / "assets" / self.asset_name
        except Exception:
            return Path("assets") / self.asset_name

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W = float(self.width())
        H = float(self.height())
        cx, cy = W / 2.0, H / 2.0
        s = min(W, H)

        if self.glow:
            halo = QRadialGradient(QPointF(cx, cy), s * 0.62)
            halo.setColorAt(0.00, qcol(C.PRI, 70))
            halo.setColorAt(0.52, qcol(C.PRI, 22))
            halo.setColorAt(1.00, qcol("#000000", 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(cx, cy), s * 0.50, s * 0.50)

        path = self._asset_path()
        pix = QPixmap(str(path))

        if pix.isNull():
            # Asset bulunamazsa uygulama Ã§Ã¶kmesin diye minimal fallback
            p.setPen(QPen(qcol(C.PRI, 220), max(1, int(s * 0.04))))
            p.setBrush(QBrush(qcol("#061421", 230)))
            p.drawRoundedRect(QRectF(4, 4, W - 8, H - 8), 12, 12)
            p.setFont(QFont("Segoe UI", max(8, int(s * 0.22)), QFont.Weight.Black))
            p.setPen(qcol(C.PRI, 235))
            p.drawText(QRectF(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, "MP")
            return

        target_size = s * 0.84
        target = QRectF(
            (W - target_size) / 2.0,
            (H - target_size) / 2.0,
            target_size,
            target_size,
        )

        p.drawPixmap(target, pix, QRectF(pix.rect()))


class ShieldMark(QWidget):
    """
    Header MEDPOV shield mark.
    Drawn in-code so the app does not crash if an external logo file is missing.
    """

    def __init__(self, size: int = 50, parent=None):
        super().__init__(parent)
        self._size = int(size or 50)
        self.setFixedSize(self._size, self._size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())
        cx, cy = W / 2.0, H / 2.0
        s = min(W, H)

        # Outer glow
        glow = QRadialGradient(QPointF(cx, cy), s * 0.62)
        glow.setColorAt(0.00, qcol(C.PRI, 78))
        glow.setColorAt(0.48, qcol(C.PRI, 24))
        glow.setColorAt(1.00, qcol("#000000", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), s * 0.47, s * 0.47)

        # Hex frame
        r = s * 0.36
        hex_path = QPainterPath()
        for i in range(6):
            ang = math.radians(30 + i * 60)
            x = cx + math.cos(ang) * r
            y = cy + math.sin(ang) * r
            if i == 0:
                hex_path.moveTo(x, y)
            else:
                hex_path.lineTo(x, y)
        hex_path.closeSubpath()

        fill = QLinearGradient(0, 0, W, H)
        fill.setColorAt(0.00, qcol("#0c3148", 230))
        fill.setColorAt(0.55, qcol("#072033", 245))
        fill.setColorAt(1.00, qcol("#03101d", 252))
        p.setBrush(QBrush(fill))
        p.setPen(QPen(qcol(C.PRI, 210), max(1.2, s * 0.035)))
        p.drawPath(hex_path)

        # Inner shield
        shield = QPainterPath()
        shield.moveTo(cx, cy - s * 0.20)
        shield.lineTo(cx + s * 0.18, cy - s * 0.12)
        shield.lineTo(cx + s * 0.15, cy + s * 0.12)
        shield.quadTo(cx, cy + s * 0.24, cx - s * 0.15, cy + s * 0.12)
        shield.lineTo(cx - s * 0.18, cy - s * 0.12)
        shield.closeSubpath()

        shield_grad = QLinearGradient(0, cy - s * 0.24, 0, cy + s * 0.25)
        shield_grad.setColorAt(0.00, qcol("#13ecff", 85))
        shield_grad.setColorAt(0.65, qcol("#0b75b9", 150))
        shield_grad.setColorAt(1.00, qcol("#063c70", 170))
        p.setBrush(QBrush(shield_grad))
        p.setPen(QPen(qcol(C.PRI, 225), max(1.0, s * 0.026)))
        p.drawPath(shield)

        # Core mark
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(qcol(C.GREEN, 220), max(1.0, s * 0.025)))
        inner = QRectF(cx - s * 0.08, cy - s * 0.08, s * 0.16, s * 0.16)
        p.drawEllipse(inner)

        p.setPen(QPen(qcol(C.PRI, 185), max(1.0, s * 0.018)))
        p.drawLine(QPointF(cx, cy - s * 0.025), QPointF(cx, cy + s * 0.075))
        p.drawLine(QPointF(cx - s * 0.055, cy + s * 0.025), QPointF(cx, cy + s * 0.075))
        p.drawLine(QPointF(cx + s * 0.055, cy + s * 0.025), QPointF(cx, cy + s * 0.075))

class MetricBar(QWidget):
    """
    MEDPOV compact readable metric row.
    v7: Removes unclear symbol glyphs and uses readable CPU/MEM/NET/GPU/TMP chips.
    """

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = str(label or "").upper()
        self._color = color
        self._value = 0.0
        self._text = "--"
        self.setFixedHeight(45)
        self.setMinimumWidth(118)

    def set_value(self, pct: float, text: str):
        try:
            pct = float(pct)
        except Exception:
            pct = 0.0

        self._value = max(0.0, min(100.0, pct))
        self._text = str(text or "--")
        self.update()

    def _chip_text(self) -> str:
        key = self._label.strip().upper()

        if key in ("CPU", "PROCESSOR"):
            return "CPU"

        if key in ("MEM", "MEMORY", "RAM"):
            return "MEM"

        if key in ("NET", "NETWORK"):
            return "NET"

        if key == "GPU":
            return "GPU"

        if key in ("TMP", "TEMP", "TEMPERATURE"):
            return "TMP"

        return key[:3] if key else "SYS"

    def _pretty_label(self) -> str:
        key = self._label.strip().upper()

        if key == "MEM":
            return "MEMORY"

        if key == "NET":
            return "NETWORK"

        if key == "TMP":
            return "TEMP"

        return key

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        W = float(self.width())
        H = float(self.height())

        bg = QLinearGradient(0, 0, W, H)
        bg.setColorAt(0.00, qcol("#0b2134", 238))
        bg.setColorAt(0.45, qcol("#071827", 248))
        bg.setColorAt(1.00, qcol("#030a14", 252))

        p.setPen(QPen(qcol(C.BORDER_A, 160), 1))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 13, 13)

        # soft upper light
        top_glow = QLinearGradient(0, 1, 0, H * 0.58)
        top_glow.setColorAt(0.00, qcol(C.PRI, 24))
        top_glow.setColorAt(1.00, qcol(C.PRI, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(top_glow))
        p.drawRoundedRect(QRectF(2, 2, W - 4, H * 0.54), 12, 12)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        # readable chip instead of broken symbol icon
        chip_rect = QRectF(11, 8, 42, 28)

        chip_grad = QLinearGradient(chip_rect.left(), chip_rect.top(), chip_rect.right(), chip_rect.bottom())
        chip_grad.setColorAt(0.00, qcol(self._color, 82))
        chip_grad.setColorAt(0.55, qcol("#09263a", 225))
        chip_grad.setColorAt(1.00, qcol("#04101d", 245))

        p.setBrush(QBrush(chip_grad))
        p.setPen(QPen(qcol(self._color, 175), 1))
        p.drawRoundedRect(chip_rect, 9, 9)

        # tiny chip inner scan line
        p.setPen(QPen(qcol(self._color, 72), 1))
        p.drawLine(
            QPointF(chip_rect.left() + 6, chip_rect.bottom() - 6),
            QPointF(chip_rect.right() - 6, chip_rect.bottom() - 6),
        )

        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Black))
        p.setPen(qcol("#e7fbff", 235))
        p.drawText(
            chip_rect,
            Qt.AlignmentFlag.AlignCenter,
            self._chip_text(),
        )

        # label
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        p.setPen(qcol(C.WHITE, 238))
        p.drawText(
            QRectF(62, 7, max(20, W - 154), 15),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._pretty_label(),
        )

        # value
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.Black))
        p.setPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM))
        p.drawText(
            QRectF(W - 96, 5, 80, 18),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._text,
        )

        # progress rail
        bar_x = 62
        bar_y = H - 14
        bar_w = max(32, W - 84)
        bar_h = 5
        fill_w = int(bar_w * self._value / 100.0)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol("#0a2638", 245)))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)

        if fill_w > 0:
            grad = QLinearGradient(bar_x, bar_y, bar_x + max(1, fill_w), bar_y)
            grad.setColorAt(0.00, qcol(self._color, 120))
            grad.setColorAt(0.70, bar_col)
            grad.setColorAt(1.00, qcol("#ffffff", 185))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 3, 3)

        # status dot
        p.setBrush(QBrush(bar_col))
        p.drawEllipse(QPointF(W - 16, bar_y + bar_h / 2), 2.0, 2.0)



class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Cascadia Mono", 8))
        try:
            # Sağ panel uzun çalışmalarda ağırlaşmasın.
            self.document().setMaximumBlockCount(450)
        except Exception:
            pass
        self.setStyleSheet(f"""
            QTextEdit {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(4, 15, 27, 0.98),
                    stop:0.55 rgba(6, 20, 33, 0.98),
                    stop:1 rgba(2, 7, 17, 0.98));
                color: {C.TEXT};
                border: 1px solid rgba(40, 233, 255, 0.28);
                border-radius: 16px;
                padding: 9px;
                selection-background-color: rgba(40, 233, 255, 0.20);
            }}
            QScrollBar:vertical {{
                background: rgba(2, 7, 17, 0.88);
                width: 8px;
                border: none;
                margin: 10px 2px 10px 0;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(40, 233, 255, 0.74);
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        # Eski sürümde loglar harf harf yazılıyordu. Kamera/voice akışında
        # kuyruk büyüyünce kullanıcı bir önceki konuşmayı geç görüyordu.
        # v2.7.0: satırı tek seferde basıyoruz; komut geçmişi artık anlık akar.
        self._last_text = ""
        self._last_text_ts = 0.0
        self._sig.connect(self._append_now)

    def append_log(self, text: str):
        self._sig.emit(str(text or ""))

    def _tag_for(self, text: str) -> str:
        tl = (text or "").lower()
        if tl.startswith("you:"):
            return "you"
        if tl.startswith("friday:") or tl.startswith("friday:"):
            return "ai"
        if tl.startswith("file:"):
            return "file"
        if "err" in tl or "error" in tl:
            return "err"
        return "sys"

    def _append_now(self, text: str):
        text = str(text or "").strip()
        if not text:
            return

        # Aynı Qt sinyal zincirinden gelen kamera online/offline tekrarlarını temiz tut.
        now = time.time()
        if text == self._last_text and (now - self._last_text_ts) < 0.85:
            return
        self._last_text = text
        self._last_text_ts = now

        tag = self._tag_for(text)
        col = {
            "you":  qcol(C.WHITE),
            "ai":   qcol(C.PRI),
            "err":  qcol(C.RED),
            "file": qcol(C.GREEN),
            "sys":  qcol(C.ACC2),
        }.get(tag, qcol(C.TEXT))

        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)

        ts_fmt = cur.charFormat()
        ts_fmt.setForeground(QBrush(qcol(C.TEXT_DIM, 210)))
        cur.insertText(time.strftime("%H:%M:%S") + "  ", ts_fmt)

        txt_fmt = cur.charFormat()
        txt_fmt.setForeground(QBrush(col))
        cur.insertText(text + "\n", txt_fmt)

        self.setTextCursor(cur)
        self.ensureCursorVisible()

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(112)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for MEDPOV FRIDAY", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 7
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        if z._drag_over:
            bg.setColorAt(0.0, qcol("#073047", 240))
            bg.setColorAt(1.0, qcol("#03101c", 250))
        elif z._hovering:
            bg.setColorAt(0.0, qcol("#062638", 230))
            bg.setColorAt(1.0, qcol("#04101b", 245))
        else:
            bg.setColorAt(0.0, qcol("#071826", 235))
            bg.setColorAt(1.0, qcol("#030a14", 245))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(rect, 14, 14)

        if z._current_file:   border_col = qcol(C.GREEN, 210)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 205)
        else:                 border_col = qcol(C.BORDER_A, 180)

        pen = QPen(border_col, 1.4, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 14, 14)

        # center soft glow
        glow = QRadialGradient(rect.center(), min(W, H) * 0.82)
        glow.setColorAt(0.0, qcol(C.PRI, 20 if not z._current_file else 34))
        glow.setColorAt(1.0, qcol(C.PRI, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 14, 14)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2 - 4
        col = qcol(C.PRI if hover else C.PRI_DIM, 235 if hover else 180)

        # Minimal clean upload icon; avoids visual clutter in the compact right panel.
        icon_rect = QRectF(cx - 21, cy - 22, 42, 34)
        p.setPen(QPen(col, 2.0))
        p.setBrush(QBrush(qcol(C.PRI, 18 if hover else 10)))
        p.drawRoundedRect(icon_rect, 9, 9)
        p.drawLine(QPointF(cx, cy + 3), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx - 8, cy - 8), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx + 8, cy - 8), QPointF(cx, cy - 16))
        p.drawLine(QPointF(cx - 13, cy + 11), QPointF(cx + 13, cy + 11))

        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
        p.setPen(QPen(qcol(C.WHITE if hover else C.TEXT_MED), 1))
        p.drawText(QRectF(0, cy + 22, W, 18), Qt.AlignmentFlag.AlignCenter,
                   "Drop file or click to analyze")
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM, 170), 1))
        p.drawText(QRectF(0, cy + 43, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Image · PDF · Office · Code · Data · Media")

    def _paint_drag_over(self, p, W, H):
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Black))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, 35, W, 24), Qt.AlignmentFlag.AlignCenter, "RELEASE TO LOAD FILE")
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_MED), 1))
        p.drawText(QRectF(0, 60, W, 20), Qt.AlignmentFlag.AlignCenter, "FRIDAY will prepare analysis context")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        cx, cy = W / 2, H / 2

        badge = QRectF(cx - 19, cy - 36, 38, 30)
        p.setPen(QPen(qcol(col, 210), 1.4))
        p.setBrush(QBrush(qcol(col, 26)))
        p.drawRoundedRect(badge, 9, 9)

        p.setFont(QFont("Segoe UI Emoji", 15, QFont.Weight.Bold))
        p.setPen(QPen(qcol(col, 235), 1))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, icon)

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name
        if len(name) > 36:
            name = name[:17] + "…" + name[-16:]
        p.drawText(QRectF(14, cy - 1, W - 28, 18), Qt.AlignmentFlag.AlignCenter, name)

        try:
            meta = f"{cat.upper()} · {_fmt_size(path.stat().st_size)} · READY"
        except Exception:
            meta = f"{cat.upper()} · READY"
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.GREEN, 220), 1))
        p.drawText(QRectF(0, cy + 20, W, 18), Qt.AlignmentFlag.AlignCenter, meta)

class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  MEDPOV FRIDAY SETUP", 13, True))
        layout.addWidget(_lbl("Connect your Gemini API key to start the MEDPOV FRIDAY core.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 10px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  ACTIVATE FRIDAY CORE")
        init_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 10px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 10px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 10px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class ActivityLineWidget(QWidget):
    """
    Compact live telemetry line chart for the left SYSTEM ACTIVITY card.
    Safe standalone widget: draws a soft MEDPOV cyan activity line without
    depending on external chart libraries.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setMinimumWidth(120)
        self._tick = 0
        self._points = [
            0.20, 0.26, 0.41, 0.34, 0.31, 0.33, 0.22, 0.19,
            0.36, 0.40, 0.34, 0.36, 0.42, 0.28, 0.29, 0.35,
            0.36, 0.39, 0.44, 0.27
        ]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(950)

    def _animate(self):
        self._tick += 1

        try:
            snap = _metrics.snapshot()
            cpu = float(snap.get("cpu", 0.0)) / 100.0
            mem = float(snap.get("mem", 0.0)) / 100.0
            net = min(1.0, float(snap.get("net", 0.0)) / 4.0)
            live = max(0.10, min(0.92, (cpu * 0.45) + (mem * 0.25) + (net * 0.30)))
        except Exception:
            live = 0.30 + 0.16 * math.sin(self._tick * 0.65)

        pulse = 0.035 * math.sin(self._tick * 0.82)
        live = max(0.08, min(0.94, live + pulse))

        self._points.append(live)
        if len(self._points) > 22:
            self._points = self._points[-22:]

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        W = float(self.width())
        H = float(self.height())

        # Background panel
        bg = QLinearGradient(0, 0, W, H)
        bg.setColorAt(0.00, qcol("#061421", 190))
        bg.setColorAt(1.00, qcol("#020711", 225))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(0, 0, W, H), 12, 12)

        left = 13.0
        right = W - 11.0
        top = 9.0
        bottom = H - 10.0
        width = max(1.0, right - left)
        height = max(1.0, bottom - top)

        # Grid / baseline
        p.setPen(QPen(qcol(C.BORDER_A, 58), 1))
        for i in range(1, 4):
            y = top + height * i / 4.0
            p.drawLine(QPointF(left, y), QPointF(right, y))

        p.setPen(QPen(qcol(C.PRI, 54), 1))
        p.drawLine(QPointF(left, bottom), QPointF(right, bottom))

        pts = list(self._points)
        if len(pts) < 2:
            return

        step = width / max(1, len(pts) - 1)

        path = QPainterPath()
        area = QPainterPath()

        for i, value in enumerate(pts):
            x = left + i * step
            y = bottom - (max(0.0, min(1.0, value)) * height)

            if i == 0:
                path.moveTo(x, y)
                area.moveTo(x, bottom)
                area.lineTo(x, y)
            else:
                px = left + (i - 1) * step
                py = bottom - (max(0.0, min(1.0, pts[i - 1])) * height)
                cx1 = px + step * 0.48
                cx2 = x - step * 0.48
                path.cubicTo(QPointF(cx1, py), QPointF(cx2, y), QPointF(x, y))
                area.cubicTo(QPointF(cx1, py), QPointF(cx2, y), QPointF(x, y))

        area.lineTo(right, bottom)
        area.closeSubpath()

        fill = QLinearGradient(0, top, 0, bottom)
        fill.setColorAt(0.00, qcol(C.PRI, 66))
        fill.setColorAt(1.00, qcol(C.PRI, 0))
        p.setBrush(QBrush(fill))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(area)

        # Glow line
        glow_pen = QPen(qcol(C.PRI, 58), 5)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(glow_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        line_pen = QPen(qcol("#32efff", 235), 2)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(line_pen)
        p.drawPath(path)

        # Latest point
        last_value = max(0.0, min(1.0, pts[-1]))
        lx = right
        ly = bottom - last_value * height
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.GREEN, 220)))
        p.drawEllipse(QPointF(lx, ly), 3.2, 3.2)

        p.setBrush(QBrush(qcol(C.PRI, 55)))
        p.drawEllipse(QPointF(lx, ly), 7.0, 7.0)

class MainWindow(QMainWindow):
    _log_sig          = pyqtSignal(str)
    _state_sig        = pyqtSignal(str)
    _standby_sig      = pyqtSignal(bool)
    _camera_start_sig = pyqtSignal(object)
    _camera_stop_sig  = pyqtSignal()
    _map_start_sig    = pyqtSignal(object)
    _map_focus_sig    = pyqtSignal(object)
    _map_stop_sig     = pyqtSignal()

    def __init__(self, face_path: str):
        super().__init__()
        self.setWindowTitle("MEDPOV FRIDAY — Holographic AI Command Center")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command  = None
        self._muted           = False
        self._standby         = False
        self._camera_access_enabled = bool(get_friday_camera_enabled())
        self._current_file: str | None = None

        central = QWidget()
        central.setObjectName("FridayRoot")
        central.setStyleSheet("""
            QWidget#FridayRoot {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #01050c, stop:0.45 #03111f, stop:1 #01050c);
            }
        """)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 0)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        self.hud = HudCanvas(face_path)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.hud, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._standby_sig.connect(self._set_standby)
        self._camera_start_sig.connect(self._start_camera_mode_now)
        self._camera_stop_sig.connect(self._stop_camera_mode_now)
        self._map_start_sig.connect(self._start_security_map_now)
        self._map_focus_sig.connect(self._focus_security_map_now)
        self._map_stop_sig.connect(self._stop_security_map_now)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_camera = QShortcut(QKeySequence("F6"), self)
        sc_camera.activated.connect(self._toggle_camera_access)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            cw = self.centralWidget()
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QFrame()
        w.setFixedHeight(88)
        w.setObjectName("FridayHeader")
        w.setStyleSheet(f"""
            QFrame#FridayHeader {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 rgba(3, 13, 24, 0.99),
                    stop:0.48 rgba(7, 27, 43, 0.98),
                    stop:1 rgba(3, 13, 24, 0.99));
                border: 1px solid rgba(40, 233, 255, 0.32);
                border-radius: 16px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)

        grid = QGridLayout(w)
        grid.setContentsMargins(22, 9, 22, 9)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        left_wrap = QHBoxLayout()
        left_wrap.setSpacing(13)
        left_wrap.addWidget(AssetIconWidget("medpov_ui_shield.png", size=50, glow=True))

        left = QVBoxLayout()
        left.setSpacing(1)
        brand = QLabel("MEDPOV")
        brand.setFont(QFont("Segoe UI", 22, QFont.Weight.Black))
        brand.setStyleSheet(f"color: {C.WHITE}; letter-spacing: 1.1px;")
        left.addWidget(brand)
        build = QLabel("PRIVATE AI COMMAND SYSTEM")
        build.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        build.setStyleSheet(f"color: {C.PRI}; letter-spacing: 3px;")
        left.addWidget(build)
        left_wrap.addLayout(left)
        left_wrap.addStretch()
        grid.addLayout(left_wrap, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        mid = QVBoxLayout()
        mid.setSpacing(0)
        title = QLabel("F.R.I.D.A.Y")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 29, QFont.Weight.Black))
        title.setStyleSheet(f"color: {C.PRI}; letter-spacing: 10px;")
        mid.addWidget(title)
        sub = QLabel("MEDPOV HOLOGRAPHIC PERSONAL INTELLIGENCE INTERFACE")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        sub.setStyleSheet(f"color: {C.TEXT_MED}; letter-spacing: 3px;")
        mid.addWidget(sub)
        grid.addLayout(mid, 0, 1, Qt.AlignmentFlag.AlignCenter)

        right_box = QFrame()
        right_box.setObjectName("HeaderStatusBox")
        right_box.setFixedSize(214, 52)
        right_box.setStyleSheet(f"""
            QFrame#HeaderStatusBox {{
                background: rgba(2, 12, 22, 0.46);
                border: 1px solid rgba(40, 233, 255, 0.20);
                border-radius: 14px;
            }}
        """)
        rb = QHBoxLayout(right_box)
        rb.setContentsMargins(14, 6, 14, 6)
        rb.setSpacing(12)

        time_col = QVBoxLayout()
        time_col.setSpacing(0)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Black))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI};")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Black))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM};")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_col.addWidget(self._date_lbl)
        rb.addLayout(time_col, stretch=1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color: rgba(40,233,255,0.25);")
        rb.addWidget(line)

        status = QLabel("SYSTEM\nONLINE")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setFont(QFont("Segoe UI", 7, QFont.Weight.Black))
        status.setStyleSheet(f"color: {C.GREEN}; letter-spacing: 0.8px;")
        rb.addWidget(status)
        grid.addWidget(right_box, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QFrame()
        w.setFixedWidth(_LEFT_W)
        w.setObjectName("LeftCommandPanel")
        w.setStyleSheet(f"""
            QFrame#LeftCommandPanel {{
                background: rgba(3, 11, 21, 0.70);
                border: 1px solid rgba(40, 233, 255, 0.22);
                border-radius: 16px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        def section(title: str, icon: str = "✦"):
            box = QFrame()
            box.setObjectName("FridaySectionBox")
            box.setStyleSheet(f"""
                QFrame#FridaySectionBox {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 rgba(7, 24, 38, 0.90), stop:1 rgba(3, 10, 20, 0.96));
                    border: 1px solid rgba(40, 233, 255, 0.24);
                    border-radius: 16px;
                }}
            """)
            outer = QVBoxLayout(box)
            outer.setContentsMargins(12, 10, 12, 12)
            outer.setSpacing(9)
            head = QLabel(f"{icon}  {title}")
            head.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
            head.setStyleSheet(f"color: {C.WHITE}; letter-spacing: 0.8px;")
            outer.addWidget(head)
            return box, outer

        status_box, status_lay = section("SYSTEM STATUS", "⌁")
        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEMORY", C.ACC2)
        self._bar_net = MetricBar("NETWORK", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TEMP", "#ff6688")
        for bar in [self._bar_cpu, self._bar_mem, self._bar_net, self._bar_gpu, self._bar_tmp]:
            status_lay.addWidget(bar)
        lay.addWidget(status_box)

        info_box, info_lay = section("SYSTEM INFO", "◈")
        def info_row(icon: str, label: QLabel):
            row = QHBoxLayout(); row.setSpacing(8)
            ic = QLabel(icon); ic.setFixedWidth(22); ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setFont(QFont("Segoe UI", 11, QFont.Weight.Black))
            ic.setStyleSheet(f"color: {C.PRI};")
            label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            label.setStyleSheet(f"color: {C.TEXT_MED};")
            row.addWidget(ic); row.addWidget(label, stretch=1)
            return row

        self._uptime_lbl = QLabel("UP TIME        --:--")
        self._proc_lbl = QLabel("PROCESSES      --")
        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS             {os_name}")
        for icon, lbl in [("◷", self._uptime_lbl), ("▤", self._proc_lbl), ("▦", os_lbl)]:
            info_lay.addLayout(info_row(icon, lbl))
        lay.addWidget(info_box)

        sc_box, sc_lay = section("SECURITY SYNOPSIS", "✧")
        self._sc_synopsis = SecuritySynopsisWidget(self)
        sc_lay.addWidget(self._sc_synopsis)
        lay.addWidget(sc_box)

        activity_box, activity_lay = section("SYSTEM ACTIVITY", "⌁")
        spark_top = QHBoxLayout()
        spark_title = QLabel("Live telemetry")
        spark_title.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        spark_title.setStyleSheet(f"color: {C.TEXT_DIM};")
        spark_peak = QLabel("Peak 72%")
        spark_peak.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        spark_peak.setStyleSheet(f"color: {C.PRI};")
        spark_top.addWidget(spark_title)
        spark_top.addStretch()
        spark_top.addWidget(spark_peak)
        activity_lay.addLayout(spark_top)
        activity_lay.addWidget(ActivityLineWidget(self))
        lay.addWidget(activity_box)

        lay.addStretch()

        lay.addWidget(self._build_left_quick_access_panel())

        pills = QHBoxLayout(); pills.setSpacing(8)
        for txt, col in [("●  FRIDAY ONLINE", C.GREEN), ("◇  MEDPOV SECURE", C.PRI), ("◎  AI CORE READY", C.TEXT_MED)]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Black))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: rgba(7,24,38,0.82); "
                f"border: 1px solid rgba(40,233,255,0.26); border-radius: 10px; padding: 7px 6px;"
            )
            pills.addWidget(lbl)
        lay.addLayout(pills)

        return w

    def _build_left_quick_access_panel(self) -> QWidget:
        """Bottom-left map/camera quick launcher. No duplicate buttons in map/camera HUD."""
        box = QFrame()
        box.setObjectName("LeftQuickAccessPanel")
        box.setStyleSheet(f"""
            QFrame#LeftQuickAccessPanel {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(7, 24, 38, 0.94),
                    stop:0.55 rgba(3, 12, 22, 0.98),
                    stop:1 rgba(2, 8, 16, 0.98));
                border: 1px solid rgba(40, 233, 255, 0.30);
                border-radius: 16px;
            }}
            QFrame#LeftQuickAccessPanel QLabel {{
                background: transparent;
                border: none;
            }}
            QFrame#LeftQuickAccessPanel QPushButton {{
                border-radius: 11px;
                padding: 7px 8px;
                font-weight: 900;
                text-align: center;
            }}
        """)

        lay = QVBoxLayout(box)
        lay.setContentsMargins(11, 10, 11, 11)
        lay.setSpacing(7)

        title = QLabel("◇  QUICK ACCESS")
        title.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        title.setStyleSheet(f"color: {C.WHITE}; letter-spacing: 0.8px;")
        lay.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._left_map_btn = QPushButton("🗺  MAP")
        self._left_map_btn.setFixedHeight(32)
        self._left_map_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        self._left_map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._left_map_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(40,233,255,0.12);
                color: {C.PRI};
                border: 1px solid rgba(40,233,255,0.40);
            }}
            QPushButton:hover {{
                background: rgba(40,233,255,0.26);
                color: {C.WHITE};
                border: 1px solid rgba(40,233,255,0.78);
            }}
        """)
        self._left_map_btn.clicked.connect(self._open_security_map_quick)
        row.addWidget(self._left_map_btn)

        self._left_camera_btn = QPushButton("📷  CAMERA")
        self._left_camera_btn.setFixedHeight(32)
        self._left_camera_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        self._left_camera_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._left_camera_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(34,242,168,0.12);
                color: {C.GREEN};
                border: 1px solid rgba(34,242,168,0.40);
            }}
            QPushButton:hover {{
                background: rgba(34,242,168,0.25);
                color: {C.WHITE};
                border: 1px solid rgba(34,242,168,0.78);
            }}
        """)
        self._left_camera_btn.clicked.connect(self._open_camera_quick)
        row.addWidget(self._left_camera_btn)

        lay.addLayout(row)

        hint = QLabel("Map and camera open in the main HUD.")
        hint.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        return box


    def _build_friday_settings_panel(self):
        """
        Right sidebar settings shortcut panel.
        Safe method injected by MEDPOV Friday Settings Panel Repair.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QMessageBox

        panel = QFrame()
        panel.setObjectName("FridaySettingsQuickPanel")
        panel.setStyleSheet(f"""
            QFrame#FridaySettingsQuickPanel {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(255, 159, 28, 0.18),
                    stop:0.48 rgba(7, 24, 38, 0.86),
                    stop:1 rgba(3, 10, 20, 0.96));
                border: 1px solid rgba(255, 209, 102, 0.36);
                border-radius: 16px;
            }}
            QLabel {{ background: transparent; border: none; }}
            QLabel#FridaySettingsTitle {{
                color: {C.ACC2};
                font-size: 12px;
                font-weight: 900;
                letter-spacing: 1.2px;
            }}
            QLabel#FridaySettingsDesc {{
                color: rgba(226, 245, 255, 0.72);
                font-size: 10px;
            }}
            QPushButton {{
                color: #fff7ed;
                background: rgba(255, 159, 28, 0.18);
                border: 1px solid rgba(255, 209, 102, 0.38);
                border-radius: 11px;
                padding: 8px 10px;
                font-weight: 900;
            }}
            QPushButton:hover {{
                background: rgba(255, 159, 28, 0.30);
                border-color: rgba(255, 209, 102, 0.70);
            }}
        """)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(7)

        title = QLabel("⚙  FRIDAY SETTINGS")
        title.setObjectName("FridaySettingsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)

        desc = QLabel(_ui_text("Voice, AI provider, language, camera privacy and Security Center settings.", "Ses, AI sağlayıcı, dil, kamera gizliliği ve Security Center ayarları."))
        desc.setObjectName("FridaySettingsDesc")
        desc.setWordWrap(True)

        btn = QPushButton(_ui_text("Open Settings     ›", "Ayarları Aç     ›"))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._open_friday_settings_dialog)

        lay.addWidget(title)
        lay.addWidget(desc)
        lay.addWidget(btn)

        return panel

    def _open_friday_settings_dialog(self):
        """
        Opens the settings dialog without breaking the UI if the dialog file is missing.
        """
        from PyQt6.QtWidgets import QMessageBox
        import importlib

        try:
            mod = importlib.import_module("tools.friday_settings_dialog")
            dialog_cls = (
                getattr(mod, "FridaySettingsDialog", None)
                or getattr(mod, "SettingsDialog", None)
                or getattr(mod, "FridaySettingsPanel", None)
            )
            if dialog_cls is None:
                raise RuntimeError("FridaySettingsDialog class was not found in tools/friday_settings_dialog.py.")

            try:
                dlg = dialog_cls(self)
            except TypeError:
                dlg = dialog_cls()

            if hasattr(dlg, "exec"):
                dlg.exec()
            elif hasattr(dlg, "show"):
                dlg.show()
                self._friday_settings_dialog_ref = dlg
            else:
                raise RuntimeError("Settings window does not support exec/show.")

        except Exception as exc:
            QMessageBox.warning(
                self,
                "FRIDAY Settings",
                "Settings window could not be opened.\n\n"
                f"Error: {exc}\n\n"
                "Check:\n"
                "- tools/friday_settings_dialog.py exists\n"
                "- tools/friday_settings_store.py exists\n"
                "- config/friday_settings.json is writable"
            )

    def _build_right_panel(self) -> QWidget:
        w = QFrame()
        w.setFixedWidth(_RIGHT_W)
        w.setObjectName("RightCommandPanel")
        w.setStyleSheet(f"""
            QFrame#RightCommandPanel {{
                background: rgba(3, 11, 21, 0.70);
                border: 1px solid rgba(40, 233, 255, 0.22);
                border-radius: 16px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        def _sec(txt, icon="▸"):
            row = QHBoxLayout(); row.setSpacing(8)
            ic = QLabel(icon)
            ic.setFixedWidth(18)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setFont(QFont("Segoe UI", 10, QFont.Weight.Black))
            ic.setStyleSheet(f"color: {C.PRI};")
            title = QLabel(txt)
            title.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
            title.setStyleSheet(f"color: {C.WHITE}; letter-spacing: 0.8px;")
            row.addWidget(ic); row.addWidget(title); row.addStretch()
            wrap = QWidget(); wrap.setLayout(row); wrap.setStyleSheet("background: transparent; border: none;")
            return wrap

        lay.addWidget(_sec("FRIDAY COMMAND LOG", "▣"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        lay.addWidget(_sec("INTELLIGENT FILE INPUT", "⌁"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click to analyze with FRIDAY")
        self._file_hint.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; padding-left: 4px;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        lay.addWidget(_sec("SECURITY CENTER QUICK LINKS", "✦"))
        lay.addWidget(self._build_security_center_quick_panel())

        lay.addWidget(_sec("FRIDAY SETTINGS", "⚙"))
        lay.addWidget(self._build_friday_settings_panel())

        lay.addWidget(_sec("DIRECT COMMAND", "⌲"))
        lay.addLayout(self._build_input_row())

        buttons = QHBoxLayout(); buttons.setSpacing(8)
        self._standby_btn = QPushButton("⏻  STANDBY MODE")
        self._standby_btn.setFixedHeight(34)
        self._standby_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        self._standby_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._standby_btn.clicked.connect(self._toggle_standby)
        self._style_standby_btn()
        buttons.addWidget(self._standby_btn)

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(34)
        self._mute_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        buttons.addWidget(self._mute_btn)
        lay.addLayout(buttons)

        self._camera_btn = QPushButton("")
        self._camera_btn.setFixedHeight(30)
        self._camera_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        self._camera_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._camera_btn.clicked.connect(self._toggle_camera_access)
        self._style_camera_btn()
        lay.addWidget(self._camera_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(30)
        fs_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(7, 24, 38, 0.82);
                color: {C.TEXT_MED};
                border: 1px solid rgba(40,233,255,0.24);
                border-radius: 11px;
            }}
            QPushButton:hover {{
                color: {C.PRI};
                border: 1px solid rgba(40,233,255,0.56);
                background: rgba(8, 34, 56, 0.92);
            }}
        """)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        return w

    def _run_security_center_quick(self, command: str, send_now: bool = True):
        try:
            self._input.setText(command)
            self._input.setFocus()
            if send_now:
                self._send()
        except Exception as e:
            try: self._log.append_log(f"ERR: Security Center quick command — {e}")
            except Exception: pass
    def _build_security_center_quick_panel(self) -> QWidget:
        box = QFrame()
        box.setObjectName("SecurityQuickPanel")
        box.setStyleSheet(f"""
            QFrame#SecurityQuickPanel {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(7, 24, 38, 0.94),
                    stop:0.62 rgba(4, 14, 25, 0.97),
                    stop:1 rgba(2, 8, 16, 0.98));
                border: 1px solid rgba(40, 233, 255, 0.28);
                border-radius: 17px;
            }}
            QLabel {{ background: transparent; border: none; }}
            QPushButton {{
                background: rgba(6, 22, 38, 0.88);
                color: {C.TEXT_MED};
                border: 1px solid rgba(40, 233, 255, 0.24);
                border-radius: 10px;
                padding: 6px 8px;
                text-align: left;
                font-weight: 800;
            }}
            QPushButton:hover {{
                color: {C.WHITE};
                border: 1px solid rgba(40, 233, 255, 0.62);
                background: rgba(9, 38, 61, 0.98);
            }}
        """)
        outer = QHBoxLayout(box)
        outer.setContentsMargins(13, 12, 13, 12)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(7)

        head = QLabel("SECURITY CENTER")
        head.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
        head.setStyleSheet(f"color: {C.ACC2}; letter-spacing: 1px;")
        hint = QLabel("Live MEDPOV threat intelligence")
        hint.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        left.addWidget(head)
        left.addWidget(hint)

        commands = [
            ("◉  Overview", "/sc overview", True),
            ("▲  Threats", "/sc threats", True),
            ("◇  Health", "/sc health", True),
            ("◎  Live", "/sc live", True),
            ("⌁  IP Profile", "/sc ip 65.55.210.207", False),
            ("✦  IP Analyze", "/sc analyze 65.55.210.207", False),
            ("⬢  IP Block", "/sc block 1.2.3.4", False),
            ("✓  Resolve Event", "/sc resolve-event 124", False),
        ]
        for idx in range(0, len(commands), 2):
            row = QHBoxLayout()
            row.setSpacing(8)
            for label, command, send_now in commands[idx:idx+2]:
                btn = QPushButton(label)
                btn.setFixedHeight(29)
                btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Black))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _=False, c=command, s=send_now: self._run_security_center_quick(c, s))
                row.addWidget(btn)
            left.addLayout(row)

        outer.addLayout(left, stretch=1)
        outer.addWidget(SecurityBadgeWidget(self), alignment=Qt.AlignmentFlag.AlignVCenter)
        return box

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask FRIDAY or type a command…")
        self._input.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._input.setFixedHeight(34)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(2, 12, 22, 0.92);
                color: {C.WHITE};
                border: 1px solid rgba(40,233,255,0.24);
                border-radius: 12px;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(40,233,255,0.72);
                background: rgba(5, 22, 36, 0.96);
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("➤")
        send.setFixedSize(34, 34)
        send.setFont(QFont("Segoe UI", 12, QFont.Weight.Black))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: rgba(40,233,255,0.10);
                color: {C.PRI};
                border: 1px solid rgba(40,233,255,0.42);
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background: rgba(40,233,255,0.22);
                color: {C.WHITE};
                border: 1px solid rgba(40,233,255,0.82);
            }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_footer(self) -> QWidget:
        w = QFrame()
        w.setFixedHeight(34)
        w.setObjectName("FridayFooter")
        w.setStyleSheet(f"""
            QFrame#FridayFooter {{
                background: rgba(3, 11, 21, 0.72);
                border: 1px solid rgba(40,233,255,0.20);
                border-bottom: none;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lay = QHBoxLayout(w); lay.setContentsMargins(16, 0, 16, 0); lay.setSpacing(14)

        def _fl(txt, color=C.TEXT_MED, weight=QFont.Weight.Bold):
            l = QLabel(txt); l.setFont(QFont("Segoe UI", 8, weight))
            l.setStyleSheet(f"color: {color};")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F6] Camera Toggle  ·  Map/Camera Buttons  ·  [F11] Fullscreen", C.TEXT_MED))
        lay.addStretch()
        lay.addWidget(_fl("© MEDPOV Technologies", C.TEXT_DIM))
        lay.addWidget(_fl("|", C.BORDER_A))
        lay.addWidget(_fl("FRIDAY AI COMMAND CENTER", C.WHITE, QFont.Weight.Black))
        lay.addWidget(_fl("|", C.BORDER_A))
        lay.addWidget(_fl("PRIVATE BUILD", C.TEXT_MED))
        lay.addStretch()
        lay.addWidget(_fl("v2.8.6", C.TEXT_DIM))
        lay.addWidget(_fl("⌁", C.PRI))
        lay.addWidget(_fl("ONLINE", C.GREEN, QFont.Weight.Black))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{icon}  {p.name}  ·  {size}  ·  Ready for FRIDAY analysis")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def _toggle_standby(self):
        self._set_standby(not self._standby)

    def _set_standby(self, enabled: bool):
        enabled = bool(enabled)
        if enabled:
            # Standby is not real mute. It only gates Gemini microphone input.
            if self._muted:
                self._muted = False
                self.hud.muted = False
                self._style_mute_btn()
            self._standby = True
            self._apply_state("STANDBY")
            self._log.append_log("SYS: Standby mode active. Typed commands still work. Say /wake or double clap to listen.")
        else:
            self._standby = False
            if not self._muted:
                self._apply_state("LISTENING")
            self._log.append_log("SYS: Listening mode active.")
        self._style_standby_btn()

    def _style_standby_btn(self):
        if self._standby:
            self._standby_btn.setText("▶  WAKE FRIDAY")
            self._standby_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(255,159,28,0.18); color: {C.ACC2}; border: 1px solid rgba(255,209,102,0.54); border-radius: 12px; }}
                QPushButton:hover {{ background: rgba(255,159,28,0.30); color: {C.WHITE}; }}
            """)
        else:
            self._standby_btn.setText("⏻  STANDBY MODE")
            self._standby_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(255,159,28,0.14); color: {C.ACC2}; border: 1px solid rgba(255,209,102,0.40); border-radius: 12px; }}
                QPushButton:hover {{ background: rgba(255,159,28,0.25); color: {C.WHITE}; }}
            """)

    def _toggle_mute(self):
        self._muted = not self._muted
        if self._muted:
            self._standby = False
        self.hud.muted = self._muted
        self._style_mute_btn()
        self._style_standby_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("STANDBY" if self._standby else "LISTENING")
            self._log.append_log("SYS: Microphone active." if not self._standby else "SYS: Microphone active, standby gate remains on.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(255,59,107,0.14); color: {C.RED}; border: 1px solid rgba(255,59,107,0.46); border-radius: 12px; }}
                QPushButton:hover {{ background: rgba(255,59,107,0.24); color: {C.WHITE}; }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(34,242,168,0.12); color: {C.GREEN}; border: 1px solid rgba(34,242,168,0.42); border-radius: 12px; }}
                QPushButton:hover {{ background: rgba(34,242,168,0.23); color: {C.WHITE}; }}
            """)

    def _camera_disabled_message(self) -> str:
        try:
            return str(get_friday_camera_disabled_message())
        except Exception:
            return _ui_text(
                "Camera access is currently disabled in FRIDAY settings. I cannot open the camera until Camera Access is enabled.",
                "Kamera şu anda FRIDAY ayarlarından devre dışı. Camera Access etkinleştirilmeden kamerayı açamam."
            )

    def _style_camera_btn(self):
        if not hasattr(self, "_camera_btn"):
            return
        if self._camera_access_enabled:
            self._camera_btn.setText("📷  CAMERA ENABLED  [F6]")
            self._camera_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(34,242,168,0.10); color: {C.GREEN}; border: 1px solid rgba(34,242,168,0.34); border-radius: 11px; }}
                QPushButton:hover {{ background: rgba(34,242,168,0.21); color: {C.WHITE}; }}
            """)
        else:
            self._camera_btn.setText("📷  CAMERA DISABLED  [F6]")
            self._camera_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(255,59,107,0.12); color: {C.RED}; border: 1px solid rgba(255,59,107,0.45); border-radius: 11px; }}
                QPushButton:hover {{ background: rgba(255,59,107,0.24); color: {C.WHITE}; }}
            """)

    def _toggle_camera_access(self):
        self._camera_access_enabled = not bool(getattr(self, "_camera_access_enabled", True))
        try:
            set_friday_camera_enabled(self._camera_access_enabled)
        except Exception as exc:
            self._log.append_log(f"ERR: Camera access setting could not be saved — {exc}")
        if not self._camera_access_enabled:
            try:
                self.stop_camera_mode()
            except Exception:
                pass
            self._log.append_log("SYS: Camera access disabled. Camera commands will be refused.")
        else:
            self._log.append_log("SYS: Camera access enabled.")
        self._style_camera_btn()

    def camera_access_enabled(self) -> bool:
        return bool(getattr(self, "_camera_access_enabled", True))

    def camera_disabled_message(self) -> str:
        return self._camera_disabled_message()

    def _open_camera_quick(self):
        """Open FRIDAY camera vision directly from the UI button."""
        if not self.camera_access_enabled():
            self._log.append_log("SYS: " + self._camera_disabled_message())
            return
        try:
            self.start_camera_mode()
            self._log.append_log("SYS: Camera quick button requested live vision.")
        except Exception as exc:
            self._log.append_log(f"ERR: Camera quick button failed — {exc}")

    def _open_security_map_quick(self):
        """Open the Security Center global map directly from the UI button."""
        try:
            self.start_security_map(mode="world", data={}, focus="")
            self._log.append_log("SYS: Map quick button requested global map.")
        except Exception as exc:
            self._log.append_log(f"ERR: Map quick button failed — {exc}")

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        if self._standby and not self._muted and state not in ("MUTED", "CAMERA"):
            state = "STANDBY"
        self.hud.state    = state
        self.hud.muted    = self._muted
        self.hud.speaking = (state == "SPEAKING")

    def start_camera_mode(self, camera_index: int | None = None) -> bool:
        if not self.camera_access_enabled():
            self._log.append_log("SYS: " + self._camera_disabled_message())
            return False
        self._camera_start_sig.emit(camera_index)
        return True

    def _start_camera_mode_now(self, camera_index=None):
        """
        Start camera view from the UI thread and make it win over the Security Map.
        Left-panel quick buttons stay in place; this only switches the main HUD.
        """
        # If the global map is open, close it before starting camera.
        # The V6 map paint hook can otherwise keep drawing the map over the live camera.
        try:
            if hasattr(self.hud, "security_map_is_open") and self.hud.security_map_is_open():
                self.hud.stop_security_map_mode()
        except Exception:
            try:
                self.hud.security_map_mode = False
            except Exception:
                pass

        already_online = False
        try:
            already_online = self.hud.camera_is_open()
        except Exception:
            already_online = False

        ok = self.hud.start_camera_mode(camera_index=camera_index)
        if ok:
            self._apply_state("CAMERA")
            # Aynı komut zincirinde start_camera_mode birden fazla çağrılabiliyor.
            # Kamera zaten açıksa logu tekrar basma; sağ panel temiz kalsın.
            if not already_online:
                self._log.append_log("SYS: CAMERA VISION online.")
        else:
            self._log.append_log(f"ERR: Kamera modu açılamadı — {self.hud._camera_error}")

    def stop_camera_mode(self):
        self._camera_stop_sig.emit()

    def _stop_camera_mode_now(self):
        was_online = False
        try:
            was_online = self.hud.camera_is_open()
        except Exception:
            was_online = False
        self.hud.stop_camera_mode()
        if was_online:
            self._log.append_log("SYS: CAMERA VISION offline.")

    def capture_camera_snapshot(self, wait_seconds: float = 1.0) -> tuple[bytes, str]:
        return self.hud.camera_snapshot(wait_seconds=wait_seconds)

    def camera_snapshot_ready(self) -> bool:
        try:
            return self.hud.camera_snapshot_ready()
        except Exception:
            return False

    def closeEvent(self, event):
        try:
            self.hud.stop_camera_capture_only()
        except Exception:
            pass
        try:
            if hasattr(self.hud, "stop_security_map_mode"):
                self.hud.stop_security_map_mode()
        except Exception:
            pass
        super().closeEvent(event)

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        key = str(key or "").strip()
        os_name = str(os_name or "windows").strip().lower()

        if not key:
            self._log.append_log("ERR: Gemini API key is required.")
            return

        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)

            # Ana kayıt noktası: helper varsa iki JSON'u da günceller.
            if save_gemini_api_key_everywhere is not None:
                save_gemini_api_key_everywhere(key, os_name)
            else:
                # Güvenli fallback: helper yüklenemezse yine de iki config dosyasını elle güncelle.
                api_data = {}
                if API_FILE.exists():
                    try:
                        api_data = json.loads(API_FILE.read_text(encoding="utf-8") or "{}")
                        if not isinstance(api_data, dict):
                            api_data = {}
                    except Exception:
                        api_data = {}

                api_data["gemini_api_key"] = key
                api_data["google_api_key"] = key
                api_data["GOOGLE_API_KEY"] = key
                api_data["os_system"] = os_name
                api_data.setdefault("friday_voice_name", "Aoede")
                api_data.setdefault("friday_voice_language", "tr-TR")
                api_data.setdefault("friday_voice_profile", "female_soft")
                api_data.setdefault("friday_character_gender", "female")
                api_data.setdefault("friday_response_language", "tr")
                api_data.setdefault(
                    "gemini_live_model",
                    "gemini-2.5-flash-native-audio-preview-12-2025"
                )

                API_FILE.write_text(
                    json.dumps(api_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                settings_file = CONFIG_DIR / "friday_settings.json"
                settings_data = {}
                if settings_file.exists():
                    try:
                        settings_data = json.loads(settings_file.read_text(encoding="utf-8") or "{}")
                        if not isinstance(settings_data, dict):
                            settings_data = {}
                    except Exception:
                        settings_data = {}

                settings_data.setdefault("voice", {})
                settings_data["voice"].setdefault("name", "Aoede")
                settings_data["voice"].setdefault("language", "tr-TR")
                settings_data["voice"].setdefault("character_gender", "female")

                settings_data.setdefault("assistant", {})
                settings_data["assistant"].setdefault("response_language", "tr")
                settings_data["assistant"].setdefault("ui_language", "en")
                settings_data.setdefault("privacy", {})
                settings_data["privacy"].setdefault("camera_enabled", True)

                settings_data.setdefault("gemini", {})
                settings_data["gemini"]["api_key"] = key
                settings_data["gemini"].setdefault(
                    "model",
                    "gemini-2.5-flash-native-audio-preview-12-2025"
                )

                settings_data.setdefault("security_center", {})
                settings_data["security_center"].setdefault(
                    "base_url",
                    "https://siteadi.com/security-center"
                )
                settings_data["security_center"].setdefault(
                    "api_url",
                    "https://siteadi.com/security-center/admin/api/remote-access.php"
                )
                settings_data["security_center"].setdefault("api_key", "")
                settings_data["security_center"].setdefault("timeout", 25)

                settings_file.write_text(
                    json.dumps(settings_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            if bootstrap_environment is not None:
                bootstrap_environment()

            self._ready = True

            if self._overlay:
                self._overlay.hide()
                self._overlay = None

            self._apply_state("LISTENING")
            self._log.append_log(f"SYS: Gemini API key saved. OS={os_name.upper()}. FRIDAY online.")

        except Exception as exc:
            self._log.append_log(f"ERR: Gemini API key save failed — {exc}")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class FridayUI:
    def __init__(self, face_path: str, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        self._win.show()
        self.root = _RootShim(self._app)

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def standby(self) -> bool:
        return bool(getattr(self._win, "_standby", False))

    @standby.setter
    def standby(self, v: bool):
        self.set_standby(v)

    def set_standby(self, enabled: bool):
        self._win._standby_sig.emit(bool(enabled))

    def camera_access_enabled(self) -> bool:
        try:
            return bool(self._win.camera_access_enabled())
        except Exception:
            return True

    def camera_disabled_message(self) -> str:
        try:
            return str(self._win.camera_disabled_message())
        except Exception:
            return "Camera access is currently disabled in FRIDAY settings."

    def set_camera_access(self, enabled: bool):
        current = self.camera_access_enabled()
        if bool(enabled) != current:
            self._win._toggle_camera_access()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if self.standby:
            self.set_state("STANDBY")
        elif not self.muted:
            self.set_state("LISTENING")

    def start_camera_mode(self, camera_index: int | None = None) -> bool:
        return self._win.start_camera_mode(camera_index=camera_index)

    def stop_camera_mode(self):
        self._win.stop_camera_mode()

    def capture_camera_snapshot(self, wait_seconds: float = 1.0) -> tuple[bytes, str]:
        return self._win.capture_camera_snapshot(wait_seconds=wait_seconds)

    def camera_snapshot_ready(self) -> bool:
        try:
            return self._win.camera_snapshot_ready()
        except Exception:
            return False


# Compatibility alias for the MEDPOV FRIDAY build.


# --- MEDPOV FRIDAY settings panel bridge ---
def _mp_friday_open_settings_dialog(self):
    try:
        from tools.friday_settings_dialog import FridaySettingsDialog
        dlg = FridaySettingsDialog(self)
        dlg.exec()
        try:
            if hasattr(self, "write_log"):
                self.write_log("FRIDAY: Settings updated. Restart is recommended for some changes.")
        except Exception:
            pass
    except Exception as e:
        try:
            if hasattr(self, "write_log"):
                self.write_log(f"ERR: Settings panel could not be opened — {e}")
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Settings", str(e))
        except Exception:
            print("FRIDAY settings dialog error:", e)


def _mp_friday_build_settings_panel(self):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout
    box = QFrame()
    try:
        border = getattr(C, "BORDER", "rgba(255,145,55,.30)")
        text = getattr(C, "TEXT_MED", "#d8ecff")
        dim = getattr(C, "TEXT_DIM", "#8da2b8")
        acc = getattr(C, "ACC2", "#ff9b36")
    except Exception:
        border, text, dim, acc = "rgba(255,145,55,.30)", "#d8ecff", "#8da2b8", "#ff9b36"
    box.setStyleSheet(f"""
        QFrame {{ background: rgba(20, 12, 5, 0.72); border: 1px solid {border}; border-radius: 12px; }}
        QLabel {{ background: transparent; border: none; }}
        QPushButton {{ background: #15110d; color: {text}; border: 1px solid rgba(255,145,55,.35); border-radius: 9px; padding: 7px 9px; text-align: left; }}
        QPushButton:hover {{ color: #ffbf75; border-color: #ff9b36; background: #21170e; }}
    """)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(6)
    head = QLabel("FRIDAY SETTINGS")
    head.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
    head.setStyleSheet(f"color:{acc};")
    info = QLabel("Voice · Security Center · Gemini")
    info.setFont(QFont("Courier New", 7))
    info.setStyleSheet(f"color:{dim};")
    btn = QPushButton("Open Settings")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda: self._open_friday_settings_dialog())
    lay.addWidget(head)
    lay.addWidget(info)
    lay.addWidget(btn)
    return box

try:
    FridayUI._open_friday_settings_dialog = _mp_friday_open_settings_dialog
    FridayUI._build_friday_settings_panel = _mp_friday_build_settings_panel
except NameError:
    try:
        MainWindow._open_friday_settings_dialog = _mp_friday_open_settings_dialog
        MainWindow._build_friday_settings_panel = _mp_friday_build_settings_panel
    except NameError:
        pass
# --- /MEDPOV FRIDAY settings panel bridge ---

# === MEDPOV FRIDAY UI V3 FILE INPUT + SECURITY BADGE FIX ===
# This block is intentionally appended and monkey-patches only the visual layer.
# It keeps the FRIDAY hologram/core logic untouched.

def _mpv3_panel_section(text: str) -> QLabel:
    lbl = QLabel(f"⌁  {text}")
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {C.WHITE};
            background: transparent;
            border: none;
            padding: 2px 0 2px 0;
            letter-spacing: 0.8px;
        }}
    """)
    return lbl


def _mpv3_drop_paint_idle(self, p, W, H, hover):
    """Cleaner file input idle state: all text stays inside the dashed border."""
    cx = W / 2
    rect = QRectF(10, 10, W - 20, H - 20)
    accent = C.PRI if hover else C.PRI_DIM

    # soft inner glow
    p.setPen(Qt.PenStyle.NoPen)
    glow = QRadialGradient(QPointF(cx, H * 0.46), max(W, H) * 0.48)
    glow.setColorAt(0.0, qcol(C.PRI, 34 if hover else 22))
    glow.setColorAt(0.58, qcol(C.PRI_DIM, 10))
    glow.setColorAt(1.0, qcol("#000000", 0))
    p.setBrush(QBrush(glow))
    p.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 12, 12)

    # upload icon lower and cleaner
    icon_y = H * 0.36
    p.setPen(QPen(qcol(accent, 220), 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(cx - 16, icon_y - 16, 32, 32), 9, 9)
    p.drawLine(QPointF(cx, icon_y + 8), QPointF(cx, icon_y - 9))
    p.drawLine(QPointF(cx - 8, icon_y - 1), QPointF(cx, icon_y - 9))
    p.drawLine(QPointF(cx + 8, icon_y - 1), QPointF(cx, icon_y - 9))

    # main text fully inside dashed area
    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(QPen(qcol(C.WHITE, 235), 1))
    p.drawText(
        QRectF(16, H * 0.53, W - 32, 20),
        Qt.AlignmentFlag.AlignCenter,
        "Drop file or click to analyze",
    )

    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(QPen(qcol(C.TEXT_DIM, 185), 1))
    p.drawText(
        QRectF(16, H * 0.68, W - 32, 18),
        Qt.AlignmentFlag.AlignCenter,
        "No file loaded  —  Images · PDF · Office · Code · Data · Media",
    )

    # tiny lower status rail
    p.setPen(QPen(qcol(C.PRI_DIM, 75), 1))
    p.drawLine(QPointF(W * 0.28, H - 18), QPointF(W * 0.72, H - 18))


def _mpv3_drop_paint_drag_over(self, p, W, H):
    cx = W / 2
    p.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    p.setPen(QPen(qcol(C.PRI, 245), 1))
    p.drawText(QRectF(0, H * 0.42, W, 24), Qt.AlignmentFlag.AlignCenter, "Release file to load")
    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(QPen(qcol(C.TEXT_MED, 200), 1))
    p.drawText(QRectF(0, H * 0.61, W, 18), Qt.AlignmentFlag.AlignCenter, "FRIDAY intelligent file input")
    p.setPen(QPen(qcol(C.PRI, 180), 2))
    p.drawEllipse(QPointF(cx, H * 0.32), 12, 12)


def _mpv3_drop_paint_file(self, p, W, H):
    path = Path(self._z._current_file or "")
    name = path.name if path.name else "Selected file"
    suffix = path.suffix.lstrip(".").upper() if path.suffix else "FILE"
    try:
        size = _fmt_size(path.stat().st_size) if path.exists() else "ready"
    except Exception:
        size = "ready"

    cat = _file_category(path)
    icon, color = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(qcol(color, 32)))
    p.drawRoundedRect(QRectF(18, 22, 54, 54), 14, 14)

    p.setFont(QFont("Segoe UI Emoji", 20, QFont.Weight.Bold))
    p.setPen(QPen(qcol(color, 245), 1))
    p.drawText(QRectF(18, 22, 54, 54), Qt.AlignmentFlag.AlignCenter, icon)

    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(QPen(qcol(C.WHITE, 235), 1))
    p.drawText(QRectF(82, 25, W - 98, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name[:46])

    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(QPen(qcol(C.TEXT_MED, 190), 1))
    p.drawText(QRectF(82, 49, W - 98, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{suffix}  ·  {size}  ·  Ready for FRIDAY analysis")

    p.setPen(QPen(qcol(C.GREEN, 180), 1))
    p.drawLine(QPointF(82, 76), QPointF(W - 20, 76))


try:
    _DropCanvas._paint_idle = _mpv3_drop_paint_idle
    _DropCanvas._paint_drag_over = _mpv3_drop_paint_drag_over
    _DropCanvas._paint_file = _mpv3_drop_paint_file
except Exception:
    pass


_MPV3_BADGE_PIXMAP_CACHE = {}


def _mpv3_remove_badge_white_halo(pix: QPixmap, size: int) -> QPixmap:
    """
    Security Center badge assetinin icindeki beyaz/pale dis konturlari
    panel uzerinde beyaz parlama gibi gorunuyordu. Burada sadece cok acik
    renkli konturlari MEDPOV cyan tonuna ceviriyoruz; arka plan tamamen
    transparent kalir.
    """
    cache_key = (str(BASE_DIR / "assets" / "medpov_security_badge.png"), int(size))
    cached = _MPV3_BADGE_PIXMAP_CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached

    scaled = pix.scaled(
        int(size),
        int(size),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    img = scaled.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    accent = QColor(C.PRI)

    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            a = c.alpha()
            if a <= 2:
                continue

            r, g, b = c.red(), c.green(), c.blue()

            # Beyaz anti-alias / dis kontur / pale glow pikselleri.
            is_white_halo = r >= 210 and g >= 210 and b >= 210
            is_pale_cyan_white = r >= 185 and g >= 215 and b >= 225

            if is_white_halo or is_pale_cyan_white:
                c.setRed(accent.red())
                c.setGreen(accent.green())
                c.setBlue(accent.blue())
                # Cok sert parlamasin; hologram hissi kalsin.
                c.setAlpha(max(55, min(a, 185)))
                img.setPixelColor(x, y, c)

    cleaned = QPixmap.fromImage(img)
    _MPV3_BADGE_PIXMAP_CACHE[cache_key] = cleaned
    return cleaned


def _mpv3_make_badge_label(size: int = 104) -> QLabel:
    badge = QLabel()
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setMinimumWidth(size + 8)
    badge.setStyleSheet("background: transparent; border: none;")
    try:
        asset = BASE_DIR / "assets" / "medpov_security_badge.png"
        pix = QPixmap(str(asset))
        if not pix.isNull():
            badge.setPixmap(_mpv3_remove_badge_white_halo(pix, size))
        else:
            badge.setText("🛡")
            badge.setFont(QFont("Segoe UI Emoji", 34, QFont.Weight.Bold))
            badge.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
    except Exception:
        badge.setText("🛡")
        badge.setFont(QFont("Segoe UI Emoji", 34, QFont.Weight.Bold))
        badge.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
    return badge


def _mpv3_build_security_center_quick_panel(self) -> QWidget:
    box = QFrame()
    box.setObjectName("MedpovSecurityQuickPanelV3")
    box.setStyleSheet(f"""
        QFrame#MedpovSecurityQuickPanelV3 {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 rgba(6, 18, 31, 0.98),
                stop:0.58 rgba(5, 15, 27, 0.96),
                stop:1 rgba(2, 10, 19, 0.98));
            border: 1px solid rgba(40, 233, 255, 0.28);
            border-radius: 18px;
        }}
        QFrame#MedpovSecurityQuickPanelV3 QLabel {{
            background: transparent;
            border: none;
        }}
        QFrame#MedpovSecurityQuickPanelV3 QPushButton {{
            background: rgba(8, 31, 50, 0.82);
            color: {C.TEXT_MED};
            border: 1px solid rgba(40, 233, 255, 0.24);
            border-radius: 9px;
            padding: 5px 8px;
            text-align: left;
            font-weight: 800;
        }}
        QFrame#MedpovSecurityQuickPanelV3 QPushButton:hover {{
            background: rgba(17, 62, 88, 0.92);
            color: {C.WHITE};
            border: 1px solid rgba(40, 233, 255, 0.70);
        }}
    """)

    outer = QHBoxLayout(box)
    outer.setContentsMargins(13, 12, 13, 12)
    outer.setSpacing(12)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(7)

    head = QLabel("SECURITY CENTER")
    head.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    head.setStyleSheet(f"color: {C.ACC2}; letter-spacing: 0.8px;")
    left.addWidget(head)

    hint = QLabel("Live MEDPOV threat intelligence")
    hint.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    hint.setStyleSheet(f"color: {C.TEXT_DIM};")
    left.addWidget(hint)

    commands = [
        ("◉ Overview", "/sc overview", True),
        ("▲ Threats", "/sc threats", True),
        ("◇ Health", "/sc health", True),
        ("◉ Live", "/sc live", True),
        ("⌁ IP Profile", "/sc ip 65.55.210.207", False),
        ("✦ IP Analyze", "/sc analyze 65.55.210.207", False),
        ("● IP Block", "/sc block 1.2.3.4", False),
        ("✓ Resolve Event", "/sc resolve-event 124", False),
    ]

    grid = QGridLayout()
    grid.setContentsMargins(0, 2, 0, 0)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(6)

    for i, (label, command, send_now) in enumerate(commands):
        btn = QPushButton(label)
        btn.setFixedHeight(27)
        btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, c=command, s=send_now: self._run_security_center_quick(c, s))
        grid.addWidget(btn, i // 2, i % 2)

    left.addLayout(grid)
    outer.addLayout(left, stretch=1)

    badge_wrap = QFrame()
    badge_wrap.setObjectName("MedpovSecurityBadgeWrap")
    badge_wrap.setStyleSheet(f"""
        QFrame#MedpovSecurityBadgeWrap {{
           
            border: none;
        }}
    """)
    badge_lay = QVBoxLayout(badge_wrap)
    badge_lay.setContentsMargins(0, 0, 0, 0)
    badge_lay.setSpacing(0)
    badge_lay.addStretch()
    badge_lay.addWidget(_mpv3_make_badge_label(110), alignment=Qt.AlignmentFlag.AlignCenter)
    badge_lay.addStretch()
    outer.addWidget(badge_wrap, stretch=0)

    return box


try:
    MainWindow._build_security_center_quick_panel = _mpv3_build_security_center_quick_panel
except Exception:
    pass


def _mpv3_build_right_panel(self) -> QWidget:
    w = QWidget()
    w.setFixedWidth(_RIGHT_W)
    w.setStyleSheet(f"""
        QWidget {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #04101e,
                stop:0.55 #030b15,
                stop:1 #020710);
            border-left: 1px solid rgba(40, 233, 255, 0.22);
        }}
    """)

    lay = QVBoxLayout(w)
    lay.setContentsMargins(13, 12, 13, 12)
    lay.setSpacing(9)

    lay.addWidget(_mpv3_panel_section("FRIDAY COMMAND LOG"))
    self._log = LogWidget()
    lay.addWidget(self._log, stretch=1)

    lay.addWidget(_mpv3_panel_section("INTELLIGENT FILE INPUT"))
    self._drop_zone = FileDropZone()
    self._drop_zone.setFixedHeight(112)
    self._drop_zone.file_selected.connect(self._on_file_selected)
    lay.addWidget(self._drop_zone)

    # kept for compatibility with _on_file_selected, but visual text now lives inside drop zone
    self._file_hint = QLabel("")
    self._file_hint.setVisible(False)

    lay.addWidget(_mpv3_panel_section("SECURITY CENTER QUICK LINKS"))
    lay.addWidget(self._build_security_center_quick_panel())

    lay.addWidget(_mpv3_panel_section("FRIDAY SETTINGS"))
    lay.addWidget(self._build_friday_settings_panel())

    lay.addWidget(_mpv3_panel_section("DIRECT COMMAND"))
    lay.addLayout(self._build_input_row())

    controls = QHBoxLayout()
    controls.setContentsMargins(0, 0, 0, 0)
    controls.setSpacing(8)

    self._standby_btn = QPushButton("⏻  STANDBY MODE")
    self._standby_btn.setFixedHeight(31)
    self._standby_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    self._standby_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self._standby_btn.clicked.connect(self._toggle_standby)
    self._style_standby_btn()
    controls.addWidget(self._standby_btn)

    self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
    self._mute_btn.setFixedHeight(31)
    self._mute_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self._mute_btn.clicked.connect(self._toggle_mute)
    self._style_mute_btn()
    controls.addWidget(self._mute_btn)

    lay.addLayout(controls)

    fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
    fs_btn.setFixedHeight(28)
    fs_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    fs_btn.setStyleSheet(f"""
        QPushButton {{
            background: rgba(7, 23, 37, 0.95);
            color: {C.TEXT_MED};
            border: 1px solid rgba(40, 233, 255, 0.28);
            border-radius: 10px;
        }}
        QPushButton:hover {{
            color: {C.WHITE};
            background: rgba(11, 46, 69, 0.95);
            border: 1px solid rgba(40, 233, 255, 0.72);
        }}
    """)
    fs_btn.clicked.connect(self._toggle_fullscreen)
    lay.addWidget(fs_btn)

    return w


try:
    MainWindow._build_right_panel = _mpv3_build_right_panel
except Exception:
    pass

# === /MEDPOV FRIDAY UI V3 FILE INPUT + SECURITY BADGE FIX ===




# === MEDPOV FRIDAY UI V4 RESPONSIVE CENTER CORE FIX ===
# Amaç:
# - Pencere daralınca FRIDAY çemberinin sağa taşmasını engeller.
# - Sol paneli dar ekranda otomatik gizler.
# - Sağ paneli kademeli küçültür.
# - Orta HUD çok dar kalırsa dikdörtgen "Command Core" moduna geçer.
# - Kamera modunu bozmaz.

try:
    _MPV4_ORIGINAL_MAIN_INIT = MainWindow.__init__
    _MPV4_ORIGINAL_MAIN_RESIZE = MainWindow.resizeEvent
    _MPV4_ORIGINAL_HUD_PAINT = HudCanvas.paintEvent
except Exception:
    _MPV4_ORIGINAL_MAIN_INIT = None
    _MPV4_ORIGINAL_MAIN_RESIZE = None
    _MPV4_ORIGINAL_HUD_PAINT = None


def _mpv4_hud_set_compact_core(self, enabled: bool):
    self._mpv4_compact_core = bool(enabled)
    try:
        self.update()
    except Exception:
        pass


def _mpv4_draw_responsive_command_core(self, p: QPainter, w: float, h: float):
    pal = self._pal()

    cx = w / 2.0
    cy = h / 2.0

    self._draw_background(p, w, h, cx, cy)

    panel_w = max(300.0, min(w - 36.0, 760.0))
    panel_h = max(260.0, min(h * 0.68, 430.0))

    panel = QRectF(
        (w - panel_w) / 2.0,
        (h - panel_h) / 2.0,
        panel_w,
        panel_h,
    )

    p.save()

    glow = QRadialGradient(QPointF(panel.center().x(), panel.center().y()), panel_w * 0.72)
    glow.setColorAt(0.00, self._q(pal["primary"], 76))
    glow.setColorAt(0.42, self._q(pal["primary"], 26))
    glow.setColorAt(1.00, self._q("#000000", 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawRoundedRect(panel.adjusted(-38, -42, 38, 42), 34, 34)

    base_grad = QLinearGradient(panel.left(), panel.top(), panel.right(), panel.bottom())
    base_grad.setColorAt(0.00, self._q("#04111e", 238))
    base_grad.setColorAt(0.45, self._q("#061827", 230))
    base_grad.setColorAt(1.00, self._q("#020711", 248))

    p.setPen(QPen(self._q(pal["primary"], 150), 1.4))
    p.setBrush(QBrush(base_grad))
    p.drawRoundedRect(panel, 24, 24)

    inner = panel.adjusted(18, 18, -18, -18)
    p.setPen(QPen(self._q(pal["primary"], 54), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(inner, 18, 18)

    scan_x = inner.left() + ((self._tick * 2.2) % max(1, int(inner.width())))
    scan = QLinearGradient(scan_x, inner.top(), scan_x, inner.bottom())
    scan.setColorAt(0.00, self._q(pal["primary"], 0))
    scan.setColorAt(0.50, self._q(pal["primary"], 105))
    scan.setColorAt(1.00, self._q(pal["primary"], 0))
    p.setPen(QPen(QBrush(scan), 2))
    p.drawLine(QPointF(scan_x, inner.top() + 8), QPointF(scan_x, inner.bottom() - 8))

    title_size = max(24, min(48, int(panel_w * 0.075)))
    p.setFont(QFont("Segoe UI", title_size, QFont.Weight.Black))
    p.setPen(self._q("#f5fcff", 235))
    p.drawText(
        QRectF(inner.left(), inner.top() + inner.height() * 0.28, inner.width(), 58),
        Qt.AlignmentFlag.AlignCenter,
        "F.R.I.D.A.Y",
    )

    p.setFont(QFont("Segoe UI", max(7, int(panel_w * 0.013)), QFont.Weight.Black))
    p.setPen(self._q(pal["primary"], 190))
    p.drawText(
        QRectF(inner.left(), inner.top() + inner.height() * 0.43, inner.width(), 22),
        Qt.AlignmentFlag.AlignCenter,
        "MEDPOV RESPONSIVE COMMAND CORE",
    )

    status_text = "SPEAKING" if bool(getattr(self, "speaking", False)) else pal["label"]
    p.setFont(QFont("Courier New", max(8, int(panel_w * 0.015)), QFont.Weight.Bold))
    p.setPen(self._q(pal["label_color"], 220))
    p.drawText(
        QRectF(inner.left(), inner.bottom() - 44, inner.width(), 28),
        Qt.AlignmentFlag.AlignCenter,
        f"◎ {status_text}",
    )

    # Üst ve alt data rail çizgileri
    rail_y_top = inner.top() + 22
    rail_y_bot = inner.bottom() - 22

    rail_grad = QLinearGradient(inner.left(), rail_y_top, inner.right(), rail_y_top)
    rail_grad.setColorAt(0.00, self._q(pal["primary"], 0))
    rail_grad.setColorAt(0.18, self._q(pal["primary"], 160))
    rail_grad.setColorAt(0.50, self._q(pal["secondary"], 230))
    rail_grad.setColorAt(0.82, self._q(pal["primary"], 160))
    rail_grad.setColorAt(1.00, self._q(pal["primary"], 0))

    p.setPen(QPen(QBrush(rail_grad), 3))
    p.drawLine(QPointF(inner.left() + 24, rail_y_top), QPointF(inner.right() - 24, rail_y_top))
    p.drawLine(QPointF(inner.left() + 24, rail_y_bot), QPointF(inner.right() - 24, rail_y_bot))

    # Ses / activity barları
    bar_count = 42
    bar_area_w = inner.width() * 0.78
    start_x = inner.center().x() - bar_area_w / 2.0
    base_y = inner.bottom() - 82

    meter = float(getattr(self, "_speech_meter", 0.0) or 0.0)
    if not bool(getattr(self, "speaking", False)):
        meter = max(meter, 0.18 + self._pulse * 0.18)

    for i in range(bar_count):
        phase = self._tick * 0.14 + i * 0.55
        amp = 0.28 + 0.72 * ((math.sin(phase) + 1.0) * 0.5)
        bar_h = 8 + amp * meter * 44
        x = start_x + i * (bar_area_w / max(1, bar_count - 1))
        alpha = 70 + int(amp * 130)
        p.setPen(QPen(self._q(pal["primary"], alpha), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x, base_y), QPointF(x, base_y - bar_h))

    # Sol / sağ teknik köşe blokları
    p.setPen(QPen(self._q(pal["primary"], 120), 2))
    corner = 42
    p.drawLine(QPointF(panel.left() + 18, panel.top() + 18), QPointF(panel.left() + corner, panel.top() + 18))
    p.drawLine(QPointF(panel.left() + 18, panel.top() + 18), QPointF(panel.left() + 18, panel.top() + corner))

    p.drawLine(QPointF(panel.right() - 18, panel.top() + 18), QPointF(panel.right() - corner, panel.top() + 18))
    p.drawLine(QPointF(panel.right() - 18, panel.top() + 18), QPointF(panel.right() - 18, panel.top() + corner))

    p.drawLine(QPointF(panel.left() + 18, panel.bottom() - 18), QPointF(panel.left() + corner, panel.bottom() - 18))
    p.drawLine(QPointF(panel.left() + 18, panel.bottom() - 18), QPointF(panel.left() + 18, panel.bottom() - corner))

    p.drawLine(QPointF(panel.right() - 18, panel.bottom() - 18), QPointF(panel.right() - corner, panel.bottom() - 18))
    p.drawLine(QPointF(panel.right() - 18, panel.bottom() - 18), QPointF(panel.right() - 18, panel.bottom() - corner))

    # Minik teknik etiketler
    p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
    p.setPen(self._q(pal["soft"], 95))
    p.drawText(QRectF(panel.left() + 24, panel.top() + 42, 180, 20), Qt.AlignmentFlag.AlignLeft, "CORE MODE // RESPONSIVE")
    p.drawText(QRectF(panel.right() - 210, panel.top() + 42, 186, 20), Qt.AlignmentFlag.AlignRight, "NO OVERFLOW // ACTIVE")

    p.restore()


def _mpv4_hud_paint_event(self, event):
    try:
        w = float(self.width())
        h = float(self.height())

        compact_forced = bool(getattr(self, "_mpv4_compact_core", False))
        compact_auto = (not bool(getattr(self, "camera_mode", False))) and (
            w < 560 or (w / max(1.0, h)) < 0.62
        )

        if compact_forced or compact_auto:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            _mpv4_draw_responsive_command_core(self, p, w, h)
            p.end()
            return
    except Exception:
        pass

    if _MPV4_ORIGINAL_HUD_PAINT:
        return _MPV4_ORIGINAL_HUD_PAINT(self, event)


def _mpv4_apply_responsive_layout(self):
    try:
        win_w = int(self.width())

        # Normal geniş ekran
        if win_w >= 1550:
            left_visible = True
            left_w = _LEFT_W
            right_w = _RIGHT_W
            hud_min_w = 520
            force_compact_core = False

        # Orta genişlik
        elif win_w >= 1320:
            left_visible = True
            left_w = 290
            right_w = 410
            hud_min_w = 460
            force_compact_core = False

        # Dar ekran: sol panel gizlenir, sağ panel korunur
        elif win_w >= 1120:
            left_visible = False
            left_w = 0
            right_w = 390
            hud_min_w = 500
            force_compact_core = False

        # Çok dar ekran: sağ panel küçülür, HUD dikdörtgen moda geçer
        else:
            left_visible = False
            left_w = 0
            right_w = 345
            hud_min_w = 360
            force_compact_core = True

        if hasattr(self, "_left_panel") and self._left_panel:
            self._left_panel.setVisible(left_visible)
            if left_visible:
                self._left_panel.setFixedWidth(left_w)

        if hasattr(self, "_right_panel") and self._right_panel:
            self._right_panel.setVisible(True)
            self._right_panel.setFixedWidth(right_w)

        if hasattr(self, "hud") and self.hud:
            self.hud.setMinimumWidth(hud_min_w)
            self.hud.setMinimumHeight(360)
            if hasattr(self.hud, "set_compact_core"):
                self.hud.set_compact_core(force_compact_core)

        # Pencere daralınca minimumu biraz gevşet.
        # Böylece Windows pencereyi sıkıştırırken layout boğulmaz.
        if win_w < 1120:
            self.setMinimumSize(960, 640)
        else:
            self.setMinimumSize(_MIN_W, _MIN_H)

    except Exception as exc:
        try:
            print("[FRIDAY UI] responsive layout error:", exc)
        except Exception:
            pass


def _mpv4_main_resize_event(self, event):
    if _MPV4_ORIGINAL_MAIN_RESIZE:
        _MPV4_ORIGINAL_MAIN_RESIZE(self, event)
    else:
        try:
            super(MainWindow, self).resizeEvent(event)
        except Exception:
            pass

    try:
        self._apply_responsive_layout()
    except Exception:
        pass


def _mpv4_main_init(self, *args, **kwargs):
    if _MPV4_ORIGINAL_MAIN_INIT:
        _MPV4_ORIGINAL_MAIN_INIT(self, *args, **kwargs)

    try:
        QTimer.singleShot(0, self._apply_responsive_layout)
        QTimer.singleShot(250, self._apply_responsive_layout)
    except Exception:
        pass


try:
    HudCanvas.set_compact_core = _mpv4_hud_set_compact_core
    HudCanvas.paintEvent = _mpv4_hud_paint_event

    MainWindow._apply_responsive_layout = _mpv4_apply_responsive_layout
    MainWindow.resizeEvent = _mpv4_main_resize_event
    MainWindow.__init__ = _mpv4_main_init
except Exception as _mpv4_patch_error:
    try:
        print("[FRIDAY UI] responsive patch install error:", _mpv4_patch_error)
    except Exception:
        pass

# === /MEDPOV FRIDAY UI V4 RESPONSIVE CENTER CORE FIX ===
# === MEDPOV FRIDAY UI V5 SPLIT SETTINGS + PC WORKSPACE PANEL ===
# Amaç:
# - Sağ paneldeki FRIDAY Settings kartını daraltıp ikiye böler.
# - Sol kart: FRIDAY AI/voice/security ayarları.
# - Sağ kart: PC Settings / trusted folders / backup workspace.


def _mpv5_open_pc_settings_dialog(self):
    try:
        from tools.friday_pc_settings_dialog import FridayPCSettingsDialog
        dlg = FridayPCSettingsDialog(self)
        dlg.exec()
        try:
            if hasattr(self, "write_log"):
                self.write_log("FRIDAY: PC Settings updated. Trusted folders and backup settings refreshed.")
        except Exception:
            pass
    except Exception as e:
        try:
            if hasattr(self, "write_log"):
                self.write_log(f"ERR: PC Settings panel could not be opened — {e}")
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "PC Settings", str(e))
        except Exception:
            print("FRIDAY PC settings dialog error:", e)


def _mpv5_build_mini_setting_card(title: str, desc: str, button_text: str, accent: str, on_click) -> QFrame:
    card = QFrame()
    card.setObjectName("Mpv5MiniSettingCard")
    card.setStyleSheet(f"""
        QFrame#Mpv5MiniSettingCard {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 rgba(7, 24, 38, 0.96),
                stop:1 rgba(5, 12, 22, 0.98));
            border: 1px solid rgba(40, 233, 255, 0.22);
            border-radius: 14px;
        }}
        QFrame#Mpv5MiniSettingCard QLabel {{
            background: transparent;
            border: none;
        }}
        QFrame#Mpv5MiniSettingCard QPushButton {{
            background: rgba(8, 31, 50, 0.82);
            color: #e8f8ff;
            border: 1px solid rgba(40, 233, 255, 0.28);
            border-radius: 9px;
            padding: 6px 8px;
            font-weight: 900;
        }}
        QFrame#Mpv5MiniSettingCard QPushButton:hover {{
            background: rgba(18, 55, 76, 0.98);
            border-color: {accent};
            color: #ffffff;
        }}
    """)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(6)

    head = QLabel(title)
    head.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    head.setStyleSheet(f"color:{accent}; letter-spacing:.7px;")
    head.setWordWrap(True)

    info = QLabel(desc)
    info.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    info.setStyleSheet(f"color:{C.TEXT_DIM};")
    info.setWordWrap(True)
    info.setMinimumHeight(34)

    btn = QPushButton(button_text)
    btn.setFixedHeight(28)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(on_click)

    lay.addWidget(head)
    lay.addWidget(info)
    lay.addStretch(1)
    lay.addWidget(btn)
    return card


def _mpv5_build_friday_settings_panel(self):
    box = QFrame()
    box.setObjectName("Mpv5SplitSettingsPanel")
    box.setStyleSheet(f"""
        QFrame#Mpv5SplitSettingsPanel {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 rgba(20, 12, 5, 0.60),
                stop:0.45 rgba(4, 18, 30, 0.92),
                stop:1 rgba(3, 10, 20, 0.98));
            border: 1px solid rgba(255, 184, 107, 0.24);
            border-radius: 16px;
        }}
        QFrame#Mpv5SplitSettingsPanel QLabel {{
            background: transparent;
            border: none;
        }}
    """)
    outer = QVBoxLayout(box)
    outer.setContentsMargins(10, 10, 10, 10)
    outer.setSpacing(8)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.setSpacing(8)

    left = _mpv5_build_mini_setting_card(
        "FRIDAY",
        "AI provider, voice, Security Center and model settings.",
        "Open Settings",
        getattr(C, "ACC2", "#ffb86b"),
        lambda _=False: self._open_friday_settings_dialog(),
    )
    right = _mpv5_build_mini_setting_card(
        "PC SETTINGS",
        "Trusted folders, backup, zip, notes, screenshot permissions.",
        "PC Settings",
        getattr(C, "PRI", "#28e9ff"),
        lambda _=False: self._open_pc_settings_dialog(),
    )
    top.addWidget(left, stretch=1)
    top.addWidget(right, stretch=1)
    outer.addLayout(top)

    status = QLabel("PC Workspace: add folders → FRIDAY can copy, zip, back up, take notes and capture screenshots.")
    status.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    status.setWordWrap(True)
    status.setStyleSheet(f"color:{C.TEXT_DIM}; padding: 0 2px 1px 2px;")
    outer.addWidget(status)
    return box


try:
    MainWindow._open_pc_settings_dialog = _mpv5_open_pc_settings_dialog
    MainWindow._build_friday_settings_panel = _mpv5_build_friday_settings_panel
except Exception as _mpv5_settings_patch_error:
    try:
        print("[FRIDAY UI] split settings patch install error:", _mpv5_settings_patch_error)
    except Exception:
        pass

# === /MEDPOV FRIDAY UI V5 SPLIT SETTINGS + PC WORKSPACE PANEL ===

# === MEDPOV FRIDAY UI V6 SECURITY CENTER GLOBAL MAP HUD ===
# Large AI-grade world map mode for Security Center map-intelligence data.

_MP_MAP_PLACES = {
    "turkiye": (39.0000, 35.0000, "Türkiye"), "turkey": (39.0000, 35.0000, "Türkiye"),
    "turkiye merkez": (39.0000, 35.0000, "Türkiye"), "turkey center": (39.0000, 35.0000, "Türkiye"),
    "ankara": (39.9334, 32.8597, "Ankara"), "izmir": (38.4237, 27.1428, "Izmir"),
    "bursa": (40.1828, 29.0665, "Bursa"), "antalya": (36.8969, 30.7133, "Antalya"),
    "london": (51.5072, -0.1276, "London"), "londra": (51.5072, -0.1276, "London"),
    "istanbul": (41.0082, 28.9784, "Istanbul"), "istanbul ac": (41.0082, 28.9784, "Istanbul"),
    "new york": (40.7128, -74.0060, "New York"), "newyork": (40.7128, -74.0060, "New York"),
    "los angeles": (34.0522, -118.2437, "Los Angeles"),
    "san francisco": (37.7749, -122.4194, "San Francisco"),
    "paris": (48.8566, 2.3522, "Paris"), "paris ac": (48.8566, 2.3522, "Paris"),
    "berlin": (52.5200, 13.4050, "Berlin"), "frankfurt": (50.1109, 8.6821, "Frankfurt"),
    "amsterdam": (52.3676, 4.9041, "Amsterdam"), "madrid": (40.4168, -3.7038, "Madrid"),
    "rome": (41.9028, 12.4964, "Rome"), "roma": (41.9028, 12.4964, "Rome"),
    "moscow": (55.7558, 37.6173, "Moscow"), "moskova": (55.7558, 37.6173, "Moscow"),
    "dubai": (25.2048, 55.2708, "Dubai"), "doha": (25.2854, 51.5310, "Doha"),
    "riyadh": (24.7136, 46.6753, "Riyadh"), "riyad": (24.7136, 46.6753, "Riyadh"),
    "tokyo": (35.6762, 139.6503, "Tokyo"), "tokio": (35.6762, 139.6503, "Tokyo"),
    "seoul": (37.5665, 126.9780, "Seoul"), "singapore": (1.3521, 103.8198, "Singapore"),
    "hong kong": (22.3193, 114.1694, "Hong Kong"), "mumbai": (19.0760, 72.8777, "Mumbai"),
    "delhi": (28.7041, 77.1025, "Delhi"), "sydney": (-33.8688, 151.2093, "Sydney"),
    "melbourne": (-37.8136, 144.9631, "Melbourne"), "sao paulo": (-23.5505, -46.6333, "São Paulo"),
    "são paulo": (-23.5505, -46.6333, "São Paulo"), "rio": (-22.9068, -43.1729, "Rio de Janeiro"),
    "toronto": (43.6532, -79.3832, "Toronto"), "vancouver": (49.2827, -123.1207, "Vancouver"),
    "mexico city": (19.4326, -99.1332, "Mexico City"), "meksika": (19.4326, -99.1332, "Mexico City"),
    "cairo": (30.0444, 31.2357, "Cairo"), "kahire": (30.0444, 31.2357, "Cairo"),
    "lagos": (6.5244, 3.3792, "Lagos"), "johannesburg": (-26.2041, 28.0473, "Johannesburg"),
}

_MP_MAP_CITY_LABELS = [
    (51.5072, -0.1276, "London"), (41.0082, 28.9784, "Istanbul"), (40.7128, -74.0060, "New York"),
    (34.0522, -118.2437, "Los Angeles"), (48.8566, 2.3522, "Paris"), (52.5200, 13.4050, "Berlin"),
    (55.7558, 37.6173, "Moscow"), (25.2048, 55.2708, "Dubai"), (35.6762, 139.6503, "Tokyo"),
    (1.3521, 103.8198, "Singapore"), (22.3193, 114.1694, "Hong Kong"), (-33.8688, 151.2093, "Sydney"),
    (-23.5505, -46.6333, "São Paulo"), (43.6532, -79.3832, "Toronto"), (30.0444, 31.2357, "Cairo"),
]

# Very lightweight vector land masses, enough for a premium offline map without WebEngine/tiles.
# Coordinates are lng, lat in rough equirectangular space.
_MP_LAND_POLYS = [
    [(-168, 72), (-142, 70), (-122, 62), (-105, 58), (-90, 50), (-72, 48), (-58, 56), (-52, 45), (-68, 25), (-84, 18), (-98, 16), (-117, 25), (-128, 36), (-150, 50), (-168, 72)],
    [(-82, 13), (-70, 10), (-55, 2), (-48, -12), (-57, -35), (-66, -55), (-76, -45), (-82, -20), (-82, 13)],
    [(-52, 84), (-20, 78), (16, 70), (40, 64), (32, 54), (10, 54), (-20, 60), (-48, 72), (-52, 84)],
    [(-10, 36), (3, 52), (30, 58), (60, 55), (95, 60), (130, 52), (150, 45), (160, 30), (135, 18), (105, 8), (80, 20), (52, 26), (34, 30), (26, 40), (8, 44), (-10, 36)],
    [(-17, 36), (8, 35), (30, 30), (44, 12), (38, -20), (24, -35), (8, -34), (-5, -18), (-12, 8), (-17, 36)],
    [(68, 23), (86, 28), (94, 20), (82, 8), (74, 8), (68, 23)],
    [(99, 20), (112, 18), (121, 8), (116, -6), (104, -8), (97, 6), (99, 20)],
    [(128, -12), (146, -16), (154, -30), (145, -43), (126, -38), (113, -25), (128, -12)],
    [(35, 32), (49, 28), (56, 18), (48, 12), (40, 20), (35, 32)],
    [(138, 42), (146, 41), (145, 35), (139, 34), (138, 42)],
]



# Dashboard-grade real map tiles (same visual source family as Security Center Leaflet dashboard).
# Tiles are downloaded once and cached locally, so the map keeps working after first load.
_MP_TILE_SIZE = 256
_MP_TILE_PROVIDER = "carto_dark"
_MP_TILE_SUBDOMAINS = ("a", "b", "c", "d")
_MP_TILE_PENDING = set()
_MP_TILE_LOCK = threading.Lock()
_MP_TILE_CACHE_DIR = BASE_DIR / "cache" / "map_tiles" / _MP_TILE_PROVIDER
_MP_MERCATOR_MAX_LAT = 85.05112878


def _mp_map_tile_zoom(self) -> int:
    _mp_map_init(self)
    visual_zoom = float(getattr(self, "_security_map_zoom", 1.0) or 1.0)
    if visual_zoom >= 4.0:
        return 5
    if visual_zoom >= 2.2:
        return 4
    if visual_zoom >= 1.25:
        return 3
    return 2


def _mp_map_clip_lat(lat: float) -> float:
    return max(-_MP_MERCATOR_MAX_LAT, min(_MP_MERCATOR_MAX_LAT, float(lat)))


def _mp_map_latlng_to_world_px(lat: float, lng: float, z: int) -> QPointF:
    lat = _mp_map_clip_lat(lat)
    lng = float(lng)
    scale = _MP_TILE_SIZE * (2 ** int(z))
    x = (lng + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return QPointF(x, y)


def _mp_map_norm_lng(lng: float) -> float:
    lng = float(lng)
    while lng > 180.0:
        lng -= 360.0
    while lng < -180.0:
        lng += 360.0
    return lng


def _mp_map_world_px_to_latlng(point: QPointF, z: int):
    scale = _MP_TILE_SIZE * (2 ** int(z))
    x = float(point.x()) % scale
    y = max(0.0, min(scale, float(point.y())))

    lng = (x / scale) * 360.0 - 180.0
    merc = math.pi - (2.0 * math.pi * y / scale)
    lat = math.degrees(math.atan(math.sinh(merc)))
    return _mp_map_clip_lat(lat), _mp_map_norm_lng(lng)


def _mp_map_widget_rect(self) -> QRectF:
    return QRectF(18, 24, max(80, float(self.width()) - 36), max(80, float(self.height()) - 48))


def _mp_map_event_pos(event) -> QPointF:
    try:
        return QPointF(event.position())
    except Exception:
        try:
            return QPointF(event.pos())
        except Exception:
            return QPointF(0, 0)


def _mp_map_screen_to_latlng(self, pos: QPointF, rect: QRectF):
    try:
        z = _mp_map_tile_zoom(self)
        center_lat, center_lng = getattr(self, "_security_map_center", (18.0, 28.0))
        center_px = _mp_map_latlng_to_world_px(float(center_lat), float(center_lng), z)

        world_px = QPointF(
            center_px.x() + (float(pos.x()) - rect.center().x()),
            center_px.y() + (float(pos.y()) - rect.center().y()),
        )

        return _mp_map_world_px_to_latlng(world_px, z)
    except Exception:
        return None


def _mp_map_tile_path(z: int, x: int, y: int) -> Path:
    return _MP_TILE_CACHE_DIR / str(int(z)) / str(int(x)) / f"{int(y)}.png"


def _mp_map_schedule_tile_download(widget, z: int, x: int, y: int, path: Path) -> None:
    key = (int(z), int(x), int(y))
    with _MP_TILE_LOCK:
        if key in _MP_TILE_PENDING:
            return
        _MP_TILE_PENDING.add(key)

    def _worker():
        try:
            sub = _MP_TILE_SUBDOMAINS[(x + y) % len(_MP_TILE_SUBDOMAINS)]
            url = f"https://{sub}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            from urllib.request import Request, urlopen
            req = Request(url, headers={"User-Agent": "MEDPOV-FRIDAY-SecurityMap/2.8"})
            with urlopen(req, timeout=9) as resp:
                data = resp.read()
            if data:
                tmp.write_bytes(data)
                tmp.replace(path)
        except Exception:
            pass
        finally:
            with _MP_TILE_LOCK:
                _MP_TILE_PENDING.discard(key)
            try:
                widget.update()
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()


def _mp_map_draw_real_tiles(self, p: QPainter, rect: QRectF) -> int:
    """Draw real dashboard-like dark world tiles. Returns loaded tile count."""
    _mp_map_init(self)
    z = _mp_map_tile_zoom(self)
    n = 2 ** z
    center_lat, center_lng = getattr(self, "_security_map_center", (18.0, 28.0))
    center_px = _mp_map_latlng_to_world_px(float(center_lat), float(center_lng), z)

    left_world = center_px.x() - rect.width() / 2.0
    top_world = center_px.y() - rect.height() / 2.0
    right_world = center_px.x() + rect.width() / 2.0
    bottom_world = center_px.y() + rect.height() / 2.0

    start_tx = int(math.floor(left_world / _MP_TILE_SIZE)) - 1
    end_tx = int(math.floor(right_world / _MP_TILE_SIZE)) + 1
    start_ty = max(0, int(math.floor(top_world / _MP_TILE_SIZE)) - 1)
    end_ty = min(n - 1, int(math.floor(bottom_world / _MP_TILE_SIZE)) + 1)

    loaded = 0
    p.save()
    p.setClipRect(rect)

    # Tile placeholder glow while the real map downloads.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(qcol("#050a12", 235)))
    p.drawRect(rect)

    for ty in range(start_ty, end_ty + 1):
        for tx_raw in range(start_tx, end_tx + 1):
            tx = tx_raw % n
            path = _mp_map_tile_path(z, tx, ty)
            sx = rect.center().x() + (tx_raw * _MP_TILE_SIZE - center_px.x())
            sy = rect.center().y() + (ty * _MP_TILE_SIZE - center_px.y())
            tile_rect = QRectF(sx, sy, _MP_TILE_SIZE + 1, _MP_TILE_SIZE + 1)

            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    p.drawPixmap(tile_rect, pix, QRectF(0, 0, pix.width(), pix.height()))
                    loaded += 1
                    continue

            # Soft placeholder tile grid while the image is not cached yet.
            p.setPen(QPen(qcol(C.PRI, 16), 1))
            p.setBrush(QBrush(qcol("#06111d", 190)))
            p.drawRect(tile_rect)
            _mp_map_schedule_tile_download(self, z, tx, ty, path)

    # Dashboard-style darkening and cyan/red atmosphere overlay.
    shade = QLinearGradient(rect.topLeft(), rect.bottomRight())
    shade.setColorAt(0.00, qcol("#00050a", 95))
    shade.setColorAt(0.45, qcol("#00131a", 42))
    shade.setColorAt(1.00, qcol("#050006", 105))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(shade))
    p.drawRect(rect)

    # If there is no internet/cache yet, keep a recognisable vector fallback under the HUD.
    if loaded == 0:
        _mp_map_draw_land(self, p, rect)
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(qcol(C.TEXT_DIM, 170))
        p.drawText(
            QRectF(rect.left() + 24, rect.bottom() - 28, rect.width() - 48, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Real dashboard map tiles are loading and will be cached locally."
        )

    p.restore()
    return loaded

def _mp_map_norm_place(value: str) -> str:
    value = (value or "").lower().strip()
    value = value.translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    value = value.replace("'", " ").replace("’", " ")
    for word in ("ac", "aç", "zoom", "yap", "git", "goster", "göster", "harita", "map", "open", "to", "go", "konumuna", "odaklan"):
        value = value.replace(word, " ")
    return " ".join(value.split())


def _mp_map_init(self):
    if not hasattr(self, "security_map_mode"):
        self.security_map_mode = False
    if not hasattr(self, "_security_map_data"):
        self._security_map_data = {}
    if not hasattr(self, "_security_map_active_mode"):
        self._security_map_active_mode = "world"
    if not hasattr(self, "_security_map_center"):
        self._security_map_center = (18.0, 28.0)  # lat, lng
    if not hasattr(self, "_security_map_zoom"):
        self._security_map_zoom = 1.0
    if not hasattr(self, "_security_map_focus_label"):
        self._security_map_focus_label = "World"
    if not hasattr(self, "_security_map_notice"):
        self._security_map_notice = "World intelligence map ready."
    if not hasattr(self, "_security_map_dragging"):
        self._security_map_dragging = False
    if not hasattr(self, "_security_map_drag_last"):
        self._security_map_drag_last = None


def _mp_map_find_place(place: str):
    q = _mp_map_norm_place(place)
    if not q:
        return None
    if q in _MP_MAP_PLACES:
        return _MP_MAP_PLACES[q]
    for key, value in _MP_MAP_PLACES.items():
        if key in q or q in key:
            return value
    return None


def _mp_map_start(self, mode="world", map_data=None, focus=""):
    _mp_map_init(self)
    self.security_map_mode = True
    try:
        self.stop_camera_capture_only()
    except Exception:
        pass
    self.camera_mode = False
    self.state = "MAP"
    self._security_map_active_mode = (mode or "world").lower().strip()
    self._security_map_data = map_data if isinstance(map_data, dict) else {}
    self._security_map_notice = "Security Center map intelligence loaded." if self._security_map_data else "World intelligence map ready."
    place = _mp_map_find_place(focus)
    if place:
        lat, lng, label = place
        self._security_map_center = (lat, lng)
        self._security_map_zoom = 4.8
        self._security_map_focus_label = label
    elif self._security_map_data.get("target") and self._security_map_active_mode in {"threat", "live", "both"}:
        target = self._security_map_data.get("target") or {}
        try:
            self._security_map_center = (float(target.get("lat", 28.0)), float(target.get("lng", 18.0)))
            self._security_map_zoom = 1.85
            self._security_map_focus_label = str(target.get("url") or target.get("label") or "Protected target")
        except Exception:
            self._security_map_center = (18.0, 28.0)
            self._security_map_zoom = 1.0
            self._security_map_focus_label = "World"
    else:
        self._security_map_center = (18.0, 28.0)
        self._security_map_zoom = 1.0
        self._security_map_focus_label = "World"
    self.update()
    return True


def _mp_map_stop(self):
    _mp_map_init(self)
    self.security_map_mode = False
    self._security_map_data = {}
    self._security_map_active_mode = "world"
    self.state = "IDLE"
    self.update()


def _mp_map_focus(self, place: str):
    _mp_map_init(self)
    hit = _mp_map_find_place(place)
    if not hit:
        self._security_map_notice = f"Unknown focus target: {place}"
        self.update()
        return False
    lat, lng, label = hit
    self.security_map_mode = True
    self.camera_mode = False
    self.state = "MAP"
    self._security_map_center = (float(lat), float(lng))
    self._security_map_zoom = 4.2 if str(label).lower() in {"türkiye", "turkiye", "turkey"} else 5.2
    self._security_map_focus_label = label
    self._security_map_notice = f"Focused on {label}."
    self.update()
    return True


def _mp_map_is_open(self):
    return bool(getattr(self, "security_map_mode", False))


def _mp_map_project(self, lat, lng, rect: QRectF):
    """Project lat/lng using Web Mercator so markers align with dashboard map tiles."""
    _mp_map_init(self)
    z = _mp_map_tile_zoom(self)
    center_lat, center_lng = self._security_map_center
    center_px = _mp_map_latlng_to_world_px(float(center_lat), float(center_lng), z)
    point_px = _mp_map_latlng_to_world_px(float(lat), float(lng), z)

    world = _MP_TILE_SIZE * (2 ** z)
    dx = point_px.x() - center_px.x()
    # Choose the nearest wrapped world copy, like Leaflet worldCopyJump.
    if dx > world / 2:
        dx -= world
    elif dx < -world / 2:
        dx += world

    dy = point_px.y() - center_px.y()
    x = rect.center().x() + dx
    y = rect.center().y() + dy
    return QPointF(x, y)

def _mp_map_on_screen(pt: QPointF, rect: QRectF, margin: float = 80.0) -> bool:
    return (rect.left() - margin) <= pt.x() <= (rect.right() + margin) and (rect.top() - margin) <= pt.y() <= (rect.bottom() + margin)


def _mp_map_draw_grid(self, p: QPainter, rect: QRectF):
    p.save()
    p.setClipRect(rect)
    p.setPen(QPen(qcol(C.PRI, 34), 1))
    for lng in range(-180, 181, 30):
        a = _mp_map_project(self, -75, lng, rect)
        b = _mp_map_project(self, 75, lng, rect)
        p.drawLine(a, b)
    for lat in range(-60, 81, 20):
        a = _mp_map_project(self, lat, -180, rect)
        b = _mp_map_project(self, lat, 180, rect)
        p.drawLine(a, b)
    p.restore()


def _mp_map_draw_land(self, p: QPainter, rect: QRectF):
    p.save()
    p.setClipRect(rect)
    for poly in _MP_LAND_POLYS:
        path = QPainterPath()
        first = True
        for lng, lat in poly:
            pt = _mp_map_project(self, lat, lng, rect)
            if first:
                path.moveTo(pt)
                first = False
            else:
                path.lineTo(pt)
        path.closeSubpath()
        p.setPen(QPen(qcol("#2b526b", 85), 1.0))
        p.setBrush(QBrush(qcol("#122a34", 185)))
        p.drawPath(path)
    p.restore()


def _mp_map_risk_color(risk: str, kind: str = "threat") -> str:
    if kind == "live":
        return C.GREEN
    risk = (risk or "").lower()
    if "critical" in risk:
        return C.RED
    if "high" in risk:
        return "#ff6b35"
    if "medium" in risk:
        return "#ffd166"
    return C.PRI


def _mp_map_extract_points(self, kind: str):
    data = getattr(self, "_security_map_data", {}) or {}
    layers = data.get("layers") if isinstance(data, dict) else {}
    layer = (layers or {}).get(kind) if isinstance(layers, dict) else {}
    points = layer.get("points") if isinstance(layer, dict) else None
    if points:
        return [x for x in points if isinstance(x, dict)]
    key = "threat_events" if kind == "threat" else "live_users"
    return [x for x in (data.get(key) or []) if isinstance(x, dict)] if isinstance(data, dict) else []


def _mp_map_extract_traces(self, kind: str):
    data = getattr(self, "_security_map_data", {}) or {}
    layers = data.get("layers") if isinstance(data, dict) else {}
    layer = (layers or {}).get(kind) if isinstance(layers, dict) else {}
    traces = layer.get("traces") if isinstance(layer, dict) else None
    if traces:
        return [x for x in traces if isinstance(x, dict)]
    traces_root = data.get("traces") if isinstance(data, dict) else {}
    return [x for x in ((traces_root or {}).get(kind) or []) if isinstance(x, dict)] if isinstance(traces_root, dict) else []


def _mp_map_draw_trace(self, p: QPainter, rect: QRectF, trace: dict, kind: str):
    """Draw a Security Center trace, clipped strictly inside the map rectangle."""
    p.save()
    p.setClipRect(rect.adjusted(1, 1, -1, -1))

    try:
        style = trace.get("style") or {}
        color = style.get("color") or (C.GREEN if kind == "live" else C.ACC)
        opacity = int(225 * float(style.get("opacity", .78) or .78))
        width = float(style.get("weight", 2) or 2)

        pen = QPen(
            qcol(str(color), opacity),
            max(1.2, width),
            Qt.PenStyle.DashLine,
            Qt.PenCapStyle.RoundCap,
        )
        p.setPen(pen)

        curve_points = trace.get("curve_points") or []
        path = QPainterPath()
        has_path = False

        if isinstance(curve_points, list) and len(curve_points) >= 2:
            for idx, pair in enumerate(curve_points):
                try:
                    lat, lng = float(pair[0]), float(pair[1])
                except Exception:
                    continue

                pt = _mp_map_project(self, lat, lng, rect)
                if idx == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
                has_path = True
        else:
            src = trace.get("from") or {}
            dst = trace.get("to") or {}
            try:
                p1 = _mp_map_project(self, float(src.get("lat")), float(src.get("lng")), rect)
                p2 = _mp_map_project(self, float(dst.get("lat")), float(dst.get("lng")), rect)
                mid = QPointF(
                    (p1.x() + p2.x()) / 2,
                    (p1.y() + p2.y()) / 2 - abs(p2.x() - p1.x()) * 0.16,
                )
                path.moveTo(p1)
                path.quadTo(mid, p2)
                has_path = True
            except Exception:
                has_path = False

        if has_path:
            p.drawPath(path)
    finally:
        p.restore()


def _mp_map_draw_point(self, p: QPainter, rect: QRectF, item: dict, kind: str, index: int):
    try:
        lat, lng = float(item.get("lat")), float(item.get("lng"))
    except Exception:
        return
    pt = _mp_map_project(self, lat, lng, rect)
    if not _mp_map_on_screen(pt, rect, 60):
        return
    source = item.get("source") if isinstance(item.get("source"), dict) else item
    risk = str(source.get("risk") or item.get("risk") or "LOW")
    color = _mp_map_risk_color(risk, kind)
    pulse = (math.sin((getattr(self, "_tick", 0) * 0.18) + index) + 1) * .5
    radius = 5.5 + pulse * 2.4
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(qcol(color, 35)))
    p.drawEllipse(pt, radius * 4.0, radius * 4.0)
    p.setBrush(QBrush(qcol(color, 92)))
    p.drawEllipse(pt, radius * 2.1, radius * 2.1)
    p.setBrush(QBrush(qcol(color, 236)))
    p.drawEllipse(pt, radius, radius)
    p.setPen(QPen(qcol("#eaffff", 210), 1.3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(pt, radius + 3.6, radius + 3.6)
    if float(getattr(self, "_security_map_zoom", 1.0) or 1.0) > 2.6 or index < 16:
        label = str(source.get("city") or source.get("label") or source.get("country") or source.get("ip") or "")[:22]
        if label:
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.setPen(qcol("#dff8ff", 190))
            p.drawText(QRectF(pt.x() + 9, pt.y() - 10, 140, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)


def _mp_map_draw_target(self, p: QPainter, rect: QRectF):
    data = getattr(self, "_security_map_data", {}) or {}
    target = data.get("target") if isinstance(data, dict) else None
    if not isinstance(target, dict):
        # Default MEDPOV target hint near Istanbul when no live API payload exists.
        target = {"lat": 41.0082, "lng": 28.9784, "url": "medpov.com"}
    try:
        pt = _mp_map_project(self, float(target.get("lat")), float(target.get("lng")), rect)
    except Exception:
        return
    if not _mp_map_on_screen(pt, rect, 80):
        return
    pulse = (math.sin(getattr(self, "_tick", 0) * .12) + 1) * .5
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(qcol(C.PRI, 48)))
    p.drawEllipse(pt, 20 + pulse * 9, 20 + pulse * 9)
    p.setBrush(QBrush(qcol(C.PRI, 220)))
    p.drawEllipse(pt, 7.0, 7.0)
    p.setPen(QPen(qcol("#ffffff", 220), 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(pt, 11.5, 11.5)
    label = str(target.get("url") or target.get("label") or "Protected website")
    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(qcol("#ffffff", 225))
    p.drawText(QRectF(pt.x() + 14, pt.y() - 14, 190, 28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label[:28])


def _mp_map_draw_city_labels(self, p: QPainter, rect: QRectF):
    p.save()
    p.setClipRect(rect)
    zoom = float(getattr(self, "_security_map_zoom", 1.0) or 1.0)
    p.setFont(QFont("Segoe UI", 7 if zoom < 2 else 8, QFont.Weight.Bold))
    for idx, (lat, lng, label) in enumerate(_MP_MAP_CITY_LABELS):
        pt = _mp_map_project(self, lat, lng, rect)
        if not _mp_map_on_screen(pt, rect, 20):
            continue
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.PRI, 118)))
        p.drawEllipse(pt, 2.7, 2.7)
        if zoom > 1.35 or idx < 8:
            p.setPen(qcol("#a7c6d8", 158))
            p.drawText(QRectF(pt.x() + 5, pt.y() - 8, 110, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
    p.restore()


def _mp_map_draw_threat_legend(self, p: QPainter, rect: QRectF):
    """Draw Threat Level legend with auto height so Critical never overflows."""
    items = [
        (C.GREEN, "Live User"),
        (C.PRI, "Low"),
        (C.ACC2, "Medium"),
        ("#ff6b35", "High"),
        (C.RED, "Critical"),
    ]

    box_w = 176.0
    pad_x = 18.0
    title_h = 18.0
    title_top = 13.0
    first_row_y = title_top + title_h + 19.0
    row_gap = 22.0
    bottom_pad = 22.0
    box_h = first_row_y + (len(items) * row_gap) + bottom_pad - 6.0

    leg = QRectF(
        rect.left() + 18.0,
        rect.bottom() - box_h - 20.0,
        box_w,
        box_h,
    )

    p.save()
    p.setPen(QPen(qcol(C.PRI, 78), 1))
    p.setBrush(QBrush(qcol("#061421", 226)))
    p.drawRoundedRect(leg, 14, 14)

    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(qcol("#ffffff", 235))
    p.drawText(
        QRectF(leg.left() + pad_x, leg.top() + title_top, leg.width() - pad_x * 2, title_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "Threat Level",
    )

    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    y = leg.top() + first_row_y
    for color, label in items:
        dot = QPointF(leg.left() + pad_x + 5, y + 7)

        glow = QRadialGradient(dot, 10)
        glow.setColorAt(0, qcol(color, 145))
        glow.setColorAt(1, qcol(color, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(dot, 10, 10)

        p.setBrush(QBrush(qcol(color, 240)))
        p.drawEllipse(dot, 4.2, 4.2)

        p.setPen(qcol(C.TEXT, 222))
        p.drawText(
            QRectF(leg.left() + pad_x + 21, y - 2, leg.width() - pad_x * 2 - 24, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        y += row_gap

    p.restore()


def _mp_map_draw_hud_panel(self, p: QPainter, rect: QRectF, w: float, h: float):
    data = getattr(self, "_security_map_data", {}) or {}
    mode = str(getattr(self, "_security_map_active_mode", "world") or "world").upper()
    counts = data.get("counts") if isinstance(data, dict) else {}
    threat_count = counts.get("threats") if isinstance(counts, dict) else None
    user_count = counts.get("live_users") if isinstance(counts, dict) else None
    if threat_count is None:
        threat_count = len(_mp_map_extract_points(self, "threat"))
    if user_count is None:
        user_count = len(_mp_map_extract_points(self, "live"))
    updated = ""
    if isinstance(data, dict):
        updated = str(data.get("updated_at") or data.get("server_time") or "")

    # Top left map badge.
    badge = QRectF(rect.left() + 18, rect.top() + 16, 365, 76)
    p.setPen(QPen(qcol(C.PRI, 78), 1))
    p.setBrush(QBrush(qcol("#061421", 214)))
    p.drawRoundedRect(badge, 13, 13)
    p.setFont(QFont("Segoe UI", 10, QFont.Weight.Black))
    p.setPen(qcol("#ffffff", 235))
    p.drawText(QRectF(badge.left() + 16, badge.top() + 11, badge.width() - 28, 22), Qt.AlignmentFlag.AlignLeft, "GLOBAL SECURITY MAP")
    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(qcol(C.TEXT_MED, 210))
    p.drawText(QRectF(badge.left() + 16, badge.top() + 35, badge.width() - 28, 18), Qt.AlignmentFlag.AlignLeft, f"MODE {mode}  ·  FOCUS {getattr(self, '_security_map_focus_label', 'World')}")
    p.setPen(qcol(C.TEXT_DIM, 205))
    p.drawText(QRectF(badge.left() + 16, badge.top() + 53, badge.width() - 28, 18), Qt.AlignmentFlag.AlignLeft, str(getattr(self, "_security_map_notice", ""))[:68])

    # Legend. Auto-height fixes the Critical row overflow.
    _mp_map_draw_threat_legend(self, p, rect)

    # Bottom status pill. It is moved left so the mini FRIDAY hologram can sit at bottom-right.
    mini_reserve = max(230.0, min(float(w), float(h)) * 0.30)
    desired_w = 420 if mode == "BOTH" else 340
    max_w = max(260.0, rect.width() - 240.0 - mini_reserve)
    pill_w = min(float(desired_w), max_w)
    pill_x = rect.right() - mini_reserve - pill_w - 18
    pill_x = max(rect.left() + 206, pill_x)
    pill = QRectF(pill_x, rect.bottom() - 54, pill_w, 34)

    p.setPen(QPen(qcol(C.PRI, 82), 1))
    p.setBrush(QBrush(qcol("#061421", 226)))
    p.drawRoundedRect(pill, 13, 13)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(qcol(C.GREEN if mode in {"LIVE", "BOTH"} else C.ACC, 235)))
    p.drawEllipse(QPointF(pill.left() + 18, pill.center().y()), 4.2, 4.2)
    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(qcol("#eaf8ff", 225))
    status = f"Map lines active · Threats: {threat_count} · Users: {user_count}"
    if updated:
        status += f" · {updated[-8:]}"
    p.drawText(QRectF(pill.left() + 31, pill.top() + 8, pill.width() - 42, 18), Qt.AlignmentFlag.AlignLeft, status[:76])


def _mp_map_draw(self, p: QPainter, w: float, h: float):
    _mp_map_init(self)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg = QRadialGradient(QPointF(w * .52, h * .48), max(w, h) * .76)
    bg.setColorAt(0, qcol("#071b24", 255))
    bg.setColorAt(.48, qcol("#06101a", 255))
    bg.setColorAt(1, qcol("#01050b", 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRect(0, 0, int(w), int(h))

    rect = _mp_map_widget_rect(self)
    p.setPen(QPen(qcol(C.PRI, 52), 1))
    p.setBrush(QBrush(qcol("#020812", 76)))
    p.drawRoundedRect(rect, 18, 18)

    # Real dashboard-like map tiles. The old cyan coordinate grid is intentionally removed.
    _mp_map_draw_real_tiles(self, p, rect)

    # Subtle atmospheric hotspots stay inside the map area.
    p.save()
    p.setClipRect(rect.adjusted(1, 1, -1, -1))
    for gx, gy, col, alpha in [
        (0.21, 0.42, C.ACC, 22),
        (0.53, 0.42, C.PRI, 28),
        (0.76, 0.42, C.RED, 20),
        (0.58, 0.70, C.GREEN, 16),
    ]:
        g = QRadialGradient(
            QPointF(rect.left() + rect.width() * gx, rect.top() + rect.height() * gy),
            rect.width() * 0.18,
        )
        g.setColorAt(0, qcol(col, alpha))
        g.setColorAt(1, qcol(col, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(
            QPointF(rect.left() + rect.width() * gx, rect.top() + rect.height() * gy),
            rect.width() * 0.18,
            rect.width() * 0.18,
        )

    _mp_map_draw_city_labels(self, p, rect)

    mode = str(getattr(self, "_security_map_active_mode", "world") or "world").lower()
    if mode in {"threat", "both", "map", "map-data"}:
        for tr in _mp_map_extract_traces(self, "threat")[:90]:
            _mp_map_draw_trace(self, p, rect, tr, "threat")
    if mode in {"live", "both"}:
        for tr in _mp_map_extract_traces(self, "live")[:110]:
            _mp_map_draw_trace(self, p, rect, tr, "live")

    _mp_map_draw_target(self, p, rect)

    if mode in {"threat", "both", "map", "map-data"}:
        for i, item in enumerate(_mp_map_extract_points(self, "threat")[:80]):
            _mp_map_draw_point(self, p, rect, item, "threat", i)
    if mode in {"live", "both"}:
        for i, item in enumerate(_mp_map_extract_points(self, "live")[:100]):
            _mp_map_draw_point(self, p, rect, item, "live", i)

    # Center reticle when zoomed to a city/country.
    if float(getattr(self, "_security_map_zoom", 1.0) or 1.0) > 3.0:
        cx, cy = rect.center().x(), rect.center().y()
        p.setPen(QPen(qcol(C.PRI, 92), 1.0))
        p.drawLine(QPointF(cx - 18, cy), QPointF(cx + 18, cy))
        p.drawLine(QPointF(cx, cy - 18), QPointF(cx, cy + 18))
        p.setPen(QPen(qcol(C.PRI, 58), 1.0))
        p.drawEllipse(QPointF(cx, cy), 26, 26)
    p.restore()

    _mp_map_draw_hud_panel(self, p, rect, w, h)

    # Mini FRIDAY hologram, same idea as camera mode, always visible in map mode.
    try:
        self._draw_mini_friday_core(p, w, h)
    except Exception:
        pass


_MPV6_ORIGINAL_HUD_PAINT = getattr(HudCanvas, "paintEvent", None)
_MPV6_ORIGINAL_HUD_MOUSE_PRESS = getattr(HudCanvas, "mousePressEvent", None)
_MPV6_ORIGINAL_HUD_MOUSE_MOVE = getattr(HudCanvas, "mouseMoveEvent", None)
_MPV6_ORIGINAL_HUD_MOUSE_RELEASE = getattr(HudCanvas, "mouseReleaseEvent", None)
_MPV6_ORIGINAL_HUD_MOUSE_DOUBLE = getattr(HudCanvas, "mouseDoubleClickEvent", None)
_MPV6_ORIGINAL_HUD_WHEEL = getattr(HudCanvas, "wheelEvent", None)


def _mpv6_hud_mouse_press_event(self, event):
    if bool(getattr(self, "security_map_mode", False)) and not bool(getattr(self, "camera_mode", False)):
        pos = _mp_map_event_pos(event)
        rect = _mp_map_widget_rect(self)
        if rect.contains(pos) and event.button() == Qt.MouseButton.LeftButton:
            _mp_map_init(self)
            self._security_map_dragging = True
            self._security_map_drag_last = pos
            try:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            except Exception:
                pass
            event.accept()
            return

    if _MPV6_ORIGINAL_HUD_MOUSE_PRESS:
        return _MPV6_ORIGINAL_HUD_MOUSE_PRESS(self, event)


def _mpv6_hud_mouse_move_event(self, event):
    if bool(getattr(self, "security_map_mode", False)) and not bool(getattr(self, "camera_mode", False)) and bool(getattr(self, "_security_map_dragging", False)):
        pos = _mp_map_event_pos(event)
        last = getattr(self, "_security_map_drag_last", None)
        if last is not None:
            try:
                dx = float(pos.x() - last.x())
                dy = float(pos.y() - last.y())
                z = _mp_map_tile_zoom(self)
                center_lat, center_lng = getattr(self, "_security_map_center", (18.0, 28.0))
                center_px = _mp_map_latlng_to_world_px(float(center_lat), float(center_lng), z)
                new_px = QPointF(center_px.x() - dx, center_px.y() - dy)
                lat, lng = _mp_map_world_px_to_latlng(new_px, z)
                self._security_map_center = (lat, lng)
                self._security_map_focus_label = "Manual"
                self._security_map_notice = "Manual pan active · drag to move, wheel to zoom."
                self._security_map_drag_last = pos
                self.update()
            except Exception:
                pass
        event.accept()
        return

    if _MPV6_ORIGINAL_HUD_MOUSE_MOVE:
        return _MPV6_ORIGINAL_HUD_MOUSE_MOVE(self, event)


def _mpv6_hud_mouse_release_event(self, event):
    if bool(getattr(self, "security_map_mode", False)) and not bool(getattr(self, "camera_mode", False)) and bool(getattr(self, "_security_map_dragging", False)):
        self._security_map_dragging = False
        self._security_map_drag_last = None
        try:
            self.unsetCursor()
        except Exception:
            pass
        event.accept()
        return

    if _MPV6_ORIGINAL_HUD_MOUSE_RELEASE:
        return _MPV6_ORIGINAL_HUD_MOUSE_RELEASE(self, event)


def _mpv6_hud_mouse_double_click_event(self, event):
    if bool(getattr(self, "security_map_mode", False)) and not bool(getattr(self, "camera_mode", False)):
        pos = _mp_map_event_pos(event)
        rect = _mp_map_widget_rect(self)
        if rect.contains(pos):
            geo = _mp_map_screen_to_latlng(self, pos, rect)
            if geo:
                self._security_map_center = geo
                self._security_map_zoom = min(6.6, float(getattr(self, "_security_map_zoom", 1.0) or 1.0) * 1.35)
                self._security_map_focus_label = "Manual"
                self._security_map_notice = "Manual zoom point selected."
                self.update()
            event.accept()
            return

    if _MPV6_ORIGINAL_HUD_MOUSE_DOUBLE:
        return _MPV6_ORIGINAL_HUD_MOUSE_DOUBLE(self, event)


def _mpv6_hud_wheel_event(self, event):
    if bool(getattr(self, "security_map_mode", False)) and not bool(getattr(self, "camera_mode", False)):
        pos = _mp_map_event_pos(event)
        rect = _mp_map_widget_rect(self)
        if rect.contains(pos):
            before_geo = _mp_map_screen_to_latlng(self, pos, rect)

            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = 0

            current = float(getattr(self, "_security_map_zoom", 1.0) or 1.0)
            if delta > 0:
                self._security_map_zoom = min(6.8, current * 1.22)
            else:
                self._security_map_zoom = max(1.0, current / 1.22)

            # Keep the geographic point under the mouse as stable as possible while zooming.
            after_geo = _mp_map_screen_to_latlng(self, pos, rect)
            if before_geo and after_geo:
                center_lat, center_lng = getattr(self, "_security_map_center", (18.0, 28.0))
                self._security_map_center = (
                    _mp_map_clip_lat(float(center_lat) + (before_geo[0] - after_geo[0])),
                    _mp_map_norm_lng(float(center_lng) + (before_geo[1] - after_geo[1])),
                )

            self._security_map_notice = "Mouse navigation active · drag to move, wheel to zoom."
            self.update()
            event.accept()
            return

    if _MPV6_ORIGINAL_HUD_WHEEL:
        return _MPV6_ORIGINAL_HUD_WHEEL(self, event)


def _mpv6_hud_paint_event(self, event):
    # Camera must have priority over the Security Map. When map mode remains true
    # from a previous view, drawing the map first hides the live camera even though
    # the camera backend is already online.
    if bool(getattr(self, "camera_mode", False)):
        if _MPV6_ORIGINAL_HUD_PAINT:
            return _MPV6_ORIGINAL_HUD_PAINT(self, event)

    if bool(getattr(self, "security_map_mode", False)):
        p = QPainter(self)
        _mp_map_draw(self, p, float(self.width()), float(self.height()))
        p.end()
        return
    if _MPV6_ORIGINAL_HUD_PAINT:
        return _MPV6_ORIGINAL_HUD_PAINT(self, event)


def _mpv6_start_security_map_now(self, payload):
    payload = payload if isinstance(payload, dict) else {}
    try:
        self.hud.start_security_map_mode(
            mode=payload.get("mode") or "world",
            map_data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
            focus=payload.get("focus") or "",
        )
        self._apply_state("MAP")
        mode = str(payload.get("mode") or "world").upper()
        self._log.append_log(f"SYS: SECURITY MAP online · {mode}.")
    except Exception as exc:
        self._log.append_log(f"ERR: Security map could not open — {exc}")


def _mpv6_focus_security_map_now(self, place):
    try:
        ok = self.hud.focus_security_map(str(place or ""))
        self._log.append_log(f"SYS: Security map focus {'updated' if ok else 'not found'} · {place}.")
    except Exception as exc:
        self._log.append_log(f"ERR: Security map focus failed — {exc}")


def _mpv6_stop_security_map_now(self):
    try:
        was_open = bool(self.hud.security_map_is_open())
    except Exception:
        was_open = False
    try:
        self.hud.stop_security_map_mode()
    except Exception:
        pass
    if was_open:
        self._log.append_log("SYS: SECURITY MAP offline.")


def _mpv6_start_security_map(self, mode="world", data=None, focus=""):
    self._map_start_sig.emit({"mode": mode, "data": data or {}, "focus": focus or ""})
    return True


def _mpv6_focus_security_map(self, place: str):
    self._map_focus_sig.emit(str(place or ""))
    return True


def _mpv6_stop_security_map(self):
    self._map_stop_sig.emit()
    return True


def _mpv6_friday_open_security_map(self, mode="world", data=None, focus=""):
    return self._win.start_security_map(mode=mode, data=data or {}, focus=focus or "")


def _mpv6_friday_focus_security_map(self, place: str):
    return self._win.focus_security_map(place)


def _mpv6_friday_stop_security_map(self):
    return self._win.stop_security_map()

try:
    HudCanvas.start_security_map_mode = _mp_map_start
    HudCanvas.stop_security_map_mode = _mp_map_stop
    HudCanvas.focus_security_map = _mp_map_focus
    HudCanvas.security_map_is_open = _mp_map_is_open
    HudCanvas.paintEvent = _mpv6_hud_paint_event
    HudCanvas.mousePressEvent = _mpv6_hud_mouse_press_event
    HudCanvas.mouseMoveEvent = _mpv6_hud_mouse_move_event
    HudCanvas.mouseReleaseEvent = _mpv6_hud_mouse_release_event
    HudCanvas.mouseDoubleClickEvent = _mpv6_hud_mouse_double_click_event
    HudCanvas.wheelEvent = _mpv6_hud_wheel_event

    MainWindow._start_security_map_now = _mpv6_start_security_map_now
    MainWindow._focus_security_map_now = _mpv6_focus_security_map_now
    MainWindow._stop_security_map_now = _mpv6_stop_security_map_now
    MainWindow.start_security_map = _mpv6_start_security_map
    MainWindow.focus_security_map = _mpv6_focus_security_map
    MainWindow.stop_security_map = _mpv6_stop_security_map

    FridayUI.open_security_map = _mpv6_friday_open_security_map
    FridayUI.start_security_map = _mpv6_friday_open_security_map
    FridayUI.focus_security_map = _mpv6_friday_focus_security_map
    FridayUI.stop_security_map = _mpv6_friday_stop_security_map
    FridayUI.close_security_map = _mpv6_friday_stop_security_map
except Exception as _mpv6_map_patch_error:
    try:
        print("[FRIDAY UI] security map patch install error:", _mpv6_map_patch_error)
    except Exception:
        pass

# === /MEDPOV FRIDAY UI V6 SECURITY CENTER GLOBAL MAP HUD ===

# === MEDPOV FRIDAY UI V6.1 DASHBOARD-STYLE SECURITY MAP FIX ===
# Drop-in patch: paste this block at the END of ui.py.
# Fixes:
# - map fills the available HUD area in fullscreen
# - removes duplicated/wrapped route breakage when panning
# - redraws routes like Security Center dashboard with moving threat pulses
# - adds camera-style red HUD frame around the map
# - quick MAP button opens real Security Center both-map data when available

_MPV81_DASHBOARD_MAP_PATCH = True


def _mp_map_widget_rect(self) -> QRectF:
    """Use almost the full HUD canvas so fullscreen does not leave top/bottom dead space."""
    w = float(self.width())
    h = float(self.height())

    mx = 14.0 if w >= 900 else 8.0
    my = 12.0 if h >= 620 else 8.0
    return QRectF(mx, my, max(120.0, w - (mx * 2.0)), max(120.0, h - (my * 2.0)))


def _mpv81_project_continuous(self, lat: float, lng: float, rect: QRectF) -> QPointF:
    _mp_map_init(self)
    z = _mp_map_tile_zoom(self)
    center_lat, center_lng = getattr(self, "_security_map_center", (18.0, 28.0))
    center_px = _mp_map_latlng_to_world_px(float(center_lat), float(center_lng), z)
    point_px = _mp_map_latlng_to_world_px(float(lat), float(lng), z)
    return QPointF(
        rect.center().x() + (point_px.x() - center_px.x()),
        rect.center().y() + (point_px.y() - center_px.y()),
    )


def _mp_map_project(self, lat, lng, rect: QRectF):
    return _mpv81_project_continuous(self, float(lat), float(lng), rect)


def _mpv81_adjust_lng_to_anchor(lng: float, anchor_lng: float) -> float:
    lng = float(lng)
    anchor_lng = float(anchor_lng)
    while (lng - anchor_lng) > 180.0:
        lng -= 360.0
    while (lng - anchor_lng) < -180.0:
        lng += 360.0
    return lng


def _mpv81_default_target(self) -> dict:
    data = getattr(self, "_security_map_data", {}) or {}
    target = data.get("target") if isinstance(data, dict) else None
    if isinstance(target, dict):
        return target
    return {"lat": 41.0082, "lng": 28.9784, "url": "medpov.com", "label": "medpov.com"}


def _mpv81_trace_endpoint(trace: dict, key: str, fallback: dict | None = None) -> dict | None:
    value = trace.get(key) if isinstance(trace, dict) else None
    if isinstance(value, dict) and value.get("lat") is not None and value.get("lng") is not None:
        return value
    if fallback and fallback.get("lat") is not None and fallback.get("lng") is not None:
        return fallback
    return None


def _mpv81_make_trace_path(self, rect: QRectF, trace: dict, kind: str) -> QPainterPath | None:
    target = _mpv81_default_target(self)
    src = _mpv81_trace_endpoint(trace, "from")
    dst = _mpv81_trace_endpoint(trace, "to", target)

    if (not src or not dst) and isinstance(trace.get("curve_points"), list) and len(trace.get("curve_points") or []) >= 2:
        pts = trace.get("curve_points") or []
        try:
            src = {"lat": float(pts[0][0]), "lng": float(pts[0][1])}
            dst = {"lat": float(pts[-1][0]), "lng": float(pts[-1][1])}
        except Exception:
            src = src or None
            dst = dst or None

    if not src or not dst:
        return None

    try:
        dst_lat = float(dst.get("lat"))
        dst_lng = float(dst.get("lng"))
        src_lat = float(src.get("lat"))
        src_lng = _mpv81_adjust_lng_to_anchor(float(src.get("lng")), dst_lng)
    except Exception:
        return None

    p1 = _mpv81_project_continuous(self, src_lat, src_lng, rect)
    p2 = _mpv81_project_continuous(self, dst_lat, dst_lng, rect)

    if not (_mp_map_on_screen(p1, rect, 180.0) or _mp_map_on_screen(p2, rect, 180.0)):
        return None

    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    distance = math.hypot(dx, dy)
    if distance < 10.0:
        return None

    if abs(dx) > rect.width() * 1.35:
        return None

    lift = max(34.0, min(170.0, distance * 0.18))
    side = -1.0 if p1.y() > p2.y() else 1.0
    mid = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0 - lift * side)

    path = QPainterPath()
    path.moveTo(p1)
    path.quadTo(mid, p2)
    return path



def _mpv81_draw_red_map_frame(self, p: QPainter, rect: QRectF):
    p.save()
    p.setClipRect(rect.adjusted(-8, -8, 8, 8))
    red = "#ff3131"
    soft = "#ff6b35"

    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(qcol(red, 150), 1.2))
    p.drawRect(rect.adjusted(1.0, 1.0, -1.0, -1.0))

    l = 58.0
    gap = 11.0
    p.setPen(QPen(qcol(red, 235), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap))
    corners = [
        (rect.left(), rect.top(), 1, 1),
        (rect.right(), rect.top(), -1, 1),
        (rect.left(), rect.bottom(), 1, -1),
        (rect.right(), rect.bottom(), -1, -1),
    ]
    for x, y, sx, sy in corners:
        p.drawLine(QPointF(x, y + sy * gap), QPointF(x, y + sy * l))
        p.drawLine(QPointF(x + sx * gap, y), QPointF(x + sx * l, y))

    p.setPen(QPen(qcol(soft, 105), 1.0, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(rect.left() + 92, rect.top() + 9), QPointF(rect.right() - 92, rect.top() + 9))
    p.drawLine(QPointF(rect.right() - 9, rect.top() + 92), QPointF(rect.right() - 9, rect.bottom() - 92))

    hot = QRadialGradient(QPointF(rect.right() - rect.width() * 0.11, rect.bottom() - rect.height() * 0.13), rect.width() * 0.22)
    hot.setColorAt(0.0, qcol(red, 38))
    hot.setColorAt(1.0, qcol(red, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(hot))
    p.drawEllipse(QPointF(rect.right() - rect.width() * 0.11, rect.bottom() - rect.height() * 0.13), rect.width() * 0.22, rect.width() * 0.22)

    p.restore()


def _mpv81_draw_protected_site_badge(self, p: QPainter, rect: QRectF):
    target = _mpv81_default_target(self)
    label = str(target.get("url") or target.get("label") or "medpov.com")[:34]
    box_w = min(292.0, max(218.0, rect.width() * 0.22))
    box = QRectF(rect.right() - box_w - 18.0, rect.top() + 20.0, box_w, 62.0)

    p.save()
    p.setPen(QPen(qcol(C.PRI, 70), 1.0))
    p.setBrush(QBrush(qcol("#061421", 224)))
    p.drawRoundedRect(box, 12, 12)
    icon = QPointF(box.left() + 28, box.center().y())
    p.setPen(QPen(qcol(C.PRI, 210), 1.2))
    p.setBrush(QBrush(qcol(C.PRI, 28)))
    p.drawEllipse(icon, 14, 14)
    p.drawEllipse(icon, 5, 5)
    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Black))
    p.setPen(qcol(C.TEXT_DIM, 215))
    p.drawText(QRectF(box.left() + 52, box.top() + 11, box.width() - 66, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "PROTECTED WEBSITE")
    p.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    p.setPen(qcol("#ffffff", 235))
    p.drawText(QRectF(box.left() + 52, box.top() + 29, box.width() - 66, 21), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
    p.restore()


def _mpv81_has_layer_data(self, kind: str) -> bool:
    return bool(_mp_map_extract_points(self, kind) or _mp_map_extract_traces(self, kind))


def _mp_map_draw(self, p: QPainter, w: float, h: float):
    _mp_map_init(self)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    bg = QRadialGradient(QPointF(w * .52, h * .48), max(w, h) * .76)
    bg.setColorAt(0, qcol("#071b24", 255))
    bg.setColorAt(.50, qcol("#06101a", 255))
    bg.setColorAt(1, qcol("#01050b", 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawRect(0, 0, int(w), int(h))

    rect = _mp_map_widget_rect(self)

    p.setPen(QPen(qcol(C.PRI, 58), 1.0))
    p.setBrush(QBrush(qcol("#020812", 92)))
    p.drawRoundedRect(rect, 12, 12)

    _mp_map_draw_real_tiles(self, p, rect)

    p.save()
    p.setClipRect(rect.adjusted(1, 1, -1, -1))

    for gx, gy, col, alpha, scale in [
        (0.24, 0.44, C.ACC, 22, 0.22),
        (0.54, 0.43, C.PRI, 30, 0.25),
        (0.78, 0.46, C.RED, 23, 0.24),
        (0.58, 0.74, C.GREEN, 16, 0.20),
    ]:
        center = QPointF(rect.left() + rect.width() * gx, rect.top() + rect.height() * gy)
        g = QRadialGradient(center, rect.width() * scale)
        g.setColorAt(0, qcol(col, alpha))
        g.setColorAt(1, qcol(col, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, rect.width() * scale, rect.width() * scale)

    _mp_map_draw_city_labels(self, p, rect)

    mode = str(getattr(self, "_security_map_active_mode", "world") or "world").lower()
    threat_on = mode in {"world", "threat", "both", "map", "map-data"} or _mpv81_has_layer_data(self, "threat")
    live_on = mode in {"live", "both"} or (mode == "world" and _mpv81_has_layer_data(self, "live"))

    if threat_on:
        for tr in _mp_map_extract_traces(self, "threat")[:100]:
            _mp_map_draw_trace(self, p, rect, tr, "threat")
    if live_on:
        for tr in _mp_map_extract_traces(self, "live")[:120]:
            _mp_map_draw_trace(self, p, rect, tr, "live")

    _mp_map_draw_target(self, p, rect)

    if threat_on:
        for i, item in enumerate(_mp_map_extract_points(self, "threat")[:90]):
            _mp_map_draw_point(self, p, rect, item, "threat", i)
    if live_on:
        for i, item in enumerate(_mp_map_extract_points(self, "live")[:110]):
            _mp_map_draw_point(self, p, rect, item, "live", i)

    p.restore()

    _mpv81_draw_red_map_frame(self, p, rect)
    _mp_map_draw_hud_panel(self, p, rect, w, h)
    _mpv81_draw_protected_site_badge(self, p, rect)

    try:
        self._draw_mini_friday_core(p, w, h)
    except Exception:
        pass


def _mpv81_hud_paint_event(self, event):
    if bool(getattr(self, "camera_mode", False)):
        try:
            return _MPV6_ORIGINAL_HUD_PAINT(self, event)
        except Exception:
            pass

    if bool(getattr(self, "security_map_mode", False)):
        p = QPainter(self)
        _mp_map_draw(self, p, float(self.width()), float(self.height()))
        p.end()
        return

    try:
        return _MPV6_ORIGINAL_HUD_PAINT(self, event)
    except Exception:
        pass


def _mpv81_open_security_map_quick(self):
    """Left MAP button: open immediately, then hydrate with real Security Center dashboard map data."""
    try:
        self.start_security_map(mode="both", data={}, focus="")
        self._log.append_log("SYS: Map quick button requested · loading Security Center both-map.")
    except Exception as exc:
        try:
            self._log.append_log(f"ERR: Map quick button failed — {exc}")
        except Exception:
            pass
        return

    def _worker():
        try:
            try:
                from tools.security_center_client import SecurityCenterClient
            except Exception:
                from security_center_client import SecurityCenterClient  # type: ignore
            data = SecurityCenterClient(timeout=18).both_map(threat_range="24h", live_range="live", include_curve_points=True)
            if isinstance(data, dict) and data.get("ok", True) is not False:
                self._map_start_sig.emit({"mode": "both", "data": data, "focus": ""})
            else:
                self._map_start_sig.emit({"mode": "world", "data": {}, "focus": ""})
        except Exception:
            self._map_start_sig.emit({"mode": "world", "data": {}, "focus": ""})

    threading.Thread(target=_worker, daemon=True).start()


try:
    HudCanvas.paintEvent = _mpv81_hud_paint_event
    MainWindow._open_security_map_quick = _mpv81_open_security_map_quick
except Exception as _mpv81_patch_error:
    try:
        print("[FRIDAY UI] dashboard map patch install error:", _mpv81_patch_error)
    except Exception:
        pass

# === /MEDPOV FRIDAY UI V6.1 DASHBOARD-STYLE SECURITY MAP FIX ===

# === MEDPOV FRIDAY MAP TOP/BOTTOM SEAM COLOR FIX ===
# Paste this block at the END of ui.py
# Fixes the empty-looking top/bottom areas inside the red map frame.
# Top gap: sea color        #1E1F21
# Bottom gap: Antarctica    #08100F

_MPV6_MAP_TOP_SEA = "#1E1F21"
_MPV6_MAP_BOTTOM_ANTARCTICA = "#08100F"


def _mp_map_draw_real_tiles(self, p: QPainter, rect: QRectF) -> int:
    """Draw real dashboard-like dark world tiles with fixed top/bottom seam colors."""
    _mp_map_init(self)

    z = _mp_map_tile_zoom(self)
    n = 2 ** z
    world_size = _MP_TILE_SIZE * n

    center_lat, center_lng = getattr(self, "_security_map_center", (18.0, 28.0))
    center_px = _mp_map_latlng_to_world_px(float(center_lat), float(center_lng), z)

    left_world = center_px.x() - rect.width() / 2.0
    top_world = center_px.y() - rect.height() / 2.0
    right_world = center_px.x() + rect.width() / 2.0
    bottom_world = center_px.y() + rect.height() / 2.0

    start_tx = int(math.floor(left_world / _MP_TILE_SIZE)) - 1
    end_tx = int(math.floor(right_world / _MP_TILE_SIZE)) + 1
    start_ty = max(0, int(math.floor(top_world / _MP_TILE_SIZE)) - 1)
    end_ty = min(n - 1, int(math.floor(bottom_world / _MP_TILE_SIZE)) + 1)

    loaded = 0

    p.save()
    p.setClipRect(rect)

    # Base background: top sea color, bottom Antarctica color.
    # This removes the empty black-looking cut above/below the actual tile world.
    base = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    base.setColorAt(0.00, qcol(_MPV6_MAP_TOP_SEA, 255))
    base.setColorAt(0.58, qcol("#121719", 255))
    base.setColorAt(0.82, qcol(_MPV6_MAP_BOTTOM_ANTARCTICA, 255))
    base.setColorAt(1.00, qcol(_MPV6_MAP_BOTTOM_ANTARCTICA, 255))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(base))
    p.drawRect(rect)

    for ty in range(start_ty, end_ty + 1):
        for tx_raw in range(start_tx, end_tx + 1):
            tx = tx_raw % n
            path = _mp_map_tile_path(z, tx, ty)

            sx = rect.center().x() + (tx_raw * _MP_TILE_SIZE - center_px.x())
            sy = rect.center().y() + (ty * _MP_TILE_SIZE - center_px.y())
            tile_rect = QRectF(sx, sy, _MP_TILE_SIZE + 1, _MP_TILE_SIZE + 1)

            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    p.drawPixmap(tile_rect, pix, QRectF(0, 0, pix.width(), pix.height()))
                    loaded += 1
                    continue

            # Placeholder while tile is downloading.
            # Upper missing tiles use sea tone, lower missing tiles use Antarctica tone.
            placeholder = _MPV6_MAP_TOP_SEA if tile_rect.center().y() < rect.center().y() else _MPV6_MAP_BOTTOM_ANTARCTICA

            p.setPen(QPen(qcol(C.PRI, 10), 1))
            p.setBrush(QBrush(qcol(placeholder, 210)))
            p.drawRect(tile_rect)

            _mp_map_schedule_tile_download(self, z, tx, ty, path)

    # Explicitly paint the areas outside Mercator tile bounds.
    # North/top area.
    world_top_screen_y = rect.center().y() - center_px.y()
    if world_top_screen_y > rect.top():
        top_bottom = min(rect.bottom(), world_top_screen_y)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(_MPV6_MAP_TOP_SEA, 255)))
        p.drawRect(QRectF(rect.left(), rect.top(), rect.width(), top_bottom - rect.top()))

        # Soft blend into map tiles.
        fade = QLinearGradient(
            QPointF(rect.left(), top_bottom - 2),
            QPointF(rect.left(), min(rect.bottom(), top_bottom + 42))
        )
        fade.setColorAt(0.00, qcol(_MPV6_MAP_TOP_SEA, 230))
        fade.setColorAt(1.00, qcol(_MPV6_MAP_TOP_SEA, 0))
        p.setBrush(QBrush(fade))
        p.drawRect(QRectF(rect.left(), top_bottom - 2, rect.width(), 44))

    # South/bottom area.
    world_bottom_screen_y = rect.center().y() + world_size - center_px.y()
    if world_bottom_screen_y < rect.bottom():
        bottom_top = max(rect.top(), world_bottom_screen_y)

        # Soft blend from map tiles into Antarctica color.
        fade = QLinearGradient(
            QPointF(rect.left(), max(rect.top(), bottom_top - 46)),
            QPointF(rect.left(), bottom_top + 2)
        )
        fade.setColorAt(0.00, qcol(_MPV6_MAP_BOTTOM_ANTARCTICA, 0))
        fade.setColorAt(1.00, qcol(_MPV6_MAP_BOTTOM_ANTARCTICA, 235))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fade))
        p.drawRect(QRectF(rect.left(), max(rect.top(), bottom_top - 46), rect.width(), 48))

        p.setBrush(QBrush(qcol(_MPV6_MAP_BOTTOM_ANTARCTICA, 255)))
        p.drawRect(QRectF(rect.left(), bottom_top, rect.width(), rect.bottom() - bottom_top))

    # Dashboard-style dark atmosphere overlay.
    shade = QLinearGradient(rect.topLeft(), rect.bottomRight())
    shade.setColorAt(0.00, qcol("#00050a", 72))
    shade.setColorAt(0.45, qcol("#00131a", 36))
    shade.setColorAt(1.00, qcol("#050006", 88))

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(shade))
    p.drawRect(rect)

    # If there is no internet/cache yet, keep the offline vector fallback visible.
    if loaded == 0:
        _mp_map_draw_land(self, p, rect)

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(qcol(C.TEXT_DIM, 170))
        p.drawText(
            QRectF(rect.left() + 24, rect.bottom() - 28, rect.width() - 48, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Real dashboard map tiles are loading and will be cached locally."
        )

    p.restore()
    return loaded