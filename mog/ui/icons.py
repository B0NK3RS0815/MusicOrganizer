"""Eigene Linien-Icons (SVG), Format-Badges und Logo-Darstellung."""
import math
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

from mog.core.formats import get_format
from mog.core.paths import resource


def _gear():
    pts = []
    for i in range(16):
        a = math.radians(i * 22.5 - 90)
        r = 9.2 if i % 2 == 0 else 7.0
        pts.append(f"{12 + r * math.cos(a):.2f},{12 + r * math.sin(a):.2f}")
    return f'<polygon points="{" ".join(pts)}" stroke-linejoin="round"/><circle cx="12" cy="12" r="3"/>'


# 24×24, Strichstärke 1.8 – 'S' = Strich, 'F' = gefüllt
_ICONS = {
    "play": ('F', '<path d="M7.5 4.8 19 12 7.5 19.2Z"/>'),
    "pause": ('F', '<rect x="6" y="5" width="4.2" height="14" rx="1.2"/><rect x="13.8" y="5" width="4.2" height="14" rx="1.2"/>'),
    "stop": ('F', '<rect x="6" y="6" width="12" height="12" rx="2"/>'),
    "prev": ('F', '<path d="M18 5.5v13L8.8 12Z"/><rect x="5.5" y="5.5" width="2.4" height="13" rx="1"/>'),
    "next": ('F', '<path d="M6 5.5v13l9.2-6.5Z"/><rect x="16.1" y="5.5" width="2.4" height="13" rx="1"/>'),
    "drive": ('S', '<path d="M3 14h18v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M3 14 5.8 5.5A2 2 0 0 1 7.7 4h8.6a2 2 0 0 1 1.9 1.5L21 14"/><circle cx="17" cy="17" r=".6"/><path d="M6.5 17h5"/>'),
    "folder": ('S', '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.6l2.2 2.2h7.2A2.5 2.5 0 0 1 21 9.7v7.8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>'),
    "file": ('S', '<path d="M6 3h8l4.5 4.5V19a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M14 3v4.5h4.5"/><circle cx="10" cy="16.5" r="1.8"/><path d="M11.8 16.5V11l3 1"/>'),
    "duplicates": ('S', '<rect x="8.5" y="8.5" width="12" height="12" rx="2.2"/><path d="M15.5 8.5V6a2.5 2.5 0 0 0-2.5-2.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>'),
    "convert": ('S', '<path d="M4 8.5h14.5"/><path d="M15 5l3.5 3.5L15 12"/><path d="M20 15.5H5.5"/><path d="M9 12l-3.5 3.5L9 19"/>'),
    "tag": ('S', '<path d="M3.5 12.2V5a1.5 1.5 0 0 1 1.5-1.5h7.2l8.3 8.3a1.5 1.5 0 0 1 0 2.1l-7 7a1.5 1.5 0 0 1-2.1 0z"/><circle cx="8.2" cy="8.2" r="1.4"/>'),
    "globe": ('S', '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="3.8" ry="9"/><path d="M3.3 9h17.4M3.3 15h17.4"/>'),
    "settings": ('S', _gear()),
    "trash": ('S', '<path d="M4 6.5h16"/><path d="M9.5 6.5V4.5h5v2"/><path d="M6 6.5l1 13a1.5 1.5 0 0 0 1.5 1.5h7a1.5 1.5 0 0 0 1.5-1.5l1-13"/><path d="M10 10.5v6.5M14 10.5v6.5"/>'),
    "search": ('S', '<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5 5"/>'),
    "volume": ('S', '<path d="M4 9.5v5h3.5l4.5 4V5.5l-4.5 4z" fill="currentColor"/><path d="M15.5 9a4 4 0 0 1 0 6"/><path d="M18 6.5a7.5 7.5 0 0 1 0 11"/>'),
    "mute": ('S', '<path d="M4 9.5v5h3.5l4.5 4V5.5l-4.5 4z" fill="currentColor"/><path d="m16 9.5 5 5M21 9.5l-5 5"/>'),
    "pulse": ('S', '<path d="M2.5 12h4l2.5-6.5 5 13 2.5-6.5h5"/>'),
    "refresh": ('S', '<path d="M20 11a8 8 0 0 0-14.3-4.6L4 8.5"/><path d="M4 4v4.5h4.5"/><path d="M4 13a8 8 0 0 0 14.3 4.6L20 15.5"/><path d="M20 20v-4.5h-4.5"/>'),
    "library": ('S', '<path d="M4 5h16M4 10h16M4 15h10M4 20h7"/><circle cx="18" cy="18" r="2.3"/><path d="M20.3 18v-6l-2 .8"/>'),
    "warning": ('S', '<path d="M12 3.5 21.5 20h-19z" stroke-linejoin="round"/><path d="M12 10v4.5"/><circle cx="12" cy="17.2" r=".4"/>'),
    "eye": ('S', '<path d="M2.5 12s3.5-6.5 9.5-6.5 9.5 6.5 9.5 6.5-3.5 6.5-9.5 6.5S2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>'),
    "x": ('S', '<path d="m6 6 12 12M18 6 6 18"/>'),
    "check": ('S', '<path d="m5 12.5 4.5 4.5L19 7.5"/>'),
    "lossless": ('S', '<path d="M3 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0"/>'),
    "low": ('S', '<path d="M4 20V14M9 20v-3M14 20v-1M19 20v-.5"/>'),
    "nobpm": ('S', '<path d="M2.5 12h4l2.5-6.5 5 13 2.5-6.5h5"/><path d="m4 4 16 16"/>'),
    "notags": ('S', '<path d="M3.5 12.2V5a1.5 1.5 0 0 1 1.5-1.5h7.2l8.3 8.3a1.5 1.5 0 0 1 0 2.1l-7 7a1.5 1.5 0 0 1-2.1 0z"/><path d="m4 4 16 16"/>'),
    "unlink": ('S', '<path d="M9 7H7a5 5 0 0 0 0 10h2M15 7h2a5 5 0 0 1 4 8"/><path d="m3 3 18 18"/>'),
    "plus": ('S', '<path d="M12 5v14M5 12h14"/>'),
    "image": ('S', '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m4 18 5.5-5 4 3.5 2.5-2 4.5 3.5"/>'),
    "swap": ('S', '<path d="M7 4v16M3.5 7.5 7 4l3.5 3.5"/><path d="M17 20V4M13.5 16.5 17 20l3.5-3.5"/>'),
    "save": ('S', '<path d="M5 3.5h11.5L20.5 7.5V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5z"/><path d="M7.5 3.5v5h8v-5"/><rect x="7" y="13" width="10" height="7.5" rx="1"/>'),
    "power": ('S', '<path d="M12 3v8.5"/><path d="M7 6.2a7.5 7.5 0 1 0 10 0"/>'),
    "rename": ('S', '<rect x="3" y="7" width="18" height="10" rx="2"/><path d="M13 4.5h2.5M14.25 4.5v15M13 19.5h2.5"/><path d="M6.5 12h4"/>'),
    "download": ('S', '<path d="M12 3.5v12"/><path d="m7 11 5 5 5-5"/><path d="M4.5 20.5h15"/>'),
    "info": ('S', '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r=".5"/>'),
    "undo": ('S', '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>'),
    "eraser": ('S', '<path d="m14.5 4.5 5 5-9 9H6l-2.5-2.5a1.5 1.5 0 0 1 0-2.1z"/><path d="M9 10l5 5"/><path d="M11 20.5h9"/>'),
    "fingerprint": ('S', '<path d="M7 18.5c1.5-2 2-4.2 2-6.5a3 3 0 0 1 6 0c0 3.5-1 6.5-3 9"/><path d="M4.5 15c.8-1.4 1-2.4 1-3a6.5 6.5 0 0 1 13 0c0 2.3-.4 4.5-1.2 6.5"/><path d="M12 12c0 3.2-1 6-2.8 8.5"/>'),
}


def _svg(name, color):
    kind, body = _ICONS[name]
    body = body.replace("currentColor", color)
    if kind == "F":
        attrs = f'fill="{color}" stroke="none"'
    else:
        attrs = (f'fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
                 f'stroke-linejoin="round"')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
            f'<g {attrs}>{body}</g></svg>')


def _render(svg_text, w, h, dpr=2.0):
    r = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


@lru_cache(maxsize=None)
def icon(name, color="#C9CAD6", active=None, size=24):
    ic = QIcon()
    ic.addPixmap(_render(_svg(name, color), size, size), QIcon.Normal)
    ic.addPixmap(_render(_svg(name, active or "#FFFFFF"), size, size), QIcon.Active)
    ic.addPixmap(_render(_svg(name, "#5A5D6C"), size, size), QIcon.Disabled)
    return ic


@lru_cache(maxsize=None)
def pixmap(name, color="#C9CAD6", size=24):
    return _render(_svg(name, color), size, size)


# --------------------------------------------------------------------------
# Format-Badges ("Logo" des Audioformats)
# --------------------------------------------------------------------------
@lru_cache(maxsize=None)
def format_badge(fmt_key, height=18, dpr=2.0):
    fmt = get_format(fmt_key)
    text = fmt.label
    f = QFont()
    f.setPixelSize(int(height * 0.58))
    f.setBold(True)
    f.setLetterSpacing(QFont.PercentageSpacing, 104)
    from PySide6.QtGui import QFontMetrics
    fm = QFontMetrics(f)
    w = max(fm.horizontalAdvance(text) + 14, int(height * 2.4))
    pm = QPixmap(int(w * dpr), int(height * dpr))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0.5, 0.5, w - 1, height - 1)
    col = QColor(fmt.color)
    path = QPainterPath()
    path.addRoundedRect(rect, 4, 4)
    if fmt.lossless:
        p.fillPath(path, col)
        p.setPen(QColor("#0E0F13"))
    else:
        bg = QColor(col)
        bg.setAlpha(40)
        p.fillPath(path, bg)
        p.setPen(col)
        p.drawPath(path)
        p.setPen(col.lighter(125))
    p.setFont(f)
    p.drawText(rect, Qt.AlignCenter, text)
    p.end()
    return pm


# --------------------------------------------------------------------------
# Logo
# --------------------------------------------------------------------------
def logo_pixmap(height, variant="dark", dpr=2.0):
    path = resource(f"mog_wordmark_{variant}.svg")
    r = QSvgRenderer(path)
    size = r.defaultSize()
    w = int(size.width() * height / size.height())
    pm = QPixmap(int(w * dpr), int(height * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def app_icon():
    ic = QIcon()
    r = QSvgRenderer(resource("mog_icon.svg"))
    for s in (16, 24, 32, 48, 64, 128, 256, 512):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p)
        p.end()
        ic.addPixmap(pm)
    return ic


def svg_pixmap(path, w, h, dpr=2.0):
    r = QSvgRenderer(path)
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def placeholder_cover(size=220, dpr=2.0):
    """Schallplatte als Platzhalter, wenn kein Cover vorhanden ist."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 10, 10)
    p.fillPath(path, QColor("#1C1E27"))
    c = size / 2
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0F1015"))
    p.drawEllipse(QRectF(c - size * 0.36, c - size * 0.36, size * 0.72, size * 0.72))
    pen_col = QColor(255, 255, 255, 14)
    from PySide6.QtGui import QPen
    p.setBrush(Qt.NoBrush)
    for i in range(9):
        r = size * (0.17 + i * 0.021)
        p.setPen(QPen(pen_col, 1))
        p.drawEllipse(QRectF(c - r, c - r, 2 * r, 2 * r))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2C2F3B"))
    p.drawEllipse(QRectF(c - size * 0.12, c - size * 0.12, size * 0.24, size * 0.24))
    p.setBrush(QColor("#1C1E27"))
    p.drawEllipse(QRectF(c - 4, c - 4, 8, 8))
    p.end()
    return pm
