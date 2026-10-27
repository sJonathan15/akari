//! akari para Windows: las mismas burbujas flotantes que en Linux, con WebView2 (ya viene en
//! Windows 10/11) en lugar de Electron. Hay una burbuja por grupo (AGENTS.md: Equipo, IA,
//! Archivos) y la lista de grupos y piezas la da el servicio (GET /api/burbujas).
//!  * Cerrado, cada grupo es una píldora nativa con un chip por pieza (cerradas.rs): sin
//!    navegador, casi sin memoria.
//!  * Al pasar el ratón se abre una ventana transparente, sin marco, siempre visible y fuera de
//!    la barra de tareas con la página del servicio (?vista=burbuja&c=…) en la pieza que estaba
//!    debajo; al cerrar se esconde y al minuto se destruye.
//!
//! Esta app solo maneja las ventanas, la bandeja y el servicio de Python.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
// fuera de Windows (solo para desarrollar) las píldoras nativas no se usan
#![cfg_attr(not(windows), allow(dead_code))]

mod cabecera;
mod cerradas;
mod forma;
mod iconos;
#[cfg(windows)]
mod nativo;
mod servicio;
#[cfg(windows)]
mod sistema;

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::PathBuf;
use std::process::Child;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use forma::{Burbuja, Medidas, Posicion};
use serde_json::Value;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::webview::PageLoadEvent;
use tauri::{AppHandle, Manager, RunEvent, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

/// Argumentos de WebView2 para gastar poco: un solo proceso de render para todas las burbujas
/// y nada de servicios en segundo plano. (Los tres primeros los pone wry por defecto.)
/// AKARI_WEBVIEW_ARGS agrega más (el CI lo usa para comparar variantes).
const ARGS_WEBVIEW: &str = "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection \
  --renderer-process-limit=1 --disable-background-networking --disable-component-update --disable-sync \
  --no-first-run --disable-default-apps";

struct App {
  burbujas: Mutex<HashMap<String, Burbuja>>,
  cierres: Mutex<HashMap<String, u64>>,
  abiertas: Mutex<Option<BTreeSet<String>>>,
  raiz: PathBuf,
  python: PathBuf,
  hijo: Mutex<Option<Child>>,
  config: PathBuf,
  // ---- grupos cerrados sin navegador (cerradas.rs)
  /// fuentes para dibujar las píldoras; sin ellas, todo con WebView2 como antes
  fuentes: Option<cabecera::Fuentes>,
  /// el último /api/estado y cuándo llegó
  datos: Mutex<(Value, Instant)>,
  /// grupo → ventana nativa (HWND)
  nativas: Mutex<HashMap<String, isize>>,
  /// grupo → dónde quedó cada pieza en su píldora
  partes: Mutex<HashMap<String, cabecera::Partes>>,
  /// grupo → la pieza en que se abre su página (y si la página ya terminó de cargar)
  paginas: Mutex<HashMap<String, String>>,
  cargadas: Mutex<HashSet<String>>,
  /// archivos soltados sobre un grupo cerrado, esperando a que su página cargue
  pendientes: Mutex<HashMap<String, Vec<String>>>,
}

fn carpeta_config() -> PathBuf {
  // la misma que el servicio (akari/comun.py)
  if cfg!(windows) {
    std::env::var_os("APPDATA")
      .map(PathBuf::from)
      .unwrap_or_default()
      .join("akari")
  } else {
    std::env::var_os("XDG_CONFIG_HOME")
      .map(PathBuf::from)
      .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))
      .unwrap_or_default()
      .join("akari")
  }
}

fn leer_json(ruta: &PathBuf) -> Value {
  std::fs::read_to_string(ruta)
    .ok()
    .and_then(|t| serde_json::from_str(&t).ok())
    .unwrap_or(Value::Null)
}
fn escribir_json(ruta: &PathBuf, datos: &Value) {
  if let Some(p) = ruta.parent() {
    let _ = std::fs::create_dir_all(p);
  }
  let tmp = ruta.with_extension("json.tmp");
  if std::fs::write(&tmp, serde_json::to_string_pretty(datos).unwrap_or_default()).is_ok() {
    let _ = std::fs::rename(&tmp, ruta);
  }
}

impl App {
  fn ajustes(&self) -> Value {
    leer_json(&self.config.join("app.json"))
  }
  fn guardar_ajuste(&self, clave: &str, valor: Value) {
    let ruta = self.config.join("app.json");
    let mut a = leer_json(&ruta);
    if !a.is_object() {
      a = serde_json::json!({});
    }
    a[clave] = valor;
    escribir_json(&ruta, &a);
  }
  fn mostrar_burbujas(&self) -> bool {
    self.ajustes()["burbujas"].as_bool() != Some(false)
  }
  fn guardar_posicion(&self, nombre: &str, p: Option<Posicion>) {
    let ruta = self.config.join("posiciones.json");
    let mut datos = leer_json(&ruta);
    if !datos.is_object() {
      datos = serde_json::json!({});
    }
    if !datos["capsulas"].is_object() {
      datos["capsulas"] = serde_json::json!({});
    }
    match p {
      Some(p) => datos["capsulas"][nombre] = serde_json::to_value(p).unwrap_or(Value::Null),
      None => {
        if let Some(m) = datos["capsulas"].as_object_mut() {
          m.remove(nombre);
        }
      }
    }
    escribir_json(&ruta, &datos);
  }
}

// ------------------------------------------------------------ pantalla

/// Área de trabajo del monitor (AKARI_PANTALLA=<número o nombre>; si no, el principal):
/// (x, y físicos, ancho y alto lógicos, escala).
fn area(app: &AppHandle) -> (i32, i32, f64, f64, f64) {
  let elegida = std::env::var("AKARI_PANTALLA").unwrap_or_default();
  let monitores = app.available_monitors().unwrap_or_default();
  let m = monitores
    .iter()
    .enumerate()
    .find(|(i, m)| {
      !elegida.is_empty() && (i.to_string() == elegida || m.name().map(|n| n == &elegida).unwrap_or(false))
    })
    .map(|(_, m)| m.clone())
    .or_else(|| app.primary_monitor().ok().flatten())
    .or_else(|| monitores.first().cloned());
  match m {
    Some(m) => {
      let a = m.work_area();
      let s = m.scale_factor();
      (
        a.position.x,
        a.position.y,
        a.size.width as f64 / s,
        a.size.height as f64 / s,
        s,
      )
    }
    None => (0, 0, 1920.0, 1040.0, 1.0),
  }
}

fn etiqueta(nombre: &str) -> String {
  format!("b-{nombre}")
}

/// Pone la ventana donde dice la geometría de la burbuja.
fn colocar(app: &AppHandle, ventana: &WebviewWindow, b: &Burbuja) {
  let (ax, ay, w, h, s) = area(app);
  let r = b.limites(w, h);
  let (x, y) = (ax + (r.x * s).round() as i32, ay + (r.y * s).round() as i32);
  let (ancho, alto) = ((r.w * s).round() as i32, (r.h * s).round() as i32);
  #[cfg(windows)]
  if let Ok(hwnd) = ventana.hwnd() {
    sistema::colocar(hwnd.0 as _, x, y, ancho, alto);
    return;
  }
  let _ = ventana.set_position(tauri::PhysicalPosition::new(x, y));
  let _ = ventana.set_size(tauri::PhysicalSize::new(ancho as u32, alto as u32));
}

/// Le dice a la página qué forma tiene (ver web/ventana.js).
fn avisar(app: &AppHandle, ventana: &WebviewWindow, b: &Burbuja, ventana_cerrada: bool) {
  let (_, _, w, h, _) = area(app);
  let f = b.forma(w, h, ventana_cerrada);
  let _ = ventana.eval(format!(
    "(function(f){{window.__akariForma?window.__akariForma(f):(window.__akariFormaPendiente=f)}})({f})"
  ));
}

/// Avisa al servicio qué hay abierto: sin nada abierto baja a su ritmo de reposo.
fn informar_abiertas(app: &AppHandle) {
  let estado = app.state::<Arc<App>>();
  let mut abiertas: BTreeSet<String> = estado
    .burbujas
    .lock()
    .unwrap()
    .values()
    .filter(|b| b.desplegada())
    .map(|b| b.m.nombre.clone())
    .collect();
  if app.get_webview_window("panel").is_some() {
    abiertas.insert("panel".into());
  }
  let mut anterior = estado.abiertas.lock().unwrap();
  if anterior.as_ref() == Some(&abiertas) {
    return;
  }
  *anterior = Some(abiertas.clone());
  let cuerpo = serde_json::json!({ "abiertas": abiertas.into_iter().collect::<Vec<_>>() }).to_string();
  std::thread::spawn(move || servicio::pedir("POST", "/api/burbujas", Some(&cuerpo)));
}

// ------------------------------------------------------------ burbujas

fn crear_burbuja(app: &AppHandle, m: Medidas, guardada: Option<Posicion>) {
  let nombre = m.nombre.clone();
  let pieza = m
    .piezas
    .first()
    .map(|p| p.nombre.clone())
    .unwrap_or_else(|| nombre.clone());
  app
    .state::<Arc<App>>()
    .burbujas
    .lock()
    .unwrap()
    .insert(nombre.clone(), Burbuja::new(m, guardada.as_ref()));
  if cerradas::activo(app) {
    cerradas::crear(app, &nombre); // WebView2 solo cuando se abra
  } else {
    crear_webview(app, &nombre, &pieza);
  }
}

/// La página de un grupo (la pieza se elige al mostrarla: ver `mostrar_abierta`).
fn url_de(grupo: &str) -> String {
  format!("{}?vista=burbuja&c={grupo}", servicio::URL)
}

fn crear_webview(app: &AppHandle, nombre: &str, pieza: &str) {
  let estado = app.state::<Arc<App>>();
  let Some(b) = estado.burbujas.lock().unwrap().get(nombre).cloned() else {
    return;
  };
  let teclado = b.m.teclado;
  let (_, _, w, h, _) = area(app);
  let r = b.limites(w, h);
  let url = url_de(nombre);
  estado
    .paginas
    .lock()
    .unwrap()
    .insert(nombre.to_string(), pieza.to_string());
  estado.cargadas.lock().unwrap().remove(nombre);
  let Ok(url) = url.parse() else { return };
  let args = format!(
    "{ARGS_WEBVIEW} {}",
    std::env::var("AKARI_WEBVIEW_ARGS").unwrap_or_default()
  );
  let constructor = WebviewWindowBuilder::new(app, etiqueta(nombre), WebviewUrl::External(url))
    .title("akari")
    .inner_size(r.w, r.h)
    .position(r.x, r.y)
    .decorations(false)
    .transparent(true)
    .shadow(false)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .visible_on_all_workspaces(true)
    .focused(false)
    // solo la de IA tiene dónde escribir; las demás no se roban el foco al hacer clic
    .focusable(teclado)
    .visible(false)
    .zoom_hotkeys_enabled(false)
    .browser_extensions_enabled(false)
    .additional_browser_args(&args)
    .on_page_load(move |ventana, carga| {
      if carga.event() != PageLoadEvent::Finished {
        return;
      }
      let app = ventana.app_handle().clone();
      let estado = app.state::<Arc<App>>();
      let nombre = ventana.label().trim_start_matches("b-").to_string();
      estado.cargadas.lock().unwrap().insert(nombre.clone());
      let Some(b) = estado.burbujas.lock().unwrap().get(&nombre).cloned() else {
        return;
      };
      if cerradas::activo(&app) {
        // se creó al pasar el ratón: se muestra solo si sigue abierta
        if b.desplegada() {
          mostrar_abierta(&app, &ventana, &nombre, &b);
        }
        return;
      }
      colocar(&app, &ventana, &b);
      avisar(&app, &ventana, &b, !b.desplegada());
      if estado.mostrar_burbujas() {
        let _ = ventana.show();
      }
      #[cfg(windows)]
      sistema::memoria_baja(&ventana, true);
    });
  if let Ok(ventana) = constructor.build() {
    #[cfg(windows)]
    if let Ok(hwnd) = ventana.hwnd() {
      sistema::herramienta(hwnd.0 as _);
    }
    let _ = ventana; // las burbujas no se cierran con Alt+F4: ver on_window_event
  }
}

/// Muestra la página de un grupo ya abierta (y esconde su píldora nativa).
fn mostrar_abierta(app: &AppHandle, ventana: &WebviewWindow, nombre: &str, b: &Burbuja) {
  colocar(app, ventana, b);
  // en la pieza cuyo chip tenía el puntero (web/ventana.js: __akariPieza)
  let pieza = app.state::<Arc<App>>().paginas.lock().unwrap().get(nombre).cloned();
  if let Some(pieza) = pieza.filter(|_| b.m.piezas.len() > 1) {
    let pieza = Value::String(pieza);
    let _ = ventana.eval(format!("window.__akariPieza && window.__akariPieza({pieza})"));
  }
  avisar(app, ventana, b, false);
  let _ = ventana.show();
  #[cfg(windows)]
  sistema::memoria_baja(ventana, false);
  cerradas::mostrar(app, nombre, false);
  // archivos soltados sobre la píldora: a la página, cuando ya tenga sus datos
  if let Some(rutas) = app.state::<Arc<App>>().pendientes.lock().unwrap().remove(nombre) {
    let (v, x) = (ventana.clone(), b.m.ancho_abierto / 2.0);
    std::thread::spawn(move || {
      std::thread::sleep(Duration::from_millis(900));
      let datos = serde_json::json!({ "tipo": "soltar", "rutas": rutas, "x": x, "y": 160.0 });
      let _ = v.eval(format!("window.__akariArrastre && window.__akariArrastre({datos})"));
    });
  }
}

/// Abre un grupo en una pieza (al pasar el ratón por su chip en la píldora nativa).
fn abrir_en(app: &AppHandle, nombre: &str, pieza: &str) {
  let estado = app.state::<Arc<App>>();
  let b = {
    let mut lista = estado.burbujas.lock().unwrap();
    let Some(b) = lista.get_mut(nombre) else { return };
    if b.moviendo {
      return;
    }
    b.abierta = true;
    b.clone()
  };
  // un cierre o una destrucción pendientes ya no corren
  *estado.cierres.lock().unwrap().entry(nombre.to_string()).or_insert(0) += 1;
  estado
    .paginas
    .lock()
    .unwrap()
    .insert(nombre.to_string(), pieza.to_string());
  match app.get_webview_window(&etiqueta(nombre)) {
    None => crear_webview(app, nombre, pieza),
    Some(v) => {
      if estado.cargadas.lock().unwrap().contains(nombre) {
        mostrar_abierta(app, &v, nombre, &b);
      }
    }
  }
  informar_abiertas(app);
}

/// Pone la ventana de WebView2 de un grupo (si existe) donde dice su geometría.
fn colocar_webview(app: &AppHandle, nombre: &str) {
  let estado = app.state::<Arc<App>>();
  let Some(b) = estado.burbujas.lock().unwrap().get(nombre).cloned() else {
    return;
  };
  if let Some(v) = app.get_webview_window(&etiqueta(nombre)) {
    colocar(app, &v, &b);
    avisar(app, &v, &b, !b.desplegada());
  }
}

/// Lo que manda la página (web/ventana.js → invoke("burbuja")).
#[tauri::command]
fn burbuja(app: AppHandle, ventana: WebviewWindow, estado: State<Arc<App>>, accion: String, datos: Value) {
  let nombre = ventana.label().trim_start_matches("b-").to_string();
  let (_, _, w, h, _) = area(&app);
  let mut lista = estado.burbujas.lock().unwrap();
  let Some(b) = lista.get_mut(&nombre) else { return };
  let numero = |k: &str| datos[k].as_f64().unwrap_or(0.0);
  match accion.as_str() {
    "abrir" => {
      estado.cierres.lock().unwrap().remove(&nombre);
      if b.desplegada() {
        return;
      }
      b.abierta = true;
      colocar(&app, &ventana, b);
      avisar(&app, &ventana, b, false);
      #[cfg(windows)]
      sistema::memoria_baja(&ventana, false);
    }
    "cerrar" => {
      if !b.abierta {
        return;
      }
      b.abierta = false;
      avisar(&app, &ventana, b, false); // la página anima el cierre (400 ms); luego se achica
      let turno = {
        let mut c = estado.cierres.lock().unwrap();
        let n = c.get(&nombre).copied().unwrap_or(0) + 1;
        c.insert(nombre.clone(), n);
        n
      };
      let (app2, nombre) = (app.clone(), nombre.clone());
      std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(450));
        // todo lo que toca ventanas va al hilo de la interfaz (y sin tener el candado tomado
        // mientras se espera a ese hilo)
        let app3 = app2.clone();
        let _ = app2.run_on_main_thread(move || {
          let estado = app3.state::<Arc<App>>();
          if estado.cierres.lock().unwrap().get(&nombre) != Some(&turno) {
            return; // se volvió a abrir mientras tanto
          }
          let Some(b) = estado.burbujas.lock().unwrap().get(&nombre).cloned() else {
            return;
          };
          let Some(v) = app3.get_webview_window(&etiqueta(&nombre)) else {
            return;
          };
          if b.desplegada() {
            return;
          }
          if cerradas::activo(&app3) {
            // vuelve la píldora nativa; la página queda escondida un minuto por si se reabre
            cerradas::pintar(&app3, &nombre);
            cerradas::mostrar(&app3, &nombre, estado.mostrar_burbujas());
            let _ = v.hide();
            #[cfg(windows)]
            sistema::memoria_baja(&v, true);
            let app4 = app3.clone();
            std::thread::spawn(move || {
              std::thread::sleep(Duration::from_secs(60));
              let app5 = app4.clone();
              let _ = app4.run_on_main_thread(move || {
                let estado = app5.state::<Arc<App>>();
                let sigue = estado.cierres.lock().unwrap().get(&nombre) == Some(&turno);
                let abierta = estado
                  .burbujas
                  .lock()
                  .unwrap()
                  .get(&nombre)
                  .map(|b| b.desplegada())
                  .unwrap_or(false);
                if sigue && !abierta {
                  if let Some(v) = app5.get_webview_window(&etiqueta(&nombre)) {
                    let _ = v.destroy();
                  }
                  estado.paginas.lock().unwrap().remove(&nombre);
                  estado.cargadas.lock().unwrap().remove(&nombre);
                }
              });
            });
            return;
          }
          colocar(&app3, &v, &b);
          avisar(&app3, &v, &b, true);
          #[cfg(windows)]
          sistema::memoria_baja(&v, true);
        });
      });
    }
    "alto" => {
      let alto = numero("alto").ceil();
      if alto != b.alto_cuerpo {
        b.alto_cuerpo = alto;
        if b.desplegada() {
          colocar(&app, &ventana, b);
        }
      }
    }
    "mover-inicio" => {
      b.empezar_mover(w);
      colocar(&app, &ventana, b);
      avisar(&app, &ventana, b, true);
    }
    "mover" => {
      b.mover(numero("dx"), numero("dy"), w, h);
      colocar(&app, &ventana, b);
    }
    "soltar" => {
      b.soltar(w, h);
      estado.guardar_posicion(&nombre, b.posicion());
      colocar(&app, &ventana, b);
      avisar(&app, &ventana, b, !b.desplegada());
    }
    "fabrica" => {
      b.fabrica();
      estado.guardar_posicion(&nombre, None);
      colocar(&app, &ventana, b);
      avisar(&app, &ventana, b, !b.desplegada());
    }
    _ => return,
  }
  drop(lista);
  if cerradas::activo(&app) && matches!(accion.as_str(), "soltar" | "fabrica") {
    cerradas::pintar(&app, &nombre);
  }
  informar_abiertas(&app);
}

#[tauri::command]
fn alternar_panel(app: AppHandle) {
  alternar(&app);
}

fn recolocar_todas(app: &AppHandle) {
  let (_, _, w, h, _) = area(app);
  let estado = app.state::<Arc<App>>();
  let nombres: Vec<String> = {
    let mut lista = estado.burbujas.lock().unwrap();
    lista.values_mut().for_each(|b| b.recolocar(w, h));
    lista.keys().cloned().collect()
  };
  for nombre in nombres {
    colocar_webview(app, &nombre);
    if cerradas::activo(app) {
      cerradas::pintar(app, &nombre);
    }
  }
}

fn mostrar_todas(app: &AppHandle, si: bool) {
  let estado = app.state::<Arc<App>>();
  let lista: Vec<(String, bool)> = estado
    .burbujas
    .lock()
    .unwrap()
    .iter()
    .map(|(n, b)| (n.clone(), b.desplegada()))
    .collect();
  for (nombre, abierta) in lista {
    if let Some(v) = app.get_webview_window(&etiqueta(&nombre)) {
      // con píldoras nativas, la página solo se ve abierta
      let _ = if si && (abierta || !cerradas::activo(app)) {
        v.show()
      } else {
        v.hide()
      };
    }
    if cerradas::activo(app) {
      cerradas::mostrar(app, &nombre, si && !abierta);
    }
  }
}

fn todas_a_su_sitio(app: &AppHandle) {
  let estado = app.state::<Arc<App>>();
  let nombres: Vec<String> = estado.burbujas.lock().unwrap().keys().cloned().collect();
  for nombre in nombres {
    if let Some(b) = estado.burbujas.lock().unwrap().get_mut(&nombre) {
      b.fabrica();
    }
    estado.guardar_posicion(&nombre, None);
  }
  recolocar_todas(app);
}

// ------------------------------------------------------------ panel completo

fn alternar(app: &AppHandle) {
  if let Some(p) = app.get_webview_window("panel") {
    if p.is_visible().unwrap_or(false) && p.is_focused().unwrap_or(false) {
      let _ = p.close(); // cerrado de verdad: no se queda ocupando memoria
    } else {
      let _ = p.show();
      let _ = p.set_focus();
    }
    return;
  }
  let (_, _, w, h, _) = area(app);
  let (ancho, alto) = (460f64.min(w - 20.0), 800f64.min(h - 60.0));
  let args = format!(
    "{ARGS_WEBVIEW} {}",
    std::env::var("AKARI_WEBVIEW_ARGS").unwrap_or_default()
  );
  let Ok(url) = servicio::URL.parse() else { return };
  let creado = WebviewWindowBuilder::new(app, "panel", WebviewUrl::External(url))
    .title("akari")
    .inner_size(ancho, alto)
    .min_inner_size(380.0, 480.0)
    .position(((w - ancho) / 2.0).round(), 52.0)
    .background_color(tauri::window::Color(19, 19, 23, 255))
    .additional_browser_args(&args)
    .build();
  if creado.is_ok() {
    informar_abiertas(app);
  }
}

// ------------------------------------------------------------ bandeja

fn claude_conectado() -> bool {
  let base = std::env::var_os("CLAUDE_CONFIG_DIR").map(PathBuf::from).or_else(|| {
    std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).map(|h| PathBuf::from(h).join(".claude"))
  });
  base
    .map(|b| {
      leer_json(&b.join("settings.json"))["statusLine"]["command"]
        .as_str()
        .unwrap_or("")
        .contains("akari")
    })
    .unwrap_or(false)
}

/// ¿Español? AKARI_IDIOMA manda; si no, el idioma de Windows (es-MX, es-ES…) o LANG en Linux.
fn es() -> bool {
  if let Ok(v) = std::env::var("AKARI_IDIOMA") {
    return v.starts_with("es");
  }
  idioma_sistema().starts_with("es")
}
#[cfg(windows)]
fn idioma_sistema() -> String {
  #[link(name = "kernel32")]
  extern "system" {
    fn GetUserDefaultLocaleName(nombre: *mut u16, largo: i32) -> i32;
  }
  let mut buf = [0u16; 85];
  let n = unsafe { GetUserDefaultLocaleName(buf.as_mut_ptr(), buf.len() as i32) };
  String::from_utf16_lossy(&buf[..(n.max(1) - 1) as usize]).to_lowercase()
}
#[cfg(not(windows))]
fn idioma_sistema() -> String {
  ["LANGUAGE", "LC_ALL", "LANG"]
    .iter()
    .find_map(|v| std::env::var(v).ok().filter(|x| !x.is_empty()))
    .unwrap_or_default()
}

fn crear_bandeja(app: &AppHandle) -> tauri::Result<()> {
  let es = es();
  let t = |a: &'static str, b: &'static str| if es { a } else { b };
  let estado = app.state::<Arc<App>>();
  let panel = MenuItem::with_id(app, "panel", t("Abrir panel", "Open panel"), true, None::<&str>)?;
  let ver = CheckMenuItem::with_id(
    app,
    "ver",
    t("Mostrar las burbujas", "Show the bubbles"),
    true,
    estado.mostrar_burbujas(),
    None::<&str>,
  )?;
  let sitio = MenuItem::with_id(
    app,
    "sitio",
    t("Devolver las burbujas a su sitio", "Put the bubbles back in place"),
    true,
    None::<&str>,
  )?;
  #[cfg(windows)]
  let auto = sistema::autoarranque();
  #[cfg(not(windows))]
  let auto = false;
  let inicio = CheckMenuItem::with_id(
    app,
    "inicio",
    t("Iniciar con Windows", "Start with Windows"),
    cfg!(windows),
    auto,
    None::<&str>,
  )?;
  let claude = CheckMenuItem::with_id(
    app,
    "claude",
    t("Conectar con Claude Code (límites)", "Connect to Claude Code (limits)"),
    true,
    claude_conectado(),
    None::<&str>,
  )?;
  let salir = MenuItem::with_id(app, "salir", t("Salir", "Quit"), true, None::<&str>)?;
  let menu = Menu::with_items(
    app,
    &[
      &panel,
      &ver,
      &sitio,
      &inicio,
      &claude,
      &PredefinedMenuItem::separator(app)?,
      &salir,
    ],
  )?;
  let (ver2, inicio2, claude2) = (ver.clone(), inicio.clone(), claude.clone());
  let mut b = TrayIconBuilder::with_id("akari")
    .tooltip("akari")
    .menu(&menu)
    .show_menu_on_left_click(false);
  if let Some(icono) = app.default_window_icon() {
    b = b.icon(icono.clone());
  }
  b.on_menu_event(move |app, ev| {
    let estado = app.state::<Arc<App>>();
    match ev.id.as_ref() {
      "panel" => alternar(app),
      "ver" => {
        let si = ver2.is_checked().unwrap_or(true);
        estado.guardar_ajuste("burbujas", Value::Bool(si));
        mostrar_todas(app, si);
      }
      "sitio" => todas_a_su_sitio(app),
      "inicio" => {
        #[cfg(windows)]
        sistema::poner_autoarranque(inicio2.is_checked().unwrap_or(false));
        let _ = &inicio2;
      }
      "claude" => {
        let orden = if claude2.is_checked().unwrap_or(false) {
          "conectar-claude"
        } else {
          "desconectar-claude"
        };
        let (raiz, python, item) = (estado.raiz.clone(), estado.python.clone(), claude2.clone());
        std::thread::spawn(move || {
          let _ = servicio::orden(&raiz, &python, &[orden]).status();
          let _ = item.set_checked(claude_conectado());
        });
      }
      "salir" => app.exit(0),
      _ => {}
    }
  })
  .on_tray_icon_event(|tray, ev| {
    if let TrayIconEvent::Click {
      button: MouseButton::Left,
      button_state: MouseButtonState::Up,
      ..
    } = ev
    {
      alternar(tray.app_handle());
    }
  })
  .build(app)?;
  Ok(())
}

// ------------------------------------------------------------ arranque

fn arrancar(app: AppHandle) {
  let estado = app.state::<Arc<App>>().inner().clone();
  if let Some(hijo) = servicio::asegurar(&estado.raiz, &estado.python) {
    *estado.hijo.lock().unwrap() = Some(hijo);
  }
  let respuesta = servicio::pedir("GET", "/api/burbujas", None)
    .and_then(|t| serde_json::from_str::<Value>(&t).ok())
    .unwrap_or_default();
  let medidas: Vec<Medidas> = serde_json::from_value(respuesta["grupos"].clone())
    .ok()
    .filter(|l: &Vec<Medidas>| !l.is_empty())
    .unwrap_or_else(forma::de_fabrica);
  if cerradas::activo(&app) {
    // los datos de las píldoras antes de dibujarlas; luego, de vez en cuando
    if let Some(d) = servicio::pedir("GET", "/api/estado", None).and_then(|t| serde_json::from_str(&t).ok()) {
      *estado.datos.lock().unwrap() = (d, Instant::now());
    }
    #[cfg(windows)]
    {
      let app2 = app.clone();
      nativo::iniciar(Box::new(move |nombre, ev| {
        let (app3, nombre) = (app2.clone(), nombre.to_string());
        let _ = app2.run_on_main_thread(move || cerradas::evento(&app3, &nombre, ev));
      }));
    }
    let app2 = app.clone();
    std::thread::spawn(move || cerradas::sondear(app2));
  }
  let guardadas = leer_json(&estado.config.join("posiciones.json"));
  for m in medidas {
    let p = serde_json::from_value::<Posicion>(guardadas["capsulas"][&m.nombre].clone()).ok();
    let app2 = app.clone();
    // las ventanas se crean en el hilo de la interfaz
    let _ = app.run_on_main_thread(move || crear_burbuja(&app2, m, p));
  }
  informar_abiertas(&app);
}

/// Las fuentes de Windows para las píldoras nativas (Segoe UI, Cascadia Mono o Consolas y la
/// de símbolos para ⚡). Fuera de Windows no se usan píldoras nativas.
fn fuentes_del_sistema() -> Option<cabecera::Fuentes> {
  if !cfg!(windows) || std::env::var("AKARI_SIN_NATIVAS").is_ok() {
    return None;
  }
  let dir = std::env::var("WINDIR").unwrap_or_else(|_| r"C:\Windows".into()) + r"\Fonts\";
  let f = |n: &str| format!("{dir}{n}");
  cabecera::Fuentes::cargar(
    &[&f("segoeui.ttf")],
    &[&f("seguisb.ttf"), &f("segoeui.ttf")],
    &[&f("CascadiaMono.ttf"), &f("consola.ttf")],
    &[&f("seguisym.ttf")],
  )
}

fn main() {
  let config = carpeta_config();
  let aplicacion = tauri::Builder::default()
    .plugin(tauri_plugin_single_instance::init(|app, argv, _| {
      // abrir akari otra vez: que se vean las burbujas y el panel
      let estado = app.state::<Arc<App>>();
      if !estado.mostrar_burbujas() {
        estado.guardar_ajuste("burbujas", Value::Bool(true));
        mostrar_todas(app, true);
      }
      if !argv.iter().any(|a| a == "--sin-panel") {
        alternar(app);
      }
    }))
    .invoke_handler(tauri::generate_handler![burbuja, alternar_panel])
    .setup(move |app| {
      let (raiz, python) = servicio::rutas(app.path().resource_dir().ok());
      let estado = Arc::new(App {
        burbujas: Mutex::new(HashMap::new()),
        cierres: Mutex::new(HashMap::new()),
        abiertas: Mutex::new(None),
        raiz,
        python,
        hijo: Mutex::new(None),
        config: config.clone(),
        fuentes: fuentes_del_sistema(),
        datos: Mutex::new((Value::Null, Instant::now())),
        nativas: Mutex::new(HashMap::new()),
        partes: Mutex::new(HashMap::new()),
        paginas: Mutex::new(HashMap::new()),
        cargadas: Mutex::new(HashSet::new()),
        pendientes: Mutex::new(HashMap::new()),
      });
      app.manage(estado.clone());
      // la primera vez queda para iniciar con Windows (se cambia en la bandeja)
      #[cfg(windows)]
      if estado.ajustes()["autoarranque"].is_null() {
        sistema::poner_autoarranque(true);
        estado.guardar_ajuste("autoarranque", Value::Bool(true));
      }
      crear_bandeja(app.handle())?;
      let handle = app.handle().clone();
      std::thread::spawn(move || arrancar(handle));
      Ok(())
    })
    .on_window_event(|ventana, ev| match ev {
      tauri::WindowEvent::CloseRequested { api, .. } if ventana.label().starts_with("b-") => api.prevent_close(),
      tauri::WindowEvent::Destroyed if ventana.label() == "panel" => informar_abiertas(ventana.app_handle()),
      // archivos soltados en una burbuja (o en el panel): la página los recibe como un "drop"
      // normal y sabe su ruta real con window.akari.rutaDe (ver web/ventana.js)
      tauri::WindowEvent::DragDrop(arrastre) => {
        let escala = ventana.scale_factor().unwrap_or(1.0);
        let punto = |p: &tauri::PhysicalPosition<f64>| (p.x / escala, p.y / escala);
        let (tipo, rutas, (x, y)) = match arrastre {
          tauri::DragDropEvent::Enter { paths, position } => ("entrar", paths.clone(), punto(position)),
          tauri::DragDropEvent::Over { position } => ("encima", vec![], punto(position)),
          tauri::DragDropEvent::Drop { paths, position } => ("soltar", paths.clone(), punto(position)),
          _ => ("salir", vec![], (0.0, 0.0)),
        };
        let rutas: Vec<String> = rutas.iter().map(|r| r.to_string_lossy().into_owned()).collect();
        let datos = serde_json::json!({ "tipo": tipo, "rutas": rutas, "x": x, "y": y });
        if let Some(v) = ventana.app_handle().get_webview_window(ventana.label()) {
          let _ = v.eval(format!("window.__akariArrastre && window.__akariArrastre({datos})"));
        }
      }
      tauri::WindowEvent::ScaleFactorChanged { .. } => {
        // llega en medio de un SetWindowPos: se recoloca después, ya fuera de esa llamada
        let app = ventana.app_handle().clone();
        std::thread::spawn(move || {
          std::thread::sleep(Duration::from_millis(50));
          let app2 = app.clone();
          let _ = app.run_on_main_thread(move || recolocar_todas(&app2));
        });
      }
      _ => {}
    })
    .build(tauri::generate_context!())
    .expect("no pude iniciar akari");
  aplicacion.run(|app, ev| match ev {
    // sin ventanas abiertas sigue en la bandeja
    RunEvent::ExitRequested { api, code: None, .. } => api.prevent_exit(),
    RunEvent::Exit => {
      if let Some(mut hijo) = app.state::<Arc<App>>().hijo.lock().unwrap().take() {
        let _ = hijo.kill();
      }
    }
    _ => {}
  });
}
