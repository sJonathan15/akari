//! Los grupos cerrados sin navegador (Windows). Cada grupo cerrado es una ventana nativa con
//! su píldora (cabecera.rs + nativo.rs); WebView2 solo se crea al abrir uno (en la pieza que
//! está bajo el puntero), se esconde al cerrarlo y se destruye un minuto después. Así, en
//! reposo, akari es esta app y el servicio de Python, sin ningún proceso de WebView2.
//!
//! Los datos de las píldoras salen de /api/estado: cada 5 s con algo abierto y cada 30 s con
//! todo cerrado (el servicio también baja a su ritmo de reposo).
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::Value;
use tauri::{AppHandle, Manager};

use crate::forma::{Burbuja, ALTO};
use crate::App;

/// ¿Se usan píldoras nativas? Solo en Windows y si se pudieron cargar las fuentes.
pub fn activo(app: &AppHandle) -> bool {
  cfg!(windows) && app.state::<Arc<App>>().fuentes.is_some()
}

/// Píldora cerrada de una burbuja: dónde va (físicos) y su dibujo.
fn dibujar(app: &AppHandle, b: &Burbuja) -> Option<(i32, i32, tiny_skia::Pixmap, crate::cabecera::Partes)> {
  let estado = app.state::<Arc<App>>();
  let fuentes = estado.fuentes.as_ref()?;
  let mut c = b.clone();
  c.abierta = false;
  let (ax, ay, w, h, s) = crate::area(app);
  let r = c.limites(w, h);
  let (datos, cuando) = estado.datos.lock().unwrap().clone();
  let ahora = datos["ahora"].as_f64().unwrap_or(0.0) + cuando.elapsed().as_secs_f64();
  let forma = crate::cabecera::Forma {
    piezas: &b.m.piezas,
    ancho: b.m.ancho_cerrado,
    vertical: c.vertical(),
    borde: &c.borde,
    pegada_arriba: !c.vertical() && c.cy <= 0.0,
    pegada_abajo: !c.vertical() && c.cy + ALTO >= h,
  };
  let (px, partes) = crate::cabecera::dibujar(&forma, &datos, ahora, s as f32, fuentes)?;
  Some((ax + (r.x * s).round() as i32, ay + (r.y * s).round() as i32, px, partes))
}

/// La pieza que está bajo el puntero (según dónde quedó cada chip al dibujar).
fn pieza_bajo_puntero(app: &AppHandle, nombre: &str) -> Option<String> {
  let estado = app.state::<Arc<App>>();
  let b = estado.burbujas.lock().unwrap().get(nombre).cloned()?;
  let partes = estado.partes.lock().unwrap().get(nombre).cloned()?;
  let (ax, ay, w, h, s) = crate::area(app);
  let mut c = b.clone();
  c.abierta = false;
  let r = c.limites(w, h);
  let (px, py) = cursor();
  let a_lo_largo = if c.vertical() {
    (py - ay) as f64 / s - r.y
  } else {
    (px - ax) as f64 / s - r.x
  } as f32;
  partes
    .iter()
    .find(|(_, desde, hasta)| a_lo_largo >= *desde && a_lo_largo < *hasta)
    .or(partes.first())
    .map(|(n, _, _)| n.clone())
}

#[cfg(windows)]
fn cursor() -> (i32, i32) {
  let mut p = windows_sys::Win32::Foundation::POINT { x: 0, y: 0 };
  unsafe { windows_sys::Win32::UI::WindowsAndMessaging::GetCursorPos(&mut p) };
  (p.x, p.y)
}
#[cfg(not(windows))]
fn cursor() -> (i32, i32) {
  (0, 0)
}

pub fn crear(app: &AppHandle, nombre: &str) {
  #[cfg(windows)]
  {
    let hwnd = crate::nativo::crear(nombre);
    app
      .state::<Arc<App>>()
      .nativas
      .lock()
      .unwrap()
      .insert(nombre.to_string(), hwnd as isize);
    pintar(app, nombre);
    if app.state::<Arc<App>>().mostrar_burbujas() {
      mostrar(app, nombre, true);
    }
  }
  let _ = (app, nombre);
}

/// Redibuja la píldora cerrada y la pone en su sitio (aunque esté escondida).
pub fn pintar(app: &AppHandle, nombre: &str) {
  let estado = app.state::<Arc<App>>();
  let Some(b) = estado.burbujas.lock().unwrap().get(nombre).cloned() else {
    return;
  };
  let Some((x, y, px, partes)) = dibujar(app, &b) else {
    return;
  };
  estado.partes.lock().unwrap().insert(nombre.to_string(), partes);
  #[cfg(windows)]
  if let Some(h) = estado.nativas.lock().unwrap().get(nombre) {
    crate::nativo::pintar(*h as _, x, y, &px);
  }
  let _ = (x, y, px);
}

pub fn mostrar(app: &AppHandle, nombre: &str, si: bool) {
  #[cfg(windows)]
  if let Some(h) = app.state::<Arc<App>>().nativas.lock().unwrap().get(nombre) {
    crate::nativo::mostrar(*h as _, si);
  }
  let _ = (app, nombre, si);
}

/// Mientras se arrastra la píldora solo cambia de sitio (redibujar a cada paso no hace falta).
fn mover_a(app: &AppHandle, nombre: &str) {
  let estado = app.state::<Arc<App>>();
  let Some(b) = estado.burbujas.lock().unwrap().get(nombre).cloned() else {
    return;
  };
  let (ax, ay, w, h, s) = crate::area(app);
  let r = b.limites(w, h);
  #[cfg(windows)]
  if let Some(hwnd) = estado.nativas.lock().unwrap().get(nombre) {
    crate::nativo::mover(*hwnd as _, ax + (r.x * s).round() as i32, ay + (r.y * s).round() as i32);
  }
  let _ = (ax, ay, r, s);
}

/// Archivos soltados sobre un grupo cerrado: la pieza que los recibe (AGENTS.md).
fn pieza_para_archivos(b: &Burbuja, rutas: &[String]) -> Option<String> {
  let tiene = |n: &str| b.m.piezas.iter().any(|p| p.nombre == n);
  let audio = rutas.iter().all(|r| {
    let r = r.to_lowercase();
    [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".webm"]
      .iter()
      .any(|e| r.ends_with(e))
  });
  if audio && tiene("audio") {
    return Some("audio".into());
  }
  if tiene("documentos") {
    return Some("documentos".into());
  }
  b.m.piezas.first().map(|p| p.nombre.clone())
}

/// Lo que pasa con el puntero sobre una píldora (ya en el hilo de la interfaz).
#[cfg(windows)]
pub fn evento(app: &AppHandle, nombre: &str, ev: crate::nativo::Evento) {
  use crate::nativo::Evento;
  let estado = app.state::<Arc<App>>();
  let (_, _, w, h, s) = crate::area(app);
  match ev {
    Evento::Entrar => {
      if let Some(pieza) = pieza_bajo_puntero(app, nombre) {
        crate::abrir_en(app, nombre, &pieza);
      }
    }
    Evento::Salir => {
      // todavía cargando: ya no hace falta mostrarla
      let visible = app
        .get_webview_window(&crate::etiqueta(nombre))
        .and_then(|v| v.is_visible().ok())
        .unwrap_or(false);
      if !visible {
        if let Some(b) = estado.burbujas.lock().unwrap().get_mut(nombre) {
          b.abierta = false;
        }
        crate::informar_abiertas(app);
      }
    }
    Evento::EmpezarMover => {
      if let Some(b) = estado.burbujas.lock().unwrap().get_mut(nombre) {
        b.abierta = false;
        b.empezar_mover(w);
      }
    }
    Evento::Mover(dx, dy) => {
      if let Some(b) = estado.burbujas.lock().unwrap().get_mut(nombre) {
        b.mover(dx as f64 / s, dy as f64 / s, w, h);
      }
      mover_a(app, nombre);
    }
    Evento::Soltar => {
      let p = estado.burbujas.lock().unwrap().get_mut(nombre).map(|b| {
        b.soltar(w, h);
        b.posicion()
      });
      if let Some(p) = p {
        estado.guardar_posicion(nombre, p);
      }
      pintar(app, nombre);
      crate::colocar_webview(app, nombre);
    }
    Evento::DobleClic => {
      if let Some(b) = estado.burbujas.lock().unwrap().get_mut(nombre) {
        b.fabrica();
      }
      estado.guardar_posicion(nombre, None);
      pintar(app, nombre);
      crate::colocar_webview(app, nombre);
    }
    Evento::Archivos(rutas) => {
      let Some(b) = estado.burbujas.lock().unwrap().get(nombre).cloned() else {
        return;
      };
      if let Some(pieza) = pieza_para_archivos(&b, &rutas) {
        estado.pendientes.lock().unwrap().insert(nombre.to_string(), rutas);
        crate::abrir_en(app, nombre, &pieza);
      }
    }
  }
}

/// Trae /api/estado de vez en cuando y redibuja las píldoras.
pub fn sondear(app: AppHandle) {
  loop {
    if let Some(datos) =
      crate::servicio::pedir("GET", "/api/estado", None).and_then(|t| serde_json::from_str::<Value>(&t).ok())
    {
      *app.state::<Arc<App>>().datos.lock().unwrap() = (datos, Instant::now());
      let app2 = app.clone();
      let _ = app.run_on_main_thread(move || {
        let nombres: Vec<String> = app2
          .state::<Arc<App>>()
          .burbujas
          .lock()
          .unwrap()
          .keys()
          .cloned()
          .collect();
        for n in nombres {
          pintar(&app2, &n);
        }
      });
    }
    let algo_abierto = app
      .state::<Arc<App>>()
      .burbujas
      .lock()
      .unwrap()
      .values()
      .any(|b| b.desplegada());
    std::thread::sleep(Duration::from_secs(if algo_abierto { 5 } else { 30 }));
  }
}
