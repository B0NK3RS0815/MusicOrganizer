"""Dialog „Lautstärke angleichen“: Zielpegel und Verfahren wählen, Vorschau je Titel."""
import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QTableView, QVBoxLayout)  # noqa: F401

from mog.core import loudness as L

from .dialogs import primary
from .icons import icon
from .theme import C

PRESETS = [("auto", "Automatisch – optimal für diese Auswahl"),
           (-9.0, "−9 LUFS – laut (Club)"),
           (-11.0, "−11 LUFS"),
           (-14.0, "−14 LUFS – Streaming-Standard"),
           (-18.0, "−18 LUFS – ReplayGain-Standard"),
           ("custom", "Eigener Wert")]

MODE_FILE = "file"
MODE_RG = "rg"


def _db(v, sign=False):
    if v is None:
        return ""
    s = f"{v:+.1f}" if sign else f"{v:.1f}"
    return s.replace(".", ",").replace("-", "−")


class PlanModel(QAbstractTableModel):
    HEAD = ["Artist", "Titel", "Format", "Jetzt (LUFS)", "True Peak", "Änderung", "Danach", "Weg / Hinweis"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []      # dict(track, lufs, peak, method, gain, note, skip)

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
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
        r = self.rows[index.row()]
        c = index.column()
        t = r["track"]
        if role == Qt.DisplayRole:
            if c == 0:
                return t.display_artist
            if c == 1:
                return t.display_title
            if c == 2:
                return t.fmt
            if c == 3:
                return _db(r["lufs"])
            if c == 4:
                return _db(r["peak"])
            if c == 5:
                return "" if r["skip"] else ("±0" if not r["gain"] else _db(r["gain"], sign=True) + " dB")
            if c == 6:
                return "" if r["skip"] or r["lufs"] is None else _db(r["lufs"] + r["gain"])
            if c == 7:
                return r["note"]
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignRight if 3 <= c <= 6 else Qt.AlignCenter if c == 2 else Qt.AlignLeft)
                       | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if r["skip"]:
                return QColor(C["text3"])
            if c == 5 and r["gain"]:
                return QColor(C["ok"] if r["gain"] > 0 else C["accent2"])
            if c == 7 and r.get("warn"):
                return QColor(C["accent2"])
            if c in (2, 3, 4, 6, 7):
                return QColor(C["text2"])
        return None


class LoudnessDialog(QDialog):
    def __init__(self, tracks, loud, settings, rb_ids=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lautstärke angleichen")
        self.resize(1080, 700)
        self.s = settings
        self.tracks = tracks
        self.loud = loud
        self.rb_ids = set(rb_ids)
        self.plan = []
        self.mode = MODE_FILE
        self.backup_dir = ""

        lay = QVBoxLayout(self)
        intro = QLabel("MOG misst die Lautheit nach EBU R128 und gleicht die Titel auf einen gemeinsamen Pegel an. "
                       "Die Peak-Grenze verhindert Übersteuern: Leise Titel mit hohen Spitzen werden nur so weit "
                       "angehoben, wie es ohne Verzerrung geht.")
        intro.setWordWrap(True)
        intro.setObjectName("Hint")
        lay.addWidget(intro)

        top = QHBoxLayout()
        # --- Verfahren
        g1 = QGroupBox("Verfahren")
        v1 = QVBoxLayout(g1)
        self.rb_file = QRadioButton("Pegel in den Dateien ändern (empfohlen – wirkt überall, auch in rekordbox)")
        self.rb_rg = QRadioButton("Nur ReplayGain-Tags schreiben (Dateien bleiben unverändert)")
        self.grp = QButtonGroup(self)
        self.grp.addButton(self.rb_file)
        self.grp.addButton(self.rb_rg)
        v1.addWidget(self.rb_file)
        v1.addWidget(self.rb_rg)
        self.cb_reencode = QCheckBox("AAC, OGG und WMA neu kodieren (mit Qualitätsverlust)")
        self.cb_reencode.setToolTip("Für diese Formate gibt es keinen verlustfreien Weg. Ohne Haken werden sie "
                                    "übersprungen.")
        v1.addWidget(self.cb_reencode)
        how = QLabel("MP3: verlustfrei in 1,5-dB-Schritten · WAV/AIFF: direkt in der Datei · FLAC/ALAC: verlustfrei "
                     "neu kodiert · Opus: verlustfrei über den Kopf. Tags, Cover und Cue-Punkte bleiben erhalten.")
        how.setWordWrap(True)
        how.setObjectName("Muted")
        v1.addWidget(how)
        v1.addStretch()
        top.addWidget(g1, 3)

        # --- Zielpegel
        g2 = QGroupBox("Zielpegel")
        f2 = QFormLayout(g2)
        self.cmb_target = QComboBox()
        for key, label in PRESETS:
            self.cmb_target.addItem(label, key)
        f2.addRow("Ziel:", self.cmb_target)
        self.sp_target = QDoubleSpinBox()
        self.sp_target.setRange(-30.0, -5.0)
        self.sp_target.setSingleStep(0.5)
        self.sp_target.setDecimals(1)
        self.sp_target.setSuffix(" LUFS")
        f2.addRow("Wert:", self.sp_target)
        self.sp_ceiling = QDoubleSpinBox()
        self.sp_ceiling.setRange(-6.0, 0.0)
        self.sp_ceiling.setSingleStep(0.1)
        self.sp_ceiling.setDecimals(1)
        self.sp_ceiling.setSuffix(" dBTP")
        self.sp_ceiling.setToolTip("Höchster erlaubter True Peak nach dem Angleichen (−1 dBTP ist üblich).")
        f2.addRow("Peak-Grenze:", self.sp_ceiling)
        self.cb_down = QCheckBox("Nur leiser machen, nie lauter")
        f2.addRow("", self.cb_down)
        self.lbl_rg = QLabel("ReplayGain bezieht sich immer auf −18 LUFS – Player und Software gleichen "
                             "beim Abspielen selbst an.")
        self.lbl_rg.setWordWrap(True)
        self.lbl_rg.setObjectName("Muted")
        f2.addRow(self.lbl_rg)
        top.addWidget(g2, 2)
        lay.addLayout(top)

        # --- Vorschau
        self.model = PlanModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate([180, 230, 60, 90, 80, 84, 70]):
            self.table.setColumnWidth(i, w)
        lay.addWidget(self.table, 1)

        self.lbl_sum = QLabel("")
        self.lbl_sum.setWordWrap(True)
        lay.addWidget(self.lbl_sum)
        self.lbl_rb = QLabel("")
        self.lbl_rb.setWordWrap(True)
        self.lbl_rb.setObjectName("Warning")
        lay.addWidget(self.lbl_rb)

        # --- Sicherung
        bk = QHBoxLayout()
        self.cb_backup = QCheckBox("Originale vorher sichern nach:")
        self.ed_backup = QLineEdit()
        self.ed_backup.setPlaceholderText("Ordner für Sicherungskopien")
        b_choose = QPushButton(icon("folder"), "")
        b_choose.setToolTip("Ordner wählen")
        b_choose.clicked.connect(lambda: self._choose_backup())
        bk.addWidget(self.cb_backup)
        bk.addWidget(self.ed_backup, 1)
        bk.addWidget(b_choose)
        lay.addLayout(bk)

        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.b_ok = primary(QPushButton("Angleichen"))
        bb.addButton(self.b_ok, QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        # --- Gespeicherte Einstellungen
        mode = self.s.value("loud/mode", MODE_FILE)
        (self.rb_rg if mode == MODE_RG else self.rb_file).setChecked(True)
        self.cb_reencode.setChecked(str(self.s.value("loud/reencode", "false")).lower() == "true")
        tm = self.s.value("loud/target_mode", "auto")
        idx = self.cmb_target.findData(tm if tm in ("auto", "custom") else float(tm))
        self.cmb_target.setCurrentIndex(max(0, idx))
        self.sp_target.setValue(float(self.s.value("loud/target", -14.0)))
        self.sp_ceiling.setValue(float(self.s.value("loud/ceiling", -1.0)))
        self.cb_down.setChecked(str(self.s.value("loud/only_down", "false")).lower() == "true")
        self.ed_backup.setText(self.s.value("loud/backup_dir", ""))
        self.cb_backup.setChecked(str(self.s.value("loud/backup", "false")).lower() == "true")

        for w in (self.rb_file, self.rb_rg, self.cb_reencode, self.cb_down):
            w.toggled.connect(lambda *_: self._recompute())
        self.cmb_target.currentIndexChanged.connect(lambda *_: self._target_changed())
        self.sp_target.valueChanged.connect(lambda *_: self._recompute())
        self.sp_ceiling.valueChanged.connect(lambda *_: self._recompute())
        self._target_changed()

    # ------------------------------------------------------------------
    def _choose_backup(self):
        d = QFileDialog.getExistingDirectory(self, "Ordner für Sicherungskopien", self.ed_backup.text() or "")
        if d:
            self.ed_backup.setText(d)
            self.cb_backup.setChecked(True)

    def _measured(self):
        out = []
        for t in self.tracks:
            v = self.loud.get(t.id)
            if v and v[0] is not None:
                out.append((v[0], v[1]))
        return out

    def _target_changed(self):
        key = self.cmb_target.currentData()
        if key == "auto":
            self.sp_target.blockSignals(True)
            self.sp_target.setValue(L.auto_target(self._measured(), self.sp_ceiling.value()))
            self.sp_target.blockSignals(False)
        elif key != "custom":
            self.sp_target.blockSignals(True)
            self.sp_target.setValue(float(key))
            self.sp_target.blockSignals(False)
        self.sp_target.setEnabled(key == "custom")
        self._recompute()

    def _recompute(self):
        rg = self.rb_rg.isChecked()
        self.mode = MODE_RG if rg else MODE_FILE
        for w in (self.cmb_target, self.sp_ceiling, self.cb_down, self.cb_reencode, self.cb_backup, self.ed_backup):
            w.setEnabled(not rg)
        self.sp_target.setEnabled(not rg and self.cmb_target.currentData() == "custom")
        self.lbl_rg.setVisible(rg)
        if self.cmb_target.currentData() == "auto" and not rg:
            self.sp_target.blockSignals(True)
            self.sp_target.setValue(L.auto_target(self._measured(), self.sp_ceiling.value()))
            self.sp_target.blockSignals(False)
        target = self.sp_target.value()
        ceiling = self.sp_ceiling.value()
        only_down = self.cb_down.isChecked()
        reencode = self.cb_reencode.isChecked()
        rows = []
        up = down = same = skip = limited = 0
        for t in self.tracks:
            v = self.loud.get(t.id)
            lufs, peak = (v[0], v[1]) if v else (None, None)
            row = {"track": t, "lufs": lufs, "peak": peak, "gain": 0.0, "note": "", "skip": False,
                   "method": L.M_NONE}
            if lufs is None:
                row.update(skip=True, note="nicht gemessen")
            elif t.missing:
                row.update(skip=True, note="Datei nicht erreichbar")
            elif rg:
                row["gain"] = round(L.REPLAYGAIN_REF - lufs, 2)
                row["note"] = "ReplayGain-Tag" if t.fmt != "OPUS" else "R128-Tag (Opus)"
                row["method"] = "rg"
            else:
                m = L.method_for(t.fmt, reencode)
                if m == L.M_NONE:
                    why = "nur mit Neukodierung möglich" if t.fmt in ("AAC", "OGG", "WMA") else \
                        f"für {t.fmt} nicht möglich"
                    row.update(skip=True, note=why)
                else:
                    gain, note = L.plan_gain(lufs, peak, target, ceiling, m, only_down)
                    row["gain"], row["method"] = gain, m
                    txt = L.METHOD_LABEL[m]
                    if note == "peak":
                        txt += " · durch Peak-Grenze begrenzt"
                        row["warn"] = True
                        limited += 1
                    elif note == "down":
                        txt += " · nur leiser erlaubt"
                    elif note == "step":
                        txt += " · nächster 1,5-dB-Schritt"
                    row["note"] = txt
            if row["skip"]:
                skip += 1
            elif not row["gain"]:
                same += 1
            elif row["gain"] > 0:
                up += 1
            else:
                down += 1
            rows.append(row)
        self.model.set_rows(rows)
        self.plan = [r for r in rows if not r["skip"] and (r["gain"] or rg)]
        if rg:
            self.lbl_sum.setText(f"{len(self.plan)} Titel erhalten ReplayGain-Tags" +
                                 (f" · {skip} übersprungen" if skip else ""))
        else:
            parts = [f"Ziel {_db(target)} LUFS", f"{up} lauter", f"{down} leiser", f"{same} unverändert"]
            if skip:
                parts.append(f"{skip} übersprungen")
            if limited:
                parts.append(f"{limited} durch die Peak-Grenze begrenzt")
            self.lbl_sum.setText(" · ".join(parts))
        n_rb = sum(1 for r in self.plan if r["track"].id in self.rb_ids) if not rg else 0
        self.lbl_rb.setVisible(bool(n_rb))
        self.lbl_rb.setText(f"⚠ {n_rb} der Titel stecken in rekordbox. Danach dort neu analysieren lassen "
                            "(Titel markieren → Rechtsklick → „Titel analysieren“), damit Wellenform und Auto Gain "
                            "stimmen. Cue-Punkte bleiben erhalten." if n_rb else "")
        self.b_ok.setEnabled(bool(self.plan))
        self.b_ok.setText("ReplayGain schreiben" if rg else f"Angleichen ({len(self.plan)})")

    def _accept(self):
        if not self.plan:
            return
        if self.mode == MODE_FILE and self.cb_backup.isChecked():
            d = self.ed_backup.text().strip()
            if not d:
                self._choose_backup()
                d = self.ed_backup.text().strip()
                if not d:
                    return
            self.backup_dir = d
        s = self.s
        s.set("loud/mode", self.mode)
        s.set("loud/reencode", "true" if self.cb_reencode.isChecked() else "false")
        key = self.cmb_target.currentData()
        s.set("loud/target_mode", key if key in ("auto", "custom") else str(key))
        s.set("loud/target", self.sp_target.value())
        s.set("loud/ceiling", self.sp_ceiling.value())
        s.set("loud/only_down", "true" if self.cb_down.isChecked() else "false")
        s.set("loud/backup", "true" if self.cb_backup.isChecked() else "false")
        s.set("loud/backup_dir", self.ed_backup.text().strip())
        self.accept()

    def plan_items(self):
        """[(track, method, gain)]"""
        return [(r["track"], r["method"], r["gain"]) for r in self.plan]


def backup_target(backup_dir, path):
    """Pfad für die Sicherungskopie (vorhandene Dateien werden nicht überschrieben)."""
    base = os.path.join(backup_dir, os.path.basename(path))
    if not os.path.exists(base):
        return base
    stem, ext = os.path.splitext(base)
    i = 2
    while os.path.exists(f"{stem} ({i}){ext}"):
        i += 1
    return f"{stem} ({i}){ext}"
