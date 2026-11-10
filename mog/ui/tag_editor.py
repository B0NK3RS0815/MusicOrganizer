"""Tag-Editor für einen oder mehrere Titel (Stapelbearbeitung)."""
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from mog.core import tags as tagio
from mog.core.track import TAG_FIELDS, TAG_LABELS

from .dialogs import primary
from .icons import icon, placeholder_cover

MIXED = "‹verschiedene Werte›"

# Gängige Camelot-/Musik-Tonarten als Vorschläge
KEYS = ["", "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7A", "7B",
        "8A", "8B", "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B",
        "Am", "C", "Em", "G", "Bm", "D", "F#m", "A", "C#m", "E", "G#m", "B",
        "Ebm", "F#", "Bbm", "Db", "Fm", "Ab", "Cm", "Eb", "Gm", "Bb", "Dm", "F"]
GENRES = ["", "House", "Deep House", "Tech House", "Techno", "Melodic Techno", "Progressive House",
          "Trance", "Drum & Bass", "Dubstep", "Hip-Hop", "R&B", "Pop", "Dance", "Electro",
          "Afro House", "Disco", "Nu Disco", "Funk", "Soul", "Reggaeton", "Latin", "Schlager",
          "Rock", "Indie Dance", "Minimal", "Hardstyle", "Garage", "Breaks", "Ambient", "Downtempo"]


class TagEditor(QDialog):
    """Bearbeitet Tags. Änderungen werden nicht sofort geschrieben, sondern vorgemerkt:
    nach dem Schließen steht in ``self.changes`` eine Liste (track, werte, cover, cover_gesetzt).
    """

    def __init__(self, tracks, cover_getter=None, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.multi = len(tracks) > 1
        self.setWindowTitle(f"Tags bearbeiten – {len(tracks)} Titel" if self.multi else "Tags bearbeiten")
        self.resize(760, 560)
        self.changes = []
        self.cover_changed = False
        self.new_cover = None
        cover_getter = cover_getter or (lambda t: tagio.read_cover(t.path))

        # Werte aus der Bibliothek (enthält bereits vorgemerkte, noch nicht gespeicherte Änderungen)
        self.values = {f: set() for f in TAG_FIELDS}
        self.read_errors = []
        for t in tracks:
            d = t.tag_dict()
            for f in TAG_FIELDS:
                self.values[f].add(d.get(f, "") or "")
        first_cover = None
        cover_differs = False
        for i, t in enumerate(tracks[:50]):
            cov = cover_getter(t)
            if i == 0:
                first_cover = cov
            elif (cov or (None,))[0] != (first_cover or (None,))[0]:
                cover_differs = True
        self.orig_cover = first_cover

        lay = QHBoxLayout(self)
        # linke Spalte: Cover
        left = QVBoxLayout()
        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(220, 220)
        self.cover_lbl.setScaledContents(True)
        left.addWidget(self.cover_lbl)
        self.cover_info = QLabel("")
        self.cover_info.setObjectName("Hint")
        self.cover_info.setAlignment(Qt.AlignCenter)
        left.addWidget(self.cover_info)
        b_load = QPushButton(icon("image"), " Cover laden …")
        b_load.clicked.connect(self._load_cover)
        b_del = QPushButton(icon("x"), " Cover entfernen")
        b_del.clicked.connect(self._remove_cover)
        left.addWidget(b_load)
        left.addWidget(b_del)
        left.addStretch()
        if not self.multi:
            fn = QLabel(os.path.basename(tracks[0].path))
            fn.setObjectName("Hint")
            fn.setWordWrap(True)
            fn.setFixedWidth(220)
            fn.setToolTip(tracks[0].path)
            left.addWidget(fn)
        lay.addLayout(left)
        self._show_cover(first_cover, mixed=cover_differs)

        # rechte Spalte: Felder
        right = QVBoxLayout()
        if self.multi:
            h = QLabel("Nur geänderte Felder werden in alle markierten Dateien geschrieben. "
                       f"Felder mit „{MIXED}“ bleiben unverändert, solange du sie nicht bearbeitest.")
            h.setObjectName("Hint")
            h.setWordWrap(True)
            right.addWidget(h)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.edits = {}
        layout_spec = [("artist", 0, 0, 3), ("title", 1, 0, 3), ("album", 2, 0, 3),
                       ("albumartist", 3, 0, 3), ("genre", 4, 0, 1), ("label", 4, 2, 1),
                       ("year", 5, 0, 1), ("track", 5, 2, 1), ("bpm", 6, 0, 1), ("key", 6, 2, 1)]
        for f, r, c, span in layout_spec:
            lbl = QLabel(TAG_LABELS[f] + ":")
            lbl.setObjectName("Muted")
            if f in ("genre", "key"):
                w = QComboBox()
                w.setEditable(True)
                w.addItems(GENRES if f == "genre" else KEYS)
                w.setInsertPolicy(QComboBox.NoInsert)
                edit = w.lineEdit()
            else:
                w = edit = QLineEdit()
            self._prefill(edit, f)
            grid.addWidget(lbl, r, c)
            grid.addWidget(w, r, c + 1, 1, span if c == 0 and span > 1 else 1)
            self.edits[f] = edit
        right.addLayout(grid)
        cl = QLabel("Kommentar:")
        cl.setObjectName("Muted")
        right.addWidget(cl)
        self.comment = QPlainTextEdit()
        self.comment.setMaximumHeight(80)
        vals = self.values["comment"]
        if len(vals) > 1:
            self.comment.setPlaceholderText(MIXED)
        elif vals:
            self.comment.setPlainText(next(iter(vals)))
        self.comment_orig = self.comment.toPlainText()
        right.addWidget(self.comment)

        tools = QHBoxLayout()
        b_fn = QPushButton(icon("file"), " Aus Dateiname")
        b_fn.setToolTip("Artist und Titel aus dem Dateinamen übernehmen (Muster: Artist - Titel)")
        b_fn.clicked.connect(self._from_filename)
        b_swap = QPushButton(icon("swap"), " Artist ↔ Titel")
        b_swap.clicked.connect(self._swap)
        tools.addWidget(b_fn)
        tools.addWidget(b_swap)
        tools.addStretch()
        right.addLayout(tools)
        right.addStretch()
        if self.read_errors:
            w = QLabel(f"{len(self.read_errors)} Datei(en) konnten nicht gelesen werden.")
            w.setObjectName("Warning")
            right.addWidget(w)

        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        ok = primary(QPushButton("Speichern"))
        bb.addButton(ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right, 1)

    def _prefill(self, edit, f):
        vals = self.values[f]
        if len(vals) > 1:
            edit.setText("")
            edit.setPlaceholderText(MIXED)
        else:
            edit.setText(next(iter(vals)) if vals else "")
        edit.setProperty("orig", edit.text())

    def _show_cover(self, cover, mixed=False):
        if cover:
            pm = QPixmap()
            pm.loadFromData(cover[0])
            if not pm.isNull():
                self.cover_lbl.setPixmap(pm)
                self.cover_info.setText(f"{pm.width()}×{pm.height()} px · {len(cover[0]) // 1024} KB")
                return
        self.cover_lbl.setPixmap(placeholder_cover(220))
        self.cover_info.setText(MIXED if mixed else "Kein Cover")

    def _load_cover(self):
        p, _ = QFileDialog.getOpenFileName(self, "Cover wählen", "",
                                           "Bilder (*.jpg *.jpeg *.png);;Alle Dateien (*)")
        if not p:
            return
        with open(p, "rb") as fh:
            data = fh.read()
        self.new_cover = (data, tagio.guess_mime(data))
        self.cover_changed = True
        self._show_cover(self.new_cover)

    def set_cover(self, cover):
        self.new_cover = cover
        self.cover_changed = True
        self._show_cover(cover)

    def _remove_cover(self):
        self.new_cover = None
        self.cover_changed = True
        self._show_cover(None)

    def _from_filename(self):
        if self.multi:
            self.edits["artist"].setText("")
            self.edits["artist"].setPlaceholderText("wird pro Datei aus dem Dateinamen gesetzt")
            self.edits["title"].setText("")
            self.edits["title"].setPlaceholderText("wird pro Datei aus dem Dateinamen gesetzt")
            self._per_file_from_name = True
            return
        a, t = tagio.parse_filename(self.tracks[0].path)
        self.edits["artist"].setText(a)
        self.edits["title"].setText(t)

    def _swap(self):
        a, t = self.edits["artist"].text(), self.edits["title"].text()
        self.edits["artist"].setText(t)
        self.edits["title"].setText(a)

    def changed_values(self):
        out = {}
        for f, e in self.edits.items():
            if e.text() != (e.property("orig") or ""):
                out[f] = e.text()
        if self.comment.toPlainText() != self.comment_orig:
            out["comment"] = self.comment.toPlainText()
        return out

    def _save(self):
        changes = self.changed_values()
        per_file = getattr(self, "_per_file_from_name", False)
        if not changes and not self.cover_changed and not per_file:
            self.reject()
            return
        for t in self.tracks:
            vals = dict(changes)
            if per_file:
                a, ti = tagio.parse_filename(t.path)
                if not vals.get("artist"):
                    vals["artist"] = a
                if not vals.get("title"):
                    vals["title"] = ti
            self.changes.append((t, vals, self.new_cover, self.cover_changed))
        self.accept()
