"""
Sonic Precision design system — QSS stylesheet for Playlist Converter.

Palette from Design Ideen/sonic_precision/DESIGN.md:
  surface-container-lowest : #0C0E12  (log background)
  surface-container-low    : #1A1C20  (sidebar, toolbar)
  surface-container        : #1E2024  (track panel, cards)
  surface-container-high   : #282A2E  (hover)
  surface-container-highest: #333539  (active / selected bg)
  surface / background     : #111317  (main window)
  on-surface               : #E2E2E8  (primary text)
  on-surface-variant       : #C1C6D7  (secondary text)
  outline                  : #8B90A0  (borders, muted labels)
  outline-variant          : #414755  (dividers)
  primary                  : #ADC6FF  (accent / selection text)
  primary-container        : #4B8EFF  (button fill, focus ring)
  on-primary               : #002E69  (text on blue buttons)
  secondary-container      : #C3F400  (lime — sync / ready)
  on-secondary-container   : #556D00  (text on lime)
  tertiary-container       : #FF5545  (alert / error)
  error-container          : #93000A  (deep red bg for errors)
"""

from PySide6.QtWidgets import QApplication


QSS = """
/* ── Base ──────────────────────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #111317;
    color: #E2E2E8;
    font-size: 13px;
}

/* ── Toolbar frame ──────────────────────────────────────────────────── */
QFrame#toolbar {
    background-color: #1A1C20;
    border-bottom: 1px solid #414755;
}

/* ── Labels ─────────────────────────────────────────────────────────── */
QLabel {
    color: #E2E2E8;
    background-color: transparent;
}

QLabel#sectionHeader {
    color: #8B90A0;
    font-size: 11px;
    font-weight: 700;
}

/* ── ComboBox ────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #1A1C20;
    color: #E2E2E8;
    border: 1px solid #414755;
    border-radius: 6px;
    padding: 4px 32px 4px 10px;
    min-height: 30px;
    selection-background-color: #4B8EFF;
    selection-color: #FFFFFF;
}

QComboBox:hover {
    border-color: #8B90A0;
}

QComboBox:focus {
    border-color: #4B8EFF;
}

QComboBox:disabled {
    color: #414755;
    border-color: #1E2024;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8B90A0;
    width: 0;
    height: 0;
}

QComboBox QAbstractItemView {
    background-color: #1E2024;
    color: #E2E2E8;
    border: 1px solid #414755;
    border-radius: 4px;
    selection-background-color: #002E69;
    selection-color: #ADC6FF;
    outline: none;
    padding: 4px;
}

QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    min-height: 28px;
    border-radius: 3px;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
QPushButton {
    background-color: #1E2024;
    color: #E2E2E8;
    border: 1px solid #414755;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 30px;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #282A2E;
    border-color: #8B90A0;
}

QPushButton:pressed {
    background-color: #111317;
}

QPushButton:disabled {
    color: #414755;
    border-color: #282A2E;
    background-color: #1A1C20;
}

QPushButton#primaryBtn {
    background-color: #4B8EFF;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}

QPushButton#primaryBtn:hover {
    background-color: #6BA3FF;
}

QPushButton#primaryBtn:pressed {
    background-color: #3A7AE8;
}

QPushButton#primaryBtn:disabled {
    background-color: #1E2024;
    color: #414755;
    border: 1px solid #282A2E;
    font-weight: 400;
}

/* ── Splitter ────────────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: #414755;
}

QSplitter::handle:horizontal {
    width: 1px;
}

QSplitter::handle:hover {
    background-color: #8B90A0;
}

/* ── Tree Widget (Playlists) ─────────────────────────────────────────── */
QTreeWidget {
    background-color: #1A1C20;
    alternate-background-color: #1E2024;
    color: #E2E2E8;
    border: none;
    outline: none;
    show-decoration-selected: 1;
}

QTreeWidget::item {
    padding-top: 5px;
    padding-bottom: 5px;
    padding-left: 4px;
    border-bottom: 1px solid #1E2024;
    min-height: 28px;
}

QTreeWidget::item:hover {
    background-color: #282A2E;
    border-bottom: 1px solid #282A2E;
}

QTreeWidget::item:selected {
    background-color: #0D2140;
    color: #ADC6FF;
    border-left: 2px solid #4B8EFF;
    border-bottom: 1px solid #0D2140;
}

QTreeWidget::item:selected:hover {
    background-color: #112650;
}

QTreeWidget QHeaderView::section {
    background-color: #1A1C20;
    color: #8B90A0;
    font-size: 11px;
    font-weight: 700;
    border: none;
    border-bottom: 1px solid #414755;
    padding: 4px 8px;
}

QTreeWidget::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #8B90A0;
    border-radius: 3px;
    background-color: transparent;
}

QTreeWidget::indicator:checked {
    background-color: #4B8EFF;
    border-color: #4B8EFF;
}

QTreeWidget::indicator:indeterminate {
    background-color: #0D2140;
    border-color: #4B8EFF;
}

QTreeWidget::indicator:hover {
    border-color: #ADC6FF;
}

QTreeWidget::branch:closed:has-children {
    color: #8B90A0;
}

QTreeWidget::branch:open:has-children {
    color: #8B90A0;
}

/* ── Table Widget (Tracks) ───────────────────────────────────────────── */
QTableWidget {
    background-color: #1E2024;
    alternate-background-color: #1A1C20;
    color: #E2E2E8;
    border: none;
    gridline-color: #282A2E;
    outline: none;
    selection-background-color: #0D2140;
    selection-color: #ADC6FF;
}

QTableWidget::item {
    padding: 4px 8px;
    border: none;
}

QTableWidget::item:selected {
    background-color: #0D2140;
    color: #ADC6FF;
}

QTableWidget::item:hover {
    background-color: #282A2E;
}

QHeaderView {
    background-color: #1A1C20;
}

QHeaderView::section {
    background-color: #1A1C20;
    color: #8B90A0;
    font-size: 11px;
    font-weight: 700;
    border: none;
    border-bottom: 1px solid #414755;
    border-right: 1px solid #282A2E;
    padding: 4px 8px;
}

QHeaderView::section:hover {
    background-color: #282A2E;
    color: #C1C6D7;
}

QHeaderView::section:last {
    border-right: none;
}

QHeaderView::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #8B90A0;
    width: 0;
    height: 0;
    subcontrol-position: center right;
    margin-right: 6px;
}

QHeaderView::up-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid #ADC6FF;
    width: 0;
    height: 0;
    subcontrol-position: center right;
    margin-right: 6px;
}

/* ── Log panel ───────────────────────────────────────────────────────── */
QFrame#logFrame {
    background-color: #0C0E12;
    border-top: 1px solid #414755;
}

QPlainTextEdit#logText {
    background-color: #0C0E12;
    color: #8B90A0;
    border: none;
    selection-background-color: #282A2E;
    selection-color: #E2E2E8;
}

/* ── Scrollbars ──────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background-color: transparent;
    width: 6px;
    margin: 0;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #414755;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #8B90A0;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: none;
    height: 0px;
    border: none;
}

QScrollBar:horizontal {
    background-color: transparent;
    height: 6px;
    margin: 0;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #414755;
    border-radius: 3px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #8B90A0;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: none;
    width: 0px;
    border: none;
}

/* ── Tooltip ─────────────────────────────────────────────────────────── */
QToolTip {
    background-color: #1E2024;
    color: #E2E2E8;
    border: 1px solid #414755;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}
"""


def apply_theme(app: QApplication) -> None:
    """Apply Sonic Precision dark theme to the QApplication."""
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
