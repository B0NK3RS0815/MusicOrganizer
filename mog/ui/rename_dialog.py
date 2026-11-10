"""Dateinamen bearbeiten – einzeln von Hand oder für viele Dateien nach einem Muster."""
import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from mog.core.fileops import sanitize_filename
from mog.core.track import format_bpm

from .dialogs import primary
from .icons import icon
from .theme import C

PATTERNS = [
    "%artist% - %title%",
    "%track% - %artist% - %title%",
    "%artist% - %title% (%bpm% BPM)",
    "%bpm% - %key% - %artist% - %title%",
    "%artist% - %album% - %track% - %title%",
]
TOKENS = ["%artist%", "%title%", "%album%", "%albumartist%", "%genre%", "%year%", "%track%",
          "%bpm%", "%key%", "%label%", "%filename%"]

COL_OLD, COL_NEW, COL_EXT, COL_STATE = range(4)


def apply_pattern(pattern, t):
    def val(name):
        if name == "bpm":
            return format_bpm(t.bpm)
        if name == "track":
            n = (t.track or "").split("/")[0].strip()
            return n.zfill(2) if n.isdigit() else n
        if name == "filename":
            return os.path.splitext(t.filename)[0]
        if name == "title":
            return t.display_title
        return getattr(t, name, "") or ""
    out = re.sub(r"%(\w+)%", lambda m: val(m.group(1).lower()), pattern)
    # Reste leerer Platzhalter aufräumen, z. B. "Artist -  - Titel" oder "()"
    out = re.sub(r"\(\s*(BPM)?\s*\)", "", out)
    out = re.sub(r"(\s*-\s*){2,}", " - ", out)
    out = re.sub(r"^\s*-\s*|\s*-\s*$", "", out)
    return sanitize_filename(out)


class RenameDialog(QDialog):
    """Nach dem Schließen enthält ``self.renames`` die Liste (track, neuer_dateistamm)."""

    def __init__(self, tracks, settings, parent=None):
        super().__init__(parent)
        self.tracks = [t for t in tracks if not t.missing]
        self.s = settings
        self.renames = []
        n = len(self.tracks)
        self.setWindowTitle("Dateinamen bearbeiten")
        self.resize(1000, 560 if n > 1 else 300)

        lay = QVBoxLayout(self)
        t = QLabel(f"{n} Dateiname{'n' if n != 1 else ''} bearbeiten")
        t.setObjectName("BigTitle")
        lay.addWidget(t)
        h = QLabel("Den neuen Namen direkt in der Spalte „Neuer Name“ bearbeiten (Doppelklick) – oder "
                   "ein Muster aus den Tags anwenden. Die Dateiendung bleibt immer erhalten; "
                   "Zeichen, die Windows oder macOS nicht erlauben, werden automatisch ersetzt.")
        h.setObjectName("Hint")
        h.setWordWrap(True)
        lay.addWidget(h)

        row = QHBoxLayout()
        row.addWidget(QLabel("Muster:"))
        self.cmb = QComboBox()
        self.cmb.setEditable(True)
        self.cmb.addItems(PATTERNS)
        last = self.s.value("rename/pattern", PATTERNS[0])
        self.cmb.setCurrentText(last)
        self.cmb.setToolTip("Platzhalter: " + "  ".join(TOKENS))
        row.addWidget(self.cmb, 1)
        b_apply = QPushButton(icon("tag"), " Muster anwenden")
        b_apply.clicked.connect(self.apply_pattern)
        row.addWidget(b_apply)
        b_reset = QPushButton(icon("refresh"), " Zurücksetzen")
        b_reset.clicked.connect(self._fill)
        row.addWidget(b_reset)
        lay.addLayout(row)
        tok = QLabel("Platzhalter: " + "  ".join(TOKENS))
        tok.setObjectName("Hint")
        tok.setWordWrap(True)
        lay.addWidget(tok)

        self.table = QTableWidget(n, 4)
        self.table.setHorizontalHeaderLabels(["Aktueller Name", "Neuer Name", "Endung", "Status"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                                   QAbstractItemView.AnyKeyPressed)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_OLD, QHeaderView.Interactive)
        hh.setSectionResizeMode(COL_NEW, QHeaderView.Stretch)
        self.table.setColumnWidth(COL_OLD, 380)
        self.table.setColumnWidth(COL_EXT, 76)
        self.table.setColumnWidth(COL_STATE, 170)
        lay.addWidget(self.table, 1)
        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        lay.addWidget(self.summary)

        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.ok = primary(QPushButton(icon("check", "#FFFFFF"), "  Umbenennen"))
        bb.addButton(self.ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._fill()
        self.table.itemChanged.connect(lambda *_: self._validate())
        if n == 1:
            self.table.setCurrentCell(0, COL_NEW)
            self.table.editItem(self.table.item(0, COL_NEW))

    def _fill(self):
        self.table.blockSignals(True)
        for r, t in enumerate(self.tracks):
            stem, ext = os.path.splitext(t.filename)
            old = QTableWidgetItem(stem)
            old.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            old.setToolTip(t.path)
            old.setForeground(QBrush(QColor(C["text2"])))
            new = QTableWidgetItem(stem)
            e = QTableWidgetItem(ext)
            e.setFlags(Qt.ItemIsEnabled)
            e.setForeground(QBrush(QColor(C["text3"])))
            st = QTableWidgetItem("")
            st.setFlags(Qt.ItemIsEnabled)
            for c, it in ((COL_OLD, old), (COL_NEW, new), (COL_EXT, e), (COL_STATE, st)):
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        self._validate()

    def apply_pattern(self):
        pattern = self.cmb.currentText().strip()
        if not pattern:
            return
        self.s.set("rename/pattern", pattern)
        rows = sorted({i.row() for i in self.table.selectedIndexes()}) or range(len(self.tracks))
        if len(rows) == 1 and len(self.tracks) > 1:
            rows = range(len(self.tracks))   # einzelne Markierung: auf alle anwenden
        self.table.blockSignals(True)
        for r in rows:
            name = apply_pattern(pattern, self.tracks[r])
            if name:
                self.table.item(r, COL_NEW).setText(name)
        self.table.blockSignals(False)
        self._validate()

    def _validate(self):
        """Prüft alle neuen Namen auf Gültigkeit und Kollisionen."""
        targets = {}
        changed = bad = 0
        for r, t in enumerate(self.tracks):
            folder = t.folder
            ext = os.path.splitext(t.filename)[1]
            raw = self.table.item(r, COL_NEW).text()
            clean = sanitize_filename(raw)
            key = os.path.normcase(os.path.join(folder, clean + ext))
            targets.setdefault(key, []).append(r)
        self.table.blockSignals(True)
        for r, t in enumerate(self.tracks):
            ext = os.path.splitext(t.filename)[1]
            raw = self.table.item(r, COL_NEW).text()
            clean = sanitize_filename(raw)
            dst = os.path.join(t.folder, clean + ext)
            st = self.table.item(r, COL_STATE)
            color = C["text3"]
            if not clean:
                text, color = "✗ leerer Name", C["bad"]
                bad += 1
            elif clean + ext == t.filename:
                text = "unverändert"
            elif len(targets[os.path.normcase(dst)]) > 1:
                text, color = "✗ Name doppelt vergeben", C["bad"]
                bad += 1
            elif os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(t.path):
                text, color = "✗ existiert bereits", C["bad"]
                bad += 1
            else:
                text, color = "✓ wird umbenannt", C["ok"]
                if clean != raw.strip():
                    text = "✓ (Zeichen ersetzt)"
                    color = C["warn"]
                changed += 1
            st.setText(text)
            st.setForeground(QBrush(QColor(color)))
            st.setToolTip(clean + ext)
        self.table.blockSignals(False)
        self.summary.setText((f"{changed} Datei wird umbenannt" if changed == 1 else f"{changed} Dateien werden umbenannt") + (f" · {bad} mit Problemen (werden übersprungen)"
                                                              if bad else ""))
        self.ok.setEnabled(changed > 0)

    def _accept(self):
        self.renames = []
        for r, t in enumerate(self.tracks):
            if self.table.item(r, COL_STATE).text().startswith("✓"):
                self.renames.append((t, sanitize_filename(self.table.item(r, COL_NEW).text())))
        self.accept()
