"""Cerebro: un mapa de la computadora y una memoria de lo que se hizo con la IA, para que Claude
Code, Codex o el asistente de akari busquen ahí primero.

REGLA DE ORO: nunca mueve, renombra, edita ni borra archivos del usuario. Solo mira nombres, rutas,
tipos, tamaños y fechas (y, en las carpetas que el usuario activa, lee el texto para buscar por
significado). Escribe únicamente en su base (DATOS/cerebro.db) y en su bóveda de Obsidian.

  Mapa        recorre las carpetas elegidas (por defecto la personal) sin IA y guarda el índice en
              SQLite con FTS5; reconoce proyectos (.git, package.json, pyproject.toml, *.sln…) y áreas
              (carpetas con muchos documentos: «Universidad», «Trabajo»…). Revisión incremental al
              arrancar y cada noche.
  Bóveda      boveda.py: Inicio, Mapa/<Área>, Proyectos/<Proyecto>, Como-me-organizo, Bitacora, Pendientes.
  Memoria     memoria.py: un resumen corto de cada sesión de Claude Code, Codex y del asistente.
  Buscar      por nombre (FTS, instantáneo) y por significado (embeddings locales de Ollama); y
              `pregunta`: el modelo de chat decide qué buscar, junta los resultados y responde.
  Agentes     `akari cerebro …` con salida corta, herramientas del asistente (HERRAMIENTAS) y ganchos
              de Claude Code / AGENTS.md de Codex (ganchos.py).

Privacidad: todo queda en el equipo. Si el modelo elegido es por API, solo se manda (y solo si el
usuario lo permitió) el texto mínimo de cada pregunta: nombres, rutas y fragmentos encontrados.
"""
import json
import operator
import os
import re
import sqlite3
import sys
import threading
import time
import zipfile
from array import array
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .comun import CONFIG, DATOS, HOME, IDIOMA, WINDOWS, abrir, correr, escribir_json, leer_json, t, tiene

AJUSTES = CONFIG / "cerebro.json"
BD = Path(os.environ.get("AKARI_CEREBRO_BD") or DATOS / "cerebro.db")
MAX_ARCHIVOS = 400_000          # tope por revisión (un disco enorme no debe colgar el equipo)
MAX_PROFUNDIDAD = 24
MIN_AREA = 5                    # documentos para que una carpeta cuente como área
MAX_VECTORES = 20_000           # cuántos nombres de archivo entran en la búsqueda por significado
DIMENSIONES = 256               # embeddings recortados (Matryoshka): menos memoria, casi igual de buenos
HORA_NOCHE = (3, 5)             # entre las 3 y las 5 de la mañana, la revisión de cada noche

# ---------------------------------------------------------------- tipos de archivo

TIPOS = {
    "documento": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".markdown", ".tex", ".pages", ".epub", ".djvu"},
    "hoja": {".xls", ".xlsx", ".xlsm", ".ods", ".csv", ".numbers"},
    "presentacion": {".ppt", ".pptx", ".odp", ".key"},
    "imagen": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".bmp", ".tif", ".tiff", ".raw", ".cr2", ".nef", ".psd"},
    "audio": {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv"},
    "codigo": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php", ".html",
               ".css", ".sh", ".ps1", ".ipynb", ".sql", ".kt", ".swift", ".r", ".lua", ".json", ".yaml", ".yml", ".toml", ".qml"},
    "comprimido": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"},
    "programa": {".exe", ".msi", ".appimage", ".deb", ".rpm", ".apk", ".dmg", ".flatpakref"},
}
TIPO_DE = {ext: tipo for tipo, exts in TIPOS.items() for ext in exts}
DOCUMENTOS = TIPOS["documento"] | TIPOS["hoja"] | TIPOS["presentacion"]
NOMBRE_TIPO = {"documento": ("documento", "document"), "hoja": ("hoja de cálculo", "spreadsheet"),
               "presentacion": ("presentación", "presentation"), "imagen": ("imagen", "image"), "audio": ("audio", "audio"),
               "video": ("video", "video"), "codigo": ("código", "code"), "comprimido": ("comprimido", "archive"),
               "programa": ("programa", "program"), "carpeta": ("carpeta", "folder"), "otro": ("archivo", "file")}
# lo que nunca se abre solo (un modelo pidiendo «abrir» un .exe lo ejecutaría): solo se muestra en su carpeta
NO_ABRIR = TIPOS["programa"] | {".bat", ".cmd", ".com", ".scr", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".ps1", ".sh", ".lnk",
                                ".desktop", ".jar", ".reg", ".msc", ".cpl", ".hta", ".pif", ".run", ".bin", ".command"}

# ---------------------------------------------------------------- exclusiones (siempre)

# carpetas que no se recorren nunca, estén donde estén (en minúsculas). Además se saltan todas las
# ocultas (.ssh, .gnupg, .git, .cache, .mozilla, .config, papeleras .Trash-*…) y, en Windows, las
# marcadas como ocultas o de sistema.
DIRS_FUERA = {"node_modules", "__pycache__", "venv", "site-packages", "bower_components", "cache", "caches", "gpucache",
              "code cache", "cacheddata", "shadercache", "$recycle.bin", "recycler", "system volume information", "appdata",
              "lost+found", "keyrings", "keychains", "1password", "bitwarden", "keepass", "keepassxc", "dashlane", "lastpass",
              "enpass", "password safe", "msocache", "$winreagent", "$windows.~bt", "$windows.~ws"}
# solo justo debajo de la carpeta personal
DIRS_FUERA_HOME = {"snap", "library", "applications"} if sys.platform == "darwin" else {"snap"}
# solo en la raíz de un disco (por si el usuario elige / o C:\)
DIRS_FUERA_RAIZ = {"proc", "sys", "dev", "run", "tmp", "var", "usr", "bin", "sbin", "lib", "lib32", "lib64", "libx32", "etc",
                   "boot", "opt", "srv", "root", "snap", "nix", "windows", "program files", "program files (x86)",
                   "programdata", "recovery", "perflogs", "users", "documents and settings", "system", "private", "cores"}
EXT_FUERA = {".key", ".pem", ".p12", ".pfx", ".kdbx", ".kdb", ".keychain", ".keychain-db", ".gpg", ".pgp", ".ppk", ".jks",
             ".keystore", ".ovpn", ".crt", ".cer", ".der", ".csr", ".sqlite-wal", ".lock", ".tmp", ".part", ".crdownload"}
PALABRAS_FUERA = ("credential", "password", "passwd", "contraseña", "contrasena", "secret_key", "private_key")
ARCHIVOS_FUERA = {"desktop.ini", "thumbs.db", "ntuser.dat", "hiberfil.sys", "pagefile.sys", "swapfile.sys"}

# lo que el usuario ve en la pantalla de primera vez
EXCLUIDO_TEXTO = (
    ("Carpetas ocultas: .ssh, .gnupg, .git, .config, cachés y papelera",
     "Hidden folders: .ssh, .gnupg, .git, .config, caches and trash"),
    ("Llaveros, gestores de contraseñas y perfiles de navegadores",
     "Keyrings, password managers and browser profiles"),
    (".env, *credentials*, *.key, *.pem y archivos de claves",
     ".env, *credentials*, *.key, *.pem and key files"),
    ("node_modules, entornos de Python y carpetas del sistema (AppData, Windows, Archivos de programa)",
     "node_modules, Python environments and system folders (AppData, Windows, Program Files)"),
)

# marcadores de proyecto: archivos, carpetas y extensiones
PROYECTO_ARCHIVOS = {"package.json": "Node", "pyproject.toml": "Python", "setup.py": "Python", "requirements.txt": "Python",
                     "cargo.toml": "Rust", "go.mod": "Go", "pom.xml": "Java", "build.gradle": "Java/Kotlin",
                     "build.gradle.kts": "Kotlin", "composer.json": "PHP", "gemfile": "Ruby", "cmakelists.txt": "C/C++",
                     "deno.json": "Deno", "pubspec.yaml": "Flutter", "mix.exs": "Elixir", "package.swift": "Swift",
                     "makefile": "Make", "dockerfile": "Docker", "main.tex": "LaTeX", "_quarto.yml": "Quarto"}
PROYECTO_DIRS = {".git": "Git", ".obsidian": "Obsidian", ".hg": "Mercurial", ".svn": "SVN"}
PROYECTO_EXT = {".sln": ".NET", ".csproj": ".NET", ".xcodeproj": "Xcode", ".rproj": "R", ".uproject": "Unreal"}
# carpetas genéricas: contienen cosas pero no son un «área» por sí mismas
GENERICAS = {"documentos", "documents", "mis documentos", "my documents", "escritorio", "desktop", "descargas", "downloads",
             "onedrive", "dropbox", "google drive", "mi unidad", "my drive", "icloud drive", "nextcloud", "home", "users",
             "usuarios", "archivos", "files", "datos", "data", "varios", "misc", "otros", "other"}
PALABRAS_VACIAS = set("""el la los las un una unos unas de del al a y o u en con por para que qué mi mis tu tus su sus
donde dónde esta está están estan deje dejé dejo guarde guardé puse tengo tenía archivo archivos carpeta busca buscar
encuentra encontrar lo le me se es era hay sobre ese esa eso este esto ver abrir abre the an of to in on for my your
where is are did i put left saved file files folder find search it me please show open""".split())

_cerrojo = threading.Lock()


# ---------------------------------------------------------------- ajustes

def ajustes():
    """{"carpetas": [...], "boveda": ruta real de la bóveda, "texto_en": [...], "permitir_api": bool,
    "embeddings": modelo|None, "creado": ts}. Sin "carpetas" el cerebro no está configurado."""
    return leer_json(AJUSTES)


def guardar_ajustes(a):
    escribir_json(AJUSTES, a)


def configurado():
    a = ajustes()
    return bool(a.get("carpetas")) and bool(a.get("boveda"))


def boveda_para(elegida):
    """Dónde va la bóveda si el usuario eligió `elegida`: ahí mismo si está vacía, no existe o ya es
    nuestra; si es una bóveda o carpeta con cosas del usuario, en su subcarpeta akari/ (sin tocar el resto)."""
    elegida = Path(elegida).expanduser()
    if not elegida.exists() or (elegida / ".akari-cerebro").exists():
        return elegida
    try:
        propias = [x for x in elegida.iterdir() if x.name not in (".akari-cerebro",)]
    except OSError:
        return elegida / "akari"
    return elegida / "akari" if propias else elegida


def boveda():
    """La carpeta de la bóveda (o None si no está configurado)."""
    ruta = ajustes().get("boveda")
    return Path(ruta) if ruta else None


def carpetas_candidatas():
    """Lo que se ofrece recorrer: la carpeta personal y los discos montados."""
    lista = [{"ruta": str(HOME), "nombre": t("Carpeta personal", "Home folder"), "tipo": "personal"}]
    vistos = {str(HOME)}
    if WINDOWS:
        import ctypes
        import string
        sistema = (os.environ.get("SystemDrive") or "C:").upper()
        for letra in string.ascii_uppercase:
            raiz = f"{letra}:\\"
            if f"{letra}:" == sistema:
                continue
            try:
                tipo = ctypes.windll.kernel32.GetDriveTypeW(raiz)
            except (OSError, AttributeError):
                tipo = 0
            if tipo in (2, 3) and os.path.isdir(raiz):          # extraíble o fijo
                lista.append({"ruta": raiz, "nombre": t(f"Disco {letra}:", f"Drive {letra}:"), "tipo": "disco"})
    else:
        usuario = os.environ.get("USER") or HOME.name
        for base in (Path("/media") / usuario, Path("/run/media") / usuario, Path("/mnt"), Path("/media")):
            try:
                hijos = sorted(base.iterdir()) if base.is_dir() else []
            except OSError:
                hijos = []
            for d in hijos:
                if str(d) in vistos or d.name == usuario or not d.is_dir() or not os.access(d, os.R_OK):
                    continue
                vistos.add(str(d))
                lista.append({"ruta": str(d), "nombre": d.name, "tipo": "disco"})
    return lista


# ---------------------------------------------------------------- base de datos

_FTS = None


def _esquema(c):
    global _FTS
    c.executescript("""
    CREATE TABLE IF NOT EXISTS archivos (id INTEGER PRIMARY KEY, ruta TEXT UNIQUE, nombre TEXT, carpeta TEXT,
        lugar TEXT, ext TEXT, tipo TEXT, tam INTEGER, mtime REAL, raiz TEXT, proyecto TEXT);
    CREATE INDEX IF NOT EXISTS archivos_carpeta ON archivos(carpeta);
    CREATE INDEX IF NOT EXISTS archivos_tipo ON archivos(tipo, mtime);
    CREATE TABLE IF NOT EXISTS proyectos (ruta TEXT PRIMARY KEY, nombre TEXT, nota TEXT, tipo TEXT, descripcion TEXT,
        origen TEXT, mtime REAL);
    CREATE TABLE IF NOT EXISTS areas (ruta TEXT PRIMARY KEY, nombre TEXT, nota TEXT, docs INTEGER, sueltos INTEGER);
    CREATE TABLE IF NOT EXISTS sesiones (id TEXT PRIMARY KEY, agente TEXT, archivo TEXT, inicio REAL, fin REAL, cwd TEXT,
        proyecto TEXT, titulo TEXT, resumen TEXT, pendiente TEXT, archivos TEXT, tam INTEGER, estado TEXT, con_ia INTEGER);
    CREATE INDEX IF NOT EXISTS sesiones_fin ON sesiones(fin);
    CREATE TABLE IF NOT EXISTS pendientes (id INTEGER PRIMARY KEY, texto TEXT, proyecto TEXT, creado REAL, hecho REAL,
        origen TEXT);
    CREATE TABLE IF NOT EXISTS notas (id INTEGER PRIMARY KEY, t REAL, texto TEXT, proyecto TEXT, agente TEXT);
    CREATE TABLE IF NOT EXISTS vectores (clave TEXT PRIMARY KEY, tipo TEXT, ruta TEXT, texto TEXT, firma TEXT,
        modelo TEXT, vec BLOB);
    CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT);
    """)
    if _FTS is None:
        try:
            c.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS nombres USING fts5(nombre, lugar, content='archivos', content_rowid='id',
                tokenize="unicode61 remove_diacritics 2");
            CREATE TRIGGER IF NOT EXISTS archivos_ai AFTER INSERT ON archivos BEGIN
                INSERT INTO nombres(rowid, nombre, lugar) VALUES (new.id, new.nombre, new.lugar); END;
            CREATE TRIGGER IF NOT EXISTS archivos_ad AFTER DELETE ON archivos BEGIN
                INSERT INTO nombres(nombres, rowid, nombre, lugar) VALUES ('delete', old.id, old.nombre, old.lugar); END;
            CREATE TRIGGER IF NOT EXISTS archivos_au AFTER UPDATE OF nombre, lugar ON archivos BEGIN
                INSERT INTO nombres(nombres, rowid, nombre, lugar) VALUES ('delete', old.id, old.nombre, old.lugar);
                INSERT INTO nombres(rowid, nombre, lugar) VALUES (new.id, new.nombre, new.lugar); END;
            """)
            _FTS = True
        except sqlite3.OperationalError:        # un SQLite sin FTS5: se busca con LIKE
            _FTS = False


@contextmanager
def bd():
    """Conexión a DATOS/cerebro.db (una por uso: el servicio y la terminal la abren a la vez)."""
    BD.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(BD), timeout=20)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _esquema(c)
        yield c
        c.commit()
    finally:
        c.close()


def meta(c, clave, defecto=None):
    fila = c.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
    if not fila:
        return defecto
    try:
        return json.loads(fila[0])
    except ValueError:
        return defecto


def poner_meta(c, clave, valor):
    c.execute("INSERT OR REPLACE INTO meta(clave, valor) VALUES (?, ?)", (clave, json.dumps(valor, ensure_ascii=False)))


def registrar_uso(quien):
    """Cuándo usó el cerebro cada agente (para la cápsula: «Claude Code lo usó hace 2 h»)."""
    try:
        with bd() as c:
            uso = meta(c, "uso", {})
            hoy = time.strftime("%Y-%m-%d")
            u = uso.get(quien) or {}
            u = {"t": time.time(), "hoy": (u.get("hoy", 0) if u.get("dia") == hoy else 0) + 1, "dia": hoy}
            uso[quien] = u
            poner_meta(c, "uso", uso)
    except sqlite3.Error:
        pass


def quien_llama():
    """claude / codex / terminal según el entorno con el que corre la orden."""
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if any(k.startswith("CODEX_") for k in os.environ):
        return "codex"
    return "terminal"


# ---------------------------------------------------------------- mapa

def tipo_de(nombre):
    return TIPO_DE.get(os.path.splitext(nombre)[1].lower(), "otro")


def archivo_fuera(nombre):
    bajo = nombre.lower()
    if bajo.startswith(".") or bajo.startswith("~$") or bajo in ARCHIVOS_FUERA:
        return True
    if os.path.splitext(bajo)[1] in EXT_FUERA or bajo.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")):
        return True
    return any(p in bajo for p in PALABRAS_FUERA)


def carpeta_fuera(nombre, padre_es_home=False, padre_es_raiz=False):
    bajo = nombre.lower()
    if bajo.startswith(".") or bajo.startswith("$") or bajo in DIRS_FUERA or bajo.startswith(".trash"):
        return True
    if padre_es_home and bajo in DIRS_FUERA_HOME:
        return True
    return padre_es_raiz and bajo in DIRS_FUERA_RAIZ


def _oculto_windows(entrada):
    if not WINDOWS:
        return False
    try:
        return bool(entrada.stat(follow_symlinks=False).st_file_attributes & 0x6)      # HIDDEN | SYSTEM
    except (OSError, AttributeError):
        return False


def _es_raiz_disco(ruta):
    return Path(ruta).parent == Path(ruta)


def lugar_de(carpeta, raiz):
    """Las últimas carpetas de la ruta (para buscar «informe tesis» aunque «tesis» sea la carpeta)."""
    try:
        partes = Path(carpeta).relative_to(raiz).parts
    except ValueError:
        partes = Path(carpeta).parts
    return " ".join(partes[-4:])


class Revision:
    """Un recorrido incremental: solo escribe en la base lo que cambió (por fecha y tamaño)."""

    def __init__(self, al_avanzar=None):
        self.al_avanzar = al_avanzar or (lambda _: None)
        self.archivos = 0
        self.carpeta = ""
        self.cortada = False
        self.proyectos = {}         # ruta -> {nombre, tipo}
        self.directos = {}          # carpeta -> documentos sueltos
        self.hijos = {}             # carpeta -> subcarpetas
        self.excluir = set()        # rutas que nunca se recorren (la bóveda, los datos de akari)

    def correr(self, carpetas):
        b = boveda()
        self.excluir = {os.path.normcase(str(x)) for x in (b, DATOS, CONFIG) if x}
        inicio = time.time()
        with bd() as c:
            # carpetas que ya no se recorren: fuera del índice
            raices = [str(Path(x)) for x in carpetas]
            for (raiz,) in c.execute("SELECT DISTINCT raiz FROM archivos").fetchall():
                if raiz not in raices:
                    c.execute("DELETE FROM archivos WHERE raiz=?", (raiz,))
            for raiz in raices:
                if Path(raiz).is_dir():
                    self._recorrer(c, Path(raiz))
                c.commit()
            self._guardar_proyectos(c)
            self._guardar_areas(c, raices)
            poner_meta(c, "ultima_revision", time.time())
            poner_meta(c, "duracion", round(time.time() - inicio, 1))
            poner_meta(c, "cortada", self.cortada)
        return self

    # ------------------------------------------------------------ recorrido
    def _recorrer(self, c, raiz):
        pila = [(raiz, 0, None)]
        while pila:
            carpeta, nivel, proyecto = pila.pop()
            if self.archivos >= MAX_ARCHIVOS:
                self.cortada = True
                return
            try:
                entradas = list(os.scandir(carpeta))
            except OSError:
                continue
            nombres = {e.name.lower() for e in entradas}
            marcas = self._marcas(entradas, nombres)
            if marcas and proyecto is None:
                proyecto = str(carpeta)
                self.proyectos[proyecto] = {"nombre": carpeta.name or str(carpeta), "tipo": " · ".join(marcas)}
            es_home, es_raiz = Path(carpeta) == HOME, _es_raiz_disco(carpeta)
            vistos, subcarpetas, sueltos = {}, [], 0
            for e in entradas:
                try:
                    es_dir = e.is_dir(follow_symlinks=False)
                    if not es_dir and not e.is_file(follow_symlinks=False):
                        continue                # enlaces simbólicos, sockets…: nunca se siguen
                except OSError:
                    continue
                if es_dir:
                    if carpeta_fuera(e.name, es_home, es_raiz) or _oculto_windows(e) or \
                            os.path.normcase(e.path) in self.excluir:
                        continue
                    subcarpetas.append(e.path)
                    vistos[e.path] = (e.name, "carpeta", 0, self._mtime(e))
                else:
                    if archivo_fuera(e.name) or _oculto_windows(e):
                        continue
                    try:
                        info = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    tipo = tipo_de(e.name)
                    vistos[e.path] = (e.name, tipo, info.st_size, info.st_mtime)
                    if proyecto is None and os.path.splitext(e.name)[1].lower() in DOCUMENTOS:
                        sueltos += 1
            self.archivos += len(vistos)
            self.directos[str(carpeta)] = sueltos
            self.hijos[str(carpeta)] = subcarpetas
            self._sincronizar(c, carpeta, raiz, vistos, proyecto)
            if self.carpeta != str(carpeta) and self.archivos % 500 < len(vistos) + 1:
                self.carpeta = str(carpeta)
                self.al_avanzar(self)
            if nivel < MAX_PROFUNDIDAD:
                for sub in reversed(subcarpetas):
                    pila.append((Path(sub), nivel + 1, proyecto))

    @staticmethod
    def _mtime(e):
        try:
            return e.stat(follow_symlinks=False).st_mtime
        except OSError:
            return 0

    @staticmethod
    def _marcas(entradas, nombres):
        marcas = [v for k, v in PROYECTO_DIRS.items() if k in nombres]
        marcas += sorted({v for k, v in PROYECTO_ARCHIVOS.items() if k in nombres} - set(marcas))
        for e in entradas:
            ext = os.path.splitext(e.name)[1].lower()
            if ext in PROYECTO_EXT and PROYECTO_EXT[ext] not in marcas:
                marcas.append(PROYECTO_EXT[ext])
        # un Makefile o un Dockerfile solos no hacen un proyecto
        if marcas and set(marcas) <= {"Make", "Docker"}:
            return []
        return marcas

    def _sincronizar(self, c, carpeta, raiz, vistos, proyecto):
        antes = {f["ruta"]: (f["tam"], f["mtime"], f["proyecto"]) for f in
                 c.execute("SELECT ruta, tam, mtime, proyecto FROM archivos WHERE carpeta=?", (str(carpeta),))}
        lugar = lugar_de(carpeta, raiz)
        nuevos = []
        for ruta, (nombre, tipo, tam, mtime) in vistos.items():
            previo = antes.get(ruta)
            if previo and previo[0] == tam and abs((previo[1] or 0) - mtime) < 1 and previo[2] == proyecto:
                continue
            nuevos.append((ruta, nombre, str(carpeta), lugar, os.path.splitext(nombre)[1].lower() if tipo != "carpeta" else "",
                           tipo, tam, mtime, str(raiz), proyecto))
        if nuevos:
            c.executemany("""INSERT INTO archivos(ruta, nombre, carpeta, lugar, ext, tipo, tam, mtime, raiz, proyecto)
                VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ruta) DO UPDATE SET nombre=excluded.nombre, lugar=excluded.lugar,
                tipo=excluded.tipo, tam=excluded.tam, mtime=excluded.mtime, raiz=excluded.raiz, proyecto=excluded.proyecto""",
                          nuevos)
        for ruta in set(antes) - set(vistos):
            borrar_bajo(c, ruta)

    # ------------------------------------------------------------ proyectos y áreas
    def _guardar_proyectos(self, c):
        nombres = _nombres_unicos(self.proyectos, {r["ruta"]: r["nota"] for r in c.execute(
            "SELECT ruta, nota FROM proyectos WHERE origen='sesion'") if r["ruta"] not in self.proyectos})
        anteriores = {r["ruta"]: r for r in c.execute("SELECT * FROM proyectos WHERE origen='mapa'")}
        for ruta, p in self.proyectos.items():
            previo = anteriores.pop(ruta, None)
            descripcion = previo["descripcion"] if previo and previo["descripcion"] else leer_readme(ruta)
            c.execute("""INSERT OR REPLACE INTO proyectos(ruta, nombre, nota, tipo, descripcion, origen, mtime)
                VALUES (?,?,?,?,?,?,?)""", (ruta, p["nombre"], nombres[ruta], p["tipo"], descripcion, "mapa",
                                           _mtime_ruta(ruta)))
        for ruta in anteriores:                 # proyectos que ya no están (o ya no se recorren)
            if not Path(ruta).is_dir() or not any(_bajo(ruta, r) for r in ajustes().get("carpetas", [])):
                c.execute("DELETE FROM proyectos WHERE ruta=?", (ruta,))

    def _guardar_areas(self, c, raices):
        total = {}
        for carpeta in sorted(self.directos, key=lambda x: -len(Path(x).parts)):     # de lo más hondo hacia arriba
            if carpeta in self.proyectos:
                total[carpeta] = 0
                continue
            total[carpeta] = self.directos[carpeta] + sum(total.get(h, 0) for h in self.hijos.get(carpeta, []))
        areas = {}

        def visitar(carpeta, nivel):
            if carpeta in self.proyectos or total.get(carpeta, 0) < MIN_AREA or nivel > 4:
                return
            nombre = Path(carpeta).name or carpeta
            generica = nivel == 0 or nombre.lower() in GENERICAS
            if not generica:
                areas[carpeta] = {"nombre": nombre, "docs": total[carpeta], "sueltos": 0}
                return
            if nivel > 0 and self.directos.get(carpeta, 0) >= MIN_AREA:      # p. ej. Descargas llena de PDF
                areas[carpeta] = {"nombre": nombre, "docs": self.directos[carpeta], "sueltos": 1}
            for h in self.hijos.get(carpeta, []):
                visitar(h, nivel + 1)

        for raiz in raices:
            visitar(str(Path(raiz)), 0)
        nombres = _nombres_unicos(areas, {})
        c.execute("DELETE FROM areas")
        c.executemany("INSERT INTO areas(ruta, nombre, nota, docs, sueltos) VALUES (?,?,?,?,?)",
                      [(r, a["nombre"], nombres[r], a["docs"], a["sueltos"]) for r, a in areas.items()])


def borrar_bajo(c, ruta):
    """Quita del índice una ruta y, si era carpeta, todo lo que tenía debajo."""
    c.execute("DELETE FROM archivos WHERE ruta=?", (ruta,))
    prefijo = ruta.rstrip("/\\") + os.sep
    c.execute("DELETE FROM archivos WHERE ruta >= ? AND ruta < ?", (prefijo, prefijo + "\uffff"))


def _bajo(ruta, carpeta):
    try:
        Path(ruta).relative_to(carpeta)
        return True
    except ValueError:
        return False


def _mtime_ruta(ruta):
    try:
        return os.stat(ruta).st_mtime
    except OSError:
        return 0


def nombre_nota(texto):
    """Un nombre de nota válido en Obsidian y en Windows."""
    limpio = re.sub(r'[\\/:*?"<>|#^\[\]\x00-\x1f]+', " ", str(texto)).strip(" .") or "sin-nombre"
    return " ".join(limpio.split())[:80]


def _nombres_unicos(cosas, ocupados):
    """ruta -> nombre de nota; si dos se llaman igual (dos «web»), se les agrega la carpeta de arriba."""
    usados = {v.lower() for v in ocupados.values() if v}
    salida, cuenta = {}, {}
    for ruta, x in cosas.items():
        cuenta[x["nombre"].lower()] = cuenta.get(x["nombre"].lower(), 0) + 1
    for ruta, x in sorted(cosas.items()):
        nombre = nombre_nota(x["nombre"])
        if cuenta[x["nombre"].lower()] > 1 or nombre.lower() in usados:
            nombre = nombre_nota(f"{x['nombre']} ({Path(ruta).parent.name or Path(ruta).anchor})")
        n, base = 2, nombre
        while nombre.lower() in usados:
            nombre, n = f"{base} {n}", n + 1
        usados.add(nombre.lower())
        salida[ruta] = nombre
    return salida


def leer_readme(carpeta, largo=240):
    """El primer párrafo del README (solo se lee; sirve para «de qué trata» el proyecto)."""
    for nombre in ("README.md", "readme.md", "Readme.md", "README.txt", "README", "README.rst", "LEEME.md", "LÉEME.md"):
        ruta = Path(carpeta) / nombre
        try:
            if not ruta.is_file() or ruta.stat().st_size > 2_000_000:
                continue
            with open(ruta, encoding="utf-8", errors="replace") as f:
                texto = f.read(8000)
        except OSError:
            continue
        for parrafo in re.split(r"\n\s*\n", texto):
            limpio = re.sub(r"<[^>]+>|!\[[^\]]*\]\([^)]*\)|\[!\[.*?\]\(.*?\)\]\(.*?\)", "", parrafo)
            limpio = re.sub(r"[#*_`>]+", "", limpio)
            limpio = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", limpio)
            limpio = " ".join(limpio.split())
            if len(limpio) >= 25 and not limpio.startswith(("|", "---", "===")):
                return limpio[:largo].rstrip() + ("…" if len(limpio) > largo else "")
    return ""


# ---------------------------------------------------------------- consultas

def cifras():
    with bd() as c:
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return {
            "archivos": c.execute("SELECT COUNT(*) FROM archivos WHERE tipo != 'carpeta'").fetchone()[0],
            "carpetas": c.execute("SELECT COUNT(*) FROM archivos WHERE tipo = 'carpeta'").fetchone()[0],
            "proyectos": c.execute("SELECT COUNT(*) FROM proyectos").fetchone()[0],
            "areas": c.execute("SELECT COUNT(*) FROM areas").fetchone()[0],
            "sesiones_hoy": c.execute("SELECT COUNT(*) FROM sesiones WHERE fin >= ?", (hoy,)).fetchone()[0],
            "sesiones": c.execute("SELECT COUNT(*) FROM sesiones").fetchone()[0],
            "pendientes": c.execute("SELECT COUNT(*) FROM pendientes WHERE hecho IS NULL").fetchone()[0],
            "ultima_revision": meta(c, "ultima_revision"),
            "duracion": meta(c, "duracion"),
            "cortada": meta(c, "cortada", False),
            "uso": meta(c, "uso", {}),
        }


def palabras(consulta):
    todas = re.findall(r"\w+", consulta.lower())
    utiles = [p for p in todas if p not in PALABRAS_VACIAS and (len(p) > 1 or p.isdigit())]
    return utiles or [p for p in todas if len(p) > 1]


def _puntaje(fila, base):
    """bm25 (más negativo = mejor) + documentos y cosas recientes primero."""
    extra = {"documento": 3, "hoja": 2.5, "presentacion": 2.5, "carpeta": 2, "imagen": 0.5, "codigo": -1}.get(fila["tipo"], 0)
    if fila["proyecto"] and fila["tipo"] not in ("carpeta",) and fila["ruta"] != fila["proyecto"]:
        extra -= 1.5                     # los archivos de dentro de un proyecto, después
    edad = max(0.0, (time.time() - (fila["mtime"] or 0)) / 86400)
    return -base + extra + max(0.0, 2.0 - edad / 90)


def buscar(consulta, limite=10, tipo=None):
    """Búsqueda por nombre (y carpeta) en el mapa: [{ruta, nombre, tipo, tam, mtime, carpeta}]."""
    toks = palabras(consulta)[:8]
    if not toks:
        return []
    filtro, extra = ("AND a.tipo = ?", [tipo]) if tipo else ("", [])
    with bd() as c:
        filas = []
        if _FTS:
            for union in (" ", " OR "):
                expr = union.join(f'"{p}"*' for p in toks)
                try:
                    filas = c.execute(f"""SELECT a.*, bm25(nombres, 10.0, 2.0) AS r FROM nombres JOIN archivos a ON a.id = nombres.rowid
                        WHERE nombres MATCH ? {filtro} ORDER BY r LIMIT 300""", [expr, *extra]).fetchall()
                except sqlite3.OperationalError:
                    filas = []
                if filas or len(toks) == 1:
                    break
        else:
            donde = " AND ".join("(a.nombre LIKE ? ESCAPE '\\' OR a.lugar LIKE ? ESCAPE '\\')" for _ in toks)
            valores = []
            for p in toks:
                patron = "%" + p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                valores += [patron, patron]
            filas = c.execute(f"SELECT a.*, -1.0 AS r FROM archivos a WHERE {donde} {filtro} LIMIT 300",
                              [*valores, *extra]).fetchall()
    ordenadas = sorted(filas, key=lambda f: -_puntaje(f, f["r"]))
    return [_resultado(f) for f in ordenadas[:limite]]


def _resultado(f, via="nombre"):
    return {"ruta": f["ruta"], "nombre": f["nombre"], "tipo": f["tipo"], "tam": f["tam"], "mtime": f["mtime"],
            "carpeta": f["carpeta"], "via": via}


def proyectos(limite=50):
    with bd() as c:
        filas = c.execute("""SELECT p.*, (SELECT MAX(fin) FROM sesiones s WHERE s.proyecto = p.ruta) AS ultima
            FROM proyectos p ORDER BY COALESCE(ultima, 0) DESC, p.mtime DESC LIMIT ?""", (limite,)).fetchall()
    return [dict(f) for f in filas]


def areas():
    with bd() as c:
        return [dict(f) for f in c.execute("SELECT * FROM areas ORDER BY docs DESC")]


def sesiones(limite=8, proyecto=None, desde=None):
    """Las últimas sesiones resumidas; `proyecto` filtra por nombre o ruta (parcial)."""
    donde, valores = ["estado = 'hecha'"], []
    if proyecto:
        donde.append("(proyecto LIKE ? OR cwd LIKE ? OR titulo LIKE ? OR resumen LIKE ?)")
        valores += [f"%{proyecto}%"] * 4
    if desde:
        donde.append("fin >= ?")
        valores.append(desde)
    with bd() as c:
        filas = c.execute(f"SELECT * FROM sesiones WHERE {' AND '.join(donde)} ORDER BY fin DESC LIMIT ?",
                          [*valores, limite]).fetchall()
    salida = []
    for f in filas:
        s = dict(f)
        s["archivos"] = json.loads(s["archivos"] or "[]")
        s["proyecto_nombre"] = nombre_proyecto(s["proyecto"]) if s["proyecto"] else ""
        salida.append(s)
    return salida


def nombre_proyecto(ruta):
    with bd() as c:
        fila = c.execute("SELECT nombre FROM proyectos WHERE ruta=?", (ruta,)).fetchone()
    return fila[0] if fila else Path(ruta).name


def pendientes(todos=False, proyecto=None):
    donde, valores = ([] if todos else ["hecho IS NULL"]), []
    if proyecto:
        donde.append("proyecto LIKE ?")
        valores.append(f"%{proyecto}%")
    with bd() as c:
        filas = c.execute(f"SELECT * FROM pendientes {'WHERE ' + ' AND '.join(donde) if donde else ''} ORDER BY id DESC LIMIT 200",
                          valores).fetchall()
    salida = [dict(f) for f in filas]
    for p in salida:
        p["proyecto_nombre"] = nombre_proyecto(p["proyecto"]) if p["proyecto"] else ""
    return salida


def proyecto_de(ruta):
    """El proyecto (ruta) al que pertenece una carpeta (el de prefijo más largo), o None."""
    if not ruta:
        return None
    with bd() as c:
        todos = [r[0] for r in c.execute("SELECT ruta FROM proyectos")]
    candidatos = [p for p in todos if _bajo(ruta, p)]
    return max(candidatos, key=len) if candidatos else None


def buscar_proyecto(texto):
    """Ruta del proyecto que mejor coincide con un nombre («tesis», «web»…)."""
    if not texto:
        return None
    bajo = texto.lower().strip()
    lista = proyectos(500)
    for p in lista:
        if p["nombre"].lower() == bajo or p["ruta"] == texto:
            return p["ruta"]
    for p in lista:
        if bajo in p["nombre"].lower():
            return p["ruta"]
    return None


def agregar_pendiente(texto, proyecto=None, origen="usuario"):
    texto = " ".join(str(texto).split())[:400]
    if not texto:
        return None
    ruta = buscar_proyecto(proyecto) if proyecto else None
    with bd() as c:
        cur = c.execute("INSERT INTO pendientes(texto, proyecto, creado, origen) VALUES (?,?,?,?)",
                        (texto, ruta, time.time(), origen))
        ident = cur.lastrowid
    _regenerar(pendientes=True, proyecto=ruta)
    return ident


def marcar_hecho(cual, hecho=True):
    """Por número o por texto (el pendiente abierto que más se parece). Devuelve el pendiente o None."""
    with bd() as c:
        fila = None
        if str(cual).lstrip("#").isdigit():
            fila = c.execute("SELECT * FROM pendientes WHERE id=?", (int(str(cual).lstrip("#")),)).fetchone()
        else:
            for p in palabras(str(cual)) and c.execute("SELECT * FROM pendientes WHERE hecho IS NULL ORDER BY id DESC"):
                if all(w in p["texto"].lower() for w in palabras(str(cual))):
                    fila = p
                    break
        if not fila:
            return None
        c.execute("UPDATE pendientes SET hecho=? WHERE id=?", (time.time() if hecho else None, fila["id"]))
    _regenerar(pendientes=True, proyecto=fila["proyecto"])
    return dict(fila)


def anotar(texto, proyecto=None, agente="usuario"):
    texto = str(texto).strip()[:2000]
    if not texto:
        return False
    ruta = buscar_proyecto(proyecto) if proyecto else None
    with bd() as c:
        c.execute("INSERT INTO notas(t, texto, proyecto, agente) VALUES (?,?,?,?)", (time.time(), texto, ruta, agente))
    _regenerar(dia=time.strftime("%Y-%m-%d"), proyecto=ruta)
    return True


def _regenerar(**que):
    """Rehace las notas de la bóveda afectadas (si el cerebro está configurado)."""
    if not configurado():
        return
    from . import boveda as B
    try:
        B.regenerar(**que)
    except OSError as e:
        print(f"akari: bóveda: {e!r}", file=sys.stderr)


# ---------------------------------------------------------------- fechas legibles

DIAS_SEMANA = {"es": ("el lunes", "el martes", "el miércoles", "el jueves", "el viernes", "el sábado", "el domingo"),
               "en": ("on Monday", "on Tuesday", "on Wednesday", "on Thursday", "on Friday", "on Saturday", "on Sunday")}
MESES = {"es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
                "diciembre"),
         "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
                "December")}


def cuando(ts, ahora=None):
    """«hoy», «ayer», «el lunes», «el 3 de octubre»."""
    if not ts:
        return "—"
    ahora = datetime.fromtimestamp(ahora or time.time())
    dia = datetime.fromtimestamp(ts)
    dias = (ahora.date() - dia.date()).days
    if dias <= 0:
        return t("hoy", "today")
    if dias == 1:
        return t("ayer", "yesterday")
    if dias < 7:
        return DIAS_SEMANA[IDIOMA][dia.weekday()]
    return fecha_larga(dia, con_dia=True)


def fecha_larga(dia, con_dia=False):
    mes = MESES[IDIOMA][dia.month - 1]
    texto = f"{dia.day} de {mes} de {dia.year}" if IDIOMA == "es" else f"{mes} {dia.day}, {dia.year}"
    return (t("el ", "on ") + texto) if con_dia else texto


def nombre_agente(a):
    return {"claude": "Claude Code", "codex": "Codex", "akari": t("el asistente de akari", "the akari assistant")}.get(a, a or "IA")


def en_que_quedamos(proyecto=None, limite=3):
    """«Ayer trabajaste en el capítulo 3 con Claude Code; quedó pendiente la bibliografía.»"""
    lista = sesiones(limite, proyecto=proyecto)
    abiertos = pendientes(proyecto=proyecto)[:5]
    if not lista and not abiertos:
        if proyecto:
            return t(f"No tengo sesiones ni pendientes de «{proyecto}».", f"I have no sessions or to-dos for “{proyecto}”.")
        return t("Todavía no tengo sesiones guardadas.", "No sessions saved yet.")
    lineas = []
    for s in lista:
        quien = nombre_agente(s["agente"])
        donde = f" ({s['proyecto_nombre']})" if s["proyecto_nombre"] else ""
        hecho = (s["resumen"] or s["titulo"] or "").rstrip(".")
        frase = t(f"{cuando(s['fin']).capitalize()} trabajaste{donde} con {quien}: {hecho}.",
                  f"{cuando(s['fin']).capitalize()} you worked{donde} with {quien}: {hecho}.")
        if s.get("pendiente"):
            frase += t(f" Quedó pendiente: {s['pendiente'].rstrip('.')}.", f" Left to do: {s['pendiente'].rstrip('.')}.")
        lineas.append(frase)
    if abiertos:
        lineas.append(t("Pendientes: ", "To-dos: ") + "; ".join(f"#{p['id']} {p['texto']}" for p in abiertos))
    return "\n".join(lineas)


# ---------------------------------------------------------------- abrir

def abrir_archivo(ruta, carpeta=False):
    """(ok, mensaje). Solo rutas del mapa o de las carpetas elegidas; los programas, solo en su carpeta."""
    ruta = Path(str(ruta)).expanduser()
    if not ruta.exists():
        return False, t("Ese archivo ya no está ahí.", "That file is no longer there.")
    permitido = any(_bajo(ruta, c) for c in ajustes().get("carpetas", [])) or (boveda() and _bajo(ruta, boveda()))
    if not permitido:
        with bd() as c:
            permitido = c.execute("SELECT 1 FROM archivos WHERE ruta=?", (str(ruta),)).fetchone() is not None
    if not permitido:
        return False, t("Solo abro archivos de las carpetas del cerebro.", "I only open files in the brain's folders.")
    if carpeta or (ruta.is_file() and ruta.suffix.lower() in NO_ABRIR):
        return mostrar_en_carpeta(ruta), (t("Lo muestro en su carpeta (no abro programas).", "Shown in its folder (programs are not opened).")
                                          if not carpeta else "")
    return abrir(ruta), ""


def mostrar_en_carpeta(ruta):
    """Abre la carpeta con el archivo marcado (Explorador, Nautilus/Dolphin…); si no se puede, la carpeta."""
    ruta = Path(ruta)
    if WINDOWS:
        import subprocess
        try:
            subprocess.Popen(["explorer", f"/select,{ruta}"])
            return True
        except OSError:
            return abrir(ruta.parent)
    if tiene("gdbus") and ruta.exists():
        ok, _ = correr(["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1", "--object-path",
                        "/org/freedesktop/FileManager1", "--method", "org.freedesktop.FileManager1.ShowItems",
                        f"['{ruta.as_uri()}']", ""], 5)
        if ok:
            return True
    return abrir(ruta if ruta.is_dir() else ruta.parent)


# ---------------------------------------------------------------- texto de documentos

def texto_de(ruta, largo=4000):
    """Texto de un documento para buscarlo por significado (sin escribir nada junto al original)."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    try:
        if ruta.stat().st_size > 50 * 2**20:
            return ""
        if ext in (".md", ".markdown", ".txt", ".csv", ".tex"):
            with open(ruta, encoding="utf-8", errors="replace") as f:
                return f.read(largo)
        if ext in (".docx", ".pptx", ".odt", ".odp"):
            with zipfile.ZipFile(ruta) as z:
                partes = [n for n in z.namelist() if n in ("word/document.xml", "content.xml")
                          or re.match(r"ppt/slides/slide\d+\.xml$", n)]
                xml = " ".join(z.read(n).decode("utf-8", errors="replace") for n in partes[:30])
            xml = re.sub(r"</w:p>|</a:p>|</text:p>", "\n", xml)
            return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", xml)).strip()[:largo]
        if ext == ".pdf":
            from . import extras
            python = extras.python_de("documentos")
            if python:          # markitdown sin -o escribe en la salida, no junto al PDF
                ok, salida = correr([str(python), "-m", "markitdown", str(ruta)], 120)
                return salida[:largo] if ok else ""
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return ""
    return ""


# ---------------------------------------------------------------- búsqueda por significado

def prefijos(modelo):
    """Cada modelo de embeddings espera su propio prefijo para consultas y documentos."""
    m = (modelo or "").lower()
    if "embeddinggemma" in m:
        return "task: search result | query: ", "title: none | text: "
    if "nomic" in m:
        return "search_query: ", "search_document: "
    if "e5" in m:
        return "query: ", "passage: "
    return "", ""


def _vector(valores):
    v = valores[:DIMENSIONES]
    norma = sum(x * x for x in v) ** 0.5 or 1.0
    return array("f", (x / norma for x in v))


class Semantica:
    """Índice de embeddings (Ollama local) sobre áreas, proyectos, nombres de documentos, notas de la
    bóveda, sesiones y, solo en las carpetas activadas, el texto de los documentos."""

    def __init__(self):
        self.cache = None           # (modelo, [(clave, tipo, ruta, texto, vec)])
        self.trabajando = False
        self.hechos = 0
        self.faltan = 0
        self.error = ""

    @staticmethod
    def modelo(monitor_modelos=None):
        """El modelo de embeddings instalado en Ollama (el elegido en ajustes o el recomendado)."""
        from .modelos import CATALOGO_EMBED, embebedores_instalados
        instalados = embebedores_instalados(monitor_modelos)
        elegido = ajustes().get("embeddings")
        if elegido and elegido in instalados:
            return elegido
        for m in CATALOGO_EMBED:
            for inst in instalados:
                if inst == m["id"] or inst.split(":")[0] == m["id"].split(":")[0]:
                    return inst
        return instalados[0] if instalados else None

    def elementos(self):
        """Lo que hay que tener embebido: (clave, tipo, ruta, texto, firma)."""
        salida = []
        with bd() as c:
            for a in c.execute("SELECT * FROM areas"):
                salida.append((f"area:{a['ruta']}", "area", a["ruta"], f"{a['nombre']} — {a['ruta']}", str(a["docs"])))
            for p in c.execute("SELECT * FROM proyectos"):
                salida.append((f"proyecto:{p['ruta']}", "proyecto", p["ruta"],
                               f"{p['nombre']} — {p['descripcion'] or p['tipo'] or ''} — {p['ruta']}", p["descripcion"] or ""))
            for s in c.execute("SELECT * FROM sesiones WHERE estado='hecha' ORDER BY fin DESC LIMIT 2000"):
                salida.append((f"sesion:{s['id']}", "sesion", s["cwd"] or "", f"{s['titulo']} — {s['resumen'] or ''}",
                               str(s["tam"])))
            for f in c.execute("""SELECT ruta, nombre, lugar, tipo, mtime FROM archivos WHERE tipo IN
                    ('documento','hoja','presentacion','carpeta') ORDER BY mtime DESC LIMIT ?""", (MAX_VECTORES,)):
                nombre = os.path.splitext(f["nombre"])[0] if f["tipo"] != "carpeta" else f["nombre"]
                salida.append((f"archivo:{f['ruta']}", f["tipo"], f["ruta"],
                               f"{re.sub(r'[_.-]+', ' ', nombre)} — {f['lugar']}", str(int(f["mtime"] or 0))))
            activas = ajustes().get("texto_en") or []
            for carpeta in activas:
                prefijo = str(Path(carpeta)).rstrip("/\\") + os.sep
                for f in c.execute("""SELECT ruta, mtime, tam FROM archivos WHERE ruta >= ? AND ruta < ? AND ext IN
                        ('.md','.txt','.docx','.pdf','.odt','.pptx') ORDER BY mtime DESC LIMIT 3000""",
                                   (prefijo, prefijo + "\uffff")):
                    salida.append((f"texto:{f['ruta']}", "texto", f["ruta"], None, f"{int(f['mtime'] or 0)}:{f['tam']}"))
        b = boveda()
        if b and b.is_dir():
            for nota in b.rglob("*.md"):
                try:
                    info = nota.stat()
                except OSError:
                    continue
                salida.append((f"nota:{nota}", "nota", str(nota), None, f"{int(info.st_mtime)}:{info.st_size}"))
        return salida

    def actualizar(self, monitor_modelos=None, tope=400):
        """Embebe lo nuevo o cambiado (hasta `tope` por llamada, para no ocupar el equipo de golpe)."""
        from .modelos import embeber
        modelo = self.modelo(monitor_modelos)
        if not modelo or self.trabajando:
            return False
        self.trabajando = True
        try:
            todos = self.elementos()
            with bd() as c:
                hechos = {r["clave"]: (r["firma"], r["modelo"]) for r in c.execute("SELECT clave, firma, modelo FROM vectores")}
                vigentes = {e[0] for e in todos}
                viejos = [k for k in hechos if k not in vigentes]
                c.executemany("DELETE FROM vectores WHERE clave=?", [(k,) for k in viejos])
            faltan = [e for e in todos if hechos.get(e[0]) != (e[4], modelo)]
            self.faltan = len(faltan)
            _, doc = prefijos(modelo)
            cambio = bool(viejos)
            for i in range(0, min(len(faltan), tope), 32):
                lote = []
                for clave, tipo, ruta, texto, firma in faltan[i:i + 32]:
                    if texto is None:            # notas y documentos: su texto
                        texto = texto_de(ruta, 1500)
                        if tipo == "texto":
                            texto = f"{Path(ruta).stem} — {texto}" if texto else ""
                    if texto and texto.strip():
                        lote.append((clave, tipo, ruta, texto.strip()[:1500], firma))
                if not lote:
                    continue
                vectores = embeber([doc + x[3] for x in lote], modelo)
                with bd() as c:
                    c.executemany("INSERT OR REPLACE INTO vectores(clave, tipo, ruta, texto, firma, modelo, vec) VALUES (?,?,?,?,?,?,?)",
                                  [(x[0], x[1], x[2], x[3][:300], x[4], modelo, _vector(v).tobytes()) for x, v in zip(lote, vectores)])
                self.hechos += len(lote)
                self.faltan = max(0, self.faltan - 32)
                cambio = True
            if cambio:
                self.cache = None
            self.error = ""
            return cambio
        except (OSError, ValueError) as e:
            self.error = str(e)[:200]
            return False
        finally:
            self.trabajando = False

    def _cargar(self, modelo):
        if self.cache and self.cache[0] == modelo:
            return self.cache[1]
        filas = []
        with bd() as c:
            for r in c.execute("SELECT clave, tipo, ruta, texto, vec FROM vectores WHERE modelo=?", (modelo,)):
                v = array("f")
                v.frombytes(r["vec"])
                filas.append((r["clave"], r["tipo"], r["ruta"], r["texto"], v))
        self.cache = (modelo, filas)
        return filas

    def buscar(self, consulta, limite=8, monitor_modelos=None):
        from .modelos import embeber
        modelo = self.modelo(monitor_modelos)
        if not modelo:
            return []
        pregunta, _ = prefijos(modelo)
        try:
            q = _vector(embeber([pregunta + consulta], modelo)[0])
        except (OSError, ValueError, IndexError):
            return []
        filas = self._cargar(modelo)
        puntos = [(sum(map(operator.mul, v, q)), clave, tipo, ruta, texto) for clave, tipo, ruta, texto, v in filas]
        puntos.sort(reverse=True)
        salida, vistos = [], set()
        for p, clave, tipo, ruta, texto in puntos:
            if ruta in vistos or p < 0.25:
                continue
            vistos.add(ruta)
            salida.append({"ruta": ruta, "nombre": Path(ruta).name or ruta, "tipo": tipo, "puntos": round(p, 3),
                           "texto": texto, "via": "significado", "clave": clave})
            if len(salida) >= limite:
                break
        return salida

    def estado(self, monitor_modelos=None):
        modelo = self.modelo(monitor_modelos)
        try:
            with bd() as c:
                n = c.execute("SELECT COUNT(*) FROM vectores WHERE modelo=?", (modelo or "",)).fetchone()[0]
        except sqlite3.Error:
            n = 0
        return {"modelo": modelo, "listo": bool(modelo) and n > 0, "vectores": n, "trabajando": self.trabajando,
                "faltan": self.faltan, "error": self.error, "texto_en": ajustes().get("texto_en") or []}


SEMANTICA = Semantica()


def buscar_todo(consulta, limite=10, monitor_modelos=None):
    """Por nombre y por significado, juntos y sin repetir."""
    por_nombre = buscar(consulta, limite)
    por_significado = SEMANTICA.buscar(consulta, limite, monitor_modelos)
    salida, vistos = [], set()
    # se intercalan: el mejor por nombre, el mejor por significado…
    for par in zip(por_nombre + [None] * limite, por_significado + [None] * limite):
        for r in par:
            if r and r["ruta"] not in vistos:
                vistos.add(r["ruta"])
                salida.append(r)
    return salida[:limite]


# ---------------------------------------------------------------- pregunta (el modelo decide qué buscar)

def puede_usar_ia(monitor_modelos):
    """(sí/no, motivo): hay modelo y, si es por API, el usuario permitió mandarle nombres y rutas."""
    if monitor_modelos is None:
        return False, ""
    camino, motivo = monitor_modelos.elegido()
    if camino is None:
        return False, motivo
    if camino != "ollama" and not ajustes().get("permitir_api"):
        return False, t("El modelo por API no tiene permiso para ver nombres de archivos (Cerebro → Privacidad).",
                        "The API model may not see file names (Brain → Privacy).")
    return True, ""


def _json_de(texto):
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def pregunta(texto, monitor_modelos=None):
    """Responde «¿dónde dejé…?», «¿en qué nos quedamos con…?»: el modelo de chat elige qué buscar, se
    busca en el equipo y responde con lo mínimo encontrado. Sin modelo, devuelve lo encontrado."""
    from .modelos import ErrorIA, preguntar
    texto = str(texto).strip()[:600]
    ia, _ = puede_usar_ia(monitor_modelos)
    plan = {}
    if ia:
        try:
            plan = _json_de(preguntar(monitor_modelos, texto, sistema=(
                "Decides qué buscar en el índice de archivos y sesiones de una persona. Responde solo JSON: "
                '{"buscar": ["2-4 palabras clave de nombres de archivo o carpeta"], "proyecto": "nombre o vacío", '
                '"sesiones": true si pregunta en qué se quedó o qué hizo}'), timeout=60))
        except ErrorIA:
            ia = False
    terminos = [str(x)[:60] for x in (plan.get("buscar") or []) if str(x).strip()][:4] or [texto]
    hallados, vistos = [], set()
    for termino in terminos:
        for r in buscar_todo(termino, 6, monitor_modelos):
            if r["ruta"] not in vistos:
                vistos.add(r["ruta"])
                hallados.append(r)
    quiere_sesiones = bool(plan.get("sesiones")) or bool(re.search(
        r"qued|hicimos|hice|trabaj|pendiente|where (did )?we|left off|last time|working on", texto.lower()))
    proyecto = str(plan.get("proyecto") or "").strip() or None
    memoria = en_que_quedamos(proyecto) if quiere_sesiones else ""
    if quiere_sesiones and proyecto and memoria.startswith(t("No tengo", "I have no")):
        memoria = en_que_quedamos()
    lineas = [f"- {r['ruta']}" + (f" ({_fecha_corta(r['mtime'])})" if r.get("mtime") else "") for r in hallados[:10]]
    if not ia:
        partes = []
        if memoria:
            partes.append(memoria)
        if lineas:
            partes.append(t("Encontré:", "Found:") + "\n" + "\n".join(lineas[:6]))
        return "\n\n".join(partes) or t("No encontré nada parecido en el cerebro.", "Nothing similar in the brain.")
    contexto = (t("Archivos encontrados:\n", "Files found:\n") + ("\n".join(lineas) or "-")) + \
        ("\n\n" + t("Sesiones y pendientes:\n", "Sessions and to-dos:\n") + memoria if memoria else "")
    try:
        return preguntar(monitor_modelos, f"{texto}\n\n{contexto}", sistema=t(
            "Eres el cerebro de akari: conoces el mapa de archivos y las sesiones de trabajo de esta persona. Responde "
            "en español, corto y cercano, con la ruta exacta cuando la sepas. Usa solo los datos que te doy; si no "
            "están, dilo.",
            "You are akari's brain: you know this person's file map and work sessions. Answer in English, short and "
            "friendly, with the exact path when you know it. Use only the data given; if it's not there, say so."),
            timeout=90)
    except ErrorIA as e:
        return f"{contexto}\n\n({e})"


def _fecha_corta(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""


# ---------------------------------------------------------------- herramientas del asistente

HERRAMIENTAS = [
    {"nombre": "buscar_archivo",
     "descripcion": t("Busca archivos y carpetas del usuario por nombre y por significado en el mapa de su computadora.",
                      "Finds the user's files and folders by name and meaning in the map of their computer."),
     "parametros": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]}},
    {"nombre": "abrir_archivo",
     "descripcion": t("Abre un archivo del mapa con su programa (o lo muestra en su carpeta con carpeta=true).",
                      "Opens a file from the map with its app (or shows it in its folder with carpeta=true)."),
     "parametros": {"type": "object", "properties": {"ruta": {"type": "string"}, "carpeta": {"type": "boolean"}},
                    "required": ["ruta"]}},
    {"nombre": "en_que_quedamos",
     "descripcion": t("Últimas sesiones de trabajo con IA (qué se hizo, qué quedó pendiente), de un proyecto o de todo.",
                      "Latest AI work sessions (what was done, what is left), for a project or everything."),
     "parametros": {"type": "object", "properties": {"proyecto": {"type": "string"}}}},
    {"nombre": "anotar",
     "descripcion": t("Guarda una nota en la bitácora de hoy del cerebro.", "Saves a note in today's brain log."),
     "parametros": {"type": "object", "properties": {"texto": {"type": "string"}, "proyecto": {"type": "string"}},
                    "required": ["texto"]}},
    {"nombre": "pendientes",
     "descripcion": t("Lista, agrega o marca como hechos los pendientes del usuario.", "Lists, adds or completes the user's to-dos."),
     "parametros": {"type": "object", "properties": {"accion": {"type": "string", "enum": ["listar", "agregar", "hecho"]},
                                                     "texto": {"type": "string"}, "proyecto": {"type": "string"}}}},
]


def usar_herramienta(nombre, args, monitor_modelos=None):
    """Lo que devuelve cada herramienta: texto corto (para gastar pocos tokens)."""
    args = args if isinstance(args, dict) else {}
    if not configurado():
        return t("El cerebro todavía no está creado (akari → Archivos → Cerebro).",
                 "The brain isn't set up yet (akari → Files → Brain).")
    if nombre == "buscar_archivo":
        r = buscar_todo(str(args.get("consulta") or ""), 8, monitor_modelos)
        return "\n".join(linea_resultado(x) for x in r) or t("Nada con ese nombre.", "Nothing by that name.")
    if nombre == "abrir_archivo":
        ok, mensaje = abrir_archivo(args.get("ruta") or "", bool(args.get("carpeta")))
        return mensaje or (t("Abierto.", "Opened.") if ok else t("No se pudo abrir.", "Couldn't open it."))
    if nombre == "en_que_quedamos":
        return en_que_quedamos(args.get("proyecto") or None)
    if nombre == "anotar":
        return t("Anotado.", "Noted.") if anotar(args.get("texto") or "", args.get("proyecto"), "akari") else "?"
    if nombre == "pendientes":
        accion = args.get("accion") or "listar"
        if accion == "agregar":
            ident = agregar_pendiente(args.get("texto") or "", args.get("proyecto"), "akari")
            return t(f"Pendiente #{ident} guardado.", f"To-do #{ident} saved.") if ident else "?"
        if accion == "hecho":
            p = marcar_hecho(args.get("texto") or "")
            return t(f"Hecho: {p['texto']}", f"Done: {p['texto']}") if p else t("No encontré ese pendiente.", "To-do not found.")
        lista = pendientes(proyecto=args.get("proyecto"))
        return "\n".join(f"#{p['id']} {p['texto']}" + (f" ({p['proyecto_nombre']})" if p["proyecto_nombre"] else "")
                         for p in lista[:20]) or t("Sin pendientes.", "No to-dos.")
    return "?"


def linea_resultado(r):
    detalle = [t(*NOMBRE_TIPO.get(r["tipo"], NOMBRE_TIPO["otro"]))] if r["tipo"] in NOMBRE_TIPO else [r["tipo"]]
    if r.get("mtime"):
        detalle.append(_fecha_corta(r["mtime"]))
    if r.get("via") == "significado":
        detalle.append("~")
    return f"{r['ruta']}  ({', '.join(detalle)})"


# ---------------------------------------------------------------- selector de carpeta

def elegir_carpeta(titulo):
    """Selector nativo de carpetas; la ruta elegida o "" (None si no hay selector)."""
    if WINDOWS:
        from .comun import powershell
        script = ("Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                  "$d.Description = $env:AKARI_TITULO; [Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                  "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }")
        salida = powershell(script, 3600, {**os.environ, "AKARI_TITULO": titulo})
        return (salida or "").strip()
    kde = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if tiene("kdialog") and (kde or not tiene("zenity")):
        orden = ["kdialog", "--title", titulo, "--getexistingdirectory", str(HOME)]
    elif tiene("zenity"):
        orden = ["zenity", "--file-selection", "--directory", f"--title={titulo}", f"--filename={HOME}/"]
    else:
        return None
    ok, salida = correr(orden, 3600)
    return salida.strip().splitlines()[-1] if ok and salida.strip() else ""


# ---------------------------------------------------------------- Obsidian

def obsidian_instalado():
    if WINDOWS:
        local = Path(os.environ.get("LOCALAPPDATA") or HOME)
        if (local / "Programs" / "Obsidian" / "Obsidian.exe").exists() or (local / "Obsidian" / "Obsidian.exe").exists():
            return True
        try:
            import winreg
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\obsidian"))
            return True
        except OSError:
            return False
    if tiene("obsidian") or Path("/snap/bin/obsidian").exists():
        return True
    for base in (Path("/var/lib/flatpak/app"), HOME / ".local" / "share" / "flatpak" / "app"):
        if (base / "md.obsidian.Obsidian").exists():
            return True
    if tiene("xdg-mime"):
        ok, salida = correr(["xdg-mime", "query", "default", "x-scheme-handler/obsidian"], 5)
        return ok and bool(salida.strip())
    return False


def abrir_obsidian():
    b = boveda()
    if not b:
        return False, t("Primero crea tu cerebro.", "Create your brain first.")
    if not obsidian_instalado():
        return False, t("Obsidian no está instalado.", "Obsidian isn't installed.")
    from urllib.parse import quote
    abrir(f"obsidian://open?path={quote(str(b / 'Inicio.md'), safe='')}")
    return True, t(f"Si Obsidian no la abre: «Abrir carpeta como bóveda» → {b}",
                   f"If Obsidian doesn't open it: “Open folder as vault” → {b}")


def instalar_obsidian():
    if WINDOWS and tiene("winget"):
        ok, salida = correr(["winget", "install", "-e", "--id", "Obsidian.Obsidian", "--silent",
                             "--accept-package-agreements", "--accept-source-agreements"], 900)
        return ok, "" if ok else salida[-300:]
    if not WINDOWS and tiene("flatpak"):
        ok, _ = correr(["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", "md.obsidian.Obsidian"], 900)
        if ok:
            return True, t("Obsidian instalado.", "Obsidian installed.")
    abrir("https://obsidian.md/download")
    return True, t("Se abrió la página de descarga de Obsidian.", "Opened the Obsidian download page.")


# ---------------------------------------------------------------- configurar y olvidar

def configurar(carpetas, elegida=None, texto_en=None, permitir_api=None):
    """Guarda qué recorrer y dónde va la bóveda. Devuelve (ok, mensaje)."""
    limpias = []
    for c in carpetas or []:
        ruta = Path(str(c)).expanduser()
        if ruta.is_dir() and str(ruta) not in limpias:
            limpias.append(str(ruta))
    if not limpias:
        return False, t("Elige al menos una carpeta que exista.", "Choose at least one existing folder.")
    a = ajustes()
    if elegida or not a.get("boveda"):
        destino = boveda_para(elegida or HOME / "Cerebro")
        if str(destino) in limpias:
            return False, t("La bóveda no puede ser una de las carpetas a recorrer.", "The vault can't be a folder to scan.")
        a["boveda"] = str(destino)
    a["carpetas"] = limpias
    if texto_en is not None:
        a["texto_en"] = [str(Path(x)) for x in texto_en if Path(str(x)).is_dir()]
    if permitir_api is not None:
        a["permitir_api"] = bool(permitir_api)
    a.setdefault("creado", time.time())
    guardar_ajustes(a)
    raiz = Path(a["boveda"])
    raiz.mkdir(parents=True, exist_ok=True)
    marca = raiz / ".akari-cerebro"
    if not marca.exists():
        marca.write_text("akari\n", encoding="utf-8")
    return True, ""


def olvidar():
    """Borra el índice de akari (no la bóveda: puede tener notas del usuario). Devuelve la ruta de la bóveda."""
    b = boveda()
    for sufijo in ("", "-wal", "-shm"):
        try:
            Path(str(BD) + sufijo).unlink()
        except OSError:
            pass
    try:
        AJUSTES.unlink()
    except OSError:
        pass
    return b


def revisar(al_avanzar=None):
    """Una revisión completa (incremental) y la bóveda al día. Devuelve la Revision."""
    with _cerrojo:
        a = ajustes()
        rev = Revision(al_avanzar).correr(a.get("carpetas", []))
        from . import boveda as B
        B.regenerar(todo=True)
        return rev


def toca_revision_nocturna(ultima, ahora=None):
    ahora = datetime.fromtimestamp(ahora or time.time())
    if not ultima:
        return True
    hace = ahora - datetime.fromtimestamp(ultima)
    return (HORA_NOCHE[0] <= ahora.hour < HORA_NOCHE[1] and hace > timedelta(hours=20)) or hace > timedelta(hours=30)


# ---------------------------------------------------------------- monitor (servicio)

class MonitorCerebro:
    """Lo que hace el servicio: revisión al arrancar y cada noche, memoria de sesiones cada 2 min,
    embeddings en segundo plano y el estado para la cápsula y el panel."""

    def __init__(self, al_cambiar, modelos):
        from . import boveda as B
        B._MODELOS["monitor"] = modelos
        self.al_cambiar = al_cambiar
        self.modelos = modelos
        self.revisando = False
        self.progreso = None
        self.arrancado = False
        self.ultima_memoria = 0
        self.memoria_ya = False
        self.eligiendo = False
        self.mensaje = ""
        self.estado = {}
        self._ultimo = None
        self.calcular()

    def paso(self):
        if configurado():
            with bd() as c:
                ultima = meta(c, "ultima_revision")
            if not self.revisando and (not self.arrancado or toca_revision_nocturna(ultima)):
                self.arrancado = True
                self.revisar()
            if not self.revisando and (self.memoria_ya or time.time() - self.ultima_memoria > 120):
                from . import memoria
                self.memoria_ya, self.ultima_memoria = False, time.time()
                if memoria.procesar(self.modelos):
                    self.calcular()
            if not self.revisando:
                self.describir_proyectos()
                if SEMANTICA.actualizar(self.modelos, tope=200):
                    self.calcular()
        self.calcular()

    def revisar(self):
        if self.revisando or not configurado():
            return False
        self.revisando = True
        self.progreso = {"archivos": 0, "carpeta": ""}
        self.calcular()

        def trabajo():
            try:
                revisar(self._avance)
                self.mensaje = ""
            except (OSError, sqlite3.Error) as e:
                self.mensaje = str(e)[:200]
                print(f"akari: cerebro: {e!r}", file=sys.stderr, flush=True)
            finally:
                self.revisando = False
                self.progreso = None
                self.calcular()
        threading.Thread(target=trabajo, daemon=True).start()
        return True

    def _avance(self, rev):
        self.progreso = {"archivos": rev.archivos, "carpeta": rev.carpeta}
        self.calcular()

    def describir_proyectos(self, tope=3):
        """«De qué trata» con la IA para los proyectos sin README (unos pocos por vuelta)."""
        ia, _ = puede_usar_ia(self.modelos)
        if not ia:
            return
        from .modelos import ErrorIA, preguntar
        with bd() as c:
            sin = c.execute("""SELECT ruta, nombre FROM proyectos WHERE COALESCE(descripcion, '') = '' AND origen='mapa'
                LIMIT ?""", (tope,)).fetchall()
            listas = {p["ruta"]: [r[0] for r in c.execute("SELECT nombre FROM archivos WHERE carpeta=? ORDER BY tipo LIMIT 40",
                                                          (p["ruta"],))] for p in sin}
        for p in sin:
            try:
                d = preguntar(self.modelos, f"{p['nombre']}: " + ", ".join(listas[p["ruta"]]), sistema=t(
                    "Con solo estos nombres de archivo, di en una frase corta en español de qué trata el proyecto. Sin adornos.",
                    "From these file names only, say in one short English sentence what the project is about. Plain."),
                    timeout=60)
            except ErrorIA:
                return
            d = " ".join(d.split())[:240] or "—"
            with bd() as c:
                c.execute("UPDATE proyectos SET descripcion=? WHERE ruta=?", (d, p["ruta"]))
            _regenerar(proyecto=p["ruta"], inicio=False)

    def calcular(self):
        a = ajustes()
        listo = configurado()
        try:
            cif = cifras() if listo else {}
        except sqlite3.Error:
            cif = {}
        from . import ganchos
        ultima = cif.get("ultima_revision")
        salud = ("configurar" if not listo else "revisando" if self.revisando
                 else "atencion" if self.mensaje or not ultima or time.time() - ultima > 3 * 86400 else "sano")
        camino = self.modelos.elegido()[0] if self.modelos else None
        estado = {
            "configurado": listo, "salud": salud, "mensaje": self.mensaje,
            "boveda": a.get("boveda") or str(boveda_para(HOME / "Cerebro")),
            "carpetas": a.get("carpetas") or [], "texto_en": a.get("texto_en") or [],
            "permitir_api": bool(a.get("permitir_api")), "modelo_api": bool(camino and camino != "ollama"),
            "candidatas": carpetas_candidatas(), "excluido": [t(*x) for x in EXCLUIDO_TEXTO],
            "cifras": cif, "progreso": dict(self.progreso) if self.progreso else None, "eligiendo": self.eligiendo,
            "conectado": ganchos.estado(), "obsidian": obsidian_instalado() if listo else False,
            "semantica": SEMANTICA.estado(self.modelos) if listo else {},
            "sesiones": [{k: s[k] for k in ("id", "agente", "fin", "titulo", "resumen", "pendiente", "proyecto_nombre")}
                         for s in sesiones(5)] if listo else [],
            "pendientes": [{k: p[k] for k in ("id", "texto", "proyecto_nombre")} for p in pendientes()[:8]] if listo else [],
        }
        if estado != self._ultimo:
            self._ultimo = estado
            self.estado = estado
            self.al_cambiar()

    # ------------------------------------------------------------ acciones (POST /api/cerebro)
    def accion(self, d):
        accion = str(d.get("accion"))
        if accion == "configurar":
            ok, mensaje = configurar(d.get("carpetas") if isinstance(d.get("carpetas"), list) else ajustes().get("carpetas"),
                                     d.get("boveda") or None, d.get("texto_en") if isinstance(d.get("texto_en"), list) else None,
                                     d.get("permitir_api") if isinstance(d.get("permitir_api"), bool) else None)
            if ok:
                self.revisar()
            self.calcular()
            return {"ok": ok, "mensaje": mensaje}
        if accion == "memoria":                 # aviso del gancho SessionEnd
            self.memoria_ya = True
            return {"ok": True}
        if not configurado() and accion not in ("elegir", "obsidian_instalar"):
            return {"ok": False, "mensaje": t("Primero crea tu cerebro.", "Create your brain first.")}
        if accion == "revisar":
            return {"ok": self.revisar(), "mensaje": "" if not self.revisando else t("Revisando…", "Checking…")}
        if accion == "buscar":
            q = str(d.get("q") or "")[:200]
            registrar_uso("panel")
            return {"ok": True, "resultados": buscar_todo(q, 12, self.modelos) if q.strip() else []}
        if accion == "pregunta":
            registrar_uso("panel")
            return {"ok": True, "respuesta": pregunta(str(d.get("texto") or ""), self.modelos)}
        if accion == "abrir":
            ok, mensaje = abrir_archivo(str(d.get("ruta") or ""), bool(d.get("carpeta")))
            return {"ok": ok, "mensaje": mensaje}
        if accion == "en_que_quedamos":
            return {"ok": True, "texto": en_que_quedamos(d.get("proyecto") or None)}
        if accion == "pendiente":
            ident = agregar_pendiente(str(d.get("texto") or ""), d.get("proyecto") or None)
            self.calcular()
            return {"ok": bool(ident), "id": ident}
        if accion == "hecho":
            p = marcar_hecho(d.get("id"), d.get("hecho") is not False)
            self.calcular()
            return {"ok": bool(p)}
        if accion == "nota":
            ok = anotar(str(d.get("texto") or ""), d.get("proyecto") or None)
            return {"ok": ok}
        if accion == "obsidian":
            ok, mensaje = abrir_obsidian()
            return {"ok": ok, "mensaje": mensaje, "instalar": not obsidian_instalado()}
        if accion == "obsidian_instalar":
            ok, mensaje = instalar_obsidian()
            self.calcular()
            return {"ok": ok, "mensaje": mensaje}
        if accion == "carpeta_boveda":
            return {"ok": abrir(boveda())}
        if accion in ("conectar", "desconectar"):
            from . import ganchos
            agente = d.get("agente") if d.get("agente") in ("claude", "codex") else "todos"
            mensaje = (ganchos.conectar if accion == "conectar" else ganchos.desconectar)(agente)
            self.calcular()
            return {"ok": True, "mensaje": mensaje}
        if accion == "elegir":                  # selector nativo: carpeta a recorrer, a leer o para la bóveda
            para = d.get("para") if d.get("para") in ("mapa", "texto", "boveda") else "mapa"
            threading.Thread(target=self._elegir, args=(para,), daemon=True).start()
            return {"ok": True}
        if accion == "quitar":
            ruta = str(d.get("ruta") or "")
            a = ajustes()
            a["carpetas"] = [x for x in a.get("carpetas", []) if x != ruta] or a.get("carpetas", [])
            a["texto_en"] = [x for x in a.get("texto_en", []) if x != ruta]
            guardar_ajustes(a)
            self.revisar()
            return {"ok": True}
        if accion == "olvidar":
            b = olvidar()
            self.calcular()
            return {"ok": True, "mensaje": t(f"Índice borrado. La bóveda sigue en {b} (bórrala tú si quieres).",
                                             f"Index deleted. The vault is still at {b} (delete it yourself if you want).")}
        return {"ok": False, "mensaje": "?"}

    def _elegir(self, para):
        if self.eligiendo:
            return
        self.eligiendo = True
        self.calcular()
        try:
            titulo = {"mapa": t("Carpeta para el cerebro", "Folder for the brain"),
                      "texto": t("Carpeta cuyo texto puede leer el cerebro", "Folder whose text the brain may read"),
                      "boveda": t("Dónde guardar la bóveda", "Where to keep the vault")}[para]
            ruta = elegir_carpeta(titulo)
            if ruta is None:
                self.mensaje = t("No hay selector de carpetas: instala zenity o kdialog.", "No folder picker: install zenity or kdialog.")
            elif ruta:
                a = ajustes()
                if para == "boveda":
                    configurar(a.get("carpetas") or [str(HOME)], ruta)
                elif para == "texto":
                    a["texto_en"] = sorted(set(a.get("texto_en", [])) | {ruta})
                    guardar_ajustes(a)
                else:
                    configurar(sorted(set(a.get("carpetas", [])) | {ruta}))
                if para != "texto":
                    self.revisar()
        finally:
            self.eligiendo = False
            self.calcular()


# ---------------------------------------------------------------- servidor MCP (opcional)

def servidor_mcp():
    """`akari cerebro mcp`: las herramientas del cerebro por MCP (stdio). Para Claude Code:
    claude mcp add akari-cerebro -- akari cerebro mcp"""
    from . import VERSION
    monitor = None
    for linea in sys.stdin:
        try:
            msg = json.loads(linea)
        except ValueError:
            continue
        metodo, ident, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        error = None
        if metodo == "initialize":
            res = {"protocolVersion": params.get("protocolVersion") or "2025-06-18", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "akari-cerebro", "version": VERSION}}
        elif metodo == "tools/list":
            res = {"tools": [{"name": h["nombre"], "description": h["descripcion"], "inputSchema": h["parametros"]}
                             for h in HERRAMIENTAS]}
        elif metodo == "tools/call":
            registrar_uso(quien_llama() if quien_llama() != "terminal" else "mcp")
            res = {"content": [{"type": "text", "text": usar_herramienta(params.get("name"), params.get("arguments"), monitor)}]}
        elif metodo == "ping":
            res = {}
        elif ident is None:
            continue                    # notificaciones (initialized, cancelled…)
        else:
            res, error = None, {"code": -32601, "message": f"method not found: {metodo}"}
        respuesta = {"jsonrpc": "2.0", "id": ident}
        respuesta.update({"error": error} if error else {"result": res})
        sys.stdout.write(json.dumps(respuesta, ensure_ascii=False) + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------- orden `akari cerebro`

AYUDA = t("""akari cerebro: el mapa de tu computadora y la memoria de tus sesiones con IA.
(nunca mueve, renombra ni cambia tus archivos)

  buscar <palabras>       archivos y carpetas por nombre y significado
  donde <nombre>          la ruta más probable
  pregunta <texto>        pregunta libre («¿dónde dejé el informe de la tesis?»)
  sesiones [proyecto]     últimas sesiones con Claude Code, Codex y el asistente
  proyectos               proyectos que conoce
  pendientes [proyecto]   lo que quedó por hacer
  pendiente <texto>       agrega uno   (--proyecto <nombre>)
  hecho <número|texto>    marca uno como hecho
  nota <texto>            anota en la bitácora de hoy   (--proyecto <nombre>)
  abrir <ruta>            abre un archivo del mapa   (--carpeta: lo muestra en su carpeta)
  estado                  cuántos archivos y proyectos conoce, última revisión
  revisar                 revisa las carpetas ahora
  conectar [claude|codex] / desconectar   ganchos de Claude Code y AGENTS.md de Codex
  mcp                     servidor MCP (stdio) con las mismas herramientas""",
          """akari cerebro: the map of your computer and the memory of your AI sessions.
(never moves, renames or changes your files)

  buscar <words>          files and folders by name and meaning
  donde <name>            the most likely path
  pregunta <text>         free question (“where did I leave the thesis report?”)
  sesiones [project]      latest sessions with Claude Code, Codex and the assistant
  proyectos               known projects
  pendientes [project]    what is left to do
  pendiente <text>        add one   (--proyecto <name>)
  hecho <number|text>     mark one as done
  nota <text>             note in today's log   (--proyecto <name>)
  abrir <path>            open a file from the map   (--carpeta: show it in its folder)
  estado                  how many files and projects it knows, last check
  revisar                 check the folders now
  conectar [claude|codex] / desconectar   Claude Code hooks and Codex AGENTS.md
  mcp                     MCP server (stdio) with the same tools""")


def _opcion(args, nombre):
    if nombre in args:
        i = args.index(nombre)
        valor = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
        return valor
    return None


def _monitor_modelos():
    from .modelos import MonitorModelos
    m = MonitorModelos(lambda: None)
    m.leer_ollama()
    m.calcular()
    return m


def main(args):
    args = list(args)
    orden = args.pop(0) if args else "ayuda"
    if orden == "sesion-inicio":
        from . import ganchos
        return ganchos.sesion_inicio() or 0
    if orden == "sesion-fin":
        from . import ganchos
        return ganchos.sesion_fin() or 0
    if orden in ("ayuda", "help", "-h", "--help"):
        print(AYUDA)
        return 0
    if orden == "mcp":
        servidor_mcp()
        return 0
    if orden in ("conectar", "desconectar"):
        from . import ganchos
        agente = args[0] if args and args[0] in ("claude", "codex") else "todos"
        print((ganchos.conectar if orden == "conectar" else ganchos.desconectar)(agente))
        return 0
    if not configurado():
        print(t("El cerebro todavía no está creado: ábrelo en akari (Archivos → Cerebro).",
                "The brain isn't set up yet: open it in akari (Files → Brain)."))
        return 1
    registrar_uso(quien_llama())
    proyecto = _opcion(args, "--proyecto")
    carpeta = "--carpeta" in args
    args = [a for a in args if a != "--carpeta"]
    texto = " ".join(args).strip()
    if orden == "buscar":
        if not texto:
            print(t("Uso: akari cerebro buscar <palabras>", "Usage: akari cerebro buscar <words>"))
            return 2
        resultados = buscar_todo(texto, 10)
        print("\n".join(linea_resultado(r) for r in resultados) or t("Nada con ese nombre.", "Nothing by that name."))
        return 0 if resultados else 1
    if orden == "donde":
        r = buscar(texto, 1) or SEMANTICA.buscar(texto, 1)
        print(r[0]["ruta"] if r else t("No lo encontré.", "Not found."))
        return 0 if r else 1
    if orden == "pregunta":
        print(pregunta(texto, _monitor_modelos()))
        return 0
    if orden == "sesiones":
        lista = sesiones(8, proyecto=texto or proyecto)
        for s in lista:
            dia = datetime.fromtimestamp(s["fin"]).strftime("%Y-%m-%d %H:%M")
            linea = f"{dia} · {nombre_agente(s['agente'])} · {s['proyecto_nombre'] or '-'} · {s['resumen'] or s['titulo']}"
            print(linea + (f" · {t('pendiente', 'to do')}: {s['pendiente']}" if s["pendiente"] else ""))
        if not lista:
            print(t("Sin sesiones todavía.", "No sessions yet."))
        return 0
    if orden == "proyectos":
        for p in proyectos(40):
            print(f"{p['nombre']}  {p['ruta']}" + (f"  ({t('última sesión', 'last session')} {cuando(p['ultima'])})" if p.get("ultima") else ""))
        return 0
    if orden == "pendientes":
        lista = pendientes(proyecto=texto or proyecto)
        print("\n".join(f"#{p['id']} {p['texto']}" + (f" ({p['proyecto_nombre']})" if p["proyecto_nombre"] else "")
                        for p in lista) or t("Sin pendientes.", "No to-dos."))
        return 0
    if orden == "pendiente":
        ident = agregar_pendiente(texto, proyecto, quien_llama())
        print(t(f"Pendiente #{ident} guardado.", f"To-do #{ident} saved.") if ident else "?")
        return 0 if ident else 2
    if orden == "hecho":
        p = marcar_hecho(texto)
        print(t(f"Hecho: {p['texto']}", f"Done: {p['texto']}") if p else t("No encontré ese pendiente.", "To-do not found."))
        return 0 if p else 1
    if orden == "nota":
        ok = anotar(texto, proyecto, quien_llama())
        print(t("Anotado en la bitácora de hoy.", "Noted in today's log.") if ok else "?")
        return 0 if ok else 2
    if orden == "abrir":
        ok, mensaje = abrir_archivo(texto, carpeta)
        print(mensaje or (t("Abierto.", "Opened.") if ok else t("No se pudo abrir.", "Couldn't open it.")))
        return 0 if ok else 1
    if orden == "estado":
        c = cifras()
        sem = SEMANTICA.estado()
        print(t(f"{c['archivos']:,} archivos · {c['carpetas']:,} carpetas · {c['proyectos']} proyectos · {c['areas']} áreas",
                f"{c['archivos']:,} files · {c['carpetas']:,} folders · {c['proyectos']} projects · {c['areas']} areas"))
        print(t(f"Última revisión: {_fecha_corta(c['ultima_revision']) or '—'} · sesiones hoy: {c['sesiones_hoy']} · "
                f"pendientes: {c['pendientes']}", f"Last check: {_fecha_corta(c['ultima_revision']) or '—'} · sessions today: "
                f"{c['sesiones_hoy']} · to-dos: {c['pendientes']}"))
        print(t("Por significado: ", "By meaning: ") + (f"{sem['modelo']} · {sem['vectores']}" if sem["modelo"] else t("sin modelo de embeddings", "no embeddings model")))
        print(t("Bóveda: ", "Vault: ") + str(boveda()))
        return 0
    if orden == "revisar":
        rev = revisar()
        print(t(f"Listo: {rev.archivos:,} entradas, {len(rev.proyectos)} proyectos.", f"Done: {rev.archivos:,} entries, {len(rev.proyectos)} projects."))
        return 0
    print(AYUDA)
    return 2
