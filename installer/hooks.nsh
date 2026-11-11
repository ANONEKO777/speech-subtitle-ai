; One question on the uninstall page: Tauri's "delete application data" tick box, worded (see
; lang-*.nsh) as also deleting the downloaded models, runtimes and projects. Unticked by default.
; Tauri skips the tick box on updates and silent runs leave it unticked, so neither deletes data.
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    RMDir /r "$LOCALAPPDATA\video-subtitle-translator"
  ${EndIf}
!macroend
