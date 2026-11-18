"""rekordbox-Fenster: Variante wählen (XML / Datenbank), Playlists und Titel bearbeiten."""
import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPushButton, QSplitter, QTableView,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from mog.core import rekordbox as rbmod
from mog.core.keydetect import CAMELOT_TO_MUSICAL, camelot_sort_key
from mog.core.track import format_bpm, format_duration

from .dialogs import primary
from .icons import icon
from .theme import C

COLLECTION = "__collection__"
STARS = ["–", "★", "★★", "★★★", "★★★★", "★★★★★"]
KEYS = [""] + sorted(CAMELOT_TO_MUSICAL, key=camelot_sort_key)


# --------------------------------------------------------------------------
# Titel-Tabelle
# --------------------------------------------------------------------------
class RBTrackModel(QAbstractTableModel):
    HEAD = ["#", "Artist", "Titel", "BPM", "Tonart", "Bewertung", "Länge", "In MOG", "Pfad"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []          # RBTrack-Objekte
        self.in_mog = set()     # Track-IDs, die auch in der MOG-Bibliothek sind
        self.sortable = True

    def set_rows(self, rows, in_mog, sortable=True):
        self.beginResetModel()
        self.rows = list(rows)
        self.in_mog = in_mog
        self.sortable = sortable
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEAD)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEAD[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t = self.rows[index.row()]
        c = index.column()
        if role == Qt.DisplayRole:
            return [str(index.row() + 1), t.artist, t.title, format_bpm(t.bpm), t.key,
                    STARS[t.rating] if t.rating else "", format_duration(t.length),
                    "✓" if t.id in self.in_mog else "", t.path][c]
        if role == Qt.UserRole:
            return t
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignRight if c in (0, 3, 6) else Qt.AlignCenter if c in (4, 5, 7)
                        else Qt.AlignLeft) | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if c == 7:
                return QColor(C["ok"])
            if c in (0, 3, 6, 8):
                return QColor(C["text2"])
            if c == 5:
                return QColor(C["accent2"])
            if t.path and not os.path.exists(t.path) and c in (1, 2):
                return QColor(C["text3"])
        if role == Qt.ToolTipRole:
            if t.path and not os.path.exists(t.path):
                return f"Datei nicht gefunden:\n{t.path}"
            return t.path
        return None

    def sort(self, column, order=Qt.AscendingOrder):
        if not self.sortable or column == 0:
            return
        keys = [None, lambda t: (t.artist or "").lower(), lambda t: (t.title or "").lower(),
                lambda t: t.bpm or 0, lambda t: camelot_sort_key(t.key), lambda t: t.rating,
                lambda t: t.length, lambda t: t.id in self.in_mog, lambda t: t.path.lower()]
        self.layoutAboutToBeChanged.emit()
        self.rows.sort(key=keys[column], reverse=order == Qt.DescendingOrder)
        self.layoutChanged.emit()


# --------------------------------------------------------------------------
# Playlist-Baum mit Drag & Drop
# --------------------------------------------------------------------------
class PlaylistTree(QTreeWidget):
    moved = Signal(object, object, int)     # node, neuer Elternknoten, Index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIconSize(QSize(18, 18))
        self.setIndentation(16)

    def dropEvent(self, e):
        src = self.currentItem()
        node = src.data(0, Qt.UserRole) if src else None
        if node is None or not getattr(node, "editable", False):
            e.ignore()
            return
        target = self.itemAt(e.position().toPoint())
        pos = self.dropIndicatorPosition()
        tnode = target.data(0, Qt.UserRole) if target else None
        if tnode is None or tnode == COLLECTION:
            parent, index = None, None
        elif pos == QAbstractItemView.OnItem and tnode.is_folder:
            parent, index = tnode, None
        else:
            parent = tnode.parent
            index = parent.children.index(tnode) + (1 if pos == QAbstractItemView.BelowItem else 0)
            if node in parent.children and parent.children.index(node) < index:
                index -= 1
        e.ignore()     # Baum wird nach dem Verschieben neu aufgebaut
        self.moved.emit(node, parent, -1 if index is None else index)


# --------------------------------------------------------------------------
# Titel bearbeiten
# --------------------------------------------------------------------------
class RBTrackEditor(QDialog):
    def __init__(self, track, kind, parent=None):
        super().__init__(parent)
        self.setWindowTitle("rekordbox-Titel bearbeiten")
        self.setMinimumWidth(520)
        self.track = track
        lay = QVBoxLayout(self)
        p = QLabel(track.path)
        p.setObjectName("Hint")
        p.setWordWrap(True)
        lay.addWidget(p)
        f = QFormLayout()
        self.ed = {}
        for key, label in (("title", "Titel"), ("artist", "Artist"), ("album", "Album"), ("genre", "Genre"),
                           ("label", "Label"), ("year", "Jahr"), ("comment", "Kommentar")):
            e = QLineEdit(str(getattr(track, key) or ""))
            f.addRow(label + ":", e)
            self.ed[key] = e
        self.bpm = QLineEdit(format_bpm(track.bpm) if track.bpm else "")
        f.addRow("BPM:", self.bpm)
        self.key = QComboBox()
        self.key.setEditable(True)
        for k in KEYS:
            self.key.addItem(f"{k}  ({CAMELOT_TO_MUSICAL[k]})" if k else "", k)
        self.key.setCurrentText(track.key or "")
        f.addRow("Tonart:", self.key)
        self.rating = QComboBox()
        self.rating.addItems(STARS)
        self.rating.setCurrentIndex(int(track.rating or 0))
        f.addRow("Bewertung:", self.rating)
        lay.addLayout(f)
        if kind == rbmod.DB:
            h = QLabel("Tonart: rekordbox kennt nur Tonarten aus seiner eigenen Liste – unbekannte "
                       "Schreibweisen werden ignoriert.")
            h.setObjectName("Hint")
            h.setWordWrap(True)
            lay.addWidget(h)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        ok = primary(QPushButton("Übernehmen"))
        bb.addButton(ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        out = {k: e.text().strip() for k, e in self.ed.items()}
        try:
            out["bpm"] = float(self.bpm.text().replace(",", ".")) if self.bpm.text().strip() else None
        except ValueError:
            out["bpm"] = self.track.bpm
        key = self.key.currentData() if self.key.currentText() == self.key.itemText(self.key.currentIndex()) \
            else self.key.currentText().strip()
        out["key"] = key or ""
        out["rating"] = self.rating.currentIndex()
        return {k: v for k, v in out.items() if v != getattr(self.track, k)}


# --------------------------------------------------------------------------
# Hauptfenster rekordbox
# --------------------------------------------------------------------------
class RekordboxWindow(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.s = mw.s
        self.setWindowTitle("rekordbox")
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.resize(1180, 720)
        self.current = COLLECTION

        lay = QVBoxLayout(self)
        # --- Variante
        top = QHBoxLayout()
        top.addWidget(QLabel("Variante:"))
        self.cmb = QComboBox()
        self.cmb.addItem("rekordbox-XML (offiziell, sicher)", rbmod.XML)
        self.cmb.addItem("rekordbox-Datenbank (direkt, inoffiziell)", rbmod.DB)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(self.s.value("rekordbox/kind", rbmod.XML))))
        top.addWidget(self.cmb)
        self.b_open = QPushButton(icon("folder"), " XML öffnen …")
        self.b_new = QPushButton(icon("plus"), " Neue XML")
        self.b_db = QPushButton(icon("library"), " Datenbank laden")
        self.b_dbpath = QPushButton(icon("folder"), " Pfad wählen …")
        for b in (self.b_open, self.b_new, self.b_db, self.b_dbpath):
            top.addWidget(b)
        top.addStretch()
        self.lbl_src = QLabel("")
        self.lbl_src.setObjectName("Hint")
        top.addWidget(self.lbl_src)
        lay.addLayout(top)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        # --- Inhalt
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.tree = PlaylistTree()
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        ll.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.b_newpl = QPushButton(icon("plus"), " Playlist")
        self.b_newfo = QPushButton(icon("folder"), " Ordner")
        row.addWidget(self.b_newpl)
        row.addWidget(self.b_newfo)
        ll.addLayout(row)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        self.lbl_list = QLabel("")
        self.lbl_list.setObjectName("BigTitle")
        rl.addWidget(self.lbl_list)
        self.model = RBTrackModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        hh = self.table.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        for i, w in enumerate([40, 190, 240, 56, 60, 86, 60, 60, 340]):
            self.table.setColumnWidth(i, w)
        rl.addWidget(self.table, 1)
        tb = QHBoxLayout()
        self.b_add = QPushButton(icon("plus"), " Markierte MOG-Titel hinzufügen")
        self.b_add.setToolTip("Fügt die im Hauptfenster markierten Titel dieser Playlist hinzu "
                              "(und bei Bedarf der rekordbox-Sammlung).")
        self.b_remove = QPushButton(icon("x"), " Aus Playlist entfernen")
        self.b_up = QPushButton(icon("up"), "")
        self.b_up.setToolTip("Nach oben")
        self.b_down = QPushButton(icon("down"), "")
        self.b_down.setToolTip("Nach unten")
        self.b_edit = QPushButton(icon("tag"), " Bearbeiten …")
        self.b_show = QPushButton(icon("search"), " In MOG zeigen")
        for b in (self.b_add, self.b_remove, self.b_up, self.b_down, self.b_edit, self.b_show):
            tb.addWidget(b)
        tb.addStretch()
        rl.addLayout(tb)
        split.addWidget(right)
        split.setSizes([300, 880])
        lay.addWidget(split, 1)

        # --- Speichern
        bottom = QHBoxLayout()
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("Muted")
        bottom.addWidget(self.lbl_state, 1)
        self.b_discard = QPushButton(icon("undo"), " Verwerfen")
        self.b_saveas = QPushButton(icon("save"), " Speichern unter …")
        self.b_save = primary(QPushButton(icon("save", "#FFFFFF"), "  Speichern"))
        for b in (self.b_discard, self.b_saveas, self.b_save):
            bottom.addWidget(b)
        b_close = QPushButton("Schließen")
        b_close.clicked.connect(self.close)
        bottom.addWidget(b_close)
        lay.addLayout(bottom)

        self._icons = [(self.b_open, "folder"), (self.b_new, "plus"), (self.b_db, "library"),
                       (self.b_dbpath, "folder"), (self.b_newpl, "plus"), (self.b_newfo, "folder"),
                       (self.b_add, "plus"), (self.b_remove, "x"), (self.b_up, "up"), (self.b_down, "down"),
                       (self.b_edit, "tag"), (self.b_show, "search"), (self.b_discard, "undo"),
                       (self.b_saveas, "save")]

        # --- Signale
        self.cmb.currentIndexChanged.connect(self._kind_changed)
        self.b_open.clicked.connect(lambda: self.open_xml())
        self.b_new.clicked.connect(lambda: self.new_xml())
        self.b_db.clicked.connect(lambda: self.load_db())
        self.b_dbpath.clicked.connect(lambda: self.load_db(choose=True))
        self.tree.itemSelectionChanged.connect(self._on_node)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self._rename(it.data(0, Qt.UserRole)))
        self.tree.moved.connect(self._move_node)
        self.b_newpl.clicked.connect(lambda: self._create("playlist"))
        self.b_newfo.clicked.connect(lambda: self._create("folder"))
        self.b_add.clicked.connect(lambda: self.add_mog_selection())
        self.b_remove.clicked.connect(lambda: self._remove_selected())
        self.b_up.clicked.connect(lambda: self._move_selected(-1))
        self.b_down.clicked.connect(lambda: self._move_selected(1))
        self.b_edit.clicked.connect(lambda: self._edit_selected())
        self.b_show.clicked.connect(lambda: self._show_in_mog())
        self.table.doubleClicked.connect(lambda _i: self._edit_selected())
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.b_save.clicked.connect(lambda: self.save())
        self.b_saveas.clicked.connect(lambda: self.save(ask_path=True))
        self.b_discard.clicked.connect(lambda: self.discard())
        self._kind_changed()

    def retheme(self):
        for b, name in self._icons:
            b.setIcon(icon(name))
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        self._fill_tree()
        self.table.viewport().update()

    # ------------------------------------------------------------------ Hilfen
    @property
    def lib(self):
        return self.mw.rb

    def _kind(self):
        return self.cmb.currentData()

    def _kind_changed(self, *_):
        k = self._kind()
        self.s.set("rekordbox/kind", k)
        xml = k == rbmod.XML
        self.b_open.setVisible(xml)
        self.b_new.setVisible(xml)
        self.b_saveas.setVisible(xml)
        self.b_db.setVisible(not xml)
        self.b_dbpath.setVisible(not xml)
        if xml:
            self.hint.setObjectName("Hint")
            self.hint.setText(
                "So geht's: In rekordbox „Datei → Sammlung im xml-Format exportieren“ und die Datei hier öffnen – "
                "oder eine neue XML anlegen. Zum Einlesen in rekordbox: Einstellungen → Erweitert → Datenbank → "
                "„rekordbox xml“ → Importierte Bibliothek: diese Datei wählen. Links erscheint dann "
                "„rekordbox xml“ mit deinen Playlists (per Drag & Drop übernehmen).")
        else:
            self.hint.setObjectName("Warning")
            self.hint.setText(
                "⚠ Direkter Zugriff auf die rekordbox-Datenbank (master.db) – nicht offiziell von AlphaTheta "
                "unterstützt. rekordbox muss zum Speichern beendet sein. MOG legt vor jedem Speichern "
                "automatisch eine Sicherung an. Neu hinzugefügte Titel in rekordbox danach analysieren lassen.")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)
        if self.lib is not None and self.lib.kind != k:
            # andere Variante gewählt: nicht automatisch wechseln, wenn noch Änderungen offen sind
            pass
        self.refresh()

    def _ask_unsaved(self):
        if self.lib is None or not self.lib.dirty:
            return True
        r = QMessageBox.question(self, "rekordbox", "Es gibt ungespeicherte rekordbox-Änderungen. Jetzt speichern?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save()
        return True

    # ------------------------------------------------------------------ Laden
    def open_xml(self, path=None):
        if not self._ask_unsaved():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "rekordbox-XML öffnen", self.s.value("rekordbox/xml", ""),
                                                  "rekordbox-XML (*.xml);;Alle Dateien (*)")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            lib = rbmod.XmlLibrary.load(path)
        except rbmod.RekordboxError as e:
            QMessageBox.warning(self, "rekordbox-XML", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.s.set("rekordbox/xml", path)
        self.mw.set_rekordbox(lib)
        self.refresh()

    def new_xml(self):
        if not self._ask_unsaved():
            return
        from mog import __version__
        self.mw.set_rekordbox(rbmod.XmlLibrary.new(__version__))
        self.refresh()

    def load_db(self, choose=False):
        if not self._ask_unsaved():
            return
        path = self.s.value("rekordbox/db", "") or rbmod.default_db_path()
        if choose or not path or not os.path.exists(path):
            path, _ = QFileDialog.getOpenFileName(self, "rekordbox-Datenbank (master.db) wählen", path or "",
                                                  "rekordbox-Datenbank (master.db);;Alle Dateien (*)")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            lib = rbmod.DbLibrary.load(path, backup_dir=os.path.join(self.mw.data_dir, "rekordbox-backups"))
        except rbmod.RekordboxError as e:
            QMessageBox.warning(self, "rekordbox-Datenbank", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.s.set("rekordbox/db", path)
        self.mw.set_rekordbox(lib)
        if rbmod.rekordbox_running():
            QMessageBox.information(self, "rekordbox läuft", "rekordbox ist gerade geöffnet. Du kannst lesen und "
                                    "bearbeiten – zum Speichern muss rekordbox aber beendet sein.")
        self.refresh()

    # ------------------------------------------------------------------ Anzeige
    def refresh(self):
        lib = self.lib
        has = lib is not None
        matches = has and lib.kind == self._kind()
        for b in (self.b_newpl, self.b_newfo, self.b_add, self.b_remove, self.b_up, self.b_down, self.b_edit,
                  self.b_show, self.tree, self.table):
            b.setEnabled(matches)
        if has and not matches:
            self.lbl_src.setText(f"Geladen ist: {lib.label} – zum Wechseln oben laden")
        else:
            self.lbl_src.setText(f"{lib.label}: {lib.source or 'neu (noch nicht gespeichert)'}" if has
                                 else "Noch nichts geladen")
        self._fill_tree()
        self._on_node()
        self._update_state()

    def _update_state(self):
        lib = self.lib
        n = lib.changes if lib else 0
        self.lbl_state.setText(f"{n} ungespeicherte Änderung(en)" if n else
                               ("Alles gespeichert" if lib else ""))
        self.b_save.setEnabled(bool(lib) and (n > 0 or (lib.kind == rbmod.XML and not lib.source)))
        self.b_saveas.setEnabled(bool(lib))
        self.b_discard.setEnabled(n > 0)

    def _changed(self):
        self.mw.rekordbox_changed()
        self._update_state()

    def _fill_tree(self):
        sel = self.current
        self.tree.blockSignals(True)
        self.tree.clear()
        lib = self.lib
        if lib is not None:
            coll = QTreeWidgetItem([f"Sammlung ({len(lib.tracks):,})".replace(",", ".")])
            coll.setIcon(0, icon("library"))
            coll.setData(0, Qt.UserRole, COLLECTION)
            coll.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled)
            self.tree.addTopLevelItem(coll)

            def add(parent_item, node):
                it = QTreeWidgetItem([node.name + (f"  ({len(node.tracks)})" if node.kind == "playlist" else "")])
                it.setData(0, Qt.UserRole, node)
                ic = {"folder": "folder", "playlist": "library", "smart": "pulse"}[node.kind]
                it.setIcon(0, icon(ic))
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if node.editable:
                    flags |= Qt.ItemIsDragEnabled
                if node.kind == "folder":
                    flags |= Qt.ItemIsDropEnabled
                if node.kind == "smart":
                    it.setToolTip(0, "Intelligente Playlist – nur Anzeige")
                it.setFlags(flags)
                if parent_item is None:
                    self.tree.addTopLevelItem(it)
                else:
                    parent_item.addChild(it)
                for c in node.children:
                    add(it, c)
                if node.id == sel or (sel != COLLECTION and getattr(sel, "id", None) == node.id):
                    self.tree.setCurrentItem(it)
                return it

            for c in lib.root.children:
                add(None, c)
            self.tree.expandAll()
            if self.tree.currentItem() is None:
                self.tree.setCurrentItem(coll)
        self.tree.blockSignals(False)

    def _node(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def _on_node(self):
        lib = self.lib
        node = self._node()
        self.current = node if node is not None else COLLECTION
        if lib is None or node is None:
            self.model.set_rows([], set())
            self.lbl_list.setText("")
            return
        in_mog = self.mw.rb_ids_in_mog()
        if node == COLLECTION:
            rows = list(lib.tracks.values())
            self.lbl_list.setText(f"Sammlung · {len(rows):,} Titel".replace(",", "."))
            self.model.set_rows(rows, in_mog, sortable=True)
            self.table.setSortingEnabled(True)
        else:
            rows = [lib.tracks[t] for t in node.tracks if t in lib.tracks]
            self.lbl_list.setText(f"{node.path_name()} · {len(rows)} Titel")
            self.table.setSortingEnabled(False)
            self.model.set_rows(rows, in_mog, sortable=False)
            self.table.horizontalHeader().setSortIndicatorShown(False)
        is_pl = node != COLLECTION and node.kind == "playlist"
        for b in (self.b_remove, self.b_up, self.b_down):
            b.setEnabled(is_pl)
        self.b_add.setEnabled(node == COLLECTION or is_pl)

    def _selected_tracks(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.rows[r] for r in rows]

    # ------------------------------------------------------------------ Playlists bearbeiten
    def _create(self, kind):
        if self.lib is None:
            return
        node = self._node()
        parent = node if (node not in (None, COLLECTION) and node.is_folder) else \
            (node.parent if node not in (None, COLLECTION) else None)
        title = "Neue Playlist" if kind == "playlist" else "Neuer Ordner"
        name, ok = QInputDialog.getText(self, title, "Name:", text=title)
        if not ok or not name.strip():
            return
        try:
            n = (self.lib.create_playlist if kind == "playlist" else self.lib.create_folder)(parent, name.strip())
        except rbmod.RekordboxError as e:
            QMessageBox.warning(self, "rekordbox", str(e))
            return
        self.current = n
        self._changed()
        self._fill_tree()
        self._on_node()

    def _rename(self, node):
        if node in (None, COLLECTION) or not node.editable:
            return
        name, ok = QInputDialog.getText(self, "Umbenennen", "Neuer Name:", text=node.name)
        if ok and name.strip() and name.strip() != node.name:
            self.lib.rename(node, name.strip())
            self._changed()
            self._fill_tree()

    def _delete(self, node):
        if node in (None, COLLECTION) or not node.editable:
            return
        what = "den Ordner (inklusive allem darin)" if node.kind == "folder" else "die Playlist"
        if QMessageBox.question(self, "Löschen", f"„{node.name}“ – {what} löschen?\n"
                                "Die Titel bleiben in der Sammlung.") != QMessageBox.Yes:
            return
        self.lib.delete(node)
        self.current = COLLECTION
        self._changed()
        self._fill_tree()
        self._on_node()

    def _move_node(self, node, parent, index):
        try:
            self.lib.move_node(node, parent, None if index < 0 else index)
        except rbmod.RekordboxError as e:
            QMessageBox.warning(self, "Verschieben", str(e))
            return
        self.current = node
        self._changed()
        self._fill_tree()

    def _tree_menu(self, pos):
        if self.lib is None:
            return
        it = self.tree.itemAt(pos)
        node = it.data(0, Qt.UserRole) if it else None
        m = QMenu(self)
        m.addAction(icon("plus"), "Neue Playlist …", lambda: self._create("playlist"))
        m.addAction(icon("folder"), "Neuer Ordner …", lambda: self._create("folder"))
        if node not in (None, COLLECTION) and node.editable:
            m.addSeparator()
            m.addAction(icon("rename"), "Umbenennen …", lambda: self._rename(node))
            m.addAction(icon("trash", C["bad"]), "Löschen …", lambda: self._delete(node))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ Titel bearbeiten
    def add_mog_selection(self, node=None):
        node = node or self._node()
        mog = [t for t in self.mw.selected_tracks() if not t.missing]
        if not mog:
            QMessageBox.information(self, "Hinzufügen", "Bitte zuerst im Hauptfenster Titel markieren.")
            return
        self.add_tracks(mog, node)

    def add_tracks(self, mog_tracks, node):
        if self.lib is None:
            return 0
        errors, ids = [], []
        for t in mog_tracks:
            try:
                ids.append(self.lib.ensure_track(t).id)
            except rbmod.RekordboxError as e:
                errors.append(str(e))
        added = 0
        if node not in (None, COLLECTION) and node.kind == "playlist":
            added = self.lib.add_to_playlist(node, ids)
        self._changed()
        self._fill_tree()
        self._on_node()
        msg = f"{len(ids)} Titel in der Sammlung" + (f", {added} zur Playlist hinzugefügt" if node not in
                                                     (None, COLLECTION) else "")
        self.lbl_state.setText(msg + f" · {self.lib.changes} ungespeicherte Änderung(en)")
        if errors:
            QMessageBox.warning(self, "Hinzufügen", "Nicht hinzugefügt:\n\n" + "\n".join(errors[:12]))
        return added

    def _remove_selected(self):
        node = self._node()
        ts = self._selected_tracks()
        if node in (None, COLLECTION) or not ts:
            return
        self.lib.remove_from_playlist(node, [t.id for t in ts])
        self._changed()
        self._fill_tree()
        self._on_node()

    def _move_selected(self, step):
        node = self._node()
        ts = self._selected_tracks()
        if node in (None, COLLECTION) or len(ts) != 1:
            return
        i = node.tracks.index(ts[0].id)
        j = i + step
        if 0 <= j < len(node.tracks):
            self.lib.move_in_playlist(node, ts[0].id, j)
            self._changed()
            self._on_node()
            self.table.selectRow(j)

    def _edit_selected(self):
        ts = self._selected_tracks()
        if not ts or self.lib is None:
            return
        t = ts[0]
        dlg = RBTrackEditor(t, self.lib.kind, self)
        if dlg.exec():
            vals = dlg.values()
            if vals:
                self.lib.update_track(t.id, **vals)
                self._changed()
                self.model.layoutChanged.emit()

    def _show_in_mog(self):
        ts = self._selected_tracks()
        if ts:
            self.mw.reveal_in_list(ts[0].path)

    def _table_menu(self, pos):
        ts = self._selected_tracks()
        if not ts:
            return
        node = self._node()
        m = QMenu(self)
        m.addAction(icon("tag"), "Bearbeiten …", lambda: self._edit_selected())
        m.addAction(icon("search"), "In MOG zeigen", lambda: self._show_in_mog())
        if node not in (None, COLLECTION) and node.kind == "playlist":
            m.addAction(icon("x"), "Aus Playlist entfernen", lambda: self._remove_selected())
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ Speichern
    def save(self, ask_path=False):
        lib = self.lib
        if lib is None:
            return True
        path = None
        if lib.kind == rbmod.XML and (ask_path or not lib.source):
            path, _ = QFileDialog.getSaveFileName(self, "rekordbox-XML speichern",
                                                  lib.source or os.path.join(os.path.expanduser("~"), "MOG-rekordbox.xml"),
                                                  "rekordbox-XML (*.xml)")
            if not path:
                return False
            if not path.lower().endswith(".xml"):
                path += ".xml"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            backup = lib.save(path)
        except rbmod.RekordboxError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "rekordbox speichern", str(e))
            return False
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "rekordbox speichern", f"Speichern fehlgeschlagen: {e}")
            return False
        QApplication.restoreOverrideCursor()
        if lib.kind == rbmod.XML:
            self.s.set("rekordbox/xml", lib.source)
            self.lbl_state.setText(f"Gespeichert: {lib.source}")
        else:
            self.lbl_state.setText(f"In rekordbox gespeichert · Sicherung: {backup}")
        self.mw.rekordbox_changed()
        self.refresh()
        return True

    def discard(self):
        if self.lib is None or not self.lib.dirty:
            return
        if QMessageBox.question(self, "Verwerfen", "Alle ungespeicherten rekordbox-Änderungen verwerfen?") \
                != QMessageBox.Yes:
            return
        self.mw.set_rekordbox(self.lib.discard())
        self.current = COLLECTION
        self.refresh()
