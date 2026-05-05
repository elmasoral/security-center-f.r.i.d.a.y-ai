from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from .friday_pc_settings_store import (
    add_trusted_path,
    load_pc_settings,
    remove_trusted_path,
    save_pc_settings,
)


class FridayPCSettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MEDPOV FRIDAY PC Settings")
        self.setMinimumWidth(820)
        self.settings: Dict[str, Any] = load_pc_settings()
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog { background: #050b12; color: #e7f6ff; }
            QLabel { color: #c9d7e6; background: transparent; }
            QLabel#Title { color:#28e9ff; font-size:17px; font-weight:900; letter-spacing:1px; }
            QLabel#Hint { color:#8fa1b8; }
            QLineEdit, QTextEdit, QListWidget {
                background: #07111d;
                color: #f3fbff;
                border: 1px solid rgba(40,233,255,.28);
                border-radius: 9px;
                padding: 8px;
                selection-background-color: #28e9ff;
                selection-color: #04101e;
            }
            QListWidget::item { padding: 7px; border-bottom: 1px solid rgba(255,255,255,.045); }
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
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(10)

        title = QLabel("PC Workspace Settings")
        title.setObjectName("Title")
        root.addWidget(title)

        hint = QLabel(
            "FRIDAY dosya kopyalama, zip, yedekleme, not, screenshot ve uygulama kontrol işlemlerini burada güvenilir olarak eklediğin klasörlerde yapar. "
            "Proje klasörlerini buraya ekle: örn. C:\\wamp64\\www veya C:\\MEDPOV."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.enabled = QCheckBox("PC Workspace aktif")
        self.allow_write = QCheckBox("Dosya yazma / kopyalama / zip / yedekleme aktif")
        self.allow_delete = QCheckBox("Silme işlemleri sadece Geri Dönüşüm Kutusu ile aktif")
        self.allow_apps = QCheckBox("Word, Notepad, klasör açma ve pencere kontrolü aktif")
        self.allow_screenshot = QCheckBox("Ekran görüntüsü alma aktif")
        for cb in [self.enabled, self.allow_write, self.allow_delete, self.allow_apps, self.allow_screenshot]:
            root.addWidget(cb)

        paths_label = QLabel("Güvenilir klasörler")
        paths_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        paths_label.setStyleSheet("color:#ffb86b; padding-top:6px;")
        root.addWidget(paths_label)

        self.paths = QListWidget()
        self.paths.setMinimumHeight(150)
        root.addWidget(self.paths)

        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(r"C:\wamp64\www\proje veya C:\MEDPOV gibi klasör yolu")
        browse_btn = QPushButton("Gözat")
        browse_btn.clicked.connect(self._browse_trusted_path)
        add_btn = QPushButton("Ekle")
        add_btn.clicked.connect(self._add_path)
        remove_btn = QPushButton("Seçileni Kaldır")
        remove_btn.setObjectName("dangerBtn")
        remove_btn.clicked.connect(self._remove_selected_path)
        path_row.addWidget(self.path_input, stretch=1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(add_btn)
        path_row.addWidget(remove_btn)
        root.addLayout(path_row)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.backup_root = QLineEdit()
        self.screenshots_root = QLineEdit()
        self.notes_root = QLineEdit()
        form.addRow("Backup klasörü", self._with_browse(self.backup_root, "backup_root"))
        form.addRow("Screenshot klasörü", self._with_browse(self.screenshots_root, "screenshots_root"))
        form.addRow("Not klasörü", self._with_browse(self.notes_root, "notes_root"))
        root.addLayout(form)

        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setFixedHeight(74)
        self.result_box.setPlaceholderText("Kayıt sonucu burada görünecek.")
        root.addWidget(self.result_box)

        actions = QHBoxLayout()
        actions.addStretch(1)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Kaydet")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._save)
        actions.addWidget(close_btn)
        actions.addWidget(save_btn)
        root.addLayout(actions)

    def _with_browse(self, line: QLineEdit, key: str):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("Gözat")
        btn.clicked.connect(lambda _=False, k=key, l=line: self._browse_output_root(k, l))
        row.addWidget(line, stretch=1)
        row.addWidget(btn)
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        w.setLayout(row)
        return w

    def _load_values(self) -> None:
        s = self.settings
        self.enabled.setChecked(bool(s.get("enabled", True)))
        self.allow_write.setChecked(bool(s.get("allow_write", True)))
        self.allow_delete.setChecked(bool(s.get("allow_delete_to_trash", True)))
        self.allow_apps.setChecked(bool(s.get("allow_app_control", True)))
        self.allow_screenshot.setChecked(bool(s.get("allow_screenshot", True)))
        self.paths.clear()
        for path in s.get("trusted_paths", []) or []:
            self.paths.addItem(str(path))
        self.backup_root.setText(str(s.get("backup_root", "")))
        self.screenshots_root.setText(str(s.get("screenshots_root", "")))
        self.notes_root.setText(str(s.get("notes_root", "")))

    def _browse_trusted_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Güvenilir klasör seç")
        if folder:
            self.path_input.setText(folder)

    def _browse_output_root(self, key: str, line: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Klasör seç")
        if folder:
            line.setText(folder)

    def _add_path(self) -> None:
        raw = self.path_input.text().strip()
        if not raw:
            return
        try:
            updated = add_trusted_path(raw)
            self.settings = updated
            self._load_values()
            self.path_input.clear()
            self.result_box.setPlainText(f"Klasör eklendi:\n{Path(raw).expanduser()}")
        except Exception as exc:
            QMessageBox.warning(self, "PC Settings", str(exc))

    def _remove_selected_path(self) -> None:
        item = self.paths.currentItem()
        if not item:
            return
        raw = item.text()
        try:
            updated = remove_trusted_path(raw)
            self.settings = updated
            self._load_values()
            self.result_box.setPlainText(f"Klasör kaldırıldı:\n{raw}")
        except Exception as exc:
            QMessageBox.warning(self, "PC Settings", str(exc))

    def _save(self) -> None:
        current_paths = [self.paths.item(i).text() for i in range(self.paths.count())]
        raw = self.path_input.text().strip()
        if raw and raw not in current_paths:
            current_paths.append(raw)
        data = dict(self.settings)
        data.update({
            "enabled": self.enabled.isChecked(),
            "trusted_paths": current_paths,
            "backup_root": self.backup_root.text().strip(),
            "screenshots_root": self.screenshots_root.text().strip(),
            "notes_root": self.notes_root.text().strip(),
            "allow_write": self.allow_write.isChecked(),
            "allow_delete_to_trash": self.allow_delete.isChecked(),
            "allow_app_control": self.allow_apps.isChecked(),
            "allow_screenshot": self.allow_screenshot.isChecked(),
        })
        saved = save_pc_settings(data)
        self.settings = saved
        self._load_values()
        self.result_box.setPlainText("PC ayarları kaydedildi.\n\n" + json.dumps(saved, ensure_ascii=False, indent=2))
