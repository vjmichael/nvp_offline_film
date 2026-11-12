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
; If Windows interrupted promotion after parking the original program,
; the SAME installer can offer a visible, owner-confirmed restoration.
; Silent install never authorizes an automatic ambiguous rollback.
Function .onInit
    IfFileExists "$LOCALAPPDATA\Programs\NVP" init_complete
    IfFileExists "${PREVIOUS_DIR}" recover_previous init_complete
    recover_previous:
        IfFileExists "${PREVIOUS_DIR}\NVP.exe" +2 0
            Abort "Stranded NVP previous executable missing; manual recovery needed"
        IfFileExists "${PREVIOUS_DIR}\${MARKER}" +2 0
            Abort "Stranded NVP previous ownership marker missing"
        ClearErrors
        FileOpen $0 "${PREVIOUS_DIR}\${MARKER}" r
        IfErrors init_failed
        FileRead $0 $1
        FileClose $0
        StrCmp $1 "NVP-ALPHA-INSTALL-v1" 0 init_failed
        IfSilent init_failed
        MessageBox MB_ICONEXCLAMATION|MB_YESNO \
            "An NVP upgrade was interrupted. Restore the preserved previous program without touching your movies? (The staged candidate will remain for review.)" \
            IDYES do_restore IDNO init_failed
    do_restore:
        ClearErrors
        Rename "${PREVIOUS_DIR}" "$LOCALAPPDATA\Programs\NVP"
        IfErrors init_failed
        Abort "Previous NVP program restored. Review the pending candidate before another upgrade."
    init_failed:
        Abort "Interrupted NVP upgrade is unresolved; the prior program remains preserved"
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
        StrCmp $1 "upgrade" park_old promote_new
    park_old:
        ClearErrors
        Rename "$INSTDIR" "${PREVIOUS_DIR}"
        IfErrors package_failed
    promote_new:
        ClearErrors
        Rename "${STAGE_DIR}" "$INSTDIR"
        IfErrors restore_old
        Goto promoted
    restore_old:
        StrCmp $1 "upgrade" 0 package_failed
        IfFileExists "$INSTDIR" restore_failed
        ClearErrors
        Rename "${PREVIOUS_DIR}" "$INSTDIR"
        IfErrors restore_failed
        Abort "NVP upgrade promotion failed; original program restored"
    restore_failed:
        Abort "NVP upgrade interrupted; original runtime retained in NVP.previous"
    promoted:
        ; Preserve old program until independent installed acceptance.
        WriteUninstaller "$INSTDIR\Uninstall NVP.exe"
        IfErrors promotion_uncertain
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
