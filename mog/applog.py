"""Diagnose-Protokoll (mog.log im App-Datenordner).

Schreibt Programmmeldungen, Qt-Warnungen (inkl. Audio/Multimedia) und unerwartete Fehler
in eine Datei, die der Nutzer bei Problemen weitergeben kann.
"""
import logging
import os
import platform
import sys
import threading

LOG_NAME = "mog.log"
MAX_BYTES = 2 * 1024 * 1024
_path = None


def log_path():
    return _path


def setup(data_dir, version):
    global _path
    os.makedirs(data_dir, exist_ok=True)
    _path = os.path.join(data_dir, LOG_NAME)
    # Bei Überlänge alte Datei als .1 behalten
    try:
        if os.path.getsize(_path) > MAX_BYTES:
            os.replace(_path, _path + ".1")
    except OSError:
        pass
    handler = logging.FileHandler(_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                                           "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())
    log = logging.getLogger("mog")
    log.info("=" * 60)
    log.info("MusicOrganizer %s gestartet – %s %s (%s), Python %s", version, platform.system(),
             platform.release(), platform.machine(), platform.python_version())

    def excepthook(exc_type, exc, tb):
        logging.getLogger("mog").error("Unerwarteter Fehler", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = excepthook
    threading.excepthook = lambda a: logging.getLogger("mog").error(
        "Fehler im Hintergrund-Thread", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def install_qt_handler():
    """Leitet Qt-Meldungen (z. B. 'qt.multimedia…') ins Protokoll um."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    qlog = logging.getLogger("qt")
    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    def handler(mode, ctx, msg):
        cat = getattr(ctx, "category", "") or ""
        qlog.log(levels.get(mode, logging.INFO), "%s%s", f"[{cat}] " if cat and cat != "default" else "", msg)
    qInstallMessageHandler(handler)


def multimedia_info():
    """Kurzer Bericht über Audio-Backend und -Geräte (für Protokoll und Einstellungen)."""
    try:
        from PySide6.QtMultimedia import QMediaDevices
        default = QMediaDevices.defaultAudioOutput()
        outs = QMediaDevices.audioOutputs()
        lines = [f"Backend: {os.environ.get('QT_MEDIA_BACKEND') or 'Standard (ffmpeg)'}",
                 f"Standard-Ausgabe: {default.description() or '–'}",
                 f"Ausgabegeräte ({len(outs)}):"]
        for d in outs:
            fmt = d.preferredFormat()
            lines.append(f"  • {d.description()}  ({fmt.sampleRate()} Hz, {fmt.channelCount()} Kanäle)")
        return "\n".join(lines)
    except Exception as e:  # pragma: no cover
        return f"Multimedia-Info nicht verfügbar: {e}"
