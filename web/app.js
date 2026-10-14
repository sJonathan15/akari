// Panel de akari. Recibe el estado del servicio por SSE (/eventos) y dibuja las tres
// secciones: IA (Claude Code / Codex), dispositivos (con 3D) y habilidades.
// Con ?vista=capsula dibuja solo la pastilla flotante de la app de escritorio.
import { Visor } from "./visor3d.js";

const vista = new URLSearchParams(location.search).get("vista");
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

// ------------------------------------------------------------------ IA
function dibujarIA() {
  const ia = E.ia || {};
  const provs = ["claude", "codex"].filter((p) => ia[p]);
  const prov = provs.includes(ui.proveedor) ? ui.proveedor : ia.principal || provs[0] || "";
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
      + `<div class="botones">${d.acciones.map((a, i) => `<button class="boton ${i === 0 ? "principal" : ""}" data-accion="${a.id}">${icono({ conectar: "bluetooth_connected", desconectar: "bluetooth_disabled", sonar: "ring_volume" }[a.id] || "bolt")}${esc(a.etiqueta)}</button>`).join("")}</div>
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

// ------------------------------------------------------------------ pastilla
function dibujarCapsula() {
  const ia = E.ia || {};
  const p = ia[ia.principal];
  const v5 = p && p.limites.cinco_horas;
  $("#cap-anillo").innerHTML = anillo(v5 ? v5.libre / 100 : 0, colorLibre(v5), 18, 4);
  $("#cap-ia").textContent = v5 ? Math.round(v5.libre) + "%" : "—";
  $("#cap-ia").style.color = colorLibre(v5);
  $("#cap-disp").innerHTML = ((E.dispositivos || {}).dispositivos || []).filter((d) => d.conectado).slice(0, 4)
    .map((d) => `<span style="color:${colorNivel(nivel(d))}">${icono(ICONOS_DISP[d.tipo] || "devices", true)}${d.bateria != null ? d.bateria + "%" : ""}</span>`).join("");
  $("#cap-hab").textContent = E.habilidades ? E.habilidades.total : "—";
}

// ------------------------------------------------------------------ general
function dibujar() {
  if (!E) return;
  $("#servicio").classList.add("vivo");
  if (vista === "capsula") return dibujarCapsula();
  if (ui.pagina === "ia") dibujarIA();
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
  if (b.id === "pastilla" && window.akari) window.akari.alternarPanel();
});
document.addEventListener("submit", (e) => {
  if (e.target.id !== "form-activar") return;
  e.preventDefault();
  const campo = $("#mensaje");
  enviar("/api/ia/activar", { mensaje: campo.value });
  campo.value = "";
  campo.blur();
});

if (vista === "capsula") {
  document.body.classList.add("vista-capsula");
  $("#capsula").hidden = false;
} else {
  $("#panel").hidden = false;
  const p = new URLSearchParams(location.search).get("pagina");
  if (p) document.querySelector(`#pestanas button[data-p="${p}"]`)?.click();
}
traducir();
conectar();
setInterval(dibujar, 15000);      // cuentas regresivas aunque no cambie nada
