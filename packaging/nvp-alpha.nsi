; NVP-E2E-01E — Windows per-user standalone alpha installer.
; Bundled output is built from React Vite + PyInstaller WebView2/FastAPI.
; Keep author work in LOCALAPPDATA\NVP\Projects during uninstall.
Unicode true
; Invoke makensis from repository root; relative payload paths resolve from this script.
!include "MUI2.nsh"
!include "LogicLib.nsh"
!define APP_NAME "NVP Alpha"
!define APP_VERSION "0.1.0"
!define PRODUCT_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\NVPAlpha"
!define PACKAGE_FILES "..\dist\NVP"
Name "${APP_NAME}"
OutFile "..\dist\NVP-Alpha-Setup.exe"
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
Section "NVP Alpha" SEC_MAIN
    StrCmp "$INSTDIR" "$LOCALAPPDATA\Programs\NVP" safe_install
        Abort "Refusing non-dedicated NVP installation directory"
    safe_install:
    SetOutPath "$INSTDIR"
    File /r "${PACKAGE_FILES}\*"
    IfFileExists "$INSTDIR\NVP.exe" +2 0
        Abort "Missing built NVP.exe; installer payload invalid"
    FileOpen $0 "$INSTDIR\nvp-alpha-install.marker" w
    FileWrite $0 "NVP-ALPHA-INSTALL-v1"
    FileClose $0
    WriteUninstaller "$INSTDIR\Uninstall NVP.exe"
    CreateDirectory "$SMPROGRAMS\NVP"
    CreateShortcut "$SMPROGRAMS\NVP\NVP.lnk" "$INSTDIR\NVP.exe"
    CreateShortcut "$SMPROGRAMS\NVP\Uninstall NVP.lnk" "$INSTDIR\Uninstall NVP.exe"
    WriteRegStr HKCU "${PRODUCT_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${PRODUCT_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${PRODUCT_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${PRODUCT_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall NVP.exe$\"'
    WriteRegDWORD HKCU "${PRODUCT_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${PRODUCT_KEY}" "NoRepair" 1
SectionEnd
Section "Uninstall"
    StrCmp "$INSTDIR" "$LOCALAPPDATA\Programs\NVP" safe_remove
        Abort "Refusing to remove an unexpected installation directory"
    safe_remove:
    IfFileExists "$INSTDIR\nvp-alpha-install.marker" marker_present
        Abort "Refusing to remove directory without NVP install marker"
    marker_present:
    Delete "$SMPROGRAMS\NVP\NVP.lnk"
    Delete "$SMPROGRAMS\NVP\Uninstall NVP.lnk"
    RMDir "$SMPROGRAMS\NVP"
    DeleteRegKey HKCU "${PRODUCT_KEY}"
    RMDir /r "$INSTDIR"
    ; NSIS may otherwise return a success status after silently failing to
    ; delete an in-use NVP.exe. Treat an incomplete uninstall as a real error.
    IfFileExists "$INSTDIR\NVP.exe" uninstall_incomplete uninstall_complete
    uninstall_incomplete:
        SetErrorLevel 79
        Abort "NVP.exe remains after uninstall. Close NVP and retry; creator Projects were not touched."
    uninstall_complete:
    ; Never remove LOCALAPPDATA\NVP\Projects: user-owned film work.
SectionEnd
