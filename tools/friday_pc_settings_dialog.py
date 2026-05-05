from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .friday_pc_settings_store import (
    add_trusted_path,
    get_trusted_folders,
    load_pc_settings,
    remove_trusted_path,
    save_pc_settings,
)


class FridayPCSettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MEDPOV FRIDAY PC Settings")
        self.setMinimumSize(930, 760)
        self.settings: Dict[str, Any] = load_pc_settings()
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog { background: #050b12; color: #e7f6ff; }
            QLabel { color: #c9d7e6; background: transparent; }
            QLabel#Title { color:#28e9ff; font-size:18px; font-weight:900; letter-spacing:1px; }
            QLabel#Section { color:#ffb86b; font-weight:900; padding-top:8px; }
            QLabel#Hint { color:#8fa1b8; }
            QLabel#Tiny { color:#7f91aa; font-size:11px; }
            QLineEdit, QTextEdit, QListWidget, QSpinBox {
                background: #07111d;
                color: #f3fbff;
                border: 1px solid rgba(40,233,255,.28);
                border-radius: 9px;
                padding: 8px;
                selection-background-color: #28e9ff;
                selection-color: #04101e;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid rgba(255,255,255,.05); }
            QListWidget::item:selected { background: rgba(40,233,255,.20); color: #ffffff; }
            QCheckBox { color:#c9d7e6; spacing:8px; }
            QCheckBox::indicator { width:16px; height:16px; }
            QPushButton {
                background: #0b1a2a;
                color: #f4fbff;
                border: 1px solid rgba(40,233,255,.34);
                border-radius: 10px;
                padding: 9px 13px;
                font-weight: 800;
            }
            QPushButton:hover { background: #102f45; border-color:#28e9ff; }
            QPushButton#saveBtn { background:#28e9ff; color:#03101a; border-color:#86f7ff; }
            QPushButton#dangerBtn { border-color: rgba(255,112,112,.42); color:#ffc4c4; }
            QPushButton#softBtn { color:#d7f7ff; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(10)

        title = QLabel("PC Workspace Settings")
        title.setObjectName("Title")
        root.addWidget(title)

        hint = QLabel(
            "FRIDAY performs file operations, project backups, screenshots/recordings, notes, Word/Notepad writing and PC control only inside trusted folders added here. "
            "Give each folder a short nickname, for example 'projects' → C:\\wamp64\\www."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        self.enabled = QCheckBox("PC Workspace enabled")
        self.allow_read = QCheckBox("File read / list / search enabled")
        self.allow_write = QCheckBox("File writing enabled")
        self.allow_create = QCheckBox("File / folder creation enabled")
        self.allow_copy_move = QCheckBox("Copy / move / rename enabled")
        self.allow_zip_backup = QCheckBox("ZIP / project backup enabled")
        self.allow_delete = QCheckBox("Delete enabled only via Recycle Bin")
        self.allow_apps = QCheckBox("App and window control enabled")
        self.allow_open_path = QCheckBox("Open trusted folder / file enabled")
        self.allow_office = QCheckBox("Word / Notepad writing enabled")
        self.allow_clipboard = QCheckBox("Clipboard copy / read enabled")
        self.allow_screenshot = QCheckBox("Screenshot capture enabled")
        self.allow_screen_recording = QCheckBox("Screen recording enabled")
        self.allow_system_report = QCheckBox("Disk / RAM / CPU system report enabled")
        self.allow_window_control = QCheckBox("Active window info / control enabled")

        checks = [
            self.enabled, self.allow_read, self.allow_write,
            self.allow_create, self.allow_copy_move, self.allow_zip_backup,
            self.allow_delete, self.allow_apps, self.allow_open_path,
            self.allow_office, self.allow_clipboard, self.allow_screenshot,
            self.allow_screen_recording, self.allow_system_report, self.allow_window_control,
        ]
        for i, cb in enumerate(checks):
            grid.addWidget(cb, i // 2, i % 2)
        root.addLayout(grid)

        paths_label = QLabel("Trusted folders and nicknames")
        paths_label.setObjectName("Section")
        root.addWidget(paths_label)

        tiny = QLabel("Example: enter 'projects' as nickname and C:\\wamp64\\www as path. Then saying 'list projects folder' is enough.")
        tiny.setObjectName("Tiny")
        tiny.setWordWrap(True)
        root.addWidget(tiny)

        self.paths = QListWidget()
        self.paths.setMinimumHeight(170)
        self.paths.currentItemChanged.connect(self._selected_folder_changed)
        root.addWidget(self.paths)

        add_grid = QGridLayout()
        self.nickname_input = QLineEdit()
        self.nickname_input.setPlaceholderText("Nickname / short name: projects, friday, security, client1...")
        self.aliases_input = QLineEdit()
        self.aliases_input.setPlaceholderText("Extra aliases separated by commas: project, web, wamp, medpov...")
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(r"C:\wamp64\www\project or C:\MEDPOV folder path")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_trusted_path)
        add_btn = QPushButton("Add / Update")
        add_btn.clicked.connect(self._add_path)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.setObjectName("dangerBtn")
        remove_btn.clicked.connect(self._remove_selected_path)
        add_grid.addWidget(QLabel("Nickname"), 0, 0)
        add_grid.addWidget(self.nickname_input, 0, 1, 1, 3)
        add_grid.addWidget(QLabel("Aliases"), 1, 0)
        add_grid.addWidget(self.aliases_input, 1, 1, 1, 3)
        add_grid.addWidget(QLabel("Folder path"), 2, 0)
        add_grid.addWidget(self.path_input, 2, 1)
        add_grid.addWidget(browse_btn, 2, 2)
        add_grid.addWidget(add_btn, 2, 3)
        add_grid.addWidget(remove_btn, 2, 4)
        root.addLayout(add_grid)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.backup_root = QLineEdit()
        self.screenshots_root = QLineEdit()
        self.recordings_root = QLineEdit()
        self.notes_root = QLineEdit()
        self.record_seconds = QSpinBox()
        self.record_seconds.setRange(3, 600)
        self.record_seconds.setSuffix(" sec max")
        self.record_fps = QSpinBox()
        self.record_fps.setRange(3, 30)
        self.record_fps.setSuffix(" fps")
        form.addRow("Backup folder", self._with_browse(self.backup_root, "backup_root"))
        form.addRow("Screenshot folder", self._with_browse(self.screenshots_root, "screenshots_root"))
        form.addRow("Screen recording folder", self._with_browse(self.recordings_root, "recordings_root"))
        form.addRow("Notes folder", self._with_browse(self.notes_root, "notes_root"))
        form.addRow("Screen recording limit", self._two_spin_widget(self.record_seconds, self.record_fps))
        root.addLayout(form)

        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setFixedHeight(92)
        self.result_box.setPlaceholderText("Save result will appear here.")
        root.addWidget(self.result_box)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._save)
        actions.addWidget(close_btn)
        actions.addWidget(save_btn)
        root.addLayout(actions)

    def _two_spin_widget(self, a: QSpinBox, b: QSpinBox) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(a)
        row.addWidget(b)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        return w

    def _with_browse(self, line: QLineEdit, key: str) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("Browse")
        btn.clicked.connect(lambda _=False, k=key, l=line: self._browse_output_root(k, l))
        row.addWidget(line, stretch=1)
        row.addWidget(btn)
        w = QWidget()
        w.setLayout(row)
        return w

    def _load_values(self) -> None:
        s = self.settings
        self.enabled.setChecked(bool(s.get("enabled", True)))
        self.allow_read.setChecked(bool(s.get("allow_read", True)))
        self.allow_write.setChecked(bool(s.get("allow_write", True)))
        self.allow_create.setChecked(bool(s.get("allow_create", True)))
        self.allow_copy_move.setChecked(bool(s.get("allow_copy_move", True)))
        self.allow_zip_backup.setChecked(bool(s.get("allow_zip_backup", True)))
        self.allow_delete.setChecked(bool(s.get("allow_delete_to_trash", True)))
        self.allow_apps.setChecked(bool(s.get("allow_app_control", True)))
        self.allow_open_path.setChecked(bool(s.get("allow_open_path", True)))
        self.allow_office.setChecked(bool(s.get("allow_office_control", True)))
        self.allow_clipboard.setChecked(bool(s.get("allow_clipboard", True)))
        self.allow_screenshot.setChecked(bool(s.get("allow_screenshot", True)))
        self.allow_screen_recording.setChecked(bool(s.get("allow_screen_recording", True)))
        self.allow_system_report.setChecked(bool(s.get("allow_system_report", True)))
        self.allow_window_control.setChecked(bool(s.get("allow_window_control", True)))
        self.paths.clear()
        for folder in get_trusted_folders(include_disabled=True):
            name = str(folder.get("name") or Path(str(folder.get("path", ""))).name or "Folder")
            path = str(folder.get("path") or "")
            aliases = ", ".join(str(x) for x in (folder.get("aliases") or []) if str(x) != name)
            status = "✓" if folder.get("enabled", True) else "×"
            text = f"{status} {name}  →  {path}"
            if aliases:
                text += f"\n   alias: {aliases}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, folder)
            item.setSizeHint(QSize(0, 46 if aliases else 34))
            self.paths.addItem(item)
        self.backup_root.setText(str(s.get("backup_root", "")))
        self.screenshots_root.setText(str(s.get("screenshots_root", "")))
        self.recordings_root.setText(str(s.get("recordings_root", "")))
        self.notes_root.setText(str(s.get("notes_root", "")))
        self.record_seconds.setValue(int(s.get("screen_recording_max_seconds", 90) or 90))
        self.record_fps.setValue(int(s.get("screen_recording_fps", 12) or 12))

    def _selected_folder_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None = None) -> None:
        if not current:
            return
        folder = current.data(Qt.ItemDataRole.UserRole) or {}
        self.nickname_input.setText(str(folder.get("name") or ""))
        self.path_input.setText(str(folder.get("path") or ""))
        self.aliases_input.setText(", ".join(str(x) for x in (folder.get("aliases") or [])))

    def _browse_trusted_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select trusted folder")
        if folder:
            self.path_input.setText(folder)
            if not self.nickname_input.text().strip():
                self.nickname_input.setText(Path(folder).name or "Folder")

    def _browse_output_root(self, key: str, line: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder seç")
        if folder:
            line.setText(folder)

    def _add_path(self) -> None:
        raw = self.path_input.text().strip()
        if not raw:
            QMessageBox.warning(self, "PC Settings", "Enter a folder path first or select one with Browse.")
            return
        nickname = self.nickname_input.text().strip() or Path(raw).name or "Folder"
        aliases = self.aliases_input.text().strip()
        try:
            updated = add_trusted_path(raw, name=nickname, aliases=aliases)
            self.settings = updated
            self._load_values()
            self.path_input.clear()
            self.nickname_input.clear()
            self.aliases_input.clear()
            self.result_box.setPlainText(f"Folder eklendi/güncellendi:\n{nickname} → {Path(raw).expanduser()}")
        except Exception as exc:
            QMessageBox.warning(self, "PC Settings", str(exc))

    def _remove_selected_path(self) -> None:
        item = self.paths.currentItem()
        if not item:
            return
        folder = item.data(Qt.ItemDataRole.UserRole) or {}
        raw = str(folder.get("path") or item.text())
        try:
            updated = remove_trusted_path(raw)
            self.settings = updated
            self._load_values()
            self.result_box.setPlainText(f"Folder kaldırıldı:\n{raw}")
        except Exception as exc:
            QMessageBox.warning(self, "PC Settings", str(exc))

    def _collect_folders_from_list(self) -> List[Dict[str, Any]]:
        folders: List[Dict[str, Any]] = []
        for i in range(self.paths.count()):
            folder = self.paths.item(i).data(Qt.ItemDataRole.UserRole) or {}
            if folder.get("path"):
                folders.append(dict(folder))
        raw = self.path_input.text().strip()
        if raw:
            folders.append({
                "name": self.nickname_input.text().strip() or Path(raw).name or "Folder",
                "path": raw,
                "aliases": [x.strip() for x in self.aliases_input.text().split(",") if x.strip()],
                "enabled": True,
            })
        return folders

    def _save(self) -> None:
        data = dict(self.settings)
        data.update({
            "enabled": self.enabled.isChecked(),
            "trusted_folders": self._collect_folders_from_list(),
            "backup_root": self.backup_root.text().strip(),
            "screenshots_root": self.screenshots_root.text().strip(),
            "recordings_root": self.recordings_root.text().strip(),
            "notes_root": self.notes_root.text().strip(),
            "allow_read": self.allow_read.isChecked(),
            "allow_write": self.allow_write.isChecked(),
            "allow_create": self.allow_create.isChecked(),
            "allow_copy_move": self.allow_copy_move.isChecked(),
            "allow_zip_backup": self.allow_zip_backup.isChecked(),
            "allow_delete_to_trash": self.allow_delete.isChecked(),
            "allow_app_control": self.allow_apps.isChecked(),
            "allow_open_path": self.allow_open_path.isChecked(),
            "allow_office_control": self.allow_office.isChecked(),
            "allow_clipboard": self.allow_clipboard.isChecked(),
            "allow_screenshot": self.allow_screenshot.isChecked(),
            "allow_screen_recording": self.allow_screen_recording.isChecked(),
            "allow_system_report": self.allow_system_report.isChecked(),
            "allow_window_control": self.allow_window_control.isChecked(),
            "screen_recording_max_seconds": self.record_seconds.value(),
            "screen_recording_fps": self.record_fps.value(),
        })
        saved = save_pc_settings(data)
        self.settings = saved
        self._load_values()
        self.result_box.setPlainText("PC settings saved.\n\n" + json.dumps(saved, ensure_ascii=False, indent=2))
