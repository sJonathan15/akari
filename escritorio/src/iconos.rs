//! Iconos de Material Symbols (Apache-2.0) para las cabeceras nativas. Generado por
//! herramientas/iconos_nativos.py: no editar a mano.
pub const FUENTE: &[u8] = include_bytes!("../recursos/iconos.ttf");

pub const TABLA: &[(&str, char)] = &[
  ("auto_awesome", '\u{e65f}'),
  ("auto_stories", '\u{e666}'),
  ("bolt", '\u{ea0b}'),
  ("build", '\u{e869}'),
  ("chat", '\u{e0b7}'),
  ("construction", '\u{ea3c}'),
  ("description", '\u{e873}'),
  ("devices", '\u{e1b1}'),
  ("devices_other", '\u{e337}'),
  ("diamond", '\u{ead5}'),
  ("folder", '\u{e2c7}'),
  ("graphic_eq", '\u{e1b8}'),
  ("handyman", '\u{f10b}'),
  ("headphones", '\u{e310}'),
  ("key", '\u{e73c}'),
  ("keyboard", '\u{e312}'),
  ("mic", '\u{e029}'),
  ("mouse", '\u{e323}'),
  ("music_note", '\u{e3a1}'),
  ("notes", '\u{e26c}'),
  ("progress_activity", '\u{e9d0}'),
  ("psychology", '\u{ea4a}'),
  ("radio_button_checked", '\u{e837}'),
  ("record_voice_over", '\u{e91f}'),
  ("smart_toy", '\u{f06c}'),
  ("smartphone", '\u{e0d4}'),
  ("spa", '\u{eb4c}'),
  ("sports_esports", '\u{e6ec}'),
  ("swap_horiz", '\u{e8d4}'),
  ("system_update", '\u{e62a}'),
  ("terminal", '\u{eb8e}'),
  ("translate", '\u{e8e2}'),
  ("widgets", '\u{e1bd}'),
];

pub fn icono(nombre: &str) -> char {
  TABLA.iter().find(|(n, _)| *n == nombre).or_else(|| TABLA.iter().find(|(n, _)| *n == "widgets")).map(|(_, c)| *c).unwrap_or('?')
}
