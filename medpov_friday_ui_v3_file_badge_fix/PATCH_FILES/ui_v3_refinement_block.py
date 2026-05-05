# === MEDPOV FRIDAY UI V3 FILE INPUT + SECURITY BADGE FIX ===
# This block is intentionally appended and monkey-patches only the visual layer.
# It keeps the FRIDAY hologram/core logic untouched.

def _mpv3_panel_section(text: str) -> QLabel:
    lbl = QLabel(f"⌁  {text}")
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {C.WHITE};
            background: transparent;
            border: none;
            padding: 2px 0 2px 0;
            letter-spacing: 0.8px;
        }}
    """)
    return lbl


def _mpv3_drop_paint_idle(self, p, W, H, hover):
    """Cleaner file input idle state: all text stays inside the dashed border."""
    cx = W / 2
    rect = QRectF(10, 10, W - 20, H - 20)
    accent = C.PRI if hover else C.PRI_DIM

    # soft inner glow
    p.setPen(Qt.PenStyle.NoPen)
    glow = QRadialGradient(QPointF(cx, H * 0.46), max(W, H) * 0.48)
    glow.setColorAt(0.0, qcol(C.PRI, 34 if hover else 22))
    glow.setColorAt(0.58, qcol(C.PRI_DIM, 10))
    glow.setColorAt(1.0, qcol("#000000", 0))
    p.setBrush(QBrush(glow))
    p.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 12, 12)

    # upload icon lower and cleaner
    icon_y = H * 0.36
    p.setPen(QPen(qcol(accent, 220), 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(cx - 16, icon_y - 16, 32, 32), 9, 9)
    p.drawLine(QPointF(cx, icon_y + 8), QPointF(cx, icon_y - 9))
    p.drawLine(QPointF(cx - 8, icon_y - 1), QPointF(cx, icon_y - 9))
    p.drawLine(QPointF(cx + 8, icon_y - 1), QPointF(cx, icon_y - 9))

    # main text fully inside dashed area
    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(QPen(qcol(C.WHITE, 235), 1))
    p.drawText(
        QRectF(16, H * 0.53, W - 32, 20),
        Qt.AlignmentFlag.AlignCenter,
        "Drop file or click to analyze",
    )

    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(QPen(qcol(C.TEXT_DIM, 185), 1))
    p.drawText(
        QRectF(16, H * 0.68, W - 32, 18),
        Qt.AlignmentFlag.AlignCenter,
        "No file loaded  —  Images · PDF · Office · Code · Data · Media",
    )

    # tiny lower status rail
    p.setPen(QPen(qcol(C.PRI_DIM, 75), 1))
    p.drawLine(QPointF(W * 0.28, H - 18), QPointF(W * 0.72, H - 18))


def _mpv3_drop_paint_drag_over(self, p, W, H):
    cx = W / 2
    p.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    p.setPen(QPen(qcol(C.PRI, 245), 1))
    p.drawText(QRectF(0, H * 0.42, W, 24), Qt.AlignmentFlag.AlignCenter, "Release file to load")
    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(QPen(qcol(C.TEXT_MED, 200), 1))
    p.drawText(QRectF(0, H * 0.61, W, 18), Qt.AlignmentFlag.AlignCenter, "FRIDAY intelligent file input")
    p.setPen(QPen(qcol(C.PRI, 180), 2))
    p.drawEllipse(QPointF(cx, H * 0.32), 12, 12)


def _mpv3_drop_paint_file(self, p, W, H):
    path = Path(self._z._current_file or "")
    name = path.name if path.name else "Selected file"
    suffix = path.suffix.lstrip(".").upper() if path.suffix else "FILE"
    try:
        size = _fmt_size(path.stat().st_size) if path.exists() else "ready"
    except Exception:
        size = "ready"

    cat = _file_category(path)
    icon, color = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(qcol(color, 32)))
    p.drawRoundedRect(QRectF(18, 22, 54, 54), 14, 14)

    p.setFont(QFont("Segoe UI Emoji", 20, QFont.Weight.Bold))
    p.setPen(QPen(qcol(color, 245), 1))
    p.drawText(QRectF(18, 22, 54, 54), Qt.AlignmentFlag.AlignCenter, icon)

    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    p.setPen(QPen(qcol(C.WHITE, 235), 1))
    p.drawText(QRectF(82, 25, W - 98, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name[:46])

    p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    p.setPen(QPen(qcol(C.TEXT_MED, 190), 1))
    p.drawText(QRectF(82, 49, W - 98, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{suffix}  ·  {size}  ·  Ready for FRIDAY analysis")

    p.setPen(QPen(qcol(C.GREEN, 180), 1))
    p.drawLine(QPointF(82, 76), QPointF(W - 20, 76))


try:
    _DropCanvas._paint_idle = _mpv3_drop_paint_idle
    _DropCanvas._paint_drag_over = _mpv3_drop_paint_drag_over
    _DropCanvas._paint_file = _mpv3_drop_paint_file
except Exception:
    pass


def _mpv3_make_badge_label(size: int = 104) -> QLabel:
    badge = QLabel()
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setMinimumWidth(size + 8)
    badge.setStyleSheet("background: transparent; border: none;")
    try:
        asset = BASE_DIR / "assets" / "medpov_security_badge.png"
        pix = QPixmap(str(asset))
        if not pix.isNull():
            badge.setPixmap(
                pix.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            badge.setText("🛡")
            badge.setFont(QFont("Segoe UI Emoji", 34, QFont.Weight.Bold))
            badge.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
    except Exception:
        badge.setText("🛡")
        badge.setFont(QFont("Segoe UI Emoji", 34, QFont.Weight.Bold))
        badge.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
    return badge


def _mpv3_build_security_center_quick_panel(self) -> QWidget:
    box = QFrame()
    box.setObjectName("MedpovSecurityQuickPanelV3")
    box.setStyleSheet(f"""
        QFrame#MedpovSecurityQuickPanelV3 {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 rgba(6, 18, 31, 0.98),
                stop:0.58 rgba(5, 15, 27, 0.96),
                stop:1 rgba(2, 10, 19, 0.98));
            border: 1px solid rgba(40, 233, 255, 0.28);
            border-radius: 18px;
        }}
        QFrame#MedpovSecurityQuickPanelV3 QLabel {{
            background: transparent;
            border: none;
        }}
        QFrame#MedpovSecurityQuickPanelV3 QPushButton {{
            background: rgba(8, 31, 50, 0.82);
            color: {C.TEXT_MED};
            border: 1px solid rgba(40, 233, 255, 0.24);
            border-radius: 9px;
            padding: 5px 8px;
            text-align: left;
            font-weight: 800;
        }}
        QFrame#MedpovSecurityQuickPanelV3 QPushButton:hover {{
            background: rgba(17, 62, 88, 0.92);
            color: {C.WHITE};
            border: 1px solid rgba(40, 233, 255, 0.70);
        }}
    """)

    outer = QHBoxLayout(box)
    outer.setContentsMargins(13, 12, 13, 12)
    outer.setSpacing(12)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(7)

    head = QLabel("SECURITY CENTER")
    head.setFont(QFont("Segoe UI", 9, QFont.Weight.Black))
    head.setStyleSheet(f"color: {C.ACC2}; letter-spacing: 0.8px;")
    left.addWidget(head)

    hint = QLabel("Live MEDPOV threat intelligence")
    hint.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
    hint.setStyleSheet(f"color: {C.TEXT_DIM};")
    left.addWidget(hint)

    commands = [
        ("◉ Overview", "/sc overview", True),
        ("▲ Son Tehditler", "/sc threats", True),
        ("◇ Health", "/sc health", True),
        ("◉ Live", "/sc live", True),
        ("⌁ IP Profil", "/sc ip 65.55.210.207", False),
        ("✦ IP Analiz", "/sc analyze 65.55.210.207", False),
        ("● IP Block", "/sc block 1.2.3.4", False),
        ("✓ Resolve Event", "/sc resolve-event 124", False),
    ]

    grid = QGridLayout()
    grid.setContentsMargins(0, 2, 0, 0)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(6)

    for i, (label, command, send_now) in enumerate(commands):
        btn = QPushButton(label)
        btn.setFixedHeight(27)
        btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, c=command, s=send_now: self._run_security_center_quick(c, s))
        grid.addWidget(btn, i // 2, i % 2)

    left.addLayout(grid)
    outer.addLayout(left, stretch=1)

    badge_wrap = QFrame()
    badge_wrap.setObjectName("MedpovSecurityBadgeWrap")
    badge_wrap.setStyleSheet(f"""
        QFrame#MedpovSecurityBadgeWrap {{
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.78,
                stop:0 rgba(40, 233, 255, 0.13),
                stop:0.52 rgba(40, 233, 255, 0.04),
                stop:1 rgba(0, 0, 0, 0));
            border: none;
        }}
    """)
    badge_lay = QVBoxLayout(badge_wrap)
    badge_lay.setContentsMargins(0, 0, 0, 0)
    badge_lay.setSpacing(0)
    badge_lay.addStretch()
    badge_lay.addWidget(_mpv3_make_badge_label(110), alignment=Qt.AlignmentFlag.AlignCenter)
    badge_lay.addStretch()
    outer.addWidget(badge_wrap, stretch=0)

    return box


try:
    MainWindow._build_security_center_quick_panel = _mpv3_build_security_center_quick_panel
except Exception:
    pass


def _mpv3_build_right_panel(self) -> QWidget:
    w = QWidget()
    w.setFixedWidth(_RIGHT_W)
    w.setStyleSheet(f"""
        QWidget {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #04101e,
                stop:0.55 #030b15,
                stop:1 #020710);
            border-left: 1px solid rgba(40, 233, 255, 0.22);
        }}
    """)

    lay = QVBoxLayout(w)
    lay.setContentsMargins(13, 12, 13, 12)
    lay.setSpacing(9)

    lay.addWidget(_mpv3_panel_section("FRIDAY COMMAND LOG"))
    self._log = LogWidget()
    lay.addWidget(self._log, stretch=1)

    lay.addWidget(_mpv3_panel_section("INTELLIGENT FILE INPUT"))
    self._drop_zone = FileDropZone()
    self._drop_zone.setFixedHeight(112)
    self._drop_zone.file_selected.connect(self._on_file_selected)
    lay.addWidget(self._drop_zone)

    # kept for compatibility with _on_file_selected, but visual text now lives inside drop zone
    self._file_hint = QLabel("")
    self._file_hint.setVisible(False)

    lay.addWidget(_mpv3_panel_section("SECURITY CENTER QUICK LINKS"))
    lay.addWidget(self._build_security_center_quick_panel())

    lay.addWidget(_mpv3_panel_section("FRIDAY SETTINGS"))
    lay.addWidget(self._build_friday_settings_panel())

    lay.addWidget(_mpv3_panel_section("DIRECT COMMAND"))
    lay.addLayout(self._build_input_row())

    controls = QHBoxLayout()
    controls.setContentsMargins(0, 0, 0, 0)
    controls.setSpacing(8)

    self._standby_btn = QPushButton("⏻  STANDBY MODE")
    self._standby_btn.setFixedHeight(31)
    self._standby_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    self._standby_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self._standby_btn.clicked.connect(self._toggle_standby)
    self._style_standby_btn()
    controls.addWidget(self._standby_btn)

    self._mute_btn = QPushButton("🎙  MICROPHONE ACTIVE")
    self._mute_btn.setFixedHeight(31)
    self._mute_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Black))
    self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    self._mute_btn.clicked.connect(self._toggle_mute)
    self._style_mute_btn()
    controls.addWidget(self._mute_btn)

    lay.addLayout(controls)

    fs_btn = QPushButton("⛶  FULLSCREEN  [F11]")
    fs_btn.setFixedHeight(28)
    fs_btn.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    fs_btn.setStyleSheet(f"""
        QPushButton {{
            background: rgba(7, 23, 37, 0.95);
            color: {C.TEXT_MED};
            border: 1px solid rgba(40, 233, 255, 0.28);
            border-radius: 10px;
        }}
        QPushButton:hover {{
            color: {C.WHITE};
            background: rgba(11, 46, 69, 0.95);
            border: 1px solid rgba(40, 233, 255, 0.72);
        }}
    """)
    fs_btn.clicked.connect(self._toggle_fullscreen)
    lay.addWidget(fs_btn)

    return w


try:
    MainWindow._build_right_panel = _mpv3_build_right_panel
except Exception:
    pass

# === /MEDPOV FRIDAY UI V3 FILE INPUT + SECURITY BADGE FIX ===
