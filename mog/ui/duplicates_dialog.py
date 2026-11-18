"""Duplikate finden, prüfen, anhören, löschen oder in einen Ordner verschieben."""
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from mog.core import duplicates
from mog.core.fingerprint import find_fpcalc
from mog.core.library import Library
from mog.core.track import format_date, format_duration, format_size

from .dialogs import primary, run_task
from .icons import format_badge, icon
from .theme import C

REASON_LABEL = {"tags": "gleiche Tags", "identisch": "identische Datei", "fingerprint": "gleicher Klang"}

# Spalten
COL_MARK, COL_ARTIST, COL_TITLE, COL_LEN, COL_KBPS, COL_CREATED, COL_FMT, COL_RB, COL_PATH = range(9)
HEADERS = ["Löschen", "Artist", "Titel", "Länge", "kbps", "Erstellt", "Format", "rekordbox", "Ordner"]
WIDTHS = [92, 200, 250, 58, 54, 122, 66, 96, 300]

RULES = [
    ("quality", "Beste Qualität behalten"),
    ("oldest", "Älteste Datei behalten (Erstellungsdatum)"),
    ("newest", "Neueste Datei behalten (Erstellungsdatum)"),
    ("rekordbox", "Datei aus rekordbox behalten"),
    ("folder", "Datei aus bevorzugtem Ordner behalten …"),
]


def pick_keep(group_tracks, rule, rb_info=None, folder=None):
    """Wählt den zu behaltenden Titel einer Gruppe. group_tracks ist nach Qualität sortiert."""
    ts = list(group_tracks)
    best = ts[0]
    if rule == "oldest":
        dated = [t for t in ts if t.created]
        return min(dated, key=lambda t: t.created) if dated else best
    if rule == "newest":
        dated = [t for t in ts if t.created]
        return max(dated, key=lambda t: t.created) if dated else best
    if rule == "rekordbox" and rb_info:
        inrb = [t for t in ts if t.id in rb_info]
        return max(inrb, key=lambda t: len(rb_info[t.id])) if inrb else best
    if rule == "folder" and folder:
        pref = folder.rstrip("/\\") + os.sep
        inside = [t for t in ts if t.path.startswith(pref)]
        return inside[0] if inside else best
    return best


class DuplicatesDialog(QDialog):
    play_requested = Signal(object)
    delete_requested = Signal(list)          # Liste von Tracks
    move_requested = Signal(list, str)       # Tracks, Zielordner

    def __init__(self, tracks, settings, db_path, parent=None, rb_info=None):
        super().__init__(parent)
        self.setWindowTitle("Duplikate finden")
        self.resize(1260, 760)
        self.tracks = tracks
        self.s = settings
        self.db_path = db_path
        self.rb_info = rb_info or {}          # track_id -> [Playlists]
        self.groups = []
        self.fpcalc = find_fpcalc(self.s.get("tools/fpcalc") or None)

        lay = QVBoxLayout(self)
        title = QLabel("Duplikate finden")
        title.setObjectName("BigTitle")
        lay.addWidget(title)
        sub = QLabel(f"Durchsucht {len(tracks):,} Titel der aktuellen Ansicht.".replace(",", "."))
        sub.setObjectName("Hint")
        lay.addWidget(sub)

        # --- Suchoptionen
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
        self.sp_tol.setDecimals(1)
        self.sp_tol.setValue(self.s.get("dup/tolerance"))
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
        self.btn_search.clicked.connect(lambda: self.search())
        opts.addWidget(self.btn_search)
        lay.addLayout(opts)

        # --- Liste
        self.tree = QTreeWidget()
        self.tree.setObjectName("DupTree")
        self.tree.setColumnCount(len(HEADERS))
        self.tree.setHeaderLabels(HEADERS)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setIconSize(QSize(46, 18))
        for i, w in enumerate(WIDTHS):
            self.tree.setColumnWidth(i, w)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionsMovable(True)
        self.tree.itemDoubleClicked.connect(self._play_item)
        self.tree.itemChanged.connect(self._update_summary)
        lay.addWidget(self.tree, 1)

        self.summary = QLabel("Noch keine Suche durchgeführt.")
        self.summary.setObjectName("Muted")
        lay.addWidget(self.summary)

        # --- Markieren
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Regel:"))
        self.cmb_rule = QComboBox()
        for k, label in RULES:
            if k == "rekordbox" and not self.rb_info:
                continue
            self.cmb_rule.addItem(label, k)
        self.cmb_rule.setCurrentIndex(max(0, self.cmb_rule.findData(self.s.value("dup/rule", "quality"))))
        row1.addWidget(self.cmb_rule)
        b_auto = QPushButton(icon("check"), " Automatisch markieren")
        b_auto.setToolTip("Behält je Gruppe eine Datei nach der gewählten Regel und markiert alle anderen.")
        b_auto.clicked.connect(lambda: self.auto_mark())
        row1.addWidget(b_auto)
        b_none = QPushButton("Markierung aufheben")
        b_none.clicked.connect(lambda: self._mark_all(False))
        row1.addWidget(b_none)
        row1.addSpacing(12)
        b_ign = QPushButton(icon("eye"), " Kein Duplikat")
        b_ign.setToolTip("Die ausgewählten Gruppen sind keine Duplikate – sie werden bei künftigen Suchen "
                         "nicht mehr angezeigt.")
        b_ign.clicked.connect(lambda: self._ignore_selected())
        row1.addWidget(b_ign)
        b_reset = QPushButton("Ausgeblendete zurücksetzen")
        b_reset.clicked.connect(lambda: self._reset_ignored())
        row1.addWidget(b_reset)
        row1.addStretch()
        lay.addLayout(row1)

        # --- Aktionen
        row = QHBoxLayout()
        b_play = QPushButton(icon("play"), " Anhören")
        b_play.clicked.connect(lambda: self._play_item(self.tree.currentItem()))
        b_reveal = QPushButton(icon("folder"), " Im Ordner zeigen")
        b_reveal.clicked.connect(lambda: self._reveal())
        row.addWidget(b_play)
        row.addWidget(b_reveal)
        row.addStretch()
        self.btn_move = QPushButton(icon("folder"), "  Markierte verschieben …")
        self.btn_move.setToolTip("Sicherer als Löschen: Die markierten Dateien wandern in einen Ordner "
                                 "deiner Wahl (z. B. „Duplikate prüfen“) und verschwinden aus der MOG-Liste.")
        self.btn_move.setEnabled(False)
        self.btn_move.clicked.connect(lambda: self._move())
        self.btn_delete = QPushButton(icon("trash", C["danger_text"]), "  Markierte löschen …")
        self.btn_delete.setObjectName("Danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(lambda: self._delete())
        b_close = QPushButton("Schließen")
        b_close.clicked.connect(self.accept)
        row.addWidget(self.btn_move)
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
                groups = duplicates.run_search(tracks, lib=lib, progress=progress, cancel=cancel, **opts)
                ignored = lib.dup_ignored()
                groups = [g for g in groups
                          if not any({t.id for t in g.tracks} <= ig for ig in ignored)]
                progress(0, 0, "Lese Erstellungsdaten …")
                lib.fill_created([t for g in groups for t in g.tracks])
                return groups, len(ignored)
            finally:
                lib.close()

        res = run_task(self, "Suche Duplikate …", job)
        if res is None:
            return
        self.groups, self.n_ignored = res
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
            save = sum(t.size or 0 for t in g.tracks) - (best.size or 0)
            head = QTreeWidgetItem([f"#{gi}", best.display_artist, best.display_title, "", "", "", "", "",
                                    f"{len(g.tracks)} Dateien · {reasons}{sim} · bis {format_size(save)} frei"])
            for c in range(len(HEADERS)):
                head.setFont(c, bold)
                head.setBackground(c, QBrush(QColor(C["panel2"])))
            head.setForeground(COL_PATH, QBrush(QColor(C["text2"])))
            head.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            head.setData(0, Qt.UserRole + 1, g)
            self.tree.addTopLevelItem(head)
            oldest = min((t.created for t in g.tracks if t.created), default=None)
            for t in g.tracks:
                pl = self.rb_info.get(t.id)
                rb_text = "" if pl is None else (f"● {len(pl)}" if pl else "●")
                it = QTreeWidgetItem(["", t.display_artist, t.display_title, format_duration(t.duration),
                                      str(round(t.bitrate / 1000)) if t.bitrate else "",
                                      format_date(t.created), "", rb_text, t.folder])
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                it.setCheckState(COL_MARK, Qt.Unchecked)
                it.setData(0, Qt.UserRole, t)
                it.setIcon(COL_FMT, format_badge(t.fmt or "?", 18))
                it.setToolTip(COL_PATH, t.path)
                it.setToolTip(COL_TITLE, t.filename)
                for c in (COL_LEN, COL_KBPS, COL_CREATED):
                    it.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                it.setTextAlignment(COL_RB, Qt.AlignCenter)
                if pl is not None:
                    it.setForeground(COL_RB, QBrush(QColor(C["ok"])))
                    it.setToolTip(COL_RB, "In rekordbox" + (":\n• " + "\n• ".join(pl[:12]) if pl else
                                                            " (in keiner Playlist)"))
                if t.created and t.created == oldest and len(g.tracks) > 1:
                    it.setToolTip(COL_CREATED, "Älteste Datei dieser Gruppe")
                if t is best:
                    it.setText(COL_MARK, "★")
                    it.setForeground(COL_MARK, QBrush(QColor(C["ok"])))
                    it.setToolTip(COL_MARK, "Beste Qualität in dieser Gruppe")
                head.addChild(it)
            head.setExpanded(True)
        self.tree.blockSignals(False)
        self._update_summary()
        if not self.groups:
            extra = f" ({self.n_ignored} Gruppen als „Kein Duplikat“ ausgeblendet)" if getattr(self, "n_ignored", 0) else ""
            self.summary.setText("Keine Duplikate gefunden." + extra)

    # --- Markieren ---------------------------------------------------------
    def _children(self):
        for i in range(self.tree.topLevelItemCount()):
            head = self.tree.topLevelItem(i)
            yield head, [head.child(j) for j in range(head.childCount())]

    def auto_mark(self):
        rule = self.cmb_rule.currentData()
        self.s.set("dup/rule", rule)
        folder = None
        if rule == "folder":
            folder = QFileDialog.getExistingDirectory(self, "Bevorzugter Ordner (diese Dateien behalten)",
                                                      self.s.value("dup/folder", ""))
            if not folder:
                return
            self.s.set("dup/folder", folder)
        self.tree.blockSignals(True)
        for head, kids in self._children():
            g = head.data(0, Qt.UserRole + 1)
            keep = pick_keep(g.tracks, rule, self.rb_info, folder)
            for it in kids:
                it.setCheckState(COL_MARK, Qt.Unchecked if it.data(0, Qt.UserRole) is keep else Qt.Checked)
        self.tree.blockSignals(False)
        self._update_summary()

    def _mark_all(self, state):
        self.tree.blockSignals(True)
        for head, kids in self._children():
            for it in kids:
                it.setCheckState(COL_MARK, Qt.Checked if state else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._update_summary()

    def marked(self):
        out = []
        for head, kids in self._children():
            for it in kids:
                if it.checkState(COL_MARK) == Qt.Checked:
                    out.append(it.data(0, Qt.UserRole))
        return out

    def _update_summary(self, *_):
        m = self.marked()
        n_files = sum(len(g.tracks) for g in self.groups)
        size = sum(t.size or 0 for t in m)
        self.summary.setText(f"{len(self.groups)} Gruppen · {n_files} Dateien · "
                             f"{len(m)} markiert ({format_size(size)} werden frei)")
        self.btn_delete.setEnabled(bool(m))
        self.btn_move.setEnabled(bool(m))

    # --- „Kein Duplikat“ -----------------------------------------------------
    def _selected_groups(self):
        out = []
        for it in self.tree.selectedItems():
            head = it if it.parent() is None else it.parent()
            g = head.data(0, Qt.UserRole + 1)
            if g is not None and g not in out:
                out.append(g)
        return out

    def _ignore_selected(self):
        gs = self._selected_groups()
        if not gs:
            QMessageBox.information(self, "Kein Duplikat", "Bitte zuerst eine oder mehrere Gruppen auswählen.")
            return
        lib = Library(self.db_path)
        try:
            for g in gs:
                lib.add_dup_ignore([t.id for t in g.tracks])
        finally:
            lib.close()
        self.groups = [g for g in self.groups if g not in gs]
        self.n_ignored = getattr(self, "n_ignored", 0) + len(gs)
        self._fill()

    def _reset_ignored(self):
        if QMessageBox.question(self, "Ausgeblendete zurücksetzen",
                                "Alle als „Kein Duplikat“ markierten Gruppen wieder anzeigen?\n"
                                "(Wirkt bei der nächsten Suche.)") != QMessageBox.Yes:
            return
        lib = Library(self.db_path)
        try:
            lib.clear_dup_ignore()
        finally:
            lib.close()
        self.n_ignored = 0

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

    def _confirm_full_groups(self):
        full = [head.text(COL_ARTIST) + " – " + head.text(COL_TITLE) for head, kids in self._children()
                if kids and all(k.checkState(COL_MARK) == Qt.Checked for k in kids)]
        if not full:
            return True
        r = QMessageBox.warning(
            self, "Alle Dateien einer Gruppe markiert",
            "In folgenden Gruppen sind ALLE Dateien markiert – der Titel wäre danach komplett weg:\n\n"
            + "\n".join(full[:10]) + ("\n…" if len(full) > 10 else "") + "\n\nTrotzdem fortfahren?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return r == QMessageBox.Yes

    def _delete(self):
        m = self.marked()
        if m and self._confirm_full_groups():
            self.delete_requested.emit(m)

    def _move(self):
        m = self.marked()
        if not m or not self._confirm_full_groups():
            return
        folder = QFileDialog.getExistingDirectory(self, "Zielordner für aussortierte Duplikate",
                                                  self.s.value("dup/move_dir", ""))
        if folder:
            self.s.set("dup/move_dir", folder)
            self.move_requested.emit(m, folder)

    def remove_deleted(self, deleted_ids):
        """Nach Löschen/Verschieben die Einträge aus der Ansicht entfernen."""
        deleted_ids = set(deleted_ids)
        new_groups = []
        for g in self.groups:
            rest = [t for t in g.tracks if t.id not in deleted_ids]
            if len(rest) >= 2:
                new_groups.append(duplicates.DuplicateGroup(g.reason, rest, g.similarity))
        self.groups = new_groups
        self.tracks = [t for t in self.tracks if t.id not in deleted_ids]
        self._fill()
