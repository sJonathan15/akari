# Cerebro de akari: estado del trabajo

Bitácora de avance para retomar sin preguntar. Rama: `claude/compassionate-curie-8vxk92` (sale de
`funciones-nuevas`), PR hacia `main`. No se tocan `app/` ni `escritorio/` (otra sesión).

**Regla de oro:** el cerebro nunca mueve, renombra, edita ni borra archivos del usuario. Solo lee
nombres/rutas/tamaños/fechas y escribe en `DATOS/cerebro.db` y en su bóveda (`~/Cerebro` por defecto;
si la carpeta elegida ya tiene cosas, en su subcarpeta `akari/`).

## Partes (en orden de prioridad)

| # | Parte | Estado |
|---|---|---|
| 1 | Mapa (recorrido, exclusiones, proyectos, áreas, SQLite + FTS5) | ✅ hecho |
| 2 | Bóveda de Obsidian (marcas `<!-- akari -->`) | ✅ hecho |
| 3 | `akari cerebro buscar\|donde\|sesiones\|estado` (y más) | ✅ hecho |
| 4 | Memoria de sesiones (Claude Code, Codex, asistente) | ✅ hecho (probado sin modelo) |
| 5 | Pieza «Cerebro» en el grupo Archivos (estado + buscador + abrir) | ✅ hecho (web probada con Playwright; QML escrita, sin Quickshell para probarla aquí) |
| 6 | Búsqueda por significado (embeddings de Ollama) | 🟡 a medias: código escrito, sin probar con Ollama |
| 7 | Ganchos opt-in (Claude Code SessionStart/SessionEnd, AGENTS.md de Codex) | ✅ hecho (probado a mano) |
| 8 | Recorrido de bienvenida (fase final) | ⬜ falta |
| — | Pruebas automáticas (`pruebas/servicio/prueba_cerebro.py`, 11 pruebas) | ✅ hecho |

## Archivos

- `akari/cerebro.py`: ajustes (`~/.config/akari/cerebro.json`), base `DATOS/cerebro.db`, mapa (`Revision`),
  búsqueda por nombre (FTS5, con LIKE si el SQLite no trae FTS5), `Semantica` (embeddings),
  `pregunta` (el modelo de chat decide qué buscar), `en_que_quedamos`, pendientes/notas,
  `HERRAMIENTAS` + `usar_herramienta` (para el asistente), `MonitorCerebro` (lo usa el servicio), servidor MCP (`akari cerebro mcp`) y la orden `akari cerebro …` (`main`).
- `akari/boveda.py`: notas de la bóveda (`Inicio`, `Como-me-organizo`, `Mapa/<Área>`, `Proyectos/<P>`,
  `Bitacora/AAAA-MM-DD`, `Pendientes`). Fusiona entre marcas; lo escrito fuera se respeta. Las casillas
  `[x]` marcadas en `Pendientes.md` pasan a la base.
- `akari/memoria.py`: lee `~/.claude/projects/*/*.jsonl` y `~/.codex/sessions/**/rollout-*.jsonl`,
  resume con `modelos.preguntar` (o solo título/proyecto/archivos sin modelo) → bitácora + nota del proyecto.
  `registrar_asistente(...)` para el asistente de akari (cuando exista).
- `akari/ganchos.py`: conectar/desconectar Claude Code (hooks en `settings.json`, restaura byte a byte)
  y Codex (bloque entre marcas en `~/.codex/AGENTS.md`).
- `akari/modelos.py`: `CATALOGO_EMBED` (`embeddinggemma:300m` 622 MB multilingüe, `nomic-embed-text`
  274 MB; nombres verificados en ollama.com/library), `embeber()`, `embebedores_instalados()`, y en el
  estado `embeddings` + `para_archivos` {buscar, conversar} para la tarjeta «Modelos de IA».
- `akari/__main__.py`: `akari cerebro …`.
- `akari/servidor.py`: `MonitorCerebro` en el bucle (cada 20 s: revisión al arrancar y cada noche, memoria
  cada 2 min, embeddings), `"cerebro"` en `/api/estado`, `POST /api/cerebro {accion, …}` (configurar, revisar,
  buscar, pregunta, abrir, en_que_quedamos, pendiente, hecho, nota, obsidian, obsidian_instalar, conectar,
  desconectar, elegir, quitar, olvidar, memoria). `akari/demo.py`: cerebro de ejemplo (rutas `~/…`).
- `akari/grupos.py`: pieza `cerebro` (icono `neurology`, chip 70) en el grupo Archivos.
- `capsulas/PiezaCerebro.qml` (+ `shell.qml`, `Datos.qml`): chip con cuántos archivos conoce; abierta:
  primera vez («Crear mi cerebro» con la carpeta personal), estado, cifras, buscador con Abrir / Mostrar en
  carpeta, «En qué quedamos», botones Obsidian / Revisar / Conectar / Elegir carpetas (abre el panel).
- `web/index.html`, `web/app.js` (`dibujarCerebro`, `htmlCerebroPrimera`, buscador fijo `#cer-buscador`
  que no se redibuja mientras se escribe, «Preguntar»), `web/estilo.css` (`.cer-*`).

## Cómo se prueba

Automático (carpeta personal falsa en un subproceso, con `.ssh`, `.env`, `*.pem` y `credentials.json` que no
deben aparecer; mtime + sha256 de todo antes y después; texto a mano fuera de las marcas; casillas marcadas
en Obsidian; ganchos byte a byte; sesión falsa de Claude Code → bitácora):

```sh
AKARI_PUERTO=47891 python -m unittest discover -s pruebas/servicio -p "prueba_*.py"
```

A mano, sin tocar tu carpeta real:

```sh
H=$(mktemp -d)        # carpeta personal falsa
export HOME=$H XDG_CONFIG_HOME=$H/.config XDG_DATA_HOME=$H/.local/share XDG_CACHE_HOME=$H/.cache
mkdir -p $H/Documentos/Universidad/2026/tesis $H/.ssh && echo x > "$H/Documentos/Universidad/2026/tesis/informe de la tesis.docx"
echo k > $H/.ssh/id_rsa; echo T=1 > $H/.env
python3 -c "from akari import cerebro as C; print(C.configurar([C.HOME])); C.revisar()"
python3 bin/akari.py cerebro buscar informe tesis     # → la ruta del .docx
python3 bin/akari.py cerebro buscar id_rsa            # → nada (excluido)
python3 bin/akari.py cerebro estado
ls $H/Cerebro                                        # la bóveda
python3 bin/akari.py cerebro conectar && python3 bin/akari.py cerebro desconectar   # settings.json igual que antes
```

## Decisiones

- Se saltan **todas** las carpetas y archivos ocultos (cubre `.ssh`, `.gnupg`, `.git`, `.env*`, cachés,
  perfiles de navegador de Linux, papelera) + lista fija (`node_modules`, `AppData`, llaveros, gestores de
  contraseñas, carpetas de sistema en la raíz de un disco) + archivos `*.key/*.pem/*.kdbx…` y nombres con
  credential/password/contraseña. Enlaces simbólicos nunca se siguen.
- Incremental por carpeta: se compara (tamaño, mtime) con la base y solo se escribe lo que cambió.
  Tope 400 000 entradas y 24 niveles.
- Proyecto = carpeta con `.git`, `package.json`, `pyproject.toml`, `*.sln`… (el de más arriba; los
  paquetes de un monorepo no cuentan aparte). Área = carpeta no genérica con ≥ 5 documentos (las
  genéricas como Documentos/Descargas se abren hacia sus hijas; Descargas cuenta por sus sueltos).
- Sesiones de una carpeta que no es proyecto del mapa (p. ej. `…/tesis`) crean un proyecto «de sesión».
- Embeddings recortados a 256 dimensiones (Matryoshka) y siempre locales (nunca por API: sería el índice entero).
- Con modelo por API, nombres/rutas solo se mandan si el usuario lo permitió (`permitir_api` en
  `cerebro.json`); si no, todo funciona sin IA.
- Las casillas de `Pendientes.md` solo se leen si el archivo cambió después de la última escritura de
  akari (si no, una regeneración desharía un «hecho» dado por la terminal).
- `abrir_archivo` solo abre rutas del mapa/carpetas elegidas, y nunca ejecuta programas (`.exe`, `.sh`…):
  esos solo se muestran en su carpeta.

## Qué sigue (siguiente paso concreto)

1. Probar `capsulas/PiezaCerebro.qml` en Quickshell de verdad (`AKARI_ABIERTA=1 qs -p capsulas`).
2. Tarjeta «Modelos de IA»: fila de embeddings (descargar sin `usar`) y la línea «Para buscar y abrir
   archivos: X (buscar) + Y (conversar)» con `modelos.para_archivos`.
3. Probar la búsqueda por significado con Ollama + `embeddinggemma:300m`.
4. Recorrido de bienvenida (`akari/recorrido.py`, `GET/POST /api/recorrido`, tarjeta en cápsulas/burbujas,
   `akari recorrido`, «Primeros pasos»).
