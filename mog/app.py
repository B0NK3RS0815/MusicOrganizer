"""Startpunkt der Anwendung."""
import os
import sys


def _load_translations(app):
    """Deutsche Texte für Qt-Standarddialoge (Abbrechen, Ja/Nein, Dateiauswahl …)."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    app._translators = []
    for name in ("qtbase", "qt"):
        tr = QTranslator(app)
        if tr.load(QLocale("de_DE"), name, "_", path):
            app.installTranslator(tr)
            app._translators.append(tr)


def _apply_audio_backend():
    """Gewählte Wiedergabe-Technik setzen – muss vor dem ersten Abspielen passieren."""
    from PySide6.QtCore import QSettings

    from mog import APP_NAME, APP_ORG
    backend = QSettings(APP_ORG, APP_NAME).value("audio/backend", "auto") or "auto"
    if backend != "auto" and not os.environ.get("QT_MEDIA_BACKEND"):
        os.environ["QT_MEDIA_BACKEND"] = backend


def _selftest(out_path):
    """Prüft im fertig gepackten Programm, ob alle Zusatzmodule geladen werden (MOG_SELFTEST=<datei>)."""
    lines, ok = [], True

    def check(name, fn):
        nonlocal ok
        try:
            lines.append(f"OK   {name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            ok = False
            lines.append(f"FAIL {name}: {type(e).__name__}: {e}")

    def sqlcipher():
        from sqlcipher3 import dbapi2
        con = dbapi2.connect(":memory:")
        con.execute("PRAGMA key='mog'")
        v = con.execute("PRAGMA cipher_version").fetchone()
        con.close()
        return v[0] if v else "?"

    def pyrekordbox():
        import pyrekordbox
        from pyrekordbox import MasterDatabase  # noqa: F401
        from pyrekordbox.masterdb import models  # noqa: F401
        return pyrekordbox.__version__

    def mog_modules():
        from mog import __version__
        from mog.core import keydetect, rekordbox, waveform  # noqa: F401
        x = rekordbox.XmlLibrary.new(__version__)
        x.create_playlist(None, "Test")
        return f"{__version__}, Tonart {keydetect.to_camelot('A minor')}"

    check("sqlcipher3", sqlcipher)
    check("pyrekordbox", pyrekordbox)
    check("mog", mog_modules)
    lines.append("SELFTEST " + ("OK" if ok else "FAILED"))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


def main():
    if os.environ.get("MOG_SELFTEST"):
        return _selftest(os.environ["MOG_SELFTEST"])
    # Multimedia: nur Debug-Meldungen ausblenden, Warnungen landen im Diagnose-Protokoll
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*.debug=false")
    from PySide6.QtCore import QCoreApplication, QStandardPaths, Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from mog import APP_NAME, APP_ORG, __version__, applog
    from mog.core.paths import resource

    QCoreApplication.setOrganizationName(APP_ORG)
    QCoreApplication.setApplicationName(APP_NAME)
    data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or \
        os.path.join(os.path.expanduser("~"), ".musicorganizer")
    applog.setup(data, __version__)
    _apply_audio_backend()
    applog.install_qt_handler()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(__version__)
    app.setApplicationDisplayName("MusicOrganizer")
    app.setStyle("Fusion")

    from mog.ui import theme
    from mog.ui.icons import app_icon
    from PySide6.QtCore import QSettings
    mode = QSettings(APP_ORG, APP_NAME).value("ui/theme", "dark") or "dark"
    theme.apply(app, mode, resource("check.svg"), resource("chevron.svg"))
    _load_translations(app)
    f = QFont()
    if sys.platform.startswith("win"):
        f.setFamily("Segoe UI")
        f.setPointSizeF(9.5)
    elif sys.platform == "darwin":
        f.setFamily(".AppleSystemUIFont")
        f.setPointSizeF(13)
    app.setFont(f)
    app.setWindowIcon(app_icon())

    if sys.platform.startswith("win"):
        try:  # eigenes Taskleisten-Symbol statt Python-Icon
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MOG.MusicOrganizer")
        except Exception:
            pass

    from mog.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    # Dateien/Ordner als Startargument (z. B. "Öffnen mit")
    args = [a for a in sys.argv[1:] if os.path.exists(a)]
    if args:
        w.start_scan(args)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
