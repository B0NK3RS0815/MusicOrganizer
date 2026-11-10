"""Tags aus Online-Datenbanken suchen und übernehmen."""
import os

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from mog.core import tags as tagio
from mog.core.fingerprint import compute_compressed, find_fpcalc
from mog.core.track import TAG_LABELS, format_duration
from mog.online import providers as prov

from .dialogs import primary
from .icons import icon, placeholder_cover

SOURCES = ["MusicBrainz", "Discogs", "Spotify", "AcoustID (Fingerabdruck)"]
APPLY_FIELDS = ["artist", "title", "album", "albumartist", "year", "track", "genre", "label"]


class _Worker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.finished_ok.emit(self.fn())
        except prov.ProviderError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class OnlineTagDialog(QDialog):
    # (track, werte, cover, cover_gesetzt) – Änderungen werden vorgemerkt, nicht sofort geschrieben
    staged = Signal(object, object, object, bool)

    def __init__(self, tracks, settings, parent=None):
        super().__init__(parent)
        self.tracks = [t for t in tracks if not t.missing]
        self.s = settings
        self.pos = 0
        self.results = []
        self._workers = []
        self.cover_data = None
        self.setWindowTitle("Tags online suchen")
        self.resize(1100, 680)

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.lbl_file = QLabel()
        self.lbl_file.setObjectName("BigTitle")
        top.addWidget(self.lbl_file, 1)
        self.btn_prev = QPushButton(icon("prev"), "")
        self.btn_next = QPushButton(icon("next"), "")
        self.btn_prev.setToolTip("Vorheriger Titel")
        self.btn_next.setToolTip("Nächster Titel")
        self.btn_prev.clicked.connect(lambda: self._goto(self.pos - 1))
        self.btn_next.clicked.connect(lambda: self._goto(self.pos + 1))
        self.lbl_pos = QLabel()
        self.lbl_pos.setObjectName("Muted")
        top.addWidget(self.btn_prev)
        top.addWidget(self.lbl_pos)
        top.addWidget(self.btn_next)
        lay.addLayout(top)
        self.lbl_path = QLabel()
        self.lbl_path.setObjectName("Hint")
        lay.addWidget(self.lbl_path)

        q = QHBoxLayout()
        self.cmb_src = QComboBox()
        self.cmb_src.addItems(SOURCES)
        self.cmb_src.setCurrentText(self.s.value("online/last_source", "MusicBrainz"))
        self.ed_artist = QLineEdit()
        self.ed_artist.setPlaceholderText("Artist")
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Titel")
        self.btn_search = primary(QPushButton(icon("search", "#FFFFFF"), "  Suchen"))
        q.addWidget(self.cmb_src)
        q.addWidget(self.ed_artist, 1)
        q.addWidget(self.ed_title, 1)
        q.addWidget(self.btn_search)
        lay.addLayout(q)
        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Artist", "Titel", "Album", "Jahr", "Genre", "Label", "Info"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate([170, 200, 180, 50, 110, 120]):
            self.table.setColumnWidth(i, w)
        split.addWidget(self.table)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0)
        self.cover = QLabel()
        self.cover.setFixedSize(180, 180)
        self.cover.setScaledContents(True)
        self.cover.setPixmap(placeholder_cover(180))
        rl.addWidget(self.cover, 0, Qt.AlignHCenter)
        self.cb_cover = QCheckBox("Cover übernehmen")
        self.cb_cover.setChecked(True)
        rl.addWidget(self.cb_cover)
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        self.field_cbs = {}
        self.field_vals = {}
        for r, f in enumerate(APPLY_FIELDS):
            cb = QCheckBox(TAG_LABELS[f])
            cb.setChecked(f not in ("track",))
            val = QLabel("")
            val.setObjectName("Muted")
            val.setWordWrap(True)
            grid.addWidget(cb, r, 0)
            grid.addWidget(val, r, 1)
            self.field_cbs[f] = cb
            self.field_vals[f] = val
        rl.addLayout(grid)
        self.cb_only_empty = QCheckBox("Nur leere Felder füllen")
        rl.addWidget(self.cb_only_empty)
        rl.addStretch()
        self.btn_apply = primary(QPushButton(icon("check", "#FFFFFF"), "  Übernehmen"))
        self.btn_apply.setEnabled(False)
        self.btn_apply_next = QPushButton("Übernehmen && weiter")
        self.btn_apply_next.setEnabled(False)
        rl.addWidget(self.btn_apply)
        rl.addWidget(self.btn_apply_next)
        right.setMinimumWidth(300)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        lay.addWidget(split, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        b_close = QPushButton("Schließen")
        b_close.clicked.connect(self.accept)
        bottom.addWidget(b_close)
        lay.addLayout(bottom)

        self.btn_search.clicked.connect(self.search)
        self.ed_artist.returnPressed.connect(self.search)
        self.ed_title.returnPressed.connect(self.search)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.itemDoubleClicked.connect(lambda *_: self.apply())
        self.btn_apply.clicked.connect(lambda: self.apply())
        self.btn_apply_next.clicked.connect(lambda: self.apply(go_next=True))
        self.cmb_src.currentTextChanged.connect(self._src_changed)
        self._goto(0)
        self._src_changed(self.cmb_src.currentText())

    # --- Navigation --------------------------------------------------------
    def _goto(self, i):
        if not self.tracks:
            return
        self.pos = max(0, min(i, len(self.tracks) - 1))
        t = self.tracks[self.pos]
        self.lbl_file.setText(f"{t.display_artist} – {t.display_title}" if t.display_artist else t.display_title)
        self.lbl_path.setText(t.path)
        self.lbl_pos.setText(f"{self.pos + 1} / {len(self.tracks)}")
        self.btn_prev.setEnabled(self.pos > 0)
        self.btn_next.setEnabled(self.pos < len(self.tracks) - 1)
        self.ed_artist.setText(t.artist)
        self.ed_title.setText(t.title)
        self.table.setRowCount(0)
        self.results = []
        self.status.setText("")
        self._clear_preview()
        if self.isVisible():
            self.search()

    def showEvent(self, e):
        super().showEvent(e)
        if not self.results and self.tracks:
            self.search()

    def _src_changed(self, src):
        self.s.set("online/last_source", src)
        fp = src.startswith("AcoustID")
        self.ed_artist.setEnabled(not fp)
        self.ed_title.setEnabled(not fp)
        hints = {
            "MusicBrainz": "Freie Musikdatenbank – sehr vollständig, Genres aus Community-Tags.",
            "Discogs": "Ideal für elektronische Musik: Label, Genre & Stil. Persönlicher Token nötig.",
            "Spotify": "Benötigt eigene Spotify-App (Client-ID/Secret). Liefert keine BPM und keine Labels mehr.",
            "AcoustID (Fingerabdruck)": "Erkennt den Titel am Klang – hilfreich bei Dateien ohne Tags.",
        }
        self.status.setText(hints.get(src, ""))

    # --- Suche -------------------------------------------------------------
    def search(self):
        if not self.tracks:
            return
        src = self.cmb_src.currentText()
        artist, title = self.ed_artist.text().strip(), self.ed_title.text().strip()
        t = self.tracks[self.pos]
        s = self.s
        contact = s.get("online/contact")

        if src == "MusicBrainz":
            fn = lambda: prov.musicbrainz_search(artist, title, contact)
        elif src == "Discogs":
            fn = lambda: prov.discogs_search(artist, title, s.get("online/discogs_token"), contact)
        elif src == "Spotify":
            fn = lambda: prov.spotify_search(artist, title, s.get("online/spotify_id"),
                                             s.get("online/spotify_secret"))
        else:
            fpcalc = find_fpcalc(s.get("tools/fpcalc") or None)
            if not fpcalc:
                self.status.setText("fpcalc (Chromaprint) nicht gefunden – siehe Einstellungen → Encoder.")
                return
            key = s.get("online/acoustid_key")

            def fn():
                d, fp = compute_compressed(fpcalc, t.path)
                return prov.acoustid_lookup(fp, d, key, contact)
        self.status.setText(f"Suche bei {src} …")
        self.btn_search.setEnabled(False)
        w = _Worker(fn)
        w.finished_ok.connect(self._show_results)
        w.failed.connect(self._failed)
        w.finished.connect(lambda: self.btn_search.setEnabled(True))
        self._workers.append(w)
        w.start()

    def _failed(self, msg):
        self.status.setText(f"⚠ {msg}")

    def _show_results(self, results):
        self.results = results
        self.table.setRowCount(len(results))
        t = self.tracks[self.pos]
        for r, res in enumerate(results):
            info = res.info
            if res.duration:
                info = (info + " · " if info else "") + format_duration(res.duration)
                if t.duration and abs(res.duration - t.duration) > 15:
                    info += " ≠"
            if res.score:
                info += f" · {res.score} %"
            for c, val in enumerate([res.artist, res.title, res.album, res.year, res.genre, res.label, info]):
                it = QTableWidgetItem(val)
                it.setToolTip(val)
                self.table.setItem(r, c, it)
        self.status.setText(f"{len(results)} Treffer bei {self.cmb_src.currentText()}."
                            if results else "Keine Treffer – Suchbegriffe anpassen (z. B. Mix-Angabe entfernen).")
        if results:
            self.table.selectRow(0)

    def _clear_preview(self):
        self.cover.setPixmap(placeholder_cover(180))
        self.cover_data = None
        for f in APPLY_FIELDS:
            self.field_vals[f].setText("")
        self.btn_apply.setEnabled(False)
        self.btn_apply_next.setEnabled(False)

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._clear_preview()
            return
        res = self.results[rows[0].row()]
        for f in APPLY_FIELDS:
            self.field_vals[f].setText(getattr(res, f) or "–")
            self.field_cbs[f].setEnabled(bool(getattr(res, f)))
        self.btn_apply.setEnabled(True)
        self.btn_apply_next.setEnabled(self.pos < len(self.tracks) - 1)
        self.cover.setPixmap(placeholder_cover(180))
        self.cover_data = None
        if res.cover_url:
            url = res.cover_url
            contact = self.s.get("online/contact")
            w = _Worker(lambda: (url, prov.download_image(url, contact)))
            w.finished_ok.connect(self._cover_loaded)
            self._workers.append(w)
            w.start()

    def _cover_loaded(self, payload):
        url, data = payload
        rows = self.table.selectionModel().selectedRows()
        if not rows or self.results[rows[0].row()].cover_url != url or not data:
            return
        pm = QPixmap()
        pm.loadFromData(data[0])
        if not pm.isNull():
            self.cover.setPixmap(pm)
            self.cover_data = data

    # --- Übernehmen --------------------------------------------------------
    def apply(self, go_next=False):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        res = self.results[rows[0].row()]
        t = self.tracks[self.pos]
        # aktuelle Werte aus der Bibliothek (inkl. vorgemerkter Änderungen);
        # aus dem Dateinamen abgeleitete Werte gelten als leer
        current = t.tag_dict()
        if t.tags_missing:
            current["artist"] = current["title"] = ""
        vals = {}
        for f in APPLY_FIELDS:
            v = getattr(res, f)
            if v and self.field_cbs[f].isChecked() and self.field_cbs[f].isEnabled():
                if self.cb_only_empty.isChecked() and current.get(f):
                    continue
                vals[f] = v
        # Label bei MusicBrainz ggf. nachladen
        if (res.source == "MusicBrainz" and self.field_cbs["label"].isChecked() and not res.label
                and res.extra.get("release_id") and not (self.cb_only_empty.isChecked() and current.get("label"))):
            lab = prov.musicbrainz_release_label(res.extra["release_id"], self.s.get("online/contact"))
            if lab:
                vals["label"] = lab
        use_cover = bool(self.cb_cover.isChecked() and self.cover_data)
        self.staged.emit(t, vals, self.cover_data if use_cover else None, use_cover)
        self.status.setText(f"✓ Übernommen für „{os.path.basename(t.path)}“ – wird beim Speichern "
                            "bzw. Beenden in die Datei geschrieben.")
        if go_next and self.pos < len(self.tracks) - 1:
            self._goto(self.pos + 1)

    def done(self, r):
        for w in self._workers:
            w.wait(15000)
        super().done(r)
