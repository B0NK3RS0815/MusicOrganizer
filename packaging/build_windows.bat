@echo off
REM ============================================================
REM  MusicOrganizer (MOG) - Windows 10/11 x64 Build
REM  Voraussetzung: Python 3.12 (64 Bit) von python.org
REM  Aufruf: Doppelklick oder in der Eingabeaufforderung im Projektordner:
REM          packaging\build_windows.bat
REM ============================================================
setlocal
cd /d "%~dp0\.."

echo [1/5] Virtuelle Umgebung anlegen ...
if not exist .venv (
    py -3.12 -m venv .venv || python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error

echo [2/5] Abhaengigkeiten installieren ...
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt || goto :error

echo [3/5] fpcalc (Audio-Fingerabdruck) laden ...
python tools\fetch_fpcalc.py

echo [4/5] App bauen ...
pyinstaller packaging\mog.spec --noconfirm --clean || goto :error

echo [5/5] Installer erstellen (falls Inno Setup installiert ist) ...
for /f %%v in ('python -c "import mog; print(mog.__version__)"') do set MOGVER=%%v
where iscc >nul 2>nul
if %errorlevel%==0 (
    iscc /DAppVersion=%MOGVER% packaging\mog_installer.iss
) else if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=%MOGVER% packaging\mog_installer.iss
) else (
    echo Inno Setup nicht gefunden - ueberspringe Installer. Die App liegt in dist\MusicOrganizer\
)

echo.
echo Fertig! Programm: dist\MusicOrganizer\MusicOrganizer.exe
goto :eof

:error
echo.
echo FEHLER beim Build - siehe Meldungen oben.
exit /b 1
