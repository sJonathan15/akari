//! Burbujas cerradas como ventanas nativas de Windows: "layered" (transparencia por píxel, el
//! clic en las esquinas transparentes pasa a lo de abajo), siempre visibles, sin foco, fuera de
//! la barra de tareas y de Alt+Tab. Muestran la cabecera que dibuja cabecera.rs y avisan del
//! puntero: entrar (para abrir con WebView2), arrastrar, soltar y doble clic. Así, con todo
//! cerrado, no corre ningún proceso de WebView2.
#![cfg(windows)]
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use tiny_skia::Pixmap;
use windows_sys::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, SIZE, WPARAM};
use windows_sys::Win32::Graphics::Gdi::{
  CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, GetDC, ReleaseDC, SelectObject, AC_SRC_ALPHA,
  AC_SRC_OVER, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, BLENDFUNCTION, DIB_RGB_COLORS,
};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
  ReleaseCapture, SetCapture, TrackMouseEvent, TME_LEAVE, TRACKMOUSEEVENT,
};
use windows_sys::Win32::UI::Shell::{DragAcceptFiles, DragFinish, DragQueryFileW, HDROP};
use windows_sys::Win32::UI::WindowsAndMessaging::{
  CreateWindowExW, DefWindowProcW, GetCursorPos, LoadCursorW, RegisterClassW, SetWindowPos, ShowWindow,
  UpdateLayeredWindow, CS_DBLCLKS, HWND_TOPMOST, IDC_ARROW, MA_NOACTIVATE, SWP_NOACTIVATE, SWP_NOSIZE, SW_HIDE,
  SW_SHOWNOACTIVATE, ULW_ALPHA, WM_CAPTURECHANGED, WM_DROPFILES, WM_LBUTTONDBLCLK, WM_LBUTTONDOWN, WM_LBUTTONUP,
  WM_MOUSEACTIVATE, WM_MOUSEMOVE, WNDCLASSW, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST,
  WS_POPUP,
};

// (en windows-sys está con los controles comunes; se define aquí para no traerlos)
const WM_MOUSELEAVE: u32 = 0x02A3;

/// Lo que pasa con el puntero sobre una burbuja cerrada.
#[derive(Clone, Debug)]
pub enum Evento {
  Entrar,
  Salir,
  EmpezarMover,
  /// cuánto se movió el puntero desde que se apretó (píxeles físicos)
  Mover(i32, i32),
  Soltar,
  DobleClic,
  /// archivos soltados sobre la burbuja cerrada (rutas)
  Archivos(Vec<String>),
}

type Aviso = Box<dyn Fn(&str, Evento) + Send + Sync>;
static AVISO: OnceLock<Aviso> = OnceLock::new();

#[derive(Default, Clone, Copy)]
struct Raton {
  siguiendo: bool,
  apretado: Option<(i32, i32)>,
  moviendo: bool,
}
/// hwnd → (nombre de la burbuja, estado del puntero)
static VENTANAS: Mutex<Option<HashMap<isize, (String, Raton)>>> = Mutex::new(None);

fn ancho(texto: &str) -> Vec<u16> {
  texto.encode_utf16().chain(std::iter::once(0)).collect()
}

fn cursor() -> (i32, i32) {
  let mut p = POINT { x: 0, y: 0 };
  unsafe { GetCursorPos(&mut p) };
  (p.x, p.y)
}

/// Llamadas de Win32 que mandan mensajes a la misma ventana al instante: se hacen ya sin el
/// candado tomado, si no el mensaje que provocan se quedaría esperándolo.
enum Despues {
  Nada,
  Capturar,
  Soltar,
  Seguir,
}

/// Lo que hay que avisar según el mensaje (el candado se suelta antes de avisar).
fn interpretar(hwnd: HWND, msg: u32) -> Option<(String, Evento)> {
  let mut despues = Despues::Nada;
  let resultado = interpretar_con(hwnd, msg, &mut despues);
  unsafe {
    match despues {
      Despues::Capturar => {
        SetCapture(hwnd);
      }
      Despues::Soltar => {
        ReleaseCapture();
      }
      Despues::Seguir => {
        let mut t = TRACKMOUSEEVENT {
          cbSize: std::mem::size_of::<TRACKMOUSEEVENT>() as u32,
          dwFlags: TME_LEAVE,
          hwndTrack: hwnd,
          dwHoverTime: 0,
        };
        TrackMouseEvent(&mut t);
      }
      Despues::Nada => {}
    }
  }
  resultado
}

fn interpretar_con(hwnd: HWND, msg: u32, despues: &mut Despues) -> Option<(String, Evento)> {
  let mut ventanas = VENTANAS.lock().ok()?;
  let (nombre, r) = ventanas.as_mut()?.get_mut(&(hwnd as isize))?;
  let evento = match msg {
    WM_MOUSEMOVE => {
      if let Some((x0, y0)) = r.apretado {
        let (x, y) = cursor();
        let (dx, dy) = (x - x0, y - y0);
        if !r.moviendo && dx * dx + dy * dy >= 36 {
          r.moviendo = true;
          Some(Evento::EmpezarMover)
        } else if r.moviendo {
          Some(Evento::Mover(dx, dy))
        } else {
          None
        }
      } else if !r.siguiendo {
        r.siguiendo = true;
        *despues = Despues::Seguir;
        Some(Evento::Entrar)
      } else {
        None
      }
    }
    WM_MOUSELEAVE => {
      r.siguiendo = false;
      if r.apretado.is_none() {
        Some(Evento::Salir)
      } else {
        None
      }
    }
    WM_LBUTTONDOWN => {
      r.apretado = Some(cursor());
      *despues = Despues::Capturar;
      None
    }
    WM_LBUTTONUP | WM_CAPTURECHANGED => {
      let movio = r.moviendo;
      r.apretado = None;
      r.moviendo = false;
      if msg == WM_LBUTTONUP {
        *despues = Despues::Soltar;
      }
      if movio {
        Some(Evento::Soltar)
      } else {
        None
      }
    }
    WM_LBUTTONDBLCLK => Some(Evento::DobleClic),
    _ => None,
  }?;
  Some((nombre.clone(), evento))
}

unsafe extern "system" fn procedimiento(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
  if msg == WM_MOUSEACTIVATE {
    return MA_NOACTIVATE as LRESULT; // un clic no le quita el foco a la ventana en la que estás
  }
  if msg == WM_DROPFILES {
    let soltado = wp as HDROP;
    let mut rutas = Vec::new();
    for i in 0..DragQueryFileW(soltado, u32::MAX, std::ptr::null_mut(), 0) {
      let largo = DragQueryFileW(soltado, i, std::ptr::null_mut(), 0) as usize;
      let mut buf = vec![0u16; largo + 1];
      DragQueryFileW(soltado, i, buf.as_mut_ptr(), buf.len() as u32);
      rutas.push(String::from_utf16_lossy(&buf[..largo]));
    }
    DragFinish(soltado);
    let nombre = VENTANAS
      .lock()
      .ok()
      .and_then(|v| v.as_ref()?.get(&(hwnd as isize)).map(|x| x.0.clone()));
    if let (Some(nombre), Some(aviso)) = (nombre, AVISO.get()) {
      aviso(&nombre, Evento::Archivos(rutas));
    }
    return 0;
  }
  if let Some((nombre, evento)) = interpretar(hwnd, msg) {
    if let Some(aviso) = AVISO.get() {
      aviso(&nombre, evento);
    }
  }
  DefWindowProcW(hwnd, msg, wp, lp)
}

const CLASE: &str = "akari-burbuja";

/// Una vez: la clase de ventana y a quién avisar de los eventos.
pub fn iniciar(aviso: Aviso) {
  let _ = AVISO.set(aviso);
  unsafe {
    let clase = ancho(CLASE);
    let wc = WNDCLASSW {
      style: CS_DBLCLKS,
      lpfnWndProc: Some(procedimiento),
      cbClsExtra: 0,
      cbWndExtra: 0,
      hInstance: GetModuleHandleW(std::ptr::null()),
      hIcon: std::ptr::null_mut(),
      hCursor: LoadCursorW(std::ptr::null_mut(), IDC_ARROW),
      hbrBackground: std::ptr::null_mut(),
      lpszMenuName: std::ptr::null(),
      lpszClassName: clase.as_ptr(),
    };
    RegisterClassW(&wc);
  }
}

pub fn crear(nombre: &str) -> HWND {
  unsafe {
    let hwnd = CreateWindowExW(
      WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
      ancho(CLASE).as_ptr(),
      ancho("akari").as_ptr(),
      WS_POPUP,
      0,
      0,
      1,
      1,
      std::ptr::null_mut(),
      std::ptr::null_mut(),
      GetModuleHandleW(std::ptr::null()),
      std::ptr::null(),
    );
    if let Ok(mut v) = VENTANAS.lock() {
      v.get_or_insert_with(HashMap::new)
        .insert(hwnd as isize, (nombre.to_string(), Raton::default()));
    }
    DragAcceptFiles(hwnd, 1); // soltar archivos sobre la burbuja cerrada
    hwnd
  }
}

/// Pone el dibujo en la ventana (con su transparencia) en (x, y) físicos de la pantalla.
pub fn pintar(hwnd: HWND, x: i32, y: i32, px: &Pixmap) {
  let (w, h) = (px.width() as i32, px.height() as i32);
  unsafe {
    let pantalla = GetDC(std::ptr::null_mut());
    let memoria = CreateCompatibleDC(pantalla);
    let mut info: BITMAPINFO = std::mem::zeroed();
    info.bmiHeader = BITMAPINFOHEADER {
      biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
      biWidth: w,
      biHeight: -h, // de arriba abajo
      biPlanes: 1,
      biBitCount: 32,
      biCompression: BI_RGB,
      ..std::mem::zeroed()
    };
    let mut bits: *mut core::ffi::c_void = std::ptr::null_mut();
    let mapa = CreateDIBSection(memoria, &info, DIB_RGB_COLORS, &mut bits, std::ptr::null_mut(), 0);
    if !mapa.is_null() && !bits.is_null() {
      // tiny-skia: RGBA premultiplicado → Windows: BGRA premultiplicado
      let destino = std::slice::from_raw_parts_mut(bits as *mut u8, (w * h * 4) as usize);
      for (d, o) in destino.chunks_exact_mut(4).zip(px.data().chunks_exact(4)) {
        d[0] = o[2];
        d[1] = o[1];
        d[2] = o[0];
        d[3] = o[3];
      }
      let anterior = SelectObject(memoria, mapa);
      let posicion = POINT { x, y };
      let tamano = SIZE { cx: w, cy: h };
      let origen = POINT { x: 0, y: 0 };
      let mezcla = BLENDFUNCTION {
        BlendOp: AC_SRC_OVER as u8,
        BlendFlags: 0,
        SourceConstantAlpha: 255,
        AlphaFormat: AC_SRC_ALPHA as u8,
      };
      UpdateLayeredWindow(
        hwnd, pantalla, &posicion, &tamano, memoria, &origen, 0, &mezcla, ULW_ALPHA,
      );
      SelectObject(memoria, anterior);
      DeleteObject(mapa);
    }
    DeleteDC(memoria);
    ReleaseDC(std::ptr::null_mut(), pantalla);
  }
}

pub fn mover(hwnd: HWND, x: i32, y: i32) {
  unsafe { SetWindowPos(hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE) };
}

pub fn mostrar(hwnd: HWND, si: bool) {
  unsafe { ShowWindow(hwnd, if si { SW_SHOWNOACTIVATE } else { SW_HIDE }) };
}
