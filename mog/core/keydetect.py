"""Tonart-Erkennung mit Ausgabe im Camelot-System (z. B. 8A = a-Moll).

Verfahren: Chromagramm (Energie je Halbton) aus dem Spektrum, dann Korrelation mit den
Dur-/Moll-Tonartprofilen nach Krumhansl-Kessler für alle 24 Tonarten.
"""
import numpy as np

SR = 11025
NFFT = 8192
HOP = 4096

NOTES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]

# Camelot-Rad: Dur = B, Moll = A
CAMELOT_MAJOR = {"C": "8B", "G": "9B", "D": "10B", "A": "11B", "E": "12B", "B": "1B", "F#": "2B",
                 "Db": "3B", "Ab": "4B", "Eb": "5B", "Bb": "6B", "F": "7B"}
CAMELOT_MINOR = {"Am": "8A", "Em": "9A", "Bm": "10A", "F#m": "11A", "C#m": "12A", "G#m": "1A",
                 "Ebm": "2A", "Bbm": "3A", "Fm": "4A", "Cm": "5A", "Gm": "6A", "Dm": "7A"}
CAMELOT_TO_MUSICAL = {v: k for k, v in {**CAMELOT_MAJOR, **CAMELOT_MINOR}.items()}

# Krumhansl-Kessler-Profile (in Tests mit linearer Spektralgewichtung am treffsichersten)
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTATIONS = {"camelot": "Camelot (8A)", "musical": "Klassisch (Am)", "both": "Beides (8A Am)"}

# Alternative Schreibweisen -> einheitlich
_ALIASES = {"C#": "Db", "D#": "Eb", "Gb": "F#", "G#": "Ab", "A#": "Bb", "Cb": "B", "Fb": "E", "E#": "F", "B#": "C",
            "Dbm": "C#m", "D#m": "Ebm", "Gbm": "F#m", "Abm": "G#m", "A#m": "Bbm"}


def chroma(y, sr=SR):
    if len(y) < NFFT:
        return None
    n = 1 + (len(y) - NFFT) // HOP
    win = np.hanning(NFFT)
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    band = (freqs >= 55) & (freqs <= 2000)
    midi = 69 + 12 * np.log2(freqs[band] / 440.0)
    pc = np.round(midi).astype(int) % 12
    # Gewichtung: Abstand zur exakten Halbtonfrequenz
    weight = np.cos(np.pi * (midi - np.round(midi))) ** 2
    acc = np.zeros(12)
    for i in range(n):
        frame = y[i * HOP:i * HOP + NFFT] * win
        mag = np.abs(np.fft.rfft(frame))[band]
        e = mag * weight
        c = np.bincount(pc, weights=e, minlength=12)
        s = c.sum()
        if s > 0:
            acc += c / s
    return acc if acc.sum() > 0 else None


def estimate_key(y, sr=SR):
    """Gibt (musikalischer Name, Camelot, Konfidenz 0..1) zurück oder (None, None, 0)."""
    c = chroma(y, sr)
    if c is None:
        return None, None, 0.0
    c = (c - c.mean()) / (c.std() + 1e-9)
    scores = []
    for root in range(12):
        for mode, prof in (("maj", _MAJ), ("min", _MIN)):
            p = np.roll(prof, root)
            p = (p - p.mean()) / p.std()
            scores.append((float(np.dot(c, p) / 12), root, mode))
    scores.sort(reverse=True)
    best, root, mode = scores[0]
    second = scores[1][0]
    name = NOTES[root] if mode == "maj" else MINOR_NAMES[root]
    cam = CAMELOT_MAJOR[name] if mode == "maj" else CAMELOT_MINOR[name]
    conf = float(np.clip((best - second) * 4 + max(0.0, best) * 0.5, 0, 1))
    return name, cam, conf


def format_key(musical, camelot, notation="camelot"):
    if notation == "musical":
        return musical
    if notation == "both":
        return f"{camelot} {musical}"
    return camelot


def to_camelot(key):
    """Wandelt beliebige Tonart-Schreibweisen (Am, A minor, 8A, 08A …) in Camelot um."""
    if not key:
        return ""
    k = key.strip().replace("♯", "#").replace("♭", "b")
    m = __import__("re").match(r"^0?(\d{1,2})\s*([ABab])\b", k)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1))}{m.group(2).upper()}"
    k = k.replace(" minor", "m").replace(" min", "m").replace(" major", "").replace(" maj", "").replace(" ", "")
    if k.endswith("m") and len(k) >= 2:
        name = k[0].upper() + k[1:-1] + "m"
        name = _ALIASES.get(name, name)
        return CAMELOT_MINOR.get(name, "")
    name = k[0].upper() + k[1:]
    name = _ALIASES.get(name, name)
    return CAMELOT_MAJOR.get(name, "")


def camelot_sort_key(key):
    """Sortierung entlang des Camelot-Rads (1A, 1B, 2A, …); Unbekanntes ans Ende."""
    c = to_camelot(key)
    if not c:
        return (99, 9, key or "")
    return (int(c[:-1]), 0 if c[-1] == "A" else 1, "")


def compatible(key):
    """Harmonisch passende Camelot-Tonarten (gleich, ±1, Dur/Moll-Wechsel)."""
    c = to_camelot(key)
    if not c:
        return set()
    n, l = int(c[:-1]), c[-1]
    other = "B" if l == "A" else "A"
    return {f"{n}{l}", f"{(n % 12) + 1}{l}", f"{((n - 2) % 12) + 1}{l}", f"{n}{other}"}


def analyze_file(ffmpeg, path, duration=0.0):
    from .encoder import decode_mono
    length = 120.0
    start = 0.0
    if duration and duration > length + 30:
        start = max(0.0, duration * 0.4 - length / 2)
    y = decode_mono(ffmpeg, path, SR, start, length)
    return estimate_key(y, SR)
