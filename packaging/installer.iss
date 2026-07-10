; installer.iss — Instalador de Andromeda para Windows 11 (Inno Setup).
; Compilar:  iscc packaging\installer.iss   (tras build_windows.ps1)
; Produce un único Andromeda-Setup.exe que instala Andromeda y, si hace falta, Ollama.
;
; La versión se lee de ..\VERSION para no tener que tocar este archivo en cada release.

#define AppName "Andromeda"
#define AppPublisher "Pablo Alonso"
#define AppURL "https://github.com/paualonso/andromeda-lite"
; Lee la versión del archivo VERSION en la raíz del repo (relativo a este .iss)
#define AppVersion Trim(FileRead(FileOpen(SourcePath + "..\VERSION")))

[Setup]
AppId={{B7A3E2C1-4D5F-4A8B-9C2E-1F3A6B8D0E2A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\Andromeda
DefaultGroupName=Andromeda
OutputBaseFilename=Andromeda-Setup-{#AppVersion}
OutputDir=..\dist\installer
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
SetupIconFile=..\andromeda.ico
UninstallDisplayIcon={app}\Andromeda.exe
DisableProgramGroupPage=yes
; Evita instalar sobre una versión en ejecución
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Todo el contenido empaquetado por PyInstaller (dist\Andromeda\)
Source: "..\dist\Andromeda\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Instalador de Ollama incluido SOLO si existe packaging\redist\OllamaSetup.exe
; (descárgalo de https://ollama.com/download/OllamaSetup.exe). Si no está, el
; instalador compila igualmente y Andromeda guiará al usuario al abrirse.
#define OllamaRedist SourcePath + "redist\OllamaSetup.exe"
#if FileExists(OllamaRedist)
Source: "redist\OllamaSetup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsOllama
#endif
; Runtime WebView2 de Microsoft (necesario para la ventana de la app; Windows 11
; lo trae de serie, pero se comprueba por robustez). Bootstrapper ~2 MB:
; https://go.microsoft.com/fwlink/p/?LinkId=2124703 → packaging\redist\
#define WebView2Redist SourcePath + "redist\MicrosoftEdgeWebView2Setup.exe"
#if FileExists(WebView2Redist)
Source: "redist\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2
#endif

[Icons]
Name: "{group}\Andromeda"; Filename: "{app}\Andromeda.exe"
Name: "{group}\Desinstalar Andromeda"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Andromeda"; Filename: "{app}\Andromeda.exe"; Tasks: desktopicon

[Run]
; Instala el runtime WebView2 en silencio si falta (imprescindible para la ventana)
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando Microsoft WebView2 (motor de la interfaz)..."; Check: NeedsWebView2; Flags: skipifdoesntexist
; Instala Ollama en silencio si no está presente
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/SILENT"; StatusMsg: "Instalando Ollama (motor de IA local)..."; Check: NeedsOllama; Flags: skipifdoesntexist
; Lanza Andromeda al terminar (no en instalación silenciosa)
Filename: "{app}\Andromeda.exe"; Description: "{cm:LaunchProgram,Andromeda}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Limpieza opcional de la carpeta de la app (los datos del usuario se conservan
; en %APPDATA%\Andromeda salvo que el usuario elija borrarlos — ver [Code]).
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function NeedsWebView2: Boolean;
var
  Ver: String;
begin
  // El runtime Evergreen registra su versión aquí (x64: WOW6432Node).
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Ver)
    or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Ver)
    or RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Ver)
  ) or (Ver = '') or (Ver = '0.0.0.0');
end;

function NeedsOllama: Boolean;
begin
  // Si ollama.exe no está en su ruta típica, lo instalamos.
  Result := not FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'))
        and not FileExists(ExpandConstant('{pf}\Ollama\ollama.exe'));
end;

// Al desinstalar, preguntar si borrar también los datos del usuario (memorias,
// conversaciones, configuración). Por defecto NO se borran.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\Andromeda');
    if DirExists(DataDir) then
    begin
      if MsgBox('¿Borrar también tus datos de Andromeda (memorias, conversaciones y ajustes)?'
                + #13#10 + 'Si eliges No, se conservarán para una futura reinstalación.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
