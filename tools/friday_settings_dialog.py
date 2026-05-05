from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .friday_settings_store import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_TEXT_MODEL,
    DEFAULT_OPENAI_VISION_MODEL,
    DEFAULT_OPENAI_REALTIME_MODEL,
    DEFAULT_OPENAI_TTS_MODEL,
    DEFAULT_OPENAI_VOICE,
    VOICE_OPTIONS,
    normalize_ai_provider,
    normalize_fallback_provider,
    normalize_response_language,
    api_url_from_base,
    load_settings,
    normalize_security_center_base_url,
    save_settings,
)


class _SecurityCenterTestThread(QThread):
    finished_ok = pyqtSignal(str)
    finished_error = pyqtSignal(str)

    def __init__(self, base_url: str, api_key: str, timeout: int = 20) -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    def run(self) -> None:
        try:
            endpoint = api_url_from_base(self.base_url)
            query = urllib.parse.urlencode({"action": "ping"})
            req = urllib.request.Request(
                endpoint + "?" + query,
                headers={
                    "Accept": "application/json",
                    "X-MEDPOV-API-Key": self.api_key,
                    "User-Agent": "MEDPOV-Friday-Settings-Test",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            try:
                data: Dict[str, Any] = json.loads(raw)
            except Exception:
                data = {"ok": False, "message": raw[:500]}
            if data.get("ok"):
                msg = "Security Center bağlantısı başarılı."
                if data.get("version"):
                    msg += f"\nVersion: {data.get('version')}"
                if data.get("access"):
                    msg += f"\nAccess: {data.get('access')}"
                self.finished_ok.emit(msg)
            else:
                self.finished_error.emit("Security Center cevap verdi ama yetki/bağlantı başarısız:\n" + json.dumps(data, ensure_ascii=False, indent=2))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            self.finished_error.emit(f"HTTP {exc.code}\n{raw[:1000]}")
        except Exception as exc:
            self.finished_error.emit(str(exc))


class _OpenAITestThread(QThread):
    finished_ok = pyqtSignal(str)
    finished_error = pyqtSignal(str)

    def __init__(self, api_key: str, model: str, timeout: int = 20) -> None:
        super().__init__()
        self.api_key = api_key
        self.model = model or DEFAULT_OPENAI_TEXT_MODEL
        self.timeout = timeout

    def run(self) -> None:
        try:
            if not self.api_key.strip():
                raise RuntimeError("OpenAI API key boş.")
            payload = json.dumps({
                "model": self.model,
                "input": "Reply with only: OK"
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=payload,
                headers={
                    "Authorization": "Bearer " + self.api_key.strip(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "MEDPOV-Friday-OpenAI-Test",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw[:500]}
            rid = data.get("id") or "response_received"
            self.finished_ok.emit(f"OpenAI bağlantısı başarılı. Model: {self.model}\nResponse: {rid}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            self.finished_error.emit(f"HTTP {exc.code}\n{raw[:1000]}")
        except Exception as exc:
            self.finished_error.emit(str(exc))


class FridaySettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MEDPOV FRIDAY Ayarları")
        self.setMinimumWidth(760)
        self._test_thread = None
        self._openai_test_thread = None
        self.settings = load_settings()
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog { background: #050b12; color: #e7f6ff; }
            QTabWidget::pane { border: 1px solid rgba(255,145,55,.32); border-radius: 12px; padding: 8px; }
            QTabBar::tab { background: #08131f; color: #9fb2c5; padding: 9px 14px; border-top-left-radius: 9px; border-top-right-radius: 9px; margin-right: 4px; }
            QTabBar::tab:selected { background: #18202b; color: #ffb86b; border: 1px solid rgba(255,145,55,.42); }
            QLabel { color: #c9d7e6; }
            QLineEdit, QComboBox, QTextEdit { background: #07111d; color: #f3fbff; border: 1px solid rgba(255,145,55,.26); border-radius: 9px; padding: 8px; selection-background-color: #ff8a22; }
            QPushButton { background: #111c2b; color: #f4fbff; border: 1px solid rgba(255,145,55,.38); border-radius: 10px; padding: 9px 13px; font-weight: 700; }
            QPushButton:hover { background: #201b18; border-color: #ff9b36; color: #ffbf75; }
            QPushButton#saveBtn { background: #ff8a22; color: #160b02; border-color: #ffb25f; }

            /* MEDPOV voice popup dark fix */
            QComboBox { background: #07111d; color: #f3fbff; border: 1px solid rgba(255,145,55,.34); border-radius: 9px; padding: 8px 28px 8px 10px; selection-background-color: #ff8a22; selection-color: #140701; }
            QComboBox:hover { border-color: #ff9b36; }
            QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 26px; border-left: 1px solid rgba(255,145,55,.28); border-top-right-radius: 9px; border-bottom-right-radius: 9px; background: #111c2b; }
            QComboBox::down-arrow { image: none; width: 0px; height: 0px; }
            QComboBox QAbstractItemView { background-color: #07111d; color: #f3fbff; border: 1px solid rgba(255,145,55,.55); outline: 0; selection-background-color: #ff8a22; selection-color: #130701; padding: 6px; }
            QListView#FridayVoiceComboView { background-color: #07111d; color: #f3fbff; border: 1px solid rgba(255,145,55,.55); outline: 0; }
            QListView#FridayVoiceComboView::item { min-height: 28px; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.045); }
            QListView#FridayVoiceComboView::item:selected { background-color: #ff8a22; color: #140701; }
            QListView#FridayVoiceComboView::item:hover { background-color: #152335; color: #ffbf75; }
        """)
        root = QVBoxLayout(self)
        title = QLabel("F.R.I.D.A.Y Control Settings")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color:#ffb86b; padding: 4px 0 8px 0;")
        root.addWidget(title)
        subtitle = QLabel("AI sağlayıcı, ses, cevap dili, Security Center, Gemini ve OpenAI ayarlarını buradan güncelleyebilirsin.")
        subtitle.setStyleSheet("color:#8fa1b8; padding-bottom:8px;")
        root.addWidget(subtitle)
        tabs = QTabWidget()
        tabs.addTab(self._provider_tab(), "AI Provider")
        tabs.addTab(self._voice_tab(), "Ses")
        tabs.addTab(self._security_tab(), "Security Center")
        tabs.addTab(self._gemini_tab(), "Gemini")
        tabs.addTab(self._openai_tab(), "OpenAI")
        root.addWidget(tabs)
        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setFixedHeight(86)
        self.result_box.setPlaceholderText("Test ve kayıt sonuçları burada görünecek.")
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


    def _provider_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItem("Gemini · mevcut canlı ses + tool orchestration", "gemini")
        self.ai_provider_combo.addItem("OpenAI · komut/vision beyni + doğal OpenAI TTS", "openai")
        self.ai_provider_combo.addItem("Auto / Fallback · Gemini ana, OpenAI yedek", "auto")
        self.fallback_provider_combo = QComboBox()
        self.fallback_provider_combo.addItem("OpenAI", "openai")
        self.fallback_provider_combo.addItem("Gemini", "gemini")
        info = QLabel(
            "Gemini modu eski davranışı korur. OpenAI modu yazılı komutları ve kamera/görüntü analizini OpenAI ile işler; "
            "mikrofon transkripsiyon köprüsü için mevcut Live bağlantısı açık kalır. OpenAI cevapları artık Windows lokal TTS yerine OpenAI doğal ses modeliyle okunur. Auto modunda Gemini sorun yaşarsa vision/text tarafında OpenAI yedeği kullanılabilir."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#8fa1b8;")
        form.addRow("AI Provider", self.ai_provider_combo)
        form.addRow("Fallback", self.fallback_provider_combo)
        form.addRow("", info)
        return w

    def _voice_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.voice_combo = QComboBox()
        self.voice_combo.setMaxVisibleItems(12)
        self.voice_combo.setView(QListView())
        self.voice_combo.view().setObjectName("FridayVoiceComboView")
        self.voice_combo.view().setStyleSheet("""
            QListView { background-color: #07111d; color: #f3fbff; border: 1px solid rgba(255,145,55,.62); outline: 0; padding: 6px; }
            QListView::item { min-height: 28px; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.05); }
            QListView::item:selected { background-color: #ff8a22; color: #140701; }
            QListView::item:hover { background-color: #152335; color: #ffbf75; }
        """)
        for item in VOICE_OPTIONS:
            self.voice_combo.addItem(item["label"], item["name"])
        self.voice_language = QLineEdit("tr-TR")
        self.response_language_combo = QComboBox()
        self.response_language_combo.addItem("Türkçe cevap ver", "tr")
        self.response_language_combo.addItem("Answer in English", "en")
        hint = QLabel("Not: Ses ve cevap dili değişikliği Gemini Live oturumu yeniden açıldığında aktif olur. Friday'i kapatıp açmak en temiz sonuç verir.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8fa1b8;")
        form.addRow("FRIDAY sesi", self.voice_combo)
        form.addRow("Ses dil kodu", self.voice_language)
        form.addRow("Cevap dili", self.response_language_combo)
        form.addRow("", hint)
        return w

    def _security_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.sc_base_url = QLineEdit()
        self.sc_base_url.textChanged.connect(self._refresh_sc_endpoint_preview)
        self.sc_api_key = QLineEdit()
        self.sc_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.sc_timeout = QLineEdit("25")
        self.sc_endpoint_preview = QLineEdit()
        self.sc_endpoint_preview.setReadOnly(True)
        test_btn = QPushButton("Bağlantıyı Test Et")
        test_btn.clicked.connect(self._test_security_center)
        info = QLabel("Örnek base URL: https://medpov.com/main/security-center veya https://xwebsitesi.com/security-center")
        info.setWordWrap(True)
        info.setStyleSheet("color:#8fa1b8;")
        form.addRow("Base URL", self.sc_base_url)
        form.addRow("API endpoint", self.sc_endpoint_preview)
        form.addRow("API key", self.sc_api_key)
        form.addRow("Timeout", self.sc_timeout)
        form.addRow("", test_btn)
        form.addRow("", info)
        return w

    def _gemini_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.gemini_api_key = QLineEdit()
        self.gemini_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_model = QLineEdit(DEFAULT_GEMINI_MODEL)
        info = QLabel("API key kaydedilince config/api_keys.json içine de yazılır. Yeni key/model için Friday'i yeniden başlatman önerilir.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#8fa1b8;")
        form.addRow("Gemini API key", self.gemini_api_key)
        form.addRow("Gemini model", self.gemini_model)
        form.addRow("", info)
        return w


    def _openai_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.openai_api_key = QLineEdit()
        self.openai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_text_model = QLineEdit(DEFAULT_OPENAI_TEXT_MODEL)
        self.openai_vision_model = QLineEdit(DEFAULT_OPENAI_VISION_MODEL)
        self.openai_realtime_model = QLineEdit(DEFAULT_OPENAI_REALTIME_MODEL)
        self.openai_tts_model = QLineEdit(DEFAULT_OPENAI_TTS_MODEL)
        self.openai_voice = QComboBox()
        for voice_name in ["marin", "cedar", "coral", "nova", "shimmer", "alloy", "ash", "ballad", "echo", "fable", "onyx", "sage", "verse"]:
            self.openai_voice.addItem(voice_name, voice_name)
        test_btn = QPushButton("OpenAI Bağlantısını Test Et")
        test_btn.clicked.connect(self._test_openai)
        info = QLabel(
            "OpenAI key config/friday_settings.json ve legacy config/api_keys.json içine yazılır. "
            "Vision için JPEG/base64 image input kullanılır; yazılı komutlar function calling ile lokal FRIDAY araçlarına yönlendirilir. OpenAI Provider modunda cevap sesi için OpenAI TTS kullanılır."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#8fa1b8;")
        form.addRow("OpenAI API key", self.openai_api_key)
        form.addRow("Text/command model", self.openai_text_model)
        form.addRow("Vision model", self.openai_vision_model)
        form.addRow("Realtime model", self.openai_realtime_model)
        form.addRow("TTS model", self.openai_tts_model)
        form.addRow("OpenAI voice", self.openai_voice)
        form.addRow("", test_btn)
        form.addRow("", info)
        return w

    def _load_values(self) -> None:
        s = self.settings
        assistant = s.get("assistant", {})
        provider_idx = self.ai_provider_combo.findData(normalize_ai_provider(assistant.get("ai_provider")))
        if provider_idx >= 0:
            self.ai_provider_combo.setCurrentIndex(provider_idx)
        fallback_idx = self.fallback_provider_combo.findData(normalize_fallback_provider(assistant.get("fallback_provider")))
        if fallback_idx >= 0:
            self.fallback_provider_combo.setCurrentIndex(fallback_idx)
        voice = s.get("voice", {})
        voice_name = str(voice.get("name") or "Aoede")
        idx = self.voice_combo.findData(voice_name)
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        self.voice_language.setText(str(voice.get("language") or "tr-TR"))
        response_lang = normalize_response_language(assistant.get("response_language"))
        response_idx = self.response_language_combo.findData(response_lang)
        if response_idx >= 0:
            self.response_language_combo.setCurrentIndex(response_idx)
        sc = s.get("security_center", {})
        self.sc_base_url.setText(str(sc.get("base_url") or "https://medpov.com/main/security-center"))
        self.sc_api_key.setText(str(sc.get("api_key") or ""))
        self.sc_timeout.setText(str(sc.get("timeout") or 25))
        self._refresh_sc_endpoint_preview()
        gemini = s.get("gemini", {})
        self.gemini_api_key.setText(str(gemini.get("api_key") or ""))
        self.gemini_model.setText(str(gemini.get("model") or DEFAULT_GEMINI_MODEL))
        openai = s.get("openai", {})
        self.openai_api_key.setText(str(openai.get("api_key") or ""))
        self.openai_text_model.setText(str(openai.get("text_model") or DEFAULT_OPENAI_TEXT_MODEL))
        self.openai_vision_model.setText(str(openai.get("vision_model") or DEFAULT_OPENAI_VISION_MODEL))
        self.openai_realtime_model.setText(str(openai.get("realtime_model") or DEFAULT_OPENAI_REALTIME_MODEL))
        self.openai_tts_model.setText(str(openai.get("tts_model") or DEFAULT_OPENAI_TTS_MODEL))
        voice_idx = self.openai_voice.findData(str(openai.get("voice") or DEFAULT_OPENAI_VOICE))
        if voice_idx >= 0:
            self.openai_voice.setCurrentIndex(voice_idx)

    def _refresh_sc_endpoint_preview(self) -> None:
        self.sc_endpoint_preview.setText(api_url_from_base(self.sc_base_url.text()))

    def _collect(self) -> Dict[str, Any]:
        try:
            timeout = int(self.sc_timeout.text().strip() or "25")
        except Exception:
            timeout = 25
        base = normalize_security_center_base_url(self.sc_base_url.text())
        female_names = {"Aoede", "Leda", "Kore", "Zephyr", "Callirrhoe", "Autonoe"}
        voice_name = str(self.voice_combo.currentData() or self.voice_combo.currentText() or "Aoede")
        return {
            "voice": {"name": voice_name, "language": self.voice_language.text().strip() or "tr-TR", "character_gender": "female" if voice_name in female_names else "male"},
            "assistant": {
                "response_language": normalize_response_language(self.response_language_combo.currentData()),
                "ai_provider": normalize_ai_provider(self.ai_provider_combo.currentData()),
                "fallback_provider": normalize_fallback_provider(self.fallback_provider_combo.currentData()),
            },
            "security_center": {"base_url": base, "api_url": api_url_from_base(base), "api_key": self.sc_api_key.text().strip(), "timeout": timeout},
            "gemini": {"api_key": self.gemini_api_key.text().strip(), "model": self.gemini_model.text().strip() or DEFAULT_GEMINI_MODEL},
            "openai": {
                "api_key": self.openai_api_key.text().strip(),
                "text_model": self.openai_text_model.text().strip() or DEFAULT_OPENAI_TEXT_MODEL,
                "vision_model": self.openai_vision_model.text().strip() or DEFAULT_OPENAI_VISION_MODEL,
                "realtime_model": self.openai_realtime_model.text().strip() or DEFAULT_OPENAI_REALTIME_MODEL,
                "tts_model": self.openai_tts_model.text().strip() or DEFAULT_OPENAI_TTS_MODEL,
                "voice": str(self.openai_voice.currentData() or DEFAULT_OPENAI_VOICE),
            },
        }

    def _save(self) -> None:
        try:
            saved = save_settings(self._collect())
            self.result_box.setPlainText("Ayarlar kaydedildi. Değişikliklerin tamamı için Friday'i yeniden başlatman önerilir.\n\n" + json.dumps(saved, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.critical(self, "Kayıt hatası", str(exc))

    def _test_security_center(self) -> None:
        self.result_box.setPlainText("Security Center bağlantısı test ediliyor...")
        if self._test_thread and self._test_thread.isRunning():
            return
        try:
            timeout = int(self.sc_timeout.text().strip() or "20")
        except Exception:
            timeout = 20
        self._test_thread = _SecurityCenterTestThread(self.sc_base_url.text(), self.sc_api_key.text(), timeout)
        self._test_thread.finished_ok.connect(lambda msg: self.result_box.setPlainText("✅ " + msg))
        self._test_thread.finished_error.connect(lambda msg: self.result_box.setPlainText("❌ " + msg))
        self._test_thread.start()


    def _test_openai(self) -> None:
        self.result_box.setPlainText("OpenAI bağlantısı test ediliyor...")
        if self._openai_test_thread and self._openai_test_thread.isRunning():
            return
        self._openai_test_thread = _OpenAITestThread(
            self.openai_api_key.text().strip(),
            self.openai_text_model.text().strip() or DEFAULT_OPENAI_TEXT_MODEL,
            25,
        )
        self._openai_test_thread.finished_ok.connect(lambda msg: self.result_box.setPlainText("✅ " + msg))
        self._openai_test_thread.finished_error.connect(lambda msg: self.result_box.setPlainText("❌ " + msg))
        self._openai_test_thread.start()
