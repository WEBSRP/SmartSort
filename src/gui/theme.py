"""Small, shared native Qt theme. No assets, effects, or extra dependencies."""

from pathlib import Path

from PyQt6.QtGui import QColor, QPalette


LIGHT = dict(
    background="#f5f4f0", surface="#ffffff", raised="#eeede8", sidebar="#eeede7",
    text="#252a28", muted="#626b65", border="#d8dcd5", accent="#315e4d",
    hover="#244a3c", tint="#e1ebe4", disabled="#89928b", selection="#dce9e0",
    success="#286343", warning="#805b19", danger="#a83f3f",
)
DARK = dict(
    background="#191d1b", surface="#222724", raised="#2b322d", sidebar="#1e231f",
    text="#eceee8", muted="#a6b0a7", border="#3c463e", accent="#a4c6ac",
    hover="#b9d7bf", tint="#303f34", disabled="#79867b", selection="#3b5142",
    success="#a4c6ac", warning="#e1be7c", danger="#edaaa4",
)


def palette(colors):
    result = QPalette()
    roles = {
        "Window": "background", "WindowText": "text", "Base": "surface",
        "AlternateBase": "raised", "ToolTipBase": "surface", "ToolTipText": "text",
        "Text": "text", "Button": "surface", "ButtonText": "text",
        "BrightText": "surface", "Highlight": "selection", "HighlightedText": "text",
        "Link": "accent", "PlaceholderText": "muted",
    }
    for role, token in roles.items():
        result.setColor(getattr(QPalette.ColorRole, role), QColor(colors[token]))
    for role in ("Text", "WindowText", "ButtonText"):
        result.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role),
                        QColor(colors["disabled"]))
    return result


def stylesheet(c):
    # Qt needs a real resource URL; SVG data URLs used to leave checks invisible.
    c = dict(c)
    icon = "check-dark.svg" if c["background"] == DARK["background"] else "check-light.svg"
    c["check"] = (Path(__file__).resolve().parents[2] / "assets" / "icons" / icon).as_posix()
    return """
    QWidget { color: %(text)s; font-family: 'Inter', 'Segoe UI', 'DejaVu Sans'; font-size: 13px; }
    QMainWindow, QWidget#shell, QTabWidget::pane { background: %(background)s; }
    QTabWidget::pane { border: none; }
    QFrame#sidebar { background: %(sidebar)s; border-right: 1px solid %(border)s; }
    QFrame#pageHeader { border-bottom: 1px solid %(border)s; }
    QLabel { background: transparent; }
    QLabel#brand { font-size: 21px; font-weight: 600; }
    QLabel#brandMark { background: %(accent)s; color: %(background)s; border-radius: 11px;
                       font-size: 20px; font-weight: 700; }
    QLabel#eyebrow { color: %(muted)s; font-size: 10px; font-weight: 600; }
    QLabel#pageTitle { font-size: 27px; font-weight: 600; }
    QLabel#pageSubtitle, QLabel[role="muted"] { color: %(muted)s; }
    QLabel#sectionTitle { font-size: 14px; font-weight: 600; }
    QFrame[class="Card"], QWidget[class="Card"] {
        background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px;
    }
    QLabel#card_title { color: %(muted)s; font-size: 11px; font-weight: 500; }
    QLabel#card_value { color: %(text)s; font-size: 24px; font-weight: 600; }
    QLabel[tone="success"], QLabel#card_value[tone="success"] { color: %(success)s; }
    QLabel[tone="warning"], QLabel#card_value[tone="warning"] { color: %(warning)s; }
    QLabel[tone="danger"], QLabel#card_value[tone="danger"] { color: %(danger)s; }
    QFrame#separator { background: %(border)s; max-height: 1px; border: none; }
    QPushButton {
        background: %(surface)s; border: 1px solid %(border)s; border-radius: 6px;
        padding: 8px 14px; font-weight: 500; min-height: 18px;
    }
    QPushButton:hover { background: %(raised)s; border-color: %(muted)s; }
    QPushButton:pressed { background: %(selection)s; }
    QPushButton:focus { border: 1px solid %(accent)s; }
    QPushButton#primary { background: %(accent)s; color: %(background)s; border-color: %(accent)s; }
    QPushButton#primary:hover { background: %(hover)s; border-color: %(hover)s; }
    QPushButton#navButton {
        text-align: left; border: 1px solid transparent; background: transparent;
        padding: 11px 14px; color: %(muted)s;
    }
    QPushButton#navButton:hover { background: %(raised)s; color: %(text)s; }
    QPushButton#navButton:checked { background: %(tint)s; color: %(accent)s; font-weight: 600; }
    QPushButton#navButton:focus { border-color: %(accent)s; }
    QPushButton:disabled, QPushButton#primary:disabled {
        color: %(disabled)s; background: %(raised)s; border-color: %(border)s;
    }
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
        background: %(surface)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 6px; padding: 8px; selection-background-color: %(selection)s;
        selection-color: %(text)s;
    }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {
        border-color: %(accent)s;
    }
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: %(disabled)s; background: %(raised)s; }
    QComboBox { padding-right: 24px; min-height: 18px; }
    QComboBox QAbstractItemView { background: %(surface)s; color: %(text)s;
        selection-background-color: %(selection)s; selection-color: %(text)s; outline: none; }
    QCheckBox { spacing: 9px; background: transparent; padding: 4px 0; }
    QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid %(muted)s;
        border-radius: 4px; background: %(surface)s; }
    QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s;
        image: url("%(check)s"); }
    QCheckBox::indicator:hover, QCheckBox::indicator:focus { border-color: %(accent)s; }
    QCheckBox::indicator:disabled { border-color: %(border)s; background: %(raised)s; }
    QCheckBox:disabled { color: %(disabled)s; }
    QGroupBox { background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px;
        margin-top: 14px; padding: 18px 12px 12px; font-weight: 600; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
        left: 12px; padding: 0 5px; }
    QScrollArea { background: transparent; border: none; }
    QWidget#scrollContent { background: %(background)s; }
    QTableWidget { background: %(surface)s; alternate-background-color: %(raised)s;
        border: 1px solid %(border)s; border-radius: 8px; gridline-color: %(border)s;
        selection-background-color: %(selection)s; selection-color: %(text)s; }
    QTableWidget::item { padding: 6px; border: none; }
    QHeaderView { background: %(surface)s; }
    QHeaderView::section { background: %(raised)s; color: %(muted)s;
        border: none; border-bottom: 1px solid %(border)s; padding: 10px 8px; font-weight: 600; }
    QTableCornerButton::section { background: %(raised)s; border: none; }
    QProgressBar { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s;
        border-radius: 5px; text-align: center; min-height: 20px; }
    QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
    QScrollBar::handle:vertical { background: %(border)s; min-height: 28px; border-radius: 5px; }
    QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
    QScrollBar::handle:horizontal { background: %(border)s; min-width: 28px; border-radius: 5px; }
    QScrollBar::handle:hover { background: %(muted)s; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QMenu { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 5px; }
    QMenu::item { padding: 7px 22px; border-radius: 4px; }
    QMenu::item:selected { background: %(selection)s; }
    QMenu::item:disabled { color: %(disabled)s; }
    QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 6px; }
    QDialog, QMessageBox { background: %(background)s; }
    """ % c
