from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
PC_SETTINGS_PATH = CONFIG_DIR / "friday_pc_settings.json"


def _home() -> Path:
    return Path.home()


def _desktop() -> Path:
    return _home() / "Desktop"


def _documents() -> Path:
    return _home() / "Documents"


def _downloads() -> Path:
    return _home() / "Downloads"


def _pictures() -> Path:
    return _home() / "Pictures"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _detected_project_paths() -> List[str]:
    candidates = []
    if os.name == "nt":
        candidates.extend([
            r"C:\\MEDPOV",
            r"C:\\wamp64\\www",
            r"C:\\laragon\\www",
            r"C:\\xampp\\htdocs",
        ])
    candidates.append(str(_base_dir()))
    out: List[str] = []
    for raw in candidates:
        try:
            p = Path(raw).expanduser()
            if p.exists() and str(p.resolve()) not in out:
                out.append(str(p.resolve()))
        except Exception:
            continue
    return out


def default_settings() -> Dict[str, Any]:
    trusted = [
        str(_desktop()),
        str(_documents()),
        str(_downloads()),
    ]
    trusted.extend(_detected_project_paths())
    deduped: List[str] = []
    for item in trusted:
        try:
            resolved = str(Path(item).expanduser().resolve())
        except Exception:
            resolved = str(item)
        if resolved not in deduped:
            deduped.append(resolved)

    return {
        "enabled": True,
        "mode": "trusted_paths",
        "trusted_paths": deduped,
        "backup_root": str(_documents() / "MEDPOV_FRIDAY_Backups"),
        "screenshots_root": str(_pictures() / "MEDPOV_FRIDAY_Screenshots"),
        "notes_root": str(_documents() / "MEDPOV_FRIDAY_Notes"),
        "allow_write": True,
        "allow_delete_to_trash": True,
        "allow_app_control": True,
        "allow_screenshot": True,
        "zip_exclude_dirs": [".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "storage/logs"],
        "zip_exclude_exts": [".pyc", ".log", ".tmp"],
    }


def _merge(default: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(default)
    for key, value in (loaded or {}).items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            tmp = dict(data[key])
            tmp.update(value)
            data[key] = tmp
        else:
            data[key] = value
    return data


def load_pc_settings() -> Dict[str, Any]:
    defaults = default_settings()
    try:
        if PC_SETTINGS_PATH.exists():
            loaded = json.loads(PC_SETTINGS_PATH.read_text(encoding="utf-8"))
            return _merge(defaults, loaded if isinstance(loaded, dict) else {})
    except Exception:
        pass
    return defaults


def save_pc_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = _merge(default_settings(), settings or {})
    cleaned["trusted_paths"] = normalize_paths(cleaned.get("trusted_paths", []))
    for key in ("backup_root", "screenshots_root", "notes_root"):
        cleaned[key] = str(Path(str(cleaned.get(key) or default_settings()[key])).expanduser())
    PC_SETTINGS_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def normalize_paths(paths: Any) -> List[str]:
    out: List[str] = []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        paths = []
    for raw in paths:
        if raw is None:
            continue
        text = str(raw).strip().strip('"')
        if not text:
            continue
        try:
            p = Path(text).expanduser().resolve()
            value = str(p)
        except Exception:
            value = text
        if value not in out:
            out.append(value)
    return out


def get_trusted_paths(include_output_roots: bool = True) -> List[Path]:
    settings = load_pc_settings()
    raw_paths: List[str] = list(settings.get("trusted_paths") or [])
    if include_output_roots:
        raw_paths.extend([
            str(settings.get("backup_root") or ""),
            str(settings.get("screenshots_root") or ""),
            str(settings.get("notes_root") or ""),
        ])
    roots: List[Path] = []
    for raw in normalize_paths(raw_paths):
        try:
            p = Path(raw).expanduser().resolve()
            if p not in roots:
                roots.append(p)
        except Exception:
            continue
    return roots


def add_trusted_path(path: str) -> Dict[str, Any]:
    settings = load_pc_settings()
    current = normalize_paths(settings.get("trusted_paths", []))
    try:
        value = str(Path(path).expanduser().resolve())
    except Exception:
        value = str(path).strip()
    if value and value not in current:
        current.append(value)
    settings["trusted_paths"] = current
    return save_pc_settings(settings)


def remove_trusted_path(path: str) -> Dict[str, Any]:
    settings = load_pc_settings()
    try:
        value = str(Path(path).expanduser().resolve())
    except Exception:
        value = str(path).strip()
    settings["trusted_paths"] = [p for p in normalize_paths(settings.get("trusted_paths", [])) if p != value]
    return save_pc_settings(settings)


def is_path_allowed(path: str | Path) -> bool:
    settings = load_pc_settings()
    if not bool(settings.get("enabled", True)):
        return False
    try:
        target = Path(path).expanduser().resolve()
        for root in get_trusted_paths(include_output_roots=True):
            try:
                if target == root or target.is_relative_to(root):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def resolve_named_path(raw: str | None, *, default_key: str = "documents") -> Path:
    settings = load_pc_settings()
    shortcuts = {
        "desktop": _desktop(),
        "downloads": _downloads(),
        "documents": _documents(),
        "home": _home(),
        "pictures": _pictures(),
        "backups": Path(str(settings.get("backup_root") or default_settings()["backup_root"])),
        "backup": Path(str(settings.get("backup_root") or default_settings()["backup_root"])),
        "screenshots": Path(str(settings.get("screenshots_root") or default_settings()["screenshots_root"])),
        "screenshot": Path(str(settings.get("screenshots_root") or default_settings()["screenshots_root"])),
        "notes": Path(str(settings.get("notes_root") or default_settings()["notes_root"])),
        "note": Path(str(settings.get("notes_root") or default_settings()["notes_root"])),
    }
    text = str(raw or default_key).strip().strip('"')
    lower = text.lower()
    if lower in shortcuts:
        return shortcuts[lower].expanduser()
    return Path(text).expanduser()


def ensure_output_roots() -> None:
    settings = load_pc_settings()
    for key in ("backup_root", "screenshots_root", "notes_root"):
        try:
            Path(str(settings.get(key) or default_settings()[key])).expanduser().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
