"""Vorgemerkte Tag-Änderungen in die Dateien schreiben."""
import os

from . import tags as tagio
from .library import Library


def commit(db_path, ids, progress=None, cancel=None, before_write=None):
    """Schreibt die vorgemerkten Änderungen der angegebenen Titel in die Dateien.

    before_write(path) wird vor jedem Schreiben aufgerufen (z. B. um den Player die Datei
    freigeben zu lassen). Gibt (aktualisierte_tracks, fehler[(pfad, meldung)]) zurück.
    """
    lib = Library(db_path)
    updated, errors = [], []
    try:
        ids = list(ids)
        for i, tid in enumerate(ids, 1):
            if cancel is not None and cancel.is_set():
                break
            t = lib.get(tid)
            if t is None:
                lib.clear_pending(tid)
                continue
            if progress:
                progress(i - 1, len(ids), os.path.basename(t.path))
            if not os.path.exists(t.path):
                errors.append((t.path, "Datei nicht erreichbar – Änderung bleibt vorgemerkt"))
                continue
            vals, cover, cover_set = lib.pending_for(tid)
            try:
                if before_write:
                    before_write(t.path)
                tagio.write_tags(t.path, vals, cover=cover if cover_set else tagio.KEEP)
                new = tagio.read_track(t.path)
            except Exception as e:
                errors.append((t.path, str(e)))
                continue
            new.id = tid
            new.audio_hash = None
            lib.clear_pending(tid)
            # BPM mit Nachkommastelle behalten, falls das Format nur ganze Zahlen speichert
            b = vals.get("bpm")
            if b:
                from .track import parse_bpm
                pb = parse_bpm(b)
                if pb and new.bpm and abs(pb - new.bpm) < 1:
                    new.bpm = pb
            lib.upsert([new])
            updated.append(new)
        if progress:
            progress(len(ids), len(ids), "")
    finally:
        lib.close()
    return updated, errors
