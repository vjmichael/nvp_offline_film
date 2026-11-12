; NVP-E2E-01E — Windows per-user standalone alpha installer.
; Bundled output is built from React Vite + PyInstaller WebView2/FastAPI.
; Keep author work in LOCALAPPDATA\NVP\Projects during uninstall.
Unicode true
; Invoke makensis from repository root; relative payload paths resolve from this script.
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WordFunc.nsh"
!define APP_NAME "NVP Alpha"
!ifndef APP_VERSION
!define APP_VERSION "0.1.0"
!endif
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
; W1-G: do not overwrite a live installation in place.
; Original films in LOCALAPPDATA\NVP\Projects remain outside program rollback.
!define STAGE_DIR "$LOCALAPPDATA\Programs\NVP.pending"
!define PREVIOUS_DIR "$LOCALAPPDATA\Programs\NVP.previous"
!define MARKER "nvp-alpha-install.marker"
; Kernel-verified recovery is mandatory. NSIS cannot inspect the actual
; host-owned worker Job Objects or authorize a previous-runtime rollback.
Function .onInit
    IfFileExists "$LOCALAPPDATA\Programs\NVP" init_complete
    IfFileExists "${PREVIOUS_DIR}" recovery_required init_complete
    recovery_required:
        IfSilent deny_recovery
        MessageBox MB_ICONEXCLAMATION|MB_OK \
            "The previous NVP installation remains preserved. Run the NVP trusted native recovery coordinator, which must verify worker Job Objects are empty before restoring any executable."
    deny_recovery:
        Abort "Interrupted NVP upgrade requires kernel-verified recovery; no automatic installer rename"
    init_complete:
FunctionEnd

Section "NVP Alpha" SEC_MAIN
    StrCmp "$INSTDIR" "$LOCALAPPDATA\Programs\NVP" safe_install
        Abort "Refusing non-dedicated NVP installation directory"
    safe_install:
    IfFileExists "${STAGE_DIR}" 0 +2
        Abort "Pending NVP upgrade exists; recover it before installing again"
    IfFileExists "${PREVIOUS_DIR}" 0 +2
        Abort "Previous NVP runtime preserved; reconcile before upgrading again"
    StrCpy $1 "new"
    IfFileExists "$INSTDIR" upgrade_existing package_stage
    upgrade_existing:
        IfFileExists "$INSTDIR\${MARKER}" upgrade_owned
            Abort "Existing NVP program directory lacks ownership marker"
    upgrade_owned:
        ; Validate the actual marker bytes: mere existence does not
        ; authorize renaming someone else's directory as NVP.
        ClearErrors
        FileOpen $0 "$INSTDIR\${MARKER}" r
        IfErrors invalid_marker
        FileRead $0 $2
        FileClose $0
        StrCmp $2 "NVP-ALPHA-INSTALL-v1" valid_marker invalid_marker
    invalid_marker:
        Abort "Existing NVP directory has invalid installer ownership marker"
    valid_marker:
        IfFileExists "$INSTDIR\NVP.exe" +2 0
            Abort "Installed NVP executable missing; manual repair required"
        ReadRegStr $2 HKCU "${PRODUCT_KEY}" "DisplayVersion"
        StrCmp $2 "" missing_version
        ${VersionCompare} "${APP_VERSION}" "$2" $3
        StrCmp $3 "1" version_newer
        Abort "NVP refuses same-version replacement or native runtime downgrade"
    missing_version:
        Abort "Existing NVP version unknown; native repair required"
    version_newer:
        StrCpy $1 "upgrade"
    package_stage:
        ; A failed rename of a busy executable refuses the upgrade.
        CreateDirectory "${STAGE_DIR}"
        IfErrors package_failed
        SetOutPath "${STAGE_DIR}"
        File /r "${PACKAGE_FILES}\*"
        IfErrors package_failed
        IfFileExists "${STAGE_DIR}\NVP.exe" +2 0
            Goto package_failed
        FileOpen $0 "${STAGE_DIR}\${MARKER}" w
        IfErrors package_failed
        FileWrite $0 "NVP-ALPHA-INSTALL-v1"
        FileClose $0
        FileOpen $0 "${STAGE_DIR}\nvp-alpha-version.txt" w
        IfErrors package_failed
        FileWrite $0 "${APP_VERSION}"
        FileClose $0
        ; The staged bundle has its own matching uninstaller.
        WriteUninstaller "${STAGE_DIR}\Uninstall NVP.exe"
        IfErrors package_failed
        StrCmp $1 "upgrade" needs_native_activation promote_new
    needs_native_activation:
        ; No installer direct promotion of an active NVP runtime.
        ; The original Job Object/host custody and fresh human approval
        ; are enforced by the W1-G native upgrade coordinator.
        Abort "NVP update staged in NVP.pending; protected native activation required"
    promote_new:
        ClearErrors
        Rename "${STAGE_DIR}" "$INSTDIR"
        IfErrors package_failed
        Goto promoted
    promoted:
        CreateDirectory "$SMPROGRAMS\NVP"
        CreateShortcut "$SMPROGRAMS\NVP\NVP.lnk" "$INSTDIR\NVP.exe"
        CreateShortcut "$SMPROGRAMS\NVP\Uninstall NVP.lnk" "$INSTDIR\Uninstall NVP.exe"
        WriteRegStr HKCU "${PRODUCT_KEY}" "DisplayName" "${APP_NAME}"
        WriteRegStr HKCU "${PRODUCT_KEY}" "DisplayVersion" "${APP_VERSION}"
        WriteRegStr HKCU "${PRODUCT_KEY}" "InstallLocation" "$INSTDIR"
        WriteRegStr HKCU "${PRODUCT_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall NVP.exe$\"'
        WriteRegDWORD HKCU "${PRODUCT_KEY}" "NoModify" 1
        WriteRegDWORD HKCU "${PRODUCT_KEY}" "NoRepair" 1
        Goto install_complete
    promotion_uncertain:
        Abort "NVP promoted, but registration failed; previous runtime preserved"
    package_failed:
        Abort "NVP candidate staging failed; installed program left unchanged"
    install_complete:
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
    ; Never recursively remove pending/previous upgrade evidence or original films.
    RMDir /r "$INSTDIR"
    ; Never remove LOCALAPPDATA\NVP\Projects: user-owned film work.
SectionEnd
