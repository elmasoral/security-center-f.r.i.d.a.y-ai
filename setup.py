from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
API_KEYS = CONFIG_DIR / "api_keys.json"
API_KEYS_EXAMPLE = CONFIG_DIR / "api_keys.example.json"
FRIDAY_SETTINGS = CONFIG_DIR / "friday_settings.json"
FRIDAY_SETTINGS_EXAMPLE = CONFIG_DIR / "friday_settings.example.json"
SECURITY_CENTER = CONFIG_DIR / "security_center.json"
SECURITY_CENTER_EXAMPLE = CONFIG_DIR / "security_center.example.json"
FRIDAY_WAKE = CONFIG_DIR / "friday_wake.json"
FRIDAY_WAKE_EXAMPLE = CONFIG_DIR / "friday_wake.example.json"


def run(cmd: list[str]) -> None:
    print("\n> " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_example(src: Path, dst: Path) -> dict:
    data = read_json(src)
    if not dst.exists():
        write_json(dst, data)
    return read_json(dst)


def configure() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    api = copy_example(API_KEYS_EXAMPLE, API_KEYS)
    settings = copy_example(FRIDAY_SETTINGS_EXAMPLE, FRIDAY_SETTINGS)
    copy_example(SECURITY_CENTER_EXAMPLE, SECURITY_CENTER)
    copy_example(FRIDAY_WAKE_EXAMPLE, FRIDAY_WAKE)

    print("\nMEDPOV Friday Command Center setup")
    print("Gemini API key is required for voice/live AI mode.")
    current_key = api.get("gemini_api_key") or api.get("google_api_key") or ""

    if current_key:
        print("Gemini API key already exists in config/api_keys.json.")
        change = input("Replace it? [y/N]: ").strip().lower()
        if change == "y":
            current_key = ""

    if not current_key:
        key = input("Enter Gemini API key: ").strip()
        if key:
            api["gemini_api_key"] = key
            api["google_api_key"] = key
            api["GOOGLE_API_KEY"] = key

    api.setdefault("friday_voice_name", "Aoede")
    api.setdefault("friday_voice_language", "tr-TR")
    api.setdefault("friday_voice_profile", "female_soft")
    api.setdefault("friday_character_gender", "female")
    api.setdefault("gemini_live_model", "gemini-2.5-flash-native-audio-preview-12-2025")
    write_json(API_KEYS, api)

    settings.setdefault("voice_name", api.get("friday_voice_name", "Aoede"))
    settings.setdefault("voice_language", api.get("friday_voice_language", "tr-TR"))
    settings.setdefault("gemini_model", api.get("gemini_live_model", "gemini-2.5-flash-native-audio-preview-12-2025"))
    settings.setdefault("security_center_base_url", "https://siteadi.com/security-center")
    settings.setdefault("security_center_api_key", "")
    write_json(FRIDAY_SETTINGS, settings)

    print("\nConfiguration files created.")
    print("Security Center URL/API key can be changed later from FRIDAY SETTINGS.")


def main() -> int:
    print("Installing Python requirements...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    print("\nInstalling Playwright Chromium...")
    try:
        run([sys.executable, "-m", "playwright", "install", "chromium"])
    except Exception:
        print("Playwright browser install failed. You can run this later:")
        print("python -m playwright install chromium")

    configure()

    print("\nSetup complete.")
    print("Start FRIDAY with:")
    print("python main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
