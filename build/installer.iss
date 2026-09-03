; Установщик «Инженерного помощника» для Inno Setup 6.
;
; Собирать после pyinstaller:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\installer.iss
;
; Файл сохранён в UTF-8 с BOM: без него Inno Setup читает его как ANSI
; и портит все русские строки.

#define AppName "Инженерный помощник"
#define AppVersion "1.0"
#define AppExe "EngineerAssistant.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\EngineerAssistant
DefaultGroupName={#AppName}
; программа хранит данные в профиле пользователя, права администратора
; нужны только для записи в Program Files
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=EngineerAssistant_Setup
Compression=lzma2
SolidCompression=no
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
DiskSpanning=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "..\dist\EngineerAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; загруженные пользователем документы и история
Type: filesandordirs; Name: "{localappdata}\{#AppName}"
