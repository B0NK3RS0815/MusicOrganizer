"""Persistente Bibliothek (SQLite). Jeder Thread öffnet seine eigene Verbindung.

Neben den Titeln speichert die Bibliothek *vorgemerkte* Tag-Änderungen (Tabelle
``pending``). Sie werden in der Liste sofort angezeigt, aber erst beim Speichern bzw.
beim Beenden (nach Rückfrage) in die Dateien geschrieben.
"""
import os
import sqlite3
import time

from .track import DB_COLUMNS, TAG_FIELDS, Track, parse_bpm

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    size INTEGER, mtime REAL, fmt TEXT,
    artist TEXT, title TEXT, album TEXT, albumartist TEXT, genre TEXT, year TEXT,
    track TEXT, bpm REAL, key TEXT, label TEXT, comment TEXT,
    duration REAL, bitrate INTEGER, samplerate INTEGER, bits INTEGER, channels INTEGER,
    lossless INTEGER, has_cover INTEGER, tags_missing INTEGER,
    audio_hash TEXT, missing INTEGER DEFAULT 0, error TEXT,
    fingerprint BLOB, fp_duration REAL
);
CREATE INDEX IF NOT EXISTS idx_tracks_size ON tracks(size);
CREATE TABLE IF NOT EXISTS roots (
    path TEXT PRIMARY KEY,
    added REAL
);
CREATE TABLE IF NOT EXISTS pending (
    track_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    new_value TEXT,
    old_value TEXT,
    blob BLOB,
    PRIMARY KEY (track_id, field)
);
"""

_DATA_COLS = [c for c in DB_COLUMNS if c != "id"]

# Felder, die nur intern mitgeführt werden (nicht in die Datei geschrieben)
COVER = "cover"
_INTERNAL = {"tags_missing", "has_cover"}


def norm_path(p):
    return os.path.normpath(os.path.abspath(p))


def _to_db(field, value):
    """Wandelt einen Text-Wert in den Datenbanktyp der Spalte um."""
    if field == "bpm":
        return parse_bpm(value)
    if field in _INTERNAL:
        return 1 if value in ("1", 1, True) else 0
    return value or ""


def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else f"{value:g}"
    return str(value)


class Library:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.con = sqlite3.connect(db_path, timeout=30)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        self.con.executescript(SCHEMA)
        self.con.commit()

    def close(self):
        self.con.close()

    # --- Titel -----------------------------------------------------------
    def load_all(self):
        cur = self.con.execute(f"SELECT {', '.join(DB_COLUMNS)} FROM tracks")
        cur.arraysize = 5000
        from_row = Track.from_row
        return [from_row(r) for r in cur]

    def count(self):
        return self.con.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

    def get(self, track_id):
        r = self.con.execute(f"SELECT {', '.join(DB_COLUMNS)} FROM tracks WHERE id=?",
                             (track_id,)).fetchone()
        return Track.from_row(r) if r else None

    def file_index(self):
        """path -> (id, size, mtime) für schnellen Änderungsabgleich."""
        return {p: (i, s, m) for i, p, s, m in
                self.con.execute("SELECT id, path, size, mtime FROM tracks")}

    def upsert(self, tracks):
        """Fügt Titel ein oder aktualisiert sie (Schlüssel: Pfad). Setzt track.id.

        Hat ein Titel vorgemerkte Änderungen, werden diese anschließend wieder darübergelegt,
        damit ein erneutes Einlesen sie nicht verdeckt.
        """
        cols = ", ".join(_DATA_COLS)
        qs = ", ".join("?" for _ in _DATA_COLS)
        upd = ", ".join(f"{c}=excluded.{c}" for c in _DATA_COLS if c != "path")
        sql = (f"INSERT INTO tracks ({cols}) VALUES ({qs}) "
               f"ON CONFLICT(path) DO UPDATE SET {upd}, fingerprint=CASE WHEN "
               f"tracks.size=excluded.size AND tracks.mtime=excluded.mtime THEN tracks.fingerprint "
               f"ELSE NULL END")
        with self.con:
            for t in tracks:
                self.con.execute(sql, [getattr(t, c) for c in _DATA_COLS])
            for t in tracks:
                t.id = self.con.execute("SELECT id FROM tracks WHERE path=?", (t.path,)).fetchone()[0]
        self._reapply_pending(tracks)
        return tracks

    def update_fields(self, track_id, **fields):
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.con:
            self.con.execute(f"UPDATE tracks SET {sets} WHERE id=?", (*fields.values(), track_id))

    def set_missing(self, ids, missing=True):
        with self.con:
            self.con.executemany("UPDATE tracks SET missing=? WHERE id=?",
                                 [(int(missing), i) for i in ids])

    def delete(self, ids):
        ids = list(ids)
        with self.con:
            self.con.executemany("DELETE FROM tracks WHERE id=?", [(i,) for i in ids])
            self.con.executemany("DELETE FROM pending WHERE track_id=?", [(i,) for i in ids])

    def delete_under(self, root):
        root = norm_path(root)
        prefix = root.rstrip(os.sep) + os.sep
        cur = self.con.execute("SELECT id FROM tracks WHERE path LIKE ? ESCAPE '\\'",
                               (_like_prefix(prefix),))
        ids = [r[0] for r in cur]
        self.delete(ids)
        return ids

    def clear_all(self):
        """Entfernt alle Titel, Quellen und vorgemerkten Änderungen (Dateien bleiben unberührt)."""
        with self.con:
            self.con.execute("DELETE FROM tracks")
            self.con.execute("DELETE FROM roots")
            self.con.execute("DELETE FROM pending")
            self.con.execute("DELETE FROM sqlite_sequence WHERE name='tracks'")
        self.con.execute("VACUUM")

    def rename_path(self, track_id, new_path):
        """Ändert den Pfad eines Titels. Gibt IDs veralteter Einträge zurück, die denselben
        Pfad hatten (z. B. eine früher gelöschte Datei) und entfernt wurden."""
        stale = [r[0] for r in self.con.execute("SELECT id FROM tracks WHERE path=? AND id<>?",
                                                (new_path, track_id))]
        if stale:
            self.delete(stale)
        with self.con:
            self.con.execute("UPDATE tracks SET path=? WHERE id=?", (new_path, track_id))
        return stale

    # --- Hash / Fingerprint ---------------------------------------------
    def get_hash(self, track_id):
        r = self.con.execute("SELECT audio_hash FROM tracks WHERE id=?", (track_id,)).fetchone()
        return r[0] if r else None

    def set_hash(self, track_id, h):
        with self.con:
            self.con.execute("UPDATE tracks SET audio_hash=? WHERE id=?", (h, track_id))

    def get_fingerprint(self, track_id):
        r = self.con.execute("SELECT fingerprint, fp_duration FROM tracks WHERE id=?",
                             (track_id,)).fetchone()
        return (r[0], r[1]) if r and r[0] else (None, None)

    def set_fingerprint(self, track_id, blob, duration):
        with self.con:
            self.con.execute("UPDATE tracks SET fingerprint=?, fp_duration=? WHERE id=?",
                             (blob, duration, track_id))

    # --- Quellen ---------------------------------------------------------
    def roots(self):
        return [r[0] for r in self.con.execute("SELECT path FROM roots ORDER BY path COLLATE NOCASE")]

    def add_root(self, path):
        with self.con:
            self.con.execute("INSERT OR IGNORE INTO roots (path, added) VALUES (?, ?)",
                             (norm_path(path), time.time()))

    def remove_root(self, path):
        with self.con:
            self.con.execute("DELETE FROM roots WHERE path=?", (norm_path(path),))

    # --- Vorgemerkte Änderungen ------------------------------------------
    def stage(self, track_id, values, cover=None, cover_set=False):
        """Merkt Tag-Änderungen vor und zeigt sie sofort in der Bibliothek an.

        values: {feld: neuer_text}. cover_set=True mit cover=None entfernt das Cover,
        cover=(bytes, mime) setzt ein neues. Gibt den aktualisierten Track zurück.
        """
        t = self.get(track_id)
        if t is None:
            return None
        values = {k: ("" if v is None else str(v).strip()) for k, v in values.items() if k in TAG_FIELDS}
        if "artist" in values or "title" in values:
            artist = values.get("artist", t.artist)
            title = values.get("title", t.title)
            values["tags_missing"] = "0" if (artist and title) else "1"
        if cover_set:
            values["has_cover"] = "1" if cover else "0"
        with self.con:
            for field, new in values.items():
                row = self.con.execute("SELECT old_value FROM pending WHERE track_id=? AND field=?",
                                       (track_id, field)).fetchone()
                old = row[0] if row else _to_text(getattr(t, field))
                if field == "bpm":
                    same = parse_bpm(new) == parse_bpm(old)
                else:
                    same = new == (old or "")
                if same:
                    self.con.execute("DELETE FROM pending WHERE track_id=? AND field=?", (track_id, field))
                else:
                    self.con.execute("INSERT OR REPLACE INTO pending (track_id, field, new_value, old_value) "
                                     "VALUES (?, ?, ?, ?)", (track_id, field, new, old))
                self.con.execute(f"UPDATE tracks SET {field}=? WHERE id=?", (_to_db(field, new), track_id))
            if cover_set:
                self.con.execute("INSERT OR REPLACE INTO pending (track_id, field, new_value, old_value, blob) "
                                 "VALUES (?, ?, ?, ?, ?)",
                                 (track_id, COVER, cover[1] if cover else "", "", cover[0] if cover else None))
            # interne Felder allein sind keine Änderung
            rest = self.con.execute("SELECT field FROM pending WHERE track_id=?", (track_id,)).fetchall()
            if rest and all(f in _INTERNAL for (f,) in rest):
                self._restore(track_id)
        return self.get(track_id)

    def pending_map(self):
        """{track_id: {geänderte Felder}} – für die farbige Markierung in der Liste."""
        out = {}
        for tid, field in self.con.execute("SELECT track_id, field FROM pending"):
            if field not in _INTERNAL:
                out.setdefault(tid, set()).add(field)
        return out

    def pending_ids(self):
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT track_id FROM pending WHERE field NOT IN ('tags_missing', 'has_cover')")]

    def pending_for(self, track_id):
        """Gibt (werte, cover, cover_gesetzt) für das Schreiben in die Datei zurück."""
        vals, cover, cover_set = {}, None, False
        for field, new, blob in self.con.execute(
                "SELECT field, new_value, blob FROM pending WHERE track_id=?", (track_id,)):
            if field == COVER:
                cover_set = True
                cover = (blob, new) if blob else None
            elif field not in _INTERNAL:
                vals[field] = new or ""
        return vals, cover, cover_set

    def pending_cover(self, track_id):
        """(gesetzt?, cover) – damit Detailansicht/Player ein vorgemerktes Cover zeigen."""
        r = self.con.execute("SELECT new_value, blob FROM pending WHERE track_id=? AND field=?",
                             (track_id, COVER)).fetchone()
        if not r:
            return False, None
        return True, ((r[1], r[0]) if r[1] else None)

    def clear_pending(self, track_id):
        with self.con:
            self.con.execute("DELETE FROM pending WHERE track_id=?", (track_id,))

    def discard_pending(self, ids=None):
        """Verwirft vorgemerkte Änderungen und stellt die ursprünglichen Werte wieder her."""
        if ids is None:
            ids = [r[0] for r in self.con.execute("SELECT DISTINCT track_id FROM pending")]
        with self.con:
            for tid in ids:
                self._restore(tid)
        return ids

    def _restore(self, track_id):
        for field, old in self.con.execute("SELECT field, old_value FROM pending WHERE track_id=?",
                                           (track_id,)).fetchall():
            if field != COVER:
                self.con.execute(f"UPDATE tracks SET {field}=? WHERE id=?", (_to_db(field, old), track_id))
        self.con.execute("DELETE FROM pending WHERE track_id=?", (track_id,))

    def _reapply_pending(self, tracks):
        """Nach erneutem Einlesen: Dateiwerte als 'alt' merken, vorgemerkte Werte wieder anzeigen."""
        if not tracks:
            return
        ids = {t.id: t for t in tracks}
        rows = []
        for i in range(0, len(ids), 900):
            chunk = list(ids)[i:i + 900]
            q = ",".join("?" * len(chunk))
            rows += self.con.execute(f"SELECT track_id, field, new_value FROM pending "
                                     f"WHERE track_id IN ({q})", chunk).fetchall()
        if not rows:
            return
        with self.con:
            for tid, field, new in rows:
                t = ids[tid]
                if field == COVER:
                    continue
                self.con.execute("UPDATE pending SET old_value=? WHERE track_id=? AND field=?",
                                 (_to_text(getattr(t, field)), tid, field))
                self.con.execute(f"UPDATE tracks SET {field}=? WHERE id=?", (_to_db(field, new), tid))
                setattr(t, field, _to_db(field, new) if field not in _INTERNAL else new == "1")
                if field == "bpm" and getattr(t, field) is None:
                    t.bpm = None


def _like_prefix(prefix):
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
