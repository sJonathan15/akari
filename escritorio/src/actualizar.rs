//! Actualizaciones de la app: el plugin updater de Tauri con el `latest.json` firmado de GitHub
//! Releases.
//!
//! Quién decide si hay versión nueva es el servicio (akari/actualizacion.py: una vez al día, canal
//! estable o beta, "actualizar": false lo apaga, «Ahora no» la pospone). Esta app solo mira su
//! `/api/estado` de vez en cuando y, si trae `actualizacion` sin posponer, pide el `latest.json`
//! de esa release. El plugin comprueba la firma con la clave pública de `tauri.conf.json` (la
//! privada solo está en los secretos del CI), así que nada sin firmar se instala. Aviso «Hay una
//! versión nueva» con Actualizar / Ahora no.
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use serde_json::Value;
use tauri::AppHandle;
use tauri_plugin_updater::UpdaterExt;

use crate::servicio;

const REPO: &str = "https://github.com/sJonathan15/akari";
/// para no preguntar dos veces a la vez (el aviso y el botón del panel)
static OCUPADO: AtomicBool = AtomicBool::new(false);

fn es() -> bool {
  servicio::pedir("GET", "/api/estado", None)
    .and_then(|t| serde_json::from_str::<Value>(&t).ok())
    .map(|e| e["idioma"].as_str() != Some("en"))
    .unwrap_or(true)
}

/// La versión nueva que anuncia el servicio, si la hay y no se pospuso.
fn anunciada() -> Option<(String, bool)> {
  let estado: Value = serde_json::from_str(&servicio::pedir("GET", "/api/estado", None)?).ok()?;
  let a = &estado["actualizacion"];
  let version = a["version"].as_str()?.to_string();
  Some((version, a["pospuesta"].as_bool() == Some(true)))
}

/// Cada media hora mira si el servicio anuncia una versión nueva (la consulta es local y barata).
pub fn vigilar(app: AppHandle) {
  if !firmada(&app) {
    return; // compilada sin clave pública (desarrollo): no hay cómo comprobar la firma
  }
  std::thread::spawn(move || loop {
    std::thread::sleep(Duration::from_secs(120));
    if let Some((version, false)) = anunciada() {
      ofrecer(&app, &version, true);
    }
    std::thread::sleep(Duration::from_secs(1800 - 120));
  });
}

fn firmada(app: &AppHandle) -> bool {
  app
    .config()
    .plugins
    .0
    .get("updater")
    .and_then(|u| u["pubkey"].as_str())
    .map(|k| !k.trim().is_empty())
    .unwrap_or(false)
}

/// Busca el `latest.json` de esa versión; si está y su firma es buena, pregunta (o, desde el
/// botón del panel, instala directamente).
pub fn ofrecer(app: &AppHandle, version: &str, preguntar: bool) {
  if OCUPADO.swap(true, Ordering::SeqCst) {
    return;
  }
  let resultado = intentar(app, version, preguntar);
  if let Err(e) = resultado {
    eprintln!("akari: actualizar: {e}");
  }
  OCUPADO.store(false, Ordering::SeqCst);
}

fn intentar(app: &AppHandle, version: &str, preguntar: bool) -> Result<(), String> {
  let url = format!("{REPO}/releases/download/v{version}/latest.json");
  let actualizador = app
    .updater_builder()
    .endpoints(vec![url.parse().map_err(|e| format!("{e}"))?])
    .map_err(|e| e.to_string())?
    .build()
    .map_err(|e| e.to_string())?;
  let Some(nueva) = tauri::async_runtime::block_on(actualizador.check()).map_err(|e| e.to_string())? else {
    return Ok(()); // ya es esta versión (o más nueva)
  };
  let es = es();
  if preguntar {
    let actual = app.package_info().version.to_string();
    match aviso(&nueva.version, &actual, es) {
      Respuesta::Actualizar => {}
      Respuesta::AhoraNo => {
        // lo mismo que «Ahora no» del panel: no se vuelve a avisar de esta versión
        servicio::pedir("POST", "/api/actualizacion", Some(r#"{"accion":"ahora-no"}"#));
        return Ok(());
      }
    }
  }
  // baja el instalador, comprueba la firma y lo abre; en Windows la app se cierra para que el
  // instalador (modo pasivo: solo una barra de progreso) reemplace sus archivos
  tauri::async_runtime::block_on(nueva.download_and_install(|_, _| {}, || {})).map_err(|e| e.to_string())?;
  app.restart();
}

enum Respuesta {
  Actualizar,
  AhoraNo,
}

#[cfg(not(windows))]
fn aviso(nueva: &str, actual: &str, _es: bool) -> Respuesta {
  // en Linux la app de escritorio es la de app/ (Electron); esta solo se usa para probar
  eprintln!("akari: hay una versión nueva: {nueva} (esta: {actual})");
  Respuesta::AhoraNo
}

/// Un diálogo de Windows con dos botones: Actualizar / Ahora no (TaskDialog; si no está, un
/// MessageBox de Sí / No con la misma pregunta).
#[cfg(windows)]
fn aviso(nueva: &str, actual: &str, es: bool) -> Respuesta {
  use windows_sys::Win32::UI::Controls::{TASKDIALOGCONFIG, TASKDIALOG_BUTTON, TDF_ALLOW_DIALOG_CANCELLATION};
  use windows_sys::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryW};
  use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, IDYES, MB_ICONINFORMATION, MB_SETFOREGROUND, MB_TOPMOST, MB_YESNO};

  let ancho = |s: &str| s.encode_utf16().chain(Some(0)).collect::<Vec<u16>>();
  let t = |a: &str, b: &str| if es { a.to_string() } else { b.to_string() };
  let titulo = ancho("akari");
  let principal = ancho(&t("Hay una versión nueva", "A new version is available"));
  let detalle = ancho(&t(
    &format!("akari {nueva} (tienes la {actual}). Tu configuración se conserva."),
    &format!("akari {nueva} (you have {actual}). Your settings are kept."),
  ));
  let si = ancho(&t("Actualizar", "Update"));
  let no = ancho(&t("Ahora no", "Not now"));
  unsafe {
    let comctl = LoadLibraryW(ancho("comctl32.dll").as_ptr());
    let funcion = if comctl.is_null() {
      None
    } else {
      GetProcAddress(comctl, c"TaskDialogIndirect".as_ptr() as *const u8)
    };
    if let Some(f) = funcion {
      type Dialogo = unsafe extern "system" fn(*const TASKDIALOGCONFIG, *mut i32, *mut i32, *mut i32) -> i32;
      let dialogo: Dialogo = std::mem::transmute(f);
      let botones = [
        TASKDIALOG_BUTTON { nButtonID: 100, pszButtonText: si.as_ptr() },
        TASKDIALOG_BUTTON { nButtonID: 101, pszButtonText: no.as_ptr() },
      ];
      let mut c: TASKDIALOGCONFIG = std::mem::zeroed();
      c.cbSize = std::mem::size_of::<TASKDIALOGCONFIG>() as u32;
      c.dwFlags = TDF_ALLOW_DIALOG_CANCELLATION;
      c.pszWindowTitle = titulo.as_ptr();
      c.pszMainInstruction = principal.as_ptr();
      c.pszContent = detalle.as_ptr();
      c.cButtons = botones.len() as u32;
      c.pButtons = botones.as_ptr();
      c.nDefaultButton = 100;
      let mut elegido = 0;
      if dialogo(&c, &mut elegido, std::ptr::null_mut(), std::ptr::null_mut()) == 0 {
        return if elegido == 100 { Respuesta::Actualizar } else { Respuesta::AhoraNo };
      }
    }
    let pregunta = ancho(&format!(
      "{}\n\n{}\n\n{}",
      t("Hay una versión nueva", "A new version is available"),
      String::from_utf16_lossy(&detalle[..detalle.len() - 1]),
      t("¿Actualizar ahora?", "Update now?")
    ));
    let r = MessageBoxW(
      std::ptr::null_mut(),
      pregunta.as_ptr(),
      titulo.as_ptr(),
      MB_YESNO | MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND,
    );
    if r == IDYES {
      Respuesta::Actualizar
    } else {
      Respuesta::AhoraNo
    }
  }
}
