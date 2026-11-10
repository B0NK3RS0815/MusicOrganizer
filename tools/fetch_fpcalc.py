"""Lädt fpcalc (Chromaprint) für das aktuelle Betriebssystem nach mog/bin/.

Wird im Build (GitHub Actions oder lokal) aufgerufen. Ohne fpcalc funktioniert MOG
weiterhin – nur Audio-Fingerabdruck und AcoustID sind dann deaktiviert.
"""
import io
import json
import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "mog" / "bin"
API = "https://api.github.com/repos/acoustid/chromaprint/releases"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MOG-build"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def wanted_patterns():
    if sys.platform.startswith("win"):
        return ["windows-x86_64"]
    if sys.platform == "darwin":
        arch = platform.machine().lower()
        return ["macos-universal", f"macos-{arch}", "macos-arm64" if arch == "arm64" else "macos-x86_64"]
    return [f"linux-{platform.machine().lower()}", "linux-x86_64"]


def main():
    BIN.mkdir(parents=True, exist_ok=True)
    releases = json.loads(_get(API))
    pats = wanted_patterns()
    for rel in releases:
        assets = [a for a in rel.get("assets", []) if "fpcalc" in a["name"]]
        for pat in pats:
            for a in assets:
                if pat in a["name"]:
                    print(f"Lade {a['name']} ({rel['tag_name']}) …")
                    data = _get(a["browser_download_url"])
                    exe = "fpcalc.exe" if sys.platform.startswith("win") else "fpcalc"
                    if a["name"].endswith(".zip"):
                        with zipfile.ZipFile(io.BytesIO(data)) as z:
                            member = next(n for n in z.namelist() if n.endswith(exe))
                            (BIN / exe).write_bytes(z.read(member))
                    else:
                        with tarfile.open(fileobj=io.BytesIO(data)) as t:
                            member = next(m for m in t.getmembers() if m.name.endswith("/" + exe) or m.name == exe)
                            (BIN / exe).write_bytes(t.extractfile(member).read())
                    p = BIN / exe
                    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    print(f"fpcalc gespeichert: {p}")
                    return 0
    print("WARNUNG: kein passendes fpcalc gefunden – Build ohne Audio-Fingerabdruck.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # Build soll daran nicht scheitern
        print(f"WARNUNG: fpcalc konnte nicht geladen werden: {e}")
        sys.exit(0)
