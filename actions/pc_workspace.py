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
    from tools.friday_pc_settings_store import (
        add_trusted_path,
        ensure_output_roots,
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
        return {"enabled": True, "trusted_paths": [str(_Path.home())], "backup_root": str(_Path.home() / "Documents" / "MEDPOV_FRIDAY_Backups"), "screenshots_root": str(_Path.home() / "Pictures" / "MEDPOV_FRIDAY_Screenshots"), "notes_root": str(_Path.home() / "Documents" / "MEDPOV_FRIDAY_Notes"), "allow_write": True, "allow_app_control": True, "allow_screenshot": True, "zip_exclude_dirs": [".git", "node_modules", "vendor", "__pycache__"], "zip_exclude_exts": [".pyc", ".log", ".tmp"]}
    def save_pc_settings(settings): return settings
    def add_trusted_path(path): return load_pc_settings()
    def remove_trusted_path(path): return load_pc_settings()
    def get_trusted_paths(include_output_roots=True): return [_Path.home()]
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


def _write_allowed() -> bool:
    return bool(load_pc_settings().get("allow_write", True))


def _apps_allowed() -> bool:
    return bool(load_pc_settings().get("allow_app_control", True))


def _screenshots_allowed() -> bool:
    return bool(load_pc_settings().get("allow_screenshot", True))


def _resolve_path(path: str | None, *, default_key: str = "documents") -> Path:
    return resolve_named_path(path, default_key=default_key).expanduser()


def _target(path: str | None, name: str | None = "", *, default_key: str = "documents") -> Path:
    base = _resolve_path(path, default_key=default_key)
    text = str(name or "").strip()
    return (base / text).expanduser() if text else base.expanduser()


def _allowed_or_message(path: Path) -> str | None:
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        resolved = path.expanduser()
    if not is_path_allowed(resolved):
        roots = "\n".join(f"- {p}" for p in get_trusted_paths(include_output_roots=True))
        return f"Access denied: {resolved}\nBu klasörü PC Settings > Güvenilir klasörler alanına ekle.\n\nTrusted roots:\n{roots}"
    return None


def _ensure_parent_allowed(path: Path) -> str | None:
    parent = path if path.exists() and path.is_dir() else path.parent
    return _allowed_or_message(parent)


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
    if not src.exists():
        return f"Source not found: {src}"
    denied = _allowed_or_message(src)
    if denied:
        return denied
    if not _write_allowed():
        return "PC Workspace write işlemleri pasif. PC Settings içinden aç."

    settings = load_pc_settings()
    ensure_output_roots()
    dest_dir = destination or Path(str(settings.get("backup_root"))).expanduser()
    denied_dest = _ensure_parent_allowed(dest_dir)
    if denied_dest:
        return denied_dest
    dest_dir.mkdir(parents=True, exist_ok=True)

    clean_name = archive_name or f"{src.stem or src.name}_{_timestamp()}.zip"
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
    lines = ["PC Workspace güvenilir klasörleri:"]
    for p in get_trusted_paths(include_output_roots=False):
        exists = "OK" if p.exists() else "YOK"
        lines.append(f"- [{exists}] {p}")
    lines.append(f"Backup: {settings.get('backup_root')}")
    lines.append(f"Screenshots: {settings.get('screenshots_root')}")
    lines.append(f"Notes: {settings.get('notes_root')}")
    return "\n".join(lines)


def add_path(path: str) -> str:
    if not path:
        return "Path boş."
    data = add_trusted_path(path)
    return "Güvenilir klasör eklendi:\n" + str(Path(path).expanduser()) + "\n\nToplam: " + str(len(data.get("trusted_paths", [])))


def remove_path(path: str) -> str:
    if not path:
        return "Path boş."
    data = remove_trusted_path(path)
    return "Güvenilir klasör kaldırıldı:\n" + str(Path(path).expanduser()) + "\n\nToplam: " + str(len(data.get("trusted_paths", [])))


def list_items(path: str = "documents", max_items: int = 80) -> str:
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
    base = _resolve_path(path)
    denied = _allowed_or_message(base)
    if denied:
        return denied
    if not base.exists() or not base.is_dir():
        return f"Folder not found: {base}"
    depth = max(1, min(int(depth or 2), 5))
    max_items = max(10, min(int(max_items or 160), 400))
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
    if not _write_allowed():
        return "PC Workspace write işlemleri pasif. PC Settings içinden aç."
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


def backup(path: str, name: str = "", archive_name: str = "") -> str:
    src = _target(path, name)
    return _make_zip(src, archive_name=archive_name or None)


def zip_path(path: str, destination: str = "backups", name: str = "", archive_name: str = "") -> str:
    src = _target(path, name)
    dest = _resolve_path(destination, default_key="backups") if destination else None
    return _make_zip(src, destination=dest, archive_name=archive_name or None)


def create_note(title: str = "FRIDAY Note", content: str = "", open_after: bool = False) -> str:
    if not _write_allowed():
        return "PC Workspace write işlemleri pasif. PC Settings içinden aç."
    ensure_output_roots()
    settings = load_pc_settings()
    notes = Path(str(settings.get("notes_root"))).expanduser()
    denied = _ensure_parent_allowed(notes)
    if denied:
        return denied
    notes.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in (title or "FRIDAY Note")).strip() or "FRIDAY Note"
    path = notes / f"{safe}_{_timestamp()}.txt"
    body = content or title or "FRIDAY note"
    path.write_text(body, encoding="utf-8")
    if open_after:
        open_path(str(path))
    return f"Not oluşturuldu: {path}"


def screenshot(path: str = "", name: str = "") -> str:
    if not _screenshots_allowed():
        return "Screenshot işlemleri pasif. PC Settings içinden aç."
    if not _PYAUTOGUI:
        return "PyAutoGUI yüklü değil. requirements içinde pyautogui olmalı."
    ensure_output_roots()
    base = _resolve_path(path or "screenshots", default_key="screenshots")
    denied = _ensure_parent_allowed(base)
    if denied:
        return denied
    base.mkdir(parents=True, exist_ok=True)
    filename = name.strip() if name else f"friday_screenshot_{_timestamp()}.png"
    if not filename.lower().endswith(".png"):
        filename += ".png"
    target = base / filename
    img = pyautogui.screenshot()
    img.save(target)
    return f"Ekran görüntüsü kaydedildi: {target}"


def open_path(path: str = "documents", name: str = "") -> str:
    if not _apps_allowed():
        return "Uygulama/klasör açma pasif. PC Settings içinden aç."
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
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.25)
        pyautogui.hotkey("ctrl", "v")
        return "Metin yapıştırıldı."
    pyautogui.typewrite(text, interval=0.02)
    return "Metin yazıldı."


def open_word(text: str = "", title: str = "FRIDAY Note") -> str:
    if not _apps_allowed():
        return "Word/uygulama kontrolü pasif. PC Settings içinden aç."
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
    if not _apps_allowed():
        return "Notepad/uygulama kontrolü pasif. PC Settings içinden aç."
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


def disk_usage(path: str = "documents") -> str:
    target = _resolve_path(path)
    denied = _allowed_or_message(target if target.exists() else target.parent)
    if denied:
        return denied
    usage = shutil.disk_usage(target)
    pct = usage.used / usage.total * 100
    return f"Disk kullanım ({target}):\nToplam: {_fmt_size(usage.total)}\nKullanılan: {_fmt_size(usage.used)} ({pct:.1f}%)\nBoş: {_fmt_size(usage.free)}"


def pc_workspace(parameters: dict | None = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").lower().strip()
    if player:
        try:
            player.write_log(f"[PC Workspace] {action}")
        except Exception:
            pass

    disabled = _check_enabled()
    if disabled and action not in {"status", "list_paths", "add_path", "remove_path", "settings"}:
        return disabled

    try:
        if action in {"status", "settings"}:
            s = load_pc_settings()
            return (
                "PC Workspace durumu:\n"
                f"Aktif: {bool(s.get('enabled', True))}\n"
                f"Write: {bool(s.get('allow_write', True))}\n"
                f"App control: {bool(s.get('allow_app_control', True))}\n"
                f"Screenshot: {bool(s.get('allow_screenshot', True))}\n\n"
                + list_trusted_paths()
            )
        if action in {"list_paths", "trusted_paths"}:
            return list_trusted_paths()
        if action == "add_path":
            return add_path(str(params.get("path") or ""))
        if action == "remove_path":
            return remove_path(str(params.get("path") or ""))
        if action == "list":
            return list_items(str(params.get("path") or "documents"), int(params.get("max_items") or 80))
        if action == "tree":
            return tree(str(params.get("path") or "documents"), int(params.get("depth") or 2), int(params.get("max_items") or 160))
        if action == "copy":
            return copy_path(str(params.get("path") or ""), str(params.get("destination") or ""), str(params.get("name") or ""))
        if action in {"backup", "backup_zip"}:
            return backup(str(params.get("path") or ""), str(params.get("name") or ""), str(params.get("archive_name") or ""))
        if action in {"zip", "make_zip"}:
            return zip_path(str(params.get("path") or ""), str(params.get("destination") or "backups"), str(params.get("name") or ""), str(params.get("archive_name") or ""))
        if action in {"note", "create_note"}:
            return create_note(str(params.get("title") or "FRIDAY Note"), str(params.get("content") or params.get("text") or ""), bool(params.get("open_after", False)))
        if action == "screenshot":
            return screenshot(str(params.get("path") or ""), str(params.get("name") or ""))
        if action == "open_path":
            return open_path(str(params.get("path") or "documents"), str(params.get("name") or ""))
        if action == "open_word":
            return open_word(str(params.get("text") or params.get("content") or ""), str(params.get("title") or "FRIDAY Note"))
        if action == "open_notepad":
            return open_notepad(str(params.get("text") or params.get("content") or ""))
        if action == "disk_usage":
            return disk_usage(str(params.get("path") or "documents"))
        return f"Unknown pc_workspace action: '{action}'"
    except Exception as exc:
        return f"PC Workspace error ({action}): {exc}"
