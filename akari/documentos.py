"""Conversor de documentos, en las dos direcciones (Linux y Windows):

  PDF / Word / Excel / CSV → Markdown   markitdown de Microsoft; los Excel con recursos/excel_md.py (una
                                        tabla por hoja, sin «NaN» ni «3.0»). .doc/.odt/.rtf y .ods pasan
                                        antes por LibreOffice si está.
  Markdown / lo copiado → Word / PDF    pandoc (+ recursos/anchos.lua, que reparte el ancho de las tablas);
                                        el PDF sale del .docx con LibreOffice.

markitdown y pandoc (pypandoc_binary) se instalan en un entorno propio con un botón (extras.py).
El resultado queda junto al original; si esa carpeta no se puede escribir, o el archivo llegó
subido desde el panel o del portapapeles, va a Documentos/akari. Convierte de a uno.
"""
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import extras
from .comun import CACHE, CONFIG, HOME, RAIZ, SIN_VENTANA, WINDOWS, abrir, correr, escribir_json, leer_json, \
    notificar, powershell, t, tiene

HISTORIAL = CONFIG / "documentos.json"
SUBIDOS = CACHE / "documentos"                  # lo subido desde el panel o copiado espera aquí su turno
PERFIL_LO = CACHE / "libreoffice"               # perfil propio: no choca con un LibreOffice abierto
RECURSOS = RAIZ / "akari" / "recursos"
PAQUETES = ["markitdown[pdf,docx,xlsx,xls]", "pypandoc_binary"]
MAX_HISTORIAL = 30
TIEMPO_MAX = 600

EXCEL = {".xlsx", ".xlsm", ".xls", ".ods"}
A_MD = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".csv", ".pptx", ".html", ".htm"} | EXCEL
DESDE_MD = {".md", ".markdown", ".txt"}
FORMATOS = {"pdf", "docx"}
LECTOR_MD = "markdown+hard_line_breaks"         # como Obsidian: cada salto de línea cuenta


def carpeta_documentos():
    """Documentos del usuario (con su nombre traducido en Linux) + /akari."""
    base = None
    if not WINDOWS and tiene("xdg-user-dir"):
        ok, salida = correr(["xdg-user-dir", "DOCUMENTS"], 5)
        if ok and salida and Path(salida) != HOME:
            base = Path(salida)
    if base is None:
        base = next((HOME / n for n in ("Documents", "Documentos") if (HOME / n).is_dir()), HOME / "Documents")
    return base / "akari"


def a_ruta(texto):
    texto = str(texto).strip()
    if texto.startswith("file://"):
        ruta = unquote(urlparse(texto).path)
        if WINDOWS and re.match(r"^/[A-Za-z]:", ruta):      # file:///C:/… → C:/…
            ruta = ruta[1:]
        texto = ruta
    return Path(texto).expanduser()


def destino_para(nombre, extension, carpeta):
    carpeta = carpeta if carpeta and os.access(carpeta, os.W_OK) else carpeta_documentos()
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = carpeta / (nombre + extension)
    n = 2
    while salida.exists():          # no pisar uno que ya existe
        salida = carpeta / f"{nombre} ({n}){extension}"
        n += 1
    return salida


def nombre_de_texto(texto):
    """Nombre de archivo a partir de la primera línea de lo copiado."""
    for linea in texto.splitlines():
        linea = re.sub(r"<[^>]+>", "", linea)
        linea = re.sub(r"[#*_`>\[\]|/\\:\"<>?]+", " ", linea)
        linea = " ".join(linea.split())[:50].strip(" .-")
        if len(linea) >= 3:
            return linea
    return t("Texto copiado ", "Copied text ") + time.strftime("%Y-%m-%d %H.%M")


def nombre_seguro(nombre):
    nombre = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", Path(nombre).name).strip(" .") or "archivo"
    return nombre[:120]


def sin_enlaces_obsidian(texto):
    texto = re.sub(r"!?\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", texto)    # [[nota|alias]] → alias
    return re.sub(r"!?\[\[([^\]]+)\]\]", r"\1", texto)                 # [[nota]] → nota


def soffice():
    encontrado = shutil.which("soffice") or shutil.which("libreoffice")
    if not encontrado and WINDOWS:
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("PROGRAMFILES(X86)", "")):
            exe = Path(base) / "LibreOffice" / "program" / "soffice.exe"
            if base and exe.exists():
                return str(exe)
    return encontrado


def _correr(orden, **kw):
    r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=TIEMPO_MAX, **SIN_VENTANA, **kw)
    if r.returncode != 0:
        raise RuntimeError(((r.stderr or r.stdout).strip().splitlines() or [t("falló la conversión", "conversion failed")])[-1][:200])
    return r


def libreoffice(archivo, formato, carpeta):
    exe = soffice()
    if not exe:
        raise RuntimeError(t("Hace falta LibreOffice para esto.", "LibreOffice is needed for this."))
    _correr([exe, f"-env:UserInstallation={PERFIL_LO.as_uri()}", "--headless",
             "--convert-to", formato, "--outdir", str(carpeta), str(archivo)])
    hecho = Path(carpeta) / (Path(archivo).stem + "." + formato)
    if not hecho.exists():
        raise RuntimeError(t("LibreOffice no generó el archivo.", "LibreOffice produced no file."))
    return hecho


# ---------------------------------------------------------------- portapapeles

def _cf_html(texto):
    """El HTML de Windows viene con una cabecera (Version:… StartFragment:…); solo interesa el fragmento."""
    m = re.search(r"<!--StartFragment-->(.*)<!--EndFragment-->", texto, re.S)
    return m.group(1) if m else texto[texto.find("<"):] if "<" in texto else texto


def leer_portapapeles():
    """(texto, es_html) de lo copiado, o (None, motivo)."""
    if WINDOWS:
        html = powershell("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-Clipboard -TextFormatType Html -Raw", 10)
        if html and html.strip():
            return _cf_html(html), True
        plano = powershell("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-Clipboard -Raw", 10)
        return (plano, False) if plano and plano.strip() else (None, t("El portapapeles está vacío.", "The clipboard is empty."))
    if os.environ.get("WAYLAND_DISPLAY") and tiene("wl-paste"):
        tipos_ok, tipos = correr(["wl-paste", "--list-types"], 5)
        leer = lambda tipo: correr(["wl-paste", "--no-newline", "--type", tipo], 5)    # noqa: E731
    elif tiene("xclip"):
        tipos_ok, tipos = correr(["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"], 5)
        leer = lambda tipo: correr(["xclip", "-selection", "clipboard", "-o", "-t", tipo], 5)    # noqa: E731
    else:
        return None, t("Instala wl-clipboard (Wayland) o xclip (X11).", "Install wl-clipboard (Wayland) or xclip (X11).")
    tipos = tipos.split() if tipos_ok else []
    if "text/html" in tipos:
        ok, html = leer("text/html")
        if ok and html.strip():
            return html, True
    for tipo in ("text/plain;charset=utf-8", "text/plain", "UTF8_STRING", "STRING"):
        if tipo in tipos:
            ok, texto = leer(tipo)
            if ok and texto.strip():
                return texto, False
    return None, t("Lo copiado no es texto.", "The clipboard has no text.")


# ---------------------------------------------------------------- selector de archivos

def elegir_archivos(titulo, exts):
    """Selector nativo (kdialog, zenity o el de Windows); lista de rutas (vacía si se cancela)."""
    patrones = " ".join(f"*{e}" for e in sorted(exts))
    if WINDOWS:
        filtro = ";".join(f"*{e}" for e in sorted(exts))
        script = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; "
                  f"$d.Title = $env:AKARI_TITULO; $d.Filter = 'Archivos|{filtro}'; $d.Multiselect = $true; "
                  "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                  "if ($d.ShowDialog() -eq 'OK') { $d.FileNames -join \"`n\" }")
        salida = powershell(script, 3600, {**os.environ, "AKARI_TITULO": titulo})
        return [r for r in (salida or "").splitlines() if r.strip()]
    inicio = str(HOME)
    kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if tiene("kdialog") and (kde or not tiene("zenity")):
        orden = ["kdialog", "--title", titulo, "--multiple", "--separate-output", "--getopenfilename", inicio, patrones]
    elif tiene("zenity"):
        orden = ["zenity", "--file-selection", "--multiple", "--separator=\n", f"--title={titulo}",
                 f"--file-filter={patrones}", f"--filename={inicio}/"]
    else:
        return None
    ok, salida = correr(orden, 3600)
    return [r for r in salida.splitlines() if r.strip()] if ok else []


# ---------------------------------------------------------------- conversor

class Conversor:
    def __init__(self, al_cambiar):
        self.al_cambiar = al_cambiar
        self.lock = threading.Lock()
        self.cola = queue.Queue()
        self.eligiendo = False
        self.instalacion = ""           # mensaje de la última instalación fallida
        self.trabajos = leer_json(HISTORIAL, [])
        if not isinstance(self.trabajos, list):
            self.trabajos = []
        for tr in self.trabajos:
            if tr.get("estado") in ("cola", "convirtiendo"):        # lo que quedó a medias al reiniciar
                tr.update(estado="error", mensaje=t("Se interrumpió (akari se reinició).", "Interrupted (akari restarted)."))
        threading.Thread(target=self._trabajar, daemon=True).start()

    def _guardar(self):
        escribir_json(HISTORIAL, self.trabajos[:MAX_HISTORIAL])

    @property
    def estado(self):
        with self.lock:
            return {
                "listo": extras.python_de("documentos") is not None,
                "instalando": extras.instalando("documentos"),
                "error_instalacion": self.instalacion,
                "libreoffice": soffice() is not None,
                "eligiendo": self.eligiendo,
                "carpeta": str(carpeta_documentos()),
                "a_md": sorted(A_MD), "desde_md": sorted(DESDE_MD),
                "trabajos": [dict(x) for x in self.trabajos[:MAX_HISTORIAL]],
            }

    def _cambio(self):
        self._guardar()
        self.al_cambiar()

    def _encolar(self, origen, nombre, formato, subido=False):
        tr = {"id": uuid.uuid4().hex[:8], "origen": str(origen), "nombre": nombre, "salida": "",
              "formato": formato, "subido": subido, "estado": "cola", "mensaje": "", "fecha": time.time()}
        with self.lock:
            self.trabajos.insert(0, tr)
            self.trabajos = self.trabajos[:MAX_HISTORIAL]
        self._cambio()
        self.cola.put(tr["id"])

    # ------------------------------------------------------------ acciones
    def accion(self, datos):
        accion = str(datos.get("accion"))
        formato = datos.get("formato") if datos.get("formato") in FORMATOS else "docx"
        if accion == "instalar":
            threading.Thread(target=self._instalar, daemon=True).start()
            return True, ""
        if accion == "convertir":
            rutas = datos.get("rutas") if isinstance(datos.get("rutas"), list) else []
            return self.agregar(rutas[:50], formato)
        if accion == "portapapeles":
            return self.portapapeles(formato)
        if accion == "elegir":
            threading.Thread(target=self._elegir, args=(datos.get("modo"), formato), daemon=True).start()
            return True, ""
        if accion == "abrir":
            tr = self._buscar(str(datos.get("id")))
            if not tr or not tr.get("salida"):
                return False, "?"
            ruta = Path(tr["salida"])
            return abrir(ruta.parent if datos.get("carpeta") else ruta), ""
        if accion == "carpeta":
            carpeta = carpeta_documentos()
            carpeta.mkdir(parents=True, exist_ok=True)
            return abrir(carpeta), ""
        if accion == "limpiar":
            with self.lock:
                self.trabajos = [x for x in self.trabajos if x["estado"] in ("cola", "convirtiendo")]
            self._cambio()
            return True, ""
        return False, "?"

    def _instalar(self):
        self.instalacion = ""
        self.al_cambiar()
        ok, mensaje = extras.instalar("documentos", PAQUETES)
        self.instalacion = "" if ok else mensaje
        if ok:
            notificar(t("Conversor listo", "Converter ready"), t("Ya puedes convertir documentos.", "You can convert documents now."))
        self.al_cambiar()

    def agregar(self, rutas, formato="docx"):
        """PDF/Word/Excel van a Markdown; los .md/.txt al formato pedido (pdf o docx)."""
        nuevos, rechazados = 0, []
        for texto in rutas:
            archivo = a_ruta(texto)
            ext = archivo.suffix.lower()
            if not archivo.is_file() or ext not in A_MD | DESDE_MD:
                rechazados.append(archivo.name or str(texto))
                continue
            self._encolar(archivo, archivo.name, "md" if ext in A_MD else formato)
            nuevos += 1
        if nuevos:
            return True, ""
        return False, t("Acepta PDF, Word, Excel, CSV o Markdown.", "Accepts PDF, Word, Excel, CSV or Markdown.")

    def subir(self, nombre, contenido, formato):
        """Un archivo que llega por HTTP (soltado en el panel o en las burbujas)."""
        nombre = nombre_seguro(nombre)
        ext = Path(nombre).suffix.lower()
        if ext not in A_MD | DESDE_MD:
            return False, t("Acepta PDF, Word, Excel, CSV o Markdown.", "Accepts PDF, Word, Excel, CSV or Markdown.")
        carpeta = SUBIDOS / uuid.uuid4().hex[:8]
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(contenido)
        self._encolar(carpeta / nombre, nombre, "md" if ext in A_MD else (formato if formato in FORMATOS else "docx"), subido=True)
        return True, ""

    def portapapeles(self, formato):
        texto, es_html = leer_portapapeles()
        if texto is None:
            return False, es_html
        plano = re.sub(r"<[^>]+>", "", re.sub(r"<(br|/p|/h\d|/li|/div|/tr)\b[^>]*>", "\n", texto, flags=re.I)) if es_html else texto
        carpeta = SUBIDOS / uuid.uuid4().hex[:8]
        carpeta.mkdir(parents=True, exist_ok=True)
        guardado = carpeta / ("copiado.html" if es_html else "copiado.md")
        guardado.write_text(texto, encoding="utf-8")
        self._encolar(guardado, nombre_de_texto(plano), formato, subido=True)
        return True, ""

    def _elegir(self, modo, formato):
        if self.eligiendo:
            return
        self.eligiendo = True
        self.al_cambiar()
        try:
            if modo == "desde-md":
                rutas = elegir_archivos(t("Elegir Markdown", "Choose Markdown"), DESDE_MD)
            else:
                rutas = elegir_archivos(t("Elegir PDF, Word o Excel", "Choose PDF, Word or Excel"), A_MD)
            if rutas is None:
                notificar("akari", t("No hay selector de archivos: instala zenity o kdialog.", "No file picker: install zenity or kdialog."))
            elif rutas:
                self.agregar(rutas, formato)
        finally:
            self.eligiendo = False
            self.al_cambiar()

    def _buscar(self, ident):
        return next((x for x in self.trabajos if x["id"] == ident), None)

    # ------------------------------------------------------------ trabajo
    def _a_markdown(self, tr, origen, tmp):
        python = extras.python_de("documentos")
        if not python:
            raise RuntimeError(t("Primero instala el conversor.", "Install the converter first."))
        salida = destino_para(Path(tr["nombre"]).stem, ".md", None if tr.get("subido") else origen.parent)
        entrada, ext = origen, origen.suffix.lower()
        if ext in (".doc", ".odt", ".rtf"):         # markitdown solo lee .docx
            entrada = libreoffice(origen, "docx", tmp)
        elif ext == ".ods":                         # pandas no lee .ods sin odfpy
            entrada = libreoffice(origen, "xlsx", tmp)
        if ext in EXCEL:
            _correr([str(python), str(RECURSOS / "excel_md.py"), str(entrada), str(salida)])
        else:
            _correr([str(python), "-m", "markitdown", str(entrada), "-o", str(salida)])
        if not salida.exists():
            raise RuntimeError(t("falló la conversión", "conversion failed"))
        return salida

    def _pandoc(self):
        python = extras.python_de("documentos")
        if python:      # pypandoc_binary trae pandoc dentro del entorno
            ok, ruta = correr([str(python), "-c", "import pypandoc; print(pypandoc.get_pandoc_path())"], 30)
            if ok and Path(ruta.splitlines()[-1]).exists():
                return ruta.splitlines()[-1]
        return shutil.which("pandoc")

    def _a_documento(self, tr, origen, tmp):
        pandoc = self._pandoc()
        if not pandoc:
            raise RuntimeError(t("Primero instala el conversor.", "Install the converter first."))
        nombre = Path(tr["nombre"]).stem if not tr.get("subido") or origen.suffix.lower() in DESDE_MD else tr["nombre"]
        carpeta = None if tr.get("subido") else origen.parent
        recursos = str(HOME if tr.get("subido") else origen.parent)
        if origen.suffix.lower() == ".html":
            entrada, lector = origen, "html"
        else:
            entrada, lector = tmp / "entrada.md", LECTOR_MD
            entrada.write_text(sin_enlaces_obsidian(origen.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        docx = tmp / (nombre_seguro(nombre) + ".docx")
        _correr([pandoc, "-f", lector, "--lua-filter", str(RECURSOS / "anchos.lua"), f"--resource-path={recursos}",
                 "-o", str(docx), str(entrada)])
        hecho = docx if tr["formato"] == "docx" else libreoffice(docx, "pdf", tmp)
        salida = destino_para(nombre_seguro(nombre), hecho.suffix, carpeta)
        shutil.move(str(hecho), str(salida))
        return salida

    def _trabajar(self):
        while True:
            ident = self.cola.get()
            with self.lock:
                tr = self._buscar(ident)
                if not tr:
                    continue
                tr["estado"] = "convirtiendo"
            self.al_cambiar()
            origen = Path(tr["origen"])
            try:
                with tempfile.TemporaryDirectory(prefix="akari-") as tmp:
                    salida = (self._a_markdown if tr["formato"] == "md" else self._a_documento)(tr, origen, Path(tmp))
                tam = salida.stat().st_size
                vacio = tr["formato"] == "md" and tam < 20
                with self.lock:
                    tr.update(estado="listo", salida=str(salida), mensaje=t("Sin texto (¿PDF escaneado?)", "No text (scanned PDF?)")
                              if vacio else f"{tam // 1024 or 1} KB")
                notificar(t("Conversión lista", "Conversion done"), f"{tr['nombre']} → {salida.name}")
            except subprocess.TimeoutExpired:
                with self.lock:
                    tr.update(estado="error", mensaje=t("Tardó demasiado.", "It took too long."))
            except Exception as e:      # noqa: BLE001 — cualquier fallo queda en el historial, no tumba el hilo
                with self.lock:
                    tr.update(estado="error", mensaje=str(e)[:200])
                notificar(t("No se pudo convertir", "Couldn't convert"), f"{tr['nombre']}: {e}")
            if tr.get("subido"):
                shutil.rmtree(origen.parent, ignore_errors=True)
            self._cambio()
