; Optional NSIS hooks for WhatsApp Forensic Studio AI.
;
; Enable by adding to tauri.conf.json -> bundle.windows.nsis:
;   "installerHooks": "../installers/hooks.nsh"
;
; The desktop shortcut is offered as a task only; the Start menu shortcut is
; always created. Case data is never touched by install or uninstall.

!macro NSIS_HOOK_POSTINSTALL
  ${If} ${FileExists} "$DESKTOP\WhatsApp Forensic Studio AI.lnk"
    ; user already has a shortcut; nothing to do
  ${Else}
    CreateShortCut "$DESKTOP\WhatsApp Forensic Studio AI.lnk" "$INSTDIR\${MAINBINARYNAME}.exe"
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  Delete "$DESKTOP\WhatsApp Forensic Studio AI.lnk"
!macroend
