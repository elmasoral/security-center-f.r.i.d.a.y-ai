from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False
    
try:
    from tools.friday_settings_store import (
        get_friday_voice_name,
        get_friday_response_language_instruction,
        get_friday_ai_provider,
        get_friday_fallback_provider,
        get_openai_api_key,
        get_friday_camera_enabled,
        get_friday_camera_disabled_message,
    )
except Exception:
    def get_friday_voice_name() -> str:
        return "Aoede"

    def get_friday_response_language_instruction() -> str:
        return "Her zaman Türkçe cevap ver."
    def get_friday_ai_provider() -> str:
        return "gemini"
    def get_friday_fallback_provider() -> str:
        return "openai"
    def get_openai_api_key() -> str:
        return ""
    def get_friday_camera_enabled() -> bool:
        return True
    def get_friday_camera_disabled_message() -> str:
        return "Camera access is currently disabled in FRIDAY settings. I cannot open the camera until Camera Access is enabled."

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

from google import genai
from google.genai import types as gtypes

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")


def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found in config.")
    return key


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()

_LIVE_MODEL         = "models/gemini-2.5-flash-native-audio-preview-12-2025"
_CHANNELS           = 1
_RECEIVE_SAMPLE_RATE = 24_000
_CHUNK_SIZE         = 1_024

_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q    = 60

_SYSTEM_PROMPT = (
    "You are F.R.I.D.A.Y, MEDPOV's private desktop AI assistant. "
    "Analyze the provided image with precision and intelligence. "
    "Be concise and direct. "
    "Strictly obey the configured response language. "
    "If the image contains an object in the user's hand, identify the most likely object first, "
    "then give one short supporting detail."
)


def _vision_language_instruction() -> str:
    try:
        return get_friday_response_language_instruction()
    except Exception:
        return "Her zaman Türkçe cevap ver."


def _ai_provider() -> str:
    try:
        return str(get_friday_ai_provider() or "gemini").lower().strip()
    except Exception:
        return "gemini"


def _openai_available() -> bool:
    try:
        return bool(str(get_openai_api_key() or "").strip())
    except Exception:
        return False


def _should_use_openai_vision() -> bool:
    # OpenAI mode uses OpenAI immediately. Auto mode keeps Gemini primary and
    # falls back to OpenAI only if Gemini vision session cannot start.
    return _ai_provider() == "openai"


def _speak_openai_result(params: dict, player, text: str) -> None:
    cb = params.get("_speak_callback") if isinstance(params, dict) else None
    try:
        if callable(cb):
            cb(text)
            return
    except Exception as exc:
        print(f"[Vision] ⚠️  speak callback failed: {exc}")
    try:
        from tools.friday_local_tts import speak_text_async
        speak_text_async(text, muted=bool(getattr(player, "muted", False)))
    except Exception as exc:
        print(f"[Vision] ⚠️  local TTS skipped: {exc}")


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"

def _capture_screen() -> tuple[bytes, str]:

    if not _MSS:
        raise RuntimeError("mss is not installed. Run: pip install mss")

    with mss.mss() as sct:
        monitors = sct.monitors          # [0] = all combined, [1..n] = real screens
        target   = monitors[1] if len(monitors) > 1 else monitors[0]
        shot     = sct.grab(target)
        png      = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(png, "PNG")


def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW    
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION  
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, _IMG_MAX_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _IMG_MAX_H)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")

    for _ in range(3):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"


def _capture_ui_camera_snapshot(player, total_wait: float = 2.4) -> tuple[bytes, str]:
    """
    Capture the latest JPEG frame produced by the Qt camera HUD.

    The Qt signal that opens the camera is asynchronous; on Windows the first
    frame may arrive a few hundred ms after start_camera_mode() returns.
    This helper uses a fast first attempt, then a short retry window so the
    first user command does not fail with 'Kamera frame hazır değil'.
    """
    if player is None or not hasattr(player, "capture_camera_snapshot"):
        raise RuntimeError("UI camera snapshot bridge is not available")

    last_error: Exception | None = None
    deadline = time.time() + max(0.35, float(total_wait or 2.4))
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        remaining = max(0.12, deadline - time.time())
        # First attempt is intentionally very quick. Retries wait a bit longer
        # only when the camera has just been opened.
        wait = min(0.38 if attempt == 1 else 0.72, remaining)
        try:
            image_bytes, mime_type = player.capture_camera_snapshot(wait_seconds=wait)
            image_bytes, mime_type = _compress(image_bytes, "JPEG")
            if image_bytes and len(image_bytes) > 1024:
                if attempt > 1:
                    print(f"[Vision] ✅ UI camera snapshot became ready on retry #{attempt}")
                return image_bytes, mime_type
            last_error = RuntimeError("UI camera snapshot is empty")
        except Exception as exc:
            last_error = exc
            print(f"[Vision] ⏳ UI camera not ready yet ({attempt}): {exc}")
        time.sleep(0.04)

    raise RuntimeError(str(last_error or "Kamera frame hazır değil"))


class _VisionSession:
    def __init__(self):
        self._loop:       Optional[asyncio.AbstractEventLoop] = None
        self._thread:     Optional[threading.Thread]          = None
        self._session                                          = None
        self._out_queue:  Optional[asyncio.Queue]             = None
        self._audio_in:   Optional[asyncio.Queue]             = None
        self._ready_evt:  threading.Event                     = threading.Event()
        self._player                                           = None
        self._lock:       threading.Lock                       = threading.Lock()
        self._request_id: int                                   = 0
        self._active_request_id: int                            = 0
        self._discard_response_until_turn_complete: bool        = False
        self._last_send_error_ts: float                         = 0.0

    def start(self, player=None, timeout: float = 12.0) -> None:
        with self._lock:
            if player is not None:
                self._player = player

            if self._thread and self._thread.is_alive():
                should_start = False
            else:
                should_start = True
                self._ready_evt.clear()
                self._thread = threading.Thread(
                    target=self._run_event_loop,
                    daemon=True,
                    name="VisionSessionThread",
                )
                self._thread.start()

        # Even if the thread already exists, wait until the Live session is really ready.
        if not self._ready_evt.wait(timeout=timeout):
            raise RuntimeError(f"Vision session did not connect within {timeout}s.")
        print("[Vision] ✅ Session ready")

    def analyze(self, image_bytes: bytes, mime_type: str, user_text: str) -> None:
        if not self._loop or not self._out_queue:
            print("[Vision] ⚠️  Session not started — dropping request")
            return
        with self._lock:
            self._request_id += 1
            request_id = self._request_id
        asyncio.run_coroutine_threadsafe(
            self._queue_latest_request(request_id, image_bytes, mime_type, user_text),
            self._loop,
        )

    def cancel_pending(self) -> None:
        """Cancel queued vision work and mute any stale response still arriving."""
        with self._lock:
            self._request_id += 1
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._cancel_now(), self._loop)

    def is_ready(self) -> bool:
        return self._session is not None

    async def _drain_queue(self, queue: Optional[asyncio.Queue]) -> None:
        if queue is None:
            return
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            except Exception:
                break

    async def _cancel_now(self) -> None:
        self._active_request_id = self._request_id
        self._discard_response_until_turn_complete = True
        await self._drain_queue(self._out_queue)
        await self._drain_queue(self._audio_in)

    async def _queue_latest_request(self, request_id: int, image_bytes: bytes, mime_type: str, user_text: str) -> None:
        # Latest-wins: a new visual command immediately removes old queued frames and old audio.
        self._active_request_id = request_id
        self._discard_response_until_turn_complete = True
        await self._drain_queue(self._out_queue)
        await self._drain_queue(self._audio_in)
        await self._out_queue.put((request_id, image_bytes, mime_type, user_text))

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_loop())
        except Exception as exc:
            # Do not let a temporary Google Live/WebSocket failure kill the
            # vision worker forever. A later request can start a fresh thread.
            print(f"[Vision] ❌ Event loop stopped: {exc}")
        finally:
            self._ready_evt.clear()

    async def _session_loop(self) -> None:
        self._out_queue = asyncio.Queue(maxsize=30)
        self._audio_in  = asyncio.Queue()

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )
        config = gtypes.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            system_instruction=_SYSTEM_PROMPT + "\n" + _vision_language_instruction(),
            speech_config=gtypes.SpeechConfig(
                voice_config=gtypes.VoiceConfig(
                    prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(
                        voice_name=get_friday_voice_name()
                    )
                )
            ),
        )

        backoff = 2.0
        while True:
            try:
                print("[Vision] 🔌 Connecting...")
                async with client.aio.live.connect(
                    model=_LIVE_MODEL, config=config
                ) as session:
                    self._session = session
                    self._ready_evt.set()
                    backoff = 2.0  
                    print("[Vision] ✅ Connected")

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_loop())
                        tg.create_task(self._recv_loop())
                        tg.create_task(self._play_loop())

            except* Exception as eg:
                for exc in eg.exceptions:
                    print(f"[Vision] ⚠️  Session error: {exc}")
            finally:
                self._session = None
                self._ready_evt.clear()
                self._discard_response_until_turn_complete = True
                await self._drain_queue(self._audio_in)

            print(f"[Vision] 🔄 Reconnecting in {backoff:.0f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)

    async def _send_loop(self) -> None:
        while True:
            request_id, image_bytes, mime_type, user_text = await self._out_queue.get()
            if request_id != self._request_id:
                print(f"[Vision] ⏭️  Skipping stale request #{request_id}")
                continue
            if not self._session:
                print("[Vision] ⚠️  No session — requeue after reconnect")
                await asyncio.sleep(0.35)
                if request_id == self._request_id:
                    await self._out_queue.put((request_id, image_bytes, mime_type, user_text))
                continue
            try:
                b64 = base64.b64encode(image_bytes).decode("ascii")
                await asyncio.wait_for(
                    self._session.send_client_content(
                        turns={
                            "parts": [
                                {"inline_data": {"mime_type": mime_type, "data": b64}},
                                {"text": user_text},
                            ]
                        },
                        turn_complete=True,
                    ),
                    timeout=8.0,
                )
                # New turn has been submitted; from this point incoming audio belongs to the latest command.
                self._active_request_id = request_id
                self._discard_response_until_turn_complete = False
                print(f"[Vision] 📤 Sent latest #{request_id} {len(image_bytes):,} bytes")
            except Exception as e:
                # Eski davranış burada sadece print edip devam ediyordu. WebSocket 1011/timeout
                # sonrası session kırık kaldığı için sonraki komutlar 'analiz devam ediyor' hissi veriyordu.
                self._discard_response_until_turn_complete = True
                now = time.time()
                if now - self._last_send_error_ts > 2.5:
                    self._last_send_error_ts = now
                    try:
                        if self._player:
                            self._player.write_log("ERR: Görsel analiz bağlantısı yenileniyor. Lütfen tekrar kameraya bak de.")
                    except Exception:
                        pass
                print(f"[Vision] ⚠️  Send error, forcing reconnect: {e}")
                raise

    async def _recv_loop(self) -> None:
        transcript: list[str] = []
        transcript_request_id = 0
        try:
            async for response in self._session.receive():
                if response.data and not self._discard_response_until_turn_complete:
                    await self._audio_in.put(response.data)

                sc = response.server_content
                if not sc:
                    continue

                if (not self._discard_response_until_turn_complete) and sc.output_transcription and sc.output_transcription.text:
                    chunk = sc.output_transcription.text.strip()
                    if chunk:
                        if transcript_request_id != self._active_request_id:
                            transcript = []
                            transcript_request_id = self._active_request_id
                        transcript.append(chunk)

                if sc.turn_complete:
                    if self._discard_response_until_turn_complete:
                        transcript = []
                        self._discard_response_until_turn_complete = False
                        continue
                    # Eğer bu sırada kullanıcı yeni bir kamera sorusu sorduysa eski turn cevabını yazma/okuma.
                    if transcript_request_id and transcript_request_id != self._request_id:
                        transcript = []
                        continue
                    if transcript and self._player:
                        full = re.sub(r"\s+", " ", " ".join(transcript)).strip()
                        if full:
                            self._player.write_log(f"FRIDAY: {full}")
                            print(f"[Vision] 💬 {full}")
                    transcript = []
                    transcript_request_id = 0

        except Exception as e:
            print(f"[Vision] ⚠️  Recv error: {e}")
            raise  

    def _player_is_muted(self) -> bool:
        try:
            return bool(getattr(self._player, "muted", False))
        except Exception:
            return False

    def _close_audio_stream(self, stream) -> None:
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    def _select_output_device(self, samplerate: int, channels: int, dtype: str = "int16") -> int:
        try:
            devices = sd.query_devices()
        except Exception as exc:
            raise RuntimeError(f"Cannot query audio devices: {exc}") from exc

        candidates: list[int] = []
        try:
            default = sd.default.device
            if isinstance(default, (list, tuple)) and len(default) > 1:
                idx = int(default[1])
                if idx >= 0:
                    candidates.append(idx)
            elif isinstance(default, int) and int(default) >= 0:
                candidates.append(int(default))
        except Exception:
            pass

        try:
            for idx, dev in enumerate(devices):
                try:
                    if int(dev.get("max_output_channels", 0) or 0) > 0:
                        candidates.append(int(idx))
                except Exception:
                    continue
        except Exception:
            pass

        seen: set[int] = set()
        for idx in candidates:
            if idx in seen:
                continue
            seen.add(idx)
            try:
                dev = devices[idx]
                if int(dev.get("max_output_channels", 0) or 0) <= 0:
                    continue
                sd.check_output_settings(
                    device=idx,
                    samplerate=int(samplerate),
                    channels=int(channels),
                    dtype=dtype,
                )
                return int(idx)
            except Exception:
                continue

        raise RuntimeError("No usable audio output device found. Check Windows Sound > Output or reinstall the audio driver.")

    async def _play_loop(self) -> None:
        stream = None
        audio_disabled = False
        next_retry_at = 0.0

        try:
            while True:
                chunk = await self._audio_in.get()

                if self._discard_response_until_turn_complete or self._player_is_muted():
                    if stream is not None:
                        self._close_audio_stream(stream)
                        stream = None
                    continue

                # If the selected/default Windows output device is broken, keep
                # the vision session alive and continue showing transcript logs.
                if audio_disabled and time.monotonic() < next_retry_at:
                    continue

                if stream is None:
                    try:
                        device = self._select_output_device(_RECEIVE_SAMPLE_RATE, _CHANNELS, "int16")
                        stream = sd.RawOutputStream(
                            samplerate=_RECEIVE_SAMPLE_RATE,
                            channels=_CHANNELS,
                            dtype="int16",
                            blocksize=_CHUNK_SIZE,
                            device=device,
                        )
                        stream.start()
                        audio_disabled = False
                        print(f"[Vision] 🔊 Audio output device: {device}")
                    except Exception as e:
                        audio_disabled = True
                        next_retry_at = time.monotonic() + 15.0
                        print(f"[Vision] 🔇 Audio output disabled: {e}")
                        try:
                            if self._player:
                                self._player.write_log("SYS: Vision audio output unavailable. Visual analysis continues in text/log mode.")
                        except Exception:
                            pass
                        self._close_audio_stream(stream)
                        stream = None
                        continue

                try:
                    await asyncio.to_thread(stream.write, chunk)
                except Exception as e:
                    audio_disabled = True
                    next_retry_at = time.monotonic() + 15.0
                    print(f"[Vision] 🔇 Audio output disabled: {e}")
                    self._close_audio_stream(stream)
                    stream = None
                    continue
        finally:
            self._close_audio_stream(stream)


_session      = _VisionSession()
_session_lock = threading.Lock()
_session_up   = False
_openai_vision_lock = threading.Lock()
_openai_vision_generation = 0


def _next_openai_vision_generation() -> int:
    global _openai_vision_generation
    with _openai_vision_lock:
        _openai_vision_generation += 1
        return _openai_vision_generation


def _is_current_openai_vision(token: int) -> bool:
    with _openai_vision_lock:
        return token == _openai_vision_generation


def _ensure_session(player=None) -> None:
    global _session_up
    with _session_lock:
        # If the background vision thread died after a transient Live/WebSocket
        # error, allow the next request to start a clean session.
        if _session_up and not (_session._thread and _session._thread.is_alive()):
            _session_up = False

        if not _session_up:
            _session.start(player=player)
            _session_up = True
        elif player is not None:
            _session._player = player


def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> bool:

    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        print("[Vision] ⚠️  No question provided — aborting")
        return False

    print(f"[Vision] ▶ angle={angle!r}  question='{user_text[:80]}'")

    if angle == "camera":
        try:
            if not bool(get_friday_camera_enabled()):
                msg = get_friday_camera_disabled_message()
                print("[Vision] ⛔ " + msg)
                try:
                    if player:
                        player.write_log("FRIDAY: " + msg)
                except Exception:
                    pass
                if params.get("_return_text"):
                    return msg
                return False
        except Exception:
            pass

    camera_started = bool(params.get("_camera_started"))

    # Put the UI into camera mode immediately, before the remote vision session connects.
    # This makes FRIDAY feel instant even on the first analysis.
    # When the caller already opened the HUD, avoid emitting a duplicate Qt signal/log.
    if angle == "camera" and not camera_started and player is not None and hasattr(player, "start_camera_mode"):
        try:
            player.start_camera_mode(camera_index=None)
            camera_started = True
        except Exception:
            pass

    use_openai_vision = _should_use_openai_vision()

    if not use_openai_vision:
        try:
            _ensure_session(player=player)
        except Exception as e:
            print(f"[Vision] ❌ Could not start Gemini vision session: {e}")
            if _ai_provider() == "auto" and _openai_available():
                use_openai_vision = True
                print("[Vision] ↪ Falling back to OpenAI Vision")
            else:
                return False

    try:
        if angle == "camera":
            # UI kamera modu açıksa aynı kamera cihazını ikinci kez açma.
            # Canlı HUD frame'i JPEG snapshot olarak kullanılır; böylece kamera kilitlenmez.
            if player is not None and hasattr(player, "capture_camera_snapshot"):
                try:
                    # UI zaten kamerayı açtı; aynı cihazı worker thread içinde tekrar açma.
                    # İlk deneme hızlıdır; frame henüz hazır değilse kısa bir retry penceresi kullanılır.
                    image_bytes, mime_type = _capture_ui_camera_snapshot(player, total_wait=4.8)
                    print(f"[Vision] 📷 UI camera snapshot compressed: {len(image_bytes):,} bytes")
                except Exception as ui_exc:
                    print(f"[Vision] ❌ UI camera snapshot failed after retry window: {ui_exc}")
                    try:
                        player.write_log("ERR: Kamera ilk frame'i hazırlayamadı. Nesneyi kameraya tutup tekrar 'kameraya bak' de.")
                    except Exception:
                        pass
                    return False
            else:
                image_bytes, mime_type = _capture_camera()
                print(f"[Vision] 📷 Camera: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Screen: {len(image_bytes):,} bytes")
    except Exception as e:
        print(f"[Vision] ❌ Capture error: {e}")
        return False

    language_guard = _vision_language_instruction()
    analysis_text = (
        f"{language_guard}\n"
        "Yanıtı tek ve net bir cümleyle ver. Emin değilsen 'büyük ihtimalle' de; uzun açıklama yapma.\n"
        f"User request: {user_text}"
    ).strip()

    if use_openai_vision:
        token = _next_openai_vision_generation()
        try:
            if player:
                player.write_log("SYS: OpenAI Vision analizi başlatıldı.")
            from providers.openai_provider import analyze_image_bytes
            result = analyze_image_bytes(image_bytes, mime_type, analysis_text)
            if not _is_current_openai_vision(token):
                print("[OpenAI Vision] ↯ stale result ignored")
                return True
            result = re.sub(r"\s+", " ", str(result or "")).strip()
            if result:
                if params.get("_return_text"):
                    print(f"[OpenAI Vision] 💬 {result}")
                    return result
                if player and not params.get("_silent"):
                    player.write_log(f"FRIDAY: {result}")
                print(f"[OpenAI Vision] 💬 {result}")
                if not params.get("_silent"):
                    _speak_openai_result(params, player, result)
                return True
            raise RuntimeError("OpenAI Vision returned an empty response.")
        except Exception as exc:
            if not _is_current_openai_vision(token):
                print("[OpenAI Vision] ↯ stale error ignored")
                return True
            print(f"[OpenAI Vision] ❌ {exc}")
            if _ai_provider() == "openai":
                try:
                    if params.get("_return_text"):
                        return "OpenAI Vision başarısız: " + str(exc)[:180]
                    if player:
                        player.write_log("ERR: OpenAI Vision başarısız — " + str(exc)[:180])
                except Exception:
                    pass
                return False
            # Auto mode: if OpenAI failed, try Gemini as final fallback.
            try:
                _ensure_session(player=player)
            except Exception as gemini_exc:
                print(f"[Vision] ❌ Gemini fallback also failed: {gemini_exc}")
                return False

    _session.analyze(image_bytes, mime_type, analysis_text)
    return True


def cancel_vision_requests() -> None:
    try:
        _next_openai_vision_generation()
    except Exception:
        pass
    try:
        _session.cancel_pending()
    except Exception as e:
        print(f"[Vision] ⚠️  Cancel failed: {e}")


def warmup_session(player=None) -> None:
    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ⚠️  Warmup failed: {e}")

if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (default: screen): ").strip().lower() or "screen"
    q    = input("Question (Enter = default): ").strip() or "What do you see? Be brief."

    t0 = time.perf_counter()
    warmup_session()
    print(f"Session ready in {time.perf_counter()-t0:.2f}s\n")

    t1 = time.perf_counter()
    ok = screen_process({"angle": mode, "text": q})
    print(f"Queued in {time.perf_counter()-t1:.3f}s — waiting for audio...")
    time.sleep(10)
    print("Done." if ok else "Failed.")