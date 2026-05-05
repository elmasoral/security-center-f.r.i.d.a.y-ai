from __future__ import annotations

import os
import re
import threading


def _clean(text: str, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def speak_text(text: str, muted: bool = False) -> bool:
    """Small Windows local TTS fallback used by non-Gemini providers.

    FRIDAY's native Gemini Live path streams its own audio. OpenAI REST vision/text
    replies are normal text, so this helper reads them locally when possible.
    It fails silently on systems without Windows SAPI.
    """
    if muted:
        return False
    msg = _clean(text)
    if not msg:
        return False
    if os.name != "nt":
        return False
    try:
        try:
            import win32com.client  # type: ignore
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception:
            import comtypes.client  # type: ignore
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")
        speaker.Speak(msg)
        return True
    except Exception as exc:
        print(f"[FRIDAY TTS] Local TTS unavailable: {exc}")
        return False


def speak_text_async(text: str, muted: bool = False) -> None:
    threading.Thread(target=speak_text, args=(text, muted), daemon=True, name="FridayLocalTTS").start()
