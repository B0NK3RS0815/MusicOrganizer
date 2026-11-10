"""Einlesen von Laufwerken, Ordnern und Einzeldateien."""
import os
import threading

from .formats import AUDIO_EXTENSIONS
from .library import Library, norm_path
from .tags import TagError, read_track

# Ordner, die beim Einlesen grundsätzlich übersprungen werden
SKIP_DIRS = {
    "$recycle.bin", "system volume information", ".trashes", ".trash", ".spotlight-v100",
    ".fseventsd", ".temporaryitems", ".documentrevisions-v100", "recycler", "$windows.~bt",
    "$windows.~ws", "found.000", "lost+found", "@eadir", ".appledouble",
}


def is_audio_file(name):
    if name.startswith("._"):          # macOS-Ressourcen-Dateien auf exFAT/FAT-SSDs
        return False
    return os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS


def collect_files(sources, cancel=None, on_found=None, skip_hidden=True):
    """Sammelt alle Audiodateien aus Dateien/Ordnern. Gibt sortierte Liste zurück."""
    found = []
    seen = set()
    for src in sources:
        src = norm_path(src)
        if os.path.isfile(src):
            if is_audio_file(os.path.basename(src)) and src not in seen:
                seen.add(src)
                found.append(src)
            continue
        for root, dirs, files in os.walk(src, onerror=lambda e: None):
            if cancel is not None and cancel.is_set():
                return found
            dirs[:] = [d for d in dirs
                       if d.lower() not in SKIP_DIRS and not (skip_hidden and d.startswith("."))]
            for fn in files:
                if skip_hidden and fn.startswith("."):
                    continue
                if is_audio_file(fn):
                    p = os.path.join(root, fn)
                    if p not in seen:
                        seen.add(p)
                        found.append(p)
            if on_found:
                on_found(len(found))
    return found


class ScanResult:
    def __init__(self):
        self.total = 0
        self.new = 0
        self.updated = 0
        self.unchanged = 0
        self.errors = []          # (pfad, meldung)
        self.missing_ids = []
        self.restored_ids = []
        self.cancelled = False


def scan(sources, db_path, progress=None, batch=None, status=None, cancel=None,
         force=False, skip_hidden=True, batch_size=250):
    """Liest Quellen ein und speichert die Titel in der Bibliothek.

    progress(done, total), batch(list[Track]), status(text) sind optionale Callbacks.
    """
    cancel = cancel or threading.Event()
    lib = Library(db_path)
    res = ScanResult()
    try:
        dir_sources = [norm_path(s) for s in sources if os.path.isdir(s)]
        for d in dir_sources:
            lib.add_root(d)

        if status:
            status("Suche Audiodateien …")
        files = collect_files(sources, cancel,
                              (lambda n: status(f"Suche Audiodateien … {n:,} gefunden".replace(",", "."))
                               ) if status else None, skip_hidden)
        res.total = len(files)
        if cancel.is_set():
            res.cancelled = True
            return res

        index = lib.file_index()
        pending = []
        for i, path in enumerate(files, 1):
            if cancel.is_set():
                res.cancelled = True
                break
            known = index.get(path)
            try:
                st = os.stat(path)
            except OSError as e:
                res.errors.append((path, str(e)))
                continue
            if known and not force and known[1] == st.st_size and abs((known[2] or 0) - st.st_mtime) < 1:
                res.unchanged += 1
            else:
                try:
                    t = read_track(path)
                    pending.append(t)
                    if known:
                        res.updated += 1
                    else:
                        res.new += 1
                except TagError as e:
                    if "Video" not in str(e):
                        res.errors.append((path, str(e)))
                except Exception as e:  # pragma: no cover – Schutz gegen exotische Dateien
                    res.errors.append((path, f"{type(e).__name__}: {e}"))
            if len(pending) >= batch_size:
                lib.upsert(pending)
                if batch:
                    batch(pending)
                pending = []
            if progress and (i % 25 == 0 or i == res.total):
                progress(i, res.total)
        if pending:
            lib.upsert(pending)
            if batch:
                batch(pending)

        # Fehlende / wieder aufgetauchte Dateien unterhalb der eingelesenen Ordner markieren
        if not res.cancelled and dir_sources:
            file_set = set(files)
            missing, restored = [], []
            for p, (tid, _s, _m) in lib.file_index().items():
                if any(p.startswith(d.rstrip(os.sep) + os.sep) for d in dir_sources):
                    if p not in file_set:
                        missing.append(tid)
            cur = lib.con.execute("SELECT id, path FROM tracks WHERE missing=1")
            for tid, p in cur.fetchall():
                if p in file_set:
                    restored.append(tid)
            lib.set_missing(missing, True)
            lib.set_missing(restored, False)
            res.missing_ids = missing
            res.restored_ids = restored
        return res
    finally:
        lib.close()


def check_missing(db_path):
    """Prüft für alle Titel, ob die Datei noch existiert (z. B. SSD abgesteckt)."""
    lib = Library(db_path)
    try:
        changed_missing, changed_present = [], []
        for tid, p, miss in lib.con.execute("SELECT id, path, missing FROM tracks").fetchall():
            exists = os.path.exists(p)
            if exists and miss:
                changed_present.append(tid)
            elif not exists and not miss:
                changed_missing.append(tid)
        lib.set_missing(changed_missing, True)
        lib.set_missing(changed_present, False)
        return changed_missing, changed_present
    finally:
        lib.close()


def quick_check(db_path):
    """Schnelle Prüfung beim Programmstart (ohne jede Datei einzeln anzufassen).

    - Ist eine Quelle (z. B. die externe SSD) nicht verbunden, werden ihre Titel als
      'nicht erreichbar' markiert.
    - Ist sie wieder da, werden nur die bisher als fehlend markierten Titel geprüft.
    - Einzeln hinzugefügte Dateien außerhalb einer Quelle werden nur geprüft, wenn ihr
      Ordner nicht mehr existiert.
    Gibt True zurück, wenn sich etwas geändert hat.
    """
    lib = Library(db_path)
    try:
        roots = [r.rstrip("/\\") + os.sep for r in lib.roots()]
        online = {r: os.path.isdir(r) for r in roots}
        to_missing, to_present = [], []
        dir_cache = {}
        for tid, p, miss in lib.con.execute("SELECT id, path, missing FROM tracks"):
            root = next((r for r in roots if p.startswith(r)), None)
            if root is not None:
                if not online[root]:
                    if not miss:
                        to_missing.append(tid)
                elif miss and os.path.exists(p):
                    to_present.append(tid)
            else:
                d = os.path.dirname(p)
                if d not in dir_cache:
                    dir_cache[d] = os.path.isdir(d)
                if not dir_cache[d] and not miss:
                    to_missing.append(tid)
                elif dir_cache[d] and miss and os.path.exists(p):
                    to_present.append(tid)
        lib.set_missing(to_missing, True)
        lib.set_missing(to_present, False)
        return bool(to_missing or to_present)
    finally:
        lib.close()
