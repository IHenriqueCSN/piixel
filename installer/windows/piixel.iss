; Compile pelo scripts/build_windows_installer.ps1, usando Inno Setup 6.
; AppId e AppMutex são contratos de atualização: não troque entre versões.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define ProjectRoot AddBackslash(SourcePath) + "..\.."
#define AppBuildDir ProjectRoot + "\dist\Piixel"
#define AppIcon ProjectRoot + "\build\windows\piixel.ico"

#if !FileExists(AppBuildDir + "\Piixel.exe")
  #error "Piixel.exe não encontrado. Execute scripts/build.py no Windows primeiro."
#endif
#if !FileExists(AppIcon)
  #error "Ícone não encontrado. Execute scripts/build.py no Windows primeiro."
#endif

[Setup]
AppId={{6D37B244-746F-4D3E-9A72-9A6EC26EFC51}
AppName=Piixel
AppVersion={#AppVersion}
AppVerName=Piixel {#AppVersion}
AppPublisher=Piixelverso
AppPublisherURL=https://github.com/IHenriqueCSN/piixel
AppSupportURL=https://github.com/IHenriqueCSN/piixel/issues
AppUpdatesURL=https://github.com/IHenriqueCSN/piixel/actions/workflows/windows-installer.yml
DefaultDirName={localappdata}\Programs\Piixel
DefaultGroupName=Piixel
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
AppMutex=Piixel.Piixelverso.Desktop
SetupMutex=Piixel.Piixelverso.Installer
CloseApplications=yes
RestartApplications=no
AlwaysRestart=no
RestartIfNeededByRun=no
UninstallDisplayIcon={app}\Piixel.exe
SetupIconFile={#AppIcon}
OutputDir={#ProjectRoot}\dist\installer
OutputBaseFilename=Piixel-Setup-{#AppVersion}-x64
VersionInfoVersion={#AppVersion}.0
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany=Piixelverso
VersionInfoDescription=Instalador do Piixel
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Somente dependências do pacote: evita DLLs antigas durante atualizações.
; Nunca apague {app}\* nem diretórios de documentos, preferências ou identidades.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#AppBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Piixel"; Filename: "{app}\Piixel.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Piixel"; Filename: "{app}\Piixel.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Piixel.exe"; Description: "Abrir o Piixel"; Flags: nowait postinstall skipifsilent
