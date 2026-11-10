#!/usr/bin/env bash
# ============================================================
#  MusicOrganizer (MOG) – macOS-Build (Sequoia, Apple Silicon oder Intel)
#  Voraussetzung: Python 3.12 von python.org oder Homebrew (brew install python@3.12)
#  Aufruf im Projektordner:  bash packaging/build_macos.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3.12}
command -v "$PY" >/dev/null || PY=python3

echo "[1/5] Virtuelle Umgebung anlegen …"
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate

echo "[2/5] Abhängigkeiten installieren …"
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt

echo "[3/5] fpcalc (Audio-Fingerabdruck) laden …"
python tools/fetch_fpcalc.py

echo "[4/5] App bauen …"
pyinstaller packaging/mog.spec --noconfirm --clean
# Ad-hoc-Signatur (nötig, damit die App auf Apple Silicon startet)
codesign --force --deep --sign - dist/MusicOrganizer.app

echo "[5/5] DMG erstellen …"
ARCH=$(uname -m)
VER=$(python -c "import mog; print(mog.__version__)")
DMG="dist/MusicOrganizer-${VER}-macOS-${ARCH}.dmg"
rm -f "$DMG"
STAGE=$(mktemp -d)
cp -R dist/MusicOrganizer.app "$STAGE/"
ln -s /Applications "$STAGE/Programme"
hdiutil create -volname "MusicOrganizer" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo
echo "Fertig! App: dist/MusicOrganizer.app"
echo "        DMG: $DMG"
echo "Hinweis: Beim ersten Start ggf. Systemeinstellungen → Datenschutz & Sicherheit → 'Dennoch öffnen'."
