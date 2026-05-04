# -*- coding: utf-8 -*-
"""Thread-safe FRIDAY mode runtime.

This module never touches PyQt widgets from worker threads.
Worker threads only call request_mode(); ui.py polls drain_requests()
from the Qt owner thread.
"""
from __future__ import annotations

import json
import math
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
WAKE_CONFIG_PATH = CONFIG_DIR / "friday_wake.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "start_in_standby": False,
    "wake_words": ["hey friday", "hey medpov", "friday", "medpov", "hey med pov"],
    "standby_phrases": [
        "bekleme moduna geç", "bekleme moduna gec", "beklemeye geç", "beklemeye gec",
        "beklemeye al", "dinlemeyi durdur", "standby", "standby mode", "uyku moduna geç", "uyku moduna gec"
    ],
    "wake_phrases": [
        "dinleme moduna geç", "dinleme moduna gec", "dinlemeye geç", "dinlemeye gec",
        "beni dinle", "hey friday", "hey medpov", "wake", "wake up"
    ],
    "double_clap": {
        "enabled": True,
        "sample_rate": 16000,
        "block_ms": 80,
        "threshold": 0.34,
        "min_gap_ms": 140,
        "max_gap_ms": 1250,
        "cooldown_ms": 1500
    },
    "vosk": {
        "enabled": True,
        "model_dir": "models/vosk-model-small-tr-0.3"
    }
}

_lock = threading.RLock()
_mode = "listening"
_requests: "queue.Queue[dict]" = queue.Queue()
_wake_thread: threading.Thread | None = None
_stop_event: threading.Event | None = None
_last_reason = "initial"


def _merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> Dict[str, Any]:
    try:
        if WAKE_CONFIG_PATH.exists():
            data = json.loads(WAKE_CONFIG_PATH.read_text(encoding="utf-8") or "{}")
            if isinstance(data, dict):
                return _merge(DEFAULT_CONFIG, data)
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_CONFIG, ensure_ascii=False))


def save_config(data: Dict[str, Any]) -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = _merge(DEFAULT_CONFIG, data or {})
    WAKE_CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def _normalize(text: str) -> str:
    text = str(text or "").strip().lower()
    text = text.translate(str.maketrans({
        "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
        "ş": "s", "Ş": "s", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    }))
    text = re.sub(r"[^a-z0-9/ ._-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_any(text: str, phrases: List[str]) -> bool:
    n = _normalize(text)
    return any(_normalize(p) in n for p in phrases if str(p or "").strip())


def parse_mode_text(text: str) -> str | None:
    raw = str(text or "").strip()
    n = _normalize(raw)
    cfg = load_config()

    if n in ("/standby", "/bekleme", "/sleep") or contains_any(raw, list(cfg.get("standby_phrases") or [])):
        return "standby"
    if n in ("/wake", "/dinle", "/listen") or contains_any(raw, list(cfg.get("wake_phrases") or [])):
        return "listening"
    if n in ("/mute", "/sessiz"):
        return "muted"
    return None


def request_mode(mode: str, source: str = "manual", message: str = "") -> str:
    global _mode, _last_reason
    mode = str(mode or "").strip().lower().replace("listen", "listening")
    aliases = {"wake": "listening", "dinle": "listening", "bekleme": "standby", "sleep": "standby", "mute": "muted"}
    mode = aliases.get(mode, mode)
    if mode not in ("standby", "listening", "muted"):
        mode = "listening"
    with _lock:
        _mode = mode
        _last_reason = source or "manual"
    _requests.put({"mode": mode, "source": source, "message": message, "ts": time.time()})
    return mode


def get_mode() -> str:
    with _lock:
        return _mode


def is_standby() -> bool:
    return get_mode() == "standby"


def is_muted_mode() -> bool:
    return get_mode() == "muted"


def is_voice_blocked() -> bool:
    return get_mode() in ("standby", "muted")


def drain_requests(limit: int = 20) -> list[dict]:
    items: list[dict] = []
    for _ in range(max(1, int(limit))):
        try:
            items.append(_requests.get_nowait())
        except queue.Empty:
            break
    return items


def _wake_loop(stop_event: threading.Event):
    cfg = load_config()
    if not bool(cfg.get("enabled", True)):
        return

    dc = cfg.get("double_clap") or {}
    if not bool(dc.get("enabled", True)):
        return

    try:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore
    except Exception:
        # sounddevice/numpy yoksa sessizce pasif kal. Uygulamayı bozmaz.
        return

    sample_rate = int(dc.get("sample_rate", 16000) or 16000)
    block_ms = int(dc.get("block_ms", 80) or 80)
    block_size = max(256, int(sample_rate * block_ms / 1000))
    threshold = float(dc.get("threshold", 0.34) or 0.34)
    min_gap = float(dc.get("min_gap_ms", 140) or 140) / 1000.0
    max_gap = float(dc.get("max_gap_ms", 1250) or 1250) / 1000.0
    cooldown = float(dc.get("cooldown_ms", 1500) or 1500) / 1000.0
    last_clap = 0.0
    last_wake = 0.0
    was_loud = False

    # Optional offline wake-word support with Vosk. If dependency/model is missing,
    # only double-clap remains active and the app still opens normally.
    vosk_rec = None
    try:
        vosk_cfg = cfg.get("vosk") or {}
        if bool(vosk_cfg.get("enabled", True)):
            import vosk  # type: ignore
            model_dir = ROOT / str(vosk_cfg.get("model_dir") or "models/vosk-model-small-tr-0.3")
            if model_dir.exists():
                vosk.SetLogLevel(-1)
                vosk_rec = vosk.KaldiRecognizer(vosk.Model(str(model_dir)), sample_rate)
    except Exception:
        vosk_rec = None

    def _vosk_check(arr):
        nonlocal last_wake
        if vosk_rec is None:
            return
        try:
            pcm = np.clip(arr.reshape(-1), -1, 1)
            pcm16 = (pcm * 32767).astype(np.int16).tobytes()
            text = ""
            if vosk_rec.AcceptWaveform(pcm16):
                payload = json.loads(vosk_rec.Result() or "{}")
                text = str(payload.get("text") or "")
            else:
                payload = json.loads(vosk_rec.PartialResult() or "{}")
                text = str(payload.get("partial") or "")
            if text and contains_any(text, list(cfg.get("wake_words") or [])):
                now = time.time()
                if now - last_wake >= cooldown:
                    last_wake = now
                    request_mode("listening", "wake_word", text)
        except Exception:
            pass

    def callback(indata, frames, time_info, status):
        nonlocal last_clap, last_wake, was_loud
        if stop_event.is_set():
            raise sd.CallbackStop()
        if get_mode() != "standby":
            was_loud = False
            return
        try:
            arr = np.asarray(indata, dtype="float32")
            _vosk_check(arr)
            rms = float(np.sqrt(np.mean(np.square(arr)))) if arr.size else 0.0
            loud = rms >= threshold
            now = time.time()
            # rising edge: tek clap say
            if loud and not was_loud:
                gap = now - last_clap
                if min_gap <= gap <= max_gap and now - last_wake >= cooldown:
                    last_wake = now
                    last_clap = 0.0
                    request_mode("listening", "double_clap", "Çift alkış algılandı")
                else:
                    last_clap = now
            was_loud = loud
        except Exception:
            pass

    try:
        with sd.InputStream(channels=1, samplerate=sample_rate, blocksize=block_size, dtype="float32", callback=callback):
            while not stop_event.is_set():
                time.sleep(0.15)
    except Exception:
        return


def start_wake_monitor() -> bool:
    global _wake_thread, _stop_event
    cfg = load_config()
    if bool(cfg.get("start_in_standby", False)):
        request_mode("standby", "startup", "Başlangıçta bekleme modu")
    with _lock:
        if _wake_thread and _wake_thread.is_alive():
            return True
        _stop_event = threading.Event()
        _wake_thread = threading.Thread(target=_wake_loop, args=(_stop_event,), daemon=True, name="FridayWakeMonitor")
        _wake_thread.start()
        return True


def stop_wake_monitor() -> None:
    global _stop_event
    try:
        if _stop_event:
            _stop_event.set()
    except Exception:
        pass
