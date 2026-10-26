"""Uso de Claude Code y de Codex en tiempo real.

Claude Code
  * ~/.claude/projects/**/*.jsonl: tokens exactos de cada respuesta;
  * copias que deja `akari statusline` (la línea de estado de Claude Code) con el % usado
    de los límites de 5 horas y semanal, el contexto y el costo.
Codex
  * $CODEX_HOME/sessions/**/rollout-*.jsonl: eventos `token_count` con los tokens de cada
    turno y los límites (`rate_limits.primary` = 5 h, `secondary` = semanal).

Todo se lee de forma incremental (solo los bytes nuevos de cada archivo) y se calcula aquí;
los frontends (cápsulas, panel, extensión de GNOME) solo dibujan el resultado.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .comun import CACHE, CONFIG, HOME, IDIOMA, SIN_VENTANA, escribir_json, leer_json, notificar, t

CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", HOME / ".claude"))
CLAUDE_JSON = HOME / ".claude.json"
CODEX_DIR = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
SESIONES = CACHE / "sesiones"                 # copias de la línea de estado de Claude Code
ALERTAS = CACHE / "alertas-ia.json"

DIAS_HISTORIAL = 8
CINCO_HORAS = 5 * 3600
SEMANA = 7 * 86400
UMBRALES_5H = (80, 95)
UMBRALES_7D = (75, 90)
DIAS = {"es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
        "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}[IDIOMA]


# ---------------------------------------------------------------- nombres

def nombre_claude(modelo):
    """'claude-opus-5-5' -> 'Opus 5.5'; 'claude-sonnet-4-5-20250929' -> 'Sonnet 4.5'."""
    if not modelo or modelo.startswith("<"):
        return t("Otro", "Other")
    partes = [p for p in modelo.replace("claude-", "").split("-") if not (p.isdigit() and len(p) == 8)]
    familia = [p for p in partes if not p.isdigit()]
    version = [p for p in partes if p.isdigit()]
    return " ".join([" ".join(f.capitalize() for f in familia), ".".join(version)]).strip()


def nombre_codex(modelo):
    """'gpt-5.1-codex-max' -> 'GPT-5.1 Codex Max'; 'o4-mini' -> 'O4 Mini'."""
    if not modelo:
        return "Codex"
    partes = modelo.split("-")
    if partes[0].lower() == "gpt" and len(partes) > 1:
        partes = [f"GPT-{partes[1]}"] + partes[2:]
    return " ".join(p if p.startswith("GPT") else p.capitalize() for p in partes)


def duracion(segundos):
    segundos = max(0, int(segundos))
    h, m = divmod(segundos // 60, 60)
    if h >= 24:
        return t(f"{h // 24} d {h % 24} h", f"{h // 24}d {h % 24}h")
    return f"{h} h {m:02d} min" if h else f"{m} min"


def marca_tiempo(texto):
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


# ---------------------------------------------------------------- lectura incremental

class Lector:
    """Lee los .jsonl de una carpeta procesando solo lo nuevo de cada archivo."""
    patron = "*.jsonl"

    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.posiciones = {}
        self.mensajes = {}

    def actualizar(self):
        if not self.carpeta.exists():
            return False
        limite = time.time() - DIAS_HISTORIAL * 86400
        cambio = False
        for ruta in self.carpeta.rglob(self.patron):
            try:
                info = ruta.stat()
            except OSError:
                continue
            clave = str(ruta)
            leido = self.posiciones.get(clave)
            if leido is None and info.st_mtime < limite:
                self.posiciones[clave] = info.st_size
                continue
            leido = leido or 0
            if info.st_size < leido:
                leido = 0
            if info.st_size == leido:
                continue
            with open(ruta, "rb") as f:
                f.seek(leido)
                bloque = f.read(info.st_size - leido)
            fin = bloque.rfind(b"\n")
            if fin < 0:
                continue
            self.posiciones[clave] = leido + fin + 1
            if self.procesar(clave, bloque[: fin + 1].splitlines()):
                cambio = True
        if cambio:
            corte = time.time() - DIAS_HISTORIAL * 86400
            self.mensajes = {k: v for k, v in self.mensajes.items() if v["t"] >= corte}
        return cambio

    def procesar(self, archivo, lineas):
        raise NotImplementedError


class LectorClaude(Lector):
    def procesar(self, archivo, lineas):
        agente = "subagents" in Path(archivo).parts
        cambio = False
        for linea in lineas:
            if b'"usage"' not in linea or b'"assistant"' not in linea:
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            uso = m.get("usage")
            ts = marca_tiempo(d.get("timestamp"))
            if not uso or ts is None or (m.get("model") or "").startswith("<"):
                continue
            clave = m.get("id") or d.get("requestId") or d.get("uuid")
            self.mensajes[clave] = {
                "t": ts,
                "modelo": nombre_claude(m.get("model")),
                "sesion": d.get("sessionId"),
                "proyecto": Path(d.get("cwd") or "~").name or "~",
                "agente": agente,
                "entrada": uso.get("input_tokens") or 0,
                "cache_escrita": uso.get("cache_creation_input_tokens") or 0,
                "cache_leida": uso.get("cache_read_input_tokens") or 0,
                "salida": uso.get("output_tokens") or 0,
                "razonamiento": (uso.get("output_tokens_details") or {}).get("thinking_tokens") or 0,
            }
            cambio = True
        return cambio


class LectorCodex(Lector):
    patron = "rollout-*.jsonl"

    def __init__(self, carpeta):
        super().__init__(carpeta)
        self.contexto = {}       # archivo -> {modelo, proyecto, sesion, total}
        self.limites = None      # el último rate_limits visto
        self.t_limites = 0

    def procesar(self, archivo, lineas):
        ctx = self.contexto.setdefault(archivo, {"modelo": None, "proyecto": "~", "sesion": archivo, "total": 0})
        cambio = False
        for n, linea in enumerate(lineas):
            if b'"session_meta"' not in linea and b'"turn_context"' not in linea and b'"token_count"' not in linea:
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            p = d.get("payload") or {}
            tipo = d.get("type")
            if tipo == "session_meta":
                ctx["sesion"] = p.get("id") or archivo
                ctx["proyecto"] = Path(p.get("cwd") or "~").name or "~"
                ctx["modelo"] = p.get("model") or ctx["modelo"]
            elif tipo == "turn_context":
                ctx["modelo"] = p.get("model") or ctx["modelo"]
                if p.get("cwd"):
                    ctx["proyecto"] = Path(p["cwd"]).name or "~"
            elif tipo == "event_msg" and p.get("type") == "token_count":
                ts = marca_tiempo(d.get("timestamp")) or time.time()
                if p.get("rate_limits") and ts >= self.t_limites:
                    self.limites, self.t_limites = p["rate_limits"], ts
                    cambio = True
                info = p.get("info") or {}
                total = (info.get("total_token_usage") or {}).get("total_tokens") or 0
                ultimo = info.get("last_token_usage") or {}
                # Codex repite token_count cuando solo cambian los límites: contar si el total creció
                if not ultimo or total <= ctx["total"]:
                    continue
                ctx["total"] = total
                cacheados = ultimo.get("cached_input_tokens") or 0
                self.mensajes[f"{archivo}:{total}"] = {
                    "t": ts,
                    "modelo": nombre_codex(ctx["modelo"]),
                    "sesion": ctx["sesion"],
                    "proyecto": ctx["proyecto"],
                    "agente": False,
                    # en OpenAI input_tokens incluye los cacheados
                    "entrada": max(0, (ultimo.get("input_tokens") or 0) - cacheados),
                    "cache_escrita": ultimo.get("cache_write_input_tokens") or 0,
                    "cache_leida": cacheados,
                    "salida": ultimo.get("output_tokens") or 0,
                    "razonamiento": ultimo.get("reasoning_output_tokens") or 0,
                }
                cambio = True
        return cambio

    def ventanas(self):
        """rate_limits de Codex al formato de la línea de estado de Claude."""
        r = self.limites or {}
        salida = {}
        for clave, origen in (("five_hour", "primary"), ("seven_day", "secondary")):
            v = r.get(origen)
            if not v or v.get("used_percent") is None:
                continue
            reinicia = v.get("resets_at")
            if not reinicia and v.get("resets_in_seconds") is not None:      # versiones antiguas
                reinicia = self.t_limites + v["resets_in_seconds"]
            minutos = v.get("window_minutes")
            # si Codex cambia la duración de las ventanas, se ubican por su largo
            if minutos and minutos > 24 * 60:
                clave = "seven_day"
            elif minutos:
                clave = "five_hour"
            salida[clave] = {"used_percentage": v["used_percent"], "resets_at": reinicia,
                             "minutos": minutos}
        return salida

    def plan(self):
        return (self.limites or {}).get("plan_type")


def sumar(registros):
    total = {"entrada": 0, "cache_escrita": 0, "cache_leida": 0, "salida": 0, "razonamiento": 0, "mensajes": 0}
    for r in registros:
        for k in ("entrada", "cache_escrita", "cache_leida", "salida", "razonamiento"):
            total[k] += r[k]
        total["mensajes"] += 1
    total["total"] = total["entrada"] + total["cache_escrita"] + total["cache_leida"] + total["salida"]
    total["nuevos"] = total["entrada"] + total["cache_escrita"] + total["salida"]
    return total


# ------------------------------------------------- copias de la línea de estado

def guardar_lectura(datos):
    SESIONES.mkdir(parents=True, exist_ok=True)
    sesion = re.sub(r"[^\w.-]", "_", str(datos.get("session_id") or "sin-sesion"))
    datos["_recibido"] = time.time()
    tmp = SESIONES / f".{sesion}.tmp"
    tmp.write_text(json.dumps(datos), encoding="utf-8")
    os.replace(tmp, SESIONES / f"{sesion}.json")


def leer_sesiones():
    sesiones = []
    if not SESIONES.exists():
        return sesiones
    corte = time.time() - SEMANA
    for ruta in SESIONES.glob("*.json"):
        try:
            if ruta.stat().st_mtime < corte:
                ruta.unlink(missing_ok=True)
                continue
            sesiones.append(json.loads(ruta.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    sesiones.sort(key=lambda s: s.get("_recibido", 0), reverse=True)
    return sesiones


def ventana(datos, largo, ahora):
    if not datos or datos.get("used_percentage") is None:
        return None
    usado = float(datos["used_percentage"])
    reinicia = float(datos.get("resets_at") or 0)
    if datos.get("minutos"):
        largo = datos["minutos"] * 60
    if reinicia and reinicia <= ahora:
        return None   # ya se renovó; esperamos la siguiente lectura
    inicio = reinicia - largo
    transcurrido = min(100.0, max(0.0, (ahora - inicio) / largo * 100)) if reinicia else None
    agotado = None
    # proyectar solo con datos suficientes: al inicio de una ventana larga el ritmo engaña
    suficiente = usado >= 25 or (ahora - inicio) >= largo * 0.15
    if reinicia and usado > 0 and ahora > inicio and suficiente:
        cuando = inicio + 100 / (usado / (ahora - inicio))
        if cuando < reinicia:
            agotado = cuando
    return {
        "usado": round(usado, 1),
        "libre": round(max(0.0, 100 - usado), 1),
        "reinicia": reinicia or None,
        "inicio": inicio if reinicia else None,
        "transcurrido": round(transcurrido, 1) if transcurrido is not None else None,
        "agotado_en": agotado,
    }


# ---------------------------------------------------------------- cuentas

def cuenta_claude():
    """Nombre y plan de la cuenta con la que se inició sesión en Claude Code (nunca el correo)."""
    o = leer_json(CLAUDE_JSON).get("oauthAccount") or {}
    if not o:
        return None
    tipo = (o.get("organizationType") or "").replace("claude_", "")
    planes = {"pro": "Pro", "max": "Max", "team": "Team", "enterprise": "Enterprise", "free": "Free"}
    return {"nombre": o.get("displayName") or (o.get("fullName") or "").split(" ")[0] or None,
            "plan": planes.get(tipo, tipo.capitalize() or None)}


def cuenta_codex(plan):
    """Nombre (de id_token, sin guardar ni mostrar tokens) y plan de ChatGPT de Codex."""
    nombre = None
    try:
        token = (leer_json(CODEX_DIR / "auth.json").get("tokens") or {}).get("id_token") or ""
        carga = token.split(".")[1]
        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
        nombre = (datos.get("name") or "").split(" ")[0] or None
        plan = plan or (datos.get("https://api.openai.com/auth") or {}).get("chatgpt_plan_type")
    except (IndexError, ValueError, AttributeError):
        pass
    if not nombre and not plan:
        return None
    return {"nombre": nombre, "plan": (plan or "").capitalize() or None}


# ---------------------------------------------------------------- alertas

class Alertas:
    def __init__(self):
        self.estado = leer_json(ALERTAS)
        self.historial = self.estado.setdefault("historial", [])

    def _guardar(self):
        self.historial[:] = self.historial[-30:]
        escribir_json(ALERTAS, self.estado)

    def _avisar(self, titulo, cuerpo, urgente=False):
        notificar(titulo, cuerpo, urgente)
        self.historial.append({"t": time.time(), "titulo": titulo, "cuerpo": cuerpo})

    def revisar(self, clave, nombre, datos, umbrales, ahora):
        cambio = False
        previo = self.estado.get(clave)
        # renovación: la ventana anterior terminó y la habías usado bastante
        if previo and previo.get("reinicia") and previo["reinicia"] <= ahora and not previo.get("renovado"):
            if previo.get("max", 0) >= 50:
                self._avisar(t(f"{nombre}: límite renovado", f"{nombre}: limit renewed"),
                             t("Ya tienes de nuevo el 100 % disponible.", "You have 100% available again."))
            previo["renovado"] = True
            cambio = True
        if datos and datos.get("reinicia"):
            if not previo or previo.get("reinicia") != datos["reinicia"]:
                previo = {"reinicia": datos["reinicia"], "avisados": [], "max": 0}
                self.estado[clave] = previo
                cambio = True
            previo["max"] = max(previo["max"], datos["usado"])
            for umbral in umbrales:
                if datos["usado"] >= umbral and umbral not in previo["avisados"]:
                    previo["avisados"].append(umbral)
                    resta = duracion(datos["reinicia"] - ahora)
                    self._avisar(
                        t(f"{nombre}: llevas el {round(datos['usado'])} %", f"{nombre}: {round(datos['usado'])}% used"),
                        t(f"Te queda el {round(datos['libre'])} %. Se renueva en {resta}.",
                          f"{round(datos['libre'])}% left. Renews in {resta}."),
                        urgente=umbral == umbrales[-1])
                    cambio = True
        if cambio:
            self._guardar()


# ------------------------------------------------------------- activar la ventana
# La ventana de 5 horas de Claude empieza con el primer mensaje. El activador manda uno
# corto con `claude -p` (modelo barato, sin herramientas ni hooks) a pedido o a una hora
# fija; la respuesta trae los límites reales y se guardan como una lectura más.

AJUSTES_ACTIVAR = CONFIG / "activar.json"
CARPETA_PING = CACHE / "ping"
GRACIA = 3 * 3600        # si el equipo estaba suspendido a la hora, aún se activa hasta 3 h después
FABRICA = {"programado": False, "hora": "06:00", "mantener": False, "hasta": "23:00", "modelo": "haiku"}


def minutos(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class Activador:
    def __init__(self, monitor):
        self.monitor = monitor
        self.ocupado = False
        self.ultimo = None
        guardado = leer_json(AJUSTES_ACTIVAR)
        self.ajustes = dict(FABRICA)
        self.ajustes.update({k: guardado[k] for k in FABRICA if k in guardado})
        self.hecho = guardado.get("hecho", "")

    def guardar(self):
        escribir_json(AJUSTES_ACTIVAR, {**self.ajustes, "hecho": self.hecho})

    def cambiar(self, datos):
        for k in ("programado", "mantener"):
            if k in datos:
                self.ajustes[k] = bool(datos[k])
        for k in ("hora", "hasta"):
            if k in datos:
                try:
                    v = minutos(str(datos[k])) % 1440
                    self.ajustes[k] = f"{v // 60:02d}:{v % 60:02d}"
                except ValueError:
                    pass
        self.guardar()
        self.monitor.recalcular()

    def resumen(self):
        return {**self.ajustes, "ocupado": self.ocupado, "ultimo": self.ultimo, "proximo": self.proximo()}

    def proximo(self):
        if not self.ajustes["programado"]:
            return None
        local = datetime.now().astimezone()
        m = minutos(self.ajustes["hora"])
        cuando = local.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)
        if cuando <= local or self.hecho == cuando.strftime("%Y-%m-%d"):
            cuando += timedelta(days=1)
        return cuando.timestamp()

    def activar(self, mensaje="", automatico=False):
        if self.ocupado:
            return False
        self.ocupado = True
        self.monitor.recalcular()
        threading.Thread(target=self._enviar, args=(mensaje.strip(), automatico), daemon=True).start()
        return True

    def _enviar(self, mensaje, automatico):
        propio = bool(mensaje)
        # el mensaje va por la entrada estándar: en Windows `claude` puede ser un .cmd y cmd.exe
        # interpretaría & | < > dentro de un argumento
        orden = [shutil.which("claude") or "claude", "-p", "--model", self.ajustes["modelo"],
                 # sin hooks ni MCP del usuario y sin herramientas: desde la cápsula solo se conversa
                 "--setting-sources", "project", "--strict-mcp-config", "--tools", "",
                 "--no-session-persistence", "--output-format", "stream-json", "--verbose"]
        if propio:
            orden += ["--append-system-prompt",
                      t("Te escriben desde un widget pequeño del escritorio: responde en español, en 3 frases como máximo, sin markdown.",
                        "You are answering from a small desktop widget: reply in at most 3 sentences, no markdown.")]
        texto, limites, error = [], {}, ""
        try:
            CARPETA_PING.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(orden, cwd=CARPETA_PING, input=mensaje or "Reply with just the word: ready",
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=180, **SIN_VENTANA)
            for linea in proc.stdout.splitlines():
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                if d.get("type") == "assistant":
                    texto += [b.get("text", "") for b in d["message"].get("content", []) if b.get("type") == "text"]
                elif d.get("type") == "rate_limit_event":
                    ventanas = (d.get("rate_limit_info") or {}).get("unifiedWindows") or {}
                    for clave in ("five_hour", "seven_day"):
                        v = ventanas.get(clave)
                        if v and v.get("utilization") is not None:
                            limites[clave] = {"used_percentage": float(v["utilization"]) * 100,
                                              "resets_at": v.get("resetsAt")}
                elif d.get("type") == "result" and d.get("is_error"):
                    error = str(d.get("result") or "error")
            if proc.returncode and not error:
                error = (proc.stderr.strip().splitlines() or [t("claude terminó con error", "claude exited with an error")])[-1]
        except FileNotFoundError:
            error = t("No encontré el comando claude.", "The claude command was not found.")
        except subprocess.TimeoutExpired:
            error = t("Claude no respondió en 3 minutos.", "Claude did not answer within 3 minutes.")
        if limites:
            guardar_lectura({"session_id": "akari-activador", "rate_limits": limites,
                             "model": {"display_name": nombre_claude(self.ajustes["modelo"])}})
        ok = not error and bool(texto or limites)
        self.ultimo = {"t": time.time(), "ok": ok, "automatico": automatico,
                       "mensaje": mensaje if propio else "",
                       "respuesta": "".join(texto).strip() if propio else "", "error": error}
        self.ocupado = False
        if automatico:
            if ok:
                notificar(t("Ventana de 5 horas activada", "5-hour window started"),
                          t("Se abrió sola a la hora programada.", "It opened at the scheduled time."))
            else:
                notificar(t("No pude activar la ventana de 5 horas", "Could not start the 5-hour window"),
                          error or t("Sin respuesta de Claude.", "No answer from Claude."))
        self.monitor.recalcular()

    def revisar(self, cinco):
        """¿Toca activar por la hora programada o para mantener la ventana abierta?"""
        if self.ocupado:
            return
        ahora = time.time()
        local = datetime.now().astimezone()
        hoy = local.strftime("%Y-%m-%d")
        m_ahora = local.hour * 60 + local.minute
        desde, hasta = minutos(self.ajustes["hora"]), minutos(self.ajustes["hasta"])
        if self.ajustes["programado"] and self.hecho != hoy and 0 <= (m_ahora - desde) * 60 < GRACIA:
            self.hecho = hoy
            self.guardar()
            if not cinco:       # con una ventana abierta no hace falta gastar nada
                self.activar(automatico=True)
            return
        dentro = desde <= m_ahora < hasta if desde < hasta else (m_ahora >= desde or m_ahora < hasta)
        reciente = self.ultimo and ahora - self.ultimo["t"] < 600     # no insistir si falla
        if self.ajustes["mantener"] and dentro and not cinco and not reciente:
            self.activar(automatico=True)


# ---------------------------------------------------------------- resumen

def resumir(msgs, cinco, siete, ahora, sesiones_estado=None):
    """Tokens por minuto/día/modelo/sesión a partir de los registros de un proveedor."""
    msgs = sorted(msgs, key=lambda r: r["t"])
    local = datetime.now().astimezone()
    inicio_hoy = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    inicio_5h = cinco["inicio"] if cinco and cinco["inicio"] else ahora - CINCO_HORAS
    inicio_7d = siete["inicio"] if siete and siete["inicio"] else ahora - SEMANA

    por_minuto = [0] * 60
    for r in msgs:
        m = int((ahora - r["t"]) // 60)
        if 0 <= m < 60:
            por_minuto[59 - m] += r["entrada"] + r["cache_escrita"] + r["salida"]
    por_dia = []
    for i in range(6, -1, -1):
        dia = (local - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        a, b = dia.timestamp(), (dia + timedelta(days=1)).timestamp()
        s = sumar(r for r in msgs if a <= r["t"] < b)
        por_dia.append({"dia": f"{DIAS[dia.weekday()]} {dia.day}", "num": dia.day, "nuevos": s["nuevos"], "total": s["total"]})

    def por_modelo(desde):
        grupos = defaultdict(list)
        for r in msgs:
            if r["t"] >= desde:
                grupos[r["modelo"]].append(r)
        return sorted(({"modelo": k, **sumar(v)} for k, v in grupos.items()), key=lambda m: m["nuevos"], reverse=True)

    info = {s.get("session_id"): s for s in (sesiones_estado or [])}
    actividad = defaultdict(list)
    for r in msgs:
        if r["t"] >= inicio_hoy:
            actividad[r["sesion"]].append(r)
    sesiones = []
    for sid, regs in actividad.items():
        s = info.get(sid, {})
        ultima = max(r["t"] for r in regs)
        sesiones.append({
            "id": sid,
            "proyecto": Path((s.get("workspace") or {}).get("current_dir") or "").name or regs[-1]["proyecto"],
            "modelo": (s.get("model") or {}).get("display_name") or regs[-1]["modelo"],
            "contexto": (s.get("context_window") or {}).get("used_percentage"),
            "costo": (s.get("cost") or {}).get("total_cost_usd"),
            "ultima": ultima,
            "activa": ahora - ultima < 300,
            **sumar(regs),
        })
    sesiones.sort(key=lambda s: s["ultima"], reverse=True)
    modelo_actual = sesiones[0]["modelo"] if sesiones else (msgs[-1]["modelo"] if msgs else None)
    recientes = [r for r in msgs if r["t"] >= ahora - 300]
    return {
        "limites": {"cinco_horas": cinco, "siete_dias": siete, "disponible": bool(cinco or siete)},
        "tokens": {
            "ventana": sumar(r for r in msgs if r["t"] >= inicio_5h),
            "hoy": sumar(r for r in msgs if r["t"] >= inicio_hoy),
            "semana": sumar(r for r in msgs if r["t"] >= inicio_7d),
        },
        "ritmo_por_min": round(sum(r["entrada"] + r["cache_escrita"] + r["salida"] for r in recientes) / 5),
        "por_minuto": por_minuto,
        "por_dia": por_dia,
        "modelos": por_modelo(inicio_7d),
        "modelos_hoy": por_modelo(inicio_hoy),
        "modelo_actual": modelo_actual,
        "sesiones": [{k: v for k, v in s.items() if k != "id"} for s in sesiones[:8]],
        "cinta": [{k: v for k, v in r.items() if k != "sesion"} for r in msgs[-40:]][::-1],
        "ultima_actividad": msgs[-1]["t"] if msgs else None,
    }


class MonitorIA:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        self.claude = LectorClaude(CLAUDE_DIR / "projects")
        self.codex = LectorCodex(CODEX_DIR / "sessions")
        self.alertas = Alertas()
        self.activador = Activador(self)
        self.estado = {}
        self._ultimo = 0

    def recalcular(self):
        self._ultimo = 0

    def paso(self):
        """Lo llama el bucle del servicio cada segundo."""
        cambio = self.claude.actualizar()
        cambio = self.codex.actualizar() or cambio
        if cambio or time.time() - self._ultimo > 5:
            self.calcular()

    def calcular(self):
        ahora = time.time()
        self._ultimo = ahora
        estado = {"claude": None, "codex": None}

        hay_claude = CLAUDE_DIR.exists() or CLAUDE_JSON.exists()
        if hay_claude:
            sesiones = leer_sesiones()
            limites = next((s["rate_limits"] for s in sesiones if s.get("rate_limits")), {})
            cinco = ventana(limites.get("five_hour"), CINCO_HORAS, ahora)
            siete = ventana(limites.get("seven_day"), SEMANA, ahora)
            self.alertas.revisar("claude-5h", "Claude · 5 h", cinco, UMBRALES_5H, ahora)
            self.alertas.revisar("claude-7d", t("Claude · semanal", "Claude · weekly"), siete, UMBRALES_7D, ahora)
            self.activador.revisar(cinco)
            estado["claude"] = {
                **resumir(self.claude.mensajes.values(), cinco, siete, ahora, sesiones),
                "cuenta": cuenta_claude(),
                "linea_estado": any(s.get("session_id") != "akari-activador" for s in sesiones),
                "activador": self.activador.resumen(),
            }

        if CODEX_DIR.exists():
            lim = self.codex.ventanas()
            cinco = ventana(lim.get("five_hour"), CINCO_HORAS, ahora)
            siete = ventana(lim.get("seven_day"), SEMANA, ahora)
            self.alertas.revisar("codex-5h", "Codex · 5 h", cinco, UMBRALES_5H, ahora)
            self.alertas.revisar("codex-7d", t("Codex · semanal", "Codex · weekly"), siete, UMBRALES_7D, ahora)
            estado["codex"] = {**resumir(self.codex.mensajes.values(), cinco, siete, ahora),
                               "cuenta": cuenta_codex(self.codex.plan())}

        # el que se usó por última vez es el que muestran primero las cápsulas
        candidatos = [(v.get("ultima_actividad") or 0, k) for k, v in estado.items() if v]
        estado["principal"] = max(candidatos)[1] if candidatos else None
        estado["avisos"] = self.alertas.historial[-8:][::-1]
        if estado != self.estado:
            self.estado = estado
            self.al_cambiar()
