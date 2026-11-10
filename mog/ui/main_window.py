"""Hauptfenster von MusicOrganizer (MOG)."""
import os
import time

from PySide6.QtCore import QByteArray, QEvent, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSplitter,
                               QTableView, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from mog import APP_NAME, __version__
from mog.core import bpm as bpmmod, encoder, fileops, pending as pendingmod, scanner, tags as tagio
from mog.core import updater
from mog.core.formats import dialog_filter
from mog.core.library import Library
from mog.core.track import format_bpm, format_duration, format_size

from .convert_dialog import ConvertDialog
from .dialogs import DeleteDialog, SettingsDialog, VolumeDialog, run_task
from .duplicates_dialog import DuplicatesDialog
from .icons import icon, logo_pixmap, placeholder_cover, svg_pixmap
from .online_dialog import OnlineTagDialog
from .player import PlayerBar
from .rename_dialog import RenameDialog
from .settings import Settings, db_path
from .tag_editor import TagEditor
from .theme import C
from .track_model import COLUMNS, COL_INDEX, FormatBadgeDelegate, TrackModel, TrackRole
from .update_dialog import UpdateDialog
from .workers import ScanThread, TaskThread

CREDIT = "MOG by B0NK3RS"


# --------------------------------------------------------------------------
# Kopfzeile mit Logo
# --------------------------------------------------------------------------
class HeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(64)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(16, 6, 10, 6)
        self.lay.setSpacing(1)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(38))
        logo.setToolTip(f"{APP_NAME} – Version {__version__}")
        self.lay.addWidget(logo)
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("VersionLabel")
        self.version.setToolTip(f"{APP_NAME} – Version {__version__}")
        self.lay.addWidget(self.version, 0, Qt.AlignBottom)
        self.lay.addSpacing(14)

    def button(self, name, text, tip, slot=None, menu=None):
        b = QToolButton()
        b.setObjectName("HeaderButton")
        b.setIcon(icon(name))
        b.setIconSize(QSize(20, 20))
        b.setText(text)
        b.setToolTip(tip)
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if text else Qt.ToolButtonIconOnly)
        if slot:
            b.clicked.connect(slot)
        if menu:
            b.setMenu(menu)
            b.setPopupMode(QToolButton.InstantPopup)
        self.lay.addWidget(b)
        return b

    def separator(self):
        f = QFrame()
        f.setObjectName("HeaderSep")
        f.setFrameShape(QFrame.VLine)
        self.lay.addWidget(f)


# --------------------------------------------------------------------------
# Detailansicht rechts
# --------------------------------------------------------------------------
class DetailsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DetailsPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(250)
        self.setMaximumWidth(380)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(6)
        self.cover = QLabel()
        self.cover.setFixedSize(200, 200)
        self.cover.setScaledContents(True)
        self.cover.setPixmap(placeholder_cover(200))
        lay.addWidget(self.cover, 0, Qt.AlignHCenter)
        lay.addSpacing(8)
        self.title = QLabel("Kein Titel ausgewählt")
        self.title.setObjectName("BigTitle")
        self.title.setWordWrap(True)
        self.artist = QLabel("")
        self.artist.setObjectName("Muted")
        self.artist.setWordWrap(True)
        lay.addWidget(self.title)
        lay.addWidget(self.artist)
        self.pending_lbl = QLabel("● Ungespeicherte Änderungen")
        self.pending_lbl.setStyleSheet(f"color: {C['accent2']}; font-size: 12px;")
        self.pending_lbl.hide()
        lay.addWidget(self.pending_lbl)
        lay.addSpacing(8)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(5)
        self.rows = {}
        for i, (k, lbl) in enumerate([("album", "Album"), ("genre", "Genre"), ("label", "Label"),
                                      ("year", "Jahr"), ("bpm", "BPM"), ("key", "Tonart"),
                                      ("format", "Format"), ("quality", "Qualität"),
                                      ("duration", "Länge"), ("size", "Größe")]):
            a = QLabel(lbl)
            a.setObjectName("Hint")
            b = QLabel("")
            b.setWordWrap(True)
            b.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(a, i, 0, Qt.AlignTop)
            self.grid.addWidget(b, i, 1)
            self.rows[k] = b
        self.grid.setColumnStretch(1, 1)
        lay.addLayout(self.grid)
        lay.addSpacing(8)
        pl = QLabel("DATEI")
        pl.setObjectName("SectionTitle")
        self.path_title = pl
        lay.addWidget(pl)
        self.path = QLabel("")
        self.path.setObjectName("Hint")
        self.path.setWordWrap(True)
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.path)
        lay.addSpacing(10)
        self.btn_edit = QPushButton(icon("tag"), " Tags bearbeiten")
        self.btn_rename = QPushButton(icon("rename"), " Dateiname bearbeiten")
        self.btn_reveal = QPushButton(icon("folder"), " Im Ordner zeigen")
        for b in (self.btn_edit, self.btn_rename, self.btn_reveal):
            lay.addWidget(b)
        lay.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        self.show_track(None)

    def _set_rows_visible(self, on):
        for i in range(self.grid.count()):
            self.grid.itemAt(i).widget().setVisible(on)
        self.path_title.setVisible(on)
        self.path.setVisible(on)

    def show_track(self, t, cover=None, count=1, pending=False):
        enabled = t is not None
        self.btn_edit.setEnabled(enabled)
        self.btn_rename.setEnabled(enabled and not t.missing)
        self.btn_reveal.setEnabled(enabled and not t.missing)
        self.pending_lbl.setVisible(bool(pending))
        if t is None:
            self.title.setText("Kein Titel ausgewählt" if count <= 1 else f"{count} Titel ausgewählt")
            self.artist.setText("")
            self.path.setText("")
            for v in self.rows.values():
                v.setText("")
            self.cover.setPixmap(placeholder_cover(200))
            self._set_rows_visible(False)
            return
        self._set_rows_visible(True)
        self.title.setText(t.display_title)
        self.artist.setText(t.display_artist + ("" if count <= 1 else f"   (+{count - 1} weitere)"))
        q = f"{round(t.bitrate / 1000)} kbps" if t.bitrate else ""
        if t.samplerate:
            q += f" · {t.samplerate / 1000:g} kHz"
        if t.bits:
            q += f" · {t.bits} Bit"
        vals = {"album": t.album, "genre": t.genre, "label": t.label, "year": t.year,
                "bpm": format_bpm(t.bpm), "key": t.key,
                "format": t.format.name + (" (verlustfrei)" if t.lossless else ""),
                "quality": q, "duration": format_duration(t.duration), "size": format_size(t.size)}
        for k, v in vals.items():
            self.rows[k].setText(v or "–")
        self.path.setText(("⚠ nicht erreichbar\n" if t.missing else "") + t.path)
        pm = QPixmap()
        if cover and pm.loadFromData(cover[0]):
            self.cover.setPixmap(pm)
        else:
            self.cover.setPixmap(placeholder_cover(200))


# --------------------------------------------------------------------------
# Hauptfenster
# --------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.s = Settings()
        self.db_path = db_path()
        self.lib = Library(self.db_path)
        self.scan_thread = None
        self._bg = []
        self._loaded = False
        self._closing_ok = False
        self.setWindowTitle(f"{APP_NAME} (MOG) – v{__version__}")
        self.resize(1440, 860)
        self.setMinimumSize(1100, 600)
        self.setAcceptDrops(True)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Kopfzeile
        self.header = h = HeaderBar()
        h.button("drive", "Laufwerk", "Ganzen Datenträger einlesen (z. B. externe SSD)", self.import_drive)
        h.button("folder", "Ordner", "Ordner einlesen (Strg+O)", self.import_folder)
        h.button("file", "Dateien", "Einzelne Dateien einlesen", self.import_files)
        lib_menu = QMenu(self)
        lib_menu.addAction(icon("refresh"), "Alle Quellen aktualisieren (nur Änderungen)", self.rescan_all)
        lib_menu.addAction(icon("unlink"), "Erreichbarkeit aller Dateien prüfen", self.check_all_missing)
        lib_menu.addSeparator()
        lib_menu.addAction(icon("undo"), "Ungespeicherte Änderungen verwerfen …", lambda: self.discard_pending())
        lib_menu.addSeparator()
        lib_menu.addAction(icon("eraser", C["bad"]), "Bibliothek leeren …", self.clear_library)
        h.button("library", "Bibliothek", "Quellen aktualisieren, Bibliothek leeren …", menu=lib_menu)
        h.separator()
        h.button("duplicates", "Duplikate", "Doppelte Titel finden und löschen (Strg+D)", self.open_duplicates)
        h.button("tag", "Tags", "Tags der markierten Titel bearbeiten (Strg+E)", self.edit_tags)
        h.button("rename", "Umbenennen", "Dateinamen der markierten Titel bearbeiten (F2)", self.rename_files)
        h.button("globe", "Online", "Tags aus Online-Datenbanken übernehmen (Strg+K)", self.open_online)
        h.button("pulse", "BPM", "BPM der markierten Titel analysieren", self.analyze_bpm)
        h.button("convert", "Konvertieren", "Markierte Titel mit ffmpeg umwandeln", self.open_convert)
        h.lay.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("SearchField")
        self.search.setPlaceholderText("Suchen …")
        self.search.setToolTip("Sucht in Artist, Titel, Album, Genre, Label, Tonart und Dateipfad (Strg+F)")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", C["text3"]), QLineEdit.LeadingPosition)
        self.search.setStyleSheet("QLineEdit#SearchField { padding-left: 6px; min-width: 150px; }")
        self.search.setMaximumWidth(300)
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h.lay.addWidget(self.search, 2)
        h.lay.addSpacing(6)
        self.btn_save = h.button("save", "Speichern", "", lambda: self.save_pending())
        h.separator()
        gear = QMenu(self)
        gear.addAction(icon("settings"), "Einstellungen …", self.open_settings)
        gear.addAction(icon("download"), "Nach Updates suchen …", lambda: self.check_updates(manual=True))
        gear.addAction(icon("file"), "Diagnose-Protokoll zeigen", self.show_log)
        gear.addSeparator()
        gear.addAction(icon("info"), f"Über {APP_NAME} …", self.show_about)
        h.button("settings", "Extras", "Einstellungen, Updates, Info", menu=gear)
        h.button("power", "Beenden", "Programm beenden (Strg+Q)", self.close)
        root.addWidget(h)

        # --- Mitte
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)
        self.splitter = split
        self.sidebar = self._build_sidebar()
        split.addWidget(self.sidebar)

        self.model = TrackModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setItemDelegateForColumn(COL_INDEX["fmt"], FormatBadgeDelegate(self.table))
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        hh = self.table.horizontalHeader()
        hh.setSectionsMovable(True)          # Spalten per Drag & Drop verschieben
        hh.setFirstSectionMovable(True)      # auch die erste Spalte (z. B. Titel vor Artist)
        hh.setSectionsClickable(True)
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.Interactive)   # alle Breiten frei veränderbar
        hh.setStretchLastSection(False)
        hh.setMinimumSectionSize(36)
        hh.setContextMenuPolicy(Qt.CustomContextMenu)
        hh.customContextMenuRequested.connect(self._header_menu)
        for i, (_k, _l, vis, w, _a) in enumerate(COLUMNS):
            self.table.setColumnWidth(i, w)
            self.table.setColumnHidden(i, not vis)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(COL_INDEX["artist"], Qt.AscendingOrder)

        self.empty = self._build_empty_state()
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.table)
        cl.addWidget(self.empty)
        split.addWidget(center)
        self.details = DetailsPanel()
        split.addWidget(self.details)
        split.setStretchFactor(1, 1)
        split.setSizes([230, 900, 290])
        root.addWidget(split, 1)

        # --- Player
        self.player = PlayerBar()
        root.addWidget(self.player)

        # --- Statuszeile
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.lbl_count = QLabel("")
        sb.addWidget(self.lbl_count, 1)
        self.scan_label = QLabel("")
        self.scan_bar = QProgressBar()
        self.scan_bar.setFixedWidth(220)
        self.scan_cancel = QPushButton("Abbrechen")
        self.scan_cancel.setFixedHeight(22)
        self.scan_cancel.clicked.connect(self._cancel_scan)
        for w in (self.scan_label, self.scan_bar, self.scan_cancel):
            sb.addPermanentWidget(w)
            w.hide()
        credit = QLabel(CREDIT)
        credit.setObjectName("Credit")
        sb.addPermanentWidget(credit)

        # --- Signale
        self._search_timer = QTimer(self, singleShot=True, interval=250)
        self._search_timer.timeout.connect(self._apply_search)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self.table.doubleClicked.connect(lambda idx: self.play(idx.data(TrackRole)))
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        self.model.modelReset.connect(self._update_counts)
        self.model.rowsInserted.connect(self._update_counts)
        self.player.request_next.connect(lambda: self._play_relative(1))
        self.player.request_prev.connect(lambda: self._play_relative(-1))
        self.player.now_playing.connect(lambda t: self.model.set_playing(t.id if t else None))
        self.details.btn_edit.clicked.connect(self.edit_tags)
        self.details.btn_rename.clicked.connect(self.rename_files)
        self.details.btn_reveal.clicked.connect(self.reveal_selected)
        self.table.installEventFilter(self)

        for seq, slot in (("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())),
                          ("Ctrl+E", self.edit_tags), ("Ctrl+O", self.import_folder),
                          ("Ctrl+D", self.open_duplicates), ("Ctrl+K", self.open_online),
                          ("F2", self.rename_files), ("Ctrl+S", lambda: self.save_pending())):
            QShortcut(QKeySequence(seq), self, activated=slot)
        QShortcut(QKeySequence.Quit, self, activated=self.close)

        self._restore_state()
        self.player.set_device_id(self.s.get("audio/device"))
        self._refresh_pending()
        if self.s.get("startup/load_library"):
            self.load_library()
        else:
            self._update_counts()
            self._rebuild_sidebar()
        if self.s.get("update/auto"):
            QTimer.singleShot(3000, lambda: self.check_updates(manual=False))

    # ------------------------------------------------------------------ UI-Aufbau
    def _build_sidebar(self):
        w = QWidget()
        w.setObjectName("Sidebar")
        w.setAttribute(Qt.WA_StyledBackground, True)
        w.setMinimumWidth(200)
        w.setMaximumWidth(340)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 12, 8, 8)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setIndentation(10)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.setRootIsDecorated(False)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._sidebar_menu)
        self.tree.itemSelectionChanged.connect(self._on_sidebar)
        lay.addWidget(self.tree)
        return w

    def _section(self, text):
        it = QTreeWidgetItem([text])
        it.setFlags(Qt.ItemIsEnabled)
        f = it.font(0)
        f.setPointSizeF(max(7.0, f.pointSizeF() - 2))
        f.setBold(True)
        f.setLetterSpacing(QFont.PercentageSpacing, 110)
        it.setFont(0, f)
        it.setForeground(0, Qt.gray)
        return it

    def _rebuild_sidebar(self):
        sel = self._sidebar_key()
        self.tree.blockSignals(True)
        self.tree.clear()
        roots = self.lib.roots()
        counts, per_root = self.model.counts(roots)
        lib = self._section("BIBLIOTHEK")
        self.tree.addTopLevelItem(lib)
        self._add_view(lib, "library", "Alle Titel", ("view", "all"), len(self.model.all))
        if roots:
            src = self._section("QUELLEN")
            self.tree.addTopLevelItem(src)
            for r in roots:
                name = os.path.basename(r.rstrip("/\\")) or r
                is_drive = len(r) <= 3 or (r.startswith("/Volumes/") and r.count("/") == 2)
                it = self._add_view(src, "drive" if is_drive else "folder", name, ("root", r), per_root.get(r, 0))
                it.setToolTip(0, r)
                if not os.path.exists(r):
                    it.setForeground(0, Qt.darkGray)
                    it.setToolTip(0, r + "\n(nicht verbunden)")
        smart = self._section("INTELLIGENTE ANSICHTEN")
        self.tree.addTopLevelItem(smart)
        for key, ic, text in (("pending", "save", "Ungespeichert"),
                              ("lossless", "lossless", "Verlustfrei"), ("lowq", "low", "Niedrige Qualität"),
                              ("nobpm", "nobpm", "Ohne BPM"), ("notags", "notags", "Fehlende Tags"),
                              ("missing", "unlink", "Nicht erreichbar")):
            it = self._add_view(smart, ic, text, ("view", key), counts.get(key, 0))
            if key == "pending" and counts.get(key):
                it.setForeground(1, QColor(C["accent2"]))
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setExpanded(True)
        self.tree.blockSignals(False)
        self._select_sidebar(sel or ("view", "all"))

    def _add_view(self, parent, ic, text, key, count):
        it = QTreeWidgetItem([text, f"{count:,}".replace(",", ".") if count else ""])
        it.setIcon(0, icon(ic, C["text2"], "#FFFFFF"))
        it.setData(0, Qt.UserRole, key)
        it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        it.setForeground(1, QColor(C["text3"]))
        parent.addChild(it)
        return it

    def _sidebar_key(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def _select_sidebar(self, key):
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                top = self.tree.topLevelItem(i)
                for j in range(top.childCount()):
                    c = top.child(j)
                    if c.data(0, Qt.UserRole) == key:
                        self.tree.setCurrentItem(c)
                        return
            if self.tree.topLevelItemCount() and self.tree.topLevelItem(0).childCount():
                self.tree.setCurrentItem(self.tree.topLevelItem(0).child(0))
        finally:
            self.tree.blockSignals(False)

    def _build_empty_state(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch()
        img = QLabel()
        from mog.core.paths import resource
        img.setPixmap(svg_pixmap(resource("mog_icon.svg"), 120, 120))
        img.setAlignment(Qt.AlignCenter)
        lay.addWidget(img)
        self.empty_title = QLabel("Willkommen bei MusicOrganizer")
        self.empty_title.setObjectName("BigTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_title)
        self.empty_hint = QLabel("Lies deine Musiksammlung ein – einen ganzen Datenträger, einzelne Ordner "
                                 "oder Dateien.\nDu kannst Ordner und Dateien auch einfach hierher ziehen.")
        self.empty_hint.setObjectName("Muted")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_hint)
        row = QHBoxLayout()
        row.addStretch()
        self.btn_load_lib = QPushButton(icon("library", "#FFFFFF"), "  Gespeicherte Bibliothek laden")
        self.btn_load_lib.setObjectName("Primary")
        self.btn_load_lib.setMinimumHeight(36)
        self.btn_load_lib.clicked.connect(self.load_library)
        row.addWidget(self.btn_load_lib)
        for name, text, slot in (("drive", "  Laufwerk wählen", self.import_drive),
                                 ("folder", "  Ordner wählen", self.import_folder),
                                 ("file", "  Dateien wählen", self.import_files)):
            b = QPushButton(icon(name), text)
            b.setIconSize(QSize(18, 18))
            b.setMinimumHeight(36)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        lay.addSpacing(12)
        lay.addLayout(row)
        lay.addStretch(1)
        w.setObjectName("EmptyState")
        w.setAttribute(Qt.WA_StyledBackground, True)
        return w

    # ------------------------------------------------------------------ Bibliothek
    def load_library(self):
        """Lädt die gespeicherte Bibliothek im Hintergrund (bleibt bei großen Archiven bedienbar)."""
        n = self.lib.count()
        if n == 0:
            self._loaded = True
            self.model.set_tracks([])
            self._rebuild_sidebar()
            return
        self.empty_title.setText("Bibliothek wird geladen …")
        self.empty_hint.setText(f"{n:,} Titel".replace(",", "."))
        self.btn_load_lib.hide()
        self.table.hide()
        self.empty.show()
        dbp = self.db_path

        def job(progress, cancel, _item):
            lib = Library(dbp)
            try:
                return lib.load_all()
            finally:
                lib.close()

        th = TaskThread(job, self)
        th.done.connect(self._library_loaded)
        th.failed.connect(lambda e: QMessageBox.warning(self, "Bibliothek", e))
        self._bg.append(th)
        th.start()

    def _library_loaded(self, tracks):
        t0 = time.time()
        self._loaded = True
        self.model.set_tracks(tracks)
        self._refresh_pending()
        self._rebuild_sidebar()
        self.empty_title.setText("Willkommen bei MusicOrganizer")
        self.empty_hint.setText("Lies deine Musiksammlung ein – einen ganzen Datenträger, einzelne Ordner "
                                "oder Dateien.\nDu kannst Ordner und Dateien auch einfach hierher ziehen.")
        self._update_counts()
        self.statusBar().showMessage(f"Bibliothek geladen ({time.time() - t0:.1f} s)", 4000)
        QTimer.singleShot(300, self._quick_check_bg)

    def _update_counts(self, *_):
        n_all = len(self.model.all)
        has_db = n_all > 0 or (not self._loaded and self.lib.count() > 0)
        self.table.setVisible(n_all > 0)
        self.empty.setVisible(n_all == 0)
        self.btn_load_lib.setVisible(not self._loaded and has_db)
        if n_all == 0:
            self.lbl_count.setText("Bibliothek nicht geladen" if (not self._loaded and has_db)
                                   else "Bibliothek ist leer")
            return
        n, dur, size = self.model.stats()
        txt = f"{n:,} Titel".replace(",", ".")
        if n != n_all:
            txt += f" von {n_all:,}".replace(",", ".")
        self.lbl_count.setText(f"{txt} · {format_duration(dur)} · {format_size(size)}")

    def _apply_search(self):
        self.model.set_search(self.search.text())
        self._update_counts()

    def _on_sidebar(self):
        key = self._sidebar_key()
        if not key:
            return
        kind, val = key
        if kind == "root":
            self.model.set_view("all", root=val)
        else:
            self.model.set_view(val)
        self._update_counts()

    def selected_tracks(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.track_at(r) for r in rows if self.model.track_at(r) is not None]

    def cover_for(self, t):
        """Cover eines Titels – ein vorgemerktes (noch nicht gespeichertes) hat Vorrang."""
        if t is None:
            return None
        is_set, cov = self.lib.pending_cover(t.id)
        if is_set:
            return cov
        return tagio.read_cover(t.path) if not t.missing else None

    def _on_selection(self, *_):
        ts = self.selected_tracks()
        if not ts:
            self.details.show_track(None)
            return
        t = ts[0]
        self.details.show_track(t, self.cover_for(t), len(ts), t.id in self.model.pending)

    def _sync_missing_flags(self):
        changed = False
        for tid, miss in self.lib.con.execute("SELECT id, missing FROM tracks"):
            t = self.model.by_id.get(tid)
            if t is not None and t.missing != bool(miss):
                t.missing = bool(miss)
                changed = True
        if changed:
            self.model.rebuild()
            self._rebuild_sidebar()

    # ------------------------------------------------------------------ Vorgemerkte Änderungen
    def _refresh_pending(self):
        self.model.set_pending(self.lib.pending_map())
        n = len(self.model.pending)
        b = self.btn_save
        b.setEnabled(n > 0)
        b.setText(f"Speichern ({n})" if n else "Speichern")
        b.setToolTip(f"{n} Titel mit ungespeicherten Tag-Änderungen jetzt in die Dateien schreiben (Strg+S)"
                     if n else "Keine ungespeicherten Änderungen")
        b.setIcon(icon("save", C["accent2"] if n else "#C9CAD6"))
        b.setStyleSheet(f"QToolButton#HeaderButton {{ color: {C['accent2']}; }}" if n else "")

    def stage_changes(self, changes):
        """changes: Liste (track, werte, cover, cover_gesetzt). Merkt vor und zeigt sofort an."""
        updated = []
        for t, vals, cover, cover_set in changes:
            if not vals and not cover_set:
                continue
            nt = self.lib.stage(t.id, vals, cover, cover_set)
            if nt is not None:
                updated.append(nt)
        if not updated:
            return 0
        self.model.upsert(updated)
        self._refresh_pending()
        self._rebuild_sidebar()
        self._on_selection()
        self.statusBar().showMessage(
            f"{len(updated)} Titel geändert – noch nicht gespeichert (Speichern oder beim Beenden).", 6000)
        return len(updated)

    def save_pending(self, ids=None):
        """Schreibt vorgemerkte Änderungen in die Dateien. Gibt die Fehlerliste zurück.

        Knöpfe/Menüs übergeben beim Klicken einen Ja/Nein-Wert ("checked") – der zählt nicht als ID-Liste.
        """
        ids = list(ids) if isinstance(ids, (list, tuple, set)) else self.lib.pending_ids()
        if not ids:
            return []
        playing = self.player.track
        if playing is not None and playing.id in ids:
            self.player.release_file(playing.path)
        dbp = self.db_path

        def job(progress, cancel, _item):
            return pendingmod.commit(dbp, ids, progress, cancel)

        res = run_task(self, f"Speichere Änderungen in {len(ids)} Datei(en) …", job)
        if res is None:
            self._refresh_pending()
            return [("", "Abgebrochen")]
        updated, errors = res
        self.model.upsert(updated)
        self._refresh_pending()
        self._rebuild_sidebar()
        self._on_selection()
        self.statusBar().showMessage(f"Tags von {len(updated)} Datei(en) gespeichert.", 6000)
        if errors:
            QMessageBox.warning(self, "Nicht alles gespeichert",
                                f"{len(errors)} Datei(en) konnten nicht geschrieben werden – die Änderungen "
                                "bleiben vorgemerkt:\n\n" + "\n".join(
                                    f"{os.path.basename(p)}: {m}" for p, m in errors[:15]))
        return errors

    def discard_pending(self, ids=None, ask=True):
        ids = list(ids) if isinstance(ids, (list, tuple, set)) else self.lib.pending_ids()
        if not ids:
            if ask:
                QMessageBox.information(self, "Änderungen verwerfen", "Es gibt keine ungespeicherten Änderungen.")
            return
        if ask and QMessageBox.question(
                self, "Änderungen verwerfen",
                f"Ungespeicherte Tag-Änderungen an {len(ids)} Titel(n) verwerfen?\n"
                "Die Dateien bleiben unverändert.") != QMessageBox.Yes:
            return
        self.lib.discard_pending(ids)
        self.model.upsert([t for t in (self.lib.get(i) for i in ids) if t is not None])
        self._refresh_pending()
        self._rebuild_sidebar()
        self._on_selection()

    # ------------------------------------------------------------------ Einlesen
    def import_drive(self):
        dlg = VolumeDialog(self)
        if dlg.exec() and dlg.selected_root():
            root = dlg.selected_root()
            if root in ("/", "C:/", "C:\\") and QMessageBox.question(
                    self, "Systemlaufwerk", "Das Systemlaufwerk einzulesen kann sehr lange dauern und "
                    "findet auch System-Sounds. Trotzdem fortfahren?") != QMessageBox.Yes:
                return
            self.start_scan([root])

    def import_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Ordner einlesen", self.s.value("last_dir", ""))
        if d:
            self.s.set("last_dir", d)
            self.start_scan([d])

    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Dateien einlesen", self.s.value("last_dir", ""),
                                                dialog_filter())
        if files:
            self.s.set("last_dir", os.path.dirname(files[0]))
            self.start_scan(files)

    def rescan_all(self):
        roots = [r for r in self.lib.roots() if os.path.exists(r)]
        if not roots:
            QMessageBox.information(self, "Aktualisieren", "Keine verbundenen Quellen vorhanden.")
            return
        self.start_scan(roots)

    def start_scan(self, sources, force=False):
        if self.scan_thread and self.scan_thread.isRunning():
            QMessageBox.information(self, "Einlesen", "Es läuft bereits ein Einlesevorgang.")
            return
        if not self._loaded and self.lib.count() > 0:
            # vorhandene Bibliothek zuerst laden, damit nichts doppelt angezeigt wird
            self._pending_scan = (sources, force)
            self.load_library()
            QTimer.singleShot(200, self._start_scan_when_loaded)
            return
        th = ScanThread(sources, self.db_path, force, self.s.get("scan/skip_hidden"), self)
        th.status.connect(self.scan_label.setText)
        th.progress.connect(self._scan_progress)
        th.batch.connect(lambda ts: self.model.upsert(ts, live=True))
        th.done.connect(self._scan_done)
        self.scan_thread = th
        self._loaded = True
        self.scan_label.setText("Einlesen …")
        self.scan_bar.setRange(0, 0)
        for w in (self.scan_label, self.scan_bar, self.scan_cancel):
            w.show()
        th.start()

    def _start_scan_when_loaded(self):
        if not self._loaded:
            QTimer.singleShot(200, self._start_scan_when_loaded)
            return
        sources, force = self._pending_scan
        self.start_scan(sources, force)

    def _scan_progress(self, done, total):
        self.scan_bar.setRange(0, total)
        self.scan_bar.setValue(done)
        self.scan_label.setText(f"Lese Tags … {done:,} / {total:,}".replace(",", "."))

    def _cancel_scan(self):
        if self.scan_thread:
            self.scan_thread.cancel()
            self.scan_label.setText("Wird abgebrochen …")

    def _scan_done(self, res):
        for w in (self.scan_label, self.scan_bar, self.scan_cancel):
            w.hide()
        for tid in res.missing_ids:
            t = self.model.by_id.get(tid)
            if t:
                t.missing = True
        for tid in res.restored_ids:
            t = self.model.by_id.get(tid)
            if t:
                t.missing = False
        self.model.rebuild()
        self._refresh_pending()
        self._rebuild_sidebar()
        parts = [f"{res.total:,} Dateien gefunden".replace(",", ".")]
        if res.new:
            parts.append(f"{res.new} neu")
        if res.updated:
            parts.append(f"{res.updated} aktualisiert")
        if res.unchanged:
            parts.append(f"{res.unchanged:,} unverändert".replace(",", "."))
        if res.missing_ids:
            parts.append(f"{len(res.missing_ids)} nicht mehr vorhanden")
        msg = ", ".join(parts)
        if res.cancelled:
            msg = "Abgebrochen – " + msg
        self.statusBar().showMessage(msg, 12000)
        if res.errors:
            lines = "\n".join(f"{os.path.basename(p)}: {e}" for p, e in res.errors[:20])
            QMessageBox.warning(self, "Einlesen abgeschlossen",
                                f"{msg}\n\n{len(res.errors)} Datei(en) konnten nicht gelesen werden:\n\n{lines}"
                                + ("\n…" if len(res.errors) > 20 else ""))

    def _quick_check_bg(self):
        """Beim Start: nur prüfen, ob die Quellen (z. B. die SSD) verbunden sind – kein Einlesen."""
        if not self.model.all:
            return
        dbp = self.db_path
        th = TaskThread(lambda p, c, i: scanner.quick_check(dbp), self)
        th.done.connect(lambda changed: changed and self._sync_missing_flags())
        self._bg.append(th)
        th.start()

    def check_all_missing(self):
        if not self.model.all:
            return
        dbp = self.db_path
        res = run_task(self, "Prüfe Erreichbarkeit aller Dateien …",
                       lambda p, c, i: scanner.check_missing(dbp))
        if res is not None:
            self._sync_missing_flags()
            gone, back = res
            self.statusBar().showMessage(f"{len(gone)} nicht erreichbar, {len(back)} wieder da.", 8000)

    def clear_library(self):
        n = len(self.model.all) or self.lib.count()
        if n == 0:
            QMessageBox.information(self, "Bibliothek leeren", "Die Bibliothek ist bereits leer.")
            return
        pend = len(self.lib.pending_ids())
        msg = (f"Alle {n:,} Titel und alle Quellen aus MusicOrganizer entfernen?\n\n".replace(",", ".")
               + "Die Musikdateien auf deinen Datenträgern bleiben unverändert. Beim nächsten Start ist "
                 "die Liste leer – du kannst danach gezielt neu einlesen.")
        if pend:
            msg += f"\n\n⚠ {pend} Titel haben ungespeicherte Tag-Änderungen – diese gehen verloren."
        box = QMessageBox(QMessageBox.Warning, "Bibliothek leeren", msg, QMessageBox.Cancel, self)
        go = box.addButton("Bibliothek leeren", QMessageBox.DestructiveRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.scan_thread.wait(10000)
        self.player.stop()
        if self.player.track:
            self.player.release_file(self.player.track.path)
        self.lib.clear_all()
        self._loaded = True
        self.model.set_tracks([])
        self._refresh_pending()
        self._rebuild_sidebar()
        self._update_counts()
        self.statusBar().showMessage("Bibliothek geleert.", 6000)

    # ------------------------------------------------------------------ Drag & Drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.start_scan(paths)

    # ------------------------------------------------------------------ Wiedergabe
    def play(self, t):
        if t is None:
            return
        if t.missing or not os.path.exists(t.path):
            self.statusBar().showMessage("Datei nicht erreichbar – ist der Datenträger verbunden?", 6000)
            return
        self.player.play_track(t, self.cover_for(t))

    def _play_relative(self, step):
        order = self.model.view
        if not order:
            return
        cur = self.player.track
        r = self.model.row_for_id(cur.id) if cur is not None else None
        if r is None:
            sel = self.selected_tracks()
            nxt = sel[0] if sel else order[0]
        else:
            i = r + step
            if i < 0 or i >= len(order):
                self.player.stop()
                return
            nxt = order[i]
        self.play(nxt)
        row = self.model.row_for_id(nxt.id)
        if row is not None:
            self.table.scrollTo(self.model.index(row, 0))

    def eventFilter(self, obj, ev):
        if obj is self.table and ev.type() == QEvent.KeyPress:
            k = ev.key()
            if k == Qt.Key_Space:
                if self.player.track is None:
                    ts = self.selected_tracks()
                    if ts:
                        self.play(ts[0])
                else:
                    self.player.toggle()
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                ts = self.selected_tracks()
                if ts:
                    self.play(ts[0])
                return True
            if k in (Qt.Key_Delete, Qt.Key_Backspace) and ev.modifiers() in (Qt.NoModifier, Qt.ControlModifier):
                self.delete_selected()
                return True
            if k == Qt.Key_Right and ev.modifiers() & Qt.AltModifier:
                self.player.seek_relative(10)
                return True
            if k == Qt.Key_Left and ev.modifiers() & Qt.AltModifier:
                self.player.seek_relative(-10)
                return True
        return super().eventFilter(obj, ev)

    # ------------------------------------------------------------------ Menüs
    def _context_menu(self, pos):
        ts = self.selected_tracks()
        if not ts:
            return
        m = QMenu(self)
        m.addAction(icon("play"), "Abspielen", lambda: self.play(ts[0]))
        m.addSeparator()
        m.addAction(icon("tag"), "Tags bearbeiten …\tStrg+E", self.edit_tags)
        m.addAction(icon("rename"), "Dateiname bearbeiten …\tF2", self.rename_files)
        m.addAction(icon("globe"), "Tags online suchen …\tStrg+K", self.open_online)
        m.addAction(icon("pulse"), "BPM analysieren", self.analyze_bpm)
        m.addAction(icon("convert"), "Konvertieren …", self.open_convert)
        m.addAction(icon("duplicates"), "Duplikate in Auswahl suchen …", lambda: self.open_duplicates(ts))
        pend = [t.id for t in ts if t.id in self.model.pending]
        if pend:
            m.addSeparator()
            m.addAction(icon("save", C["accent2"]), f"Änderungen speichern ({len(pend)})",
                        lambda: self.save_pending(pend))
            m.addAction(icon("undo"), "Änderungen verwerfen", lambda: self.discard_pending(pend, ask=False))
        m.addSeparator()
        a = m.addAction(icon("folder"), "Im Ordner zeigen", self.reveal_selected)
        a.setEnabled(not ts[0].missing)
        m.addSeparator()
        m.addAction(icon("x"), "Aus Liste entfernen (Datei bleibt)", self.remove_from_list)
        m.addAction(icon("trash", C["bad"]), "Von Datenträger löschen …\tEntf", self.delete_selected)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _header_menu(self, pos):
        hh = self.table.horizontalHeader()
        clicked = hh.logicalIndexAt(pos)
        m = QMenu(self)
        if clicked >= 0:
            vis = hh.visualIndex(clicked)
            name = COLUMNS[clicked][1]
            a = m.addAction(f"„{name}“ nach links verschieben", lambda: self._move_column(clicked, -1))
            a.setEnabled(vis > 0)
            a = m.addAction(f"„{name}“ nach rechts verschieben", lambda: self._move_column(clicked, 1))
            a.setEnabled(vis < hh.count() - 1)
            m.addAction(f"Breite von „{name}“ an Inhalt anpassen",
                        lambda: self.table.resizeColumnToContents(clicked))
            m.addSeparator()
        sub = m.addMenu("Spalten ein-/ausblenden")
        for i, (k, label, *_r) in enumerate(COLUMNS):
            a = QAction(label, sub, checkable=True)
            a.setChecked(not self.table.isColumnHidden(i))
            a.setEnabled(k not in ("artist", "title"))
            a.toggled.connect(lambda on, col=i: self.table.setColumnHidden(col, not on))
            sub.addAction(a)
        m.addSeparator()
        m.addAction("Spalten zurücksetzen", self._reset_columns)
        m.exec(hh.mapToGlobal(pos))

    def _move_column(self, logical, step):
        """Verschiebt eine Spalte um eine sichtbare Position (ausgeblendete werden übersprungen)."""
        hh = self.table.horizontalHeader()
        vis = hh.visualIndex(logical)
        target = vis + step
        while 0 <= target < hh.count() and hh.isSectionHidden(hh.logicalIndex(target)):
            target += step
        if 0 <= target < hh.count():
            hh.moveSection(vis, target)

    def _reset_columns(self):
        hh = self.table.horizontalHeader()
        for i, (_k, _l, vis, w, _a) in enumerate(COLUMNS):
            hh.moveSection(hh.visualIndex(i), i)
            self.table.setColumnHidden(i, not vis)
            self.table.setColumnWidth(i, w)

    def _sidebar_menu(self, pos):
        it = self.tree.itemAt(pos)
        if not it or not it.data(0, Qt.UserRole):
            return
        kind, val = it.data(0, Qt.UserRole)
        m = QMenu(self)
        if kind == "root":
            m.addAction(icon("refresh"), "Neu einlesen (nur Änderungen)", lambda: self.start_scan([val]))
            m.addAction(icon("refresh"), "Komplett neu einlesen (alle Tags)", lambda: self.start_scan([val], True))
            m.addAction(icon("folder"), "Im Ordner zeigen", lambda: fileops.reveal(val))
            m.addSeparator()
            m.addAction(icon("x"), "Quelle aus Bibliothek entfernen (Dateien bleiben)",
                        lambda: self._remove_root(val))
        elif val == "all":
            m.addAction(icon("refresh"), "Alle Quellen aktualisieren", self.rescan_all)
            m.addSeparator()
            m.addAction(icon("eraser", C["bad"]), "Bibliothek leeren …", self.clear_library)
        elif val == "missing":
            m.addAction(icon("refresh"), "Erreichbarkeit aller Dateien prüfen", self.check_all_missing)
            m.addAction(icon("x"), "Nicht erreichbare Titel aus Liste entfernen", self._purge_missing)
        elif val == "pending":
            m.addAction(icon("save"), "Alle Änderungen speichern", lambda: self.save_pending())
            m.addAction(icon("undo"), "Alle Änderungen verwerfen …", lambda: self.discard_pending())
        else:
            return
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _remove_root(self, root):
        if QMessageBox.question(self, "Quelle entfernen",
                                f"„{root}“ und alle zugehörigen Titel aus der Bibliothek entfernen?\n"
                                "Die Dateien auf dem Datenträger bleiben unverändert.") != QMessageBox.Yes:
            return
        ids = self.lib.delete_under(root)
        self.lib.remove_root(root)
        self.model.remove_ids(ids)
        self._refresh_pending()
        self._rebuild_sidebar()
        self._select_sidebar(("view", "all"))
        self._on_sidebar()

    def _purge_missing(self):
        ids = [t.id for t in self.model.all if t.missing]
        if ids and QMessageBox.question(self, "Aufräumen", f"{len(ids)} nicht erreichbare Titel aus der "
                                        "Liste entfernen?") == QMessageBox.Yes:
            self.lib.delete(ids)
            self.model.remove_ids(ids)
            self._refresh_pending()
            self._rebuild_sidebar()

    # ------------------------------------------------------------------ Aktionen
    def _need_selection(self, title):
        ts = self.selected_tracks()
        if not ts:
            QMessageBox.information(self, title, "Bitte zuerst einen oder mehrere Titel in der Liste markieren.")
        return ts

    def edit_tags(self):
        ts = [t for t in self._need_selection("Tags bearbeiten") if not t.missing]
        if not ts:
            return
        dlg = TagEditor(ts, self.cover_for, self)
        if dlg.exec() and dlg.changes:
            self.stage_changes(dlg.changes)

    def rename_files(self):
        ts = [t for t in self._need_selection("Dateiname bearbeiten") if not t.missing]
        if not ts:
            return
        dlg = RenameDialog(ts, self.s, self)
        if not dlg.exec() or not dlg.renames:
            return
        ok, errors, stale_all = 0, [], []
        for t, stem in dlg.renames:
            self.player.release_file(t.path)
            success, new_path, msg = fileops.rename_file(t.path, stem)
            if success and new_path != t.path:
                stale_all += self.lib.rename_path(t.id, new_path)
                t.path = new_path
                self.model.upsert([t])
                ok += 1
            elif not success:
                errors.append(f"{t.filename}: {msg}")
        if stale_all:
            self.model.remove_ids(stale_all)
        self._on_selection()
        self.statusBar().showMessage(f"{ok} Datei(en) umbenannt.", 6000)
        if errors:
            QMessageBox.warning(self, "Umbenennen", "Nicht umbenannt:\n\n" + "\n".join(errors[:15]))

    def open_online(self):
        ts = self._need_selection("Tags online suchen")
        if not ts:
            return
        dlg = OnlineTagDialog(ts, self.s, self)
        dlg.staged.connect(lambda t, v, c, cs: self.stage_changes([(t, v, c, cs)]))
        dlg.exec()

    def analyze_bpm(self):
        ts = [t for t in self._need_selection("BPM analysieren") if not t.missing]
        if not ts:
            return
        ff = encoder.find_ffmpeg(self.s.get("tools/ffmpeg") or None)
        if not ff:
            QMessageBox.warning(self, "BPM", "ffmpeg wurde nicht gefunden (Einstellungen → Encoder).")
            return
        with_bpm = [t for t in ts if t.bpm]
        overwrite = False
        if with_bpm:
            r = QMessageBox.question(self, "BPM analysieren",
                                     f"{len(with_bpm)} von {len(ts)} Titeln haben bereits einen BPM-Wert.\n\n"
                                     "Vorhandene Werte überschreiben?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
            if r == QMessageBox.Cancel:
                return
            overwrite = r == QMessageBox.Yes
        todo = ts if overwrite else [t for t in ts if not t.bpm]
        if not todo:
            return
        lo, hi = bpmmod.BPM_RANGES.get(self.s.get("bpm/range"), (78, 155))
        rnd = self.s.get("bpm/round")
        items = [(t.id, t.path, t.duration, t.display_artist, t.display_title) for t in todo]

        def job(progress, cancel, _item):
            out = []
            for i, (tid, path, dur, a, ti) in enumerate(items, 1):
                if cancel.is_set():
                    break
                progress(i - 1, len(items), f"{a} – {ti}")
                try:
                    val, _conf = bpmmod.analyze_file(ff, path, dur, lo, hi, rnd)
                    out.append((tid, val, "" if val else "kein Tempo erkannt"))
                except Exception as e:
                    out.append((tid, None, str(e)))
            progress(len(items), len(items), "")
            return out

        res = run_task(self, "Analysiere BPM …", job)
        if res is None:
            return
        changes = []
        for tid, val, _e in res:
            t = self.model.by_id.get(tid)
            if t and val:
                txt = str(int(round(val))) if rnd else f"{val:.1f}"
                changes.append((t, {"bpm": txt}, None, False))
        n = self.stage_changes(changes) if changes else 0
        fails = len(res) - len(changes)
        self.statusBar().showMessage(
            f"BPM für {n} Titel ermittelt – wird beim Speichern bzw. Beenden in die Dateien geschrieben."
            + (f" {fails} ohne Ergebnis." if fails else ""), 10000)

    def open_convert(self):
        ts = self._need_selection("Konvertieren")
        if not ts:
            return
        pend = [t for t in ts if t.id in self.model.pending]
        if pend and QMessageBox.question(
                self, "Konvertieren", f"{len(pend)} der Titel haben ungespeicherte Tag-Änderungen. "
                "Jetzt speichern, damit sie in die konvertierten Dateien übernommen werden?") == QMessageBox.Yes:
            self.save_pending([t.id for t in pend])
        dlg = ConvertDialog(ts, self.s, self)
        if dlg.exec() and dlg.results:
            new_files = [d for _t, d, _e in dlg.results if d]
            if dlg.originals_deleted:
                gone = [t.id for t, d, e in dlg.results if d and not e]
                self.lib.delete(gone)
                self.model.remove_ids(gone)
            if dlg.add_to_library and new_files:
                self.start_scan(new_files)

    def open_duplicates(self, tracks=None):
        tracks = tracks if isinstance(tracks, list) else self.model.tracks_in_order()
        if not tracks:
            QMessageBox.information(self, "Duplikate", "Die Bibliothek ist leer.")
            return
        dlg = DuplicatesDialog(tracks, self.s, self.db_path, self)
        dlg.play_requested.connect(self.play)
        dlg.delete_requested.connect(lambda ts: dlg.remove_deleted(self._delete_tracks(ts, ask=True)))
        dlg.exec()

    def reveal_selected(self):
        ts = self.selected_tracks()
        if ts:
            fileops.reveal(ts[0].path)

    def remove_from_list(self):
        ts = self.selected_tracks()
        if not ts:
            return
        self.lib.delete([t.id for t in ts])
        self.model.remove_ids([t.id for t in ts])
        self._refresh_pending()
        self._rebuild_sidebar()
        self.statusBar().showMessage(f"{len(ts)} Titel aus der Liste entfernt (Dateien unverändert).", 6000)

    def delete_selected(self):
        ts = self.selected_tracks()
        if ts:
            self._delete_tracks(ts, ask=True)

    def _delete_tracks(self, tracks, ask=True):
        """Löscht Dateien vom Datenträger. Gibt Liste gelöschter IDs zurück."""
        permanent = self.s.get("delete/permanent")
        if ask:
            dlg = DeleteDialog(tracks, permanent, self)
            if not dlg.exec():
                return []
            permanent = dlg.permanent
        for t in tracks:
            self.player.release_file(t.path)
        deleted, failed = [], []
        roots = self.lib.roots()
        for t in tracks:
            ok, msg = fileops.delete_file(t.path, permanent)
            (deleted.append(t) if ok else failed.append((t, msg)))
        if failed and not permanent:
            r = QMessageBox.question(
                self, "Papierkorb nicht verfügbar",
                f"{len(failed)} Datei(en) konnten nicht in den Papierkorb verschoben werden "
                f"(z. B. weil das Laufwerk keinen Papierkorb hat):\n\n{failed[0][1]}\n\n"
                "Stattdessen endgültig löschen?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r == QMessageBox.Yes:
                still = []
                for t, _m in failed:
                    ok, msg = fileops.delete_file(t.path, True)
                    (deleted.append(t) if ok else still.append((t, msg)))
                failed = still
        if self.s.get("delete/remove_empty_dirs"):
            for t in deleted:
                stop = next((r for r in roots if t.path.startswith(r.rstrip("/\\") + os.sep)), None)
                if stop:
                    fileops.remove_empty_dirs(t.path, stop)
        ids = [t.id for t in deleted]
        self.lib.delete(ids)
        self.model.remove_ids(ids)
        self._refresh_pending()
        self._rebuild_sidebar()
        if failed:
            QMessageBox.warning(self, "Löschen", "Nicht gelöscht:\n\n" + "\n".join(
                f"{os.path.basename(t.path)}: {m}" for t, m in failed[:15]))
        self.statusBar().showMessage(f"{len(deleted)} Datei(en) "
                                     f"{'endgültig gelöscht' if permanent else 'in den Papierkorb verschoben'}.",
                                     8000)
        return ids

    def open_settings(self):
        dlg = SettingsDialog(self.s, self)
        if dlg.exec():
            self.player.set_device_id(self.s.get("audio/device"))
            if getattr(dlg, "backend_changed", False):
                QMessageBox.information(self, "Einstellungen", "Die geänderte Wiedergabe-Technik wird "
                                        "nach einem Neustart von MusicOrganizer verwendet.")

    def show_log(self):
        from mog import applog
        p = applog.log_path()
        if p and os.path.exists(p):
            fileops.reveal(p)
        else:
            QMessageBox.information(self, "Diagnose-Protokoll", "Noch kein Protokoll vorhanden.")

    # ------------------------------------------------------------------ Updates & Info
    def check_updates(self, manual=False):
        if not manual:
            last = self.s.get("update/last_check")
            if time.time() - float(last or 0) < 20 * 3600:
                return
        self.s.set("update/last_check", time.time())
        th = TaskThread(lambda p, c, i: updater.check_latest(), self)
        th.done.connect(lambda info: self._update_result(info, manual))
        th.failed.connect(lambda e: manual and QMessageBox.information(
            self, "Nach Updates suchen", e.split(": ", 1)[-1]))
        self._bg.append(th)
        th.start()

    def _update_result(self, info, manual):
        if not updater.is_newer(info["version"]):
            if manual:
                QMessageBox.information(self, "Nach Updates suchen",
                                        f"Du hast die aktuelle Version ({__version__}).")
            return
        if not manual and self.s.get("update/skip") == info["version"]:
            return
        dlg = UpdateDialog(info, self.s, self)
        dlg.exec()
        if dlg.install_started:
            self.close()

    def show_about(self):
        QMessageBox.about(
            self, f"Über {APP_NAME}",
            f"<h3>{APP_NAME} (MOG)</h3>"
            f"<p>Version {__version__}</p>"
            f"<p>Musikarchiv-Verwaltung für DJs.<br>{CREDIT}</p>"
            f"<p><a href='{updater.RELEASES_PAGE}' style='color:{C['accent']}'>Downloads & Versionen</a></p>"
            "<p style='color:#888'>Verwendet Qt/PySide6 (LGPL), FFmpeg (LGPL/GPL), mutagen (GPL), "
            "Chromaprint (LGPL).</p>")

    # ------------------------------------------------------------------ Zustand
    def _restore_state(self):
        g = self.s.value("win/geometry")
        if isinstance(g, (QByteArray, bytes)):
            self.restoreGeometry(g)
        hh = self.table.horizontalHeader()
        h = self.s.value("win/header_v2")
        if isinstance(h, (QByteArray, bytes)):
            hh.restoreState(h)
            hh.setSectionResizeMode(QHeaderView.Interactive)
            hh.setSectionsMovable(True)
            hh.setFirstSectionMovable(True)
        try:
            col = int(self.s.value("win/sort_col", COL_INDEX["artist"]))
            order = Qt.SortOrder(int(self.s.value("win/sort_order", 0)))
            self.table.sortByColumn(col, order)
        except (TypeError, ValueError):
            pass
        sp = self.s.value("win/splitter")
        if isinstance(sp, (QByteArray, bytes)):
            self.splitter.restoreState(sp)
        vol = self.s.value("player/volume")
        if vol is not None:
            try:
                self.player.vol.setValue(int(vol))
            except (TypeError, ValueError):
                pass

    def closeEvent(self, e):
        if not self._closing_ok:
            pend = self.lib.pending_ids()
            if pend:
                box = QMessageBox(QMessageBox.Question, "Ungespeicherte Änderungen",
                                  f"An {len(pend)} Titel(n) gibt es Tag-Änderungen (z. B. BPM), die noch "
                                  "nicht in die Dateien geschrieben wurden.\n\nJetzt speichern?", parent=self)
                b_save = box.addButton("Speichern und beenden", QMessageBox.AcceptRole)
                b_drop = box.addButton("Verwerfen und beenden", QMessageBox.DestructiveRole)
                box.addButton("Abbrechen", QMessageBox.RejectRole)
                box.setDefaultButton(b_save)
                box.exec()
                clicked = box.clickedButton()
                if clicked is b_save:
                    errors = self.save_pending(pend)
                    if errors and QMessageBox.question(
                            self, "Beenden", "Nicht alle Änderungen konnten gespeichert werden (sie bleiben "
                            "vorgemerkt). Trotzdem beenden?") != QMessageBox.Yes:
                        e.ignore()
                        return
                elif clicked is b_drop:
                    self.lib.discard_pending(pend)
                else:
                    e.ignore()
                    return
        self._closing_ok = True
        self.s.set("win/geometry", self.saveGeometry())
        self.s.set("win/header_v2", self.table.horizontalHeader().saveState())
        col, order = self.model.sort_state()
        self.s.set("win/sort_col", col)
        self.s.set("win/sort_order", int(order.value) if hasattr(order, "value") else int(order))
        self.s.set("win/splitter", self.splitter.saveState())
        self.s.set("player/volume", self.player.vol.value())
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.scan_thread.wait(5000)
        for th in self._bg:
            th.wait(3000)
        self.player.stop()
        super().closeEvent(e)
