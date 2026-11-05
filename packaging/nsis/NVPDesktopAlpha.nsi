; NVP E2E-01E: per-user Windows NSIS package for an actual staged desktop build.
; Required: makensis /DSTAGE_DIR=<absolute staged directory>
;                   /DAPP_EXE=<actual desktop executable name>
;                   /DOUTPUT_DIR=<absolute output directory>
; Never substitute a test browser, Python script, or placeholder executable.
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "WinMessages.nsh"

!ifndef STAGE_DIR
  !error "STAGE_DIR must point to a built, self-contained Windows desktop app"
!endif
!ifndef APP_EXE
  !error "APP_EXE must identify the real Windows desktop .exe"
!endif
!ifndef OUTPUT_DIR
  !error "OUTPUT_DIR must be defined"
!endif
!ifexist "${STAGE_DIR}\${APP_EXE}"
!else
  !error "The specified staged native NVP desktop executable is missing"
!endif

Name "NVP Desktop Alpha"
OutFile "${OUTPUT_DIR}\NVP-Desktop-Alpha-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\NVP"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "NVP Desktop Alpha" SEC_MAIN
  SetShellVarContext current
  StrCmp "$INSTDIR" "$LOCALAPPDATA\\Programs\\NVP" +2 0
  Abort "NVP must install only in its dedicated per-user application directory"
  SetOutPath "$INSTDIR"
  ; Stage must already include all necessary native runtime dependencies.
  File /r "${STAGE_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\NVP"
  CreateShortcut "$SMPROGRAMS\NVP\NVP Desktop.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\NVP\Uninstall NVP.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha" "DisplayName" "NVP Desktop Alpha"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  StrCmp "$INSTDIR" "$LOCALAPPDATA\\Programs\\NVP" +2 0
  Abort "Refusing to delete unexpected install directory"
  IfFileExists "$INSTDIR\\nvp-install.marker" +2 0
  Abort "Refusing to uninstall directory without NVP install marker"
  ; Never delete %APPDATA%, %LOCALAPPDATA%\NVP, Documents, or creator projects.
  ; Only remove files under this application's dedicated install directory.
  Delete "$SMPROGRAMS\NVP\NVP Desktop.lnk"
  Delete "$SMPROGRAMS\NVP\Uninstall NVP.lnk"
  RMDir "$SMPROGRAMS\NVP"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPDesktopAlpha"
  RMDir /r "$INSTDIR"
SectionEnd
