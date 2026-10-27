; Ganchos del instalador de akari (plantilla NSIS de Tauri). Instala por usuario, sin admin.

!macro NSIS_HOOK_PREINSTALL
  ; La carpeta por defecto de Tauri (%LOCALAPPDATA%\akari) es donde el servicio guarda sus
  ; datos: la app va a %LOCALAPPDATA%\Programs\akari, como cualquier app por usuario.
  ${If} $INSTDIR == "$LOCALAPPDATA\${PRODUCTNAME}"
    StrCpy $INSTDIR "$LOCALAPPDATA\Programs\${PRODUCTNAME}"
    SetOutPath $INSTDIR
  ${EndIf}
  ; La versión anterior (Electron) vivía en esa misma carpeta: se desinstala antes, en silencio.
  ${If} ${FileExists} "$INSTDIR\Uninstall akari.exe"
    ExecWait '"$INSTDIR\Uninstall akari.exe" /S _?=$INSTDIR'
    Delete "$INSTDIR\Uninstall akari.exe"
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; que no vuelva a arrancar con Windows
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "akari"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Python deja sus .pyc junto al servicio al usarlo: esa carpeta es solo nuestra
  RMDir /r "$INSTDIR\servicio"
  RMDir "$INSTDIR"
  ; la caché de WebView2 se regenera sola; los ajustes de akari (%APPDATA%\akari) se quedan
  ${If} $UpdateMode <> 1
    RMDir /r "$LOCALAPPDATA\${BUNDLEID}"
  ${EndIf}
!macroend
