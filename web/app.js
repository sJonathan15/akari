// Panel de akari. Recibe el estado del servicio por SSE (/eventos) y dibuja las tres
// secciones: IA (Claude Code / Codex), dispositivos (con 3D) y habilidades.
// Con ?vista=burbuja&c=ia|dispositivos|habilidades dibuja una de las burbujas flotantes de la
// app de escritorio: la misma sección del panel, con su cabecera y su animación de apertura.
import { Visor } from "./visor3d.js";

const vista = new URLSearchParams(location.search).get("vista");
const SECCIONES = { ia: ["ia", "p-ia"], dispositivos: ["disp", "p-disp"], habilidades: ["hab", "p-hab"] };
const pedida = new URLSearchParams(location.search).get("c");
const burbuja = vista === "burbuja" ? (SECCIONES[pedida] ? pedida : "ia") : null;
let E = null;                         // último estado
let idioma = navigator.language.startsWith("es") ? "es" : "en";
const ui = { pagina: "ia", proveedor: "", dispositivo: "", hab: "recomendadas", verMas: false, respuesta: "" };
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

function htmlCabecera() {
  if (!E) return `<span class="tenue chico b-centro">${t("Iniciando akari…", "Starting akari…")}</span>`;
  if (burbuja === "ia") {
    const ia = E.ia || {};
    const { prov } = proveedorActual();
    const p = ia[prov];
    const v5 = p && p.limites.cinco_horas;
    const fam = p ? familia(prov, p.modelo_actual) : "";
    const ultima = p && p.cinta && p.cinta[0];
    const trabajando = !!ultima && ahora() - ultima.t < 25;
    const color = colorLibre(v5);
    const colorF = FAMILIAS_CHIP[fam] ? VAR(FAMILIAS_CHIP[fam]) : VAR("--texto-var");
    return `${anillo(v5 ? v5.libre / 100 : 0, color, 22, 4)}
      <span class="b-num" style="color:${color}">${v5 ? Math.round(v5.libre) + "%" : "—"}</span>
      <span class="tenue chico">${!prov ? t("sin Claude ni Codex", "no Claude or Codex") : v5 ? t("libre", "left") : t("sin lectura", "no data")}</span>
      <span class="b-relleno"></span>
      ${fam ? `<span class="b-chip" style="color:${colorF};background:color-mix(in srgb, ${colorF} 16%, transparent)">${icono(ICONO_FAM[fam] || "smart_toy", true)}${esc(fam)}</span>` : ""}
      ${v5 && v5.reinicia ? `<span class="mono chico tenue">${cuenta(v5.reinicia - ahora())}</span>` : ""}
      <i class="b-punto${trabajando ? " late" : ""}"></i>`;
  } else if (burbuja === "dispositivos") {
    const lista = (E.dispositivos || {}).dispositivos || [];
    const alerta = lista.some((d) => nivel(d) === "bajo" && !d.cargando);
    $("#b-cabecera").classList.toggle("alerta", alerta);
    return lista.slice(0, 4).map((d) => {
      const nv = nivel(d);
      return `<span class="b-disp${nv === "bajo" && !d.cargando ? " late" : ""}">${icono(ICONOS_DISP[d.tipo] || "devices", d.conectado).replace('class="icono', `style="color:${colorNivel(nv)}" class="icono`)}
        <span class="mono chico" style="color:${nv === "nada" ? VAR("--contorno") : VAR("--texto-var")}">${textoCorto(d)}${d.cargando ? "⚡" : ""}</span></span>`;
    }).join("") || `<span class="tenue chico b-centro">${t("Sin periféricos todavía", "No devices yet")}</span>`;
  } else {
    const H = E.habilidades;
    const instalando = !!H && [...H.recomendadas, ...H.mas].some((r) => r.tarea && r.tarea.estado === "instalando");
    return `${icono("auto_awesome", true).replace('class="icono', `class="icono b-estrella${instalando ? " girando" : ""}`)}
      <span class="b-num">${H ? H.total : "—"}</span><span class="tenue chico">${t("habilidades", "skills")}</span>`;
  }
}

// ------------------------------------------------------------------ general
function dibujar() {
  if (!E) return;
  aplicarTema(E.tema);
  $("#servicio").classList.add("vivo");
  if (burbuja) dibujarCabecera();
  if (ui.pagina === "ia") { dibujarIA(); dibujarModelos(); }
  if (ui.pagina === "disp") dibujarDisp();
  if (ui.pagina === "hab") dibujarHab();
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
    if (E.idioma && E.idioma !== idioma) { idioma = E.idioma; traducir(); }
    dibujar();
  };
  fuente.onerror = () => { $("#servicio").classList.remove("vivo"); };
}

// eventos (delegados: el contenido se redibuja)
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.closest("#pestanas")) {
    ui.pagina = b.dataset.p;
    document.querySelectorAll("#pestanas button").forEach((x) => x.classList.toggle("activa", x === b));
    document.querySelectorAll(".pagina").forEach((x) => x.classList.toggle("activa", x.id === "p-" + ui.pagina));
    return dibujar();
  }
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
  let F = null, fijada = false, cierre = null, arrastre = null, recienMovida = false;

  document.documentElement.classList.add("transparente");
  document.body.classList.add("vista-burbuja");
  $("#burbuja").hidden = false;
  const [pagina, seccion] = SECCIONES[burbuja];
  ui.pagina = pagina;
  $("#" + seccion).classList.add("activa");
  contenido.prepend($("#" + seccion));

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

  // arrastrar desde la cabecera; un clic la fija; doble clic, a su sitio de fábrica
  cab.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
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
  cab.addEventListener("click", () => {
    if (recienMovida) return;
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
  const p = new URLSearchParams(location.search).get("pagina");
  if (p) document.querySelector(`#pestanas button[data-p="${p}"]`)?.click();
}
traducir();
conectar();
setInterval(dibujar, 15000);      // cuentas regresivas aunque no cambie nada
