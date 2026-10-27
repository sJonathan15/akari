// Panel de akari. Recibe el estado del servicio por SSE (/eventos) y dibuja cada pieza en su
// sección. Las piezas van en tres grupos: Equipo, IA y Archivos (ver akari/grupos.py y AGENTS.md).
// Con ?vista=burbuja&c=equipo|ia|archivos dibuja uno de los grupos flotantes de la app de
// escritorio: un chip por pieza en la cabecera y, abierta, la sección de la pieza elegida.
import { Visor } from "./visor3d.js";

const params = new URLSearchParams(location.search);
const vista = params.get("vista");
// la sección del panel de cada pieza
const PIEZAS = { dispositivos: "p-disp", uso: "p-ia", modelos: "p-modelos", habilidades: "p-hab", herramientas: "p-herr",
  documentos: "p-doc", audio: "p-audio" };
// copia de akari/grupos.py para el primer dibujo; se reemplaza con GET /api/burbujas
let GRUPOS = [
  { id: "equipo", piezas: [{ id: "dispositivos", icono: "devices", chip: 254 }] },
  { id: "ia", piezas: [{ id: "uso", icono: "bolt", chip: 92 }, { id: "modelos", icono: "psychology", chip: 44 }, { id: "habilidades", icono: "auto_awesome", chip: 58 }, { id: "herramientas", icono: "construction", chip: 64 }] },
  { id: "archivos", piezas: [{ id: "documentos", icono: "swap_horiz", chip: 58 }, { id: "audio", icono: "graphic_eq", chip: 72 }] },
];
// burbuja: el grupo; c= de antes (una burbuja por función) sigue andando
const pedida = params.get("c");
const ANTIGUAS = { dispositivos: "equipo", documentos: "archivos" };
const burbuja = vista !== "burbuja" ? null : GRUPOS.some((g) => g.id === pedida) ? pedida : ANTIGUAS[pedida] || "ia";
const soloPieza = vista === "burbuja" && pedida === "habilidades" ? "habilidades" : null;
let E = null;                         // último estado
let idioma = navigator.language.startsWith("es") ? "es" : "en";
const ui = { grupo: burbuja || "ia", pagina: "uso", proveedor: "", dispositivo: "", hab: "recomendadas", verMas: false, respuesta: "" };
let visor = null;

const t = (es, en) => (idioma === "es" ? es : en);
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icono = (n, relleno = false) => `<span class="icono${relleno ? " relleno" : ""}">${n}</span>`;

function corto(n) {
  if (n == null) return "—";
  const d = (x) => (idioma === "es" ? x.replace(".", ",") : x);
  if (n >= 1e9) return d((n / 1e9).toFixed(2)) + " B";
  if (n >= 1e6) return d((n / 1e6).toFixed(n >= 1e7 ? 1 : 2)) + " M";
  if (n >= 1e4) return Math.round(n / 1e3) + " k";
  if (n >= 1e3) return d((n / 1e3).toFixed(1)) + " k";
  return String(Math.round(n));
}
const hora = (ts) => new Date(ts * 1000).toLocaleTimeString(idioma, { hour: "2-digit", minute: "2-digit", hour12: false });
function cuenta(seg) {
  seg = Math.max(0, Math.round(seg));
  const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60);
  if (h >= 24) return `${Math.floor(h / 24)} d ${h % 24} h`;
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}
function hace(seg) {
  seg = Math.max(0, Math.round(seg));
  const v = seg < 60 ? `${seg} s` : seg < 3600 ? `${Math.floor(seg / 60)} min` : `${Math.floor(seg / 3600)} h`;
  return t(`hace ${v}`, `${v} ago`);
}
const ahora = () => Date.now() / 1000;

function anillo(valor, color, tam = 64, grosor = 6, texto = "") {
  const r = (tam - grosor) / 2, c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, valor || 0));
  return `<div class="anillo" style="width:${tam}px;height:${tam}px">
    <svg viewBox="0 0 ${tam} ${tam}"><circle class="pista" cx="${tam / 2}" cy="${tam / 2}" r="${r}" fill="none" stroke-width="${grosor}"/>
    <circle class="arco" cx="${tam / 2}" cy="${tam / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${grosor}"
      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - v)}"/></svg>
    ${texto ? `<span>${texto}</span>` : ""}</div>`;
}

async function enviar(ruta, cuerpo) {
  try {
    const r = await fetch(ruta, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    return await r.json();
  } catch {
    return { ok: false, mensaje: t("akari no respondió.", "akari did not answer.") };
  }
}

const VAR = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const colorLibre = (v) => (!v ? VAR("--contorno") : v.libre <= 10 ? VAR("--error") : v.libre <= 25 ? VAR("--terciario") : VAR("--primario"));
const familia = (prov, m) => (!m ? "" : prov === "codex" ? "GPT" : m.split(" ")[0]);
const COLOR_FAM = { Opus: "--primario", Fable: "--terciario", Sonnet: "#c1c5e0", Haiku: "--exito", GPT: "--exito" };
const colorFam = (f) => (COLOR_FAM[f]?.startsWith("--") ? VAR(COLOR_FAM[f]) : COLOR_FAM[f] || VAR("--texto-var"));
const ICONO_FAM = { Opus: "diamond", Fable: "auto_stories", Sonnet: "music_note", Haiku: "spa", GPT: "terminal" };
const ICONOS_DISP = { raton: "mouse", audifonos: "headphones", teclado: "keyboard", celular: "smartphone", mando: "sports_esports", otro: "devices_other" };
function nivel(d) {
  if (!d || !d.conectado) return "nada";
  if (d.bateria == null) return "cable";
  return d.bateria <= 20 ? "bajo" : d.bateria <= 50 ? "medio" : "ok";
}
const colorNivel = (n) => VAR({ ok: "--exito", medio: "--terciario", bajo: "--error", cable: "--primario", nada: "--contorno" }[n]);

// ------------------------------------------------------------------ tema
// Colores del escritorio (Caelestia, KDE, GNOME, pywal, Windows…) que calcula el servicio.
const VARIABLES = {
  primary: "--primario", onPrimary: "--sobre-primario", secondaryContainer: "--cont-secundario",
  onSecondaryContainer: "--sobre-cont-secundario", tertiary: "--terciario", error: "--error", success: "--exito",
  surface: "--superficie", onSurface: "--texto", onSurfaceVariant: "--texto-var", surfaceContainer: "--contenedor",
  surfaceContainerHigh: "--contenedor-alto", surfaceContainerHighest: "--contenedor-max", outline: "--contorno",
  outlineVariant: "--contorno-var", secondary: "--secundario",
};
let temaAplicado = "";
function aplicarTema(tema) {
  const colores = (tema && tema.colores) || {};
  const clave = JSON.stringify(colores);
  if (clave === temaAplicado) return;
  temaAplicado = clave;
  for (const [k, v] of Object.entries(VARIABLES)) {
    if (/^#[0-9a-f]{6}$/i.test(colores[k] || "")) document.documentElement.style.setProperty(v, colores[k]);
  }
}

// ------------------------------------------------------------------ IA
function proveedorActual() {
  const ia = E.ia || {};
  const provs = ["claude", "codex"].filter((p) => ia[p]);
  return { provs, prov: provs.includes(ui.proveedor) ? ui.proveedor : ia.principal || provs[0] || "" };
}

function dibujarIA() {
  const ia = E.ia || {};
  const { provs, prov } = proveedorActual();
  const p = ia[prov];
  $("#sin-ia").hidden = !!prov;
  $("#ia-contenido").hidden = !prov;
  $("#proveedores").innerHTML = provs.length > 1
    ? provs.map((x) => `<button data-prov="${x}" class="${x === prov ? "activa" : ""}">${x === "claude" ? "Claude Code" : "Codex"}</button>`).join("")
    : "";
  if (!p) return;

  const v5 = p.limites.cinco_horas, v7 = p.limites.siete_dias;
  const lim = (titulo, v) => {
    let ritmo = "";
    if (v && v.reinicia) ritmo = v.agotado_en
      ? `<p class="peligro">${t("A este ritmo se acaba a las ", "At this pace it runs out at ")}${hora(v.agotado_en)}</p>`
      : `<p>${t("Se renueva a las ", "Renews at ")}${hora(v.reinicia)} · ${t("en ", "in ")}${cuenta(v.reinicia - ahora())}</p>`;
    return `<div class="limite">${anillo(v ? v.libre / 100 : 0, colorLibre(v), 64, 6, v ? Math.round(v.libre) + "%" : "—")}
      <div><strong>${titulo}</strong><p>${v ? t(`Te queda el ${Math.round(v.libre)} %`, `${Math.round(v.libre)}% left`) : t("Sin lectura todavía", "No reading yet")}</p>${ritmo}</div></div>`;
  };
  const cuentaTxt = p.cuenta ? [p.cuenta.nombre, p.cuenta.plan].filter(Boolean).join(" · ") : "";
  $("#limites").innerHTML = lim(t("Límite de 5 horas", "5-hour limit"), v5) + lim(t("Límite semanal", "Weekly limit"), v7)
    + (!p.limites.disponible ? `<p class="cuenta">${prov === "claude"
      ? t("Envía un mensaje en Claude Code y tus límites aparecerán aquí.", "Send a message in Claude Code and your limits will show up here.")
      : t("Usa Codex y tus límites aparecerán aquí.", "Use Codex and your limits will show up here.")}</p>` : "")
    + (cuentaTxt ? `<p class="cuenta">${esc(cuentaTxt)}</p>` : "");

  // activador (solo Claude)
  const act = p.activador;
  const caja = $("#activador");
  caja.hidden = prov !== "claude" || !act;
  if (!caja.hidden && !caja.contains(document.activeElement)) {
    const u = act.ultimo;
    caja.innerHTML = `<div class="activar-cab">${icono("bolt", true)}<strong>${t("Activar 5 horas", "Start 5-hour window")}</strong>
        <small>${act.ocupado ? t("enviando…", "sending…") : v5 && v5.reinicia ? t("abierta hasta ", "open until ") + hora(v5.reinicia) : t("sin ventana abierta", "no open window")}</small></div>
      <form class="campo" id="form-activar"><input id="mensaje" autocomplete="off" placeholder="${t("Escríbele a Claude…", "Message Claude…")}" ${act.ocupado ? "disabled" : ""}>
        <button class="redondo" type="submit">${icono(act.ocupado ? "progress_activity" : "send", true).replace('class="icono', `class="icono${act.ocupado ? " girando" : ""}`)}</button></form>
      ${u ? `<div class="respuesta ${u.ok ? "" : "error"}">${u.mensaje ? `<span class="tenue">${t("Tú: ", "You: ")}${esc(u.mensaje)}</span><br>` : ""}${esc(!u.ok ? u.error || t("No hubo respuesta.", "No answer.") : u.respuesta || t("Ventana activada ", "Window started ") + hace(ahora() - u.t))}</div>`
        : `<div class="respuesta tenue chico">${t("Vacío solo activa la ventana con un saludo a Haiku (cuesta casi nada).", "Empty just starts the window with a tiny Haiku greeting (costs almost nothing).")}</div>`}
      <div class="programa">${icono("schedule")}${t("Cada día a las", "Every day at")}
        <button class="flecha" data-hora="hora" data-d="-30">‹</button><span class="hora mono">${act.hora}</span><button class="flecha" data-hora="hora" data-d="30">›</button>
        <button class="interruptor ${act.programado ? "on" : ""}" data-sw="programado" aria-label="on/off"></button></div>
      <div class="programa">${icono("autorenew")}${t("Renovarla sola hasta las", "Keep renewing until")}
        <button class="flecha" data-hora="hasta" data-d="-30">‹</button><span class="hora mono">${act.hasta}</span><button class="flecha" data-hora="hasta" data-d="30">›</button>
        <button class="interruptor ${act.mantener ? "on" : ""}" data-sw="mantener" aria-label="on/off"></button></div>`;
  }

  // modelo
  const fam = familia(prov, p.modelo_actual);
  const hoy = (p.modelos_hoy || []).slice(0, 3), total = hoy.reduce((a, m) => a + m.nuevos, 0) || 1;
  $("#modelo").innerHTML = p.modelo_actual ? `<div class="modelo"><div class="circulo" style="background:${colorFam(fam)}">${icono(ICONO_FAM[fam] || "smart_toy", true)}</div>
    <div><small class="tenue chico">${t("Modelo en uso", "Current model")}</small><strong>${esc(p.modelo_actual)}</strong></div>
    <div class="reparto"><span class="tenue">${t("Hoy", "Today")}</span>${hoy.map((m) => `<div style="color:${colorFam(familia(prov, m.modelo))}">${esc(m.modelo.split(" ")[0])} ${Math.round((m.nuevos / total) * 100)} %</div>`).join("")}</div></div>`
    : `<p class="tenue chico">${t("Todavía no hay actividad.", "No activity yet.")}</p>`;

  // tokens
  const max = Math.max(1, ...p.por_minuto);
  $("#tokens").innerHTML = `<h3 style="display:flex">${t("Tokens de hoy", "Tokens today")}<span class="mono" style="margin-left:auto">${p.ritmo_por_min ? corto(p.ritmo_por_min) + "/min" : t("en pausa", "idle")}</span></h3>
    <div><span class="grande">${corto(p.tokens.hoy.nuevos)}</span> <span class="tenue chico">${p.tokens.hoy.mensajes} ${t("respuestas", "replies")}</span></div>
    <div class="barras">${p.por_minuto.map((v) => `<i class="${v ? "si" : ""}" style="height:${v ? Math.max(6, (v / max) * 100) : 4}%"></i>`).join("")}</div>
    <small class="tenue chico">${t("Última hora", "Last hour")}</small>`;

  // semana
  const maxDia = Math.max(1, ...p.por_dia.map((d) => d.nuevos));
  $("#semana").innerHTML = `<h3>${t("Últimos 7 días", "Last 7 days")} · ${corto(p.tokens.semana.nuevos)} tokens</h3>
    <div class="dias">${p.por_dia.map((d, i) => `<div class="${i === 6 ? "hoy" : ""}" title="${corto(d.nuevos)}"><b style="height:${(d.nuevos / maxDia) * 100}%"></b>${esc(d.dia)}</div>`).join("")}</div>`;

  // sesiones de hoy
  $("#sesiones").innerHTML = `<h3>${t("Sesiones de hoy", "Today's sessions")}</h3>` + (p.sesiones.length
    ? `<table class="tabla">${p.sesiones.map((s) => `<tr><td>${s.activa ? "●" : "○"} ${esc(s.proyecto)}</td><td class="tenue">${esc(s.modelo)}</td>
        <td class="tenue">${s.contexto != null ? t("contexto ", "context ") + Math.round(s.contexto) + "%" : ""}</td><td>${corto(s.nuevos)}</td></tr>`).join("")}</table>`
    : `<p class="tenue chico">${t("Ninguna todavía.", "None yet.")}</p>`);
}

// ------------------------------------------------------------------ modelos de IA
// Lo que usan las funciones que piensan (asistente, mirar la pantalla…): una clave de API o
// modelos locales con Ollama. Mientras se escribe una clave no se redibuja (perdería el texto).
const CABE = { gpu: ["bolt", "Rápido aquí", "Fast here", "--exito"], cpu: ["hourglass_top", "Anda, más lento", "Works, slower", "--terciario"], no: ["block", "No alcanza", "Too big", "--error"] };
let modelosDibujado = "";
function dibujarModelos() {
  const caja = $("#modelos-ia");
  const M = E.modelos;
  if (!caja || !M) return;
  if (caja.contains(document.activeElement) && document.activeElement.matches("input, select")) return;
  if (!ui.modPestana) ui.modPestana = M.modo === "api" || (M.ollama.estado === "no_instalado" && M.proveedores.some((p) => p.clave)) ? "api" : "local";
  const usando = M.listo
    ? `<span class="mod-chip ok">${icono("check_circle", true)}${esc(M.modo === "local" ? (M.local.texto || M.local.vision) : M.modelo)}${M.modo === "local" ? t(" · local", " · local") : " · " + esc((M.proveedores.find((p) => p.id === M.proveedor) || {}).nombre || "")}</span>`
    : `<span class="mod-chip alerta">${icono("info")}${esc(M.motivo)}</span>`;
  let cuerpo;
  if (ui.modPestana === "local") {
    const eq = M.equipo, gpu = eq.gpu && eq.gpu.nombre ? ` · ${esc(eq.gpu.nombre)} (${eq.gpu.vram_gb} GB)` : t(" · sin tarjeta de video dedicada", " · no dedicated GPU");
    const O = M.ollama, d = O.descarga;
    const ollama = O.estado === "activo" ? ""
      : O.estado === "apagado" ? `<div class="mod-aviso">${t("Ollama está instalado pero apagado.", "Ollama is installed but not running.")} <button class="boton principal" data-mod="arrancar_ollama">${t("Encender", "Start")}</button></div>`
      : `<div class="mod-aviso">${t("Para usar modelos en tu equipo hace falta Ollama (gratis).", "Local models need Ollama (free).")} <button class="boton principal" data-mod="instalar_ollama">${t("Instalar Ollama", "Install Ollama")}</button></div>`;
    const fila = (r) => {
      const [ic, es, en, color] = CABE[r.cabe];
      const bajando = d && d.modelo === r.id && !d.error && d.pct < 100;
      const tipo = r.vision ? "vision" : "texto";
      const boton = r.en_uso ? `<button class="listo" disabled title="${t("En uso", "In use")}">${icono("check")}</button>`
        : bajando ? `<span class="mod-barra"><b style="width:${d.pct}%"></b><i>${d.pct}%</i></span>`
        : r.instalado ? `<button class="boton" data-mod="usar" data-modelo="${esc(r.id)}" data-tipo="${tipo}">${t("Usar", "Use")}</button>`
        : r.cabe === "no" || O.estado === "no_instalado" ? ""
        : `<button class="boton${r.sugerido ? " principal" : ""}" data-mod="descargar" data-modelo="${esc(r.id)}">${t("Descargar", "Download")} · ${r.gb} GB</button>`;
      return `<div class="mod-fila${r.cabe === "no" ? " apagada" : ""}">
        <span class="circulo">${icono(r.vision ? "visibility" : "chat", r.en_uso)}</span>
        <div class="texto"><strong>${esc(r.id)}${r.sugerido ? ` <span class="mod-sugerido">${t("recomendado", "recommended")}</span>` : ""}</strong>
        <p>${esc(r.nota)}</p><small style="color:${VAR(color)}">${icono(ic)} ${t(es, en)}</small></div>${boton}</div>`;
    };
    const catalogo = new Set(M.recomendados.map((r) => r.id));
    const otros = O.modelos.filter((m) => !catalogo.has(m.nombre) && !catalogo.has(m.nombre.replace(/:latest$/, "")));
    cuerpo = `<p class="tenue chico">${t("Tu equipo: ", "Your computer: ")}${eq.ram_gb} GB ${t("de RAM", "RAM")}${gpu}</p>${ollama}
      ${d && d.error ? `<p class="error chico">${esc(d.modelo)}: ${esc(d.error)}</p>` : ""}
      <div class="mod-lista">${M.recomendados.map(fila).join("")}</div>
      ${otros.length ? `<p class="tenue chico">${t("Otros modelos que ya tienes:", "Other models you have:")}</p><div class="mod-chips">${otros.map((m) => {
        const tipo = m.vision ? "vision" : "texto", uso = M.local[tipo] === m.nombre;
        return `<button class="mod-chip${uso ? " ok" : ""}" data-mod="usar" data-modelo="${esc(m.nombre)}" data-tipo="${tipo}">${icono(m.vision ? "visibility" : "chat")}${esc(m.nombre)}</button>`;
      }).join("")}</div>` : ""}`;
  } else {
    const prov = (p) => {
      const activo = M.modo === "api" && M.proveedor === p.id;
      if (!p.clave) return `<form class="mod-fila mod-clave" data-prov-clave="${p.id}"><div class="texto"><strong>${esc(p.nombre)}</strong>
        <a class="chico" href="${esc(p.web)}" target="_blank" rel="noreferrer">${t("Conseguir una clave", "Get a key")} ${icono("open_in_new")}</a></div>
        <input type="password" name="clave" autocomplete="off" spellcheck="false" placeholder="${t("Pega tu clave", "Paste your key")}">
        <button class="boton principal">${t("Guardar", "Save")}</button></form>`;
      const opciones = (sel) => p.modelos.map((m) => `<option ${m === sel ? "selected" : ""}>${esc(m)}</option>`).join("");
      return `<div class="mod-fila"><span class="circulo">${icono("key", activo)}</span><div class="texto"><strong>${esc(p.nombre)}</strong>
        <small class="mono">••••${esc(p.final)}</small>${p.error ? `<small class="error">${esc(p.error)}</small>` : ""}
        ${activo && p.modelos.length ? `<label class="chico tenue">${t("Modelo", "Model")} <select data-mod-sel="texto">${opciones(M.modelo)}</select></label>
          <label class="chico tenue">${t("Para imágenes", "For images")} <select data-mod-sel="vision"><option value="">${t("el mismo", "same")}</option>${opciones(M.modelo_vision)}</select></label>` : ""}</div>
        ${activo ? `<button class="listo" disabled>${icono("check")}</button>` : `<button class="boton" data-mod="usar_api" data-prov="${p.id}">${t("Usar", "Use")}</button>`}
        <button class="redondo" data-mod="borrar_clave" data-prov="${p.id}" title="${t("Quitar la clave", "Remove key")}">${icono("delete")}</button></div>`;
    };
    cuerpo = `<p class="tenue chico">${t("La clave se guarda solo en este equipo y se usa para hablar directo con el proveedor. Cada uso se cobra en tu cuenta de ese proveedor.", "The key stays on this computer and is only sent to that provider. Usage is billed to your account there.")}</p>
      <div class="mod-lista">${M.proveedores.map(prov).join("")}</div>`;
  }
  const html = `<h3>${t("Modelos de IA para el asistente", "AI models for the assistant")}</h3>
    <div class="mod-cabeza">${usando}<span class="b-relleno"></span>${M.listo ? `<button class="boton" data-mod="probar">${t("Probar", "Test")}</button>` : ""}</div>
    ${ui.modRespuesta ? `<p class="chico mod-respuesta">${esc(ui.modRespuesta)}</p>` : ""}
    <div class="sub-pestanas"><button data-mod-p="local" class="${ui.modPestana === "local" ? "activa" : ""}">${icono("computer")} ${t("En mi equipo (gratis)", "On my computer (free)")}</button>
      <button data-mod-p="api" class="${ui.modPestana === "api" ? "activa" : ""}">${icono("key")} ${t("Con clave de API", "With an API key")}</button></div>
    ${cuerpo}`;
  if (html === modelosDibujado) return;
  modelosDibujado = html;
  caja.innerHTML = html;
}

// ------------------------------------------------------------------ dispositivos
function dibujarDisp() {
  const D = E.dispositivos || {};
  const lista = D.dispositivos || [];
  const d = lista.find((x) => x.id === ui.dispositivo) || lista[0];
  if (d) ui.dispositivo = d.id;
  if (!visor) visor = new Visor($("#visor"));
  visor.mostrar(d ? d.modelo3d : null, !!(d && d.conectado));
  $("#d-tipo").textContent = d ? d.tipo_nombre : "";
  $("#d-nombre").textContent = d ? d.nombre : t("Sin periféricos todavía", "No devices yet");
  const con = d && d.conectado ? d.conexion : t("Desconectado", "Disconnected");
  const ic = !d || !d.conectado ? "link_off" : con === "Bluetooth" ? "bluetooth" : con.includes("Wi-Fi") ? "wifi" : con.includes("USB") ? "usb" : "settings_input_antenna";
  $("#d-chip").innerHTML = d ? icono(ic) + esc(con) : "";
  const n = nivel(d);
  $("#d-anillo").innerHTML = d ? anillo(!d.conectado ? 0 : d.bateria != null ? d.bateria / 100 : 1, colorNivel(n), 64, 6,
    d.conectado && d.bateria != null ? d.bateria + "%" : icono(!d.conectado ? "power_off" : "power", true)) : "";

  $("#d-lista").innerHTML = lista.map((x) => {
    const nv = nivel(x);
    return `<button class="fila ${x.id === ui.dispositivo ? "elegida" : ""}" data-disp="${esc(x.id)}">
      <span class="circulo">${icono(ICONOS_DISP[x.tipo] || "devices", x.id === ui.dispositivo)}</span>
      <span class="texto"><strong>${esc(x.nombre)}</strong><small>${x.conectado ? esc(x.conexion) + (x.cargando ? t(" · cargando", " · charging") : "") : t("Desconectado", "Disconnected")}</small></span>
      <span class="bat" style="color:${colorNivel(nv)}">${x.conectado && x.bateria != null ? x.bateria + " %" : x.conectado ? t("Sin dato", "No data") : "—"}
        ${x.conectado && x.bateria != null ? `<i><b style="width:${x.bateria}%;background:${colorNivel(nv)}"></b></i>` : ""}</span></button>`;
  }).join("") || `<p class="tenue chico" style="padding:10px">${t("No encontré periféricos. Conecta uno por USB o Bluetooth.", "No devices found. Connect one over USB or Bluetooth.")}</p>`;

  $("#d-detalles").hidden = !d;
  if (d) {
    $("#d-detalles").innerHTML = d.detalles.slice(0, 5).map(([k, v]) => `<div class="detalle"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")
      + (d.horas_restantes ? `<div class="detalle" style="color:var(--primario)">${t("A este ritmo quedan unas ", "At this rate, about ")}${d.horas_restantes} h</div>` : "")
      + (d.ayuda ? `<p class="tenue chico" style="line-height:1.4">${esc(d.ayuda)}</p>` : "")
      + `<div class="botones">${d.acciones.map((a, i) => `<button class="boton ${i === 0 ? "principal" : ""}" data-accion="${a.id}">${icono({ conectar: "bluetooth_connected", desconectar: "bluetooth_disabled", sonar: "ring_volume", ajustes_bt: "settings_bluetooth" }[a.id] || "bolt")}${esc(a.etiqueta)}</button>`).join("")}</div>
      <div class="botones"><button class="enlace" data-accion="tipo">${icono("swap_horiz")}${t("Cambiar tipo", "Change type")}</button>
        <button class="enlace" data-accion="ocultar">${icono("visibility_off")}${t("Ocultar", "Hide")}</button>
        <button class="enlace" data-accion="probar">${icono("notifications")}${t("Probar aviso", "Test alert")}</button></div>
      ${ui.respuesta ? `<p class="tenue chico">${esc(ui.respuesta)}</p>` : ""}`;
  }
  const eq = D.equipo;
  const estados = { cargando: t(" · cargando", " · charging"), descargando: t(" · con batería", " · on battery"), llena: t(" · llena", " · full") };
  $("#d-pie").innerHTML = `<span>${eq ? t("Equipo ", "Laptop ") + eq.bateria + " %" + (estados[eq.estado] || "") : ""}</span><span>${D.app_celular ? esc(D.app_celular) + t(" activo", " on") : ""}</span>`;
}

// ------------------------------------------------------------------ habilidades
function dibujarHab() {
  const H = E.habilidades;
  const caja = $("#hab-contenido");
  document.querySelectorAll("#hab-pestanas button").forEach((b) => b.classList.toggle("activa", b.dataset.h === ui.hab));
  if (!H) { caja.innerHTML = ""; return; }
  const agente = (a) => (a === "claude" ? "Claude" : "Codex");
  if (ui.hab === "recomendadas") {
    const tarjeta = (r) => {
      const instalando = r.tarea && r.tarea.estado === "instalando";
      const lista = r.instalada_en.length > 0 && r.falta_en.length === 0;
      const nota = r.tarea && r.tarea.estado === "error" ? `<small class="error">${esc(r.tarea.mensaje)}</small>`
        : lista ? `<small>${t("Instalada en ", "Installed in ")}${r.instalada_en.map(agente).join(t(" y ", " & "))}${r.usos_7d ? ` · ${r.usos_7d} ${t("usos", "uses")}` : ""}</small>`
        : !r.agentes.length ? `<small>${t("Necesita Claude Code o Codex", "Needs Claude Code or Codex")}</small>` : "";
      const boton = !r.agentes.length ? ""
        : instalando ? `<button class="redondo" disabled>${icono("progress_activity").replace('class="icono', 'class="icono girando')}</button>`
        : lista ? `<button class="listo" data-hab="${r.id}" data-acc="desinstalar" title="${t("Quitar (solo si la instaló akari)", "Remove (only if installed by akari)")}">${icono("check")}</button>`
        : `<button class="boton principal" data-hab="${r.id}" data-acc="instalar">${r.instalada_en.length ? t("Completar", "Finish") : t("Instalar", "Install")}</button>`;
      return `<div class="tarjeta habilidad ${lista ? "puesta" : ""}"><span class="circulo">${icono(r.icono, lista)}</span>
        <div class="texto"><strong>${esc(r.nombre)}</strong><p>${esc(r.detalle)}</p>${nota}</div>${boton}</div>`;
    };
    caja.innerHTML = `<p class="intro">${t("10 habilidades útiles para el día a día. Se descargan de su repositorio original en GitHub.", "10 useful everyday skills. They download from their original GitHub repository.")}</p>
      <div class="rejilla">${H.recomendadas.map(tarjeta).join("")}${ui.verMas ? H.mas.map(tarjeta).join("") : ""}</div>
      <button class="mas" id="ver-mas">${ui.verMas ? t("Ver menos", "Show less") : t("Ver más habilidades", "More skills")}</button>`;
  } else if (ui.hab === "instaladas") {
    caja.innerHTML = `<div class="tarjeta"><table class="tabla">${H.instaladas.map((s) => `<tr><td><strong>${esc(s.nombre)}</strong><br><small class="tenue">${s.agentes.map(agente).join(" · ")}${s.origen !== "usuario" ? " · " + s.origen : ""}</small></td>
        <td class="tenue chico" style="max-width:380px;text-align:left">${esc(s.descripcion)}</td>
        <td><span class="uso ${s.usos_7d ? "si" : ""}">${s.usos_7d ? s.usos_7d + " " + t("usos", "uses") : t("sin usar", "unused")}</span></td></tr>`).join("")
      || `<tr><td>${t("Todavía no tienes habilidades. Mira las recomendadas.", "No skills yet. Check the recommended ones.")}</td></tr>`}</table>
      <p class="tenue chico">${t("Usos de los últimos 7 días en Claude Code.", "Uses in the last 7 days in Claude Code.")}</p></div>`;
  } else {
    caja.innerHTML = `<div class="tarjeta"><p class="tenue chico">${t("Conectores MCP: dan a tu IA acceso a otras apps (documentación, navegador, calendarios…).", "MCP connectors give your AI access to other apps (docs, browser, calendars…).")}</p>
      <table class="tabla">${H.mcp.map((m) => `<tr><td>${icono("hub")} ${esc(m.nombre)}</td><td class="tenue">${agente(m.agente)}</td></tr>`).join("") || `<tr><td>${t("No tienes conectores MCP.", "No MCP connectors.")}</td></tr>`}</table></div>`;
  }
}

// ------------------------------------------------------------------ herramientas
// Herramientas de terminal para quien usa Claude Code / Codex (akari/herramientas.py). Si la única
// forma de instalar pide contraseña, se copia el comando o se abre en una terminal.
let herrDibujado = "";
function dibujarHerr() {
  const caja = $("#herr-contenido");
  const T = E.herramientas;
  if (!caja || !T) return;
  const fila = (x) => {
    const tarea = x.tarea || {}, m = x.metodo;
    const boton = x.instalada ? `<button class="listo" disabled title="${esc(x.ruta || x.nota)}">${icono("check")}</button>`
      : tarea.estado === "instalando" ? `<button class="redondo" disabled>${icono("progress_activity").replace('class="icono', 'class="icono girando')}</button>`
      : !m ? `<a class="boton" href="${esc(x.web)}" target="_blank" rel="noreferrer">${t("Ver cómo", "How to")} ${icono("open_in_new")}</a>`
      : m.sudo ? `<button class="redondo" data-herr="copiar" data-id="${x.id}" data-texto="${esc(m.texto)}" title="${t("Copiar el comando", "Copy the command")}">${icono("content_copy")}</button>
          <button class="boton" data-herr="terminal" data-id="${x.id}" title="${t("Abrir una terminal con el comando (pide tu contraseña)", "Open a terminal with the command (asks your password)")}">${icono("terminal")} ${t("Terminal", "Terminal")}</button>`
      : `<button class="boton principal" data-herr="instalar" data-id="${x.id}">${t("Instalar", "Install")}</button>`;
    const pie = tarea.estado === "error" ? `<small class="error">${esc(tarea.mensaje)}</small>`
      : x.instalada ? (x.nota ? `<small class="tenue">${esc(x.nota)}</small>` : "")
      : m ? `<small class="mono tenue">${m.sudo ? icono("lock") + " " : ""}${esc(m.texto)}</small>`
      : x.nota ? `<small class="tenue">${esc(x.nota)}</small>` : "";
    return `<div class="mod-fila${x.instalada ? "" : " herr-falta"}"><span class="circulo">${icono(x.icono, x.instalada)}</span>
      <div class="texto"><strong>${esc(x.nombre)}</strong><p>${esc(x.detalle)}</p>${pie}</div>${boton}</div>`;
  };
  const html = `<div class="tarjeta"><h3>${t("Herramientas para tu IA", "Tools for your AI")}</h3>
    <p class="tenue chico">${t("Programas de terminal que Claude Code y Codex aprovechan: seguridad, contexto y gasto. Se instalan con lo que ya tienes (uv, npm, Homebrew, winget…).", "Terminal programs Claude Code and Codex make good use of: security, context and spending. They install with what you already have (uv, npm, Homebrew, winget…).")}</p>
    ${ui.herrRespuesta ? `<p class="chico mod-respuesta">${esc(ui.herrRespuesta)}</p>` : ""}
    <div class="mod-lista">${T.lista.map(fila).join("")}</div></div>`;
  if (html === herrDibujado) return;
  herrDibujado = html;
  caja.innerHTML = html;
}

// ------------------------------------------------------------------ documentos
// Conversor PDF / Word / Excel ⇄ Markdown. Lo soltado sube al servicio (o va su ruta, si la app
// de escritorio la da con window.akari.rutaDe) y el resultado queda junto al original.
const ICONO_DOC = { md: "markdown", docx: "description", pdf: "picture_as_pdf" };
let docDibujado = "";
function dibujarDoc() {
  const caja = $("#doc-contenido");
  const D = E.documentos;
  if (!caja || !D) return;
  ui.docModo = ui.docModo || "a-md";
  ui.docFormato = ui.docFormato || "docx";
  const pestanas = `<div class="sub-pestanas"><button data-doc-modo="a-md" class="${ui.docModo === "a-md" ? "activa" : ""}">${t("A Markdown", "To Markdown")}</button>
      <button data-doc-modo="desde-md" class="${ui.docModo === "desde-md" ? "activa" : ""}">${t("Desde Markdown", "From Markdown")}</button></div>`;
  let html;
  if (!D.listo) {
    html = `<div class="tarjeta doc-instalar"><span class="circulo">${icono("swap_horiz")}</span>
      <div class="texto"><strong>${t("Conversor de documentos", "Document converter")}</strong>
      <p>${t("PDF, Word y Excel a Markdown (para darle a una IA o a Obsidian) y Markdown o lo que copiaste a Word o PDF. Se instala una vez (≈150 MB, sin contraseña).", "PDF, Word and Excel to Markdown (for an AI or Obsidian) and Markdown or copied text to Word or PDF. Installs once (≈150 MB, no password).")}</p>
      ${D.error_instalacion ? `<small class="error">${esc(D.error_instalacion)}</small>` : ""}</div>
      ${D.instalando ? `<button class="redondo" disabled>${icono("progress_activity").replace('class="icono', 'class="icono girando')}</button>`
        : `<button class="boton principal" data-doc="instalar">${t("Instalar", "Install")}</button>`}</div>`;
  } else {
    const aMd = ui.docModo === "a-md";
    const pdfNo = !aMd && ui.docFormato === "pdf" && !D.libreoffice;
    const fila = (x) => {
      const ic = x.estado === "listo" ? ICONO_DOC[x.formato] || "description" : x.estado === "error" ? "error" : "progress_activity";
      const destino = x.formato === "md" ? "Markdown" : x.formato === "pdf" ? "PDF" : "Word";
      return `<div class="doc-fila e-${x.estado}" ${x.estado === "listo" ? `data-doc="abrir" data-id="${x.id}" title="${t("Abrir", "Open")}"` : ""}>
        ${icono(ic).replace('class="icono', `class="icono${x.estado === "convirtiendo" || x.estado === "cola" ? " girando" : ""}`)}
        <div class="texto"><strong>${esc(x.nombre)}</strong><small>${x.estado === "cola" ? t("En espera…", "Waiting…") : x.estado === "convirtiendo" ? t("Convirtiendo a ", "Converting to ") + destino + "…" : esc(x.estado === "listo" ? "→ " + destino + " · " + x.mensaje : x.mensaje)}</small></div>
        ${x.estado === "listo" ? `<button class="redondo" data-doc="abrir" data-id="${x.id}" data-carpeta="1" title="${t("Abrir carpeta", "Open folder")}">${icono("folder_open")}</button>` : ""}</div>`;
    };
    html = pestanas + `${aMd ? "" : `<div class="doc-formatos"><span class="tenue chico">${t("Sacar como", "Save as")}</span>
        <button class="mod-chip${ui.docFormato === "docx" ? " ok" : ""}" data-doc-formato="docx">${icono("description")}Word</button>
        <button class="mod-chip${ui.docFormato === "pdf" ? " ok" : ""}" data-doc-formato="pdf">${icono("picture_as_pdf")}PDF</button></div>`}
      ${pdfNo ? `<p class="chico error">${t("Para PDF hace falta LibreOffice (gratis). Word funciona sin él.", "PDF needs LibreOffice (free). Word works without it.")}</p>` : ""}
      <div class="doc-soltar">${icono(aMd ? "upload_file" : "markdown")}
        <strong>${aMd ? t("Suelta aquí PDF, Word, Excel o CSV", "Drop PDF, Word, Excel or CSV here") : t("Suelta aquí archivos Markdown (.md)", "Drop Markdown (.md) files here")}</strong>
        <span class="tenue chico">${aMd ? t("Sale un .md junto al original, listo para una IA u Obsidian.", "A .md appears next to the original, ready for an AI or Obsidian.") : t("Sale un documento con las tablas bien repartidas.", "You get a document with well-sized tables.")}</span>
        <div class="doc-botones"><button class="boton principal" data-doc="elegir" ${D.eligiendo || pdfNo ? "disabled" : ""}>${icono("folder_open")} ${t("Elegir archivos", "Choose files")}</button>
        ${aMd ? "" : `<button class="boton" data-doc="portapapeles" ${pdfNo ? "disabled" : ""}>${icono("content_paste")} ${t("Convertir lo copiado", "Convert clipboard")}</button>`}</div></div>
      ${ui.docRespuesta ? `<p class="chico mod-respuesta">${esc(ui.docRespuesta)}</p>` : ""}
      ${D.trabajos.length ? `<div class="tarjeta"><div class="doc-cabeza"><h3>${t("Últimos", "Recent")}</h3><span class="b-relleno"></span>
        <button class="redondo" data-doc="carpeta" title="${t("Carpeta de akari en Documentos", "akari folder in Documents")}">${icono("folder")}</button>
        <button class="redondo" data-doc="limpiar" title="${t("Vaciar la lista (no borra archivos)", "Clear list (keeps files)")}">${icono("delete_sweep")}</button></div>
        <div class="doc-lista">${D.trabajos.slice(0, 12).map(fila).join("")}</div></div>` : ""}`;
  }
  if (html === docDibujado) return;
  docDibujado = html;
  caja.innerHTML = html;
}

// Audio y video → Markdown (akari/audio.py): en el equipo con faster-whisper o con la clave de
// Groq / OpenAI. Lo soltado en la página de documentos que sea audio o video viene aquí solo.
const EXT_AUDIO = /\.(mp3|wav|m4a|ogg|oga|opus|flac|aac|wma|amr|mpga|mpeg|mp4|mkv|mov|avi|webm|m4v|3gp|wmv)$/i;
const reloj = (seg) => { seg = Math.max(0, Math.round(seg)); const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(s).padStart(2, "0"); };
let audioDibujado = "";
function dibujarAudio() {
  const caja = $("#audio-contenido");
  if (!caja || !E.audio) return;
  const html = htmlAudio();
  if (html === audioDibujado) return;
  audioDibujado = html;
  caja.innerHTML = html;
}
function htmlAudio() {
  const A = E.audio;
  if (!A) return "";
  const instalar = A.listo_local ? "" : A.instalando
    ? `<button class="redondo" disabled>${icono("progress_activity").replace('class="icono', 'class="icono girando')}</button>`
    : `<button class="boton${A.usa ? "" : " principal"}" data-aud="instalar">${t("Instalar", "Install")}</button>`;
  const local = `<div class="mod-fila"><span class="circulo">${icono("computer", A.usa === "local")}</span><div class="texto">
      <strong>${t("En tu equipo (gratis, sin internet)", "On your computer (free, offline)")}</strong>
      <p>${A.gpu ? t(`Whisper large-v3-turbo en tu ${esc(A.gpu)}: rápido y preciso.`, `Whisper large-v3-turbo on your ${esc(A.gpu)}: fast and accurate.`)
        : t("Whisper small en el procesador: tarda más o menos lo que dura el audio.", "Whisper small on the processor: takes about as long as the audio.")}
        ${A.listo_local ? "" : t(` Se instala una vez (${A.gpu ? "≈2 GB" : "≈400 MB"} con el modelo, sin contraseña).`, ` Installs once (${A.gpu ? "≈2 GB" : "≈400 MB"} with the model, no password).`)}</p>
      ${A.error_instalacion ? `<small class="error">${esc(A.error_instalacion)}</small>` : ""}</div>${A.listo_local ? `<button class="listo" disabled>${icono("check")}</button>` : instalar}</div>`;
  const api = `<div class="mod-fila"><span class="circulo">${icono("key", !!A.api && A.usa === A.api)}</span><div class="texto">
      <strong>${t("Con tu clave de API", "With your API key")}</strong>
      <p>${A.api ? t(`Whisper de ${esc(A.api_nombre)}: rápido; cada minuto se cobra en tu cuenta.`, `${esc(A.api_nombre)} Whisper: fast; billed per minute to your account.`)
        : t("Guarda una clave de Groq u OpenAI en «Modelos de IA».", "Save a Groq or OpenAI key in “AI models”.")}</p></div>
      ${A.api ? `<button class="listo" disabled>${icono("check")}</button>` : `<button class="boton" data-ir="modelos-api">${t("Agregar clave", "Add key")}</button>`}</div>`;
  const ambos = A.listo_local && A.api;
  const modos = ambos ? `<div class="doc-formatos"><span class="tenue chico">${t("Usar", "Use")}</span>
      ${[["auto", t("Automático", "Automatic")], ["local", t("Mi equipo", "My computer")], ["api", A.api_nombre]].map(([m, n]) =>
        `<button class="mod-chip${A.modo === m ? " ok" : ""}" data-aud="ajustes" data-modo="${m}">${esc(n)}</button>`).join("")}</div>` : "";
  if (!A.usa) return `<div class="tarjeta"><h3>${t("Audio y video a texto", "Audio and video to text")}</h3>
      <p class="tenue chico">${t("Suelta una clase, una reunión o un video y sale un .md con la transcripción junto al original. Elige cómo:", "Drop a lecture, a meeting or a video and get a .md transcript next to the original. Choose how:")}</p>
      <div class="mod-lista">${local}${api}</div></div>`;
  const g = A.grabacion;
  const grabar = !g.disponible ? "" : g.desde
    ? `<button class="boton principal" data-aud="parar">${icono("stop_circle")} ${t("Parar", "Stop")} · <span class="mono">${reloj(ahora() - g.desde)}</span></button>`
    : `<button class="boton" data-aud="grabar" title="${t("Graba tu micrófono y lo que suena en el equipo", "Records your microphone and what plays on the computer")}">${icono("radio_button_checked")} ${t("Grabar reunión", "Record meeting")}</button>`;
  const fila = (x) => {
    const ocupado = x.estado === "cola" || x.estado === "transcribiendo";
    const ic = x.estado === "listo" ? "description" : x.estado === "error" ? "error" : "progress_activity";
    const sub = x.estado === "cola" ? t("En espera…", "Waiting…")
      : x.estado === "transcribiendo" ? t("Transcribiendo", "Transcribing") + (x.pct != null ? ` · ${x.pct} %` : "…")
      : x.estado === "listo" ? "→ Markdown · " + x.mensaje : x.mensaje;
    const res = x.resumen === "haciendo" ? `<button class="redondo" disabled>${icono("progress_activity").replace('class="icono', 'class="icono girando')}</button>`
      : x.estado === "listo" ? `<button class="redondo${x.resumen === "listo" ? " hecho" : ""}" data-aud="resumir" data-id="${x.id}" title="${x.resumen === "listo" ? t("Resumen hecho (otra vez)", "Summary done (again)") : t("Resumir y sacar notas", "Summarize and take notes")}">${icono("summarize", x.resumen === "listo")}</button>` : "";
    return `<div class="doc-fila e-${x.estado === "transcribiendo" ? "convirtiendo" : x.estado}" ${x.estado === "listo" ? `data-aud="abrir" data-id="${x.id}" title="${t("Abrir", "Open")}"` : ""}>
      ${icono(ic).replace('class="icono', `class="icono${ocupado ? " girando" : ""}`)}
      <div class="texto"><strong>${esc(x.nombre)}</strong><small>${esc(sub)}${x.resumen && x.resumen.startsWith("error") ? ` · <span class="error">${esc(x.resumen.slice(7))}</span>` : ""}</small></div>
      ${res}${x.estado === "listo" ? `<button class="redondo" data-aud="abrir" data-id="${x.id}" data-carpeta="1" title="${t("Abrir carpeta", "Open folder")}">${icono("folder_open")}</button>` : ""}</div>`;
  };
  return `${modos}
    <div class="doc-soltar">${icono("graphic_eq")}
      <strong>${t("Suelta aquí un audio o un video", "Drop an audio or video file here")}</strong>
      <span class="tenue chico">${t("Sale un .md con la transcripción junto al original. ", "A .md transcript appears next to the original. ")}${esc(A.usa === "local" ? "Whisper " + A.modelo_local : "Whisper · " + A.api_nombre)}</span>
      <div class="doc-botones"><button class="boton principal" data-aud="elegir" ${A.eligiendo ? "disabled" : ""}>${icono("folder_open")} ${t("Elegir archivos", "Choose files")}</button>${grabar}</div></div>
    <div class="aud-opcion"><span>${t("Resumir y sacar notas al terminar", "Summarize and take notes when done")}<small class="tenue chico">${A.ia_lista ? t("Con el modelo de «Modelos de IA».", "With the model in “AI models”.") : t("Agrega una clave de API o usa un modelo local.", "Add an API key or use a local model.")}</small></span>
      ${A.ia_lista ? `<button class="interruptor ${A.resumir ? "on" : ""}" data-aud="ajustes" data-resumir="${!A.resumir}" aria-label="on/off"></button>` : `<button class="boton" data-ir="modelos">${t("Elegir modelo", "Choose model")}</button>`}</div>
    ${ui.docRespuesta ? `<p class="chico mod-respuesta">${esc(ui.docRespuesta)}</p>` : ""}
    ${!A.listo_local || !A.api ? `<details class="tarjeta aud-mas"><summary class="tenue chico">${t("Otra forma de transcribir", "Another way to transcribe")}</summary><div class="mod-lista">${A.listo_local ? api : local}</div></details>` : ""}
    ${A.trabajos.length ? `<div class="tarjeta"><div class="doc-cabeza"><h3>${t("Últimos", "Recent")}</h3><span class="b-relleno"></span>
      <button class="redondo" data-aud="limpiar" title="${t("Vaciar la lista (no borra archivos)", "Clear list (keeps files)")}">${icono("delete_sweep")}</button></div>
      <div class="doc-lista">${A.trabajos.slice(0, 12).map(fila).join("")}</div></div>` : ""}`;
}

async function subirDocumentos(archivos) {
  const D = E && E.documentos, A = E && E.audio;
  if (!D) return;
  // los audios y videos van a la transcripción (el servicio los reconoce por la extensión)
  const audios = archivos.filter((f) => EXT_AUDIO.test(f.name));
  if (audios.length) mostrarPieza("audio");
  if (audios.length && !(A && A.usa)) return;           // la pieza de audio dice cómo prepararla
  if (audios.length < archivos.length && !audios.length) mostrarPieza("documentos");
  archivos = archivos.filter((f) => EXT_AUDIO.test(f.name) || D.listo);
  const rutas = [];
  ui.docRespuesta = "";
  for (const f of archivos) {
    const ruta = window.akari && window.akari.rutaDe ? window.akari.rutaDe(f) : "";
    if (ruta) { rutas.push(ruta); continue; }
    try {
      const r = await fetch("/api/documentos/subir", { method: "POST", body: f, headers: { "Content-Type": "application/octet-stream",
        "X-Akari-Nombre": encodeURIComponent(f.name), "X-Akari-Formato": ui.docFormato || "docx" } });
      const j = await r.json();
      if (!j.ok) ui.docRespuesta = j.mensaje || f.name;
    } catch { ui.docRespuesta = t("akari no respondió.", "akari did not answer."); }
  }
  if (rutas.length) {
    const r = await enviar("/api/documentos", { accion: "convertir", rutas, formato: ui.docFormato });
    if (!r.ok) ui.docRespuesta = r.mensaje || "";
  }
  docDibujado = "";
  audioDibujado = "";
  dibujar();
}
// Soltar archivos: en la página de documentos o de audio, o en cualquier parte de la burbuja del
// grupo Archivos (cerrada también). Al pasar por encima se marca la zona y, en la burbuja, se abre
// en la pieza que corresponde (el tipo MIME ya se ve antes de soltar; el nombre, no).
const dondeSoltar = (e) => e.target.closest && (e.target.closest("#p-doc, #p-audio") || (burbuja === "archivos" && e.target.closest("#b-forma")));
const zonaActiva = () => document.querySelector(`#${PIEZAS[ui.pagina]} .doc-soltar`);
document.addEventListener("dragover", (e) => {
  if (!dondeSoltar(e)) return;
  e.preventDefault();
  if (burbuja === "archivos") {
    const tipos = [...e.dataTransfer.items].map((i) => i.type);
    const audio = tipos.length && tipos.every((x) => /^(audio|video)\//.test(x));
    if (audio && ui.pagina !== "audio") mostrarPieza("audio");
    else if (!audio && tipos.some((x) => x && !/^(audio|video)\//.test(x)) && ui.pagina !== "documentos") mostrarPieza("documentos");
    if (window.akari) window.akari.burbuja("abrir");
  }
  const zona = zonaActiva();
  if (zona) zona.classList.add("encima");
});
document.addEventListener("dragleave", (e) => { if (!e.relatedTarget || !dondeSoltar({ target: e.relatedTarget })) { const z = zonaActiva(); if (z) z.classList.remove("encima"); } });
document.addEventListener("drop", (e) => {
  if (!dondeSoltar(e)) return;
  e.preventDefault();
  const z = zonaActiva();
  if (z) z.classList.remove("encima");
  if (e.dataTransfer.files.length) subirDocumentos([...e.dataTransfer.files]);
});

// ------------------------------------------------------------------ cabecera de las burbujas
// Lo mismo que muestran cerradas las cápsulas de Quickshell (capsulas/Capsula*.qml).
function textoCorto(d) {
  if (!d || !d.conectado) return "—";
  if (d.bateria != null) return d.bateria + "%";
  return (d.conexion || "").includes("USB") ? "USB" : "OK";
}
const FAMILIAS_CHIP = { Opus: "--primario", Fable: "--terciario", Sonnet: "--secundario", Haiku: "--exito", GPT: "--exito" };

let cabeceraDibujada = "";
function dibujarCabecera() {
  // solo se toca el DOM si cambió algo (así no se reinicia la animación del punto que late)
  const html = htmlCabecera();
  if (html === cabeceraDibujada) return;
  cabeceraDibujada = html;
  $("#b-fila").innerHTML = html;
}

// Un chip por pieza; si el grupo tiene una sola pieza visible, su chip a lo ancho (sin pestañas).
function htmlCabecera() {
  if (!E) return `<span class="tenue chico b-centro">${t("Iniciando akari…", "Starting akari…")}</span>`;
  const ps = piezasDe(burbuja);
  $("#b-fila").classList.toggle("grupo", ps.length > 1);
  if (ps.length === 1) return htmlChip(ps[0].id, true);
  return ps.map((p) => `<span class="b-pieza${p.id === ui.pagina ? " elegida" : ""}" data-pieza="${p.id}" style="width:${p.chip}px" title="${esc(nombrePieza(p.id))}">${htmlChip(p.id, false)}</span>`).join("");
}

// Lo mismo que muestran los chips de las cápsulas de Quickshell (capsulas/Pieza*.qml).
function htmlChip(id, ancho) {
  if (id === "uso") {
    const ia = E.ia || {};
    const { prov } = proveedorActual();
    const p = ia[prov];
    const v5 = p && p.limites.cinco_horas;
    const fam = p ? familia(prov, p.modelo_actual) : "";
    const ultima = p && p.cinta && p.cinta[0];
    const trabajando = !!ultima && ahora() - ultima.t < 25;
    const color = colorLibre(v5);
    const colorF = FAMILIAS_CHIP[fam] ? VAR(FAMILIAS_CHIP[fam]) : VAR("--texto-var");
    if (!ancho) return `${anillo(v5 ? v5.libre / 100 : 0, color, 20, 4)}<span class="b-num" style="color:${color}">${v5 ? Math.round(v5.libre) + "%" : "—"}</span><i class="b-punto${trabajando ? " late" : ""}"></i>`;
    return `${anillo(v5 ? v5.libre / 100 : 0, color, 22, 4)}
      <span class="b-num" style="color:${color}">${v5 ? Math.round(v5.libre) + "%" : "—"}</span>
      <span class="tenue chico">${!prov ? t("sin Claude ni Codex", "no Claude or Codex") : v5 ? t("libre", "left") : t("sin lectura", "no data")}</span>
      <span class="b-relleno"></span>
      ${fam ? `<span class="b-chip" style="color:${colorF};background:color-mix(in srgb, ${colorF} 16%, transparent)">${icono(ICONO_FAM[fam] || "smart_toy", true)}${esc(fam)}</span>` : ""}
      ${v5 && v5.reinicia ? `<span class="mono chico tenue">${cuenta(v5.reinicia - ahora())}</span>` : ""}
      <i class="b-punto${trabajando ? " late" : ""}"></i>`;
  }
  if (id === "dispositivos") {
    const lista = (E.dispositivos || {}).dispositivos || [];
    const alerta = lista.some((d) => nivel(d) === "bajo" && !d.cargando);
    $("#b-cabecera").classList.toggle("alerta", alerta);
    return lista.slice(0, 4).map((d) => {
      const nv = nivel(d);
      return `<span class="b-disp${nv === "bajo" && !d.cargando ? " late" : ""}">${icono(ICONOS_DISP[d.tipo] || "devices", d.conectado).replace('class="icono', `style="color:${colorNivel(nv)}" class="icono`)}
        <span class="mono chico" style="color:${nv === "nada" ? VAR("--contorno") : VAR("--texto-var")}">${textoCorto(d)}${d.cargando ? "⚡" : ""}</span></span>`;
    }).join("") || `<span class="tenue chico b-centro">${t("Sin periféricos todavía", "No devices yet")}</span>`;
  }
  if (id === "modelos") {
    const M = E.modelos, d = M && M.ollama.descarga, bajando = d && !d.error && d.pct < 100;
    return icono(bajando ? "progress_activity" : M && M.listo ? "psychology" : "key", !!(M && M.listo))
      .replace('class="icono', `style="color:${VAR(M && M.listo ? "--primario" : "--terciario")}" class="icono b-estrella${bajando ? " girando" : ""}`)
      + (ancho ? `<span class="tenue chico">${M && M.listo ? esc(M.modo === "local" ? M.local.texto || M.local.vision : M.modelo) : esc(M ? M.motivo : "")}</span>` : "");
  }
  if (id === "habilidades") {
    const H = E.habilidades;
    const instalando = !!H && [...H.recomendadas, ...H.mas].some((r) => r.tarea && r.tarea.estado === "instalando");
    return `${icono("auto_awesome", true).replace('class="icono', `class="icono b-estrella${instalando ? " girando" : ""}`)}
      <span class="b-num">${H ? H.total : "—"}</span>${ancho ? `<span class="tenue chico">${t("habilidades", "skills")}</span>` : ""}`;
  }
  if (id === "herramientas") {
    const T = E.herramientas;
    const instalando = !!T && T.lista.some((x) => x.tarea && x.tarea.estado === "instalando");
    return `${icono("construction", true).replace('class="icono', `class="icono b-estrella${instalando ? " late" : ""}`)}
      <span class="b-num${ancho ? "" : " chico"}">${T ? T.instaladas + "/" + T.total : "—"}</span>${ancho ? `<span class="tenue chico">${t("herramientas", "tools")}</span>` : ""}`;
  }
  if (id === "documentos") {
    const D = E.documentos;
    const activos = D ? D.trabajos.filter((x) => x.estado === "cola" || x.estado === "convirtiendo").length : 0;
    const ic = icono("swap_horiz", true).replace('class="icono', `${D && !D.listo ? 'style="color:var(--contorno)" ' : ""}class="icono b-estrella${activos ? " girando" : ""}`);
    if (!ancho) return `${ic}<span class="b-num">${!D ? "—" : activos || D.trabajos.filter((x) => x.estado === "listo").length}</span>`;
    const ultimo = D && D.trabajos[0];
    return `${ic}<span class="tenue chico">${!D ? "—" : !D.listo ? t("Conversor sin instalar", "Converter not installed") : activos ? t("Convirtiendo ", "Converting ") + activos + "…" : ultimo ? esc(ultimo.nombre) : t("Suelta un documento", "Drop a document")}</span>`;
  }
  if (id === "audio") {
    const A = E.audio;
    if (A && A.grabacion.desde) return `${icono("radio_button_checked", true).replace('class="icono', 'class="icono late" style="color:var(--error)"')}
      <span class="mono chico" style="color:var(--error)">${reloj(ahora() - A.grabacion.desde)}</span>`;
    const actual = A && A.trabajos.find((x) => x.estado === "transcribiendo");
    const ic = icono("graphic_eq", true).replace('class="icono', `${A && !A.usa ? 'style="color:var(--contorno)" ' : ""}class="icono b-estrella${actual ? " late" : ""}`);
    return `${ic}<span class="b-num${actual ? " chico" : ""}"${actual ? ' style="color:var(--primario)"' : ""}>${!A ? "—" : actual ? (actual.pct != null ? actual.pct + "%" : "…") : A.trabajos.filter((x) => x.estado === "listo").length}</span>`;
  }
  return "";
}

// ------------------------------------------------------------------ general
function dibujar() {
  if (!E) return;
  aplicarTema(E.tema);
  $("#servicio").classList.add("vivo");
  if (burbuja) dibujarCabecera();
  const dibujos = { dispositivos: dibujarDisp, uso: dibujarIA, modelos: dibujarModelos, habilidades: dibujarHab, herramientas: dibujarHerr, documentos: dibujarDoc, audio: dibujarAudio };
  if (dibujos[ui.pagina]) dibujos[ui.pagina]();
}

// ------------------------------------------------------------------ grupos y piezas
const NOMBRES = { dispositivos: ["Dispositivos", "Devices"], uso: ["Uso de IA", "AI usage"], modelos: ["Modelos", "Models"],
  habilidades: ["Habilidades", "Skills"], herramientas: ["Herramientas", "Tools"], documentos: ["Documentos", "Documents"], audio: ["Audio", "Audio"] };
const nombrePieza = (id) => (NOMBRES[id] ? t(...NOMBRES[id]) : id);
const grupoDe = (id) => GRUPOS.find((g) => g.id === id) || GRUPOS[0];
const grupoDePieza = (pieza) => (GRUPOS.find((g) => g.piezas.some((p) => p.id === pieza)) || GRUPOS[0]).id;
function piezasDe(grupo) {
  const ps = grupoDe(grupo).piezas.filter((p) => PIEZAS[p.id]);
  return soloPieza ? ps.filter((p) => p.id === soloPieza) : ps;
}
const ultimaPieza = {};               // grupo -> pieza que se vio por última vez
function mostrarPieza(id) {
  if (!PIEZAS[id]) return;
  ui.pagina = id;
  if (!burbuja) ui.grupo = grupoDePieza(id);
  ultimaPieza[ui.grupo] = id;
  for (const [pieza, seccion] of Object.entries(PIEZAS)) $("#" + seccion).classList.toggle("activa", pieza === id);
  dibujarPiezas();
  dibujar();
}
function mostrarGrupo(id) {
  const ps = piezasDe(id);
  mostrarPieza(ps.some((p) => p.id === ultimaPieza[id]) ? ultimaPieza[id] : ps[0].id);
}
// panel: los tres grupos arriba y las piezas del elegido debajo
function dibujarPiezas() {
  if (burbuja) return;
  document.querySelectorAll("#pestanas button").forEach((b) => b.classList.toggle("activa", b.dataset.g === ui.grupo));
  const ps = piezasDe(ui.grupo);
  $("#piezas").innerHTML = ps.length > 1
    ? ps.map((p) => `<button data-pieza="${p.id}" class="${p.id === ui.pagina ? "activa" : ""}">${icono(p.icono)} ${esc(nombrePieza(p.id))}</button>`).join("") : "";
}
// en el panel se ven todas las piezas; en la burbuja, solo las que no ocultó el usuario
async function cargarGrupos() {
  try {
    const r = await fetch(burbuja ? "/api/burbujas" : "/api/burbujas?todas=1");
    const d = await r.json();
    if (Array.isArray(d.grupos) && d.grupos.length) GRUPOS = d.grupos;
  } catch { return; }
  if (burbuja && !piezasDe(burbuja).some((p) => p.id === ui.pagina) && piezasDe(burbuja).length) mostrarPieza(piezasDe(burbuja)[0].id);
  cabeceraDibujada = "";
  dibujarPiezas();
  dibujar();
}

function traducir() {
  document.documentElement.lang = idioma;
  document.querySelectorAll("[data-t]").forEach((el) => {
    const [es, en] = el.dataset.t.split("|");
    el.textContent = t(es, en);
  });
}

function conectar() {
  const fuente = new EventSource("/eventos");
  fuente.onmessage = (m) => {
    E = JSON.parse(m.data);
    if (E.idioma && E.idioma !== idioma) { idioma = E.idioma; traducir(); dibujarPiezas(); }
    dibujar();
  };
  fuente.onerror = () => { $("#servicio").classList.remove("vivo"); };
}

// eventos (delegados: el contenido se redibuja)
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button, .doc-fila[data-doc], .doc-fila[data-aud]");
  if (!b) return;
  if (b.closest("#pestanas")) return mostrarGrupo(b.dataset.g);
  if (b.dataset.pieza) return mostrarPieza(b.dataset.pieza);
  if (b.dataset.prov) { ui.proveedor = b.dataset.prov; return dibujar(); }
  if (b.dataset.disp) { ui.dispositivo = b.dataset.disp; ui.respuesta = ""; return dibujar(); }
  if (b.dataset.accion) {
    ui.respuesta = t("Un momento…", "One moment…");
    dibujar();
    const r = await enviar("/api/dispositivos", { id: ui.dispositivo, accion: b.dataset.accion });
    ui.respuesta = r.mensaje || "";
    return dibujar();
  }
  if (b.dataset.h) { ui.hab = b.dataset.h; return dibujar(); }
  if (b.id === "ver-mas") { ui.verMas = !ui.verMas; return dibujar(); }
  if (b.dataset.hab) { await enviar("/api/habilidades", { id: b.dataset.hab, accion: b.dataset.acc }); return; }
  if (b.dataset.sw) {
    const act = E.ia.claude.activador;
    return enviar("/api/ia/activador", { [b.dataset.sw]: !act[b.dataset.sw] });
  }
  if (b.dataset.hora) {
    const act = E.ia.claude.activador;
    const [h, m] = act[b.dataset.hora].split(":").map(Number);
    const total = (((h * 60 + m + Number(b.dataset.d)) % 1440) + 1440) % 1440;
    return enviar("/api/ia/activador", { [b.dataset.hora]: `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}` });
  }
  if (b.id === "b-panel" && window.akari) window.akari.alternarPanel();
  if (b.dataset.ir) {
    ui.modPestana = b.dataset.ir === "modelos-api" ? "api" : ui.modPestana;
    modelosDibujado = "";
    if (burbuja && !piezasDe(burbuja).some((p) => p.id === "modelos")) return window.akari && window.akari.alternarPanel();
    return mostrarPieza("modelos");
  }
  if (b.dataset.herr) {
    const acc = b.dataset.herr;
    if (acc === "copiar" && navigator.clipboard) {
      try { await navigator.clipboard.writeText(b.dataset.texto); ui.herrRespuesta = t("Comando copiado: pégalo en una terminal.", "Command copied: paste it in a terminal."); herrDibujado = ""; return dibujar(); } catch { /* lo copia el servicio */ }
    }
    b.disabled = true;
    const r = await enviar("/api/herramientas", { accion: acc, id: b.dataset.id });
    ui.herrRespuesta = r.mensaje || (r.ok ? "" : t("No se pudo.", "It didn't work."));
    herrDibujado = "";
    return dibujar();
  }
  if (b.dataset.aud) {
    const acc = b.dataset.aud;
    if (acc !== "abrir") b.disabled = true;
    const cuerpo = { accion: acc, id: b.dataset.id, carpeta: !!b.dataset.carpeta };
    if (b.dataset.modo) cuerpo.modo = b.dataset.modo;
    if (b.dataset.resumir) cuerpo.resumir = b.dataset.resumir === "true";
    const r = await enviar("/api/audio", cuerpo);
    ui.docRespuesta = r.ok ? "" : r.mensaje || t("No se pudo.", "It didn't work.");
    audioDibujado = "";
    return dibujar();
  }
  if (b.dataset.docModo) { ui.docModo = b.dataset.docModo; ui.docRespuesta = ""; return dibujar(); }
  if (b.dataset.docFormato) { ui.docFormato = b.dataset.docFormato; return dibujar(); }
  if (b.dataset.doc) {
    const acc = b.dataset.doc;
    if (acc !== "abrir") b.disabled = true;
    const r = await enviar("/api/documentos", { accion: acc, id: b.dataset.id, carpeta: !!b.dataset.carpeta, modo: ui.docModo, formato: ui.docFormato });
    ui.docRespuesta = r.ok ? "" : r.mensaje || t("No se pudo.", "It didn't work.");
    docDibujado = "";
    return dibujar();
  }
  if (b.dataset.modP) { ui.modPestana = b.dataset.modP; ui.modRespuesta = ""; return dibujar(); }
  if (b.dataset.mod) {
    const acc = b.dataset.mod;
    const cuerpo = acc === "usar" ? { accion: "usar", modo: "local", modelo: b.dataset.modelo, tipo: b.dataset.tipo }
      : acc === "usar_api" ? { accion: "usar", modo: "api", proveedor: b.dataset.prov }
      : { accion: acc, modelo: b.dataset.modelo, proveedor: b.dataset.prov, usar: true };
    if (acc === "borrar_clave" && !confirm(t("¿Quitar la clave de este equipo?", "Remove the key from this computer?"))) return;
    b.disabled = true;
    ui.modRespuesta = acc === "probar" || acc === "instalar_ollama" ? t("Un momento…", "One moment…") : "";
    if (ui.modRespuesta) { modelosDibujado = ""; dibujar(); }
    const r = await enviar("/api/modelos", cuerpo);
    ui.modRespuesta = r.mensaje || (r.ok ? "" : t("No se pudo.", "It didn't work."));
    modelosDibujado = "";
    return dibujar();
  }
});
document.addEventListener("change", (e) => {
  const sel = e.target.dataset && e.target.dataset.modSel;
  if (!sel) return;
  enviar("/api/modelos", { accion: "usar", modo: "api", modelo: e.target.value || null, tipo: sel });
  e.target.blur();
});
document.addEventListener("submit", async (e) => {
  const prov = e.target.dataset && e.target.dataset.provClave;
  if (prov) {
    e.preventDefault();
    const campo = e.target.elements.clave;
    if (!campo.value.trim()) return;
    ui.modRespuesta = t("Comprobando la clave…", "Checking the key…");
    modelosDibujado = "";
    campo.blur();
    dibujar();
    const r = await enviar("/api/modelos", { accion: "clave", proveedor: prov, clave: campo.value.trim() });
    ui.modRespuesta = r.mensaje || "";
    modelosDibujado = "";
    return dibujar();
  }
  if (e.target.id !== "form-activar") return;
  e.preventDefault();
  const campo = $("#mensaje");
  enviar("/api/ia/activar", { mensaje: campo.value });
  campo.value = "";
  campo.blur();
});

// ------------------------------------------------------------------ burbuja
// La app (app/main.js) dueña de la ventana dice qué forma tiene (abierta, vertical, hacia dónde
// se despliega…); aquí se anima la forma dentro de la ventana y se avisa de lo que hace el
// puntero: pasar por encima abre, clic en la cabecera la deja fija, arrastrar la mueve.
function iniciarBurbuja() {
  const forma = $("#b-forma"), cab = $("#b-cabecera"), contenido = $("#b-contenido");
  const enviar = (accion, datos) => window.akari && window.akari.burbuja(accion, datos);
  let F = null, fijada = false, cierre = null, arrastre = null, recienMovida = false, chipTocado = null;

  document.documentElement.classList.add("transparente");
  document.body.classList.add("vista-burbuja");
  $("#burbuja").hidden = false;
  // las secciones de las piezas del grupo pasan al cuerpo; se ve la de la pieza elegida
  for (const pz of [...grupoDe(burbuja).piezas].reverse()) contenido.prepend($("#" + PIEZAS[pz.id]));
  mostrarPieza(soloPieza || (PIEZAS[pedida] ? pedida : piezasDe(burbuja)[0].id));

  const px = (v) => (typeof v === "number" ? v + "px" : v);
  function poner(estilo) { for (const [k, v] of Object.entries(estilo)) forma.style[k] = px(v); }
  function sinTransicion(fn) {
    forma.classList.add("quieta");
    fn();
    void forma.offsetWidth;             // aplicar ya, antes de volver a animar
    forma.classList.remove("quieta");
  }
  function esquinas(f, abierta) {
    const r = abierta ? 28 : f.altoCerrado / 2;
    const arriba = f.pegadaArriba ? 0 : r, abajo = f.pegadaAbajo ? 0 : r;
    const izq = f.borde === "izquierda", der = f.borde === "derecha";
    return {
      borderTopLeftRadius: izq ? 0 : arriba, borderBottomLeftRadius: izq ? 0 : abajo,
      borderTopRightRadius: der ? 0 : arriba, borderBottomRightRadius: der ? 0 : abajo,
    };
  }
  function anclas(f) {
    const derecha = f.vertical ? f.borde === "derecha" : !f.haciaDerecha;
    const abajo = !f.vertical && f.haciaArriba;
    return { left: derecha ? "auto" : 0, right: derecha ? 0 : "auto", top: abajo ? "auto" : 0, bottom: abajo ? 0 : "auto" };
  }
  function cerradaEn(f) {
    return { ...anclas(f), ...(f.vertical ? { top: f.cerrada.y } : {}), width: f.cerrada.w, height: f.cerrada.h, ...esquinas(f, false) };
  }

  function aplicarForma(f) {
    const anterior = F;
    F = f;
    const b = document.body.classList;
    b.toggle("b-vertical", f.vertical);
    b.toggle("b-izquierda", f.borde === "izquierda");
    b.toggle("b-derecha", f.borde === "derecha");
    b.toggle("b-hacia-arriba", !f.vertical && f.haciaArriba);
    b.toggle("b-hacia-izquierda", !f.vertical && !f.haciaDerecha);
    document.documentElement.style.setProperty("--b-alto", f.altoCerrado + "px");
    document.documentElement.style.setProperty("--b-largo", f.largoV + "px");
    document.documentElement.style.setProperty("--b-ancho", f.anchoAbierto + "px");
    document.documentElement.style.setProperty("--b-tab-y", (f.abierta && f.vertical ? f.cerrada.y : 0) + "px");
    if (f.ventanaCerrada) {
      sinTransicion(() => poner({ left: 0, top: 0, right: "auto", bottom: "auto", width: f.cerrada.w, height: f.cerrada.h, ...esquinas(f, false) }));
    } else {
      if (!anterior || anterior.ventanaCerrada) sinTransicion(() => poner(cerradaEn(f)));
      poner(f.abierta ? { ...anclas(f), width: "100%", height: "100%", ...esquinas(f, true) } : cerradaEn(f));
    }
    forma.classList.toggle("abierta", f.abierta);
    if (visor) visor.pausado = !f.abierta;
  }
  window.akari && window.akari.alCambiarForma(aplicarForma);

  // escribiendo en la burbuja de IA: no se cierra aunque el puntero salga
  const reteniendo = () => document.activeElement && document.activeElement.matches("input") && forma.contains(document.activeElement);
  const programarCierre = () => {
    clearTimeout(cierre);
    cierre = setTimeout(() => { if (!fijada && !reteniendo() && !forma.matches(":hover")) enviar("cerrar"); }, 450);
  };
  forma.addEventListener("mouseenter", () => { clearTimeout(cierre); if (!arrastre) enviar("abrir"); });
  forma.addEventListener("mouseleave", programarCierre);
  document.addEventListener("focusout", () => setTimeout(programarCierre, 0));

  // la altura del contenido decide la de la burbuja abierta
  new ResizeObserver(() => enviar("alto", { alto: contenido.offsetHeight })).observe(contenido);

  // cerrada, el chip bajo el puntero decide en qué pieza se abre
  cab.addEventListener("pointerover", (e) => {
    const chip = e.target.closest(".b-pieza");
    if (chip && !arrastre && !(F && F.abierta) && chip.dataset.pieza !== ui.pagina) mostrarPieza(chip.dataset.pieza);
  });

  // arrastrar desde la cabecera; un clic la fija; doble clic, a su sitio de fábrica
  cab.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    chipTocado = e.target.closest(".b-pieza");       // con la captura, el clic llega a la cabecera
    cab.setPointerCapture(e.pointerId);
    arrastre = { x: e.screenX, y: e.screenY, moviendo: false };
  });
  cab.addEventListener("pointermove", (e) => {
    if (!arrastre) return;
    const dx = e.screenX - arrastre.x, dy = e.screenY - arrastre.y;
    if (!arrastre.moviendo && Math.hypot(dx, dy) < 6) return;
    if (!arrastre.moviendo) {
      arrastre.moviendo = true;
      cab.classList.add("arrastrando");
      enviar("mover-inicio");
    }
    enviar("mover", { dx, dy });
  });
  const soltar = () => {
    if (!arrastre) return;
    if (arrastre.moviendo) {
      enviar("soltar");
      recienMovida = true;
      setTimeout(() => { recienMovida = false; }, 50);
    }
    cab.classList.remove("arrastrando");
    arrastre = null;
  };
  cab.addEventListener("pointerup", soltar);
  cab.addEventListener("pointercancel", soltar);
  cab.addEventListener("click", (e) => {
    if (recienMovida) return;
    // abierta, clic en el chip de otra pieza: cambia a ella (no fija ni suelta)
    const chip = chipTocado || e.target.closest(".b-pieza");
    if (chip && F && F.abierta && chip.dataset.pieza !== ui.pagina) return mostrarPieza(chip.dataset.pieza);
    fijada = !fijada;
    cab.classList.toggle("fijada", fijada);
    if (fijada || forma.matches(":hover")) enviar("abrir"); else enviar("cerrar");
  });
  cab.addEventListener("dblclick", () => enviar("fabrica"));

  dibujarCabecera();
  setInterval(dibujarCabecera, 1000);     // cuenta regresiva y punto que late
}

if (burbuja) {
  iniciarBurbuja();
} else {
  $("#panel").hidden = false;
  const p = params.get("pagina");
  const antes = { ia: "uso", disp: "dispositivos", hab: "habilidades", doc: "documentos" };     // ?pagina= de antes
  mostrarPieza(PIEZAS[p] ? p : antes[p] || (GRUPOS.some((g) => g.id === p) ? piezasDe(p)[0].id : "uso"));
}
cargarGrupos();
traducir();
conectar();
setInterval(dibujar, 15000);      // cuentas regresivas aunque no cambie nada
// el reloj de la grabación de una reunión
setInterval(() => { if (E && E.audio && E.audio.grabacion.desde && ui.pagina === "audio") { audioDibujado = ""; dibujarAudio(); } }, 1000);
