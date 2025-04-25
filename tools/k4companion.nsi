; k4companion.nsi
;
; This script will install k4companion-.exe into a directory that
; the user selects; and optionally installs start menu and desktop shortcuts.
;

;--------------------------------

; The name of the installer
Name "k4companion"

Target x86-unicode

; The file to write
OutFile "..\k4companion-installer.exe"

!include "LogicLib.nsh"

Function .onInit
  StrCpy $INSTDIR $PROFILE\k4companion

  ReadRegStr $R0 HKLM \
  "Software\Microsoft\Windows\CurrentVersion\Uninstall\k4companion" "UninstallString"
  StrCmp $R0 "" FinishedUninstallChecks

  MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION \
  "k4companion is already installed. $\n$\nClick `OK` to remove the \
  previous version or `Cancel` to cancel this upgrade." \
  IDOK uninst
  Abort

;Run the uninstaller
uninst:
  ClearErrors
  ExecWait "$R0 /S"
FinishedUninstallChecks:
FunctionEnd

Section
Setoutpath $INSTDIR
  File ..\Windows\k4companion.exe
  File ..\example_config_files\k4companion.yaml
  File ..\Windows\k4companion.ico
  File "..\Documentation\K4 Companion User Manual.pdf"
  File ..\Contributions\opus.dll
SectionEnd

; The default installation directory

; Registry key to check for directory (so if you install again, it will
; overwrite the old one automatically)
InstallDirRegKey HKLM "Software\k4companion" "Install_Dir"

; Request application privileges for Windows Vista
RequestExecutionLevel admin

;--------------------------------

; Pages

Page components
Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

;--------------------------------

; The stuff to install
Section "k4companion (required)"
  SectionIn RO

  ; Set output path to the installation directory.
  SetOutPath $INSTDIR

  ; Write the installation path into the registry
  WriteRegStr HKLM SOFTWARE\k4companion "Install_Dir" "$INSTDIR"

  ; Write the uninstall keys for Windows
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\k4companion" "DisplayName" "k4companion-${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\k4companion" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\k4companion" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\k4companion" "NoRepair" 1
  WriteUninstaller "uninstall.exe"
SectionEnd

; Optional section (can be disabled by the user)
Section "Start Menu Shortcut"
  CreateDirectory "$SMPROGRAMS\k4companion"
  SetOutPath $INSTDIR
  CreateShortCut "$SMPROGRAMS\k4companion\k4companion.lnk" "$INSTDIR\k4companion.exe" "" "$INSTDIR\k4companion.ico" 0
SectionEnd

; Optional section (can be disabled by the user)
Section /o "Desktop Shortcut"
  SetOutPath $INSTDIR
  CreateShortCut "$DESKTOP\k4companion.lnk" "$INSTDIR\k4companion.exe" "" "$INSTDIR\k4companion.ico" 0
SectionEnd

;--------------------------------

; Uninstaller
Section "Uninstall"
  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\k4companion"
  DeleteRegKey HKLM SOFTWARE\k4companion

  ; Remove files and uninstaller
  Delete "$INSTDIR\k4companion.exe"
  Delete "$INSTDIR\k4companion.yaml"
  Delete "$INSTDIR\k4companion.ico"
  Delete "$INSTDIR\K4 Companion User Manual.pdf"
  Delete "$INSTDIR\uninstall.exe"
  Delete "$INSTDIR\opus.dll"

  ; Remove shortcuts, if any
  Delete "$SMPROGRAMS\k4companion\k4companion.lnk"
  Delete "$DESKTOP\k4companion.lnk"

  ; Remove directories used
  RMDir /r "$SMPROGRAMS\k4companion"
  RMDir "$INSTDIR"
  RMDir /r "$PROGRAMFILES32\k4companion"
SectionEnd
