"""Oberflächentest der Neuerungen in 1.1.0 (Lautheit, rekordbox verschieben/Bitrate, Update-Hinweis).

Aufruf: QT_QPA_PLATFORM=offscreen MOG_NO_AUDIO=1 python tests/ui_v110.py <samples> <ausgabe> [master.db-ordner]
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src_samples, out = sys.argv[1], sys.argv[2]
db_dir = sys.argv[3] if len(sys.argv) > 3 else None
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
samples = os.path.join(tmp, "samples")
shutil.copytree(src_samples, samples)
os.environ["XDG_DATA_HOME"] = tmp
os.environ["XDG_CONFIG_HOME"] = tmp

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402

QCoreApplication.setOrganizationName("MOG-Test")
QCoreApplication.setApplicationName("MusicOrganizer-Test110")
from mog import applog  # noqa: E402
applog.setup(tmp, "test")
from mog.core.paths import resource  # noqa: E402
from mog.ui import theme  # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
theme.apply(app, "dark", resource("check.svg"), resource("chevron.svg"))

from mog.core import encoder, loudness as L, rekordbox as rbmod  # noqa: E402
from mog.ui import main_window as mwmod  # noqa: E402
from mog.ui.main_window import MainWindow  # noqa: E402
from mog.ui.track_model import COL_INDEX  # noqa: E402

# Rückfragen automatisch beantworten
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: print("WARNUNG:", a[2] if len(a) > 2 else a) or QMessageBox.Ok)


def pump(n=60):
    for _ in range(n):
        app.processEvents()


w = MainWindow()
w.s.set("update/auto", False)
w.resize(1500, 860)
w.show()
w.start_scan([samples])
w.scan_thread.wait(60000)
pump()
ff = encoder.find_ffmpeg()

# --- Lautheit messen ----------------------------------------------------------
w.table.selectAll()
pump()
n = w.measure_loudness()
pump()
assert n >= 10, n
assert not w.table.isColumnHidden(COL_INDEX["lufs"])
vals = {t.filename: w.model.loud[t.id][0] for t in w.model.all if t.id in w.model.loud}
print(f"Lautheit gemessen: {n} Titel, z. B.", list(vals.items())[:3])
assert w.model.data(w.model.index(0, COL_INDEX["lufs"])), "Spalte Lautheit leer"

# --- Dialog: Vorschau und Angleichen --------------------------------------------
from mog.ui.loudness_dialog import LoudnessDialog  # noqa: E402
ts = [t for t in w.model.all if not t.missing]
dlg = LoudnessDialog(ts, w.model.loud, w.s, rb_ids=[], parent=w)
dlg.cmb_target.setCurrentIndex(dlg.cmb_target.findData(-14.0))
dlg.cb_reencode.setChecked(True)
dlg.resize(1180, 720)
dlg.show()
pump()
assert dlg.plan, "kein Plan"
dlg.grab().save(os.path.join(out, "01_loudness_dialog.png"))
auto = L.auto_target([(v[0], v[1]) for v in w.model.loud.values()], -1.0)
dlg.cmb_target.setCurrentIndex(dlg.cmb_target.findData("auto"))
pump()
assert abs(dlg.sp_target.value() - auto) < 0.05, (dlg.sp_target.value(), auto)
dlg.cmb_target.setCurrentIndex(dlg.cmb_target.findData("custom"))
dlg.sp_target.setValue(-25.0)
pump()
items = dlg.plan_items()
dlg.close()
mp3 = next(t for t, m, g in items if m == L.M_MP3 and g)
before = w.model.loud[mp3.id][0]
w._apply_loudness(items, "file", os.path.join(tmp, "backup"))
pump()
assert os.listdir(os.path.join(tmp, "backup")), "keine Sicherung"
lufs_after, _p, _l = L.measure(ff, mp3.path)
gain = w.model.loud[mp3.id][3]
assert abs((lufs_after - before) - gain) < 0.3, (before, lufs_after, gain)
print(f"Angleichen OK: {mp3.filename} {before:.1f} → {lufs_after:.1f} LUFS (Änderung {gain:+.1f} dB)")
w.grab().save(os.path.join(out, "02_main_lufs.png"))

# --- Zurücknehmen
w.table.clearSelection()
w.table.selectRow(w.model.row_for_id(mp3.id))
pump()
w.undo_loudness()
pump()
lufs_back, _p, _l = L.measure(ff, mp3.path)
assert abs(lufs_back - before) < 0.3 and not w.model.loud[mp3.id][3], (before, lufs_back)
print(f"Zurücknehmen OK: {lufs_back:.1f} LUFS")

# --- ReplayGain
flac = next(t for t in w.model.all if t.fmt == "FLAC")
w._apply_loudness([(flac, "rg", 0.0)], "rg", "")
import mutagen  # noqa: E402
assert mutagen.File(flac.path).tags.get("REPLAYGAIN_TRACK_GAIN"), "ReplayGain fehlt"
print("ReplayGain OK:", mutagen.File(flac.path).tags.get("REPLAYGAIN_TRACK_GAIN"))

# --- rekordbox: Bitrate + Verschieben/Kopieren -------------------------------------
w.set_rekordbox(rbmod.XmlLibrary.new("1.1.0"))
rbw = w.open_rekordbox()
lib = w.rb
a = lib.create_playlist(None, "Warm-up")
b = lib.create_playlist(None, "Peak Time")
mp3s = [t for t in w.model.all if t.fmt == "MP3"][:4]
w._rb_add(mp3s, a)
rbw.current = a
rbw.refresh()
pump()
from mog.ui.rekordbox_dialog import RBTrackModel  # noqa: E402
col = RBTrackModel.HEAD.index("kbps")
assert rbw.model.data(rbw.model.index(0, col)), "kbps leer"
print("Bitrate im rekordbox-Fenster:", [rbw.model.data(rbw.model.index(r, col)) for r in range(rbw.model.rowCount())])
rbw.table.selectRow(0)
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
rbw.table.selectionModel().select(rbw.model.index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
moved = [t.id for t in rbw._selected_tracks()]
assert len(moved) == 2
rbw._transfer(b, copy=False)
assert len(a.tracks) == 2 and len(b.tracks) == 2 and set(b.tracks) == set(moved), (a.tracks, b.tracks)
rbw.current = a
rbw.refresh()
rbw.table.selectRow(0)
rbw._transfer(b, copy=True)
assert len(a.tracks) == 2 and len(b.tracks) == 3
rbw._transfer(b, copy=True)            # schon drin → nicht doppelt
assert len(b.tracks) == 3
# Drag & Drop-Weg (Signal des Baums)
rbw.current = a
rbw.refresh()
rbw.tree.tracks_dropped.emit(b, [a.tracks[0]], False)
assert len(a.tracks) == 1 and len(b.tracks) == 3
rbw.resize(1250, 640)
rbw.current = b
rbw.refresh()
pump()
rbw.grab().save(os.path.join(out, "03_rekordbox_move.png"))
xml_path = os.path.join(tmp, "t.xml")
lib.save(xml_path)
re_ = rbmod.XmlLibrary.load(xml_path)
pb = next(n for n in re_.playlists() if n.name == "Peak Time")
assert len(pb.tracks) == 3 and all(re_.tracks[t].bitrate for t in pb.tracks)
print("rekordbox verschieben/kopieren OK (XML)")
if db_dir:
    d = os.path.join(tmp, "rbdb")
    shutil.copytree(db_dir, d)
    dbl = rbmod.DbLibrary.load(os.path.join(d, "master.db"), os.path.join(tmp, "rb-backups"))
    p1 = dbl.create_playlist(None, "DB A")
    p2 = dbl.create_playlist(None, "DB B")
    ids = [dbl.ensure_track(t).id for t in mp3s[:3]]
    dbl.add_to_playlist(p1, ids)
    dbl.move_tracks(p1, p2, ids[:2])
    dbl.save()
    dbl.close()
    re2 = rbmod.DbLibrary.load(os.path.join(d, "master.db"))
    q1 = next(n for n in re2.playlists() if n.name == "DB A")
    q2 = next(n for n in re2.playlists() if n.name == "DB B")
    assert len(q1.tracks) == 1 and len(q2.tracks) == 2, (q1.tracks, q2.tracks)
    assert all(re2.tracks[t].bitrate for t in q2.tracks), [re2.tracks[t].bitrate for t in q2.tracks]
    re2.close()
    print("rekordbox verschieben OK (Datenbank), Bitrate:", [re2.tracks[t].bitrate for t in q2.tracks])
rbw.close()
w.rb = None

# --- Update-Hinweis ---------------------------------------------------------------
shown = []
mwmod.UpdateDialog.exec = lambda self: shown.append(self.info["version"]) or QDialog.Rejected
info = {"version": "9.9.0", "tag": "v9.9.0", "notes": "Test", "page": "", "assets": []}
w._update_result(info, manual=False, startup=False)
pump()
assert w.header.update_pill.isVisible() and "9.9.0" in w.header.update_pill.text()
assert not shown, "kein Dialog mitten in der Arbeit"
w.grab().save(os.path.join(out, "04_update_pill.png"))
w.header.update_pill.click()
assert shown == ["9.9.0"]
w._update_result({"version": "9.9.1", "tag": "v9.9.1", "notes": "", "page": "", "assets": []},
                 manual=False, startup=True)
assert shown[-1] == "9.9.1", shown
w._update_result({"version": "0.0.1", "tag": "v0.0.1", "notes": "", "page": "", "assets": []},
                 manual=False)
assert not w.header.update_pill.isVisible()
print("Update-Hinweis OK")

from mog.ui.dialogs import SettingsDialog  # noqa: E402
sd = SettingsDialog(w.s, w)
sd.show()
pump()
sd.grab().save(os.path.join(out, "05_settings.png"))
assert sd.cmb_update.count() == 3
sd.close()

QTimer.singleShot(0, lambda: None)
w.lib.discard_pending()
w._closing_ok = True
w.close()
print("UI-Test 1.1.0 OK")
