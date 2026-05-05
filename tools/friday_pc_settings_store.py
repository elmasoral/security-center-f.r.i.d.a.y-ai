from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List

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


def _path_text(path: str | Path) -> str:
    try:
        return str(Path(str(path)).expanduser().resolve())
    except Exception:
        return str(path).strip()


def _slug(text: str) -> str:
    value = str(text or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ı", "i")
    value = re.sub(r"[^a-z0-9]+", "_", value, flags=re.I).strip("_")
    return value


def alias_key(text: str) -> str:
    return _slug(text)


def _nice_name_from_path(path: str | Path, fallback: str = "Klasör") -> str:
    try:
        name = Path(str(path)).expanduser().name.strip()
        return name or fallback
    except Exception:
        return fallback


def _detected_project_paths() -> List[Dict[str, Any]]:
    candidates: List[tuple[str, str, list[str]]] = []
    if os.name == "nt":
        candidates.extend([
            ("MEDPOV", r"C:\MEDPOV", ["medpov", "medpov klasoru", "medpov klasörü"]),
            ("Projelerim", r"C:\wamp64\www", ["projelerim", "projeler", "proje", "wamp", "www", "web projeleri"]),
            ("Laragon", r"C:\laragon\www", ["laragon", "laragon projeleri"]),
            ("XAMPP", r"C:\xampp\htdocs", ["xampp", "htdocs"]),
        ])
    candidates.append(("FRIDAY", str(_base_dir()), ["friday", "friday proje", "uygulama klasoru", "uygulama klasörü"]))

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for name, raw_path, aliases in candidates:
        try:
            p = Path(raw_path).expanduser()
            if not p.exists():
                continue
            resolved = str(p.resolve())
        except Exception:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append({"name": name, "path": resolved, "aliases": aliases, "enabled": True})
    return out


def _default_folder(name: str, path: Path, aliases: Iterable[str]) -> Dict[str, Any]:
    return {"name": name, "path": _path_text(path), "aliases": list(aliases), "enabled": True}


def default_settings() -> Dict[str, Any]:
    folders: List[Dict[str, Any]] = [
        _default_folder("Masaüstü", _desktop(), ["desktop", "masaustu", "masaüstü"]),
        _default_folder("Belgeler", _documents(), ["documents", "belgeler", "dokumanlar", "dökümanlar"]),
        _default_folder("İndirilenler", _downloads(), ["downloads", "indirilenler", "download"]),
    ]
    folders.extend(_detected_project_paths())

    deduped: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()
    for folder in folders:
        path = _path_text(folder.get("path", ""))
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        folder["path"] = path
        deduped.append(folder)

    return {
        "enabled": True,
        "mode": "trusted_paths",
        "trusted_paths": [f["path"] for f in deduped],
        "trusted_folders": deduped,
        "backup_root": str(_documents() / "MEDPOV_FRIDAY_Backups"),
        "screenshots_root": str(_pictures() / "MEDPOV_FRIDAY_Screenshots"),
        "recordings_root": str(_pictures() / "MEDPOV_FRIDAY_Recordings"),
        "notes_root": str(_documents() / "MEDPOV_FRIDAY_Notes"),
        "allow_read": True,
        "allow_write": True,
        "allow_create": True,
        "allow_copy_move": True,
        "allow_zip_backup": True,
        "allow_delete_to_trash": True,
        "allow_app_control": True,
        "allow_open_path": True,
        "allow_office_control": True,
        "allow_clipboard": True,
        "allow_screenshot": True,
        "allow_screen_recording": True,
        "allow_system_report": True,
        "allow_window_control": True,
        "screen_recording_max_seconds": 90,
        "screen_recording_fps": 12,
        "zip_exclude_dirs": [".git", "node_modules", "vendor", "__pycache__", ".venv", "venv", "storage/logs", "dist", "build"],
        "zip_exclude_exts": [".pyc", ".log", ".tmp", ".cache"],
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


def normalize_paths(paths: Any) -> List[str]:
    out: List[str] = []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        paths = []
    for raw in paths:
        if raw is None:
            continue
        if isinstance(raw, dict):
            raw = raw.get("path")
        text = str(raw).strip().strip('"')
        if not text:
            continue
        value = _path_text(text)
        if value not in out:
            out.append(value)
    return out


def normalize_aliases(value: Any, *, extra: Iterable[str] = ()) -> List[str]:
    aliases: List[str] = []
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = re.split(r"[,;|]", value)
    elif isinstance(value, list):
        raw_items = list(value)
    else:
        raw_items = []
    raw_items.extend(list(extra))
    for item in raw_items:
        text = str(item or "").strip()
        key = alias_key(text)
        if key and key not in aliases:
            aliases.append(key)
    return aliases


def normalize_trusted_folders(settings: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    s = settings if settings is not None else load_pc_settings()
    defaults = default_settings()
    raw_folders = s.get("trusted_folders")
    if not isinstance(raw_folders, list):
        raw_folders = []

    folders: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()

    def add_folder(raw: Any, fallback_name: str = "") -> None:
        if isinstance(raw, dict):
            path_raw = raw.get("path") or raw.get("folder") or raw.get("value")
            name = str(raw.get("name") or raw.get("nickname") or fallback_name or _nice_name_from_path(path_raw)).strip()
            aliases = normalize_aliases(raw.get("aliases"), extra=[name, raw.get("nickname", "")])
            enabled = bool(raw.get("enabled", True))
        else:
            path_raw = raw
            name = fallback_name or _nice_name_from_path(str(path_raw))
            aliases = normalize_aliases([], extra=[name])
            enabled = True
        if not path_raw:
            return
        path = _path_text(path_raw)
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        folders.append({
            "name": name or _nice_name_from_path(path),
            "path": path,
            "aliases": aliases,
            "enabled": enabled,
        })

    for folder in raw_folders:
        add_folder(folder)

    # Backward compatibility: old config had trusted_paths as a plain list.
    for path in normalize_paths(s.get("trusted_paths", [])):
        if path not in seen_paths:
            add_folder({"path": path, "name": _nice_name_from_path(path), "aliases": [_nice_name_from_path(path)]})

    # Keep default folders available when the config is brand new.
    if not folders:
        for folder in defaults.get("trusted_folders", []):
            add_folder(folder)

    return folders


def _canonical_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = _merge(default_settings(), settings or {})
    folders = normalize_trusted_folders(cleaned)
    cleaned["trusted_folders"] = folders
    cleaned["trusted_paths"] = [f["path"] for f in folders if f.get("enabled", True)]
    for key in ("backup_root", "screenshots_root", "recordings_root", "notes_root"):
        cleaned[key] = str(Path(str(cleaned.get(key) or default_settings()[key])).expanduser())
    try:
        cleaned["screen_recording_max_seconds"] = max(3, min(int(cleaned.get("screen_recording_max_seconds") or 90), 600))
    except Exception:
        cleaned["screen_recording_max_seconds"] = 90
    try:
        cleaned["screen_recording_fps"] = max(3, min(int(cleaned.get("screen_recording_fps") or 12), 30))
    except Exception:
        cleaned["screen_recording_fps"] = 12
    return cleaned


def load_pc_settings() -> Dict[str, Any]:
    defaults = default_settings()
    try:
        if PC_SETTINGS_PATH.exists():
            loaded = json.loads(PC_SETTINGS_PATH.read_text(encoding="utf-8"))
            return _canonical_settings(_merge(defaults, loaded if isinstance(loaded, dict) else {}))
    except Exception:
        pass
    return _canonical_settings(defaults)


def save_pc_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = _canonical_settings(settings or {})
    PC_SETTINGS_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def get_trusted_folders(include_disabled: bool = False) -> List[Dict[str, Any]]:
    folders = normalize_trusted_folders(load_pc_settings())
    if include_disabled:
        return folders
    return [f for f in folders if f.get("enabled", True)]


def get_alias_map() -> Dict[str, Path]:
    settings = load_pc_settings()
    mapping: Dict[str, Path] = {
        "desktop": _desktop(),
        "masaustu": _desktop(),
        "masaüstü": _desktop(),
        "downloads": _downloads(),
        "indirilenler": _downloads(),
        "documents": _documents(),
        "belgeler": _documents(),
        "home": _home(),
        "pictures": _pictures(),
        "resimler": _pictures(),
        "backups": Path(str(settings.get("backup_root") or default_settings()["backup_root"])),
        "backup": Path(str(settings.get("backup_root") or default_settings()["backup_root"])),
        "yedekler": Path(str(settings.get("backup_root") or default_settings()["backup_root"])),
        "screenshots": Path(str(settings.get("screenshots_root") or default_settings()["screenshots_root"])),
        "screenshot": Path(str(settings.get("screenshots_root") or default_settings()["screenshots_root"])),
        "ekran_goruntuleri": Path(str(settings.get("screenshots_root") or default_settings()["screenshots_root"])),
        "recordings": Path(str(settings.get("recordings_root") or default_settings()["recordings_root"])),
        "recording": Path(str(settings.get("recordings_root") or default_settings()["recordings_root"])),
        "screen_recordings": Path(str(settings.get("recordings_root") or default_settings()["recordings_root"])),
        "ekran_kayitlari": Path(str(settings.get("recordings_root") or default_settings()["recordings_root"])),
        "notes": Path(str(settings.get("notes_root") or default_settings()["notes_root"])),
        "note": Path(str(settings.get("notes_root") or default_settings()["notes_root"])),
        "notlar": Path(str(settings.get("notes_root") or default_settings()["notes_root"])),
    }
    for folder in get_trusted_folders(include_disabled=False):
        path = Path(str(folder.get("path", ""))).expanduser()
        names = [folder.get("name", ""), *(folder.get("aliases") or [])]
        # Extra natural language variants.
        if alias_key(str(folder.get("name", ""))) == "projelerim":
            names.extend(["projeler", "proje", "proje klasoru", "proje klasörü", "web projeleri"])
        for alias in names:
            key = alias_key(str(alias))
            if key:
                mapping[key] = path
    return mapping


def get_trusted_paths(include_output_roots: bool = True) -> List[Path]:
    settings = load_pc_settings()
    raw_paths: List[str] = [f["path"] for f in get_trusted_folders(include_disabled=False)]
    if include_output_roots:
        raw_paths.extend([
            str(settings.get("backup_root") or ""),
            str(settings.get("screenshots_root") or ""),
            str(settings.get("recordings_root") or ""),
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


def add_trusted_path(path: str, name: str = "", aliases: Iterable[str] | str | None = None) -> Dict[str, Any]:
    settings = load_pc_settings()
    folders = normalize_trusted_folders(settings)
    value = _path_text(path)
    nickname = str(name or _nice_name_from_path(value, "Klasör")).strip()
    alias_list = normalize_aliases(aliases or [], extra=[nickname])
    updated = False
    for folder in folders:
        if folder.get("path") == value:
            folder["name"] = nickname
            folder["aliases"] = alias_list
            folder["enabled"] = True
            updated = True
            break
    if not updated and value:
        folders.append({"name": nickname, "path": value, "aliases": alias_list, "enabled": True})
    settings["trusted_folders"] = folders
    return save_pc_settings(settings)


def remove_trusted_path(path_or_alias: str) -> Dict[str, Any]:
    settings = load_pc_settings()
    raw = str(path_or_alias or "").strip()
    key = alias_key(raw)
    try:
        value = _path_text(raw)
    except Exception:
        value = raw
    kept: List[Dict[str, Any]] = []
    for folder in normalize_trusted_folders(settings):
        aliases = set(normalize_aliases(folder.get("aliases"), extra=[folder.get("name", "")]))
        if folder.get("path") == value or (key and key in aliases):
            continue
        kept.append(folder)
    settings["trusted_folders"] = kept
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
    text = str(raw or default_key).strip().strip('"')
    key = alias_key(text)
    alias_map = get_alias_map()
    if key in alias_map:
        return alias_map[key].expanduser()
    # A model may pass Turkish with spaces. Try a partial shortcut only when it is not a real-looking path.
    looks_like_path = (":" in text) or ("\\" in text) or ("/" in text) or text.startswith("~")
    if not looks_like_path:
        for alias, path in alias_map.items():
            if key and (key == alias or key in alias or alias in key):
                return path.expanduser()
    return Path(text).expanduser()


def ensure_output_roots() -> None:
    settings = load_pc_settings()
    for key in ("backup_root", "screenshots_root", "recordings_root", "notes_root"):
        try:
            Path(str(settings.get(key) or default_settings()[key])).expanduser().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
