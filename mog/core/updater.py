"""Update-Prüfung über die GitHub-Releases von MusicOrganizer."""
import os
import platform
import re
import subprocess
import sys

import requests

from mog import __version__

REPO = "B0NK3RS0815/MusicOrganizer"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TIMEOUT = 15


class UpdateError(Exception):
    pass


def parse_version(v):
    """'v0.2.10' -> (0, 2, 10). Unbekannte Teile zählen als 0."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def is_newer(remote, local=__version__):
    return parse_version(remote) > parse_version(local)


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = f"MusicOrganizer-MOG/{__version__}"
    s.headers["Accept"] = "application/vnd.github+json"
    return s


def check_latest():
    """Fragt die neueste veröffentlichte Version ab.

    Gibt dict(version, tag, notes, page, assets=[{name, url, size}]) zurück.
    """
    try:
        r = _session().get(API_LATEST, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise UpdateError(f"Keine Verbindung zu GitHub: {e}") from e
    if r.status_code == 404:
        raise UpdateError("Noch keine veröffentlichte Version gefunden.")
    if r.status_code == 403:
        raise UpdateError("GitHub hat die Anfrage vorübergehend begrenzt – bitte später erneut versuchen.")
    if r.status_code >= 400:
        raise UpdateError(f"GitHub-Fehler {r.status_code}")
    d = r.json()
    tag = d.get("tag_name", "")
    return {
        "version": ".".join(str(x) for x in parse_version(tag)),
        "tag": tag,
        "notes": d.get("body") or "",
        "page": d.get("html_url") or RELEASES_PAGE,
        "assets": [{"name": a["name"], "url": a["browser_download_url"], "size": a.get("size", 0)}
                   for a in d.get("assets", [])],
    }


def mac_arch():
    """Echte Prozessor-Architektur – auch wenn MOG per Rosetta (Intel-Version) läuft."""
    arch = platform.machine().lower()
    if arch == "x86_64":
        try:
            out = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
            if out == "1":
                return "arm64"
        except Exception:
            pass
    return "arm64" if arch in ("arm64", "aarch64") else "x86_64"


def pick_asset(assets):
    """Wählt das passende Paket für dieses System."""
    names = {a["name"]: a for a in assets}
    if sys.platform.startswith("win"):
        for n, a in names.items():
            if n.endswith("-Setup.exe"):
                return a
        for n, a in names.items():
            if "Windows" in n and n.endswith(".zip"):
                return a
    elif sys.platform == "darwin":
        arch = mac_arch()
        for want in (f"-macOS-{arch}.dmg", "-macOS-x86_64.dmg"):
            for n, a in names.items():
                if n.endswith(want):
                    return a
    return None


def download(asset, dest_dir, progress=None, cancel=None):
    """Lädt ein Paket herunter. progress(geladen, gesamt). Gibt den Dateipfad zurück."""
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, asset["name"])
    tmp = path + ".part"
    try:
        with _session().get(asset["url"], stream=True, timeout=TIMEOUT) as r:
            if r.status_code >= 400:
                raise UpdateError(f"Download fehlgeschlagen (HTTP {r.status_code})")
            total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
            done = 0
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    if cancel is not None and cancel.is_set():
                        raise UpdateError("Abgebrochen")
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        os.replace(tmp, path)
        return path
    except requests.RequestException as e:
        raise UpdateError(f"Download fehlgeschlagen: {e}") from e
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def launch_installer(path):
    """Startet den Installer (Windows) bzw. öffnet das DMG (macOS)."""
    if sys.platform.startswith("win"):
        if path.lower().endswith(".exe"):
            # Inno Setup: vorhandene Installation wird ersetzt, MOG danach neu gestartet
            subprocess.Popen([path, "/SP-", "/CLOSEAPPLICATIONS"], close_fds=True)
        else:
            os.startfile(os.path.dirname(path))  # portable ZIP: Ordner zeigen
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
