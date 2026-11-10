"""Integrierter Player (Qt Multimedia mit FFmpeg-Backend – spielt alle gängigen Formate)."""
import os

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

import logging

from mog.core.track import format_duration

from .icons import icon, placeholder_cover
from .theme import C

log = logging.getLogger("mog.player")

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
    HAVE_MM = True
except Exception:  # pragma: no cover
    HAVE_MM = False


def find_output_device(id_hex):
    """Ausgabegerät anhand der gespeicherten ID – sonst das Windows/macOS-Standardgerät."""
    if not HAVE_MM:
        return None
    if id_hex:
        for d in QMediaDevices.audioOutputs():
            if bytes(d.id()).hex() == id_hex:
                return d
    return QMediaDevices.defaultAudioOutput()


class ClickSlider(QSlider):
    """Slider, der direkt an die geklickte Stelle springt."""

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.maximum() > self.minimum():
            x = e.position().x() if hasattr(e, "position") else e.x()
            val = self.minimum() + (self.maximum() - self.minimum()) * x / max(1, self.width())
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(e)


class PlayerBar(QWidget):
    request_next = Signal()
    request_prev = Signal()
    now_playing = Signal(object)    # Track oder None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PlayerBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(72)
        self.track = None
        self._seeking = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 18, 8)
        lay.setSpacing(10)

        def tbtn(name, tip, size=34, icon_size=20):
            b = QToolButton()
            b.setIcon(icon(name))
            b.setIconSize(QSize(icon_size, icon_size))
            b.setFixedSize(size, size)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setStyleSheet(f"QToolButton {{ border-radius: {size // 2}px; }}"
                            f"QToolButton:hover {{ background: {C['panel2']}; }}")
            return b

        self.btn_prev = tbtn("prev", "Vorheriger Titel")
        self.btn_play = QToolButton()
        self.btn_play.setIcon(icon("play", "#FFFFFF"))
        self.btn_play.setIconSize(QSize(22, 22))
        self.btn_play.setFixedSize(44, 44)
        self.btn_play.setToolTip("Abspielen / Pause (Leertaste)")
        self.btn_play.setStyleSheet(
            "QToolButton { border-radius: 22px; background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {C['accent2']}, stop:0.6 {C['accent']}, stop:1 {C['accent3']}); }}"
            f"QToolButton:hover {{ background: {C['accent']}; }}")
        self.btn_stop = tbtn("stop", "Stopp")
        self.btn_next = tbtn("next", "Nächster Titel")
        for b in (self.btn_prev, self.btn_play, self.btn_stop, self.btn_next):
            lay.addWidget(b)
        lay.addSpacing(10)

        self.cover = QLabel()
        self.cover.setFixedSize(48, 48)
        self.cover.setScaledContents(True)
        self.cover.setPixmap(placeholder_cover(48))
        lay.addWidget(self.cover)

        info = QVBoxLayout()
        info.setSpacing(1)
        self.lbl_title = QLabel("Kein Titel geladen")
        self.lbl_title.setStyleSheet("font-weight: 600;")
        self.lbl_artist = QLabel("Doppelklick auf einen Titel zum Anhören")
        self.lbl_artist.setObjectName("Muted")
        for l in (self.lbl_title, self.lbl_artist):
            l.setMinimumWidth(180)
            l.setMaximumWidth(320)
        info.addStretch()
        info.addWidget(self.lbl_title)
        info.addWidget(self.lbl_artist)
        info.addStretch()
        lay.addLayout(info)
        lay.addSpacing(10)

        self.lbl_pos = QLabel("0:00")
        self.lbl_pos.setObjectName("Muted")
        self.lbl_pos.setFixedWidth(46)
        self.lbl_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.seek = ClickSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.lbl_dur = QLabel("0:00")
        self.lbl_dur.setObjectName("Muted")
        self.lbl_dur.setFixedWidth(46)
        lay.addWidget(self.lbl_pos)
        lay.addWidget(self.seek, 1)
        lay.addWidget(self.lbl_dur)
        lay.addSpacing(12)

        self.btn_mute = tbtn("volume", "Stumm schalten", 30, 18)
        self.vol = ClickSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.setFixedWidth(100)
        lay.addWidget(self.btn_mute)
        lay.addWidget(self.vol)

        self.player = None   # wird beim ersten Abspielen erzeugt (schnellerer Start)
        self.audio = None
        self.device_id = ""

        self.btn_play.clicked.connect(self.toggle)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_next.clicked.connect(self.request_next)
        self.btn_prev.clicked.connect(self._prev)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_release)
        self.seek.sliderMoved.connect(self._seek_move)
        self.vol.valueChanged.connect(self._set_volume)
        self.btn_mute.clicked.connect(self._toggle_mute)

    # --- Steuerung ---------------------------------------------------------
    def _ensure_player(self):
        if self.player is not None or not HAVE_MM or os.environ.get("MOG_NO_AUDIO"):
            return self.player is not None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(find_output_device(self.device_id), self)
        self.player.setAudioOutput(self.audio)
        self._set_volume(self.vol.value())
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)
        # Standardgerät gewechselt (z. B. Kopfhörer eingesteckt) -> folgen
        self._devices = QMediaDevices(self)
        self._devices.audioOutputsChanged.connect(self._outputs_changed)
        log.info("Player: Ausgabegerät '%s', Backend %s", self.audio.device().description(),
                 os.environ.get("QT_MEDIA_BACKEND", "Standard (ffmpeg)"))
        return True

    def set_device_id(self, id_hex):
        """Ausgabegerät wechseln ('' = Systemstandard)."""
        self.device_id = id_hex or ""
        if self.audio is not None:
            dev = find_output_device(self.device_id)
            self.audio.setDevice(dev)
            log.info("Player: Ausgabegerät gewechselt auf '%s'", dev.description())

    def _outputs_changed(self):
        if self.audio is not None and not self.device_id:
            self.audio.setDevice(QMediaDevices.defaultAudioOutput())

    def play_track(self, track, cover=None):
        if not self._ensure_player():
            self.lbl_artist.setText("Qt Multimedia nicht verfügbar")
            return
        self.track = track
        self.lbl_title.setText(_elide(track.display_title, 44))
        self.lbl_artist.setText(_elide(track.display_artist or track.filename, 50))
        self.lbl_title.setToolTip(track.path)
        if cover:
            pm = QPixmap()
            pm.loadFromData(cover[0])
            self.cover.setPixmap(pm if not pm.isNull() else placeholder_cover(48))
        else:
            self.cover.setPixmap(placeholder_cover(48))
        self.player.setSource(QUrl.fromLocalFile(track.path))
        self.player.play()
        self.now_playing.emit(track)

    def toggle(self):
        if not self.player:
            if self.track is None:
                self.request_next.emit()
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.track is not None:
            self.player.play()
        else:
            self.request_next.emit()

    def stop(self):
        if self.player:
            self.player.stop()

    def release_file(self, path):
        """Gibt die Datei frei (wichtig vor dem Löschen unter Windows)."""
        if self.player and self.track and self.track.path == path:
            self.player.stop()
            self.player.setSource(QUrl())
            self.track = None
            self.lbl_title.setText("Kein Titel geladen")
            self.lbl_artist.setText("")
            self.now_playing.emit(None)

    def is_playing(self):
        return bool(self.player and self.player.playbackState() == QMediaPlayer.PlayingState)

    def _prev(self):
        if self.player and self.player.position() > 3000:
            self.player.setPosition(0)
        else:
            self.request_prev.emit()

    # --- Slots -------------------------------------------------------------
    def _on_pos(self, ms):
        if not self._seeking:
            self.seek.setValue(ms)
        self.lbl_pos.setText(format_duration(ms / 1000) or "0:00")

    def _on_dur(self, ms):
        self.seek.setRange(0, ms)
        self.lbl_dur.setText(format_duration(ms / 1000) or "0:00")

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlayingState
        self.btn_play.setIcon(icon("pause" if playing else "play", "#FFFFFF"))

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.request_next.emit()

    def _on_error(self, err, msg=""):
        if err != QMediaPlayer.NoError:
            text = msg or self.player.errorString()
            log.warning("Wiedergabefehler (%s): %s – %s", err, text, self.track.path if self.track else "")
            self.lbl_artist.setText(f"Wiedergabefehler: {text}")
            self.lbl_artist.setToolTip("Details im Diagnose-Protokoll (Extras → Diagnose-Protokoll)")

    def _seek_move(self, v):
        self.lbl_pos.setText(format_duration(v / 1000) or "0:00")

    def _seek_release(self):
        self._seeking = False
        if self.player:
            self.player.setPosition(self.seek.value())

    def _set_volume(self, v):
        if self.audio is not None:
            # logarithmischer Verlauf fühlt sich natürlicher an
            self.audio.setVolume((v / 100.0) ** 2)
            self.audio.setMuted(False)
        self.btn_mute.setIcon(icon("mute" if v == 0 else "volume"))

    def _toggle_mute(self):
        if self.audio is not None:
            m = not self.audio.isMuted()
            self.audio.setMuted(m)
            self.btn_mute.setIcon(icon("mute" if m else "volume"))

    def seek_relative(self, seconds):
        if self.player:
            self.player.setPosition(max(0, self.player.position() + int(seconds * 1000)))


def _elide(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"
