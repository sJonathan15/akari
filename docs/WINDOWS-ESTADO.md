# App de Windows: estado y bitácora

Rama `claude/akari-windows-ligero` (sobre `funciones-nuevas`, PR #1 → `main`). Este archivo se
actualiza con cada paso para que otra sesión pueda retomar sin preguntar. Pre-release publicada:
`v0.2.0-beta.1` (instalador `akari-setup-x64.exe`).

## Qué es

`escritorio/`: app de Windows en Rust con Tauri 2 + WebView2, ligera (objetivo: instalador ≤ 40 MB,
RAM en reposo ≤ 150 MB sumando todos sus procesos, CPU ≈ 0 %). La app Electron de `app/` sigue para
Linux (AppImage).

- **Grupos cerrados = píldoras nativas** (`cerradas.rs`, `nativo.rs`, `cabecera.rs`): ventanas Win32
  en capas (`UpdateLayeredWindow`, alfa por píxel) dibujadas con tiny-skia + ab_glyph y una fuente de
  iconos de 9 KB (`recursos/iconos.ttf`, sale de `herramientas/iconos_nativos.py`). Un chip por pieza,
  igual que `htmlChip` de `web/app.js` (asistente, uso, modelos, habilidades, herramientas,
  documentos, audio; si el grupo tiene una sola pieza, su chip a lo ancho).
- **WebView2 solo al abrir**: al pasar el ratón se crea la ventana con `?vista=burbuja&c=<grupo>`,
  se elige la pieza del chip bajo el puntero (`window.__akariPieza`, en `web/ventana.js`), al cerrar
  se esconde y a los 60 s se destruye.
- **Grupos desde el servicio**: `GET /api/burbujas` (`akari/grupos.py`); si no responde, los de
  fábrica de `forma.rs` (mismas medidas).
- **Comportamiento como en Linux**: cuelgan del borde de arriba junto al centro, hover abre, clic en
  la cabecera fija, arrastrar mueve, contra un lado se vuelven pestaña vertical, doble clic vuelve a
  su sitio; posiciones en `posiciones.json` (el mismo de Linux).
- **Servicio**: Python embebido 3.12 (`scripts/python.ps1`, recortado), oculto, en un job object
  que lo cierra con la app. `POST /api/burbujas {"abiertas": [...]}`: sin nada abierto, el servicio
  baja a su ritmo de reposo (`REPOSO` en `akari/servidor.py`).
- **`window.akari`** (`web/ventana.js`, cargado antes que `app.js`): en Tauri arma `burbuja`,
  `alCambiarForma`, `alternarPanel` y `rutaDe(file)` (la ruta real de un archivo soltado: Tauri
  recibe el drop y lo pasa a la página como un `DragEvent` con `File` de verdad). En Electron lo da
  `app/preload.js` (`webUtils.getPathForFile`).
- **Bandeja** (mostrar/ocultar burbujas, panel, salir) y **arranque con Windows** (HKCU Run).
- **Instalador NSIS por usuario** (`nsis/ganchos.nsh`): `%LOCALAPPDATA%\Programs\akari`, quita la
  app Electron vieja si estaba, desinstala limpio (clave Run, `servicio\`, caché de WebView2).
  SmartScreen avisa porque no está firmado: explicado en el README.

## Mediciones (CI, windows-latest)

| | Electron (antes) | Tauri, WebView2 siempre | **Tauri, píldoras nativas** |
|---|---|---|---|
| Instalador | 122 MB | 15,4 MB | **15,7 MB** |
| RAM reposo (Working Set, todo) | 318,9 MB | ~306 MB | **50,8 MB** |
| RAM privada | 140,3 MB | — | **26,9 MB** |
| CPU reposo | 0,11 % | — | **0,02 %** |
| RAM tras usar una burbuja (75 s) | — | — | **58,9 MB** |
| Primera apertura (crear WebView2) | — | — | ~5,4 s |

## Cómo se compila y se prueba

- Linux (desarrollo): `cd escritorio && cargo test` (geometría y dibujo de píldoras;
  `AKARI_CAPTURAS=<carpeta> cargo test` guarda los PNG). `cargo check --target x86_64-pc-windows-msvc`
  comprueba la parte de Windows. En Linux la app corre entera con WebView (sin píldoras nativas):
  se probó en Xvfb contra `AKARI_DEMO=1 python3 bin/akari.py servicio`.
- Windows: `pwsh escritorio/scripts/python.ps1` (Python embebido) y
  `npx --yes @tauri-apps/cli@2.12.1 build` en `escritorio/`.
- Servicio: `AKARI_PUERTO=47891 python -m unittest discover -s pruebas/servicio -p "prueba_*.py"`.
- CI (`.github/workflows/compilar.yml`, job `escritorio`, en cada push a esta rama): compila, instala
  en silencio, mide con `escritorio/scripts/medir.ps1` (RAM, CPU, ratón de verdad con SendInput,
  captura), comprueba que matar la app mata el servicio, desinstala y revisa que no quede nada; falla
  si se pasa de las metas. Sube el instalador y `medicion.json` como artefacto. Con `[medir-antes]`
  en el mensaje del commit mide también la app Electron.

## Decisiones

- Tauri en vez de Electron: 15 MB frente a 122 MB.
- Píldoras nativas: con WebView2 siempre encendido no se bajaba de ~300 MB; dibujarlas en Rust y
  crear WebView2 solo al abrir deja ~50 MB. Coste: la primera apertura tarda ~5 s.
- La lista de grupos y piezas es la del servicio; la app no tiene una propia (AGENTS.md).
- Los recursos del servicio van bajo `servicio/` en la instalación (el binario `akari.exe` chocaba con
  la carpeta `akari`).

## Pendiente

| | Qué | Siguiente paso concreto |
|---|---|---|
| ✅ | Tauri, píldoras nativas, grupos de `/api/burbujas`, `rutaDe`, instalador, CI con metas | — |
| ✅ | Adaptado a los grupos de `funciones-nuevas` (chips de todas las piezas, vista de grupo) | Ver que el CI siga verde tras el push. |
| 🟡 | Pestañas dentro de la burbuja de grupo | Las dibuja la web del PR #2 (`htmlCabecera`, `.b-pieza`). Cuando el PR #2 se fusione, rebasar y comprobar en el CI (captura `captura.png`) que se ven las pestañas y que `__akariPieza` abre en la pieza del chip. |
| 🟡 | Primera apertura de ~5 s | Crear WebView2 (sin mostrar) un poco después del arranque y destruirlo solo tras más tiempo sin uso; medir en el CI cuánta RAM cuesta (`-TrasUso`). Alternativa: precalentar solo el entorno (`CreateCoreWebView2Environment`) y no la ventana. |
| 🟡 | Abrir la píldora al arrastrar un archivo encima | Hoy, *soltar* sobre la píldora cerrada sí funciona (`WM_DROPFILES` en `nativo.rs` → `Evento::Archivos` en `cerradas.rs` → abre en Documentos o Audio y pasa los archivos con `__akariArrastre`). Abrirla al *pasar* el archivo por encima pide un `IDropTarget` de OLE (`RegisterDragDrop` con `DragEnter` → `abrir_en`) en lugar de `DragAcceptFiles`; con la burbuja ya abierta, el drop lo recibe Tauri. Sin probar con el Explorador de verdad. |
| ⬜ | Probar en un Windows real: ratón, varios monitores, DPI ≠ 100 % | Instalar `v0.2.0-beta.1`; probar hover/clic/arrastre/doble clic, pegar a un lado, un segundo monitor a otra escala (125 %, 150 %) y mover la burbuja entre monitores. Revisar `area()` en `main.rs` y `escala` en `nativo.rs` si algo queda corrido. |
| ⬜ | Firma de código (SmartScreen) | Conseguir certificado (p. ej. Azure Trusted Signing o SignPath para software libre), guardarlo como secreto del CI y añadir `bundle.windows.signCommand` en `tauri.conf.json`. |
| ⬜ | Actualizaciones automáticas | Ver la sección siguiente. |

## Actualizaciones automáticas (en curso)

Por partes, cada una con su commit:

1. ✅ Servicio (`akari/actualizacion.py`): un minuto después de arrancar y luego cada hora mira si
   toca (una vez al día; lo guarda en `CACHE/actualizacion.json`). Sin prereleases salvo que
   `VERSION` sea una beta o `ajustes.json` diga `"actualizar": "beta"`; `"actualizar": false` lo
   apaga. `/api/estado` trae `actualizacion: {version, notas, url, beta}` (o `null`), avisa con
   `notificar` una vez por versión, y `POST /api/actualizacion {"accion": "revisar"}` fuerza la
   revisión. Pruebas: `pruebas/servicio/prueba_actualizacion.py` (GitHub falso); probado también
   contra la API real. No corre con `AKARI_DEMO=1`.
2. ⬜ `akari actualizar` y botón en el panel: baja la versión nueva y reemplaza la instalación de
   `install.sh` / `install.ps1` conservando la configuración; reinicia el servicio.
3. ⬜ App de Windows y AppImage: updater de Tauri con GitHub Releases y `latest.json`, firmado (clave
   privada solo como secreto del CI), aviso «Hay una versión nueva» con Actualizar / Ahora no.
4. ⬜ CI: en cada etiqueta `v*` publica AppImage, `.exe`, sus firmas y `latest.json`.
