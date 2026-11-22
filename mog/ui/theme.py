"""Farbschemata für MOG: Dunkel (Standard), Hell und „System“ (folgt Windows/macOS).

Alle Oberflächenteile lesen ihre Farben aus dem Wörterbuch ``C``. Beim Umschalten wird ``C``
an Ort und Stelle ersetzt und das Stylesheet neu gesetzt – ohne Neustart.
"""
from PySide6.QtGui import QColor, QPalette

DARK = {
    "bg": "#111217", "panel": "#171820", "panel2": "#1C1E27", "row_alt": "#15161D",
    "border": "#262833", "border2": "#323543", "hover": "#22242F",
    "text": "#E8E9EF", "text2": "#9A9CAB", "text3": "#6B6E7E",
    "accent": "#FF4D6D", "accent2": "#FF8A1F", "accent3": "#9B3BFF",
    "sel": "#3A1F2E", "sel_text": "#FFFFFF", "sel_border": "#FF4D6D",
    "ok": "#3DDC97", "warn": "#F5B83D", "bad": "#FF5C5C",
    "icon": "#C9CAD6", "icon_active": "#FFFFFF", "icon_disabled": "#5A5D6C",
    "danger_bg": "#3A1A1F", "danger_hover": "#4A1F26", "danger_border": "#6B2530", "danger_text": "#FFB3BE",
    "warnbox_bg": "#33280F", "warnbox_border": "#5C4716", "warnbox_text": "#F5D38B",
    "cover_bg": "#1C1E27", "cover_disc": "#0F1015", "cover_label": "#2C2F3B", "cover_groove": (255, 255, 255, 14),
    "wave_low": "#4D7CFF", "wave_mid": "#FF9A3D", "wave_high": "#F2F2F7", "wave_bg": "#121318",
    "logo": "dark",
}

LIGHT = {
    "bg": "#F3F4F7", "panel": "#FFFFFF", "panel2": "#EEF0F4", "row_alt": "#F7F8FA",
    "border": "#E1E3EA", "border2": "#CBCED8", "hover": "#E6E8EE",
    "text": "#16171D", "text2": "#555865", "text3": "#868997",
    "accent": "#E3345A", "accent2": "#D96A00", "accent3": "#7B2BE0",
    "sel": "#FFE0E7", "sel_text": "#16171D", "sel_border": "#E3345A",
    "ok": "#178A5C", "warn": "#A86A00", "bad": "#D12F2F",
    "icon": "#474A57", "icon_active": "#111217", "icon_disabled": "#B4B7C2",
    "danger_bg": "#FDECEE", "danger_hover": "#FADADF", "danger_border": "#F2B5BF", "danger_text": "#B4233C",
    "warnbox_bg": "#FFF6E0", "warnbox_border": "#F0D9A0", "warnbox_text": "#7A5300",
    "cover_bg": "#EEF0F4", "cover_disc": "#26272E", "cover_label": "#4A4D5A", "cover_groove": (255, 255, 255, 22),
    "wave_low": "#2F5BE0", "wave_mid": "#E07A12", "wave_high": "#3A3D48", "wave_bg": "#F3F4F7",
    "logo": "light",
}

C = dict(DARK)
MODES = {"dark": "Dunkel", "light": "Hell", "system": "Wie System"}
_current = {"mode": "dark", "resolved": "dark"}


def resolve(mode):
    if mode == "system":
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication
            return "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"
        except Exception:
            return "dark"
    return "light" if mode == "light" else "dark"


def set_mode(mode):
    """Setzt die Farben (ohne Stylesheet). Gibt das tatsächlich verwendete Schema zurück."""
    resolved = resolve(mode)
    C.clear()
    C.update(LIGHT if resolved == "light" else DARK)
    _current.update(mode=mode, resolved=resolved)
    return resolved


def current_mode():
    return _current["mode"]


def is_light():
    return _current["resolved"] == "light"


def apply(app, mode, check_icon="", chevron_icon=""):
    """Schaltet das Farbschema live um."""
    set_mode(mode)
    app.setPalette(palette())
    app.setStyleSheet(stylesheet(check_icon, chevron_icon))


def gradient():
    return (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['accent2']}, "
            f"stop:0.6 {C['accent']}, stop:1 {C['accent3']})")


GRADIENT = gradient()   # für Altcode; Stylesheet nutzt gradient()


def palette():
    p = QPalette()
    p.setColor(QPalette.Window, QColor(C["bg"]))
    p.setColor(QPalette.WindowText, QColor(C["text"]))
    p.setColor(QPalette.Base, QColor(C["panel"]))
    p.setColor(QPalette.AlternateBase, QColor(C["row_alt"]))
    p.setColor(QPalette.ToolTipBase, QColor(C["panel2"]))
    p.setColor(QPalette.ToolTipText, QColor(C["text"]))
    p.setColor(QPalette.Text, QColor(C["text"]))
    p.setColor(QPalette.Button, QColor(C["panel2"]))
    p.setColor(QPalette.ButtonText, QColor(C["text"]))
    p.setColor(QPalette.BrightText, QColor("#FFFFFF"))
    p.setColor(QPalette.Highlight, QColor(C["sel"]))
    p.setColor(QPalette.HighlightedText, QColor(C["sel_text"]))
    p.setColor(QPalette.Link, QColor(C["accent"]))
    p.setColor(QPalette.PlaceholderText, QColor(C["text3"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(C["text3"]))
    return p


def stylesheet(check_icon="", chevron_icon=""):
    check_icon = check_icon.replace("\\", "/")
    chevron_icon = chevron_icon.replace("\\", "/")
    chevron_up = chevron_icon.replace("chevron.svg", "chevron_up.svg")
    if is_light():
        chevron_icon = chevron_icon.replace("chevron.svg", "chevron_light.svg")
        chevron_up = chevron_up.replace("chevron_up.svg", "chevron_up_light.svg")
    GRADIENT = gradient()
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {C['text']}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {C['bg']}; }}
QToolTip {{ background: {C['panel2']}; color: {C['text']}; border: 1px solid {C['border2']};
           padding: 5px 7px; border-radius: 4px; }}

#HeaderBar {{ background: {C['panel']}; border-bottom: 1px solid {C['border']}; }}
#PlayerBar {{ background: {C['panel']}; border-top: 1px solid {C['border']}; }}
#Sidebar, #DetailsPanel, #EmptyState {{ background: {C['panel']}; }}
#Sidebar {{ border-right: 1px solid {C['border']}; }}
#DetailsPanel {{ border-left: 1px solid {C['border']}; }}

QToolButton#HeaderButton {{
    background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 4px 4px; color: {C['text2']}; font-size: 11px; min-width: 50px;
}}
QToolButton#HeaderButton:hover {{ background: {C['panel2']}; border-color: {C['border2']}; color: {C['text']}; }}
QToolButton#HeaderButton:pressed {{ background: {C['border']}; }}
QToolButton#HeaderButton::menu-indicator {{ image: none; }}

QLabel#VersionLabel {{ color: {C['text3']}; font-size: 11px; font-weight: 600; padding: 0 0 9px 4px; }}
QPushButton#UpdatePill {{ background: {C['accent2']}; color: #FFFFFF; border: none; border-radius: 10px;
    padding: 3px 11px; font-size: 11px; font-weight: 700; margin: 0 0 7px 8px; }}
QPushButton#UpdatePill:hover {{ background: {C['accent']}; }}
QLabel#Credit {{ color: {C['text3']}; font-size: 11px; padding: 0 10px 0 12px; letter-spacing: 0.5px; }}
QFrame#HeaderSep {{ background: {C['border']}; max-width: 1px; min-width: 1px; margin: 10px 4px; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {C['bg']}; border: 1px solid {C['border2']}; border-radius: 6px;
    padding: 5px 8px; selection-background-color: {C['accent']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {C['accent']};
}}
QLineEdit#SearchField {{ border-radius: 16px; padding: 6px 12px 6px 30px; min-width: 220px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{chevron_icon}"); width: 12px; height: 12px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 18px;
    border: none; background: transparent; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
QAbstractSpinBox::up-arrow {{ image: url("{chevron_up}"); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url("{chevron_icon}"); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {C['panel2']}; border: 1px solid {C['border2']};
                               selection-background-color: {C['sel']}; }}

QPushButton {{
    background: {C['panel2']}; border: 1px solid {C['border2']}; border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {C['text3']}; background: {C['hover']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton:disabled {{ color: {C['text3']}; border-color: {C['border']}; }}
QPushButton#Primary {{ background: {GRADIENT}; border: none; color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {C['accent']}; }}
QPushButton#Primary:disabled {{ background: {C['border2']}; color: {C['text3']}; }}
QPushButton#Danger {{ background: {C['danger_bg']}; border: 1px solid {C['danger_border']}; color: {C['danger_text']}; }}
QPushButton#Danger:hover {{ background: {C['danger_hover']}; border-color: {C['bad']}; color: {C['danger_text']}; }}

QTableView {{
    background: {C['panel']}; alternate-background-color: {C['row_alt']};
    border: none; gridline-color: transparent;
    selection-background-color: {C['sel']}; selection-color: {C['sel_text']};
}}
QTableView::item {{ padding: 0 8px; border: none; }}
QTableView::item:selected {{ background: {C['sel']}; color: {C['sel_text']}; }}
QHeaderView {{ background: {C['panel']}; }}
QHeaderView::section {{
    background: {C['panel']}; color: {C['text3']}; border: none;
    border-bottom: 1px solid {C['border']}; border-right: 1px solid {C['border']};
    padding: 6px 8px; font-size: 11px; font-weight: 600; text-transform: uppercase;
}}
QHeaderView::section:hover {{ color: {C['text']}; }}
QTableCornerButton::section {{ background: {C['panel']}; border: none; }}

QTreeWidget, QListWidget {{ background: transparent; border: none; }}
QTreeWidget::item, QListWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {C['panel2']}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {C['sel']}; color: {C['sel_text']}; }}
QTreeWidget#DupTree {{ background: {C['panel']}; border: 1px solid {C['border']}; border-radius: 8px; }}
QTreeWidget#DupTree::item {{ border-radius: 0; padding: 3px 4px; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {C['border2']}; border-radius: 5px; min-height: 30px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: {C['text3']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {C['border2']}; border-radius: 5px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSlider::groove:horizontal {{ height: 4px; background: {C['border2']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {GRADIENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {C['icon_active'] if not is_light() else '#FFFFFF'}; border: 1px solid {C['border2']}; width: 12px; height: 12px; margin: -4px 0;
                              border-radius: 6px; }}
QSlider::handle:horizontal:hover {{ background: {C['accent']}; }}

QProgressBar {{ background: {C['bg']}; border: 1px solid {C['border2']}; border-radius: 5px;
               text-align: center; height: 14px; font-size: 11px; color: {C['text2']}; }}
QProgressBar::chunk {{ background: {GRADIENT}; border-radius: 4px; }}

QMenu {{ background: {C['panel2']}; border: 1px solid {C['border2']}; padding: 4px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 26px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['sel']}; color: {C['sel_text']}; }}
QMenu::item:disabled {{ color: {C['text3']}; }}
QMenu::separator {{ height: 1px; background: {C['border2']}; margin: 4px 6px; }}
QMenu::icon {{ padding-left: 6px; }}

QStatusBar {{ background: {C['panel']}; color: {C['text2']}; border-top: 1px solid {C['border']}; }}
QStatusBar QLabel {{ color: {C['text2']}; }}
QSplitter::handle {{ background: {C['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}

QTabWidget::pane {{ border: 1px solid {C['border']}; border-radius: 8px; top: -1px; background: {C['panel']}; }}
QTabBar::tab {{ background: transparent; color: {C['text2']}; padding: 8px 16px; border: none;
               border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}
QTabBar::tab:hover {{ color: {C['text']}; }}

QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator, QTreeView::indicator, QTableView::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator, QTreeView::indicator, QTableView::indicator {{ border: 1px solid {C['border2']}; border-radius: 4px; background: {C['bg']}; }}
QCheckBox::indicator:checked, QTreeView::indicator:checked, QTableView::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']};
                                image: url("{check_icon}"); }}
QRadioButton::indicator {{ border: 1px solid {C['border2']}; border-radius: 8px; background: {C['bg']}; }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
    fx:0.5, fy:0.5, stop:0 white, stop:0.35 white, stop:0.45 {C['accent']}, stop:1 {C['accent']});
    border-color: {C['accent']}; }}

QGroupBox {{ border: 1px solid {C['border']}; border-radius: 8px; margin-top: 14px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {C['text2']}; }}

QLabel#Muted {{ color: {C['text2']}; }}
QLabel#Hint {{ color: {C['text3']}; font-size: 12px; }}
QLabel#SectionTitle {{ color: {C['text3']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QLabel#BigTitle {{ font-size: 17px; font-weight: 700; }}
QLabel#Warning {{ background: {C['warnbox_bg']}; border: 1px solid {C['warnbox_border']}; color: {C['warnbox_text']}; border-radius: 6px; padding: 8px; }}
"""
