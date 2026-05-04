from __future__ import annotations

import json
import os
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

DEFAULT_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_SECURITY_CENTER_BASE_URL = "https://siteadi.com/security-center"


def run(cmd: list[str], allow_fail: bool = False) -> None:
    print("\n> " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0 and not allow_fail:
        raise subprocess.CalledProcessError(result.returncode, cmd)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
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


def pick_existing_gemini_key(api: dict, settings: dict) -> str:
    settings_gemini = settings.get("gemini") if isinstance(settings.get("gemini"), dict) else {}

    return str(
        api.get("gemini_api_key")
        or api.get("google_api_key")
        or api.get("GOOGLE_API_KEY")
        or settings_gemini.get("api_key")
        or ""
    ).strip()


def sync_configs_without_prompt() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    api = copy_example(API_KEYS_EXAMPLE, API_KEYS)
    settings = copy_example(FRIDAY_SETTINGS_EXAMPLE, FRIDAY_SETTINGS)
    security_center = copy_example(SECURITY_CENTER_EXAMPLE, SECURITY_CENTER)
    copy_example(FRIDAY_WAKE_EXAMPLE, FRIDAY_WAKE)

    existing_key = pick_existing_gemini_key(api, settings)

    # api_keys.json
    if existing_key:
        api["gemini_api_key"] = existing_key
        api["google_api_key"] = existing_key
        api["GOOGLE_API_KEY"] = existing_key
    else:
        api.setdefault("gemini_api_key", "")
        api.setdefault("google_api_key", "")
        api.setdefault("GOOGLE_API_KEY", "")

    api.setdefault("os_system", "windows")
    api.setdefault("friday_voice_name", "Aoede")
    api.setdefault("friday_voice_language", "tr-TR")
    api.setdefault("friday_voice_profile", "female_soft")
    api.setdefault("friday_character_gender", "female")
    api.setdefault("gemini_live_model", DEFAULT_MODEL)

    write_json(API_KEYS, api)

    # friday_settings.json
    settings.setdefault("voice", {})
    settings["voice"].setdefault("name", api.get("friday_voice_name", "Aoede"))
    settings["voice"].setdefault("language", api.get("friday_voice_language", "tr-TR"))
    settings["voice"].setdefault("character_gender", api.get("friday_character_gender", "female"))

    settings.setdefault("gemini", {})
    if existing_key:
        settings["gemini"]["api_key"] = existing_key
    else:
        settings["gemini"].setdefault("api_key", "")

    settings["gemini"].setdefault("model", api.get("gemini_live_model", DEFAULT_MODEL))

    settings.setdefault("security_center", {})
    settings["security_center"].setdefault("base_url", DEFAULT_SECURITY_CENTER_BASE_URL)
    settings["security_center"].setdefault(
        "api_url",
        DEFAULT_SECURITY_CENTER_BASE_URL.rstrip("/") + "/admin/api/remote-access.php"
    )
    settings["security_center"].setdefault("api_key", "")
    settings["security_center"].setdefault("timeout", 25)

    write_json(FRIDAY_SETTINGS, settings)

    # security_center.json
    security_center.setdefault("base_url", settings["security_center"]["base_url"])
    security_center.setdefault("api_url", settings["security_center"]["api_url"])
    security_center.setdefault("api_key", settings["security_center"].get("api_key", ""))
    security_center.setdefault("timeout", settings["security_center"].get("timeout", 25))

    write_json(SECURITY_CENTER, security_center)


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_desktop_shortcut() -> None:
    if os.name != "nt":
        return

    target = ROOT / "start_friday.bat"
    if not target.exists():
        print("Desktop shortcut skipped: start_friday.bat not found.")
        return

    icon_candidates = [
        ROOT / "assets" / "friday.ico",
        ROOT / "public" / "friday.ico",
        ROOT / "friday.ico",
    ]

    icon_path = None
    for candidate in icon_candidates:
        if candidate.exists():
            icon_path = candidate
            break

    icon_location = str(icon_path) if icon_path else str(target)

    ps = f"""
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop 'FRIDAY AI.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = {ps_quote(str(target))}
$Shortcut.WorkingDirectory = {ps_quote(str(ROOT))}
$Shortcut.Description = 'MEDPOV F.R.I.D.A.Y AI Command Center'
$Shortcut.IconLocation = {ps_quote(icon_location)}
$Shortcut.Save()
Write-Host "Desktop shortcut created: $ShortcutPath"
"""

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=False,
        )
    except Exception as exc:
        print(f"Desktop shortcut skipped: {exc}")


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

    print("\nPreparing local configuration files...")
    sync_configs_without_prompt()

    print("\nCreating desktop shortcut...")
    create_desktop_shortcut()

    print("\nSetup complete.")
    print("Gemini API key will be requested inside the FRIDAY interface on first launch.")
    print("Start FRIDAY with:")
    print("start_friday.bat")
    print("or")
    print(".\\.venv\\Scripts\\python.exe main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())