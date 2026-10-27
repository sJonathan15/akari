//! El servicio de akari (Python, 127.0.0.1:47830): hablarle por HTTP y, si no está corriendo,
//! arrancarlo oculto con el Python embebido. En Windows el proceso queda dentro de un "job"
//! que el sistema cierra junto con la app, así no queda nada colgado aunque la app se caiga.
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

pub const PUERTO: u16 = 47830;
pub const URL: &str = "http://127.0.0.1:47830/";
pub const APP_ID: &str = "io.github.sjonathan15.akari";

/// Petición HTTP/1.0 mínima (el servicio solo habla con 127.0.0.1): el cuerpo si responde 200.
pub fn pedir(metodo: &str, ruta: &str, cuerpo: Option<&str>) -> Option<String> {
  let direccion = SocketAddr::from(([127, 0, 0, 1], PUERTO));
  let mut s = TcpStream::connect_timeout(&direccion, Duration::from_millis(800)).ok()?;
  s.set_read_timeout(Some(Duration::from_secs(5))).ok()?;
  let cuerpo = cuerpo.unwrap_or("");
  let pedido = format!(
    "{metodo} {ruta} HTTP/1.0\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{cuerpo}",
    cuerpo.len()
  );
  s.write_all(pedido.as_bytes()).ok()?;
  let mut respuesta = Vec::new();
  s.read_to_end(&mut respuesta).ok()?;
  let texto = String::from_utf8_lossy(&respuesta);
  let (cabecera, resto) = texto.split_once("\r\n\r\n")?;
  if !cabecera.starts_with("HTTP/1.") || cabecera.split_whitespace().nth(1) != Some("200") {
    return None;
  }
  Some(resto.to_string())
}

pub fn vivo() -> bool {
  pedir("GET", "/api/estado", None).is_some()
}

/// Dónde están el servicio (servicio/akari, servicio/web…) y el intérprete: junto al .exe
/// instalado o, compilando desde el repositorio, la carpeta de arriba y el Python del sistema.
pub fn rutas(recursos: Option<PathBuf>) -> (PathBuf, PathBuf) {
  if let Some(r) = recursos.filter(|r| r.join("servicio").join("bin").join("akari.py").exists()) {
    let raiz = r.join("servicio");
    let python = r
      .join("python")
      .join(if cfg!(windows) { "pythonw.exe" } else { "python3" });
    if python.exists() {
      return (raiz, python);
    }
    return (raiz, PathBuf::from(if cfg!(windows) { "pythonw" } else { "python3" }));
  }
  let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
    .parent()
    .unwrap_or(Path::new(".."))
    .to_path_buf();
  (repo, PathBuf::from(if cfg!(windows) { "pythonw" } else { "python3" }))
}

/// `python bin/akari.py <args>` sin ventana de consola.
pub fn orden(raiz: &Path, python: &Path, args: &[&str]) -> Command {
  let mut c = Command::new(python);
  c.arg(raiz.join("bin").join("akari.py")).args(args);
  c.env("AKARI_APP_ID", APP_ID)
    .stdin(Stdio::null())
    .stdout(Stdio::null())
    .stderr(Stdio::null());
  #[cfg(windows)]
  {
    use std::os::windows::process::CommandExt;
    c.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
  }
  c
}

/// Arranca el servicio si no responde; espera hasta 15 s a que conteste.
pub fn asegurar(raiz: &Path, python: &Path) -> Option<Child> {
  if vivo() {
    return None;
  }
  let mut c = orden(raiz, python, &["servicio"]);
  // revisar como mucho cada 5 s; con todo cerrado, el ritmo de reposo (akari/servidor.py)
  c.env("AKARI_INTERVALO_MIN", "5");
  let hijo = c.spawn().ok()?;
  #[cfg(windows)]
  crate::sistema::atar_al_cierre(&hijo);
  let inicio = Instant::now();
  while inicio.elapsed() < Duration::from_secs(15) && !vivo() {
    std::thread::sleep(Duration::from_millis(200));
  }
  Some(hijo)
}
