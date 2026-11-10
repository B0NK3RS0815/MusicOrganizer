# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Spezifikation für MusicOrganizer (MOG) – Windows 10/11 x64 und macOS.
# Aufruf aus dem Projektordner:  pyinstaller packaging/mog.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

sys.path.insert(0, os.path.abspath("."))
from mog import __version__  # noqa: E402

ROOT = os.path.abspath(".")
RES = os.path.join(ROOT, "mog", "resources")
BIN = os.path.join(ROOT, "mog", "bin")

datas = [(os.path.join(RES, f), "mog/resources") for f in os.listdir(RES)
         if f.endswith((".svg", ".png", ".ico", ".icns"))]
binaries = []
for f in os.listdir(BIN):
    if f.startswith("fpcalc"):
        binaries.append((os.path.join(BIN, f), "mog/bin"))

# ffmpeg-Binary aus imageio-ffmpeg mitliefern
datas += collect_data_files("imageio_ffmpeg", subdir="binaries")
binaries += collect_dynamic_libs("imageio_ffmpeg")

a = Analysis(
    [os.path.join(ROOT, "packaging", "run_mog.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtSvg", "PySide6.QtNetwork"],
    excludes=["tkinter", "matplotlib", "PIL", "cryptography", "cairosvg", "fontTools", "IPython", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtBluetooth",
              "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtSerialPort"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(RES, "mog.ico" if sys.platform.startswith("win") else "mog.icns")

# Windows-Versionsinfo automatisch aus mog/__init__.py erzeugen
version_file = None
if sys.platform.startswith("win"):
    nums = (tuple(int(x) for x in __version__.split(".")[:3]) + (0, 0, 0))[:3] + (0,)
    tpl = open(os.path.join(ROOT, "packaging", "version_info.txt"), encoding="utf-8").read()
    tpl = tpl.replace("(0, 1, 0, 0)", repr(nums)).replace("'0.1.0'", repr(__version__))
    version_file = os.path.join(ROOT, "build", "version_info_gen.txt")
    os.makedirs(os.path.dirname(version_file), exist_ok=True)
    open(version_file, "w", encoding="utf-8").write(tpl)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MusicOrganizer",
    console=False,
    icon=icon,
    upx=False,
    version=version_file,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MusicOrganizer")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MusicOrganizer.app",
        icon=icon,
        bundle_identifier="de.mog.musicorganizer",
        version=__version__,
        info_plist={
            "CFBundleName": "MusicOrganizer",
            "CFBundleDisplayName": "MusicOrganizer",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.music",
            "NSRemovableVolumesUsageDescription":
                "MusicOrganizer liest dein Musikarchiv auf externen Laufwerken ein.",
            "NSDocumentsFolderUsageDescription": "MusicOrganizer liest Musikdateien aus deinen Ordnern.",
            "NSDownloadsFolderUsageDescription": "MusicOrganizer liest Musikdateien aus deinen Downloads.",
            "NSDesktopFolderUsageDescription": "MusicOrganizer liest Musikdateien vom Schreibtisch.",
            "NSNetworkVolumesUsageDescription": "MusicOrganizer liest Musik von Netzlaufwerken.",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Audio",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.audio", "public.folder"],
            }],
        },
    )
