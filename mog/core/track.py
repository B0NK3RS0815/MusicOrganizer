"""Datenobjekt für einen Titel der Bibliothek."""
import os

from .formats import get_format

TAG_FIELDS = ["artist", "title", "album", "albumartist", "genre", "year",
              "track", "bpm", "key", "label", "comment"]

TAG_LABELS = {
    "artist": "Artist", "title": "Titel", "album": "Album", "albumartist": "Album-Artist",
    "genre": "Genre", "year": "Jahr", "track": "Track-Nr.", "bpm": "BPM", "key": "Tonart",
    "label": "Label", "comment": "Kommentar",
}

DB_COLUMNS = ["id", "path", "size", "mtime", "fmt", "artist", "title", "album", "albumartist",
              "genre", "year", "track", "bpm", "key", "label", "comment", "duration", "bitrate",
              "samplerate", "bits", "channels", "lossless", "has_cover", "tags_missing",
              "audio_hash", "missing", "error"]


class Track:
    __slots__ = DB_COLUMNS

    def __init__(self, **kw):
        for c in DB_COLUMNS:
            setattr(self, c, kw.get(c))
        for c in ("artist", "title", "album", "albumartist", "genre", "year", "track",
                  "key", "label", "comment"):
            if getattr(self, c) is None:
                setattr(self, c, "")
        for c in ("size", "bitrate", "samplerate", "bits", "channels"):
            if getattr(self, c) is None:
                setattr(self, c, 0)
        for c in ("lossless", "has_cover", "tags_missing", "missing"):
            setattr(self, c, bool(getattr(self, c)))
        if self.duration is None:
            self.duration = 0.0
        if self.bpm in ("", None):
            self.bpm = None

    # --- Hilfen ----------------------------------------------------------
    @property
    def format(self):
        return get_format(self.fmt)

    @property
    def filename(self):
        return os.path.basename(self.path)

    @property
    def folder(self):
        return os.path.dirname(self.path)

    @property
    def display_artist(self):
        return self.artist or ""

    @property
    def display_title(self):
        return self.title or os.path.splitext(self.filename)[0]

    def as_row(self):
        return tuple(getattr(self, c) for c in DB_COLUMNS)

    @classmethod
    def from_row(cls, row):
        """Schnelles Erzeugen aus einer Datenbankzeile (wichtig bei 100.000+ Titeln)."""
        t = cls.__new__(cls)
        _assign(t, row)
        return t

    def copy(self):
        return Track.from_row(self.as_row())

    def tag_dict(self):
        d = {f: getattr(self, f) for f in TAG_FIELDS}
        d["bpm"] = format_bpm(self.bpm)
        return d

    def __repr__(self):
        return f"<Track {self.id} {self.artist!r} – {self.title!r}>"


def format_bpm(bpm):
    if bpm in (None, "", 0):
        return ""
    try:
        b = float(bpm)
    except (TypeError, ValueError):
        return str(bpm)
    return str(int(round(b))) if abs(b - round(b)) < 0.05 else f"{b:.1f}"


def parse_bpm(value):
    if value in (None, ""):
        return None
    try:
        b = float(str(value).replace(",", ".").strip())
    except ValueError:
        return None
    return b if 0 < b < 1000 else None


def format_duration(seconds):
    if not seconds:
        return ""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


# Zuweisung aller Spalten in einer generierten Funktion – deutlich schneller als setattr-Schleifen.
# Leere Datenbankwerte werden dabei in passende Standardwerte umgewandelt.
_STR = {"path", "fmt", "artist", "title", "album", "albumartist", "genre", "year", "track",
        "key", "label", "comment", "error"}
_INT = {"size", "bitrate", "samplerate", "bits", "channels"}
_BOOL = {"lossless", "has_cover", "tags_missing", "missing"}


def _make_assign():
    lines = ["def _assign(t, r):"]
    for i, c in enumerate(DB_COLUMNS):
        if c in _STR:
            lines.append(f"    t.{c} = r[{i}] or ''")
        elif c in _INT:
            lines.append(f"    t.{c} = r[{i}] or 0")
        elif c in _BOOL:
            lines.append(f"    t.{c} = bool(r[{i}])")
        elif c == "duration":
            lines.append(f"    t.{c} = r[{i}] or 0.0")
        elif c == "bpm":
            lines.append(f"    t.{c} = r[{i}] or None")
        else:
            lines.append(f"    t.{c} = r[{i}]")
    ns = {}
    exec("\n".join(lines), ns)
    return ns["_assign"]


_assign = _make_assign()
