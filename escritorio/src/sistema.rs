//! Lo propio de Windows: atar el servicio al cierre de la app (job object), iniciar con
//! Windows (HKCU\…\Run), mover y redimensionar una ventana de una sola vez, sacarla de
//! Alt+Tab y bajar la memoria de WebView2 de las burbujas cerradas.
#![cfg(windows)]
use std::os::windows::io::AsRawHandle;
use std::process::Child;

use windows_sys::Win32::Foundation::{HANDLE, HWND};
use windows_sys::Win32::System::JobObjects::{
  AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
  JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows_sys::Win32::System::Registry::{
  RegDeleteKeyValueW, RegGetValueW, RegSetKeyValueW, HKEY_CURRENT_USER, REG_SZ, RRF_RT_REG_SZ,
};
use windows_sys::Win32::UI::WindowsAndMessaging::{
  GetWindowLongPtrW, SetWindowLongPtrW, SetWindowPos, GWL_EXSTYLE, SWP_NOACTIVATE, SWP_NOOWNERZORDER, SWP_NOZORDER,
  WS_EX_APPWINDOW, WS_EX_TOOLWINDOW,
};

const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const VALOR: &str = "akari";

fn ancho(texto: &str) -> Vec<u16> {
  texto.encode_utf16().chain(std::iter::once(0)).collect()
}

/// El servicio (y lo que él lance, como PowerShell) muere con la app aunque esta se caiga.
pub fn atar_al_cierre(hijo: &Child) {
  unsafe {
    let job: HANDLE = CreateJobObjectW(std::ptr::null(), std::ptr::null());
    if job.is_null() {
      return;
    }
    let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    SetInformationJobObject(
      job,
      JobObjectExtendedLimitInformation,
      &info as *const _ as *const _,
      std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
    );
    AssignProcessToJobObject(job, hijo.as_raw_handle() as HANDLE);
    // el handle del job se deja abierto a propósito: al cerrarse el proceso, Windows cierra
    // el job y con él al servicio
  }
}

pub fn autoarranque() -> bool {
  unsafe {
    let mut largo: u32 = 0;
    RegGetValueW(
      HKEY_CURRENT_USER,
      ancho(RUN).as_ptr(),
      ancho(VALOR).as_ptr(),
      RRF_RT_REG_SZ,
      std::ptr::null_mut(),
      std::ptr::null_mut(),
      &mut largo,
    ) == 0
  }
}

pub fn poner_autoarranque(activar: bool) {
  unsafe {
    if !activar {
      RegDeleteKeyValueW(HKEY_CURRENT_USER, ancho(RUN).as_ptr(), ancho(VALOR).as_ptr());
      return;
    }
    let Ok(exe) = std::env::current_exe() else { return };
    let valor = ancho(&format!("\"{}\"", exe.display()));
    RegSetKeyValueW(
      HKEY_CURRENT_USER,
      ancho(RUN).as_ptr(),
      ancho(VALOR).as_ptr(),
      REG_SZ,
      valor.as_ptr() as *const _,
      (valor.len() * 2) as u32,
    );
  }
}

/// Posición y tamaño (píxeles físicos) en una sola llamada: sin parpadeo entre mover y estirar.
pub fn colocar(hwnd: HWND, x: i32, y: i32, w: i32, h: i32) {
  unsafe {
    SetWindowPos(
      hwnd,
      std::ptr::null_mut(),
      x,
      y,
      w,
      h,
      SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
    );
  }
}

/// Ventana de herramienta: no sale en la barra de tareas ni en Alt+Tab.
pub fn herramienta(hwnd: HWND) {
  unsafe {
    let estilo = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
    SetWindowLongPtrW(
      hwnd,
      GWL_EXSTYLE,
      (estilo | WS_EX_TOOLWINDOW as isize) & !(WS_EX_APPWINDOW as isize),
    );
  }
}

/// WebView2 con poca memoria mientras la burbuja está cerrada (solo se ve su cabecera).
pub fn memoria_baja<R: tauri::Runtime>(ventana: &tauri::WebviewWindow<R>, baja: bool) {
  use webview2_com::Microsoft::Web::WebView2::Win32::{
    ICoreWebView2_19, COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL_LOW, COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL_NORMAL,
  };
  use windows::core::Interface;
  let _ = ventana.with_webview(move |w| unsafe {
    if let Ok(core) = w.controller().CoreWebView2() {
      if let Ok(c19) = core.cast::<ICoreWebView2_19>() {
        let _ = c19.SetMemoryUsageTargetLevel(if baja {
          COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL_LOW
        } else {
          COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL_NORMAL
        });
      }
    }
  });
}
