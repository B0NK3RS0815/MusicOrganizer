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


def main():
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
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet(resource("check.svg"), resource("chevron.svg")))
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
