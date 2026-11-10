; Inno-Setup-Skript für den Windows-Installer von MusicOrganizer (MOG)
; Aufruf: iscc packaging\mog_installer.iss   (nach dem PyInstaller-Build)

#define AppName "MusicOrganizer"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "MOG"
#define AppExe "MusicOrganizer.exe"

[Setup]
AppId={{6C1F7E0A-3B7D-4C55-9C2E-0A6F3C1D9B21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=MusicOrganizer-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\mog\resources\mog.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Verknüpfungen:"

[Files]
Source: "..\dist\MusicOrganizer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} starten"; Flags: nowait postinstall skipifsilent
