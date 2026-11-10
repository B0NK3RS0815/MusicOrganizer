"""Dunkles DJ-Theme für MOG."""
from PySide6.QtGui import QColor, QPalette

C = {
    "bg": "#111217",
    "panel": "#171820",
    "panel2": "#1C1E27",
    "row_alt": "#15161D",
    "border": "#262833",
    "border2": "#323543",
    "text": "#E8E9EF",
    "text2": "#9A9CAB",
    "text3": "#6B6E7E",
    "accent": "#FF4D6D",
    "accent2": "#FF8A1F",
    "accent3": "#9B3BFF",
    "sel": "#3A1F2E",
    "sel_border": "#FF4D6D",
    "ok": "#3DDC97",
    "warn": "#F5B83D",
    "bad": "#FF5C5C",
}

GRADIENT = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['accent2']}, "
            f"stop:0.6 {C['accent']}, stop:1 {C['accent3']})")


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
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.Link, QColor(C["accent"]))
    p.setColor(QPalette.PlaceholderText, QColor(C["text3"]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(C["text3"]))
    return p


def stylesheet(check_icon="", chevron_icon=""):
    check_icon = check_icon.replace("\\", "/")
    chevron_icon = chevron_icon.replace("\\", "/")
    chevron_up = chevron_icon.replace("chevron.svg", "chevron_up.svg")
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
QPushButton:hover {{ border-color: {C['text3']}; background: #22242F; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton:disabled {{ color: {C['text3']}; border-color: {C['border']}; }}
QPushButton#Primary {{ background: {GRADIENT}; border: none; color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {C['accent']}; }}
QPushButton#Primary:disabled {{ background: {C['border2']}; color: {C['text3']}; }}
QPushButton#Danger {{ background: #3A1A1F; border: 1px solid #6B2530; color: #FFB3BE; }}
QPushButton#Danger:hover {{ background: #4A1F26; border-color: {C['bad']}; color: white; }}

QTableView {{
    background: {C['panel']}; alternate-background-color: {C['row_alt']};
    border: none; gridline-color: transparent;
    selection-background-color: {C['sel']}; selection-color: white;
}}
QTableView::item {{ padding: 0 8px; border: none; }}
QTableView::item:selected {{ background: {C['sel']}; }}
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
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {C['sel']}; color: white; }}
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
QSlider::handle:horizontal {{ background: white; width: 12px; height: 12px; margin: -4px 0;
                              border-radius: 6px; }}
QSlider::handle:horizontal:hover {{ background: {C['accent']}; }}

QProgressBar {{ background: {C['bg']}; border: 1px solid {C['border2']}; border-radius: 5px;
               text-align: center; height: 14px; font-size: 11px; color: {C['text2']}; }}
QProgressBar::chunk {{ background: {GRADIENT}; border-radius: 4px; }}

QMenu {{ background: {C['panel2']}; border: 1px solid {C['border2']}; padding: 4px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 26px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['sel']}; }}
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
QLabel#Warning {{ background: #33280F; border: 1px solid #5C4716; color: #F5D38B; border-radius: 6px; padding: 8px; }}
"""
