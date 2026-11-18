"""Tests der rekordbox-Anbindung (XML immer, Datenbank wenn eine Test-master.db angegeben ist).

Aufruf: python tests/test_rekordbox.py <samples-ordner> [rekordbox-test.xml] [master.db-ordner]
"""
import glob
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mog.core import tags  # noqa: E402
from mog.core.rekordbox import (DbLibrary, XmlLibrary, location_to_path, norm_path,  # noqa: E402
                                path_to_location)

samples = sys.argv[1]
ext_xml = sys.argv[2] if len(sys.argv) > 2 else None
db_dir = sys.argv[3] if len(sys.argv) > 3 else None
work = tempfile.mkdtemp()
files = sorted(f for f in glob.glob(os.path.join(samples, "**", "*.mp3"), recursive=True)
               if not os.path.basename(f).startswith("._"))
mog_tracks = [tags.read_track(f) for f in files[:4]]

# --- Pfad <-> Location ------------------------------------------------------
for p in ("C:\\Music\\Ärzte & Co\\01 Track #1.mp3", "/Volumes/SSD/Music/Tiësto - Adagio.flac"):
    loc = path_to_location(p)
    back = location_to_path(loc)
    assert norm_path(back) == norm_path(p), (p, loc, back)
print("Location-Umwandlung OK:", path_to_location("/Volumes/SSD/a b.mp3"))

# --- XML: neu anlegen, bearbeiten, speichern, wieder laden ------------------
x = XmlLibrary.new("0.3.0")
f = x.create_folder(None, "Gigs")
pl = x.create_playlist(f, "Samstag")
ids = [x.ensure_track(t).id for t in mog_tracks]
assert x.ensure_track(mog_tracks[0]).id == ids[0], "doppelt angelegt"
x.add_to_playlist(pl, ids)
x.move_in_playlist(pl, ids[2], 0)
x.update_track(ids[0], bpm=124.0, key="8A", rating=4, comment="Opener")
x.rename(pl, "Samstag Club")
pl2 = x.create_playlist(None, "Zu löschen")
x.delete(pl2)
new_path = mog_tracks[1].path + ".renamed.mp3"
assert x.update_path(mog_tracks[1].path, new_path)
out = os.path.join(work, "mog.xml")
x.save(out)
y = XmlLibrary.load(out)
pls = y.playlists()
assert [p.name for p in pls] == ["Samstag Club"], [p.name for p in pls]
assert pls[0].parent.name == "Gigs"
assert pls[0].tracks[0] == ids[2] and len(pls[0].tracks) == len(ids)
t0 = y.tracks[ids[0]]
assert t0.bpm == 124.0 and t0.key == "8A" and t0.rating == 4 and t0.comment == "Opener", t0
assert y.track_for_path(new_path) is not None and y.track_for_path(mog_tracks[1].path) is None
info = y.info_for_paths([mog_tracks[0].path])
assert info[mog_tracks[0].path][1] == ["Gigs / Samstag Club"], info
print("XML neu/bearbeiten/speichern/laden OK:", len(y.tracks), "Titel,", [p.path_name() for p in pls])

# --- Echte rekordbox-XML: unbekannte Inhalte müssen erhalten bleiben ------------
if ext_xml:
    src = os.path.join(work, "rb.xml")
    shutil.copy(ext_xml, src)
    r = XmlLibrary.load(src)
    n_tracks, n_pl = len(r.tracks), len(r.playlists())
    raw_before = open(src, encoding="utf-8").read()
    marks_before = raw_before.count("<POSITION_MARK") + raw_before.count("<TEMPO")
    r.create_playlist(None, "MOG neu")
    r.save()
    raw_after = open(src, encoding="utf-8").read()
    marks_after = raw_after.count("<POSITION_MARK") + raw_after.count("<TEMPO")
    r2 = XmlLibrary.load(src)
    assert len(r2.tracks) == n_tracks and len(r2.playlists()) == n_pl + 1
    assert marks_before == marks_after, (marks_before, marks_after)
    print(f"Echte rekordbox-XML OK: {n_tracks} Titel, {n_pl} Playlists, {marks_after} Cue/Tempo-Einträge erhalten")

# --- Datenbank (master.db) ----------------------------------------------------
if db_dir:
    d = os.path.join(work, "rbdb")
    shutil.copytree(db_dir, d)
    music = os.path.join(work, "music")
    os.makedirs(music)
    copies = []
    for t in mog_tracks[:3]:
        dst = os.path.join(music, os.path.basename(t.path))
        shutil.copy(t.path, dst)
        copies.append(tags.read_track(dst))
    lib = DbLibrary.load(os.path.join(d, "master.db"), backup_dir=os.path.join(work, "backups"))
    n0 = len(lib.tracks)
    fo = lib.create_folder(None, "MOG Ordner")
    p = lib.create_playlist(fo, "MOG Playlist")
    tids = [lib.ensure_track(t).id for t in copies]
    lib.add_to_playlist(p, tids)
    lib.move_in_playlist(p, tids[2], 0)
    lib.update_track(tids[0], artist="DJ Test", genre="House", bpm=126.0, rating=3, comment="aus MOG", key="8A")
    lib.rename(p, "MOG Playlist 2")
    moved = copies[1].path + ".x.mp3"
    os.rename(copies[1].path, moved)
    assert lib.update_path(copies[1].path, moved)
    backup = lib.save()
    assert os.path.exists(os.path.join(backup, "master.db")), backup
    lib.close()
    lib2 = DbLibrary.load(os.path.join(d, "master.db"))
    pl = next(n for n in lib2.playlists() if n.name == "MOG Playlist 2")
    assert pl.parent.name == "MOG Ordner"
    assert pl.tracks[0] == tids[2] and len(pl.tracks) == 3, pl.tracks
    tt = lib2.tracks[tids[0]]
    assert tt.artist == "DJ Test" and tt.genre == "House" and tt.bpm == 126.0 and tt.rating == 3, tt
    assert tt.key == "8A", tt.key
    assert lib2.track_for_path(moved) is not None
    assert len(lib2.tracks) == n0 + 3
    # Verwerfen
    lib2.create_playlist(None, "verwerfen")
    lib2.discard()
    assert not any(n.name == "verwerfen" for n in lib2.playlists())
    lib2.close()
    print(f"Datenbank OK: {n0}+3 Titel, Playlist {pl.path_name()}, Sicherung angelegt, Verwerfen OK")

shutil.rmtree(work)
print("rekordbox-Tests OK")
