"""Dateioperationen: Löschen (Papierkorb / endgültig), im Dateimanager zeigen."""
import os
import subprocess
import sys


def delete_file(path, permanent=False):
    """Löscht eine Datei. Gibt (ok, fehlermeldung) zurück."""
    if not os.path.exists(path):
        return True, "Datei war bereits nicht mehr vorhanden"
    try:
        if permanent:
            os.remove(path)
        else:
            from send2trash import send2trash
            send2trash(path)
        return True, ""
    except Exception as e:
        return False, str(e)


def delete_files(paths, permanent=False, progress=None):
    results = []
    for i, p in enumerate(paths, 1):
        ok, msg = delete_file(p, permanent)
        results.append((p, ok, msg))
        if progress:
            progress(i, len(paths))
    return results


def remove_empty_dirs(start, stop_at):
    """Entfernt nach dem Löschen leer gewordene Ordner bis hoch zu stop_at (exklusiv)."""
    d = os.path.dirname(start)
    stop_at = os.path.normpath(stop_at) if stop_at else None
    while d and (stop_at is None or os.path.normpath(d) != stop_at):
        try:
            if os.listdir(d):
                break
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)


def reveal(path):
    """Zeigt die Datei im Explorer / Finder."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except Exception:
        pass


def no_window_flags():
    """Verhindert aufblitzende Konsolenfenster unter Windows."""
    if sys.platform.startswith("win"):
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


# --------------------------------------------------------------------------
# Umbenennen
# --------------------------------------------------------------------------
_BAD = {"/": "-", "\\": "-", ":": " -", "*": "", "?": "", '"': "'", "<": "(", ">": ")", "|": "-"}
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def sanitize_filename(name, max_len=200):
    """Macht einen Dateinamen (ohne Ordner) für Windows und macOS gültig."""
    out = "".join(_BAD.get(c, c) for c in name if ord(c) >= 32)
    out = " ".join(out.split())
    out = out.rstrip(" .")
    if out.split(".")[0].upper() in _RESERVED:
        out = "_" + out
    if len(out) > max_len:
        out = out[:max_len].rstrip(" .")
    return out


def rename_file(src, new_stem):
    """Benennt eine Datei im selben Ordner um; die Dateiendung bleibt erhalten.

    Gibt (ok, neuer_pfad, meldung) zurück.
    """
    folder, old_name = os.path.split(src)
    ext = os.path.splitext(old_name)[1]
    stem = sanitize_filename(new_stem)
    if not stem:
        return False, src, "Ungültiger Dateiname"
    dst = os.path.join(folder, stem + ext)
    if dst == src:
        return True, src, "unverändert"
    if not os.path.exists(src):
        return False, src, "Datei nicht gefunden"
    case_only = os.path.normcase(dst) == os.path.normcase(src) or (
        os.path.exists(dst) and _same_file(src, dst))
    if os.path.exists(dst) and not case_only:
        return False, src, "Eine Datei mit diesem Namen existiert bereits"
    try:
        if case_only:
            # nur Groß-/Kleinschreibung geändert: über Zwischennamen (macOS/Windows)
            tmp = os.path.join(folder, f".mog_rename_{os.getpid()}{ext}")
            os.rename(src, tmp)
            os.rename(tmp, dst)
        else:
            os.rename(src, dst)
    except OSError as e:
        return False, src, str(e)
    return True, dst, ""


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False
