# akari: reglas para agentes (Claude Code, Codex…)

akari (明かり) son cápsulas de escritorio para **Linux y Windows**: uso de Claude Code/Codex, modelos
de IA (API o locales), batería de dispositivos, habilidades/herramientas, documentos ⇄ Markdown,
asistente y cerebro. Servicio Python stdlib en `akari/` (127.0.0.1:47830), cápsulas Quickshell en
`capsulas/`, panel y burbujas web en `web/`, app de escritorio en `app/` / `escritorio/`.

## Las cápsulas van agrupadas (obligatorio)
Nunca agregues una cápsula/burbuja suelta nueva. Cada función es una **pieza** dentro de uno de
**tres grupos** (como mucho), para que la pantalla no se llene de widgets y nadie se pierda:

| Grupo | Piezas |
|---|---|
| **Equipo** (izquierda del centro) | Dispositivos (+ lo que sea del hardware) |
| **IA** (derecha del centro) | Asistente · Uso de IA (límites) · Modelos de IA · Habilidades · Herramientas |
| **Archivos** (a la derecha de IA) | Documentos · Audio · Cerebro |

- Cerrado, el grupo es una píldora con un **chip-resumen por pieza** (ícono + dato corto); al pasar el
  ratón se abre en la pieza que está debajo, clic la fija, se arrastra/pega a un lado/doble clic igual
  que hoy. Soltar un archivo sobre el grupo Archivos lo abre en la pieza que corresponda.
- Quickshell: un `CapsulaGrupo.qml` (ventana) que contiene las piezas como `Item` con `resumen` (chip)
  y `cuerpo`; las `CapsulaX.qml` actuales pasan a ser piezas. Web/burbujas: **una burbuja por grupo**
  con pestañas (`?vista=burbuja&c=equipo|ia|archivos`); la lista de grupos y piezas sale del servicio
  (`GET /api/burbujas`) para que la app de Windows no tenga una lista fija.
- `~/.config/akari/capsulas.json` `{"ocultas": [...]}` oculta piezas o grupos enteros; si un grupo
  queda con una sola pieza visible, se muestra sin pestañas.
- Pieza nueva = elegir su grupo según esta tabla; si no encaja en ninguno, pregunta antes.

## Reglas
- Todo funciona en Linux **y** Windows (rutas con `comun.CONFIG/DATOS/CACHE`, `comun.abrir`,
  `comun.powershell`, sin ventanas de consola: `SIN_VENTANA`).
- Textos siempre en español e inglés: `t("…", "…")` en Python, `U.t` en QML, `t()` en `web/app.js`.
- Servicio solo con la biblioteca estándar. Dependencias pesadas opcionales → `akari/extras.py`
  (entorno propio, botón «Instalar», sin contraseña).
- Toda función con IA usa `modelos.preguntar(...)`; si no hay modelo, decirlo y llevar a la tarjeta
  «Modelos de IA». Nunca mostrar ni registrar claves.
- **Nunca mover, renombrar ni editar archivos del usuario** (el cerebro solo escribe en su bóveda).
- Nada personal en el repo (rutas `/home/<alguien>`, cuentas, MACs, tokens). `gitleaks` antes de push.
- POST solo con `Content-Type: application/json` (contra CSRF); subidas con octet-stream + cabecera propia.
- Pruebas: `AKARI_PUERTO=47891 python -m unittest discover -s pruebas/servicio -p "prueba_*.py"`
  (otro puerto por si akari ya está corriendo). Python ≥ 3.9.
- Commits en español, uno por cambio con sentido.
