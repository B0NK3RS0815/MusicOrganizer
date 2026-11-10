"""Kleinere Dialoge: Laufwerk wählen, Fortschritt, Einstellungen, Bestätigung."""
import os
import sys

from PySide6.QtCore import QSize, QStorageInfo, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton, QTabWidget, QVBoxLayout,
                               QWidget)

from mog.core import encoder, fingerprint
from mog.core.bpm import BPM_RANGES
from mog.core.track import format_size

from .icons import icon


def _reveal_log(path):
    from mog.core.fileops import reveal
    if os.path.exists(path):
        reveal(path)


def primary(btn):
    btn.setObjectName("Primary")
    return btn


# --------------------------------------------------------------------------
# Laufwerk wählen
# --------------------------------------------------------------------------
_PSEUDO_FS = {"tmpfs", "devtmpfs", "proc", "sysfs", "overlay", "squashfs", "devfs", "autofs",
              "nullfs", "fdescfs", "cgroup", "cgroup2", "efivarfs", "ramfs"}


def list_volumes():
    vols = []
    for v in QStorageInfo.mountedVolumes():
        if not v.isValid() or not v.isReady():
            continue
        fs = bytes(v.fileSystemType()).decode(errors="ignore").lower()
        root = v.rootPath()
        if fs in _PSEUDO_FS:
            continue
        if sys.platform == "darwin" and root != "/" and not root.startswith("/Volumes/"):
            continue
        if sys.platform.startswith("linux") and root not in ("/",) and not root.startswith(
                ("/media", "/mnt", "/run/media", "/home")):
            continue
        name = v.displayName() or root
        vols.append({"root": root, "name": name, "fs": fs.upper(), "total": v.bytesTotal(),
                     "free": v.bytesAvailable(), "readonly": v.isReadOnly()})
    vols.sort(key=lambda d: (d["root"] in ("/", "C:/"), d["root"]))
    return vols


class VolumeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Datenträger einlesen")
        self.resize(560, 400)
        lay = QVBoxLayout(self)
        t = QLabel("Datenträger wählen")
        t.setObjectName("BigTitle")
        lay.addWidget(t)
        h = QLabel("Wähle z. B. deine externe SSD. Alle Audiodateien darauf werden eingelesen – "
                   "bereits bekannte, unveränderte Dateien werden übersprungen.")
        h.setObjectName("Hint")
        h.setWordWrap(True)
        lay.addWidget(h)
        self.list = QListWidget()
        self.list.setIconSize(QSize(28, 28))
        self.list.setSpacing(2)
        lay.addWidget(self.list, 1)
        self._fill()
        row = QHBoxLayout()
        b_ref = QPushButton(icon("refresh"), " Aktualisieren")
        b_ref.clicked.connect(self._fill)
        row.addWidget(b_ref)
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.ok = primary(QPushButton("Einlesen"))
        bb.addButton(self.ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        self.list.currentRowChanged.connect(lambda r: self.ok.setEnabled(r >= 0))
        self.ok.setEnabled(self.list.currentRow() >= 0)

    def _fill(self):
        self.list.clear()
        for v in list_volumes():
            used = v["total"] - v["free"]
            txt = (f"{v['name']}   ({v['root']})\n"
                   f"{format_size(used)} belegt von {format_size(v['total'])} · {v['fs']}")
            it = QListWidgetItem(icon("drive"), txt)
            it.setData(Qt.UserRole, v["root"])
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def selected_root(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None


# --------------------------------------------------------------------------
# Fortschritt
# --------------------------------------------------------------------------
class ProgressDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        self.label = QLabel(title)
        self.label.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.detail = QLabel("")
        self.detail.setObjectName("Hint")
        self.detail.setWordWrap(True)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        lay.addWidget(self.detail)
        row = QHBoxLayout()
        row.addStretch()
        self.btn = QPushButton("Abbrechen")
        row.addWidget(self.btn)
        lay.addLayout(row)
        self.btn.clicked.connect(self.reject)

    def update_progress(self, done, total, text=""):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(done)
            self.bar.setFormat(f"{done} / {total}")
        else:
            self.bar.setRange(0, 0)
        if text:
            self.detail.setText(text)


def run_task(parent, title, fn, item_cb=None):
    """Startet fn in einem TaskThread mit modalem Fortschrittsdialog. Gibt Ergebnis oder None."""
    from .workers import TaskThread
    dlg = ProgressDialog(title, parent)
    th = TaskThread(fn, parent)
    result = {"value": None, "error": None}
    th.progress.connect(dlg.update_progress)
    if item_cb:
        th.item_done.connect(item_cb)
    th.done.connect(lambda r: (result.__setitem__("value", r), dlg.accept()))
    th.failed.connect(lambda e: (result.__setitem__("error", e), dlg.accept()))
    dlg.rejected.connect(th.cancel)
    th.start()
    dlg.exec()
    if th.isRunning():
        dlg.label.setText("Wird abgebrochen …")
        th.wait(30000)
    if result["error"]:
        QMessageBox.warning(parent, title, result["error"])
    return result["value"]


# --------------------------------------------------------------------------
# Einstellungen
# --------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle("Einstellungen")
        self.resize(620, 520)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)

        # Allgemein
        w = QWidget()
        f = QVBoxLayout(w)
        g = QGroupBox("Löschen von Dateien")
        gl = QVBoxLayout(g)
        self.rb_trash = QRadioButton("In den Papierkorb verschieben (empfohlen, wiederherstellbar)")
        self.rb_perm = QRadioButton("Endgültig löschen (nicht wiederherstellbar)")
        (self.rb_perm if self.s.get("delete/permanent") else self.rb_trash).setChecked(True)
        self.cb_empty = QCheckBox("Leere Ordner nach dem Löschen entfernen")
        self.cb_empty.setChecked(self.s.get("delete/remove_empty_dirs"))
        for x in (self.rb_trash, self.rb_perm, self.cb_empty):
            gl.addWidget(x)
        f.addWidget(g)
        g2 = QGroupBox("Einlesen & Start")
        gl2 = QVBoxLayout(g2)
        self.cb_hidden = QCheckBox("Versteckte Dateien und Ordner überspringen")
        self.cb_hidden.setChecked(self.s.get("scan/skip_hidden"))
        gl2.addWidget(self.cb_hidden)
        self.cb_load = QCheckBox("Gespeicherte Bibliothek beim Start automatisch laden")
        self.cb_load.setToolTip("Aus: MOG startet mit leerer Ansicht, die Bibliothek lässt sich per Knopf laden.")
        self.cb_load.setChecked(self.s.get("startup/load_library"))
        gl2.addWidget(self.cb_load)
        self.cb_update = QCheckBox("Beim Start nach Updates suchen (höchstens einmal täglich)")
        self.cb_update.setChecked(self.s.get("update/auto"))
        gl2.addWidget(self.cb_update)
        f.addWidget(g2)
        g3 = QGroupBox("BPM-Analyse")
        fl3 = QFormLayout(g3)
        self.cmb_range = QComboBox()
        self.cmb_range.addItems(list(BPM_RANGES))
        self.cmb_range.setCurrentText(self.s.get("bpm/range"))
        self.cb_round = QCheckBox("Auf ganze BPM runden")
        self.cb_round.setChecked(self.s.get("bpm/round"))
        fl3.addRow("Tempobereich:", self.cmb_range)
        fl3.addRow("", self.cb_round)
        f.addWidget(g3)
        f.addStretch()
        tabs.addTab(w, "Allgemein")

        # Encoder / Werkzeuge
        w = QWidget()
        f = QFormLayout(w)
        self.ed_ff = QLineEdit(self.s.get("tools/ffmpeg"))
        self.ed_ff.setPlaceholderText("automatisch (mitgeliefert / PATH)")
        self.ed_fp = QLineEdit(self.s.get("tools/fpcalc"))
        self.ed_fp.setPlaceholderText("automatisch (mitgeliefert / PATH)")
        f.addRow("ffmpeg:", self._with_browse(self.ed_ff))
        self.lbl_ff = QLabel()
        self.lbl_ff.setObjectName("Hint")
        f.addRow("", self.lbl_ff)
        f.addRow("fpcalc (Chromaprint):", self._with_browse(self.ed_fp))
        self.lbl_fp = QLabel()
        self.lbl_fp.setObjectName("Hint")
        self.lbl_fp.setWordWrap(True)
        f.addRow("", self.lbl_fp)
        self.ed_ff.editingFinished.connect(self._check_tools)
        self.ed_fp.editingFinished.connect(self._check_tools)
        self._check_tools()
        tabs.addTab(w, "Encoder")
        tabs.addTab(self._audio_tab(), "Audio")

        # Online
        w = QWidget()
        f = QFormLayout(w)
        self.ed_contact = QLineEdit(self.s.get("online/contact"))
        self.ed_contact.setPlaceholderText("z. B. deine E-Mail oder Website (für MusicBrainz)")
        f.addRow("Kontakt:", self.ed_contact)
        f.addRow("", self._hint("MusicBrainz bittet um eine Kontaktangabe im User-Agent. Wird nur "
                                "an MusicBrainz/Discogs/AcoustID übertragen."))
        self.ed_discogs = QLineEdit(self.s.get("online/discogs_token"))
        self.ed_discogs.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        f.addRow("Discogs-Token:", self.ed_discogs)
        f.addRow("", self._link("Token erstellen: discogs.com → Einstellungen → Entwickler",
                                "https://www.discogs.com/settings/developers"))
        self.ed_sp_id = QLineEdit(self.s.get("online/spotify_id"))
        self.ed_sp_secret = QLineEdit(self.s.get("online/spotify_secret"))
        self.ed_sp_secret.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        f.addRow("Spotify Client-ID:", self.ed_sp_id)
        f.addRow("Spotify Secret:", self.ed_sp_secret)
        f.addRow("", self._link("App anlegen: developer.spotify.com/dashboard (Premium nötig)",
                                "https://developer.spotify.com/dashboard"))
        self.ed_acoustid = QLineEdit(self.s.get("online/acoustid_key"))
        f.addRow("AcoustID-Key:", self.ed_acoustid)
        f.addRow("", self._link("Kostenlosen Key holen: acoustid.org/new-application",
                                "https://acoustid.org/new-application"))
        tabs.addTab(w, "Online-Datenbanken")

        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        ok = primary(QPushButton("Speichern"))
        bb.addButton(ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # --- Audio ------------------------------------------------------------
    BACKENDS = [("auto", "Automatisch (FFmpeg, empfohlen)"), ("ffmpeg", "FFmpeg")]
    if sys.platform.startswith("win"):
        BACKENDS.append(("windows", "Windows Media Foundation"))
    elif sys.platform == "darwin":
        BACKENDS.append(("darwin", "AVFoundation (macOS)"))

    def _audio_tab(self):
        from mog import applog
        w = QWidget()
        f = QFormLayout(w)
        self.cmb_dev = QComboBox()
        try:
            from PySide6.QtMultimedia import QMediaDevices
            default = QMediaDevices.defaultAudioOutput()
            self.cmb_dev.addItem(f"Systemstandard ({default.description() or '–'})", "")
            for d in QMediaDevices.audioOutputs():
                self.cmb_dev.addItem(d.description(), bytes(d.id()).hex())
        except Exception:
            self.cmb_dev.addItem("Systemstandard", "")
        i = self.cmb_dev.findData(self.s.get("audio/device"))
        self.cmb_dev.setCurrentIndex(max(0, i))
        f.addRow("Ausgabegerät:", self.cmb_dev)
        self.cmb_backend = QComboBox()
        for key, label in self.BACKENDS:
            self.cmb_backend.addItem(label, key)
        self.cmb_backend.setCurrentIndex(max(0, self.cmb_backend.findData(self.s.get("audio/backend"))))
        f.addRow("Wiedergabe-Technik:", self.cmb_backend)
        f.addRow("", self._hint("Kein Ton? Erst den Testton probieren, dann ggf. die andere Wiedergabe-Technik "
                                "wählen. Eine geänderte Technik wirkt nach einem Neustart von MOG."))
        row = QHBoxLayout()
        b1 = QPushButton(icon("play"), " Testton über Player")
        b2 = QPushButton(icon("volume"), " Testton direkt")
        b1.setToolTip("Prüft denselben Weg wie die normale Wiedergabe")
        b2.setToolTip("Schickt den Ton ohne Umweg direkt an das Ausgabegerät")
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        wrow = QWidget()
        wrow.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f.addRow("Test:", wrow)
        self.lbl_test = QLabel("")
        self.lbl_test.setWordWrap(True)
        f.addRow("", self.lbl_test)
        info = QLabel(applog.multimedia_info())
        info.setObjectName("Hint")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow("Info:", info)
        lp = applog.log_path()
        if lp:
            b_log = QPushButton(icon("file"), " Diagnose-Protokoll zeigen")
            b_log.setToolTip(lp)
            b_log.clicked.connect(lambda: _reveal_log(lp))
            f.addRow("", b_log)

        from .audio_test import ToneTester
        self.tester = ToneTester(self)
        self.tester.result.connect(self.lbl_test.setText)

        def device():
            from .player import find_output_device
            return find_output_device(self.cmb_dev.currentData())
        b1.clicked.connect(lambda: (self.lbl_test.setText("Spiele Testton …"), self.tester.via_player(device())))
        b2.clicked.connect(lambda: (self.lbl_test.setText("Spiele Testton …"), self.tester.direct(device())))
        return w

    def _hint(self, text):
        l = QLabel(text)
        l.setObjectName("Hint")
        l.setWordWrap(True)
        return l

    def _link(self, text, url):
        l = QLabel(f'<a href="{url}" style="color:#FF4D6D;text-decoration:none">{text}</a>')
        l.setObjectName("Hint")
        l.setOpenExternalLinks(True)
        return l

    def _with_browse(self, edit):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        b = QPushButton("…")
        b.setFixedWidth(36)

        def browse():
            p, _ = QFileDialog.getOpenFileName(self, "Programm wählen")
            if p:
                edit.setText(p)
                self._check_tools()
        b.clicked.connect(browse)
        h.addWidget(b)
        return w

    def _check_tools(self):
        ff = encoder.find_ffmpeg(self.ed_ff.text().strip() or None)
        v = encoder.ffmpeg_version(ff) if ff else None
        self.lbl_ff.setText(f"✓ gefunden: {ff} (Version {v})" if v else "✗ ffmpeg nicht gefunden")
        fp = fingerprint.find_fpcalc(self.ed_fp.text().strip() or None)
        self.lbl_fp.setText(f"✓ gefunden: {fp}" if fp else
                            "✗ fpcalc nicht gefunden – Audio-Fingerabdruck und AcoustID sind deaktiviert. "
                            "macOS: 'brew install chromaprint', Windows: fpcalc.exe von acoustid.org/chromaprint.")

    def _save(self):
        s = self.s
        s.set("delete/permanent", self.rb_perm.isChecked())
        s.set("delete/remove_empty_dirs", self.cb_empty.isChecked())
        s.set("scan/skip_hidden", self.cb_hidden.isChecked())
        self.backend_changed = self.cmb_backend.currentData() != s.get("audio/backend")
        s.set("audio/device", self.cmb_dev.currentData() or "")
        s.set("audio/backend", self.cmb_backend.currentData())
        s.set("startup/load_library", self.cb_load.isChecked())
        s.set("update/auto", self.cb_update.isChecked())
        s.set("bpm/range", self.cmb_range.currentText())
        s.set("bpm/round", self.cb_round.isChecked())
        s.set("tools/ffmpeg", self.ed_ff.text().strip())
        s.set("tools/fpcalc", self.ed_fp.text().strip())
        s.set("online/contact", self.ed_contact.text().strip())
        s.set("online/discogs_token", self.ed_discogs.text().strip())
        s.set("online/spotify_id", self.ed_sp_id.text().strip())
        s.set("online/spotify_secret", self.ed_sp_secret.text().strip())
        s.set("online/acoustid_key", self.ed_acoustid.text().strip())
        self.accept()


# --------------------------------------------------------------------------
# Löschbestätigung
# --------------------------------------------------------------------------
class DeleteDialog(QDialog):
    """Fragt nach, bevor Dateien wirklich vom Datenträger gelöscht werden."""

    def __init__(self, tracks, permanent_default, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Von Datenträger löschen")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        n = len(tracks)
        t = QLabel(f"{n} Datei{'en' if n != 1 else ''} vom Datenträger löschen?")
        t.setObjectName("BigTitle")
        lay.addWidget(t)
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.NoSelection)
        for tr in tracks[:200]:
            lst.addItem(tr.path)
        if n > 200:
            lst.addItem(f"… und {n - 200} weitere")
        lst.setMaximumHeight(180)
        lay.addWidget(lst)
        self.rb_trash = QRadioButton("In den Papierkorb verschieben")
        self.rb_perm = QRadioButton("Endgültig löschen – kann nicht rückgängig gemacht werden")
        (self.rb_perm if permanent_default else self.rb_trash).setChecked(True)
        lay.addWidget(self.rb_trash)
        lay.addWidget(self.rb_perm)
        hint = QLabel("Hinweis: Bei manchen externen Laufwerken (z. B. als 'Wechseldatenträger' "
                      "eingebunden) gibt es keinen Papierkorb. Schlägt das Verschieben fehl, fragt "
                      "MOG nach, ob endgültig gelöscht werden soll.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        ok = QPushButton(icon("trash", "#FFB3BE"), "  Löschen")
        ok.setObjectName("Danger")
        bb.addButton(ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @property
    def permanent(self):
        return self.rb_perm.isChecked()
