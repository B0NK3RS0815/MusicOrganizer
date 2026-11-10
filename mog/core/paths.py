"""Pfade zu mitgelieferten Ressourcen und Programmen (auch im PyInstaller-Build)."""
import os
import shutil
import sys


def base_dir():
    """Ordner des Pakets 'mog' – im Build der entpackte Bundle-Ordner."""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "mog")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource(name):
    return os.path.join(base_dir(), "resources", name)


def bundled_tool(name):
    exe = name + (".exe" if sys.platform.startswith("win") else "")
    p = os.path.join(base_dir(), "bin", exe)
    return p if os.path.isfile(p) else None


def find_tool(name, configured=None, extra_dirs=()):
    """Sucht ein Hilfsprogramm: Einstellung -> mitgeliefert -> PATH -> typische Orte."""
    if configured and os.path.isfile(configured):
        return configured
    p = bundled_tool(name)
    if p:
        return p
    p = shutil.which(name)
    if p:
        return p
    candidates = list(extra_dirs)
    if sys.platform == "darwin":
        candidates += ["/opt/homebrew/bin", "/usr/local/bin"]
    elif sys.platform.startswith("win"):
        candidates += [r"C:\ffmpeg\bin", os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin")]
    exe = name + (".exe" if sys.platform.startswith("win") else "")
    for d in candidates:
        c = os.path.join(d, exe)
        if os.path.isfile(c):
            return c
    return None
