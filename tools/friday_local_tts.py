from __future__ import annotations

import os
import re
import threading
import time
from typing import Optional

_TTS_SAMPLE_RATE = 24_000
_TTS_CHANNELS = 1
_TTS_DTYPE = "int16"

_lock = threading.RLock()
_play_lock = threading.RLock()
_generation = 0
_last_error_at = 0.0


def _clean(text: str, max_chars: int = 1_200) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    # Avoid reading internal routing/silence directives aloud.
    text = re.sub(r"Vision module activated\.?\s*Stay completely silent.*$", "", text, flags=re.I).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def _next_generation() -> int:
    global _generation
    with _lock:
        _generation += 1
        return _generation


def _is_current(token: int) -> bool:
    with _lock:
        return token == _generation


def stop_speech() -> None:
    """Invalidate the current cloud/local TTS playback.

    This does not forcibly close a device handle from another thread, but every
    streaming loop checks the token and stops as soon as possible.
    """
    _next_generation()


def _openai_settings() -> tuple[str, str, str, str]:
    try:
        from tools.friday_settings_store import (
            get_openai_api_key,
            get_openai_tts_model,
            get_openai_voice,
            get_friday_response_language,
        )
        key = get_openai_api_key()
        model = get_openai_tts_model()
        voice = get_openai_voice()
        lang = get_friday_response_language()
    except Exception:
        key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("FRIDAY_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        voice = os.getenv("FRIDAY_OPENAI_VOICE", "marin")
        lang = os.getenv("FRIDAY_RESPONSE_LANGUAGE", "tr")
    return (str(key or "").strip(), str(model or "gpt-4o-mini-tts").strip(), str(voice or "marin").strip(), str(lang or "tr").strip())


def _tts_instructions(lang: str) -> str:
    if str(lang).lower().startswith("en"):
        return "Speak naturally, clearly, and confidently. Keep a smooth conversational assistant tone."
    return (
        "Akıcı, doğal ve net Türkçe konuş. Robot gibi okuma; samimi ama profesyonel bir asistan tonu kullan. "
        "Kelimeleri bölmeden, normal konuşma ritmiyle söyle."
    )




def _speech_kwargs(model: str, voice: str, text: str, instructions: str) -> dict:
    return {
        "model": model,
        "voice": voice,
        "input": text,
        "instructions": instructions,
        "response_format": "pcm",
    }


def _speech_kwargs_legacy(model: str, voice: str, text: str) -> dict:
    return {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "pcm",
    }

def _play_pcm_bytes(pcm: bytes, token: int) -> bool:
    if not pcm or not _is_current(token):
        return False
    try:
        import sounddevice as sd  # type: ignore
        with sd.RawOutputStream(
            samplerate=_TTS_SAMPLE_RATE,
            channels=_TTS_CHANNELS,
            dtype=_TTS_DTYPE,
            blocksize=2_048,
        ) as stream:
            step = 4096
            for i in range(0, len(pcm), step):
                if not _is_current(token):
                    break
                stream.write(pcm[i:i + step])
        return True
    except Exception as exc:
        _print_tts_error(f"PCM playback failed: {exc}")
        return False


def _iter_response_bytes(response) -> bytes:
    chunks = []
    if hasattr(response, "iter_bytes"):
        for chunk in response.iter_bytes(chunk_size=4096):
            if chunk:
                chunks.append(bytes(chunk))
        return b"".join(chunks)
    if hasattr(response, "read"):
        data = response.read()
        return bytes(data or b"")
    content = getattr(response, "content", None)
    if content:
        return bytes(content)
    try:
        return bytes(response)  # type: ignore[arg-type]
    except Exception:
        return b""


def _speak_openai_tts(text: str, token: int) -> bool:
    key, model, voice, lang = _openai_settings()
    if not key:
        return False
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        _print_tts_error(f"OpenAI package missing: {exc}")
        return False

    try:
        client = OpenAI(api_key=key)
        instructions = _tts_instructions(lang)

        # Preferred path: streaming_response keeps latency low and plays while the
        # model is still producing audio. Some older SDKs expose only the normal
        # create() method, so we keep a compatibility fallback below.
        speech = getattr(getattr(client, "audio", None), "speech", None)
        if speech is None:
            raise RuntimeError("client.audio.speech is unavailable in this OpenAI SDK version")

        with _play_lock:
            if not _is_current(token):
                return False
            try:
                streaming = getattr(speech, "with_streaming_response", None)
                if streaming is not None:
                    try:
                        response_cm = streaming.create(**_speech_kwargs(model, voice, text, instructions))
                    except TypeError:
                        response_cm = streaming.create(**_speech_kwargs_legacy(model, voice, text))
                    with response_cm as response:
                        try:
                            import sounddevice as sd  # type: ignore
                            with sd.RawOutputStream(
                                samplerate=_TTS_SAMPLE_RATE,
                                channels=_TTS_CHANNELS,
                                dtype=_TTS_DTYPE,
                                blocksize=2_048,
                            ) as stream:
                                for chunk in response.iter_bytes(chunk_size=4096):
                                    if not _is_current(token):
                                        break
                                    if chunk:
                                        stream.write(bytes(chunk))
                            return True
                        except Exception as play_exc:
                            _print_tts_error(f"Streaming playback failed: {play_exc}")
                            return False
            except TypeError:
                # Older SDK signature or voice/model mismatch; try non-streaming.
                pass

            if not _is_current(token):
                return False
            try:
                response = speech.create(**_speech_kwargs(model, voice, text, instructions))
            except TypeError:
                response = speech.create(**_speech_kwargs_legacy(model, voice, text))
            return _play_pcm_bytes(_iter_response_bytes(response), token)
    except Exception as exc:
        _print_tts_error(f"OpenAI TTS unavailable: {exc}")
        return False


def _print_tts_error(message: str) -> None:
    global _last_error_at
    now = time.time()
    if now - _last_error_at > 4.0:
        _last_error_at = now
        print(f"[FRIDAY TTS] {message}")


def _speak_windows_sapi(text: str, token: int) -> bool:
    if os.name != "nt" or not _is_current(token):
        return False
    try:
        # pywin32 path. Initialize COM inside the worker thread when available.
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
            co_uninit = pythoncom.CoUninitialize
        except Exception:
            co_uninit = None
        try:
            try:
                import win32com.client  # type: ignore
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
            except Exception:
                import comtypes.client  # type: ignore
                speaker = comtypes.client.CreateObject("SAPI.SpVoice")
            if not _is_current(token):
                return False
            speaker.Speak(text)
            return True
        finally:
            try:
                if co_uninit:
                    co_uninit()
            except Exception:
                pass
    except Exception as exc:
        _print_tts_error(f"Windows SAPI fallback unavailable: {exc}")
        return False


def speak_text(text: str, muted: bool = False) -> bool:
    """Speak text for non-Gemini provider replies.

    In v2.7.1 OpenAI mode uses OpenAI's cloud TTS instead of Windows SAPI, so the
    voice is much more natural. SAPI remains as an emergency offline fallback.
    """
    if muted:
        return False
    msg = _clean(text)
    if not msg:
        return False
    token = _next_generation()
    if _speak_openai_tts(msg, token):
        return True
    return _speak_windows_sapi(msg, token)


def speak_text_async(text: str, muted: bool = False) -> None:
    threading.Thread(target=speak_text, args=(text, muted), daemon=True, name="FridayOpenAITTS").start()
