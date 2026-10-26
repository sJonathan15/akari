<p align="center">
  <img src="docs/logo.png" alt="akari" width="420">
</p>

<p align="center">
  <b>Floating desktop capsules for Linux and Windows: your AI usage, your devices and your AI skills — at a glance.</b><br>
  <a href="#español">Español</a> · <a href="#install">Install</a> · <a href="#first-steps">First steps</a> · <a href="#privacy">Privacy</a>
</p>

<p align="center">
  <img src="docs/capsules-en.png" alt="akari capsules: devices with 3D models, Claude Code / Codex usage, and AI skills" width="820">
</p>

**akari** (明かり, *light*) hangs three small capsules from the top edge of your screen. Hover one and it
opens; drag it anywhere (or against a side edge to turn it into a vertical tab).

| Capsule | What it shows |
|---|---|
| **AI** | **Claude Code** and **Codex**: what's left of your 5-hour and weekly limits, when they renew, when you'd run out at the current pace, tokens today, the model in use, sessions. Desktop alerts at 80 % / 95 %. A button (or a daily schedule) to **start your 5-hour window** with a tiny Haiku message. |
| **Devices** | Your mouse, keyboard, headphones, phone, controllers… **detected automatically** (Bluetooth, USB, UPower, KDE Connect / GSConnect; on Windows, Bluetooth and USB through Plug and Play) with battery, charging state, codec/volume, Caps Lock, remaining time — and a **3D model** you can spin. Low-battery alerts. |
| **Skills** | The skills and MCP connectors your AI already has, how often it used each one, and **10 recommended everyday skills** (PDF, Word, Excel, slides, writing, posters, diagrams…) you can install with one click for Claude Code and/or Codex. |

## Works on every Linux desktop — and on Windows

| Desktop | Interface |
|---|---|
| KDE Plasma (Wayland), Hyprland (Caelestia, end-4…), Sway, niri, river, labwc, Wayfire, COSMIC | **Capsules** (Quickshell, layer-shell) |
| GNOME 45–50 (Ubuntu, Fedora…) | **Native GNOME Shell extension** in the top bar + full panel with 3D |
| X11, XFCE, Cinnamon, MATE, LXQt, Budgie, and distros without Quickshell (Debian, Ubuntu, Mint, Pop!_OS…) | **Bubbles app** (AppImage): the same three capsules — hover to open, drag, vertical tab on the side edges — plus a tray icon |
| **Windows 10 / 11** | **Bubbles app** (installer with Python built in) + tray icon, starts with Windows |

Every interface takes your desktop's colors: the full Caelestia scheme, the KDE or GNOME accent color,
pywal / wallust, or the Windows accent color (or your own, in `~/.config/akari/tema.json`).

**Distributions:** Arch and derivatives (CachyOS, EndeavourOS, Manjaro, Garuda — repos or AUR), Fedora,
openSUSE, Debian / Ubuntu / Mint, Void, Alpine, Solus, NixOS (Nix), Gentoo… with or without systemd
(OpenRC, runit, s6: Artix, Devuan, MX Linux…). Without systemd or PyGObject, akari talks to D-Bus by itself.

<p align="center">
  <img src="docs/gnome-bar.png" alt="akari in the GNOME top bar" width="560"><br>
  <img src="docs/panel-en.png" alt="akari full panel: AI, devices with 3D, skills" width="900">
</p>

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/sJonathan15/akari/main/install.sh | bash
```

> **Ubuntu / GNOME:** after installing, **log out and log back in** — akari appears in the top bar.
> Then see [First steps](#first-steps) for your desktop.

**Windows 10 / 11** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/sJonathan15/akari/main/install.ps1 | iex
```

or download `akari-setup-x64.exe` from [Releases](https://github.com/sJonathan15/akari/releases) and run it.
It carries Python and the service inside: nothing else to install. To remove it: *Settings → Apps → akari*.

Linux, from a clone:

```sh
git clone https://github.com/sJonathan15/akari && cd akari && ./install.sh
```

The installer detects your distribution and desktop, installs what's missing (Quickshell where
available — from the repos, the AUR, the Fedora COPR or Nix — and the icon font), sets up `systemd --user`
services when there is systemd and, in any case, starts akari with your session (`~/.config/autostart`,
or `exec-once` / `exec` / `spawn-at-startup` in Hyprland, Sway, niri, labwc, river and Wayfire when they
are not started through systemd), and offers to connect Claude Code's status line (your current status
line is kept and still shown). Options: `--interfaz capsulas|gnome|app`, `--sin-statusline`,
`--sin-dependencias`, `--si`, `--desinstalar`.

**Just want the app?** Download `akari-*.AppImage` from [Releases](https://github.com/sJonathan15/akari/releases),
make it executable and run it: it carries its own service (only `python3` is needed, which every
distribution ships).

**Try it without your data:** `AKARI_DEMO=1 akari servicio` shows example data.

### Requirements
- `python3` ≥ 3.9 (no pip packages). D-Bus is used through PyGObject if present, otherwise akari's own
  pure-Python client (or `busctl`). On Windows, nothing: the installer brings its own Python.
- Capsules: [Quickshell](https://quickshell.org) with Qt Quick 3D and `assimp` (installed for you on Arch and Fedora).
- Phone battery: KDE Connect (KDE) or GSConnect (GNOME) on the computer and the phone.

## First steps

After installing, **how you open akari depends on your desktop.** The installer prints this guide at
the end, and you can see it again any time with `akari guia`.

### Ubuntu / Fedora / any GNOME
1. **Log out and log back in** (first time only) — GNOME only loads extensions at login.
2. Three new icons appear at the **top right of the top bar**: your devices with their battery,
   ★ with what's left of Claude Code / Codex, and a flask with your skills. Click each one.
3. **Panel with 3D models:** *Open panel (with 3D)* in any of those menus, search **akari** in your
   apps, or run `akari abrir`.

Icons missing after logging back in? Run `gnome-extensions enable akari@sjonathan15.github.io` and log in again.

### KDE Plasma, Hyprland, Sway, niri…
Three capsules hang from the **top edge of the screen, near the center**. Hover to open, click the header
to pin, drag to move (against a side edge it becomes a vertical tab), double-click to send it home.
Not there? `systemctl --user restart akari akari-capsulas`.

### X11, XFCE, Cinnamon, MATE, Debian / Ubuntu without GNOME, others (and the AppImage)
The same **three bubbles at the top center**, with a tray icon: hover to open, click the header to pin,
drag to move (against a side edge it becomes a vertical tab), double-click to send it home. Click the tray
icon for the full panel; from its menu you can hide the bubbles, put them back in place or start them at
login. Closed it? Search **akari** in your apps or run `akari app`.

### Windows 10 / 11
The **three bubbles hang from the top of the screen** and the akari icon sits in the tray (next to the
clock; it may be under the **^** arrow). Same gestures as above. Tray menu: full panel, show/hide the
bubbles, start with Windows, connect to Claude Code. Phones show up when paired over Bluetooth or
plugged in over USB.

### Troubleshooting
| Problem | Fix |
|---|---|
| No data at all | `akari arrancar` · with systemd: `systemctl --user restart akari` · Windows: quit akari from the tray and open it again |
| `akari: command not found` | Log out and back in (adds `~/.local/bin` to your PATH) or use `~/.local/bin/akari` |
| Claude limits say "no reading yet" | Send any message in Claude Code — limits arrive with the next reply |
| Codex shows nothing | Use Codex once; akari reads `~/.codex/sessions` |
| Phone not shown | Install KDE Connect (KDE) or GSConnect (GNOME) on the computer **and** the phone, and pair them |
| AppImage won't open on Ubuntu | Re-run the installer (installs `libfuse2`); akari already adds `--no-sandbox` where AppArmor requires it |
| A device has the wrong type | Open it and use **Change type** or **Hide** |
| Bubbles with black corners (X11) | Your window manager has no compositor: turn on compositing (XFCE: *Window Manager Tweaks → Compositor*) |
| Hyprland / Sway: nothing after logging in | Run `akari arrancar`; if your `hyprland.conf` is a link to your dotfiles, add `exec-once = ~/.local/bin/akari arrancar` yourself |

## Using it

- **Hover** a capsule to open it, **click** its header to pin it open, **drag** it to move it,
  **double-click** to send it back home. Drop it against the left/right edge to make it a vertical tab.
- `akari estado` — summary in the terminal · `akari abrir` — full panel · `akari app` — bubbles · `akari arrancar` — start whatever is missing · `akari guia` — how to use it on your desktop.
- A device detected wrongly? Use **Change type** or **Hide** in its card.

### Settings (`~/.config/akari/`, on Windows `%APPDATA%\akari\`)
| File | What |
|---|---|
| `ajustes.json` | `{"idioma": "es"\|"en", "avisos": true, "interfaz": "capsulas"\|"gnome"\|"app"}` |
| `tema.json` | your own colors: `{"acento": "#ff8800"}` or Material 3 names (`primary`, `surface`…) |
| `dispositivos.json` | `ocultar`, `nombres`, `tipos`, `umbrales_bateria` (default `[20, 10, 5]`) |
| `posiciones.json` | where you left each capsule |
| `activar.json` | 5-hour window schedule |

Environment: `AKARI_PANTALLA=DP-1` (which monitor), `AKARI_SIN_MOVIMIENTO=1` (reduce motion).

<a id="privacy"></a>
## Privacy

Everything stays on your computer. The service listens only on `127.0.0.1:47830` and only accepts
JSON requests (so no website can trigger actions). akari **reads**:

- Claude Code: `~/.claude/projects/**/*.jsonl` (token counts), the status-line JSON (limits), and from
  `~/.claude.json` only your display name and plan.
- Codex: `~/.codex/sessions/**/rollout-*.jsonl` (token counts and limits), and from `~/.codex/auth.json`
  only the first name and plan inside the ID token. Tokens and e-mail addresses are never read out, stored or shown.
- Devices: BlueZ, UPower, `/sys`, PipeWire/PulseAudio, KDE Connect / GSConnect; on Windows, Plug and Play
  (Bluetooth and USB), the battery status and Caps Lock. Desktop colors: the files and settings listed above.

Network is used only to download skills you choose to install (from their original GitHub repository)
and, by the installer, fonts and the AppImage. The 5-hour window button runs `claude -p` with no tools.

## Recommended skills

| Skill | Source | License |
|---|---|---|
| PDF · Word · Excel · PowerPoint | [anthropics/skills](https://github.com/anthropics/skills) | Anthropic terms (use with your Claude account) |
| Doc co-authoring · Work updates & emails · Posters · Theme factory · Skill creator | [anthropics/skills](https://github.com/anthropics/skills) | Apache-2.0 |
| Diagrams (archify) | [tt-a1i/archify](https://github.com/tt-a1i/archify) | MIT |
| More: transcribe (Codex), frontend design, algorithmic art, web testing, MCP builder | anthropics/skills, [openai/skills](https://github.com/openai/skills) | Apache-2.0 |

Skills are downloaded on demand into `~/.claude/skills/` and/or `~/.codex/skills/`; akari only removes
the ones it installed. The list lives in [`akari/catalogo.json`](akari/catalogo.json) — PRs welcome.

## Development

```
akari/        Python service (stdlib only): ia.py (Claude Code + Codex), dispositivos.py, habilidades.py, servidor.py,
              windows.py (Windows devices), dbus_nativo.py (pure-Python D-Bus), tema.py (desktop colors)
capsulas/     Quickshell capsules (QML)            web/       full panel + bubbles (three.js 3D)
app/          Electron app (bubbles) → AppImage / Windows installer      gnome/     GNOME Shell extension
modelos/      CC0 3D models + herramientas/modelos.py
pruebas/      servicio/: service tests (Linux + Windows) · gnome/: headless GNOME Shell test (Docker)
```

- Run from the repo: `bin/akari servicio` and `AKARI_RAIZ=$PWD qs -p capsulas` (or `cd app && npm start` for the bubbles).
- Tests: `python3 -m unittest discover -s pruebas/servicio -p "prueba_*.py"` (CI runs them on Linux and Windows).
- AppImage: `cd app && npm install && npm run appimage` · Windows installer (on Windows): `cd app && npm install && npm run windows`.
- Pushing a `v*` tag builds the AppImages (x86_64, arm64) and the Windows installer and publishes them in Releases.
- GNOME extension test: `docker build -t akari-gnome pruebas/gnome && pruebas/gnome/probar.sh`.

## Credits

3D models and studio light are **CC0** (public domain): mouse and headphones by CreativeTrio, phone by
Quaternius (via [Poly Pizza](https://poly.pizza)), studio HDRI by Sergej Majboroda ([Poly Haven](https://polyhaven.com));
the keyboard is generated by akari — see [modelos/CREDITS.md](modelos/CREDITS.md).
[three.js](https://threejs.org) (MIT), [Material Symbols](https://fonts.google.com/icons) (Apache-2.0), Rubik (OFL).
Code: [MIT](LICENSE).

---

<a id="español"></a>
## Español

**akari** (明かり, *luz*) cuelga tres cápsulas pequeñas del borde superior de tu pantalla. Pasa el ratón y se
abren; arrástralas a donde quieras (o contra un borde lateral para volverlas una pestaña vertical).

- **IA** — **Claude Code** y **Codex**: cuánto te queda del límite de 5 horas y del semanal, cuándo se renuevan,
  a qué hora se acabaría a este ritmo, tokens de hoy, modelo en uso y sesiones. Avisos al 80 % y 95 %. Botón
  (o programación diaria) para **activar la ventana de 5 horas** con un mensaje mínimo a Haiku.
- **Dispositivos** — ratón, teclado, audífonos, celular, mandos… **detectados solos** (Bluetooth, USB, UPower,
  KDE Connect / GSConnect) con batería, carga, códec/volumen, Bloq Mayús, tiempo restante y un **modelo 3D** que
  puedes girar. Avisos de batería baja.
- **Habilidades** — las skills y conectores MCP que ya tiene tu IA, cuántas veces usó cada una y **10 habilidades
  recomendadas para el día a día** (PDF, Word, Excel, presentaciones, redacción, afiches, diagramas…) que se
  instalan con un clic para Claude Code y/o Codex.

<p align="center"><img src="docs/capsulas-es.png" alt="cápsulas de akari en español" width="820"></p>

**Funciona en todo Linux y en Windows:** cápsulas en KDE Plasma, Hyprland (Caelestia…), Sway, niri y demás
compositores con layer-shell; **extensión nativa** en GNOME 45–50; y **burbujas** —las mismas tres cápsulas, con
icono en la bandeja— en X11, XFCE, Cinnamon, MATE, LXQt, Budgie, en las distribuciones sin Quickshell (Debian,
Ubuntu, Mint, Pop!_OS…) y en **Windows 10 / 11**. Toma los colores de tu escritorio: el esquema de Caelestia, el
acento de KDE o de GNOME, pywal / wallust o el color de énfasis de Windows.

**Distribuciones:** Arch y derivadas (CachyOS, EndeavourOS, Manjaro, Garuda: repositorios o AUR), Fedora, openSUSE,
Debian / Ubuntu / Mint, Void, Alpine, Solus, NixOS (Nix), Gentoo… con o sin systemd (OpenRC, runit, s6: Artix,
Devuan, MX Linux…). Sin systemd ni PyGObject, akari habla con D-Bus por su cuenta.

### Instalar

```sh
curl -fsSL https://raw.githubusercontent.com/sJonathan15/akari/main/install.sh | bash
```

> **Ubuntu / GNOME:** al terminar, **cierra sesión y vuelve a entrar**: akari aparece en la barra superior.
> Luego mira [Primeros pasos](#primeros-pasos) para tu escritorio.

**Windows 10 / 11** (PowerShell):

```powershell
irm https://raw.githubusercontent.com/sJonathan15/akari/main/install.ps1 | iex
```

o baja `akari-setup-x64.exe` de [Releases](https://github.com/sJonathan15/akari/releases) y ejecútalo: trae dentro
Python y el servicio, no hay que instalar nada más. Para quitarlo: *Configuración → Aplicaciones → akari*.

El instalador de Linux detecta tu distribución y tu escritorio, instala lo que falta (Quickshell desde los
repositorios, el AUR, el COPR de Fedora o Nix), deja los servicios de `systemd --user` si hay systemd y, en todo
caso, hace que akari arranque con tu sesión (`~/.config/autostart`, o `exec-once` / `exec` / `spawn-at-startup` en
Hyprland, Sway, niri, labwc, river y Wayfire cuando no arrancan con systemd), y te ofrece conectar la línea de estado
de Claude Code (la tuya se conserva). Opciones: `--interfaz capsulas|gnome|app`. Para quitarlo:
`./install.sh --desinstalar`. ¿Solo la app? Baja el AppImage de [Releases](https://github.com/sJonathan15/akari/releases).
¿Probar sin tus datos? `AKARI_DEMO=1 akari servicio`.

<a id="primeros-pasos"></a>
### Primeros pasos

Después de instalar, **cómo se abre akari depende de tu escritorio**. El instalador muestra esta guía al
terminar y puedes verla cuando quieras con `akari guia`.

**Ubuntu / Fedora / cualquier GNOME**
1. **Cierra sesión y vuelve a entrar** (solo la primera vez): GNOME carga las extensiones al iniciar sesión.
2. Aparecen tres iconos **arriba a la derecha de la barra superior**: tus dispositivos con su batería,
   ★ con lo que te queda de Claude Code / Codex, y un matraz con tus habilidades. Haz clic en cada uno.
3. **Panel con modelos 3D:** *Abrir panel (con 3D)* en cualquiera de esos menús, busca **akari** en tus
   aplicaciones o ejecuta `akari abrir`.

¿No aparecen tras volver a entrar? `gnome-extensions enable akari@sjonathan15.github.io` y vuelve a entrar.

**KDE Plasma, Hyprland, Sway, niri…** — tres cápsulas cuelgan del **borde superior, cerca del centro**. Pasa
el ratón para abrirlas, clic en la cabecera para fijarlas, arrástralas para moverlas, doble clic para devolverlas.
¿No están? `systemctl --user restart akari akari-capsulas`.

**X11, XFCE, Cinnamon, MATE, Debian / Ubuntu sin GNOME, otros (y el AppImage)** — las mismas **tres burbujas
arriba al centro**, con icono en la bandeja: pasa el ratón para abrirlas, clic en la cabecera para fijarlas,
arrástralas (contra un borde lateral se vuelven pestaña vertical), doble clic para devolverlas. Clic en el icono de
la bandeja abre el panel completo; desde su menú las ocultas, las devuelves a su sitio o eliges si arrancan con la
sesión. ¿Las cerraste? Busca **akari** en tus aplicaciones o ejecuta `akari app`.

**Windows 10 / 11** — las **tres burbujas cuelgan del borde de arriba** y el icono de akari queda en la bandeja
(junto al reloj; puede estar bajo la flecha **^**). Se usan igual. Desde el menú de la bandeja: panel completo,
mostrar u ocultar las burbujas, iniciar con Windows y conectar con Claude Code. El celular aparece si está
vinculado por Bluetooth o conectado por USB.

| Problema | Solución |
|---|---|
| No sale ningún dato | `akari arrancar` · con systemd: `systemctl --user restart akari` · Windows: sal de akari desde la bandeja y vuelve a abrirlo |
| `akari: orden no encontrada` | Cierra sesión y vuelve a entrar (agrega `~/.local/bin` al PATH) o usa `~/.local/bin/akari` |
| Los límites de Claude dicen "sin lectura" | Envía un mensaje en Claude Code: llegan con la siguiente respuesta |
| Codex no muestra nada | Usa Codex una vez; akari lee `~/.codex/sessions` |
| No aparece el celular | Instala KDE Connect (KDE) o GSConnect (GNOME) en el equipo **y** en el celular, y vincúlalos |
| El AppImage no abre en Ubuntu | Vuelve a ejecutar el instalador (instala `libfuse2`); akari ya agrega `--no-sandbox` donde AppArmor lo exige |
| Un dispositivo salió con otro tipo | Ábrelo y usa **Cambiar tipo** u **Ocultar** |
| Burbujas con esquinas negras (X11) | Tu gestor de ventanas no tiene compositor: actívalo (XFCE: *Retoques del gestor de ventanas → Compositor*) |
| Hyprland / Sway: no aparece nada al entrar | Ejecuta `akari arrancar`; si tu `hyprland.conf` es un enlace a tus dotfiles, agrega tú `exec-once = ~/.local/bin/akari arrancar` |

### Privacidad
Todo se queda en tu equipo: el servicio solo escucha en `127.0.0.1` y solo acepta JSON. De tus cuentas lee
únicamente el nombre y el plan; nunca tokens ni correos. La red solo se usa para bajar las habilidades que elijas
instalar (desde su repositorio original) y, al instalar, las fuentes y el AppImage.

### Uso
Pasa el ratón para abrir, clic en la cabecera para dejarla fija, arrastra para mover, doble clic para devolverla
a su sitio. En la terminal: `akari estado` (resumen) y `akari abrir` (panel completo). ¿Un dispositivo salió con el
tipo equivocado? Usa **Cambiar tipo** u **Ocultar** en su tarjeta. Ajustes en `~/.config/akari/` (ver la tabla de arriba).

Modelos 3D **CC0** (dominio público) · código **MIT**.
