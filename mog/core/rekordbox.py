"""Anbindung an rekordbox – zwei Varianten mit gemeinsamer Schnittstelle.

1. ``XmlLibrary``  – rekordbox-XML (offizielles Austauschformat). Sicher, aber kein Live-Abgleich:
   rekordbox exportiert die Sammlung als XML, MOG bearbeitet sie, rekordbox liest sie im Bereich
   „rekordbox xml“ wieder ein. Unbekannte Inhalte (Cue-Punkte, Beatgrid …) bleiben erhalten.
2. ``DbLibrary``   – direkter Zugriff auf die rekordbox-6/7-Datenbank ``master.db`` über
   *pyrekordbox*. Inoffiziell: rekordbox muss beim Speichern geschlossen sein, vor jedem
   Speichern legt MOG automatisch eine Sicherung an.

Beide Varianten arbeiten mit denselben einfachen Datenobjekten (RBTrack, RBNode) und merken
Änderungen vor, bis ``save()`` aufgerufen wird.
"""
import datetime
import logging
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import quote, unquote

log = logging.getLogger("mog.rekordbox")

XML = "xml"
DB = "db"


class RekordboxError(Exception):
    pass


# --------------------------------------------------------------------------
# Datenobjekte
# --------------------------------------------------------------------------
@dataclass
class RBTrack:
    id: str
    path: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    label: str = ""
    comment: str = ""
    bpm: float = None
    key: str = ""
    rating: int = 0          # 0–5 Sterne
    length: int = 0          # Sekunden
    year: str = ""

    EDITABLE = ("title", "artist", "album", "genre", "label", "comment", "bpm", "key", "rating", "year")


@dataclass
class RBNode:
    id: str
    name: str
    kind: str = "folder"            # "root" | "folder" | "playlist" | "smart"
    children: list = field(default_factory=list)
    tracks: list = field(default_factory=list)   # Track-IDs (Playlists)
    parent: "RBNode" = None

    @property
    def is_folder(self):
        return self.kind in ("root", "folder")

    @property
    def editable(self):
        return self.kind in ("folder", "playlist")

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def path_name(self):
        parts, n = [], self
        while n is not None and n.kind != "root":
            parts.append(n.name)
            n = n.parent
        return " / ".join(reversed(parts))


def norm_path(p):
    """Vergleichbarer Pfad (rekordbox speichert '/' – unter Windows ohne Groß/Klein-Unterschied)."""
    p = (p or "").replace("\\", "/").rstrip("/")
    if sys.platform.startswith("win") or re.match(r"^[A-Za-z]:/", p):
        p = p.lower()
    return p


def native_path(p):
    return p.replace("/", "\\") if sys.platform.startswith("win") else p


def rating_from_xml(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, round(v / 51)))


# --------------------------------------------------------------------------
# Gemeinsame Basis
# --------------------------------------------------------------------------
class RekordboxLibrary:
    kind = ""
    label = ""

    def __init__(self):
        self.tracks = {}
        self.root = RBNode("root", "rekordbox", "root")
        self.source = ""
        self.changes = 0
        self._path_index = {}

    # --- Abfragen ----------------------------------------------------------
    @property
    def dirty(self):
        return self.changes > 0

    def _touch(self, n=1):
        self.changes += n

    def _reindex(self):
        self._path_index = {norm_path(t.path): tid for tid, t in self.tracks.items() if t.path}

    def track_for_path(self, path):
        tid = self._path_index.get(norm_path(path))
        return self.tracks.get(tid) if tid else None

    def find(self, node_id):
        for n in self.root.walk():
            if n.id == node_id:
                return n
        return None

    def playlists(self):
        return [n for n in self.root.walk() if n.kind in ("playlist", "smart")]

    def membership(self):
        """{track_id: [playlist-Pfadnamen]} – für Hinweise in MOG."""
        out = {}
        for n in self.root.walk():
            if n.kind == "playlist":
                name = n.path_name()
                for tid in n.tracks:
                    out.setdefault(tid, []).append(name)
        return out

    def info_for_paths(self, paths):
        """{pfad: (in_sammlung, [playlists])} für MOG-Pfade."""
        mem = self.membership()
        out = {}
        for p in paths:
            t = self.track_for_path(p)
            if t is not None:
                out[p] = (True, mem.get(t.id, []))
        return out

    # --- Gemeinsame Hilfen --------------------------------------------------
    def _check_editable(self, node):
        if node is None or (node.kind != "root" and not node.editable):
            raise RekordboxError("Intelligente oder System-Playlists können nicht bearbeitet werden.")

    # Unterklassen implementieren:
    # create_folder, create_playlist, rename, delete, move_node, add_to_playlist, remove_from_playlist,
    # move_in_playlist, update_track, update_path, ensure_track, remove_track, save, discard


# --------------------------------------------------------------------------
# Variante 1: rekordbox-XML
# --------------------------------------------------------------------------
_KIND = {"MP3": "MP3 File", "AAC": "M4A File", "ALAC": "M4A File", "FLAC": "FLAC File", "WAV": "WAV File",
         "AIFF": "AIFF File", "OGG": "OGG File"}


def location_to_path(loc):
    s = unquote(loc or "")
    for pre in ("file://localhost/", "file:///"):
        if s.startswith(pre):
            rest = s[len(pre):]
            return native_path(rest if re.match(r"^[A-Za-z]:/", rest) else "/" + rest)
    return native_path(s)


def path_to_location(path):
    p = path.replace("\\", "/")
    if not re.match(r"^[A-Za-z]:/", p):
        p = p.lstrip("/")
    return "file://localhost/" + quote(p, safe="/:")


class XmlLibrary(RekordboxLibrary):
    kind = XML
    label = "rekordbox-XML"

    def __init__(self):
        super().__init__()
        self.tree = None
        self.track_el = {}
        self._next_node = 1

    # --- Laden / Neu -------------------------------------------------------
    @classmethod
    def new(cls, version=""):
        lib = cls()
        root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
        ET.SubElement(root, "PRODUCT", Name="MusicOrganizer", Version=version or "1", Company="MOG")
        ET.SubElement(root, "COLLECTION", Entries="0")
        pls = ET.SubElement(root, "PLAYLISTS")
        ET.SubElement(pls, "NODE", Type="0", Name="ROOT", Count="0")
        lib.tree = ET.ElementTree(root)
        return lib

    @classmethod
    def load(cls, path):
        lib = cls()
        try:
            lib.tree = ET.parse(path)
        except (ET.ParseError, OSError) as e:
            raise RekordboxError(f"XML-Datei konnte nicht gelesen werden: {e}") from e
        root = lib.tree.getroot()
        if root.tag != "DJ_PLAYLISTS":
            raise RekordboxError("Keine rekordbox-XML-Datei (DJ_PLAYLISTS fehlt).")
        lib.source = path
        coll = root.find("COLLECTION")
        loc_to_id = {}
        if coll is not None:
            for el in coll.findall("TRACK"):
                tid = el.get("TrackID")
                if not tid:
                    continue
                t = RBTrack(
                    id=tid, path=location_to_path(el.get("Location", "")),
                    title=el.get("Name", ""), artist=el.get("Artist", ""), album=el.get("Album", ""),
                    genre=el.get("Genre", ""), label=el.get("Label", ""), comment=el.get("Comments", ""),
                    bpm=_float(el.get("AverageBpm")), key=el.get("Tonality", ""),
                    rating=rating_from_xml(el.get("Rating")), length=_int(el.get("TotalTime")),
                    year=el.get("Year", "") if el.get("Year", "0") != "0" else "")
                lib.tracks[tid] = t
                lib.track_el[tid] = el
                loc_to_id[el.get("Location", "")] = tid
        pls = root.find("PLAYLISTS")
        top = pls.find("NODE") if pls is not None else None
        if top is not None:
            for child in top.findall("NODE"):
                lib._read_node(child, lib.root, loc_to_id)
        lib._reindex()
        return lib

    def _new_id(self):
        self._next_node += 1
        return f"x{self._next_node}"

    def _read_node(self, el, parent, loc_to_id):
        if el.get("Type") == "1":
            n = RBNode(self._new_id(), el.get("Name", ""), "playlist", parent=parent)
            by_loc = el.get("KeyType") == "1"
            for t in el.findall("TRACK"):
                key = t.get("Key", "")
                tid = loc_to_id.get(key) if by_loc else key
                if tid in self.tracks:
                    n.tracks.append(tid)
        else:
            n = RBNode(self._new_id(), el.get("Name", ""), "folder", parent=parent)
            for c in el.findall("NODE"):
                self._read_node(c, n, loc_to_id)
        parent.children.append(n)

    # --- Playlists ---------------------------------------------------------
    def create_folder(self, parent, name):
        parent = parent or self.root
        self._check_editable(parent)
        n = RBNode(self._new_id(), name, "folder", parent=parent)
        parent.children.append(n)
        self._touch()
        return n

    def create_playlist(self, parent, name):
        parent = parent or self.root
        self._check_editable(parent)
        n = RBNode(self._new_id(), name, "playlist", parent=parent)
        parent.children.append(n)
        self._touch()
        return n

    def rename(self, node, name):
        self._check_editable(node)
        node.name = name
        self._touch()

    def delete(self, node):
        self._check_editable(node)
        node.parent.children.remove(node)
        self._touch()

    def move_node(self, node, new_parent, index=None):
        self._check_editable(node)
        new_parent = new_parent or self.root
        p = new_parent
        while p is not None:
            if p is node:
                raise RekordboxError("Ein Ordner kann nicht in sich selbst verschoben werden.")
            p = p.parent
        node.parent.children.remove(node)
        if index is None or index > len(new_parent.children):
            new_parent.children.append(node)
        else:
            new_parent.children.insert(index, node)
        node.parent = new_parent
        self._touch()

    def add_to_playlist(self, node, track_ids):
        self._check_editable(node)
        added = 0
        for tid in track_ids:
            if tid not in node.tracks:
                node.tracks.append(tid)
                added += 1
        if added:
            self._touch()
        return added

    def remove_from_playlist(self, node, track_ids):
        before = len(node.tracks)
        ids = set(track_ids)
        node.tracks = [t for t in node.tracks if t not in ids]
        if len(node.tracks) != before:
            self._touch()

    def move_in_playlist(self, node, track_id, new_index):
        node.tracks.remove(track_id)
        node.tracks.insert(max(0, min(new_index, len(node.tracks))), track_id)
        self._touch()

    # --- Titel -------------------------------------------------------------
    def ensure_track(self, mog_track):
        """Titel aus MOG in die Sammlung aufnehmen (falls noch nicht vorhanden). Gibt RBTrack zurück."""
        t = self.track_for_path(mog_track.path)
        if t is not None:
            return t
        tid = str(max([_int(k) for k in self.tracks] + [0]) + 1)
        t = RBTrack(id=tid, path=mog_track.path, title=mog_track.display_title, artist=mog_track.artist,
                    album=mog_track.album, genre=mog_track.genre, label=mog_track.label,
                    comment=mog_track.comment, bpm=mog_track.bpm, key=mog_track.key,
                    length=int(mog_track.duration or 0), year=mog_track.year or "")
        coll = self.tree.getroot().find("COLLECTION")
        el = ET.SubElement(coll, "TRACK", TrackID=tid)
        el.set("Kind", _KIND.get(mog_track.fmt, f"{mog_track.fmt} File"))
        el.set("Size", str(mog_track.size or 0))
        el.set("BitRate", str(round((mog_track.bitrate or 0) / 1000)))
        el.set("SampleRate", str(mog_track.samplerate or 0))
        el.set("DateAdded", datetime.date.today().isoformat())
        el.set("Location", path_to_location(mog_track.path))
        self.tracks[tid] = t
        self.track_el[tid] = el
        self._write_track_attrs(t)
        self._path_index[norm_path(t.path)] = tid
        self._touch()
        return t

    def _write_track_attrs(self, t):
        el = self.track_el[t.id]
        el.set("Name", t.title or "")
        el.set("Artist", t.artist or "")
        el.set("Album", t.album or "")
        el.set("Genre", t.genre or "")
        el.set("Label", t.label or "")
        el.set("Comments", t.comment or "")
        el.set("AverageBpm", f"{t.bpm:.2f}" if t.bpm else "0.00")
        el.set("Tonality", t.key or "")
        el.set("Rating", str(int(t.rating or 0) * 51))
        el.set("TotalTime", str(int(t.length or 0)))
        el.set("Year", str(t.year or "0"))

    def update_track(self, track_id, **values):
        t = self.tracks[track_id]
        for k, v in values.items():
            if k in RBTrack.EDITABLE:
                setattr(t, k, v)
        self._write_track_attrs(t)
        self._touch()

    def update_path(self, old_path, new_path):
        t = self.track_for_path(old_path)
        if t is None:
            return False
        self._path_index.pop(norm_path(t.path), None)
        t.path = new_path
        self.track_el[t.id].set("Location", path_to_location(new_path))
        self._path_index[norm_path(new_path)] = t.id
        self._touch()
        return True

    def remove_track(self, track_id, from_collection=True):
        for n in self.root.walk():
            if n.kind == "playlist" and track_id in n.tracks:
                n.tracks = [x for x in n.tracks if x != track_id]
        if from_collection:
            t = self.tracks.pop(track_id, None)
            el = self.track_el.pop(track_id, None)
            if el is not None:
                self.tree.getroot().find("COLLECTION").remove(el)
            if t is not None:
                self._path_index.pop(norm_path(t.path), None)
        self._touch()

    # --- Speichern -----------------------------------------------------------
    def save(self, path=None):
        path = path or self.source
        if not path:
            raise RekordboxError("Bitte einen Speicherort für die XML-Datei wählen.")
        root = self.tree.getroot()
        coll = root.find("COLLECTION")
        coll.set("Entries", str(len(coll.findall("TRACK"))))
        pls = root.find("PLAYLISTS")
        if pls is None:
            pls = ET.SubElement(root, "PLAYLISTS")
        for old in list(pls):
            pls.remove(old)
        top = ET.SubElement(pls, "NODE", Type="0", Name="ROOT", Count=str(len(self.root.children)))
        for c in self.root.children:
            self._write_node(top, c)
        ET.indent(self.tree, space="  ")
        tmp = path + ".mogtmp"
        self.tree.write(tmp, encoding="UTF-8", xml_declaration=True)
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        os.replace(tmp, path)
        self.source = path
        self.changes = 0
        log.info("rekordbox-XML gespeichert: %s", path)

    def _write_node(self, parent_el, n):
        if n.kind == "playlist":
            el = ET.SubElement(parent_el, "NODE", Name=n.name, Type="1", KeyType="0",
                               Entries=str(len(n.tracks)))
            for tid in n.tracks:
                ET.SubElement(el, "TRACK", Key=tid)
        elif n.kind == "folder":
            el = ET.SubElement(parent_el, "NODE", Type="0", Name=n.name, Count=str(len(n.children)))
            for c in n.children:
                self._write_node(el, c)

    def discard(self):
        if self.source and os.path.exists(self.source):
            return XmlLibrary.load(self.source)
        return XmlLibrary.new()


# --------------------------------------------------------------------------
# Variante 2: rekordbox-Datenbank (master.db) über pyrekordbox
# --------------------------------------------------------------------------
def default_db_path():
    """Typischer Speicherort der rekordbox-6/7-Datenbank."""
    try:
        from pyrekordbox.config import get_config
        for v in ("rekordbox7", "rekordbox6"):
            p = get_config(v).get("db_path")
            if p and os.path.exists(p):
                return str(p)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        cand = os.path.join(os.environ.get("APPDATA", ""), "Pioneer", "rekordbox", "master.db")
    else:
        cand = os.path.expanduser("~/Library/Pioneer/rekordbox/master.db")
    return cand if os.path.exists(cand) else ""


def rekordbox_running():
    try:
        from pyrekordbox.utils import get_rekordbox_pid
        return bool(get_rekordbox_pid())
    except Exception:
        return False


def backup_db(db_path, backup_dir, keep=10):
    """Sichert master.db und masterPlaylists6.xml mit Zeitstempel; behält die letzten `keep`."""
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(backup_dir, f"rekordbox-{stamp}")
    os.makedirs(target, exist_ok=True)
    folder = os.path.dirname(db_path)
    for name in (os.path.basename(db_path), "masterPlaylists6.xml"):
        src = os.path.join(folder, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(target, name))
    olds = sorted(d for d in os.listdir(backup_dir) if d.startswith("rekordbox-"))
    for d in olds[:-keep]:
        shutil.rmtree(os.path.join(backup_dir, d), ignore_errors=True)
    return target


class DbLibrary(RekordboxLibrary):
    kind = DB
    label = "rekordbox-Datenbank"

    def __init__(self):
        super().__init__()
        self.db = None
        self.content = {}       # id -> DjmdContent
        self.pl_obj = {}        # node id -> DjmdPlaylist
        self.backup_dir = ""

    @classmethod
    def load(cls, path, backup_dir=""):
        try:
            import logging as _l
            _l.getLogger("pyrekordbox").setLevel(_l.ERROR)
            from pyrekordbox import MasterDatabase
        except ImportError as e:
            raise RekordboxError("Die Bibliothek pyrekordbox ist nicht installiert.") from e
        if not path or not os.path.exists(path):
            raise RekordboxError("rekordbox-Datenbank (master.db) nicht gefunden. Bitte den Pfad wählen.")
        lib = cls()
        lib.source = path
        lib.backup_dir = backup_dir
        try:
            lib.db = MasterDatabase(path=path)
        except Exception as e:
            raise RekordboxError(f"rekordbox-Datenbank konnte nicht geöffnet werden: {e}") from e
        lib._read()
        return lib

    def _read(self):
        self.tracks.clear()
        self.content.clear()
        self.pl_obj.clear()
        self.root = RBNode("root", "rekordbox", "root")
        for c in self.db.get_content().all():
            tid = str(c.ID)
            self.content[tid] = c
            self.tracks[tid] = self._to_track(c)
        objs = self.db.get_playlist().all()
        nodes = {}
        for p in objs:
            kind = {0: "playlist", 1: "folder", 4: "smart"}.get(p.Attribute)
            if kind is None:
                continue
            n = RBNode(str(p.ID), p.Name or "", kind)
            if kind == "playlist":
                n.tracks = [str(s.ContentID) for s in sorted(p.Songs, key=lambda s: s.TrackNo or 0)
                            if str(s.ContentID) in self.tracks]
            nodes[str(p.ID)] = (n, str(p.ParentID), p.Seq or 0)
            self.pl_obj[n.id] = p
        for nid, (n, parent_id, _seq) in sorted(nodes.items(), key=lambda kv: kv[1][2]):
            parent = nodes.get(parent_id, (self.root,))[0]
            n.parent = parent
            parent.children.append(n)
        self._reindex()
        self.changes = 0

    @staticmethod
    def _to_track(c):
        return RBTrack(
            id=str(c.ID), path=native_path(c.FolderPath or ""), title=c.Title or "",
            artist=c.ArtistName or "", album=c.AlbumName or "", genre=c.GenreName or "",
            label=c.LabelName or "", comment=c.Commnt or "",
            bpm=(c.BPM / 100.0) if c.BPM else None, key=c.KeyName or "",
            rating=int(c.Rating or 0), length=int(c.Length or 0),
            year=str(c.ReleaseYear) if c.ReleaseYear else "")

    # --- Playlists ---------------------------------------------------------
    def _parent_obj(self, node):
        return None if node is None or node.kind == "root" else self.pl_obj[node.id]

    def create_folder(self, parent, name):
        parent = parent or self.root
        self._check_editable(parent)
        p = self.db.create_playlist_folder(name, parent=self._parent_obj(parent))
        n = RBNode(str(p.ID), name, "folder", parent=parent)
        self.pl_obj[n.id] = p
        parent.children.append(n)
        self._touch()
        return n

    def create_playlist(self, parent, name):
        parent = parent or self.root
        self._check_editable(parent)
        p = self.db.create_playlist(name, parent=self._parent_obj(parent))
        n = RBNode(str(p.ID), name, "playlist", parent=parent)
        self.pl_obj[n.id] = p
        parent.children.append(n)
        self._touch()
        return n

    def rename(self, node, name):
        self._check_editable(node)
        self.db.rename_playlist(self.pl_obj[node.id], name)
        node.name = name
        self._touch()

    def delete(self, node):
        self._check_editable(node)
        self.db.delete_playlist(self.pl_obj[node.id])
        node.parent.children.remove(node)
        for n in node.walk():
            self.pl_obj.pop(n.id, None)
        self._touch()

    def move_node(self, node, new_parent, index=None):
        self._check_editable(node)
        new_parent = new_parent or self.root
        p = new_parent
        while p is not None:
            if p is node:
                raise RekordboxError("Ein Ordner kann nicht in sich selbst verschoben werden.")
            p = p.parent
        seq = (index + 1) if index is not None else None
        self.db.move_playlist(self.pl_obj[node.id], parent=self._parent_obj(new_parent), seq=seq)
        node.parent.children.remove(node)
        if index is None or index > len(new_parent.children):
            new_parent.children.append(node)
        else:
            new_parent.children.insert(index, node)
        node.parent = new_parent
        self._touch()

    def add_to_playlist(self, node, track_ids):
        self._check_editable(node)
        added = 0
        for tid in track_ids:
            if tid not in node.tracks:
                self.db.add_to_playlist(self.pl_obj[node.id], self.content[tid])
                node.tracks.append(tid)
                added += 1
        if added:
            self._touch()
        return added

    def remove_from_playlist(self, node, track_ids):
        pl = self.pl_obj[node.id]
        ids = set(track_ids)
        for song in list(pl.Songs):
            if str(song.ContentID) in ids:
                self.db.remove_from_playlist(pl, song)
        node.tracks = [t for t in node.tracks if t not in ids]
        self._touch()

    def move_in_playlist(self, node, track_id, new_index):
        pl = self.pl_obj[node.id]
        song = next((s for s in pl.Songs if str(s.ContentID) == track_id), None)
        if song is None:
            return
        self.db.move_song_in_playlist(pl, song, new_index + 1)
        node.tracks.remove(track_id)
        node.tracks.insert(max(0, min(new_index, len(node.tracks))), track_id)
        self._touch()

    # --- Titel -------------------------------------------------------------
    def ensure_track(self, mog_track):
        t = self.track_for_path(mog_track.path)
        if t is not None:
            return t
        kw = {"Title": mog_track.display_title, "Length": int(mog_track.duration or 0),
              "BitRate": round((mog_track.bitrate or 0) / 1000), "SampleRate": mog_track.samplerate or 0}
        if mog_track.bpm:
            kw["BPM"] = int(round(mog_track.bpm * 100))
        try:
            c = self.db.add_content(mog_track.path, **kw)
        except ValueError as e:
            raise RekordboxError(f"{os.path.basename(mog_track.path)}: {e}") from e
        tid = str(c.ID)
        self.content[tid] = c
        t = self._to_track(c)
        self.tracks[tid] = t
        self._path_index[norm_path(t.path)] = tid
        if mog_track.artist or mog_track.album or mog_track.genre or mog_track.key:
            self.update_track(tid, artist=mog_track.artist, album=mog_track.album, genre=mog_track.genre,
                              label=mog_track.label, key=mog_track.key)
        self._touch()
        return self.tracks[tid]

    def _lookup(self, getter, adder, name):
        if not name:
            return None
        obj = getter(Name=name).first()
        return obj if obj is not None else adder(name)

    def _key_id(self, name):
        """ID der Tonart in rekordbox – legt sie an, falls rekordbox sie noch nicht kennt."""
        if not name:
            return None
        k = self.db.get_key(ScaleName=name).first()
        if k is not None:
            return k.ID
        from uuid import uuid4
        from pyrekordbox.masterdb import models
        seq = max([x.Seq or 0 for x in self.db.get_key().all()] + [0]) + 1
        k = models.DjmdKey.create(ID=self.db.generate_unused_id(models.DjmdKey), ScaleName=name, Seq=seq,
                                  UUID=str(uuid4()))
        self.db.add(k)
        self.db.flush()
        return k.ID

    def update_track(self, track_id, **values):
        c = self.content[track_id]
        db = self.db
        if "title" in values:
            c.Title = values["title"]
        if "comment" in values:
            c.Commnt = values["comment"]
        if "rating" in values:
            c.Rating = int(values["rating"] or 0)
        if "bpm" in values:
            c.BPM = int(round(float(values["bpm"]) * 100)) if values["bpm"] else 0
        if "year" in values:
            c.ReleaseYear = _int(values["year"]) or None
        if "artist" in values:
            a = self._lookup(db.get_artist, db.add_artist, values["artist"])
            c.ArtistID = a.ID if a else None
        if "album" in values:
            a = self._lookup(db.get_album, db.add_album, values["album"])
            c.AlbumID = a.ID if a else None
        if "genre" in values:
            g = self._lookup(db.get_genre, db.add_genre, values["genre"])
            c.GenreID = g.ID if g else None
        if "label" in values:
            lab = self._lookup(db.get_label, db.add_label, values["label"])
            c.LabelID = lab.ID if lab else None
        if "key" in values:
            c.KeyID = self._key_id(values["key"])
        t = self.tracks[track_id]
        for k, v in values.items():
            if k in RBTrack.EDITABLE:
                setattr(t, k, v)
        self._touch()

    def update_path(self, old_path, new_path):
        t = self.track_for_path(old_path)
        if t is None:
            return False
        c = self.content[t.id]
        try:
            self.db.update_content_path(c, new_path, save=True, check_path=False, commit=False)
        except (FileNotFoundError, OSError):
            # keine Analysedateien vorhanden -> nur den Datenbankeintrag ändern
            posix = new_path.replace("\\", "/")
            if c.OrgFolderPath and norm_path(c.OrgFolderPath) == norm_path(c.FolderPath):
                c.OrgFolderPath = posix
            c.FolderPath = posix
            c.FileNameL = posix.rsplit("/", 1)[-1]
        self._path_index.pop(norm_path(t.path), None)
        t.path = new_path
        self._path_index[norm_path(new_path)] = t.id
        self._touch()
        return True

    def remove_track(self, track_id, from_collection=False):
        """Entfernt den Titel aus allen Playlists. Aus der Sammlung selbst wird bei der Datenbank
        bewusst nicht gelöscht (Cue-Punkte, Verlauf usw. hängen daran) – das erledigt rekordbox."""
        for n in self.root.walk():
            if n.kind == "playlist" and track_id in n.tracks:
                self.remove_from_playlist(n, [track_id])

    # --- Speichern -----------------------------------------------------------
    def save(self, path=None):
        if rekordbox_running():
            raise RekordboxError("rekordbox läuft gerade. Bitte rekordbox beenden und erneut speichern – "
                                 "die Änderungen bleiben so lange vorgemerkt.")
        target = backup_db(self.source, self.backup_dir) if self.backup_dir else ""
        try:
            self.db.commit()
        except Exception as e:
            raise RekordboxError(f"Speichern fehlgeschlagen: {e}") from e
        self.changes = 0
        log.info("rekordbox-Datenbank gespeichert (Sicherung: %s)", target or "keine")
        return target

    def discard(self):
        try:
            self.db.rollback()
        except Exception:
            pass
        self._read()
        return self

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass


def _float(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0
