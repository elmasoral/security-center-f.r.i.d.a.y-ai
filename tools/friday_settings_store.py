from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "friday_settings.json"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"
SECURITY_CENTER_PATH = CONFIG_DIR / "security_center.json"

DEFAULT_SECURITY_CENTER_BASE_URL = "https://siteadi.com/security-center"
DEFAULT_SECURITY_CENTER_API_KEY = ""
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_VOICE = "Aoede"
DEFAULT_LANGUAGE = "tr-TR"
DEFAULT_RESPONSE_LANGUAGE = "tr"
DEFAULT_UI_LANGUAGE = "en"
DEFAULT_CAMERA_ENABLED = True
DEFAULT_AI_PROVIDER = "gemini"
DEFAULT_FALLBACK_PROVIDER = "openai"
DEFAULT_OPENAI_TEXT_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_VISION_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_REALTIME_MODEL = "gpt-realtime"
DEFAULT_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_VOICE = "marin"
DEFAULT_MAP_VIEW_MODE = "2d"
DEFAULT_MAP_LAYER = "dark"
DEFAULT_MAP_MAX_ZOOM = 18

VOICE_OPTIONS: List[Dict[str, str]] = [
    {"name": "Aoede", "group": "Female", "label": "Aoede · Female / soft"},
    {"name": "Leda", "group": "Female", "label": "Leda · Female / clear"},
    {"name": "Kore", "group": "Female", "label": "Kore · Female / balanced"},
    {"name": "Zephyr", "group": "Female", "label": "Zephyr · Female / light"},
    {"name": "Callirrhoe", "group": "Female", "label": "Callirrhoe · Female / premium"},
    {"name": "Autonoe", "group": "Female", "label": "Autonoe · Female / calm"},
    {"name": "Puck", "group": "Male", "label": "Puck · Male / energetic"},
    {"name": "Charon", "group": "Male", "label": "Charon · Male / deep"},
    {"name": "Fenrir", "group": "Male", "label": "Fenrir · Male / strong"},
    {"name": "Orus", "group": "Male", "label": "Orus · Male / professional"},
    {"name": "Iapetus", "group": "Male", "label": "Iapetus · Male / deep"},
    {"name": "Umbriel", "group": "Male", "label": "Umbriel · Male / serious"},
    {"name": "Algieba", "group": "Male", "label": "Algieba · Male / balanced"},
]

OPENAI_REALTIME_VOICE_OPTIONS: List[Dict[str, str]] = [
    {"name": "marin", "group": "Female", "label": "marin · Female / most natural · recommended"},
    {"name": "coral", "group": "Female", "label": "coral · Female / warm"},
    {"name": "shimmer", "group": "Female", "label": "shimmer · Female / bright"},
    {"name": "sage", "group": "Female", "label": "sage · Female / calm"},
    {"name": "cedar", "group": "Male", "label": "cedar · Male / most natural · recommended"},
    {"name": "alloy", "group": "Male", "label": "alloy · Male / balanced"},
    {"name": "ash", "group": "Male", "label": "ash · Male / deep"},
    {"name": "ballad", "group": "Male", "label": "ballad · Male / soft"},
    {"name": "echo", "group": "Male", "label": "echo · Male / clear"},
    {"name": "verse", "group": "Male", "label": "verse · Male / narrator"},
]

DEFAULTS: Dict[str, Any] = {
    "voice": {
        "name": DEFAULT_VOICE,
        "language": DEFAULT_LANGUAGE,
        "character_gender": "female",
    },
    "assistant": {
        "response_language": DEFAULT_RESPONSE_LANGUAGE,
        "ui_language": DEFAULT_UI_LANGUAGE,
        "ai_provider": DEFAULT_AI_PROVIDER,
        "fallback_provider": DEFAULT_FALLBACK_PROVIDER,
    },
    "privacy": {
        "camera_enabled": DEFAULT_CAMERA_ENABLED,
    },
    "map": {
        "view_mode": DEFAULT_MAP_VIEW_MODE,
        "layer": DEFAULT_MAP_LAYER,
        "max_zoom": DEFAULT_MAP_MAX_ZOOM,
    },
    "security_center": {
        "base_url": DEFAULT_SECURITY_CENTER_BASE_URL,
        "api_url": "https://siteadi.com/security-center/admin/api/remote-access.php",
        "api_key": DEFAULT_SECURITY_CENTER_API_KEY,
        "timeout": 25,
    },
    "gemini": {
        "api_key": "",
        "model": DEFAULT_GEMINI_MODEL,
    },
    "openai": {
        "api_key": "",
        "text_model": DEFAULT_OPENAI_TEXT_MODEL,
        "vision_model": DEFAULT_OPENAI_VISION_MODEL,
        "realtime_model": DEFAULT_OPENAI_REALTIME_MODEL,
        "tts_model": DEFAULT_OPENAI_TTS_MODEL,
        "voice": DEFAULT_OPENAI_VOICE,
    },
}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def normalize_security_center_base_url(value: str) -> str:
    """Normalize the customer Security Center base URL.

    FRIDAY must match the web package contract:
    - A plain customer domain becomes /security-center/.
    - An already entered /security-center/ or /main/security-center/ path is kept.
    - A direct /admin/api/remote-access.php endpoint is respected as a direct/root install.
    - Custom folders are never guessed as /main automatically.
    """
    raw = str(value or "").strip()
    if not raw:
        raw = DEFAULT_SECURITY_CENTER_BASE_URL
    if not re.match(r"^https?://", raw, flags=re.I):
        raw = "https://" + raw

    raw = raw.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    endpoint_explicit = bool(re.search(r"/admin/api/remote-access\.php$", raw, flags=re.I))
    if endpoint_explicit:
        raw = re.sub(r"/admin/api/remote-access\.php$", "", raw, flags=re.I).rstrip("/")
    elif re.search(r"/developer-api\.php$", raw, flags=re.I):
        raw = re.sub(r"/developer-api\.php$", "", raw, flags=re.I).rstrip("/")

    match = re.match(r"^(https?://[^/]+)(/.*)?$", raw, flags=re.I)
    if not match:
        return DEFAULT_SECURITY_CENTER_BASE_URL.rstrip("/")

    origin = match.group(1).rstrip("/")
    path = (match.group(2) or "").rstrip("/")
    lower_path = path.lower()
    marker = "/security-center"

    if endpoint_explicit:
        normalized_path = path
    elif marker in lower_path:
        idx = lower_path.index(marker)
        normalized_path = path[:idx + len(marker)]
    else:
        normalized_path = (path + marker) if path else marker

    return (origin + normalized_path).rstrip("/")


def api_url_from_base(base_url: str) -> str:
    return normalize_security_center_base_url(base_url) + "/admin/api/remote-access.php"


def _legacy_to_settings() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    api = _read_json(API_KEYS_PATH)
    if api:
        voice_name = api.get("friday_voice_name") or api.get("voice_name")
        if voice_name:
            merged.setdefault("voice", {})["name"] = str(voice_name)
        voice_lang = api.get("friday_voice_language") or api.get("voice_language")
        if voice_lang:
            merged.setdefault("voice", {})["language"] = str(voice_lang)
        gemini_key = api.get("gemini_api_key") or api.get("GOOGLE_API_KEY") or api.get("google_api_key") or api.get("api_key")
        if gemini_key:
            merged.setdefault("gemini", {})["api_key"] = str(gemini_key)
        gemini_model = api.get("gemini_model") or api.get("model")
        if gemini_model:
            merged.setdefault("gemini", {})["model"] = str(gemini_model)
        openai_key = api.get("openai_api_key") or api.get("OPENAI_API_KEY")
        if openai_key:
            merged.setdefault("openai", {})["api_key"] = str(openai_key)
        openai_text_model = api.get("openai_text_model")
        if openai_text_model:
            merged.setdefault("openai", {})["text_model"] = str(openai_text_model)
        openai_vision_model = api.get("openai_vision_model")
        if openai_vision_model:
            merged.setdefault("openai", {})["vision_model"] = str(openai_vision_model)
        openai_realtime_model = api.get("openai_realtime_model")
        if openai_realtime_model:
            merged.setdefault("openai", {})["realtime_model"] = str(openai_realtime_model)
        openai_tts_model = api.get("openai_tts_model")
        if openai_tts_model:
            merged.setdefault("openai", {})["tts_model"] = str(openai_tts_model)
        openai_voice = api.get("openai_voice")
        if openai_voice:
            merged.setdefault("openai", {})["voice"] = str(openai_voice)
        ai_provider = api.get("friday_ai_provider")
        if ai_provider:
            merged.setdefault("assistant", {})["ai_provider"] = str(ai_provider)
        ui_lang = api.get("friday_ui_language")
        if ui_lang:
            merged.setdefault("assistant", {})["ui_language"] = str(ui_lang)
        if "friday_camera_enabled" in api:
            merged.setdefault("privacy", {})["camera_enabled"] = normalize_camera_enabled(api.get("friday_camera_enabled"))
    sc = _read_json(SECURITY_CENTER_PATH)
    if sc:
        base = sc.get("base_url") or sc.get("security_center_base_url")
        api_url = sc.get("api_url")
        if not base and api_url:
            base = re.sub(r"/admin/api/remote-access\.php$", "", str(api_url).rstrip("/"), flags=re.I)
        if base:
            merged.setdefault("security_center", {})["base_url"] = normalize_security_center_base_url(str(base))
        if api_url:
            merged.setdefault("security_center", {})["api_url"] = str(api_url)
        key = sc.get("api_key") or sc.get("mpsec_api_key") or sc.get("security_center_api_key")
        if key:
            merged.setdefault("security_center", {})["api_key"] = str(key)
        if sc.get("timeout"):
            merged.setdefault("security_center", {})["timeout"] = int(sc.get("timeout") or 25)
    return merged


def load_settings() -> Dict[str, Any]:
    settings = _deep_merge(DEFAULTS, _legacy_to_settings())
    settings = _deep_merge(settings, _read_json(SETTINGS_PATH))
    base = normalize_security_center_base_url(settings.get("security_center", {}).get("base_url", ""))
    settings.setdefault("security_center", {})["base_url"] = base
    settings["security_center"]["api_url"] = api_url_from_base(base)
    if not settings["security_center"].get("api_key"):
        settings["security_center"]["api_key"] = DEFAULT_SECURITY_CENTER_API_KEY
    settings.setdefault("voice", {}).setdefault("name", DEFAULT_VOICE)
    settings.setdefault("voice", {}).setdefault("language", DEFAULT_LANGUAGE)
    settings.setdefault("assistant", {}).setdefault("response_language", DEFAULT_RESPONSE_LANGUAGE)
    settings["assistant"]["response_language"] = normalize_response_language(settings["assistant"].get("response_language"))
    settings["assistant"].setdefault("ui_language", DEFAULT_UI_LANGUAGE)
    settings["assistant"]["ui_language"] = normalize_ui_language(settings["assistant"].get("ui_language"))
    settings.setdefault("privacy", {}).setdefault("camera_enabled", DEFAULT_CAMERA_ENABLED)
    settings["privacy"]["camera_enabled"] = normalize_camera_enabled(settings["privacy"].get("camera_enabled"))
    settings.setdefault("map", {}).setdefault("view_mode", DEFAULT_MAP_VIEW_MODE)
    settings["map"]["view_mode"] = normalize_map_view_mode(settings["map"].get("view_mode"))
    settings["map"].setdefault("layer", DEFAULT_MAP_LAYER)
    settings["map"]["layer"] = normalize_map_layer(settings["map"].get("layer") or settings["map"].get("provider") or settings["map"].get("theme"))
    try:
        settings["map"]["max_zoom"] = max(5, min(19, int(settings["map"].get("max_zoom") or DEFAULT_MAP_MAX_ZOOM)))
    except Exception:
        settings["map"]["max_zoom"] = DEFAULT_MAP_MAX_ZOOM
    settings["assistant"]["ai_provider"] = normalize_ai_provider(settings["assistant"].get("ai_provider"))
    settings["assistant"]["fallback_provider"] = normalize_fallback_provider(settings["assistant"].get("fallback_provider"))
    settings.setdefault("gemini", {}).setdefault("model", DEFAULT_GEMINI_MODEL)
    settings.setdefault("openai", {}).setdefault("text_model", DEFAULT_OPENAI_TEXT_MODEL)
    settings["openai"].setdefault("vision_model", DEFAULT_OPENAI_VISION_MODEL)
    settings["openai"].setdefault("realtime_model", DEFAULT_OPENAI_REALTIME_MODEL)
    settings["openai"].setdefault("tts_model", DEFAULT_OPENAI_TTS_MODEL)
    settings["openai"].setdefault("voice", DEFAULT_OPENAI_VOICE)
    return settings


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    current = load_settings()
    merged = _deep_merge(current, settings if isinstance(settings, dict) else {})
    base = normalize_security_center_base_url(merged.get("security_center", {}).get("base_url", ""))
    merged.setdefault("security_center", {})["base_url"] = base
    merged["security_center"]["api_url"] = api_url_from_base(base)
    merged["security_center"]["timeout"] = int(merged["security_center"].get("timeout") or 25)
    merged.setdefault("assistant", {})["response_language"] = normalize_response_language(
        merged.get("assistant", {}).get("response_language")
    )
    merged["assistant"]["ui_language"] = normalize_ui_language(merged.get("assistant", {}).get("ui_language"))
    merged.setdefault("privacy", {})["camera_enabled"] = normalize_camera_enabled(
        merged.get("privacy", {}).get("camera_enabled")
    )
    merged.setdefault("map", {})["view_mode"] = normalize_map_view_mode(
        merged.get("map", {}).get("view_mode")
    )
    merged["map"]["layer"] = normalize_map_layer(
        merged.get("map", {}).get("layer") or merged.get("map", {}).get("provider") or merged.get("map", {}).get("theme")
    )
    try:
        merged["map"]["max_zoom"] = max(5, min(19, int(merged.get("map", {}).get("max_zoom") or DEFAULT_MAP_MAX_ZOOM)))
    except Exception:
        merged["map"]["max_zoom"] = DEFAULT_MAP_MAX_ZOOM
    merged["assistant"]["ai_provider"] = normalize_ai_provider(merged.get("assistant", {}).get("ai_provider"))
    merged["assistant"]["fallback_provider"] = normalize_fallback_provider(merged.get("assistant", {}).get("fallback_provider"))
    merged.setdefault("openai", {})
    merged["openai"].setdefault("text_model", DEFAULT_OPENAI_TEXT_MODEL)
    merged["openai"].setdefault("vision_model", DEFAULT_OPENAI_VISION_MODEL)
    merged["openai"].setdefault("realtime_model", DEFAULT_OPENAI_REALTIME_MODEL)
    merged["openai"].setdefault("tts_model", DEFAULT_OPENAI_TTS_MODEL)
    merged["openai"].setdefault("voice", DEFAULT_OPENAI_VOICE)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    _mirror_legacy_files(merged)
    return merged


def _mirror_legacy_files(settings: Dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    api = _read_json(API_KEYS_PATH)
    voice = settings.get("voice", {})
    gemini = settings.get("gemini", {})
    api["friday_voice_name"] = str(voice.get("name") or DEFAULT_VOICE)
    api["friday_voice_language"] = str(voice.get("language") or DEFAULT_LANGUAGE)
    female_names = {"Aoede", "Leda", "Kore", "Zephyr", "Callirrhoe", "Autonoe"}
    api["friday_voice_profile"] = "female_soft" if api["friday_voice_name"] in female_names else "male"
    api["friday_character_gender"] = "female" if api["friday_voice_name"] in female_names else "male"
    api["friday_response_language"] = normalize_response_language(
        settings.get("assistant", {}).get("response_language")
    )
    api["friday_ui_language"] = normalize_ui_language(
        settings.get("assistant", {}).get("ui_language")
    )
    api["friday_camera_enabled"] = normalize_camera_enabled(
        settings.get("privacy", {}).get("camera_enabled")
    )
    if gemini.get("api_key"):
        api["gemini_api_key"] = str(gemini.get("api_key") or "")
        api["GOOGLE_API_KEY"] = str(gemini.get("api_key") or "")
        api["google_api_key"] = str(gemini.get("api_key") or "")
    api["gemini_model"] = str(gemini.get("model") or DEFAULT_GEMINI_MODEL)
    assistant = settings.get("assistant", {})
    openai = settings.get("openai", {})
    api["friday_ai_provider"] = normalize_ai_provider(assistant.get("ai_provider"))
    api["friday_fallback_provider"] = normalize_fallback_provider(assistant.get("fallback_provider"))
    if openai.get("api_key"):
        api["openai_api_key"] = str(openai.get("api_key") or "")
        api["OPENAI_API_KEY"] = str(openai.get("api_key") or "")
    api["openai_text_model"] = str(openai.get("text_model") or DEFAULT_OPENAI_TEXT_MODEL)
    api["openai_vision_model"] = str(openai.get("vision_model") or DEFAULT_OPENAI_VISION_MODEL)
    api["openai_realtime_model"] = str(openai.get("realtime_model") or DEFAULT_OPENAI_REALTIME_MODEL)
    api["openai_tts_model"] = str(openai.get("tts_model") or DEFAULT_OPENAI_TTS_MODEL)
    api["openai_voice"] = str(openai.get("voice") or DEFAULT_OPENAI_VOICE)
    API_KEYS_PATH.write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding="utf-8")
    scs = settings.get("security_center", {})
    sec = _read_json(SECURITY_CENTER_PATH)
    sec["base_url"] = str(scs.get("base_url") or DEFAULT_SECURITY_CENTER_BASE_URL)
    sec["api_url"] = str(scs.get("api_url") or api_url_from_base(sec["base_url"]))
    sec["api_key"] = str(scs.get("api_key") or DEFAULT_SECURITY_CENTER_API_KEY)
    sec["timeout"] = int(scs.get("timeout") or 25)
    SECURITY_CENTER_PATH.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_ai_provider(value: Any) -> str:
    raw = str(value or DEFAULT_AI_PROVIDER).strip().lower()
    aliases = {
        "google": "gemini",
        "google_gemini": "gemini",
        "g": "gemini",
        "oai": "openai",
        "open ai": "openai",
        "open-ai": "openai",
        "auto/fallback": "auto",
        "fallback": "auto",
    }
    raw = aliases.get(raw, raw)
    if raw in {"gemini", "openai", "auto"}:
        return raw
    return DEFAULT_AI_PROVIDER


def normalize_fallback_provider(value: Any) -> str:
    raw = normalize_ai_provider(value)
    if raw == "auto":
        return DEFAULT_FALLBACK_PROVIDER
    return raw


def normalize_response_language(value: Any) -> str:
    raw = str(value or DEFAULT_RESPONSE_LANGUAGE).strip().lower()
    if raw in {"en", "eng", "english", "ing", "ingilizce", "en-us", "en-gb"}:
        return "en"
    if raw in {"tr", "turkish", "turkce", "türkçe", "tr-tr"}:
        return "tr"
    return DEFAULT_RESPONSE_LANGUAGE


def normalize_ui_language(value: Any) -> str:
    raw = str(value or DEFAULT_UI_LANGUAGE).strip().lower()
    if raw in {"tr", "turkish", "turkce", "türkçe", "tr-tr"}:
        return "tr"
    if raw in {"en", "eng", "english", "ing", "ingilizce", "en-us", "en-gb"}:
        return "en"
    return DEFAULT_UI_LANGUAGE


def normalize_map_view_mode(value: Any) -> str:
    # The old pseudo-3D/globe mode was removed. Keep accepting legacy values,
    # but always normalize the renderer back to the stable 2D tile map.
    return "2d"


def normalize_map_layer(value: Any) -> str:
    raw = str(value or DEFAULT_MAP_LAYER).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "night": "dark",
        "dark_mode": "dark",
        "koyu": "dark",
        "gece": "dark",
        "default": "dark",
        "osm": "street",
        "openstreetmap": "street",
        "open_street_map": "street",
        "normal": "street",
        "real": "street",
        "gercek": "street",
        "gerçek": "street",
        "map": "street",
        "standard": "street",
        "light_mode": "light",
        "bright": "light",
        "sat": "satellite",
        "satalate": "satellite",
        "satelite": "satellite",
        "satellite_view": "satellite",
        "uydu": "satellite",
        "imagery": "satellite",
        "hybrid": "satellite",
        "voyager_map": "voyager",
    }
    raw = aliases.get(raw, raw)
    if raw in {"dark", "street", "light", "satellite", "voyager"}:
        return raw
    return DEFAULT_MAP_LAYER


def normalize_camera_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"0", "false", "no", "off", "disabled", "disable", "kapali", "kapalı", "hayir", "hayır"}:
        return False
    if raw in {"1", "true", "yes", "on", "enabled", "enable", "acik", "açık", "evet"}:
        return True
    return DEFAULT_CAMERA_ENABLED


def get_friday_voice_name() -> str:
    return str(load_settings().get("voice", {}).get("name") or DEFAULT_VOICE)


def get_friday_voice_language() -> str:
    return str(load_settings().get("voice", {}).get("language") or DEFAULT_LANGUAGE)


def get_friday_response_language() -> str:
    return normalize_response_language(load_settings().get("assistant", {}).get("response_language"))


def get_friday_response_language_label() -> str:
    return "English" if get_friday_response_language() == "en" else "Türkçe"


def get_friday_ui_language() -> str:
    return normalize_ui_language(load_settings().get("assistant", {}).get("ui_language"))


def get_friday_ui_language_label() -> str:
    return "Türkçe" if get_friday_ui_language() == "tr" else "English"


def get_friday_map_view_mode() -> str:
    return normalize_map_view_mode(load_settings().get("map", {}).get("view_mode"))


def get_friday_map_layer() -> str:
    map_settings = load_settings().get("map", {})
    return normalize_map_layer(map_settings.get("layer") or map_settings.get("provider") or map_settings.get("theme"))


def get_friday_map_max_zoom() -> int:
    try:
        return max(5, min(19, int(load_settings().get("map", {}).get("max_zoom") or DEFAULT_MAP_MAX_ZOOM)))
    except Exception:
        return DEFAULT_MAP_MAX_ZOOM


def get_friday_camera_enabled() -> bool:
    return normalize_camera_enabled(load_settings().get("privacy", {}).get("camera_enabled"))


def get_friday_camera_disabled_message() -> str:
    if get_friday_ui_language() == "tr" or get_friday_response_language() == "tr":
        return "Kamera şu anda FRIDAY ayarlarından devre dışı. Kamera açamam; PC Settings veya FRIDAY Settings içinden Camera Access'i etkinleştir."
    return "Camera access is currently disabled in FRIDAY settings. I cannot open the camera until Camera Access is enabled."


def set_friday_camera_enabled(enabled: bool) -> Dict[str, Any]:
    settings = load_settings()
    settings.setdefault("privacy", {})["camera_enabled"] = bool(enabled)
    return save_settings(settings)


def get_friday_response_language_instruction() -> str:
    lang = get_friday_response_language()
    if lang == "en":
        return (
            "Always answer in English. Keep tool results, camera analysis, and normal replies in English. "
            "If the user speaks Turkish, understand it but reply in English unless they explicitly ask for a translation."
        )
    return (
        "Her zaman Türkçe cevap ver. Araç sonuçlarını, kamera analizini ve normal cevapları Türkçe tut. "
        "Görüntü/model çıktısı İngilizce gelse bile kullanıcıya doğal Türkçe olarak aktar."
    )


def get_friday_ai_provider() -> str:
    return normalize_ai_provider(load_settings().get("assistant", {}).get("ai_provider"))


def get_friday_fallback_provider() -> str:
    return normalize_fallback_provider(load_settings().get("assistant", {}).get("fallback_provider"))


def get_friday_ai_provider_label() -> str:
    value = get_friday_ai_provider()
    return {"gemini": "Gemini", "openai": "OpenAI", "auto": "Auto / Fallback"}.get(value, "Gemini")


def get_openai_api_key() -> str:
    value = str(load_settings().get("openai", {}).get("api_key") or "").strip()
    return value or os.getenv("OPENAI_API_KEY", "")


def get_openai_text_model() -> str:
    return str(load_settings().get("openai", {}).get("text_model") or DEFAULT_OPENAI_TEXT_MODEL)


def get_openai_vision_model() -> str:
    return str(load_settings().get("openai", {}).get("vision_model") or DEFAULT_OPENAI_VISION_MODEL)


def get_openai_realtime_model() -> str:
    return str(load_settings().get("openai", {}).get("realtime_model") or DEFAULT_OPENAI_REALTIME_MODEL)


def get_openai_tts_model() -> str:
    return str(load_settings().get("openai", {}).get("tts_model") or DEFAULT_OPENAI_TTS_MODEL)


def get_openai_voice() -> str:
    return str(load_settings().get("openai", {}).get("voice") or DEFAULT_OPENAI_VOICE)


def get_speech_config() -> Dict[str, Any]:
    return {
        "language_code": get_friday_voice_language(),
        "voice_config": {"prebuilt_voice_config": {"voice_name": get_friday_voice_name()}},
    }


def get_gemini_api_key() -> str:
    value = str(load_settings().get("gemini", {}).get("api_key") or "").strip()
    return value or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")


def get_gemini_model() -> str:
    return str(load_settings().get("gemini", {}).get("model") or DEFAULT_GEMINI_MODEL)


def get_security_center_config() -> Dict[str, Any]:
    return dict(load_settings().get("security_center", {}) or {})


def bootstrap_environment() -> Dict[str, Any]:
    settings = load_settings()
    key = str(settings.get("gemini", {}).get("api_key") or "").strip()
    if key:
        os.environ["GEMINI_API_KEY"] = key
        os.environ["GOOGLE_API_KEY"] = key
    model = str(settings.get("gemini", {}).get("model") or DEFAULT_GEMINI_MODEL).strip()
    if model:
        os.environ["FRIDAY_GEMINI_MODEL"] = model
        os.environ["GEMINI_MODEL"] = model
    voice = str(settings.get("voice", {}).get("name") or DEFAULT_VOICE).strip()
    if voice:
        os.environ["FRIDAY_VOICE_NAME"] = voice
    response_language = normalize_response_language(settings.get("assistant", {}).get("response_language"))
    os.environ["FRIDAY_RESPONSE_LANGUAGE"] = response_language
    assistant = settings.get("assistant", {})
    os.environ["FRIDAY_UI_LANGUAGE"] = normalize_ui_language(assistant.get("ui_language"))
    os.environ["FRIDAY_CAMERA_ENABLED"] = "1" if normalize_camera_enabled(settings.get("privacy", {}).get("camera_enabled")) else "0"
    os.environ["FRIDAY_AI_PROVIDER"] = normalize_ai_provider(assistant.get("ai_provider"))
    os.environ["FRIDAY_FALLBACK_PROVIDER"] = normalize_fallback_provider(assistant.get("fallback_provider"))
    openai = settings.get("openai", {})
    if str(openai.get("api_key") or "").strip():
        os.environ["OPENAI_API_KEY"] = str(openai.get("api_key") or "").strip()
    os.environ["FRIDAY_OPENAI_TEXT_MODEL"] = str(openai.get("text_model") or DEFAULT_OPENAI_TEXT_MODEL)
    os.environ["FRIDAY_OPENAI_VISION_MODEL"] = str(openai.get("vision_model") or DEFAULT_OPENAI_VISION_MODEL)
    os.environ["FRIDAY_OPENAI_REALTIME_MODEL"] = str(openai.get("realtime_model") or DEFAULT_OPENAI_REALTIME_MODEL)
    os.environ["FRIDAY_OPENAI_TTS_MODEL"] = str(openai.get("tts_model") or DEFAULT_OPENAI_TTS_MODEL)
    os.environ["FRIDAY_OPENAI_VOICE"] = str(openai.get("voice") or DEFAULT_OPENAI_VOICE)
    return settings


def save_gemini_api_key_everywhere(api_key: str, os_system: str = "windows") -> Dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Gemini API key is empty.")

    settings = load_settings()
    settings.setdefault("gemini", {})
    settings["gemini"]["api_key"] = key
    settings["gemini"].setdefault("model", DEFAULT_GEMINI_MODEL)

    saved = save_settings(settings)

    api = _read_json(API_KEYS_PATH)
    api["gemini_api_key"] = key
    api["google_api_key"] = key
    api["GOOGLE_API_KEY"] = key
    api.setdefault("friday_voice_name", get_friday_voice_name())
    api.setdefault("friday_voice_language", get_friday_voice_language())
    api.setdefault("friday_voice_profile", "female_soft")
    api.setdefault("friday_character_gender", "female")
    api.setdefault("friday_response_language", get_friday_response_language())
    api.setdefault("gemini_live_model", get_gemini_model())
    api["os_system"] = os_system or api.get("os_system", "windows")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    API_KEYS_PATH.write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding="utf-8")

    os.environ["GEMINI_API_KEY"] = key
    os.environ["GOOGLE_API_KEY"] = key

    return saved