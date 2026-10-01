; LocalDrop — Windows installer (Inno Setup 6)
;
; Compiled on the release runner (see .github/workflows/release.yml):
;   iscc /DAppVersion=1.1.0 packaging\windows\localdrop.iss
;
; Two shapes are published for Windows:
;   LocalDrop-<ver>-windows-x64-setup.exe   this installer (Start Menu, uninstaller)
;   LocalDrop-<ver>-windows-x64.zip         the same payload, run it in place
;
; The payload is a PyInstaller *onedir* bundle, so the install is a copy of a
; known directory tree rather than a self-extractor that unpacks on every boot.

#ifndef AppVersion
  #error AppVersion must be defined: iscc /DAppVersion=1.1.0 localdrop.iss
#endif

#define AppName        "LocalDrop"
#define AppPublisher   "Abhinandan Subedi"
#define AppURL         "https://github.com/Abhi-Subedi/LocalDrop"
#define AppExeName     "localdrop.exe"

[Setup]
AppId={{8F2C4B1A-6D3E-4C1A-9F27-2B6E5A4D8C31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} — self-hosted file sharing
; Two directives that do NOT exist and must not be re-added:
;   VersionInfoLegalCopyright — the VersionInfo* set is VersionInfoVersion,
;     VersionInfoTextLocation, VersionInfoCompany, VersionInfoDescription,
;     VersionInfoProductName, VersionInfoProductVersion. The licence travels as
;     the LICENSE file in [Files], which is the part that matters for AGPL.
;   RelativePathCheck — not a [Setup] directive at all.
; Instead, the release step verifies the payload exists and that the compiled
; installer is a plausible size, because Inno resolves [Files] globs silently:
; a wrong path yields a valid installer containing no payload.

DefaultDirName={autopf}\LocalDrop
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=LocalDrop-{#AppVersion}-windows-x64-setup
OutputDir=..\..\dist\release
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; A per-user install is enough and avoids needing admin, but a machine-wide
; service benefits from admin. PrivilegesRequired=lowest with a per-user dir
; means a normal user can install LocalDrop for themselves.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart";  Description: "Start LocalDrop when you sign in";  GroupDescription: "Startup:"; Flags: unchecked
Name: "addpath";    Description: "Add localdrop to PATH";              GroupDescription: "Integration:"

[Files]
; The frozen backend, including the built web UI and migrations.
Source: "..\..\dist\release\localdrop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentation worth keeping next to the binary.
Source: "..\..\LICENSE";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md";         DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\CHANGELOG.md";      DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\..\docs\BACKUP.md";    DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\..\docs\CONFIGURATION.md"; DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\..\docs\SECURITY.md";  DestDir: "{app}\docs"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
; User data lives outside Program Files: it is the user's files, and Program
; Files needs elevation to write. Matches the Docker / Linux / macOS model of
; "one data directory you can back up".
Name: "{userappdata}\LocalDrop";  Permissions: users-modify
Name: "{userappdata}\LocalDrop\backups"; Permissions: users-modify

[Icons]
Name: "{group}\{#AppName}";              Filename: "{app}\{#AppExeName}"; Parameters: "--no-browser"; WorkingDir: "{userappdata}\LocalDrop"
Name: "{group}\Documentation";            Filename: "{app}\README.md"
Name: "{group}\Uninstall {#AppName}";     Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";        Filename: "{app}\{#AppExeName}"; Parameters: "--no-browser"; WorkingDir: "{userappdata}\LocalDrop"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";        Filename: "{app}\{#AppExeName}"; Parameters: "--no-browser"; WorkingDir: "{userappdata}\LocalDrop"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; \
  Parameters: "--check"; \
  StatusMsg: "Verifying the install…"; \
  Flags: runhidden waituntilterminated; \
  BeforeInstall: "StopRunningInstance"

[Code]
// Refuse to overwrite a running server: the .exe is locked, and Inno would
// otherwise either fail confusingly or leave a half-copied binary.
procedure StopRunningInstance;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExeName} >nul 2>&1', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// Add (or remove) localdrop from the user PATH without clobbering it.
procedure CurStepChanged(CurStep: TSetupStep);
var
  PathVar, NewPath: String;
begin
  if (CurStep = ssPostInstall) and (IsTaskSelected('addpath')) then
  begin
    if not RegQueryStringValue(HKCU, 'Environment', 'Path', PathVar) then
      PathVar := '';
    if Pos(';' + ExpandConstant('{app}') + ';', ';' + PathVar + ';') = 0 then
    begin
      if PathVar <> '' then NewPath := PathVar + ';' + ExpandConstant('{app}')
      else NewPath := ExpandConstant('{app}');
      RegWriteStringValue(HKCU, 'Environment', 'Path', NewPath);
    end;
  end;
end;

// Deliberately no PATH cleanup on uninstall: rewriting a user's PATH
// registry value on the way out is a good way to break their shell. The
// install directory is left behind if you chose "add to PATH"; delete it by
// hand if you want it gone.

[UninstallDelete]
; Build artefacts and caches, never user data.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
Type: filesandordirs; Name: "{app}\_internal\*.pdb"
