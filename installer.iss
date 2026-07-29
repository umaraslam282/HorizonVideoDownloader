[Setup]
AppName=Horizon Video Downloader
AppVersion=5.0
DefaultDirName={autopf}\HorizonDownloader
DefaultGroupName=Horizon Video Downloader
OutputDir=.
OutputBaseFilename=HorizonDownloader_Setup_v5
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
SetupIconFile=icon.ico

[Files]
Source: "dist\HorizonDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Horizon Video Downloader"; Filename: "{app}\HorizonDownloader.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autoprograms}\Horizon Video Downloader"; Filename: "{app}\HorizonDownloader.exe"; WorkingDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\HorizonDownloader.exe"; Description: "Launch Horizon Video Downloader"; Flags: nowait postinstall skipifsilent