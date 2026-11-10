"""Startet MOG ohne Bildschirm, testet die Oberfläche und speichert Screenshots.

Aufruf: QT_QPA_PLATFORM=offscreen MOG_NO_AUDIO=1 python tests/ui_smoke.py <samples-ordner> <ausgabe-ordner>
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src_samples, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
samples = os.path.join(tmp, "samples")
shutil.copytree(src_samples, samples)          # Kopie, da Dateien umbenannt/geändert werden
os.environ["XDG_DATA_HOME"] = tmp
os.environ["XDG_CONFIG_HOME"] = tmp

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

QCoreApplication.setOrganizationName("MOG-Test")
QCoreApplication.setApplicationName("MusicOrganizer-Test")
from mog import applog  # noqa: E402
applog.setup(tmp, "test")

from mog.core.paths import resource  # noqa: E402
from mog.ui import theme  # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setPalette(theme.palette())
app.setStyleSheet(theme.stylesheet(resource("check.svg"), resource("chevron.svg")))
from mog.app import _load_translations  # noqa: E402
_load_translations(app)

from mog.ui.main_window import MainWindow  # noqa: E402
from mog.ui.track_model import COL_INDEX  # noqa: E402

w = MainWindow()
w.s.set("update/auto", False)
w.resize(1440, 860)
w.show()
app.processEvents()
w.grab().save(os.path.join(out, "01_empty.png"))


def pump(n=50):
    for _ in range(n):
        app.processEvents()


w.start_scan([samples])
w.scan_thread.wait(60000)
pump()
assert len(w.model.all) >= 13, len(w.model.all)

# --- Sortierung
w.table.sortByColumn(COL_INDEX["bitrate"], Qt.DescendingOrder)
kb = [t.bitrate for t in w.model.view]
assert kb == sorted(kb, reverse=True), kb
w.table.sortByColumn(COL_INDEX["artist"], Qt.AscendingOrder)
print("Sortierung OK")

# --- Spalten: Breite ändern & verschieben (Titel vor Artist)
hh = w.table.horizontalHeader()
hh.resizeSection(COL_INDEX["artist"], 300)
assert hh.sectionSize(COL_INDEX["artist"]) == 300
hh.resizeSection(COL_INDEX["title"], 280)
assert hh.sectionSize(COL_INDEX["title"]) == 280
w._move_column(COL_INDEX["title"], -1)
assert hh.visualIndex(COL_INDEX["title"]) == 0, hh.visualIndex(COL_INDEX["title"])
w._move_column(COL_INDEX["title"], 1)
assert hh.visualIndex(COL_INDEX["artist"]) == 0
print("Spalten OK (Breite + Reihenfolge)")

# --- Vormerken: BPM + Artist ändern, Liste zeigt sofort an, Datei bleibt unverändert
from mog.core import tags as tagio  # noqa: E402
t_nova = next(t for t in w.model.all if t.filename == "DJ Nova - Midnight Drive.mp3")
t_wav = next(t for t in w.model.all if t.filename == "track01.wav")
w.stage_changes([(t_nova, {"bpm": "124"}, None, False),
                 (t_wav, {"artist": "DJ Nova", "title": "Midnight Drive (WAV)"}, None, False)])
assert t_nova.bpm == 124.0 and t_wav.artist == "DJ Nova"
assert tagio.read_tags(t_nova.path)[0]["bpm"] == "", "Datei darf noch nicht geändert sein"
assert w.btn_save.isEnabled() and "2" in w.btn_save.text()
w.table.selectRow(w.model.row_for_id(t_nova.id))
pump()
w.grab().save(os.path.join(out, "02_library_pending.png"))
print("Vormerken OK:", w.btn_save.text())

# --- Dialoge rendern
from mog.ui.tag_editor import TagEditor  # noqa: E402
from mog.ui.rename_dialog import RenameDialog  # noqa: E402
from mog.ui.dialogs import SettingsDialog  # noqa: E402
from mog.ui.update_dialog import UpdateDialog  # noqa: E402

d = TagEditor([t_nova], w.cover_for, w)
assert d.edits["bpm"].text() == "124", d.edits["bpm"].text()   # zeigt vorgemerkten Wert
d.show(); pump(); d.grab().save(os.path.join(out, "03_tageditor.png")); d.close()

rd = RenameDialog(w.model.view[:6], w.s, w)
rd.cmb.setCurrentText("%artist% - %title% (%bpm% BPM)")
rd.apply_pattern()
rd.show(); pump(); rd.grab().save(os.path.join(out, "04_rename.png"))
rd._accept()
print("Umbenennen geplant:", [(t.filename, n) for t, n in rd.renames][:3])
rd.close()

# Umbenennen ausführen (ohne Dialog)
from mog.core import fileops  # noqa: E402
old = t_nova.path
ok, new, msg = fileops.rename_file(t_nova.path, "DJ Nova - Midnight Drive (124 BPM)")
assert ok and os.path.exists(new) and not os.path.exists(old), msg
w.lib.rename_path(t_nova.id, new)
t_nova.path = new
w.model.upsert([t_nova])
print("Umbenennen OK:", os.path.basename(new))

sd = SettingsDialog(w.s, w)
sd.show(); pump()
tabs = sd.findChild(type(sd.findChildren(object)[0]).__mro__[0]) if False else None
from PySide6.QtWidgets import QTabWidget  # noqa: E402
tw = sd.findChild(QTabWidget)
tw.setCurrentIndex(tw.count() - 2)   # Audio
pump(); sd.grab().save(os.path.join(out, "05_settings_audio.png")); sd.close()

info = {"version": "0.3.0", "tag": "v0.3.0", "page": "https://example.invalid",
        "notes": "## Neu\n- Beispiel-Hinweis\n- Noch einer", "assets": []}
ud = UpdateDialog(info, w.s, w)
ud.show(); pump(); ud.grab().save(os.path.join(out, "06_update.png")); ud.close()

# --- Speichern (wie beim Beenden) und prüfen, dass die Datei geschrieben wurde
# echter Klick auf den Knopf (übergibt wie in der App einen checked-Wert)
w.btn_save.click()
pump()
assert tagio.read_tags(t_nova.path)[0]["bpm"] == "124"
assert tagio.read_tags(t_wav.path)[0]["artist"] == "DJ Nova"
assert not w.btn_save.isEnabled()
print("Speichern per Knopf OK")

# --- Bibliothek leeren (ohne Rückfrage-Dialog)
w.lib.clear_all()
w.model.set_tracks([])
w._refresh_pending(); w._rebuild_sidebar(); w._update_counts()
assert w.lib.count() == 0 and w.empty.isVisible()
pump(); w.grab().save(os.path.join(out, "07_cleared.png"))
print("Leeren OK")

w._closing_ok = True
w.close()
print("UI-Test OK")
