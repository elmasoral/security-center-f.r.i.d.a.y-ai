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

VOICE_OPTIONS: List[Dict[str, str]] = [
    {"name": "Aoede", "group": "Kadın", "label": "Aoede · Kadın / soft"},
    {"name": "Leda", "group": "Kadın", "label": "Leda · Kadın / net"},
    {"name": "Kore", "group": "Kadın", "label": "Kore · Kadın / dengeli"},
    {"name": "Zephyr", "group": "Kadın", "label": "Zephyr · Kadın / hafif"},
    {"name": "Callirrhoe", "group": "Kadın", "label": "Callirrhoe · Kadın / premium"},
    {"name": "Autonoe", "group": "Kadın", "label": "Autonoe · Kadın / sakin"},
    {"name": "Puck", "group": "Erkek", "label": "Puck · Erkek / enerjik"},
    {"name": "Charon", "group": "Erkek", "label": "Charon · Erkek / tok"},
    {"name": "Fenrir", "group": "Erkek", "label": "Fenrir · Erkek / güçlü"},
    {"name": "Orus", "group": "Erkek", "label": "Orus · Erkek / profesyonel"},
    {"name": "Iapetus", "group": "Erkek", "label": "Iapetus · Erkek / derin"},
    {"name": "Umbriel", "group": "Erkek", "label": "Umbriel · Erkek / ciddi"},
    {"name": "Algieba", "group": "Erkek", "label": "Algieba · Erkek / dengeli"},
]

DEFAULTS: Dict[str, Any] = {
    "voice": {
        "name": DEFAULT_VOICE,
        "language": DEFAULT_LANGUAGE,
        "character_gender": "female",
    },
    "assistant": {
        "response_language": DEFAULT_RESPONSE_LANGUAGE,
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
    raw = str(value or "").strip()
    if not raw:
        raw = DEFAULT_SECURITY_CENTER_BASE_URL
    raw = raw.rstrip("/")
    raw = re.sub(r"/admin/api/remote-access\.php$", "", raw, flags=re.I).rstrip("/")
    return raw


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
    settings.setdefault("gemini", {}).setdefault("model", DEFAULT_GEMINI_MODEL)
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
    if gemini.get("api_key"):
        api["gemini_api_key"] = str(gemini.get("api_key") or "")
        api["GOOGLE_API_KEY"] = str(gemini.get("api_key") or "")
        api["google_api_key"] = str(gemini.get("api_key") or "")
    api["gemini_model"] = str(gemini.get("model") or DEFAULT_GEMINI_MODEL)
    API_KEYS_PATH.write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding="utf-8")
    scs = settings.get("security_center", {})
    sec = _read_json(SECURITY_CENTER_PATH)
    sec["base_url"] = str(scs.get("base_url") or DEFAULT_SECURITY_CENTER_BASE_URL)
    sec["api_url"] = str(scs.get("api_url") or api_url_from_base(sec["base_url"]))
    sec["api_key"] = str(scs.get("api_key") or DEFAULT_SECURITY_CENTER_API_KEY)
    sec["timeout"] = int(scs.get("timeout") or 25)
    SECURITY_CENTER_PATH.write_text(json.dumps(sec, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_response_language(value: Any) -> str:
    raw = str(value or DEFAULT_RESPONSE_LANGUAGE).strip().lower()
    if raw in {"en", "eng", "english", "ing", "ingilizce", "en-us", "en-gb"}:
        return "en"
    if raw in {"tr", "turkish", "turkce", "türkçe", "tr-tr"}:
        return "tr"
    return DEFAULT_RESPONSE_LANGUAGE


def get_friday_voice_name() -> str:
    return str(load_settings().get("voice", {}).get("name") or DEFAULT_VOICE)


def get_friday_voice_language() -> str:
    return str(load_settings().get("voice", {}).get("language") or DEFAULT_LANGUAGE)


def get_friday_response_language() -> str:
    return normalize_response_language(load_settings().get("assistant", {}).get("response_language"))


def get_friday_response_language_label() -> str:
    return "English" if get_friday_response_language() == "en" else "Türkçe"


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