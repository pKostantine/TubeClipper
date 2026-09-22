; TubeClipper per-user Windows installer (Inno Setup 6).

#define AppName "TubeClipper"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppExe "TubeClipper.exe"

[Setup]
; Keep this ID unchanged so every release upgrades the existing installation.
AppId={{DB70623F-AD7E-49D1-83F3-08A44D109A64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Pierre Kostantine
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
CloseApplications=yes
RestartApplications=no
Uninstallable=yes
CreateUninstallRegKey=yes
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=TubeClipper-Setup-{#AppVersion}
SetupIconFile=..\assets\TubeClipper.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\TubeClipper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This installs [name/ver] for your Windows account.%n%nTubeClipper trims YouTube videos and past livestreams, then exports video, audio, or animated GIF clips.%n%nPython and ffmpeg are included; administrator access is not required.
