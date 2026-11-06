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
!define WEBVIEW2_SETUP "..\build\MicrosoftEdgeWebview2Setup.exe"
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
; NVP never assumes a Windows machine has WebView2, even when
; running Windows 11. The launcher uses Chromium WebView2, so verify the
; Microsoft Evergreen runtime before putting a shortcut on this computer.
; The bootstrapper is fetched from Microsoft and Authenticode-checked in
; the trusted release build, then embedded into THIS one-click installer.
; Setup is per-user, no third-party download/executable is accepted.
Function EnsureWebView2Runtime
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    StrCmp $0 "" check_machine 0
    StrCmp $0 "0.0.0.0" check_machine 0
    Goto ready
    check_machine:
    ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    StrCmp $0 "" check_machine_native 0
    StrCmp $0 "0.0.0.0" check_machine_native 0
    Goto ready
    check_machine_native:
    ReadRegStr $0 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    StrCmp $0 "" install_runtime 0
    StrCmp $0 "0.0.0.0" install_runtime 0
    Goto ready
    install_runtime:
    MessageBox MB_YESNO|MB_ICONQUESTION         "NVP needs the Microsoft WebView2 Runtime for its desktop interface.$\r$\nInstall this official Microsoft prerequisite now?" IDYES run_bootstrap
        Abort "WebView2 is required. NVP was not installed."
    run_bootstrap:
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File /oname=MicrosoftEdgeWebview2Setup.exe "${WEBVIEW2_SETUP}"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
    Delete "$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe"
    IntCmp $1 0 verify_runtime
        Abort "Microsoft WebView2 installer failed. NVP was not installed."
    verify_runtime:
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    StrCmp $0 "" verify_machine 0
    StrCmp $0 "0.0.0.0" verify_machine 0
    Goto ready
    verify_machine:
    ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    StrCmp $0 "" verify_machine_native 0
    StrCmp $0 "0.0.0.0" verify_machine_native 0
    Goto ready
    verify_machine_native:
    ReadRegStr $0 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
    StrCmp $0 "" runtime_missing 0
    StrCmp $0 "0.0.0.0" runtime_missing 0
    Goto ready
    runtime_missing:
    Abort "Microsoft WebView2 installation was not verified. NVP was not installed."
    ready:
FunctionEnd

Section "NVP Alpha" SEC_MAIN
    StrCmp "$INSTDIR" "$LOCALAPPDATA\Programs\NVP" safe_install
        Abort "Refusing non-dedicated NVP installation directory"
    safe_install:
    Call EnsureWebView2Runtime
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
    ; Never remove LOCALAPPDATA\NVP\Projects: user-owned film work.
SectionEnd
