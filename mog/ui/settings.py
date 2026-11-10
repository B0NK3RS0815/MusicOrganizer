"""Einstellungen (QSettings) mit Standardwerten."""
import os

from PySide6.QtCore import QSettings, QStandardPaths

from mog import APP_NAME, APP_ORG

DEFAULTS = {
    "delete/permanent": False,
    "delete/remove_empty_dirs": True,
    "scan/skip_hidden": True,
    "startup/load_library": True,
    "audio/device": "",
    "audio/backend": "auto",
    "update/auto": True,
    "update/last_check": 0.0,
    "update/skip": "",
    "tools/ffmpeg": "",
    "tools/fpcalc": "",
    "online/contact": "",
    "online/discogs_token": "",
    "online/spotify_id": "",
    "online/spotify_secret": "",
    "online/acoustid_key": "",
    "bpm/range": "78–155",
    "bpm/round": True,
    "bpm/overwrite": False,
    "convert/preset": "mp3_320",
    "convert/out_dir": "",
    "convert/samplerate": 0,
    "dup/tags": True,
    "dup/identical": True,
    "dup/fingerprint": False,
    "dup/tolerance": 2.0,
    "dup/ignore_mix": False,
    "dup/threshold": 85,
}


class Settings:
    def __init__(self):
        self.q = QSettings(APP_ORG, APP_NAME)

    def get(self, key):
        default = DEFAULTS.get(key)
        v = self.q.value(key, default)
        if isinstance(default, bool):
            return v in (True, "true", "1", 1)
        if isinstance(default, int) and not isinstance(default, bool):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default
        return v if v is not None else ""

    def set(self, key, value):
        self.q.setValue(key, value)

    def value(self, key, default=None):
        return self.q.value(key, default)


def data_dir():
    d = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".musicorganizer")
    os.makedirs(d, exist_ok=True)
    return d


def db_path():
    return os.path.join(data_dir(), "library.sqlite")
