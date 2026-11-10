"""Konvertierung mit ffmpeg (z. B. FLAC/WAV/M4A → MP3)."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QRadioButton, QVBoxLayout)

from mog.core import encoder, tags as tagio
from mog.core.fileops import delete_file

from .dialogs import primary, run_task
from .icons import icon


PRESET_FORMAT = {"mp3_320": "MP3", "mp3_v0": "MP3", "mp3_256": "MP3", "mp3_192": "MP3",
                 "aac_256": "AAC", "alac": "ALAC", "flac": "FLAC", "wav16": "WAV", "wav24": "WAV",
                 "aiff16": "AIFF", "aiff24": "AIFF", "ogg_q8": "OGG", "opus_192": "OPUS"}


class ConvertDialog(QDialog):
    def __init__(self, tracks, settings, parent=None):
        super().__init__(parent)
        self.tracks = [t for t in tracks if not t.missing]
        self.s = settings
        self.results = []       # (quelle, ziel|None, fehler)
        self.setWindowTitle("Konvertieren")
        self.resize(640, 520)
        self.ffmpeg = encoder.find_ffmpeg(self.s.get("tools/ffmpeg") or None)

        lay = QVBoxLayout(self)
        t = QLabel(f"{len(self.tracks)} Datei{'en' if len(self.tracks) != 1 else ''} konvertieren")
        t.setObjectName("BigTitle")
        lay.addWidget(t)
        if not self.ffmpeg:
            w = QLabel("ffmpeg wurde nicht gefunden. Bitte unter Einstellungen → Encoder einen Pfad angeben.")
            w.setObjectName("Warning")
            w.setWordWrap(True)
            lay.addWidget(w)

        g = QGroupBox("Zielformat")
        f = QFormLayout(g)
        self.cmb = QComboBox()
        for p in encoder.PRESETS:
            self.cmb.addItem(p.name, p.key)
        idx = self.cmb.findData(self.s.get("convert/preset"))
        self.cmb.setCurrentIndex(max(0, idx))
        f.addRow("Format:", self.cmb)
        self.cmb_sr = QComboBox()
        for label, val in (("Original beibehalten", 0), ("44,1 kHz", 44100), ("48 kHz", 48000),
                           ("96 kHz", 96000)):
            self.cmb_sr.addItem(label, val)
        self.cmb_sr.setCurrentIndex(max(0, self.cmb_sr.findData(self.s.get("convert/samplerate"))))
        f.addRow("Samplerate:", self.cmb_sr)
        self.note = QLabel("")
        self.note.setObjectName("Hint")
        self.note.setWordWrap(True)
        f.addRow("", self.note)
        lay.addWidget(g)

        g2 = QGroupBox("Speicherort")
        v2 = QVBoxLayout(g2)
        self.rb_same = QRadioButton("Neben der Originaldatei")
        self.rb_dir = QRadioButton("In Ordner:")
        bg = QButtonGroup(self)
        bg.addButton(self.rb_same)
        bg.addButton(self.rb_dir)
        out_dir = self.s.get("convert/out_dir")
        (self.rb_dir if out_dir else self.rb_same).setChecked(True)
        v2.addWidget(self.rb_same)
        h = QHBoxLayout()
        h.addWidget(self.rb_dir)
        self.ed_dir = QLineEdit(out_dir)
        h.addWidget(self.ed_dir, 1)
        b = QPushButton(icon("folder"), "")
        b.clicked.connect(self._browse)
        h.addWidget(b)
        v2.addLayout(h)
        self.cb_struct = QCheckBox("Ordnerstruktur beibehalten (relativ zum gemeinsamen Oberordner)")
        self.cb_struct.setChecked(True)
        v2.addWidget(self.cb_struct)
        lay.addWidget(g2)

        g3 = QGroupBox("Optionen")
        v3 = QVBoxLayout(g3)
        self.cmb_exist = QComboBox()
        self.cmb_exist.addItems(["Vorhandene Dateien überspringen", "Neuen Namen vergeben",
                                 "Vorhandene überschreiben"])
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Wenn Zieldatei existiert:"))
        h3.addWidget(self.cmb_exist, 1)
        v3.addLayout(h3)
        self.cb_skip_same = QCheckBox("Dateien überspringen, die bereits im Zielformat sind")
        self.cb_skip_same.setChecked(True)
        self.cb_add = QCheckBox("Konvertierte Dateien zur Bibliothek hinzufügen")
        self.cb_add.setChecked(True)
        self.cb_del = QCheckBox("Originale nach erfolgreicher Konvertierung in den Papierkorb")
        for w in (self.cb_skip_same, self.cb_add, self.cb_del):
            v3.addWidget(w)
        lay.addWidget(g3)
        lay.addStretch()

        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.ok = primary(QPushButton(icon("convert", "#FFFFFF"), "  Konvertieren"))
        self.ok.setEnabled(bool(self.ffmpeg) and bool(self.tracks))
        bb.addButton(self.ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self._run)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.cmb.currentIndexChanged.connect(self._update_note)
        self._update_note()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Zielordner wählen", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)
            self.rb_dir.setChecked(True)

    def preset(self):
        return encoder.PRESETS_BY_KEY[self.cmb.currentData()]

    def _update_note(self):
        p = self.preset()
        lossy_src = sum(1 for t in self.tracks if not t.lossless)
        msg = []
        if p.note:
            msg.append(p.note)
        if lossy_src and not p.lossless:
            msg.append(f"⚠ {lossy_src} Quelldatei(en) sind bereits verlustbehaftet – erneutes Kodieren "
                       "verschlechtert die Qualität etwas.")
        if lossy_src and p.lossless:
            msg.append(f"ℹ {lossy_src} Quelldatei(en) sind verlustbehaftet – ein verlustfreies Ziel "
                       "stellt die Qualität nicht wieder her, macht die Datei nur größer.")
        if not p.cover:
            msg.append("Dieses Format speichert kein Cover.")
        self.note.setText("\n".join(msg))

    def _run(self):
        p = self.preset()
        out_dir = self.ed_dir.text().strip() if self.rb_dir.isChecked() else None
        if self.rb_dir.isChecked() and not out_dir:
            QMessageBox.information(self, "Konvertieren", "Bitte einen Zielordner wählen.")
            return
        self.s.set("convert/preset", p.key)
        self.s.set("convert/out_dir", out_dir or "")
        self.s.set("convert/samplerate", self.cmb_sr.currentData())
        sr = self.cmb_sr.currentData() or None
        common = None
        if out_dir and self.cb_struct.isChecked() and self.tracks:
            try:
                common = os.path.commonpath([t.folder for t in self.tracks])
            except ValueError:
                common = None
        exist_mode = self.cmb_exist.currentIndex()
        skip_same = self.cb_skip_same.isChecked()
        del_orig = self.cb_del.isChecked()
        ff = self.ffmpeg
        tracks = list(self.tracks)

        def job(progress, cancel, item_cb):
            results = []
            lock = threading.Lock()
            done = [0]
            todo = []
            for t in tracks:
                if skip_same and t.fmt == PRESET_FORMAT.get(p.key):
                    results.append((t, None, "übersprungen (bereits im Zielformat)"))
                    continue
                dst = encoder.target_path(t.path, p, out_dir, common)
                if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(t.path)):
                    stem, ext = os.path.splitext(dst)
                    dst = f"{stem} ({p.key}){ext}"
                if os.path.exists(dst):
                    if exist_mode == 0:
                        results.append((t, None, "übersprungen (Ziel existiert)"))
                        continue
                    if exist_mode == 1:
                        dst = encoder.unique_path(dst)
                todo.append((t, dst))
            total = len(todo)
            progress(0, total, "")

            def one(t, dst):
                if cancel.is_set():
                    return t, None, "abgebrochen"
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    encoder.convert(ff, t.path, dst, p, t.duration, samplerate=sr, cancel=cancel)
                    try:
                        tagio.copy_tags(t.path, dst)
                    except Exception as e:
                        return t, dst, f"konvertiert, Tags nicht übernommen: {e}"
                    if del_orig:
                        ok, msg = delete_file(t.path, permanent=False)
                        if not ok:
                            return t, dst, f"konvertiert, Original nicht gelöscht: {msg}"
                    return t, dst, ""
                except encoder.EncoderError as e:
                    return t, None, str(e)

            workers = max(1, min(4, (os.cpu_count() or 2) // 2))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(one, t, d) for t, d in todo]
                for fut in as_completed(futs):
                    r = fut.result()
                    with lock:
                        results.append(r)
                        done[0] += 1
                    item_cb(r)
                    progress(done[0], total, os.path.basename(r[0].path))
            return results

        res = run_task(self, "Konvertiere …", job)
        if res is None:
            return
        self.results = res
        ok = [r for r in res if r[1] and not r[2]]
        warn = [r for r in res if r[1] and r[2]]
        skipped = [r for r in res if not r[1] and r[2].startswith("übersprungen")]
        failed = [r for r in res if not r[1] and not r[2].startswith("übersprungen")]
        lines = [f"✓ {len(ok)} erfolgreich konvertiert"]
        if warn:
            lines.append(f"⚠ {len(warn)} mit Hinweisen")
        if skipped:
            lines.append(f"↷ {len(skipped)} übersprungen")
        if failed:
            lines.append(f"✗ {len(failed)} fehlgeschlagen:")
            lines += [f"   {os.path.basename(t.path)}: {e[:160]}" for t, _d, e in failed[:8]]
        QMessageBox.information(self, "Konvertierung abgeschlossen", "\n".join(lines))
        self.accept()

    @property
    def add_to_library(self):
        return self.cb_add.isChecked()

    @property
    def originals_deleted(self):
        return self.cb_del.isChecked()
