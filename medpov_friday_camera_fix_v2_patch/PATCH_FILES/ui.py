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
    )
except Exception:
    save_gemini_api_key_everywhere = None
    bootstrap_environment = None

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


    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
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

_DEFAULT_W, _DEFAULT_H = 1600, 1100
_MIN_W,     _MIN_H     = 1040, 640
_LEFT_W  = 205
_RIGHT_W = 385

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#02040b"
    PANEL     = "#06101d"
    PANEL2    = "#081729"
    BORDER    = "#15365d"
    BORDER_B  = "#1aa7ff"
    BORDER_A  = "#255c91"
    PRI       = "#28e9ff"
    PRI_DIM   = "#176d93"
    PRI_GHO   = "#051b2c"
    ACC       = "#ff9f1c"
    ACC2      = "#ffd166"
    GREEN     = "#22f2a8"
    GREEN_D   = "#12845e"
    RED       = "#ff3b6b"
    MUTED_C   = "#ff4d8d"
    TEXT      = "#b9f7ff"
    TEXT_DIM  = "#6888a3"
    TEXT_MED  = "#8ed8ef"
    WHITE     = "#f5fcff"
    DARK      = "#040912"
    BAR_BG    = "#081522"
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
        self.setFixedHeight(202)
        self.setMinimumWidth(120)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(6, 16, 29, 0.94);
                border: 1px solid {C.BORDER_A};
                border-radius: 12px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(7, 7, 7, 7)
        lay.setSpacing(4)

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

        # MEDPOV FRIDAY camera / Jarvis vision mode
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
    # MEDPOV FRIDAY — Jarvis style camera vision mode
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
        Kamera açıldığında ana FRIDAY core görünümünü Jarvis tarzı kamera moduna alır.
        Orta alanda kamera görüntüsü, sağ altta mini FRIDAY halkaları gösterilir.
        """
        self.camera_mode = True
        self.state = "CAMERA"
        self._camera_error = ""
        self._camera_index = self._preferred_camera_index() if camera_index is None else int(camera_index)
        with self._camera_lock:
            self._camera_snapshot_bytes = None

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
            self._camera = cv2.VideoCapture(self._camera_index, self._preferred_camera_backend())

            if not self._camera or not self._camera.isOpened():
                self._camera_error = f"Kamera açılamadı: index {self._camera_index}"
                self._camera = None
                self.update()
                return False

            try:
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self._camera.set(cv2.CAP_PROP_FPS, 30)
            except Exception:
                pass

            self._camera_timer.start(30)
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

    def stop_camera_mode(self):
        self.stop_camera_capture_only()
        self.camera_mode = False
        self._camera_error = ""
        self.state = "IDLE"
        self.update()

    def _camera_tick(self):
        if not self.camera_mode or self._camera is None:
            return

        try:
            ok, frame = self._camera.read()
            if not ok or frame is None:
                self._camera_error = "Kamera görüntüsü alınamadı"
                self.update()
                return

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

            # Vision modülü ayrı kamera açmaya çalışmasın diye periyodik JPEG snapshot sakla.
            if (self._tick % 5 == 0) or self._camera_snapshot_bytes is None:
                try:
                    ok_jpg, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 68])
                    if ok_jpg:
                        with self._camera_lock:
                            self._camera_snapshot_bytes = jpg.tobytes()
                except Exception:
                    pass

            self._camera_error = ""
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
            time.sleep(0.03)

        raise RuntimeError(self._camera_error or "Kamera frame hazır değil")

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
        cx = w - mini_r * 1.42
        cy = h - mini_r * 1.30

        p.save()
        halo = QRadialGradient(QPointF(cx, cy), mini_r * 2.20)
        halo.setColorAt(0.00, self._q(pal["primary"], 92))
        halo.setColorAt(0.45, self._q(pal["primary"], 30))
        halo.setColorAt(1.00, self._q("#000000", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), mini_r * 2.15, mini_r * 2.15)

        self._draw_outer_rings(p, cx, cy, mini_r)
        self._draw_inner_tech(p, cx, cy, mini_r)

        p.setPen(self._q("#f5fcff", 235))
        p.setFont(QFont("Arial", max(10, int(mini_r * 0.17)), QFont.Weight.Black))
        p.drawText(
            QRectF(cx - mini_r * 0.78, cy - 12, mini_r * 1.56, 24),
            Qt.AlignmentFlag.AlignCenter,
            "F.R.I.D.A.Y",
        )

        p.setPen(self._q(pal["primary"], 180))
        p.setFont(QFont("Courier New", max(7, int(mini_r * 0.075)), QFont.Weight.Bold))
        p.drawText(
            QRectF(cx - mini_r * 0.85, cy + mini_r * 0.28, mini_r * 1.70, 18),
            Qt.AlignmentFlag.AlignCenter,
            "VISION CORE",
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

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text  = "--"
        self.setFixedHeight(52)
        self.setMinimumWidth(120)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        bg = QLinearGradient(0, 0, W, H)
        bg.setColorAt(0.0, qcol("#081421", 245))
        bg.setColorAt(1.0, qcol("#050b14", 245))
        p.setBrush(QBrush(bg))
        p.setPen(QPen(qcol(C.BORDER_A, 190), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 12, 12)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(12, 7, W - 24, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Black))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(12, 7, W - 24, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        bar_h = 6
        bar_x = 12
        bar_y = H - 17
        bar_w = W - 24
        fill_w = int(bar_w * self._value / 100)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)
        if fill_w > 0:
            grad = QLinearGradient(bar_x, bar_y, bar_x + max(1, fill_w), bar_y)
            grad.setColorAt(0, qcol(self._color, 120))
            grad.setColorAt(1, bar_col)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 3, 3)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 12px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

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
        self.setFixedHeight(100)
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
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Analyze")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · PDF · Office · Code · Data · Media")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to analyze")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


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


class MainWindow(QMainWindow):
    _log_sig          = pyqtSignal(str)
    _state_sig        = pyqtSignal(str)
    _standby_sig      = pyqtSignal(bool)
    _camera_start_sig = pyqtSignal(object)
    _camera_stop_sig  = pyqtSignal()

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
        self._current_file: str | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

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

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)

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
        w = QWidget()
        w.setFixedHeight(78)
        w.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #040912, stop:0.5 #07192a, stop:1 #040912);
                border-bottom: 1px solid {C.BORDER_B};
            }}
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(22, 0, 22, 0)
        lay.setSpacing(16)

        left = QVBoxLayout(); left.setSpacing(3)
        brand = QLabel("MEDPOV")
        brand.setFont(QFont("Segoe UI", 16, QFont.Weight.Black))
        brand.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none; letter-spacing: 2px;")
        left.addWidget(brand)
        build = QLabel("PRIVATE AI COMMAND SYSTEM")
        build.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        build.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        left.addWidget(build)
        lay.addLayout(left)

        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(0)
        title = QLabel("F.R.I.D.A.Y")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 25, QFont.Weight.Black))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none; letter-spacing: 7px;")
        mid.addWidget(title)
        sub = QLabel("MEDPOV Holographic Personal Intelligence Interface")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        sub.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        mid.addWidget(sub)
        lay.addLayout(mid)

        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Segoe UI", 17, QFont.Weight.Black))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ MEDPOV SYSTEM")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 12px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont("Courier New", 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addStretch()

        self._sc_synopsis = SecuritySynopsisWidget(self)
        lay.addWidget(self._sc_synopsis)
        lay.addSpacing(4)

        for txt, col in [
            ("FRIDAY\nONLINE",     C.GREEN),
            ("MEDPOV\nSECURE",      C.PRI),
            ("AI CORE\nREADY",     C.TEXT_DIM),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 10px; padding: 4px;"
            )
            lay.addWidget(lbl)

        return w

    def _build_friday_settings_panel(self):
        """
        Right sidebar settings shortcut panel.
        Safe method injected by MEDPOV Friday Settings Panel Repair.
        """
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QMessageBox

        panel = QFrame()
        panel.setObjectName("FridaySettingsQuickPanel")
        panel.setStyleSheet("""
            QFrame#FridaySettingsQuickPanel {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(255, 139, 38, 0.16),
                    stop:0.52 rgba(15, 23, 42, 0.72),
                    stop:1 rgba(2, 6, 23, 0.86));
                border: 1px solid rgba(255, 160, 64, 0.38);
                border-radius: 18px;
                padding: 10px;
            }
            QFrame#FridaySettingsQuickPanel QLabel {
                color: rgba(255, 244, 226, 0.95);
                background: transparent;
            }
            QFrame#FridaySettingsQuickPanel QLabel#FridaySettingsTitle {
                color: #ffb45f;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1.2px;
            }
            QFrame#FridaySettingsQuickPanel QLabel#FridaySettingsDesc {
                color: rgba(226, 232, 240, 0.72);
                font-size: 10px;
                line-height: 1.35em;
            }
            QFrame#FridaySettingsQuickPanel QPushButton {
                color: #fff7ed;
                background: rgba(255, 139, 38, 0.22);
                border: 1px solid rgba(255, 177, 94, 0.45);
                border-radius: 12px;
                padding: 9px 10px;
                font-weight: 800;
            }
            QFrame#FridaySettingsQuickPanel QPushButton:hover {
                background: rgba(255, 139, 38, 0.36);
                border-color: rgba(255, 202, 133, 0.72);
            }
        """)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("⚙ FRIDAY SETTINGS")
        title.setObjectName("FridaySettingsTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)

        desc = QLabel("Ses, Gemini API ve Security Center bağlantı bilgilerini buradan değiştir.")
        desc.setObjectName("FridaySettingsDesc")
        desc.setWordWrap(True)

        btn = QPushButton("Ayarları Aç")
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
                raise RuntimeError("tools/friday_settings_dialog.py içinde FridaySettingsDialog sınıfı bulunamadı.")

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
                raise RuntimeError("Ayarlar penceresi exec/show desteklemiyor.")

        except Exception as exc:
            QMessageBox.warning(
                self,
                "FRIDAY Settings",
                "Ayarlar penceresi açılamadı.\n\n"
                f"Hata: {exc}\n\n"
                "Kontrol et:\n"
                "- tools/friday_settings_dialog.py var mı?\n"
                "- tools/friday_settings_store.py var mı?\n"
                "- config/friday_settings.json yazılabilir mi?"
            )

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        lay.addWidget(_sec("FRIDAY COMMAND LOG"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("INTELLIGENT FILE INPUT"))
        self._drop_zone = FileDropZone()
        self._drop_zone.file_selected.connect(self._on_file_selected)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click to analyze with FRIDAY")
        self._file_hint.setFont(QFont("Courier New", 7))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("SECURITY CENTER"))
        lay.addWidget(self._build_security_center_quick_panel())

        lay.addWidget(_sec("AYARLAR"))
        lay.addWidget(self._build_friday_settings_panel())

        lay.addWidget(_sec("DIRECT COMMAND"))
        lay.addLayout(self._build_input_row())

        self._standby_btn = QPushButton("⏸  STANDBY MODE")
        self._standby_btn.setFixedHeight(30)
        self._standby_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._standby_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._standby_btn.clicked.connect(self._toggle_standby)
        self._style_standby_btn()
        lay.addWidget(self._standby_btn)

        self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(30)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
        fs_btn.setFixedHeight(26)
        fs_btn.setFont(QFont("Courier New", 7))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 10px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; border: 1px solid {C.BORDER_B};
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
        box.setStyleSheet(f"""
            QFrame {{ background: rgba(5, 22, 36, 0.78); border: 1px solid {C.BORDER}; border-radius: 12px; }}
            QPushButton {{ background: #061626; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 9px; padding: 5px 7px; text-align: left; }}
            QPushButton:hover {{ color: {C.WHITE}; border: 1px solid {C.BORDER_B}; background: #09223a; }}
            QLabel {{ background: transparent; border: none; }}
        """)
        outer = QVBoxLayout(box); outer.setContentsMargins(7,7,7,7); outer.setSpacing(5)
        head = QLabel("SECURITY CENTER QUICK LINK"); head.setFont(QFont("Courier New", 7, QFont.Weight.Bold)); head.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;"); outer.addWidget(head)
        hint = QLabel("Live MEDPOV threat intelligence"); hint.setFont(QFont("Courier New", 7)); hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;"); outer.addWidget(hint)
        commands = [("● Overview","/sc overview",True),("▲ Son Tehditler","/sc threats",True),("◆ Health","/sc health",True),("◉ Live","/sc live",True),("IP Profil","/sc ip 65.55.210.207",False),("IP Analiz","/sc analyze 65.55.210.207",False),("IP Block","/sc block 1.2.3.4",False),("Resolve Event","/sc resolve-event 124",False)]
        for idx in range(0, len(commands), 2):
            row = QHBoxLayout(); row.setSpacing(5)
            for label, command, send_now in commands[idx:idx+2]:
                btn = QPushButton(label); btn.setFixedHeight(25); btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold)); btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _=False, c=command, s=send_now: self._run_security_center_quick(c, s))
                row.addWidget(btn)
            outer.addLayout(row)
        return box

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask FRIDAY or type a command…")
        self._input.setFont(QFont("Courier New", 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 10px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 10px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(28)
        w.setStyleSheet(f"background: {C.DARK}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(w); lay.setContentsMargins(18, 0, 18, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("MEDPOV Technologies  ·  FRIDAY AI COMMAND CENTER  ·  PRIVATE BUILD", C.WHITE))
        lay.addStretch()
        lay.addWidget(_fl("© MEDPOV.COM", C.PRI_DIM))
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
        if not hasattr(self, "_standby_btn"):
            return
        if self._standby:
            self._standby_btn.setText("▶  START LISTENING")
            self._standby_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #0c1a0f; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 10px;
                }}
                QPushButton:hover {{ background: #102818; }}
            """)
        else:
            self._standby_btn.setText("⏸  STANDBY MODE")
            self._standby_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #1c1005; color: {C.ACC2};
                    border: 1px solid {C.ACC2}; border-radius: 10px;
                }}
                QPushButton:hover {{ background: #281606; }}
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
                QPushButton {{
                    background: #140006; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 10px;
                }}
            """)
        else:
            self._mute_btn.setText("🎙  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #00140a; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 10px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

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
        self._camera_start_sig.emit(camera_index)
        return True

    def _start_camera_mode_now(self, camera_index=None):
        ok = self.hud.start_camera_mode(camera_index=camera_index)
        if ok:
            self._log.append_log("SYS: CAMERA VISION online.")
        else:
            self._log.append_log(f"ERR: Kamera modu açılamadı — {self.hud._camera_error}")

    def stop_camera_mode(self):
        self._camera_stop_sig.emit()

    def _stop_camera_mode_now(self):
        self.hud.stop_camera_mode()
        self._log.append_log("SYS: CAMERA VISION offline.")

    def capture_camera_snapshot(self, wait_seconds: float = 1.0) -> tuple[bytes, str]:
        return self.hud.camera_snapshot(wait_seconds=wait_seconds)

    def closeEvent(self, event):
        try:
            self.hud.stop_camera_capture_only()
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


class JarvisUI:
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


# Compatibility alias for the MEDPOV FRIDAY build.
FridayUI = JarvisUI


# --- MEDPOV FRIDAY settings panel bridge ---
def _mp_friday_open_settings_dialog(self):
    try:
        from tools.friday_settings_dialog import FridaySettingsDialog
        dlg = FridaySettingsDialog(self)
        dlg.exec()
        try:
            if hasattr(self, "write_log"):
                self.write_log("FRIDAY: Ayarlar güncellendi. Bazı değişiklikler için yeniden başlatma önerilir.")
        except Exception:
            pass
    except Exception as e:
        try:
            if hasattr(self, "write_log"):
                self.write_log(f"ERR: Ayarlar paneli açılamadı — {e}")
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Ayarlar", str(e))
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
    btn = QPushButton("Ayarları Aç")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda: self._open_friday_settings_dialog())
    lay.addWidget(head)
    lay.addWidget(info)
    lay.addWidget(btn)
    return box

try:
    JarvisUI._open_friday_settings_dialog = _mp_friday_open_settings_dialog
    JarvisUI._build_friday_settings_panel = _mp_friday_build_settings_panel
except NameError:
    try:
        MainWindow._open_friday_settings_dialog = _mp_friday_open_settings_dialog
        MainWindow._build_friday_settings_panel = _mp_friday_build_settings_panel
    except NameError:
        pass
# --- /MEDPOV FRIDAY settings panel bridge ---
