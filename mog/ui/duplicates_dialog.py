"""Duplikate finden, prüfen, anhören und löschen."""
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDoubleSpinBox,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from mog.core import duplicates
from mog.core.fingerprint import find_fpcalc
from mog.core.library import Library
from mog.core.track import format_bpm, format_duration, format_size

from .dialogs import primary, run_task
from .icons import format_badge, icon
from .theme import C

REASON_LABEL = {"tags": "gleiche Tags", "identisch": "identische Datei",
                "fingerprint": "gleicher Klang"}


class DuplicatesDialog(QDialog):
    play_requested = Signal(object)
    delete_requested = Signal(list)       # Liste von Tracks

    def __init__(self, tracks, settings, db_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplikate finden")
        self.resize(1180, 720)
        self.tracks = tracks
        self.s = settings
        self.db_path = db_path
        self.groups = []
        self.fpcalc = find_fpcalc(self.s.get("tools/fpcalc") or None)

        lay = QVBoxLayout(self)
        title = QLabel("Duplikate finden")
        title.setObjectName("BigTitle")
        lay.addWidget(title)
        sub = QLabel(f"Durchsucht {len(tracks):,} Titel der aktuellen Ansicht.".replace(",", "."))
        sub.setObjectName("Hint")
        lay.addWidget(sub)

        opts = QHBoxLayout()
        self.cb_tags = QCheckBox("Gleiche Tags (Artist + Titel)")
        self.cb_tags.setChecked(self.s.get("dup/tags"))
        self.cb_ident = QCheckBox("Identische Dateien")
        self.cb_ident.setChecked(self.s.get("dup/identical"))
        self.cb_fp = QCheckBox("Audio-Fingerabdruck")
        self.cb_fp.setChecked(self.s.get("dup/fingerprint") and bool(self.fpcalc))
        self.cb_fp.setEnabled(bool(self.fpcalc))
        self.cb_fp.setToolTip("Findet auch falsch getaggte Kopien und andere Formate desselben Titels.\n"
                              "Beim ersten Mal langsam (ca. 0,3–1 s je Datei), Ergebnisse werden gespeichert."
                              if self.fpcalc else
                              "fpcalc (Chromaprint) nicht gefunden – siehe Einstellungen → Encoder.")
        for w in (self.cb_tags, self.cb_ident, self.cb_fp):
            opts.addWidget(w)
        opts.addSpacing(16)
        opts.addWidget(QLabel("Längen-Toleranz:"))
        self.sp_tol = QDoubleSpinBox()
        self.sp_tol.setRange(0, 30)
        self.sp_tol.setSuffix(" s")
        self.sp_tol.setValue(self.s.get("dup/tolerance"))
        self.sp_tol.setDecimals(1)
        self.sp_tol.setMinimumWidth(86)
        opts.addWidget(self.sp_tol)
        self.cb_mix = QCheckBox("Mix-Angaben ignorieren")
        self.cb_mix.setToolTip("Behandelt z. B. „(Extended Mix)“ und „(Radio Edit)“ als denselben Titel.")
        self.cb_mix.setChecked(self.s.get("dup/ignore_mix"))
        opts.addWidget(self.cb_mix)
        opts.addWidget(QLabel("Ähnlichkeit:"))
        self.sp_thr = QSpinBox()
        self.sp_thr.setRange(70, 99)
        self.sp_thr.setSuffix(" %")
        self.sp_thr.setValue(self.s.get("dup/threshold"))
        self.sp_thr.setMinimumWidth(80)
        self.sp_thr.setToolTip("Mindest-Ähnlichkeit beim Audio-Fingerabdruck")
        opts.addWidget(self.sp_thr)
        opts.addStretch()
        self.btn_search = primary(QPushButton(icon("search", "#FFFFFF"), "  Suchen"))
        self.btn_search.clicked.connect(self.search)
        opts.addWidget(self.btn_search)
        lay.addLayout(opts)

        self.tree = QTreeWidget()
        self.tree.setObjectName("DupTree")
        self.tree.setColumnCount(9)
        self.tree.setHeaderLabels(["Löschen", "Artist", "Titel", "BPM", "Länge", "kbps", "Format",
                                   "Größe", "Pfad"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setAlternatingRowColors(False)
        self.tree.setIconSize(QSize(46, 18))
        h = self.tree.header()
        for i, w in enumerate([86, 200, 260, 50, 60, 56, 66, 80, 300]):
            self.tree.setColumnWidth(i, w)
        h.setStretchLastSection(True)
        self.tree.itemDoubleClicked.connect(self._play_item)
        self.tree.itemChanged.connect(self._update_summary)
        lay.addWidget(self.tree, 1)

        self.summary = QLabel("Noch keine Suche durchgeführt.")
        self.summary.setObjectName("Muted")
        lay.addWidget(self.summary)

        row = QHBoxLayout()
        b_auto = QPushButton(icon("check"), " Automatisch markieren")
        b_auto.setToolTip("In jeder Gruppe die beste Datei behalten (verlustfrei > höhere Bitrate > "
                          "vollständige Tags) und alle anderen zum Löschen markieren.")
        b_auto.clicked.connect(self.auto_mark)
        b_none = QPushButton("Markierung aufheben")
        b_none.clicked.connect(lambda: self._mark_all(False))
        b_play = QPushButton(icon("play"), " Anhören")
        b_play.clicked.connect(lambda: self._play_item(self.tree.currentItem()))
        b_reveal = QPushButton(icon("folder"), " Im Ordner zeigen")
        b_reveal.clicked.connect(self._reveal)
        for b in (b_auto, b_none, b_play, b_reveal):
            row.addWidget(b)
        row.addStretch()
        self.btn_delete = QPushButton(icon("trash", "#FFB3BE"), "  Markierte löschen …")
        self.btn_delete.setObjectName("Danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete)
        b_close = QPushButton("Schließen")
        b_close.clicked.connect(self.accept)
        row.addWidget(self.btn_delete)
        row.addWidget(b_close)
        lay.addLayout(row)

    # --- Suche -------------------------------------------------------------
    def search(self):
        for k, v in (("dup/tags", self.cb_tags.isChecked()), ("dup/identical", self.cb_ident.isChecked()),
                     ("dup/fingerprint", self.cb_fp.isChecked()), ("dup/tolerance", self.sp_tol.value()),
                     ("dup/ignore_mix", self.cb_mix.isChecked()), ("dup/threshold", self.sp_thr.value())):
            self.s.set(k, v)
        if not (self.cb_tags.isChecked() or self.cb_ident.isChecked() or self.cb_fp.isChecked()):
            QMessageBox.information(self, "Duplikate", "Bitte mindestens eine Suchmethode wählen.")
            return
        opts = dict(use_tags=self.cb_tags.isChecked(), use_identical=self.cb_ident.isChecked(),
                    use_fingerprint=self.cb_fp.isChecked(), fpcalc=self.fpcalc,
                    duration_tol=self.sp_tol.value(), ignore_mix=self.cb_mix.isChecked(),
                    threshold=self.sp_thr.value() / 100.0)
        tracks = [t for t in self.tracks if not t.missing]
        db = self.db_path

        def job(progress, cancel, _item):
            lib = Library(db)
            try:
                return duplicates.run_search(tracks, lib=lib, progress=progress, cancel=cancel, **opts)
            finally:
                lib.close()

        groups = run_task(self, "Suche Duplikate …", job)
        if groups is None:
            return
        self.groups = groups
        self._fill()

    def _fill(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        for gi, g in enumerate(self.groups, 1):
            best = g.best
            reasons = " + ".join(REASON_LABEL.get(r, r) for r in g.reason.split(" + "))
            sim = f" · {g.similarity * 100:.0f} % ähnlich" if g.similarity and "fingerprint" in g.reason else ""
            head = QTreeWidgetItem([f"#{gi}", best.display_artist, best.display_title, "", "", "",
                                    "", "", f"{len(g.tracks)} Dateien · {reasons}{sim}"])
            head.setFirstColumnSpanned(False)
            for c in range(9):
                head.setFont(c, bold)
                head.setBackground(c, QBrush(QColor(C["panel2"])))
            head.setForeground(8, QBrush(QColor(C["text2"])))
            head.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(head)
            for t in g.tracks:
                it = QTreeWidgetItem(["", t.display_artist, t.display_title, format_bpm(t.bpm),
                                      format_duration(t.duration),
                                      str(round(t.bitrate / 1000)) if t.bitrate else "", "",
                                      format_size(t.size), t.path])
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Unchecked)
                it.setData(0, Qt.UserRole, t)
                it.setIcon(6, format_badge(t.fmt or "?", 18))
                it.setToolTip(8, t.path)
                if t is best:
                    it.setText(0, "★")
                    it.setToolTip(0, "Beste Qualität in dieser Gruppe – wird bei „Automatisch markieren“ behalten")
                    it.setForeground(0, QBrush(QColor(C["ok"])))
                head.addChild(it)
            head.setExpanded(True)
        self.tree.blockSignals(False)
        self._update_summary()
        if not self.groups:
            self.summary.setText("Keine Duplikate gefunden. 🎉")

    # --- Markieren ---------------------------------------------------------
    def _children(self):
        for i in range(self.tree.topLevelItemCount()):
            head = self.tree.topLevelItem(i)
            yield head, [head.child(j) for j in range(head.childCount())]

    def auto_mark(self):
        self.tree.blockSignals(True)
        for head, kids in self._children():
            for j, it in enumerate(kids):
                it.setCheckState(0, Qt.Unchecked if j == 0 else Qt.Checked)
        self.tree.blockSignals(False)
        self._update_summary()

    def _mark_all(self, state):
        self.tree.blockSignals(True)
        for head, kids in self._children():
            for it in kids:
                it.setCheckState(0, Qt.Checked if state else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._update_summary()

    def marked(self):
        out = []
        for head, kids in self._children():
            for it in kids:
                if it.checkState(0) == Qt.Checked:
                    out.append(it.data(0, Qt.UserRole))
        return out

    def _update_summary(self, *_):
        m = self.marked()
        n_files = sum(len(g.tracks) for g in self.groups)
        size = sum(t.size or 0 for t in m)
        self.summary.setText(f"{len(self.groups)} Gruppen · {n_files} Dateien · "
                             f"{len(m)} zum Löschen markiert ({format_size(size)} werden frei)")
        self.btn_delete.setEnabled(bool(m))

    # --- Aktionen ----------------------------------------------------------
    def _play_item(self, it, *_):
        if it is None:
            return
        t = it.data(0, Qt.UserRole)
        if t:
            self.play_requested.emit(t)

    def _reveal(self):
        it = self.tree.currentItem()
        t = it.data(0, Qt.UserRole) if it else None
        if t:
            from mog.core.fileops import reveal
            reveal(t.path)

    def _delete(self):
        m = self.marked()
        if not m:
            return
        # Schutz: ganze Gruppe markiert?
        full = [head.text(1) + " – " + head.text(2) for head, kids in self._children()
                if kids and all(k.checkState(0) == Qt.Checked for k in kids)]
        if full:
            r = QMessageBox.warning(
                self, "Alle Dateien einer Gruppe markiert",
                "In folgenden Gruppen sind ALLE Dateien markiert – der Titel wäre danach komplett weg:\n\n"
                + "\n".join(full[:10]) + ("\n…" if len(full) > 10 else "") + "\n\nTrotzdem fortfahren?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        self.delete_requested.emit(m)

    def remove_deleted(self, deleted_ids):
        """Nach erfolgreichem Löschen die Einträge aus der Ansicht entfernen."""
        deleted_ids = set(deleted_ids)
        new_groups = []
        for g in self.groups:
            rest = [t for t in g.tracks if t.id not in deleted_ids]
            if len(rest) >= 2:
                new_groups.append(duplicates.DuplicateGroup(g.reason, rest, g.similarity))
        self.groups = new_groups
        self.tracks = [t for t in self.tracks if t.id not in deleted_ids]
        self._fill()
