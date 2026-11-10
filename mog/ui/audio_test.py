"""Testton zur Audio-Diagnose: einmal über den Player, einmal direkt an das Ausgabegerät."""
import logging
import math
import os
import struct
import tempfile
import wave

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, QUrl, Signal

log = logging.getLogger("mog.audiotest")

try:
    from PySide6.QtMultimedia import (QAudioFormat, QAudioOutput, QAudioSink, QMediaPlayer)
    HAVE_MM = True
except Exception:  # pragma: no cover
    HAVE_MM = False


def _tone(rate, seconds=1.2, freq=440.0):
    n = int(rate * seconds)
    fade = int(rate * 0.05)
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        yield 0.35 * env * math.sin(2 * math.pi * freq * i / rate)


def make_test_wav():
    path = os.path.join(tempfile.gettempdir(), "mog_testton.wav")
    rate = 44100
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<hh", int(v * 32767), int(v * 32767)) for v in _tone(rate)))
    return path


class ToneTester(QObject):
    result = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keep = []

    def via_player(self, device):
        """Testet den kompletten Weg der normalen Wiedergabe (QMediaPlayer + Backend)."""
        if not HAVE_MM:
            self.result.emit("✗ Qt Multimedia nicht verfügbar")
            return
        path = make_test_wav()
        player = QMediaPlayer(self)
        out = QAudioOutput(device, self)
        out.setVolume(1.0)
        player.setAudioOutput(out)
        state = {"err": ""}
        player.errorOccurred.connect(lambda e, m="": state.__setitem__("err", m or player.errorString()))
        self._keep += [player, out]
        player.setSource(QUrl.fromLocalFile(path))
        player.play()
        log.info("Testton (Player) auf '%s'", device.description())

        def check():
            if state["err"]:
                msg = f"✗ Player-Fehler: {state['err']}"
            elif player.position() > 0 or player.mediaStatus() == QMediaPlayer.EndOfMedia:
                msg = ("✓ Player hat den Ton abgespielt (Position läuft). Nichts gehört? Dann Gerät, "
                       "Lautstärke oder die Windows-Lautstärkemischung prüfen.")
            else:
                msg = "✗ Player startet nicht (Position bleibt 0) – andere Wiedergabe-Technik probieren."
            log.info("Testton (Player): %s", msg)
            self.result.emit(msg)
        QTimer.singleShot(900, check)

    def direct(self, device):
        """Spielt den Ton ohne Media-Backend direkt an das Gerät (QAudioSink)."""
        if not HAVE_MM:
            self.result.emit("✗ Qt Multimedia nicht verfügbar")
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        rate, ch = fmt.sampleRate(), fmt.channelCount()
        if fmt.sampleFormat() == QAudioFormat.Float:
            data = b"".join(struct.pack("<" + "f" * ch, *([v] * ch)) for v in _tone(rate))
        elif fmt.sampleFormat() == QAudioFormat.Int32:
            data = b"".join(struct.pack("<" + "i" * ch, *([int(v * 2147483647)] * ch)) for v in _tone(rate))
        else:
            data = b"".join(struct.pack("<" + "h" * ch, *([int(v * 32767)] * ch)) for v in _tone(rate))
        buf = QBuffer(self)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.ReadOnly)
        sink = QAudioSink(device, fmt, self)
        sink.setVolume(1.0)
        self._keep += [buf, sink]
        sink.start(buf)
        log.info("Testton (direkt) auf '%s', %d Hz, %d Kanäle, Zustand %s, Fehler %s",
                 device.description(), rate, ch, sink.state(), sink.error())

        def check():
            err = sink.error()
            # Enum je nach Qt-Version QAudio.Error oder QtAudio.Error -> über den Namen vergleichen
            if getattr(err, "name", str(err)).split(".")[-1] != "NoError":
                msg = f"✗ Gerät meldet Fehler ({getattr(err, 'name', err)}) – Gerät belegt oder nicht verfügbar?"
            elif sink.processedUSecs() > 0 or getattr(sink.state(), "name", "") in ("ActiveState", "IdleState"):
                msg = "✓ Ton direkt ans Gerät gesendet."
            else:
                msg = "✗ Gerät nimmt keine Daten an."
            log.info("Testton (direkt): %s", msg)
            self.result.emit(msg)
        QTimer.singleShot(900, check)
