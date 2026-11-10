"""Dialog: neue Version gefunden – herunterladen und installieren."""
import sys

from PySide6.QtCore import QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QTextBrowser, QVBoxLayout)

from mog import __version__
from mog.core import updater
from mog.core.track import format_size

from .dialogs import primary, run_task
from .icons import icon


class UpdateDialog(QDialog):
    """Nach exec(): ``self.install_started`` ist True, wenn MOG beendet werden soll."""

    def __init__(self, info, settings, parent=None):
        super().__init__(parent)
        self.info = info
        self.s = settings
        self.install_started = False
        self.asset = updater.pick_asset(info["assets"])
        self.setWindowTitle("Update verfügbar")
        self.resize(620, 480)

        lay = QVBoxLayout(self)
        t = QLabel(f"MusicOrganizer {info['version']} ist verfügbar")
        t.setObjectName("BigTitle")
        lay.addWidget(t)
        sub = QLabel(f"Installiert: {__version__}  →  Neu: {info['version']}")
        sub.setObjectName("Muted")
        lay.addWidget(sub)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info["notes"] or "_Keine Versionshinweise._")
        lay.addWidget(notes, 1)

        frozen = getattr(sys, "frozen", False)
        if self.asset and frozen:
            what = "Installer" if self.asset["name"].endswith(".exe") else "Paket"
            hint = (f"{what}: {self.asset['name']} ({format_size(self.asset['size'])}). "
                    + ("Nach dem Download startet der Installer; MOG wird dafür beendet "
                       "(ungespeicherte Tag-Änderungen werden vorher abgefragt)."
                       if sys.platform.startswith("win") else
                       "Nach dem Download öffnet sich das Disk-Image – MusicOrganizer dann in "
                       "„Programme“ ziehen und die vorhandene Version ersetzen."))
        else:
            hint = "Die neue Version kann auf der Download-Seite heruntergeladen werden."
            self.asset = None
        h = QLabel(hint)
        h.setObjectName("Hint")
        h.setWordWrap(True)
        lay.addWidget(h)

        row = QHBoxLayout()
        b_skip = QPushButton("Diese Version überspringen")
        b_skip.clicked.connect(self._skip)
        row.addWidget(b_skip)
        row.addStretch()
        b_later = QPushButton("Später")
        b_later.clicked.connect(self.reject)
        row.addWidget(b_later)
        if self.asset:
            b_go = primary(QPushButton(icon("download", "#FFFFFF"), "  Herunterladen && installieren"))
            b_go.clicked.connect(self._install)
        else:
            b_go = primary(QPushButton(icon("globe", "#FFFFFF"), "  Download-Seite öffnen"))
            b_go.clicked.connect(self._open_page)
        row.addWidget(b_go)
        lay.addLayout(row)

    def _skip(self):
        self.s.set("update/skip", self.info["version"])
        self.reject()

    def _open_page(self):
        QDesktopServices.openUrl(QUrl(self.info["page"]))
        self.accept()

    def _install(self):
        dest = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or \
            QStandardPaths.writableLocation(QStandardPaths.TempLocation)
        asset = self.asset

        def job(progress, cancel, _item):
            return updater.download(
                asset, dest,
                lambda d, t: progress(d // 1024, t // 1024, f"{format_size(d)} von {format_size(t)}"),
                cancel)

        path = run_task(self, f"Lade {asset['name']} …", job)
        if not path:
            return
        try:
            updater.launch_installer(path)
        except Exception as e:
            QMessageBox.warning(self, "Update", f"Installer konnte nicht gestartet werden:\n{e}\n\n"
                                f"Die Datei liegt unter:\n{path}")
            return
        self.install_started = True
        self.accept()
