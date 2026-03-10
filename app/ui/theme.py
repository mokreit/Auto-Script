from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

PREFERRED_FONTS = [
    "Segoe UI Variable Text",
    "Segoe UI",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
]

COMBO_ARROW_PATH = (
    Path(__file__).resolve().parent / "assets" / "chevron-down.svg"
).as_posix()

STYLESHEET = """
QWidget {
    color: #1f2328;
    font-size: 14px;
    background: transparent;
}

QWidget#AppShell {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #f5f7fb,
        stop: 0.48 #f3f5f8,
        stop: 1 #eef2f7
    );
}

QFrame#FunctionPanel,
QFrame#PageSurface,
QFrame#LogPanel,
QFrame#ControlPanel,
QFrame#SettingsCard,
QFrame#RunSummaryCard,
QFrame#HeroCard,
QFrame#SummaryPill,
QFrame#ScriptCard,
QFrame#CardDetailPanel {
    background: rgba(249, 250, 252, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.85);
}

QFrame#FunctionPanel {
    border-radius: 16px;
    background: rgba(248, 250, 252, 0.72);
}

QFrame#PageSurface,
QFrame#LogPanel {
    border-radius: 16px;
}

QFrame#SettingsCard,
QFrame#RunSummaryCard,
QFrame#ControlPanel,
QFrame#HeroCard {
    border-radius: 12px;
}

QFrame#ScriptCard,
QFrame#CardDetailPanel,
QFrame#SummaryPill {
    border-radius: 10px;
}

QFrame#ScriptCard {
    background: rgba(255, 255, 255, 0.82);
}

QFrame#ScriptCard[active="false"] {
    background: rgba(246, 247, 249, 0.8);
}

QFrame#ScriptCard[current="true"] {
    border: 1px solid rgba(15, 108, 189, 0.35);
    background: rgba(255, 255, 255, 0.9);
}

QLabel#BrandTitle {
    color: #111827;
    font-size: 22px;
    font-weight: 700;
}

QLabel#BrandCaption,
QLabel#HintText,
QLabel#EmptyState,
QLabel#LogCaption,
QLabel#ScriptPath,
QLabel#DetailLabel,
QLabel#SummaryPillTitle,
QLabel#RunSummaryMeta {
    color: #5f6b7a;
    font-size: 12px;
}

QLabel#PageTitle {
    color: #111827;
    font-size: 24px;
    font-weight: 700;
}

QLabel#LogPanelTitle {
    color: #111827;
    font-size: 20px;
    font-weight: 700;
}

QLabel#SectionMeta {
    color: #718096;
    font-size: 11px;
    font-weight: 600;
}

QLabel#HeroTitle {
    color: #0f172a;
    font-size: 28px;
    font-weight: 700;
}

QLabel#HeroText {
    color: #475467;
    font-size: 13px;
}

QLabel#SummaryPillValue,
QLabel#DetailValue {
    color: #111827;
    font-size: 14px;
    font-weight: 600;
}

QLabel#ScriptName {
    color: #0f172a;
    font-size: 16px;
    font-weight: 700;
}

QLabel#TagLabel {
    min-height: 22px;
    border-radius: 8px;
    padding: 0 9px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#TagLabel[tone="accent"] {
    background: rgba(15, 108, 189, 0.12);
    color: #0f5ea8;
    border: 1px solid rgba(15, 108, 189, 0.12);
}

QLabel#TagLabel[tone="neutral"] {
    background: rgba(99, 115, 129, 0.12);
    color: #435266;
    border: 1px solid rgba(99, 115, 129, 0.12);
}

QLabel#TagLabel[tone="success"] {
    background: rgba(16, 124, 16, 0.12);
    color: #0f6a0f;
    border: 1px solid rgba(16, 124, 16, 0.12);
}

QLabel#TagLabel[tone="warn"] {
    background: rgba(152, 103, 0, 0.12);
    color: #8a5f00;
    border: 1px solid rgba(152, 103, 0, 0.12);
}

QLabel#TagLabel[tone="muted"] {
    background: rgba(143, 149, 158, 0.12);
    color: #667085;
    border: 1px solid rgba(143, 149, 158, 0.12);
}

QLabel#RunSummaryResult {
    color: #111827;
    font-size: 20px;
    font-weight: 700;
}

QLabel#RunSummaryResult[state="idle"] {
    color: #667085;
}

QLabel#RunSummaryResult[state="running"] {
    color: #0f6cbd;
}

QLabel#RunSummaryResult[state="success"] {
    color: #107c10;
}

QLabel#RunSummaryResult[state="warning"],
QLabel#RunSummaryResult[state="skipped"] {
    color: #986700;
}

QLabel#RunSummaryResult[state="failed"],
QLabel#RunSummaryResult[state="stopped"] {
    color: #c42b1c;
}

QPushButton {
    min-height: 32px;
    border-radius: 8px;
    border: 1px solid rgba(208, 213, 221, 0.9);
    padding: 0 16px;
    color: #1f2328;
    background: rgba(255, 255, 255, 0.72);
    font-weight: 600;
}

QPushButton[compact="true"] {
    min-height: 28px;
    border-radius: 7px;
    padding: 0 12px;
}

QPushButton:hover {
    background: rgba(255, 255, 255, 0.94);
}

QPushButton:pressed {
    background: rgba(240, 244, 248, 0.98);
}

QPushButton:disabled {
    color: #98a2b3;
    background: rgba(249, 250, 251, 0.65);
    border-color: rgba(208, 213, 221, 0.65);
}

QPushButton[role="nav"] {
    min-height: 40px;
    text-align: left;
    padding-left: 14px;
    border: 1px solid transparent;
    background: transparent;
    color: #344054;
}

QPushButton[role="nav"]:hover {
    background: rgba(15, 108, 189, 0.08);
    color: #0f172a;
}

QPushButton[role="nav"]:checked {
    background: rgba(15, 108, 189, 0.14);
    color: #0f5ea8;
    border-color: rgba(15, 108, 189, 0.08);
}

QPushButton[role="primary"] {
    background: #0f6cbd;
    color: #ffffff;
    border-color: #0f6cbd;
}

QPushButton[role="primary"]:hover {
    background: #115ea3;
    border-color: #115ea3;
}

QPushButton[role="primary"]:pressed {
    background: #0f548c;
    border-color: #0f548c;
}

QPushButton[role="ghost"] {
    background: rgba(255, 255, 255, 0.68);
}

QPushButton[role="ghost"]:hover {
    background: rgba(255, 255, 255, 0.94);
}

QPushButton[role="danger"] {
    background: rgba(250, 243, 242, 0.94);
    color: #c42b1c;
    border-color: rgba(196, 43, 28, 0.14);
}

QPushButton[role="danger"]:hover {
    background: rgba(254, 237, 235, 0.98);
}

QLineEdit,
QSpinBox,
QComboBox,
QPlainTextEdit {
    border-radius: 8px;
    border: 1px solid rgba(208, 213, 221, 0.9);
    background: rgba(255, 255, 255, 0.88);
    padding: 8px 12px;
    selection-background-color: rgba(15, 108, 189, 0.22);
}

QLineEdit:hover,
QSpinBox:hover,
QComboBox:hover {
    border-color: rgba(152, 162, 179, 0.9);
}

QComboBox {
    combobox-popup: 0;
    padding-right: 34px;
}

QComboBox[wideDropDownHitbox="true"] {
    padding-right: 44px;
}

QLineEdit:focus,
QSpinBox:focus,
QComboBox:focus,
QPlainTextEdit:focus {
    border: 1px solid #0f6cbd;
}

QLineEdit[readOnly="true"] {
    color: #5f6b7a;
    background: rgba(246, 248, 250, 0.92);
}

QComboBox::drop-down,
QSpinBox::up-button,
QSpinBox::down-button {
    border: none;
    background: transparent;
    width: 24px;
}

QComboBox[wideDropDownHitbox="true"]::drop-down {
    width: 40px;
}

QComboBox::down-arrow {
    width: 10px;
    height: 6px;
    image: url("__COMBO_ARROW_PATH__");
}

QFrame#ComboPopupContainer {
    background: transparent;
    border: none;
}

QAbstractItemView#ComboPopupView {
    color: #1f2328;
    background: rgba(252, 253, 255, 0.98);
    border: 1px solid rgba(208, 213, 221, 0.95);
    border-radius: 12px;
    padding: 6px;
    outline: 0;
    selection-background-color: rgba(15, 108, 189, 0.14);
    selection-color: #0f172a;
}

QAbstractItemView#ComboPopupView::item {
    min-height: 32px;
    padding: 0 10px;
    border-radius: 8px;
    background: transparent;
}

QAbstractItemView#ComboPopupView::item:hover {
    background: rgba(15, 108, 189, 0.08);
}

QAbstractItemView#ComboPopupView::item:selected {
    background: rgba(15, 108, 189, 0.14);
    color: #0f5ea8;
}

QPlainTextEdit {
    background: rgba(12, 17, 29, 0.94);
    color: #e2e8f0;
    border: 1px solid rgba(30, 41, 59, 0.6);
}

QCheckBox {
    color: #344054;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid rgba(152, 162, 179, 0.9);
    background: rgba(255, 255, 255, 0.92);
}

QCheckBox::indicator:checked {
    background: #0f6cbd;
    border-color: #0f6cbd;
}

QScrollArea,
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    width: 10px;
    margin: 2px;
    background: transparent;
}

QScrollBar::handle:vertical {
    min-height: 32px;
    border-radius: 5px;
    background: rgba(98, 108, 123, 0.32);
}

QScrollBar::handle:vertical:hover {
    background: rgba(98, 108, 123, 0.5);
}

QSplitter::handle {
    background: transparent;
}

QSplitter::handle:horizontal {
    width: 8px;
}

QStatusBar {
    background: rgba(249, 250, 252, 0.82);
    border-top: 1px solid rgba(255, 255, 255, 0.85);
}

QStatusBar::item {
    border: none;
}

QStatusBar QLabel {
    color: #4b5565;
    padding: 0 8px;
}

QDialog,
QMessageBox {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #f7f9fc,
        stop: 1 #f1f5fa
    );
}

QDialogButtonBox QPushButton {
    min-width: 96px;
}
""".replace("__COMBO_ARROW_PATH__", COMBO_ARROW_PATH)


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = _pick_font()
    if font is not None:
        app.setFont(font)
    app.setStyleSheet(STYLESHEET)


def _pick_font() -> QFont | None:
    database = QFontDatabase()
    available_fonts = set(database.families())

    for family in PREFERRED_FONTS:
        if family in available_fonts:
            font = QFont(family, 10)
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            return font

    return None
