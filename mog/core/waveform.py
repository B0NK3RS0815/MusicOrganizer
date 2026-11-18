"""Wellenform-Berechnung für den Player (wie bei rekordbox: Höhe = Lautstärke, Farbe = Frequenzanteile).

Ergebnis je Spalte: Spitzenpegel und Anteile Bässe/Mitten/Höhen (jeweils 0–255) – kompakt als
Bytes speicherbar (4 Byte × Spaltenanzahl).
"""
import os
import sqlite3

import numpy as np

SR = 11025
COLUMNS = 1600


def compute(ffmpeg, path, columns=COLUMNS):
    """Dekodiert die Datei und gibt ein uint8-Array (columns × 4: peak, low, mid, high) zurück."""
    from .encoder import decode_mono
    y = decode_mono(ffmpeg, path, SR)
    return from_samples(y, columns)


def from_samples(y, columns=COLUMNS):
    n = len(y)
    if n < columns * 8:
        return None
    seg = n // columns
    y = y[: seg * columns].reshape(columns, seg)
    peak = np.abs(y).max(axis=1)
    rms = np.sqrt((y.astype(np.float64) ** 2).mean(axis=1))
    # Frequenzbänder je Spalte
    spec = np.abs(np.fft.rfft(y * np.hanning(seg), axis=1)) ** 2
    freqs = np.fft.rfftfreq(seg, 1 / SR)
    low = spec[:, freqs < 250].sum(axis=1)
    mid = spec[:, (freqs >= 250) & (freqs < 2500)].sum(axis=1)
    high = spec[:, freqs >= 2500].sum(axis=1) * 3.0   # Höhen haben wenig Energie -> anheben
    tot = low + mid + high + 1e-12
    # Höhe: Mischung aus Spitze und RMS, logarithmisch, auf 0..1 normiert
    amp = 0.6 * peak + 0.4 * rms * 1.8
    amp = amp / (amp.max() + 1e-9)
    amp = np.sqrt(amp)
    out = np.stack([amp, low / tot, mid / tot, high / tot], axis=1)
    return np.clip(out * 255, 0, 255).astype(np.uint8)


def to_bytes(arr):
    return arr.tobytes()


def from_bytes(b):
    a = np.frombuffer(b, dtype=np.uint8)
    return a.reshape(-1, 4) if len(a) % 4 == 0 else None


class WaveformCache:
    """Speichert berechnete Wellenformen (eigene kleine SQLite-Datei neben der Bibliothek)."""

    def __init__(self, path):
        self.path = path

    def _con(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.execute("CREATE TABLE IF NOT EXISTS waveforms (path TEXT PRIMARY KEY, size INTEGER, "
                    "mtime REAL, data BLOB)")
        return con

    def get(self, path):
        try:
            st = os.stat(path)
            con = self._con()
            try:
                r = con.execute("SELECT size, mtime, data FROM waveforms WHERE path=?", (path,)).fetchone()
            finally:
                con.close()
        except (OSError, sqlite3.Error):
            return None
        if r and r[0] == st.st_size and abs((r[1] or 0) - st.st_mtime) < 1:
            return from_bytes(r[2])
        return None

    def put(self, path, arr):
        try:
            st = os.stat(path)
            con = self._con()
            with con:
                con.execute("INSERT OR REPLACE INTO waveforms (path, size, mtime, data) VALUES (?, ?, ?, ?)",
                            (path, st.st_size, st.st_mtime, to_bytes(arr)))
            con.close()
        except (OSError, sqlite3.Error):
            pass

    def clear(self):
        try:
            con = self._con()
            with con:
                con.execute("DELETE FROM waveforms")
            con.execute("VACUUM")
            con.close()
        except sqlite3.Error:
            pass
