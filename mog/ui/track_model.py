"""Tabellenmodell für die Titelliste.

Filtern und Sortieren erledigt das Modell selbst in Python-Listen (statt über
QSortFilterProxyModel). Das ist bei großen Archiven (350.000+ Titel) um ein Vielfaches
schneller, weil Qt sonst für jeden Vergleich zurück in Python springen müsste.
"""
import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from mog.core.track import format_bpm, format_duration, format_size

from .icons import format_badge
from .theme import C

TrackRole = Qt.UserRole + 1

# key, Überschrift, standardmäßig sichtbar, Breite, Ausrichtung
COLUMNS = [
    ("artist", "Artist", True, 240, Qt.AlignLeft),
    ("title", "Titel", True, 360, Qt.AlignLeft),
    ("bpm", "BPM", True, 64, Qt.AlignRight),
    ("duration", "Länge", True, 70, Qt.AlignRight),
    ("bitrate", "Qualität (kbps)", True, 112, Qt.AlignRight),
    ("fmt", "Format", True, 78, Qt.AlignCenter),
    ("key", "Tonart", False, 64, Qt.AlignCenter),
    ("album", "Album", False, 200, Qt.AlignLeft),
    ("genre", "Genre", False, 120, Qt.AlignLeft),
    ("year", "Jahr", False, 56, Qt.AlignCenter),
    ("label", "Label", False, 140, Qt.AlignLeft),
    ("samplerate", "Samplerate", False, 90, Qt.AlignRight),
    ("size", "Größe", False, 80, Qt.AlignRight),
    ("filename", "Dateiname", False, 260, Qt.AlignLeft),
    ("path", "Pfad", False, 380, Qt.AlignLeft),
]
COL_INDEX = {c[0]: i for i, c in enumerate(COLUMNS)}


def _low(s):
    return (s or "").lower()


# Sortierschlüssel je Spalte (leere Werte kommen beim Aufsteigen ans Ende)
SORT_KEYS = {
    "artist": lambda t: (not t.artist, _low(t.artist), _low(t.display_title)),
    "title": lambda t: (_low(t.display_title), _low(t.artist)),
    "bpm": lambda t: (t.bpm is None, t.bpm or 0.0),
    "duration": lambda t: t.duration or 0.0,
    "bitrate": lambda t: t.bitrate or 0,
    "fmt": lambda t: (t.fmt or "", -(t.bitrate or 0)),
    "key": lambda t: (not t.key, _low(t.key)),
    "album": lambda t: (not t.album, _low(t.album)),
    "genre": lambda t: (not t.genre, _low(t.genre)),
    "year": lambda t: (not t.year, t.year or ""),
    "label": lambda t: (not t.label, _low(t.label)),
    "samplerate": lambda t: t.samplerate or 0,
    "size": lambda t: t.size or 0,
    "filename": lambda t: _low(t.filename),
    "path": lambda t: _low(t.path),
}

VIEWS = {
    "all": None,
    "lossless": lambda t: t.lossless,
    "lowq": lambda t: (not t.lossless) and 0 < (t.bitrate or 0) < 192_000,
    "nobpm": lambda t: not t.bpm,
    "notags": lambda t: t.tags_missing or not t.artist or not t.title,
    "missing": lambda t: t.missing,
    "pending": None,   # wird über die Pending-Liste des Modells gefiltert
}


def quality_color(t):
    if t.lossless:
        return QColor(C["ok"])
    kbps = (t.bitrate or 0) / 1000
    if kbps and kbps < 160:
        return QColor(C["bad"])
    if kbps and kbps < 250:
        return QColor(C["warn"])
    return None


class TrackModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all = []            # alle Titel der Bibliothek
        self.by_id = {}
        self.view = []           # gefilterte + sortierte Anzeige
        self.view_row = {}
        self.pending = {}        # track_id -> {geänderte Felder}
        self.playing_id = None
        self._search_cache = {}
        self._words = []
        self._view_key = "all"
        self._root = None
        self._sort_col = COL_INDEX["artist"]
        self._sort_order = Qt.AscendingOrder
        self._italic = QFont()
        self._italic.setItalic(True)
        self._bold = QFont()
        self._bold.setBold(True)
        self._pending_col = QColor(C["accent2"])

    # --- Daten -------------------------------------------------------------
    @property
    def tracks(self):
        return self.all

    def set_tracks(self, tracks):
        self.all = list(tracks)
        self.by_id = {t.id: t for t in self.all}
        self._search_cache.clear()
        self.rebuild()

    def set_pending(self, pending):
        self.pending = pending
        if self._view_key == "pending":
            self.rebuild()
        elif self.view:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.view) - 1, len(COLUMNS) - 1))

    def upsert(self, tracks, live=False):
        """Aktualisiert/ergänzt Titel. live=True: neue Titel sofort unten anhängen (beim Einlesen).

        Vorhandene Titel werden an Ort und Stelle aktualisiert, damit alle Verweise gültig bleiben.
        """
        new = []
        for t in tracks:
            old = self.by_id.get(t.id)
            self._search_cache.pop(t.id, None)
            if old is None:
                self.all.append(t)
                self.by_id[t.id] = t
                new.append(t)
            else:
                if old is not t:
                    for slot in t.__slots__:
                        setattr(old, slot, getattr(t, slot))
                r = self.view_row.get(t.id)
                if r is not None:
                    self.dataChanged.emit(self.index(r, 0), self.index(r, len(COLUMNS) - 1))
        if new and live:
            add = [t for t in new if self._accept(t)]
            if add:
                start = len(self.view)
                self.beginInsertRows(QModelIndex(), start, start + len(add) - 1)
                for t in add:
                    self.view_row[t.id] = len(self.view)
                    self.view.append(t)
                self.endInsertRows()
        elif new:
            self.rebuild()

    def remove_ids(self, ids):
        ids = set(ids)
        if not ids:
            return
        self.all = [t for t in self.all if t.id not in ids]
        for i in ids:
            self.by_id.pop(i, None)
            self._search_cache.pop(i, None)
        self.rebuild()

    def track_by_id(self, tid):
        return self.by_id.get(tid)

    def track_at(self, row):
        return self.view[row] if 0 <= row < len(self.view) else None

    def row_for_id(self, tid):
        return self.view_row.get(tid)

    def tracks_in_order(self):
        return list(self.view)

    def set_playing(self, tid):
        old = self.view_row.get(self.playing_id)
        self.playing_id = tid
        for r in (old, self.view_row.get(tid)):
            if r is not None:
                self.dataChanged.emit(self.index(r, 0), self.index(r, len(COLUMNS) - 1))

    # --- Filter & Sortierung ------------------------------------------------
    def search_text(self, t):
        s = self._search_cache.get(t.id)
        if s is None:
            s = " ".join((t.artist, t.title, t.album, t.genre, t.label, t.key,
                          t.fmt or "", t.path)).lower()
            self._search_cache[t.id] = s
        return s

    def set_search(self, text):
        words = [w for w in text.lower().split() if w]
        if words != self._words:
            self._words = words
            self.rebuild()

    def set_view(self, view, root=None):
        self._view_key = view
        self._root = (root.rstrip("/\\") + os.sep) if root else None
        self.rebuild()

    def _accept(self, t):
        if self._root and not t.path.startswith(self._root):
            return False
        if self._view_key == "pending":
            if t.id not in self.pending:
                return False
        else:
            f = VIEWS.get(self._view_key)
            if f is not None and not f(t):
                return False
        if self._words:
            s = self.search_text(t)
            return all(w in s for w in self._words)
        return True

    def rebuild(self):
        self.beginResetModel()
        if not self._words and not self._root and self._view_key == "all":
            view = list(self.all)
        else:
            view = [t for t in self.all if self._accept(t)]
        self._sort_list(view)
        self.view = view
        self.view_row = {t.id: i for i, t in enumerate(view)}
        self.endResetModel()

    def _sort_list(self, lst):
        key = SORT_KEYS[COLUMNS[self._sort_col][0]]
        lst.sort(key=key, reverse=(self._sort_order == Qt.DescendingOrder))

    def sort(self, column, order=Qt.AscendingOrder):
        if column < 0 or column >= len(COLUMNS):
            return
        self._sort_col, self._sort_order = column, order
        self.layoutAboutToBeChanged.emit()
        old_persistent = self.persistentIndexList()
        old_ids = [(self.view[i.row()].id, i.column()) if i.row() < len(self.view) else (None, 0)
                   for i in old_persistent]
        self._sort_list(self.view)
        self.view_row = {t.id: i for i, t in enumerate(self.view)}
        new_persistent = []
        for tid, col in old_ids:
            r = self.view_row.get(tid)
            new_persistent.append(self.index(r, col) if r is not None else QModelIndex())
        self.changePersistentIndexList(old_persistent, new_persistent)
        self.layoutChanged.emit()

    def sort_state(self):
        return self._sort_col, self._sort_order

    def stats(self):
        """(Anzahl, Gesamtdauer, Gesamtgröße) der aktuellen Ansicht."""
        v = self.view
        return len(v), sum(t.duration or 0 for t in v), sum(t.size or 0 for t in v)

    def counts(self, roots):
        """Zähler für die Seitenleiste in einem Durchlauf."""
        prefixes = [(r, r.rstrip("/\\") + os.sep) for r in roots]
        c = {k: 0 for k in VIEWS if VIEWS[k]}
        per_root = {r: 0 for r in roots}
        for t in self.all:
            if t.lossless:
                c["lossless"] += 1
            elif 0 < (t.bitrate or 0) < 192_000:
                c["lowq"] += 1
            if not t.bpm:
                c["nobpm"] += 1
            if t.tags_missing or not t.artist or not t.title:
                c["notags"] += 1
            if t.missing:
                c["missing"] += 1
            for r, p in prefixes:
                if t.path.startswith(p):
                    per_root[r] += 1
                    break
        c["pending"] = len(self.pending)
        return c, per_root

    # --- Qt-Schnittstelle --------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.view)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return COLUMNS[section][1]
            if role == Qt.TextAlignmentRole:
                return int(COLUMNS[section][4] | Qt.AlignVCenter)
            if role == Qt.ToolTipRole:
                return ("Klick: sortieren · Rand ziehen: Breite ändern · "
                        "Spalte ziehen: Reihenfolge ändern · Rechtsklick: Spalten ein-/ausblenden")
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t = self.view[index.row()]
        key = COLUMNS[index.column()][0]
        if role == Qt.DisplayRole:
            if key == "artist":
                return t.artist or ""
            if key == "title":
                return t.display_title
            if key == "bpm":
                return format_bpm(t.bpm)
            if key == "duration":
                return format_duration(t.duration)
            if key == "bitrate":
                return str(round((t.bitrate or 0) / 1000)) if t.bitrate else ""
            if key == "fmt":
                return ""  # Badge wird vom Delegate gezeichnet
            if key == "samplerate":
                return f"{t.samplerate / 1000:g} kHz" if t.samplerate else ""
            if key == "size":
                return format_size(t.size)
            if key == "filename":
                return t.filename
            return getattr(t, key, "") or ""
        if role == TrackRole:
            return t
        if role == Qt.TextAlignmentRole:
            return int(COLUMNS[index.column()][4] | Qt.AlignVCenter)
        pend = self.pending.get(t.id)
        if role == Qt.ForegroundRole:
            if pend and key in pend:
                return self._pending_col
            if t.missing:
                return QColor(C["text3"])
            if key == "bitrate":
                return quality_color(t)
            if key in ("bpm", "duration", "key", "year", "samplerate", "size"):
                return QColor(C["text2"])
            if key == "artist" and t.tags_missing:
                return QColor(C["text2"])
            if t.id == self.playing_id and key in ("artist", "title"):
                return QColor(C["accent"])
        if role == Qt.FontRole:
            if t.id == self.playing_id and key in ("artist", "title"):
                return self._bold
            if t.tags_missing and key in ("artist", "title") and not (pend and key in pend):
                return self._italic
        if role == Qt.ToolTipRole:
            if pend and key in pend:
                return "Geändert – wird beim Speichern bzw. beim Beenden in die Datei geschrieben"
            if t.missing:
                return f"Datei nicht erreichbar:\n{t.path}"
            if key == "fmt":
                tip = t.format.name
                if t.samplerate:
                    tip += f" · {t.samplerate / 1000:g} kHz"
                if t.bits:
                    tip += f" · {t.bits} Bit"
                if t.lossless:
                    tip += " · verlustfrei"
                return tip
            if key == "bitrate":
                if t.lossless:
                    return "Verlustfreies Format"
                kbps = (t.bitrate or 0) / 1000
                if kbps and kbps < 160:
                    return "Niedrige Qualität – für Clubanlagen nicht empfehlenswert"
                if kbps and kbps < 250:
                    return "Mittlere Qualität"
            if key in ("artist", "title") and t.tags_missing:
                return "Keine Tags – Werte aus dem Dateinamen abgeleitet"
            if key in ("path", "filename", "title"):
                return t.path
        return None


class FormatBadgeDelegate(QStyledItemDelegate):
    """Zeichnet das Format-Badge mittig in die Zelle."""

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        option.text = ""
        if style:
            style.drawControl(QStyle.CE_ItemViewItem, option, painter, option.widget)
        t = index.data(TrackRole)
        if t is None:
            return
        pm = format_badge(t.fmt or "?", 18)
        w = pm.width() / pm.devicePixelRatio()
        h = pm.height() / pm.devicePixelRatio()
        r = option.rect
        x = r.x() + (r.width() - w) / 2
        y = r.y() + (r.height() - h) / 2
        if t.missing:
            painter.setOpacity(0.35)
        painter.drawPixmap(int(x), int(y), pm)
        painter.setOpacity(1.0)

    def sizeHint(self, option, index):
        return QSize(60, 26)
