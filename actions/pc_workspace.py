from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _PYAUTOGUI = True
except Exception:
    pyautogui = None  # type: ignore
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except Exception:
    pyperclip = None  # type: ignore
    _PYPERCLIP = False

try:
    import psutil
    _PSUTIL = True
except Exception:
    psutil = None  # type: ignore
    _PSUTIL = False

try:
    import pygetwindow as gw
    _PYGETWINDOW = True
except Exception:
    gw = None  # type: ignore
    _PYGETWINDOW = False

try:
    from send2trash import send2trash
    _SEND2TRASH = True
except Exception:
    send2trash = None  # type: ignore
    _SEND2TRASH = False

try:
    import cv2
    import mss
    import numpy as np
    _SCREEN_RECORD = True
except Exception:
    cv2 = None  # type: ignore
    mss = None  # type: ignore
    np = None  # type: ignore
    _SCREEN_RECORD = False

try:
    from tools.friday_pc_settings_store import (
        add_trusted_path,
        ensure_output_roots,
        get_alias_map,
        get_trusted_folders,
        get_trusted_paths,
        is_path_allowed,
        load_pc_settings,
        remove_trusted_path,
        resolve_named_path,
        save_pc_settings,
    )
except Exception:
    from pathlib import Path as _Path
    def load_pc_settings():
        return {
            "enabled": True,
            "trusted_paths": [str(_Path.home())],
            "trusted_folders": [{"name": "Home", "path": str(_Path.home()), "aliases": ["home"], "enabled": True}],
            "backup_root": str(_Path.home() / "Documents" / "MEDPOV_FRIDAY_Backups"),
            "screenshots_root": str(_Path.home() / "Pictures" / "MEDPOV_FRIDAY_Screenshots"),
            "recordings_root": str(_Path.home() / "Pictures" / "MEDPOV_FRIDAY_Recordings"),
            "notes_root": str(_Path.home() / "Documents" / "MEDPOV_FRIDAY_Notes"),
            "allow_read": True, "allow_write": True, "allow_create": True, "allow_copy_move": True,
            "allow_zip_backup": True, "allow_delete_to_trash": True, "allow_app_control": True,
            "allow_open_path": True, "allow_office_control": True, "allow_clipboard": True,
            "allow_screenshot": True, "allow_screen_recording": True, "allow_system_report": True,
            "allow_window_control": True, "screen_recording_max_seconds": 90, "screen_recording_fps": 12,
            "zip_exclude_dirs": [".git", "node_modules", "vendor", "__pycache__"],
            "zip_exclude_exts": [".pyc", ".log", ".tmp"],
        }
    def save_pc_settings(settings): return settings
    def add_trusted_path(path, name="", aliases=None): return load_pc_settings()
    def remove_trusted_path(path): return load_pc_settings()
    def get_trusted_folders(include_disabled=False): return load_pc_settings().get("trusted_folders", [])
    def get_trusted_paths(include_output_roots=True): return [_Path.home()]
    def get_alias_map(): return {"home": _Path.home()}
    def is_path_allowed(path): return str(_Path(path).expanduser().resolve()).startswith(str(_Path.home().resolve()))
    def resolve_named_path(raw, default_key="documents"): return _Path(raw or _Path.home()).expanduser()
    def ensure_output_roots(): pass

_OS = platform.system()


def _fmt_size(num: int | float) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _settings_enabled() -> bool:
    return bool(load_pc_settings().get("enabled", True))


def _check_enabled() -> str | None:
    if not _settings_enabled():
        return "PC Workspace pasif. Arayüzden PC Settings > PC Workspace aktif seçeneğini aç."
    return None


def _flag(key: str, default: bool = True) -> bool:
    return bool(load_pc_settings().get(key, default))


def _read_allowed() -> bool: return _flag("allow_read", True)
def _write_allowed() -> bool: return _flag("allow_write", True)
def _create_allowed() -> bool: return _flag("allow_create", True)
def _copy_move_allowed() -> bool: return _flag("allow_copy_move", True)
def _zip_backup_allowed() -> bool: return _flag("allow_zip_backup", True)
def _delete_allowed() -> bool: return _flag("allow_delete_to_trash", True)
def _apps_allowed() -> bool: return _flag("allow_app_control", True)
def _open_path_allowed() -> bool: return _flag("allow_open_path", True)
def _office_allowed() -> bool: return _flag("allow_office_control", True)
def _clipboard_allowed() -> bool: return _flag("allow_clipboard", True)
def _screenshots_allowed() -> bool: return _flag("allow_screenshot", True)
def _recording_allowed() -> bool: return _flag("allow_screen_recording", True)
def _system_report_allowed() -> bool: return _flag("allow_system_report", True)
def _window_allowed() -> bool: return _flag("allow_window_control", True)


def _resolve_path(path: str | None, *, default_key: str = "documents") -> Path:
    return resolve_named_path(path, default_key=default_key).expanduser()


def _target(path: str | None, name: str | None = "", *, default_key: str = "documents") -> Path:
    base = _resolve_path(path, default_key=default_key)
    text = str(name or "").strip().strip('"')
    return (base / text).expanduser() if text else base.expanduser()


def _allowed_or_message(path: Path) -> str | None:
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        resolved = path.expanduser()
    if not is_path_allowed(resolved):
        rows = []
        for folder in get_trusted_folders(include_disabled=False):
            aliases = ", ".join(str(a) for a in (folder.get("aliases") or [])[:5])
            label = str(folder.get("name") or "Klasör")
            rows.append(f"- {label}: {folder.get('path')}" + (f"  (alias: {aliases})" if aliases else ""))
        roots = "\n".join(rows) or "- Henüz klasör eklenmemiş."
        return f"Access denied: {resolved}\nBu klasörü PC Settings > Güvenilir klasörler alanına ekle veya bir takma ad kullan.\n\nTrusted folders:\n{roots}"
    return None


def _ensure_parent_allowed(path: Path) -> str | None:
    parent = path if path.exists() and path.is_dir() else path.parent
    return _allowed_or_message(parent)


def _operation_denied(setting_name: str) -> str:
    return f"Bu işlem PC Settings içinde kapalı: {setting_name}. Arayüzden açman gerekiyor."


def _safe_filename(text: str, default: str = "friday_file") -> str:
    value = str(text or default).strip()
    keep = []
    for ch in value:
        keep.append(ch if ch.isalnum() or ch in " ._-()[]" else "_")
    clean = "".join(keep).strip(" ._")
    return clean or default


def _iter_files_for_zip(src: Path, exclude_dirs: Iterable[str], exclude_exts: Iterable[str]):
    exclude_dirs_norm = {x.replace("\\", "/").strip("/").lower() for x in exclude_dirs if str(x).strip()}
    exclude_exts_norm = {str(x).lower() for x in exclude_exts if str(x).strip()}
    if src.is_file():
        if src.suffix.lower() not in exclude_exts_norm:
            yield src, src.name
        return
    for file in src.rglob("*"):
        try:
            rel = file.relative_to(src)
        except Exception:
            continue
        rel_norm = str(rel).replace("\\", "/").lower()
        parts = [p.lower() for p in rel.parts]
        if any(part in exclude_dirs_norm for part in parts):
            continue
        if any(rel_norm == ex or rel_norm.startswith(ex + "/") for ex in exclude_dirs_norm):
            continue
        if not file.is_file():
            continue
        if file.suffix.lower() in exclude_exts_norm:
            continue
        yield file, str(rel)


def _make_zip(src: Path, destination: Path | None = None, archive_name: str | None = None) -> str:
    if not _zip_backup_allowed():
        return _operation_denied("ZIP / backup")
    if not src.exists():
        return f"Source not found: {src}"
    denied = _allowed_or_message(src)
    if denied:
        return denied
    if not _write_allowed():
        return _operation_denied("Dosya yazma")

    settings = load_pc_settings()
    ensure_output_roots()
    dest_dir = destination or Path(str(settings.get("backup_root"))).expanduser()
    denied_dest = _ensure_parent_allowed(dest_dir)
    if denied_dest:
        return denied_dest
    dest_dir.mkdir(parents=True, exist_ok=True)

    clean_name = archive_name or f"{_safe_filename(src.stem or src.name)}_{_timestamp()}.zip"
    if not clean_name.lower().endswith(".zip"):
        clean_name += ".zip"
    zip_path = dest_dir / clean_name

    files = list(_iter_files_for_zip(src, settings.get("zip_exclude_dirs", []), settings.get("zip_exclude_exts", [])))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file, rel in files:
            zf.write(file, rel)
    size = zip_path.stat().st_size if zip_path.exists() else 0
    return f"ZIP hazır: {zip_path}\nDosya sayısı: {len(files)}\nBoyut: {_fmt_size(size)}"


def list_trusted_paths() -> str:
    settings = load_pc_settings()
    lines = ["PC Workspace güvenilir klasörleri ve takma adlar:"]
    for folder in get_trusted_folders(include_disabled=True):
        p = Path(str(folder.get("path") or ""))
        exists = "OK" if p.exists() else "YOK"
        enabled = "aktif" if folder.get("enabled", True) else "pasif"
        aliases = ", ".join(str(x) for x in (folder.get("aliases") or []))
        lines.append(f"- [{exists}/{enabled}] {folder.get('name')}: {p}" + (f"  (alias: {aliases})" if aliases else ""))
    lines.append(f"Backup: {settings.get('backup_root')}")
    lines.append(f"Screenshots: {settings.get('screenshots_root')}")
    lines.append(f"Recordings: {settings.get('recordings_root')}")
    lines.append(f"Notes: {settings.get('notes_root')}")
    return "\n".join(lines)


def add_path(path: str, nickname: str = "", aliases: str = "") -> str:
    if not path:
        return "Path boş."
    data = add_trusted_path(path, name=nickname, aliases=aliases)
    label = nickname or Path(path).expanduser().name or "Klasör"
    return f"Güvenilir klasör eklendi/güncellendi:\n{label} → {Path(path).expanduser()}\n\nToplam: {len(data.get('trusted_folders', []))}"


def remove_path(path_or_alias: str) -> str:
    if not path_or_alias:
        return "Path veya takma ad boş."
    data = remove_trusted_path(path_or_alias)
    return f"Güvenilir klasör kaldırıldı:\n{path_or_alias}\n\nToplam: {len(data.get('trusted_folders', []))}"


def alias_help() -> str:
    alias_map = get_alias_map()
    lines = ["Kullanılabilir kısa yollar / takma adlar:"]
    shown: set[str] = set()
    for key, path in sorted(alias_map.items(), key=lambda kv: kv[0]):
        pair = f"{key} → {path}"
        if pair in shown:
            continue
        shown.add(pair)
        lines.append(f"- {pair}")
        if len(lines) >= 50:
            lines.append("... daha fazla alias var")
            break
    return "\n".join(lines)


def list_items(path: str = "documents", max_items: int = 80) -> str:
    if not _read_allowed():
        return _operation_denied("Dosya okuma / listeleme")
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists():
        return f"Path not found: {base}"
    if not base.is_dir():
        return f"Not a directory: {base}"
    rows: List[str] = []
    for item in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:max_items]:
        try:
            if item.is_dir():
                rows.append(f"📁 {item.name}/")
            else:
                rows.append(f"📄 {item.name} ({_fmt_size(item.stat().st_size)})")
        except Exception:
            rows.append(f"? {item.name}")
    if not rows:
        return f"Klasör boş: {base}"
    return f"{base} içeriği ({len(rows)} öğe):\n" + "\n".join(rows)


def tree(path: str = "documents", depth: int = 2, max_items: int = 160) -> str:
    if not _read_allowed():
        return _operation_denied("Dosya okuma / ağaç görünümü")
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists() or not base.is_dir():
        return f"Folder not found: {base}"
    depth = max(1, min(int(depth or 2), 6))
    max_items = max(10, min(int(max_items or 160), 600))
    lines = [str(base)]
    count = 0
    def walk(folder: Path, level: int):
        nonlocal count
        if level > depth or count >= max_items:
            return
        try:
            children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return
        for child in children:
            if child.name.startswith("."):
                continue
            count += 1
            prefix = "  " * level + ("📁 " if child.is_dir() else "📄 ")
            lines.append(prefix + child.name)
            if child.is_dir():
                walk(child, level + 1)
            if count >= max_items:
                lines.append("... limit reached")
                break
    walk(base, 1)
    return "\n".join(lines)


def copy_path(path: str, destination: str, name: str = "") -> str:
    if not _copy_move_allowed():
        return _operation_denied("Kopyalama / taşıma")
    if not _write_allowed():
        return _operation_denied("Dosya yazma")
    src = _target(path, name)
    dst = _resolve_path(destination)
    denied = _allowed_or_message(src)
    if denied:
        return denied
    denied = _ensure_parent_allowed(dst)
    if denied:
        return denied
    if not src.exists():
        return f"Source not found: {src}"
    if dst.exists() and dst.is_dir():
        dst = dst / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            dst = dst.with_name(dst.name + "_copy_" + _timestamp())
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return f"Kopyalandı:\n{src}\n→ {dst}"


def move_path(path: str, destination: str, name: str = "") -> str:
    if not _copy_move_allowed():
        return _operation_denied("Kopyalama / taşıma")
    if not _write_allowed():
        return _operation_denied("Dosya yazma")
    src = _target(path, name)
    dst = _resolve_path(destination)
    denied = _allowed_or_message(src)
    if denied:
        return denied
    denied = _ensure_parent_allowed(dst)
    if denied:
        return denied
    if not src.exists():
        return f"Source not found: {src}"
    if dst.exists() and dst.is_dir():
        dst = dst / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Taşındı:\n{src}\n→ {dst}"


def rename_path(path: str, name: str, new_name: str) -> str:
    if not _copy_move_allowed():
        return _operation_denied("Yeniden adlandırma")
    src = _target(path, name)
    if not new_name:
        return "new_name boş."
    denied = _allowed_or_message(src)
    if denied:
        return denied
    if not src.exists():
        return f"Source not found: {src}"
    dst = src.with_name(_safe_filename(new_name, new_name))
    denied = _ensure_parent_allowed(dst)
    if denied:
        return denied
    src.rename(dst)
    return f"Yeniden adlandırıldı:\n{src.name}\n→ {dst.name}"


def delete_path(path: str, name: str = "") -> str:
    if not _delete_allowed():
        return _operation_denied("Silme / Geri Dönüşüm Kutusu")
    target = _target(path, name)
    denied = _allowed_or_message(target)
    if denied:
        return denied
    if not target.exists():
        return f"Not found: {target}"
    if not _SEND2TRASH:
        return "send2trash yüklü değil. requirements içinde send2trash olmalı. Kalıcı silme güvenlik nedeniyle yapılmadı."
    send2trash(str(target))
    return f"Geri Dönüşüm Kutusu'na taşındı: {target}"


def create_folder(path: str, name: str) -> str:
    if not _create_allowed() or not _write_allowed():
        return _operation_denied("Dosya / klasör oluşturma")
    target = _target(path, name)
    denied = _ensure_parent_allowed(target)
    if denied:
        return denied
    target.mkdir(parents=True, exist_ok=True)
    return f"Klasör oluşturuldu: {target}"


def write_text(path: str, name: str, content: str, append: bool = False) -> str:
    if not _create_allowed() or not _write_allowed():
        return _operation_denied("Dosya yazma")
    if not name:
        name = f"friday_note_{_timestamp()}.txt"
    target = _target(path, name)
    denied = _ensure_parent_allowed(target)
    if denied:
        return denied
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as f:
        f.write(content or "")
        if append:
            f.write("\n")
    return f"Metin dosyası {'güncellendi' if append else 'oluşturuldu'}: {target}"


def read_text(path: str, name: str = "", max_chars: int = 12000) -> str:
    if not _read_allowed():
        return _operation_denied("Dosya okuma")
    target = _target(path, name)
    denied = _allowed_or_message(target)
    if denied:
        return denied
    if not target.exists() or not target.is_file():
        return f"File not found: {target}"
    if target.stat().st_size > 1024 * 1024 * 2:
        return f"Dosya çok büyük: {_fmt_size(target.stat().st_size)}. Güvenlik için ilk 2MB üstü okunmadı."
    text = target.read_text(encoding="utf-8", errors="replace")
    clipped = text[:max_chars]
    suffix = "\n... clipped" if len(text) > max_chars else ""
    return f"{target} içeriği:\n{clipped}{suffix}"


def backup(path: str, name: str = "", archive_name: str = "") -> str:
    src = _target(path, name)
    return _make_zip(src, archive_name=archive_name or None)


def zip_path(path: str, destination: str = "backups", name: str = "", archive_name: str = "") -> str:
    src = _target(path, name)
    dest = _resolve_path(destination, default_key="backups") if destination else None
    return _make_zip(src, destination=dest, archive_name=archive_name or None)


def create_note(title: str = "FRIDAY Note", content: str = "", open_after: bool = False) -> str:
    if not _create_allowed() or not _write_allowed():
        return _operation_denied("Not oluşturma")
    ensure_output_roots()
    settings = load_pc_settings()
    notes = Path(str(settings.get("notes_root"))).expanduser()
    denied = _ensure_parent_allowed(notes)
    if denied:
        return denied
    notes.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(title or "FRIDAY Note", "FRIDAY Note")
    path = notes / f"{safe}_{_timestamp()}.txt"
    body = content or title or "FRIDAY note"
    path.write_text(body, encoding="utf-8")
    if open_after:
        open_path(str(path))
    return f"Not oluşturuldu: {path}"


def screenshot(path: str = "", name: str = "") -> str:
    if not _screenshots_allowed():
        return _operation_denied("Ekran görüntüsü")
    if not _PYAUTOGUI:
        return "PyAutoGUI yüklü değil. requirements içinde pyautogui olmalı."
    ensure_output_roots()
    base = _resolve_path(path or "screenshots", default_key="screenshots")
    denied = _ensure_parent_allowed(base)
    if denied:
        return denied
    base.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(name, f"friday_screenshot_{_timestamp()}")
    if not filename.lower().endswith(".png"):
        filename += ".png"
    target = base / filename
    img = pyautogui.screenshot()
    img.save(target)
    return f"Ekran görüntüsü kaydedildi: {target}"


def screen_record(duration_seconds: int = 10, path: str = "", name: str = "", fps: int = 0) -> str:
    if not _recording_allowed():
        return _operation_denied("Ekran kaydı")
    if not _SCREEN_RECORD:
        return "Ekran kaydı için opencv-python, mss ve numpy gerekli. requirements içinde bu paketler olmalı."
    ensure_output_roots()
    settings = load_pc_settings()
    max_seconds = max(3, int(settings.get("screen_recording_max_seconds") or 90))
    seconds = max(3, min(int(duration_seconds or 10), max_seconds))
    fps = max(3, min(int(fps or settings.get("screen_recording_fps") or 12), 30))
    base = _resolve_path(path or "recordings", default_key="recordings")
    denied = _ensure_parent_allowed(base)
    if denied:
        return denied
    base.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(name, f"friday_screen_record_{_timestamp()}")
    if not filename.lower().endswith(".mp4"):
        filename += ".mp4"
    target = base / filename

    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            width = int(monitor["width"])
            height = int(monitor["height"])
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(target), fourcc, float(fps), (width, height))
            if not writer.isOpened():
                target = target.with_suffix(".avi")
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                writer = cv2.VideoWriter(str(target), fourcc, float(fps), (width, height))
            if not writer.isOpened():
                return "Ekran kaydı başlatılamadı: VideoWriter açılamadı."
            end = time.time() + seconds
            frame_delay = 1.0 / fps
            frames = 0
            while time.time() < end:
                img = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                writer.write(frame)
                frames += 1
                time.sleep(frame_delay)
            writer.release()
        size = target.stat().st_size if target.exists() else 0
        return f"Ekran kaydı kaydedildi: {target}\nSüre: {seconds} sn | FPS: {fps} | Frame: {frames} | Boyut: {_fmt_size(size)}"
    except Exception as exc:
        try:
            writer.release()  # type: ignore[name-defined]
        except Exception:
            pass
        return f"Ekran kaydı hatası: {exc}"


def open_path(path: str = "documents", name: str = "") -> str:
    if not _apps_allowed() or not _open_path_allowed():
        return _operation_denied("Klasör / dosya açma")
    target = _target(path, name)
    denied = _allowed_or_message(target if target.exists() else target.parent)
    if denied:
        return denied
    if not target.exists():
        return f"Path not found: {target}"
    if _OS == "Windows":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif _OS == "Darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return f"Açıldı: {target}"


def _paste_text(text: str) -> str:
    if not _PYAUTOGUI:
        return "PyAutoGUI yüklü değil."
    if _clipboard_allowed() and _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.25)
        pyautogui.hotkey("ctrl", "v")
        return "Metin yapıştırıldı."
    pyautogui.typewrite(text, interval=0.02)
    return "Metin yazıldı."


def open_word(text: str = "", title: str = "FRIDAY Note") -> str:
    if not _apps_allowed() or not _office_allowed():
        return _operation_denied("Word / Office kontrolü")
    if _OS == "Windows":
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "winword"])
        except Exception:
            subprocess.Popen(["cmd", "/c", "start", "", "write"])
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Microsoft Word"])
    else:
        subprocess.Popen(["libreoffice", "--writer"])
    time.sleep(3.0)
    if text:
        return "Word açıldı. " + _paste_text(text)
    return "Word açıldı."


def open_notepad(text: str = "") -> str:
    if not _apps_allowed() or not _office_allowed():
        return _operation_denied("Notepad / metin yazdırma")
    if _OS == "Windows":
        subprocess.Popen(["notepad.exe"])
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "TextEdit"])
    else:
        subprocess.Popen(["xdg-open", str(Path.home())])
    time.sleep(1.2)
    if text:
        return "Notepad açıldı. " + _paste_text(text)
    return "Notepad açıldı."


def clipboard(action: str = "read", text: str = "") -> str:
    if not _clipboard_allowed():
        return _operation_denied("Clipboard")
    if not _PYPERCLIP:
        return "pyperclip yüklü değil."
    action = str(action or "read").lower().strip()
    if action in {"write", "copy", "set"}:
        pyperclip.copy(text or "")
        return "Clipboard'a kopyalandı."
    return "Clipboard içeriği:\n" + (pyperclip.paste() or "")


def disk_usage(path: str = "documents") -> str:
    target = _resolve_path(path)
    denied = _allowed_or_message(target if target.exists() else target.parent)
    if denied:
        return denied
    usage = shutil.disk_usage(target)
    pct = usage.used / usage.total * 100
    return f"Disk kullanım ({target}):\nToplam: {_fmt_size(usage.total)}\nKullanılan: {_fmt_size(usage.used)} ({pct:.1f}%)\nBoş: {_fmt_size(usage.free)}"


def system_report(path: str = "documents") -> str:
    if not _system_report_allowed():
        return _operation_denied("Sistem raporu")
    lines = ["PC sistem raporu:"]
    lines.append(f"OS: {platform.platform()}")
    lines.append(f"Python: {sys.version.split()[0]}")
    if _PSUTIL:
        try:
            lines.append(f"CPU: {psutil.cpu_percent(interval=0.4):.1f}% | Core: {psutil.cpu_count(logical=True)}")
            mem = psutil.virtual_memory()
            lines.append(f"RAM: {_fmt_size(mem.used)} / {_fmt_size(mem.total)} ({mem.percent:.1f}%)")
            try:
                bat = psutil.sensors_battery()
                if bat:
                    lines.append(f"Battery: {bat.percent:.0f}%" + (" charging" if bat.power_plugged else ""))
            except Exception:
                pass
            target = _resolve_path(path)
            if target.exists():
                usage = shutil.disk_usage(target)
                lines.append(f"Disk ({target.anchor or target}): {_fmt_size(usage.free)} boş / {_fmt_size(usage.total)} toplam")
        except Exception as exc:
            lines.append(f"psutil raporu alınamadı: {exc}")
    else:
        lines.append("psutil yüklü değil; CPU/RAM detayı sınırlı.")
    return "\n".join(lines)


def active_window_info() -> str:
    if not _window_allowed():
        return _operation_denied("Pencere kontrolü")
    if not _PYGETWINDOW:
        return "pygetwindow yüklü değil."
    try:
        win = gw.getActiveWindow()
        if not win:
            return "Aktif pencere bulunamadı."
        return f"Aktif pencere:\nBaşlık: {win.title}\nKonum: {win.left},{win.top}\nBoyut: {win.width}x{win.height}"
    except Exception as exc:
        return f"Pencere bilgisi alınamadı: {exc}"


def find_files(path: str = "documents", name: str = "", extension: str = "", max_results: int = 50) -> str:
    if not _read_allowed():
        return _operation_denied("Dosya arama")
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists() or not base.is_dir():
        return f"Folder not found: {base}"
    needle = str(name or "").lower().strip()
    ext = str(extension or "").lower().strip()
    if ext and not ext.startswith("."):
        ext = "." + ext
    results: List[Path] = []
    settings = load_pc_settings()
    excluded = {str(x).lower() for x in settings.get("zip_exclude_dirs", [])}
    for item in base.rglob("*"):
        if len(results) >= max(1, min(int(max_results or 50), 200)):
            break
        try:
            rel_parts = [p.lower() for p in item.relative_to(base).parts]
            if any(p in excluded for p in rel_parts):
                continue
            if item.is_file() and (not needle or needle in item.name.lower()) and (not ext or item.suffix.lower() == ext):
                results.append(item)
        except Exception:
            continue
    if not results:
        return "Eşleşen dosya bulunamadı."
    return f"{base} içinde bulunan {len(results)} sonuç:\n" + "\n".join(f"- {p}" for p in results)


def recent_files(path: str = "documents", count: int = 20) -> str:
    if not _read_allowed():
        return _operation_denied("Son dosyalar")
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists() or not base.is_dir():
        return f"Folder not found: {base}"
    files: List[tuple[float, Path]] = []
    for item in base.rglob("*"):
        try:
            if item.is_file():
                files.append((item.stat().st_mtime, item))
        except Exception:
            continue
    files.sort(reverse=True, key=lambda x: x[0])
    top = files[:max(1, min(int(count or 20), 80))]
    if not top:
        return "Dosya bulunamadı."
    lines = [f"{base} son değişen dosyalar:"]
    for mtime, p in top:
        lines.append(f"- {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')} | {p.name} | {p.parent}")
    return "\n".join(lines)


def largest_files(path: str = "documents", count: int = 10) -> str:
    if not _read_allowed():
        return _operation_denied("Büyük dosya taraması")
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists() or not base.is_dir():
        return f"Folder not found: {base}"
    files: List[tuple[int, Path]] = []
    for item in base.rglob("*"):
        try:
            if item.is_file():
                files.append((item.stat().st_size, item))
        except Exception:
            continue
    files.sort(reverse=True, key=lambda x: x[0])
    top = files[:max(1, min(int(count or 10), 50))]
    if not top:
        return "Dosya bulunamadı."
    lines = [f"{base} en büyük dosyalar:"]
    for size, p in top:
        lines.append(f"- {_fmt_size(size):>10} | {p.name} | {p.parent}")
    return "\n".join(lines)


def project_summary(path: str = "documents") -> str:
    if not _read_allowed():
        return _operation_denied("Proje özeti")
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists() or not base.is_dir():
        return f"Folder not found: {base}"
    file_count = 0
    dir_count = 0
    total_size = 0
    by_ext: dict[str, int] = {}
    for item in base.rglob("*"):
        try:
            if item.is_dir():
                dir_count += 1
            elif item.is_file():
                file_count += 1
                total_size += item.stat().st_size
                ext = item.suffix.lower() or "[no ext]"
                by_ext[ext] = by_ext.get(ext, 0) + 1
        except Exception:
            continue
    top_ext = sorted(by_ext.items(), key=lambda kv: kv[1], reverse=True)[:10]
    lines = [f"Proje/klasör özeti: {base}", f"Klasör: {dir_count}", f"Dosya: {file_count}", f"Toplam boyut: {_fmt_size(total_size)}"]
    if top_ext:
        lines.append("En çok görülen uzantılar:")
        lines.extend(f"- {ext}: {cnt}" for ext, cnt in top_ext)
    return "\n".join(lines)


def pc_workspace(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").lower().strip()
    if player:
        try:
            player.write_log(f"[PC Workspace] {action}")
        except Exception:
            pass

    disabled = _check_enabled()
    if disabled and action not in {"status", "list_paths", "trusted_paths", "add_path", "remove_path", "settings", "aliases", "alias_help"}:
        return disabled

    try:
        if action in {"status", "settings"}:
            s = load_pc_settings()
            return (
                "PC Workspace durumu:\n"
                f"Aktif: {bool(s.get('enabled', True))}\n"
                f"Read/List/Search: {bool(s.get('allow_read', True))}\n"
                f"Write/Create: {bool(s.get('allow_write', True))}/{bool(s.get('allow_create', True))}\n"
                f"Copy/Move: {bool(s.get('allow_copy_move', True))}\n"
                f"ZIP/Backup: {bool(s.get('allow_zip_backup', True))}\n"
                f"Screenshot/Record: {bool(s.get('allow_screenshot', True))}/{bool(s.get('allow_screen_recording', True))}\n"
                f"Office/App: {bool(s.get('allow_office_control', True))}/{bool(s.get('allow_app_control', True))}\n"
                f"System report: {bool(s.get('allow_system_report', True))}\n\n"
                + list_trusted_paths()
            )
        if action in {"list_paths", "trusted_paths"}:
            return list_trusted_paths()
        if action in {"aliases", "alias_help"}:
            return alias_help()
        if action == "add_path":
            return add_path(str(params.get("path") or ""), str(params.get("nickname") or params.get("name") or ""), str(params.get("aliases") or ""))
        if action == "remove_path":
            return remove_path(str(params.get("path") or params.get("nickname") or params.get("name") or ""))
        if action == "list":
            return list_items(str(params.get("path") or "documents"), int(params.get("max_items") or 80))
        if action == "tree":
            return tree(str(params.get("path") or "documents"), int(params.get("depth") or 2), int(params.get("max_items") or 160))
        if action == "copy":
            return copy_path(str(params.get("path") or ""), str(params.get("destination") or ""), str(params.get("name") or ""))
        if action == "move":
            return move_path(str(params.get("path") or ""), str(params.get("destination") or ""), str(params.get("name") or ""))
        if action == "rename":
            return rename_path(str(params.get("path") or ""), str(params.get("name") or ""), str(params.get("new_name") or ""))
        if action in {"delete", "trash", "delete_to_trash"}:
            return delete_path(str(params.get("path") or ""), str(params.get("name") or ""))
        if action in {"create_folder", "mkdir"}:
            return create_folder(str(params.get("path") or "documents"), str(params.get("name") or ""))
        if action in {"write", "write_text", "create_file"}:
            return write_text(str(params.get("path") or "documents"), str(params.get("name") or ""), str(params.get("content") or params.get("text") or ""), bool(params.get("append", False)))
        if action in {"append", "append_text"}:
            return write_text(str(params.get("path") or "documents"), str(params.get("name") or ""), str(params.get("content") or params.get("text") or ""), True)
        if action in {"read", "read_text"}:
            return read_text(str(params.get("path") or "documents"), str(params.get("name") or ""), int(params.get("max_chars") or 12000))
        if action in {"backup", "backup_zip"}:
            return backup(str(params.get("path") or ""), str(params.get("name") or ""), str(params.get("archive_name") or ""))
        if action in {"zip", "make_zip"}:
            return zip_path(str(params.get("path") or ""), str(params.get("destination") or "backups"), str(params.get("name") or ""), str(params.get("archive_name") or ""))
        if action in {"note", "create_note"}:
            return create_note(str(params.get("title") or "FRIDAY Note"), str(params.get("content") or params.get("text") or ""), bool(params.get("open_after", False)))
        if action == "screenshot":
            return screenshot(str(params.get("path") or ""), str(params.get("name") or ""))
        if action in {"screen_record", "record_screen", "screen_recording"}:
            return screen_record(int(params.get("duration_seconds") or params.get("seconds") or 10), str(params.get("path") or ""), str(params.get("name") or ""), int(params.get("fps") or 0))
        if action == "open_path":
            return open_path(str(params.get("path") or "documents"), str(params.get("name") or ""))
        if action == "open_word":
            return open_word(str(params.get("text") or params.get("content") or ""), str(params.get("title") or "FRIDAY Note"))
        if action == "open_notepad":
            return open_notepad(str(params.get("text") or params.get("content") or ""))
        if action == "clipboard":
            return clipboard(str(params.get("mode") or params.get("clipboard_action") or "read"), str(params.get("text") or params.get("content") or ""))
        if action == "disk_usage":
            return disk_usage(str(params.get("path") or "documents"))
        if action in {"system_report", "pc_report", "system_status"}:
            return system_report(str(params.get("path") or "documents"))
        if action in {"active_window", "window_info"}:
            return active_window_info()
        if action == "find":
            return find_files(str(params.get("path") or "documents"), str(params.get("name") or ""), str(params.get("extension") or ""), int(params.get("max_results") or 50))
        if action in {"recent", "recent_files"}:
            return recent_files(str(params.get("path") or "documents"), int(params.get("count") or 20))
        if action in {"largest", "largest_files"}:
            return largest_files(str(params.get("path") or "documents"), int(params.get("count") or 10))
        if action in {"summary", "project_summary"}:
            return project_summary(str(params.get("path") or "documents"))
        return f"Unknown pc_workspace action: '{action}'"
    except Exception as exc:
        return f"PC Workspace error ({action}): {exc}"
