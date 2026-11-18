"""Wellenform-Anzeige im Player – ersetzt den Zeitschieberegler (gleiche Schnittstelle)."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from mog.core.track import format_duration

from .theme import C


def _rgb(hexcol):
    c = QColor(hexcol)
    return np.array([c.red(), c.green(), c.blue()], dtype=np.float32)


class WaveformWidget(QWidget):
    sliderPressed = Signal()
    sliderReleased = Signal()
    sliderMoved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._min, self._max, self._val = 0, 0, 0
        self._data = None
        self._loading = False
        self._img_played = None
        self._img_rest = None
        self._dragging = False

    # --- Slider-Schnittstelle -----------------------------------------------
    def setRange(self, lo, hi):
        self._min, self._max = lo, max(lo, hi)
        self.update()

    def setValue(self, v):
        self._val = max(self._min, min(self._max, int(v)))
        self.update()

    def value(self):
        return self._val

    def maximum(self):
        return self._max

    def minimum(self):
        return self._min

    # --- Daten ---------------------------------------------------------------
    def set_data(self, arr):
        self._data = arr
        self._loading = False
        self._rebuild()
        self.update()

    def set_loading(self, on):
        self._loading = on
        if on:
            self._data = None
            self._img_played = self._img_rest = None
        self.update()

    def retheme(self):
        self._rebuild()
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._rebuild()

    def _rebuild(self):
        """Rechnet die Wellenform einmal je Größe/Farbschema in zwei Bilder (gespielt/ungespielt)."""
        if self._data is None or self.width() < 4 or self.height() < 4:
            self._img_played = self._img_rest = None
            return
        dpr = self.devicePixelRatioF()
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        d = self._data.astype(np.float32)
        n = len(d)
        # je Bildspalte das Maximum über die zugehörigen Datenspalten
        edges = np.linspace(0, n, w + 1).astype(int)
        edges[1:] = np.maximum(edges[1:], edges[:-1] + 1)
        idx = np.minimum(edges[:-1], n - 1)
        amp = np.maximum.reduceat(d[:, 0], idx) / 255.0
        bands = np.add.reduceat(d[:, 1:4], idx, axis=0)
        bands /= bands.sum(axis=1, keepdims=True) + 1e-9
        cols = (bands[:, 0:1] * _rgb(C["wave_low"]) + bands[:, 1:2] * _rgb(C["wave_mid"])
                + bands[:, 2:3] * _rgb(C["wave_high"]))
        half = h / 2.0
        heights = np.clip(amp * (half - 1), 1, half)
        ys = np.arange(h)[:, None]
        mask = np.abs(ys - half + 0.5) <= heights[None, :]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[..., :3] = np.clip(cols[None, :, :], 0, 255).astype(np.uint8)
        rgba[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
        rest = rgba.copy()
        rest[..., 3] = np.where(mask, 95, 0).astype(np.uint8)
        self._img_played = self._to_image(rgba, dpr)
        self._img_rest = self._to_image(rest, dpr)

    @staticmethod
    def _to_image(arr, dpr):
        h, w = arr.shape[:2]
        img = QImage(arr.tobytes(), w, h, 4 * w, QImage.Format_RGBA8888).copy()
        img.setDevicePixelRatio(dpr)
        return img

    # --- Zeichnen -------------------------------------------------------------
    def _frac(self):
        span = self._max - self._min
        return (self._val - self._min) / span if span > 0 else 0.0

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        x = self._frac() * w
        if self._img_played is not None:
            p.drawImage(QPointF(0, 0), self._img_rest)
            p.save()
            p.setClipRect(QRectF(0, 0, x, h))
            p.drawImage(QPointF(0, 0), self._img_played)
            p.restore()
        else:
            # Ohne Wellenform: schlanker Fortschrittsbalken
            y = h / 2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["border2"]))
            p.drawRoundedRect(QRectF(0, y - 2, w, 4), 2, 2)
            p.setBrush(QColor(C["accent"]))
            p.drawRoundedRect(QRectF(0, y - 2, x, 4), 2, 2)
            if self._loading:
                p.setPen(QColor(C["text3"]))
                f = p.font()
                f.setPixelSize(10)
                p.setFont(f)
                p.drawText(QRectF(0, 0, w, y - 4), Qt.AlignCenter, "Wellenform wird berechnet …")
        if self._max > self._min:
            p.setPen(QPen(QColor(C["accent"]), 2))
            p.drawLine(QPointF(x, 1), QPointF(x, h - 1))
        p.end()

    # --- Maus -------------------------------------------------------------------
    def _value_at(self, px):
        f = min(1.0, max(0.0, px / max(1, self.width())))
        return int(self._min + f * (self._max - self._min))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._max > self._min:
            self._dragging = True
            self.sliderPressed.emit()
            self.setValue(self._value_at(e.position().x()))
            self.sliderMoved.emit(self._val)

    def mouseMoveEvent(self, e):
        if self._max > self._min:
            v = self._value_at(e.position().x())
            QToolTip.showText(e.globalPosition().toPoint(), format_duration(v / 1000) or "0:00", self)
            if self._dragging:
                self.setValue(v)
                self.sliderMoved.emit(v)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.sliderReleased.emit()
