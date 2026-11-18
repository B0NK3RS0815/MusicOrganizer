"""Oberflächentest der Neuerungen in 0.3.0 (rekordbox, Tonart, Wellenform, Hell/Dunkel, Duplikate).

Aufruf: QT_QPA_PLATFORM=offscreen MOG_NO_AUDIO=1 python tests/ui_v030.py <samples> <ausgabe> [master.db-ordner]
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

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

QCoreApplication.setOrganizationName("MOG-Test")
QCoreApplication.setApplicationName("MusicOrganizer-Test3")
from mog import applog  # noqa: E402
applog.setup(tmp, "test")
from mog.core.paths import resource  # noqa: E402
from mog.ui import theme  # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
theme.apply(app, "dark", resource("check.svg"), resource("chevron.svg"))

from mog.core import encoder, rekordbox as rbmod, waveform  # noqa: E402
from mog.ui.main_window import MainWindow  # noqa: E402
from mog.ui.track_model import COL_INDEX  # noqa: E402


def pump(n=60):
    for _ in range(n):
        app.processEvents()


w = MainWindow()
w.s.set("update/auto", False)
w.resize(1440, 860)
w.show()
w.start_scan([samples])
w.scan_thread.wait(60000)
pump()
assert not w.table.isColumnHidden(COL_INDEX["key"]), "Tonart-Spalte sollte sichtbar sein"

# --- Tonart analysieren (alle Titel)
w.table.selectAll()
pump()
w.analyze_key()
pump()
keys = {t.filename: t.key for t in w.model.all}
assert sum(1 for k in keys.values() if k) >= 10, keys
assert all(k == "" or k[:-1].isdigit() for k in keys.values()), keys      # Camelot-Schreibweise
print("Tonart OK:", sorted(set(keys.values()))[:8], "vorgemerkt:", len(w.model.pending))

# --- Wellenform (ohne Audiogerät direkt berechnen und anzeigen)
t0 = next(t for t in w.model.all if t.filename == "DJ Nova - Midnight Drive.mp3")
ff = encoder.find_ffmpeg()
w.player.track = t0
w.player.lbl_title.setText(t0.display_title)
w.player.lbl_artist.setText(t0.display_artist)
w.player.seek.setRange(0, int(t0.duration * 1000))
w.player.seek.setValue(int(t0.duration * 380))
w.player.seek.set_data(waveform.compute(ff, t0.path))
w.table.clearSelection()
w.table.selectRow(w.model.row_for_id(t0.id))
pump()
w.grab().save(os.path.join(out, "01_dark_main.png"))

# --- rekordbox XML: neu, Playlist, Titel aus MOG hinzufügen, speichern
w.set_rekordbox(rbmod.XmlLibrary.new("0.3.0"))
rbw = w.open_rekordbox()
lib = w.rb
fo = lib.create_folder(None, "Gigs")
pl = lib.create_playlist(fo, "Samstag Club")
w._rb_add(w.model.all[:5], pl)
lib.create_playlist(None, "Warm-up")
rbw.current = pl
rbw.refresh()
rbw.resize(1180, 640)
pump()
assert len(pl.tracks) == 5 and lib.dirty
assert not w.table.isColumnHidden(COL_INDEX["rb"])
assert len(w.model.rb_info) == 5, len(w.model.rb_info)
rbw.grab().save(os.path.join(out, "02_rekordbox_xml.png"))
xml_path = os.path.join(tmp, "mog-test.xml")
lib.save(xml_path)
assert rbmod.XmlLibrary.load(xml_path).playlists()[0].path_name() == "Gigs / Samstag Club"
print("rekordbox-XML OK:", xml_path)

# --- Umbenennen zieht rekordbox-Pfad mit
from mog.core import fileops  # noqa: E402
t_in = next(t for t in w.model.all if t.id in w.model.rb_info)
old = t_in.path
okr, new, _m = fileops.rename_file(old, "Umbenannt fuer rekordbox")
assert okr
w.lib.rename_path(t_in.id, new)
assert lib.update_path(old, new)
t_in.path = new
w.rekordbox_changed()
assert t_in.id in w.model.rb_info and lib.track_for_path(new) is not None
print("Umbenennen + rekordbox-Pfad OK")

# --- Duplikat-Dialog: Spalten, Regel „älteste“, „Kein Duplikat“
from mog.ui.duplicates_dialog import COL_CREATED, DuplicatesDialog, HEADERS  # noqa: E402
assert HEADERS[1:6] == ["Artist", "Titel", "Länge", "kbps", "Erstellt"], HEADERS
dd = DuplicatesDialog(w.model.all, w.s, w.db_path, w, rb_info=w.model.rb_info)
dd.cb_tags.setChecked(True)
dd.cb_ident.setChecked(True)
dd.search()
assert dd.groups, "keine Duplikatgruppen"
n_groups = len(dd.groups)
dd.cmb_rule.setCurrentIndex(dd.cmb_rule.findData("oldest"))
dd.auto_mark()
first = dd.tree.topLevelItem(0).child(0)
assert first.text(COL_CREATED), "Erstellungsdatum fehlt"
dd.resize(1260, 700)
dd.show()
pump()
dd.grab().save(os.path.join(out, "03_duplicates.png"))
dd.tree.setCurrentItem(dd.tree.topLevelItem(0))
dd.tree.topLevelItem(0).setSelected(True)
dd._ignore_selected()
assert len(dd.groups) == n_groups - 1
dd.search()
assert len(dd.groups) == n_groups - 1, "ausgeblendete Gruppe taucht wieder auf"
print(f"Duplikate OK: {n_groups} Gruppen, „Kein Duplikat“ bleibt gemerkt")

# --- Verschieben statt Löschen
dd.auto_mark()
marked = dd.marked()
assert marked, "nichts markiert"
quarantine = os.path.join(tmp, "Duplikate pruefen")
moved_ids = w._move_tracks(marked[:1], quarantine)
assert len(moved_ids) == 1 and os.listdir(quarantine)
assert moved_ids[0] not in w.model.by_id
dd.close()
print("Verschieben OK:", os.listdir(quarantine))

# --- Lösch-Dialog mit rekordbox-Hinweis
from mog.ui.dialogs import DeleteDialog  # noqa: E402
t_rb = [t for t in w.model.all if t.id in w.model.rb_info][:2]
info = {p: pl for p, (_i, pl) in w.rb.info_for_paths([t.path for t in t_rb]).items()}
deld = DeleteDialog(t_rb, False, w, rb_info=info, rb_kind="xml")
deld.show()
pump()
assert deld.remove_from_rekordbox
deld.grab().save(os.path.join(out, "04_delete_rekordbox.png"))
deld.close()

# --- Hell
w.set_theme("light")
pump()
assert theme.is_light()
w.grab().save(os.path.join(out, "05_light_main.png"))
rbw.refresh()
pump()
rbw.grab().save(os.path.join(out, "06_light_rekordbox.png"))
from mog.ui.dialogs import SettingsDialog  # noqa: E402
sd = SettingsDialog(w.s, w)
sd.show()
pump()
sd.grab().save(os.path.join(out, "07_light_settings.png"))
sd.close()
w.set_theme("dark")
pump()
assert not theme.is_light()
print("Hell/Dunkel OK")

# --- rekordbox-Datenbank (Test-master.db)
if db_dir:
    d = os.path.join(tmp, "rbdb")
    shutil.copytree(db_dir, d)
    dbl = rbmod.DbLibrary.load(os.path.join(d, "master.db"), os.path.join(tmp, "rb-backups"))
    w.set_rekordbox(dbl)
    rbw.cmb.setCurrentIndex(rbw.cmb.findData(rbmod.DB))
    p2 = dbl.create_playlist(None, "MOG aus Datenbank")
    w._rb_add([t for t in w.model.all if t.fmt in ("MP3", "FLAC")][:3], p2)
    rbw.current = p2
    rbw.refresh()
    pump()
    rbw.grab().save(os.path.join(out, "08_rekordbox_db.png"))
    assert len(p2.tracks) == 3
    backup = dbl.save()
    assert os.path.exists(os.path.join(backup, "master.db"))
    dbl.close()
    re = rbmod.DbLibrary.load(os.path.join(d, "master.db"))
    assert any(n.name == "MOG aus Datenbank" and len(n.tracks) == 3 for n in re.playlists())
    re.close()
    w.rb = None
    print("rekordbox-Datenbank OK (Sicherung:", os.path.basename(backup) + ")")

rbw.close()
w.lib.discard_pending()
w._closing_ok = True
w.close()
print("UI-Test 0.3.0 OK")
