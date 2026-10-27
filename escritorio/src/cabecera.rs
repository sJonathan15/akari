//! Píldora de un grupo cerrado, dibujada sin navegador (tiny-skia + ab_glyph).
//!
//! Con todo cerrado no hace falta WebView2: se ve solo la píldora del grupo (AGENTS.md: Equipo,
//! IA, Archivos) con un chip-resumen por pieza (el % libre, las baterías, las habilidades, los
//! documentos…), lo mismo que `htmlCabecera`/`htmlChip` de web/app.js, a partir de
//! /api/estado. Al abrir, la página toma el relevo. Una pieza que no se conoce aquí sale con
//! su icono (lo da /api/burbujas).
use ab_glyph::{point, Font, FontArc, PxScale, ScaleFont};
use serde_json::Value;
use tiny_skia::{Color, FillRule, Paint, PathBuilder, Pixmap, PixmapPaint, Stroke, Transform};

use crate::iconos;

pub struct Fuentes {
  pub texto: FontArc,
  pub medio: FontArc,
  pub mono: FontArc,
  pub iconos: FontArc,
  pub simbolos: Option<FontArc>,
}

impl Fuentes {
  /// Desde archivos de fuentes (en Windows, los de C:\Windows\Fonts).
  pub fn cargar(texto: &[&str], medio: &[&str], mono: &[&str], simbolos: &[&str]) -> Option<Fuentes> {
    let leer = |rutas: &[&str]| {
      rutas
        .iter()
        .find_map(|r| std::fs::read(r).ok().and_then(|b| FontArc::try_from_vec(b).ok()))
    };
    let texto = leer(texto)?;
    Some(Fuentes {
      medio: leer(medio).unwrap_or_else(|| texto.clone()),
      mono: leer(mono).unwrap_or_else(|| texto.clone()),
      simbolos: leer(simbolos),
      iconos: FontArc::try_from_slice(iconos::FUENTE).ok()?,
      texto,
    })
  }
}

/// Lo que hace falta saber del grupo para dibujarlo.
pub struct Forma<'a> {
  pub piezas: &'a [crate::forma::Pieza],
  pub ancho: f64, // largo de la píldora cerrada (horizontal)
  pub vertical: bool,
  pub borde: &'a str,
  pub pegada_arriba: bool,
  pub pegada_abajo: bool,
}

const ALTO: f32 = 38.0;

#[derive(Clone, Copy)]
struct Rgba(u8, u8, u8, u8);

fn color(tema: &Value, clave: &str, defecto: &str) -> Rgba {
  let hexa = tema[clave]
    .as_str()
    .unwrap_or(defecto)
    .trim_start_matches('#')
    .to_string();
  let v = u32::from_str_radix(&hexa, 16).unwrap_or(0xb7c4ff);
  Rgba((v >> 16) as u8, (v >> 8) as u8, v as u8, 255)
}
fn alfa(c: Rgba, a: f32) -> Rgba {
  Rgba(c.0, c.1, c.2, (a * 255.0) as u8)
}
fn pintura(c: Rgba) -> Paint<'static> {
  let mut p = Paint::default();
  p.set_color(Color::from_rgba8(c.0, c.1, c.2, c.3));
  p.anti_alias = true;
  p
}

/// Una pieza de la fila (de izquierda a derecha).
enum Pieza {
  Anillo {
    valor: f32,
    color: Rgba,
  },
  Texto {
    texto: String,
    tam: f32,
    fuente: u8,
    color: Rgba,
  }, // fuente: 0 texto, 1 medio, 2 mono
  Icono {
    nombre: String,
    tam: f32,
    color: Rgba,
  },
  Chip {
    icono: String,
    texto: String,
    color: Rgba,
  },
  Punto {
    color: Rgba,
  },
  /// el muñequito del asistente (el mismo dibujo de pixelesMuneco en web/app.js, quieto)
  Muneco {
    estado: String,
  },
  Relleno,
  /// grupo que se reparte el ancho con los demás grupos (los dispositivos)
  Grupo(Vec<Pieza>),
}

struct Paleta {
  primario: Rgba,
  sobre_primario: Rgba,
  terciario: Rgba,
  error: Rgba,
  exito: Rgba,
  secundario: Rgba,
  superficie: Rgba,
  texto_var: Rgba,
  contenedor_max: Rgba,
  contorno: Rgba,
  contorno_var: Rgba,
}

fn paleta(estado: &Value) -> Paleta {
  let t = &estado["tema"]["colores"];
  Paleta {
    primario: color(t, "primary", "#b7c4ff"),
    sobre_primario: color(t, "onPrimary", "#1f2c61"),
    terciario: color(t, "tertiary", "#f1b3e6"),
    error: color(t, "error", "#ffb4ab"),
    exito: color(t, "success", "#b5ccba"),
    secundario: color(t, "secondary", "#c1c5e0"),
    superficie: color(t, "surface", "#131317"),
    texto_var: color(t, "onSurfaceVariant", "#c6c5d1"),
    contenedor_max: color(t, "surfaceContainerHighest", "#343438"),
    contorno: color(t, "outline", "#8f909a"),
    contorno_var: color(t, "outlineVariant", "#45464f"),
  }
}

/// "2 h 05", "45 min", "3 d 4 h" (como `cuenta` de web/app.js)
pub fn cuenta(seg: f64) -> String {
  let seg = seg.max(0.0).round() as i64;
  let (h, m) = (seg / 3600, (seg % 3600) / 60);
  if h >= 24 {
    format!("{} d {} h", h / 24, h % 24)
  } else if h > 0 {
    format!("{h} h {m:02}")
  } else {
    format!("{m} min")
  }
}

fn nivel(d: &Value) -> &'static str {
  if d["conectado"].as_bool() != Some(true) {
    return "nada";
  }
  match d["bateria"].as_f64() {
    None => "cable",
    Some(b) if b <= 20.0 => "bajo",
    Some(b) if b <= 50.0 => "medio",
    _ => "ok",
  }
}

/// El chip-resumen de una pieza y si pide atención. `entero`: la pieza sola en su grupo, con el
/// ancho de toda la píldora (como `htmlChip(id, true)`); si no, el chip corto de las pestañas.
fn chip(pieza: &crate::forma::Pieza, estado: &Value, ahora: f64, p: &Paleta, entero: bool) -> (Vec<Pieza>, bool) {
  let es = estado["idioma"].as_str() != Some("en");
  let t = |a: &str, b: &str| if es { a.to_string() } else { b.to_string() };
  let tenue = |texto: String| Pieza::Texto {
    texto,
    tam: 11.0,
    fuente: 0,
    color: p.texto_var,
  };
  let num = |texto: String, color: Rgba, chico: bool| Pieza::Texto {
    texto,
    tam: if chico { 12.0 } else if entero { 16.0 } else { 15.0 },
    fuente: 1,
    color,
  };
  let icono = |nombre: &str, color: Rgba| Pieza::Icono {
    nombre: nombre.into(),
    tam: 19.0,
    color,
  };
  let color_libre = |v: &Value| match v["libre"].as_f64() {
    None => p.contorno,
    Some(l) if l <= 10.0 => p.error,
    Some(l) if l <= 25.0 => p.terciario,
    _ => p.primario,
  };
  let lista = |v: &Value| v.as_array().cloned().unwrap_or_default();
  let cuantos = |v: &Value, estados: &[&str]| {
    lista(v)
      .iter()
      .filter(|x| estados.contains(&x["estado"].as_str().unwrap_or("")))
      .count()
  };
  match pieza.nombre.as_str() {
    "uso" => {
      let ia = &estado["ia"];
      let provs: Vec<&str> = ["claude", "codex"].into_iter().filter(|x| !ia[*x].is_null()).collect();
      let prov = ia["principal"]
        .as_str()
        .filter(|x| provs.contains(x))
        .or(provs.first().copied())
        .unwrap_or("");
      let datos = &ia[prov];
      let v5 = &datos["limites"]["cinco_horas"];
      let col = color_libre(v5);
      let trabajando = datos["cinta"][0]["t"]
        .as_f64()
        .map(|x| ahora - x < 25.0)
        .unwrap_or(false);
      let punto = Pieza::Punto {
        color: if trabajando { p.terciario } else { p.contorno_var },
      };
      let mut l = vec![
        Pieza::Anillo {
          valor: v5["libre"].as_f64().map(|x| x as f32 / 100.0).unwrap_or(0.0),
          color: col,
        },
        num(
          v5["libre"].as_f64().map(|x| format!("{}%", x.round())).unwrap_or("—".into()),
          col,
          false,
        ),
      ];
      if !entero {
        l.push(punto);
        return (l, false);
      }
      l.push(tenue(if prov.is_empty() {
        t("sin Claude ni Codex", "no Claude or Codex")
      } else if v5.is_null() {
        t("sin lectura", "no data")
      } else {
        t("libre", "left")
      }));
      l.push(Pieza::Relleno);
      let modelo = datos["modelo_actual"].as_str().unwrap_or("");
      let fam = if modelo.is_empty() {
        ""
      } else if prov == "codex" {
        "GPT"
      } else {
        modelo.split(' ').next().unwrap_or("")
      };
      if !fam.is_empty() {
        let (icono, c) = match fam {
          "Opus" => ("diamond", p.primario),
          "Fable" => ("auto_stories", p.terciario),
          "Sonnet" => ("music_note", p.secundario),
          "Haiku" => ("spa", p.exito),
          "GPT" => ("terminal", p.exito),
          _ => ("smart_toy", p.texto_var),
        };
        l.push(Pieza::Chip {
          icono: icono.into(),
          texto: fam.into(),
          color: c,
        });
      }
      if let Some(r) = v5["reinicia"].as_f64() {
        l.push(Pieza::Texto {
          texto: cuenta(r - ahora),
          tam: 11.0,
          fuente: 2,
          color: p.texto_var,
        });
      }
      l.push(punto);
      (l, false)
    }
    "dispositivos" => {
      let lista = lista(&estado["dispositivos"]["dispositivos"]);
      let alerta = lista
        .iter()
        .any(|d| nivel(d) == "bajo" && d["cargando"].as_bool() != Some(true));
      if lista.is_empty() {
        return (
          vec![
            Pieza::Relleno,
            tenue(t("Sin periféricos todavía", "No devices yet")),
            Pieza::Relleno,
          ],
          false,
        );
      }
      let grupos = lista
        .iter()
        .take(4)
        .map(|d| {
          let nv = nivel(d);
          let c = match nv {
            "ok" => p.exito,
            "medio" => p.terciario,
            "bajo" => p.error,
            "cable" => p.primario,
            _ => p.contorno,
          };
          let icono = match d["tipo"].as_str().unwrap_or("") {
            "raton" => "mouse",
            "teclado" => "keyboard",
            "audifonos" => "headphones",
            "celular" => "smartphone",
            "mando" => "sports_esports",
            _ => "devices_other",
          };
          let texto = if nv == "nada" {
            "—".to_string()
          } else if let Some(b) = d["bateria"].as_f64() {
            format!("{}%", b.round())
          } else if d["conexion"].as_str().unwrap_or("").contains("USB") {
            "USB".into()
          } else {
            "OK".into()
          };
          let carga = if d["cargando"].as_bool() == Some(true) {
            "⚡"
          } else {
            ""
          };
          Pieza::Grupo(vec![
            Pieza::Icono {
              nombre: icono.into(),
              tam: 17.0,
              color: c,
            },
            Pieza::Texto {
              texto: format!("{texto}{carga}"),
              tam: 11.0,
              fuente: 2,
              color: if nv == "nada" { p.contorno } else { p.texto_var },
            },
          ])
        })
        .collect();
      (grupos, alerta)
    }
    "asistente" => {
      let a = &estado["asistente"];
      let error = a["historial"][0]["error"].as_bool() == Some(true)
        || a["historial"][0]["error"].is_string();
      let fase = if a.is_null() {
        "pausa".to_string()
      } else if error && a["historial"][0]["t"].as_f64().map(|x| ahora - x < 8.0).unwrap_or(false) {
        "error".to_string()
      } else {
        a["estado"].as_str().unwrap_or("pausa").to_string()
      };
      (vec![Pieza::Muneco { estado: fase }], false)
    }
    "modelos" => {
      let m = &estado["modelos"];
      let listo = m["listo"].as_bool() == Some(true);
      let d = &m["ollama"]["descarga"];
      let bajando = d.is_object() && d["error"].is_null() && d["pct"].as_f64().unwrap_or(100.0) < 100.0;
      let nombre = if bajando {
        "progress_activity"
      } else if listo {
        "psychology"
      } else {
        "key"
      };
      let mut l = vec![icono(nombre, if listo { p.primario } else { p.terciario })];
      if entero {
        let texto = if !listo {
          m["motivo"].as_str().unwrap_or("").to_string()
        } else if m["modo"].as_str() == Some("local") {
          m["local"]["texto"]
            .as_str()
            .filter(|x| !x.is_empty())
            .or(m["local"]["vision"].as_str())
            .unwrap_or("")
            .to_string()
        } else {
          m["modelo"].as_str().unwrap_or("").to_string()
        };
        l.push(tenue(texto));
      }
      (l, false)
    }
    "habilidades" => {
      let h = &estado["habilidades"];
      let mut l = vec![
        icono("auto_awesome", p.primario),
        num(h["total"].as_i64().map(|n| n.to_string()).unwrap_or("—".into()), p.texto_var, false),
      ];
      if entero {
        l.push(tenue(t("habilidades", "skills")));
      }
      (l, false)
    }
    "herramientas" => {
      let h = &estado["herramientas"];
      let texto = match (h["instaladas"].as_i64(), h["total"].as_i64()) {
        (Some(a), Some(b)) => format!("{a}/{b}"),
        _ => "—".into(),
      };
      let mut l = vec![icono("construction", p.primario), num(texto, p.texto_var, !entero)];
      if entero {
        l.push(tenue(t("herramientas", "tools")));
      }
      (l, false)
    }
    "documentos" => {
      let d = &estado["documentos"];
      let trabajos = lista(&d["trabajos"]);
      let activos = cuantos(&d["trabajos"], &["cola", "convirtiendo"]);
      let listo = d["listo"].as_bool() == Some(true);
      let ic = icono("swap_horiz", if d.is_object() && !listo { p.contorno } else { p.primario });
      if !entero {
        let n = if d.is_null() {
          "—".to_string()
        } else if activos > 0 {
          activos.to_string()
        } else {
          cuantos(&d["trabajos"], &["listo"]).to_string()
        };
        return (vec![ic, num(n, p.texto_var, false)], false);
      }
      let texto = if d.is_null() {
        "—".into()
      } else if !listo {
        t("Conversor sin instalar", "Converter not installed")
      } else if activos > 0 {
        format!("{}{activos}…", t("Convirtiendo ", "Converting "))
      } else if let Some(n) = trabajos.first().and_then(|x| x["nombre"].as_str()) {
        n.to_string()
      } else {
        t("Suelta un documento", "Drop a document")
      };
      (vec![ic, tenue(texto)], false)
    }
    "audio" => {
      let a = &estado["audio"];
      if let Some(desde) = a["grabacion"]["desde"].as_f64() {
        let seg = (ahora - desde).max(0.0) as i64;
        let reloj = if seg >= 3600 {
          format!("{}:{:02}:{:02}", seg / 3600, seg % 3600 / 60, seg % 60)
        } else {
          format!("{}:{:02}", seg / 60, seg % 60)
        };
        return (
          vec![
            icono("radio_button_checked", p.error),
            Pieza::Texto {
              texto: reloj,
              tam: 11.0,
              fuente: 2,
              color: p.error,
            },
          ],
          false,
        );
      }
      let trabajos = lista(&a["trabajos"]);
      let actual = trabajos
        .iter()
        .find(|x| x["estado"].as_str() == Some("transcribiendo"));
      let usa = a["usa"].as_bool().unwrap_or(!a["usa"].is_null());
      let ic = icono("graphic_eq", if a.is_object() && !usa { p.contorno } else { p.primario });
      let n = if a.is_null() {
        num("—".into(), p.texto_var, false)
      } else if let Some(x) = actual {
        let texto = x["pct"].as_f64().map(|v| format!("{}%", v.round())).unwrap_or("…".into());
        num(texto, p.primario, true)
      } else {
        num(cuantos(&a["trabajos"], &["listo"]).to_string(), p.texto_var, false)
      };
      (vec![ic, n], false)
    }
    // una pieza que esta versión no conoce: su icono, centrado
    _ => (vec![Pieza::Relleno, icono(&pieza.icono, p.primario), Pieza::Relleno], false),
  }
}

// ------------------------------------------------------------ dibujo

struct Lienzo<'a> {
  px: &'a mut Pixmap,
  f: &'a Fuentes,
  s: f32, // escala (DPI)
}

impl Lienzo<'_> {
  fn fuente(&self, cual: u8) -> &FontArc {
    match cual {
      1 => &self.f.medio,
      2 => &self.f.mono,
      3 => &self.f.iconos,
      _ => &self.f.texto,
    }
  }
  fn ancho_texto(&self, texto: &str, tam: f32, cual: u8) -> f32 {
    texto
      .chars()
      .map(|c| {
        let (fuente, c) = self.elegir(cual, c);
        let f = fuente.as_scaled(PxScale::from(tam * self.s));
        f.h_advance(fuente.glyph_id(c))
      })
      .sum()
  }
  /// La fuente que tiene el carácter (⚡ suele estar solo en la de símbolos).
  fn elegir(&self, cual: u8, c: char) -> (&FontArc, char) {
    let f = self.fuente(cual);
    if f.glyph_id(c).0 == 0 {
      if let Some(s) = &self.f.simbolos {
        if s.glyph_id(c).0 != 0 {
          return (s, c);
        }
      }
    }
    (f, c)
  }
  fn texto(&mut self, texto: &str, x: f32, cy: f32, tam: f32, cual: u8, c: Rgba) -> f32 {
    let mut x = x;
    for ch in texto.chars() {
      let (fuente, ch) = self.elegir(cual, ch);
      let fuente = fuente.clone();
      let escala = PxScale::from(tam * self.s);
      let f = fuente.as_scaled(escala);
      let base = cy + (f.ascent() + f.descent()) / 2.0;
      let id = fuente.glyph_id(ch);
      if let Some(contorno) = fuente.outline_glyph(id.with_scale_and_position(escala, point(x, base))) {
        let caja = contorno.px_bounds();
        let (ancho, alto) = (self.px.width() as i32, self.px.height() as i32);
        let datos = self.px.data_mut();
        contorno.draw(|gx, gy, cobertura| {
          let (px, py) = (caja.min.x as i32 + gx as i32, caja.min.y as i32 + gy as i32);
          if px < 0 || py < 0 || px >= ancho || py >= alto {
            return;
          }
          let a = cobertura.min(1.0) * c.3 as f32 / 255.0;
          let i = ((py * ancho + px) * 4) as usize;
          // fuente sobre lo que hay (alfa premultiplicado)
          for (k, v) in [c.0, c.1, c.2].into_iter().enumerate() {
            datos[i + k] = (v as f32 * a + datos[i + k] as f32 * (1.0 - a)).round() as u8;
          }
          datos[i + 3] = (255.0 * a + datos[i + 3] as f32 * (1.0 - a)).round() as u8;
        });
      }
      x += f.h_advance(id);
    }
    x
  }
  fn icono(&mut self, nombre: &str, x: f32, cy: f32, tam: f32, c: Rgba) -> f32 {
    let ch = iconos::icono(nombre).to_string();
    self.texto(&ch, x, cy, tam, 3, c)
  }
}

fn ancho_pieza(l: &Lienzo, p: &Pieza) -> f32 {
  let s = l.s;
  match p {
    Pieza::Anillo { .. } => 22.0 * s,
    Pieza::Texto { texto, tam, fuente, .. } => l.ancho_texto(texto, *tam, *fuente),
    Pieza::Icono { tam, .. } => tam * s,
    Pieza::Chip { texto, .. } => 13.0 * s + 3.0 * s + l.ancho_texto(texto, 11.0, 1) + 14.0 * s,
    Pieza::Punto { .. } => 7.0 * s,
    Pieza::Muneco { .. } => 24.0 * s,
    Pieza::Relleno => 0.0,
    Pieza::Grupo(hijos) => {
      hijos.iter().map(|h| ancho_pieza(l, h)).sum::<f32>() + 4.0 * s * (hijos.len().saturating_sub(1)) as f32
    }
  }
}

fn dibujar_pieza(l: &mut Lienzo, p: &Pieza, x: f32, cy: f32, fondo: &Paleta) {
  let s = l.s;
  match p {
    Pieza::Anillo { valor, color } => {
      let (r, grosor) = (9.0 * s, 4.0 * s);
      let (cx, cy2) = (x + 11.0 * s, cy);
      let mut pb = PathBuilder::new();
      pb.push_circle(cx, cy2, r);
      let trazo = Stroke {
        width: grosor,
        ..Default::default()
      };
      if let Some(c) = pb.finish() {
        l.px
          .stroke_path(&c, &pintura(fondo.contenedor_max), &trazo, Transform::identity(), None);
      }
      if *valor > 0.0 {
        // arco desde las 12 en el sentido del reloj
        let mut pb = PathBuilder::new();
        let pasos = 48;
        let fin = valor.min(1.0) * std::f32::consts::TAU;
        for i in 0..=pasos {
          let a = -std::f32::consts::FRAC_PI_2 + fin * i as f32 / pasos as f32;
          let (px, py) = (cx + r * a.cos(), cy2 + r * a.sin());
          if i == 0 {
            pb.move_to(px, py)
          } else {
            pb.line_to(px, py)
          }
        }
        let trazo = Stroke {
          width: grosor,
          line_cap: tiny_skia::LineCap::Round,
          ..Default::default()
        };
        if let Some(a) = pb.finish() {
          l.px
            .stroke_path(&a, &pintura(*color), &trazo, Transform::identity(), None);
        }
      }
    }
    Pieza::Texto {
      texto,
      tam,
      fuente,
      color,
    } => {
      l.texto(texto, x, cy, *tam, *fuente, *color);
    }
    Pieza::Icono { nombre, tam, color } => {
      l.icono(nombre, x, cy, *tam, *color);
    }
    Pieza::Chip { icono, texto, color } => {
      let w = ancho_pieza(l, p);
      let h = 22.0 * s;
      if let Some(r) = redondeado(x, cy - h / 2.0, w, h, [h / 2.0; 4]) {
        l.px.fill_path(
          &r,
          &pintura(alfa(*color, 0.16)),
          FillRule::Winding,
          Transform::identity(),
          None,
        );
      }
      let x = l.icono(icono, x + 7.0 * s, cy, 13.0, *color) + 3.0 * s;
      l.texto(texto, x, cy, 11.0, 1, *color);
    }
    Pieza::Punto { color } => {
      if let Some(c) = PathBuilder::from_circle(x + 3.5 * s, cy, 3.5 * s) {
        l.px
          .fill_path(&c, &pintura(*color), FillRule::Winding, Transform::identity(), None);
      }
    }
    Pieza::Muneco { estado } => {
      // 13 × 14 «píxeles» en 24 × 26 lógicos
      let (pw, ph) = (24.0 * s / 13.0, 26.0 * s / 14.0);
      let y0 = cy - 13.0 * s;
      for (fx, fy, c) in muneco(estado) {
        let col = match c {
          'o' => mezcla(fondo.primario, fondo.superficie, 0.15),
          'b' => fondo.primario,
          'l' => mezcla(fondo.primario, Rgba(255, 255, 255, 255), 0.6),
          'e' | 'm' => fondo.sobre_primario,
          'c' => alfa(fondo.terciario, 0.85),
          'f' => fondo.terciario,
          _ => mezcla(fondo.terciario, Rgba(255, 255, 255, 255), 0.7),
        };
        if let Some(r) = tiny_skia::Rect::from_xywh(x + fx as f32 * pw, y0 + fy as f32 * ph, pw + 0.3, ph + 0.3) {
          l.px.fill_rect(r, &pintura(col), Transform::identity(), None);
        }
      }
    }
    Pieza::Relleno => {}
    Pieza::Grupo(hijos) => {
      let mut x = x;
      for h in hijos {
        dibujar_pieza(l, h, x, cy, fondo);
        x += ancho_pieza(l, h) + 4.0 * s;
      }
    }
  }
}

/// `a` en proporción `k` sobre `b` (como color-mix de CSS).
fn mezcla(a: Rgba, b: Rgba, k: f32) -> Rgba {
  let m = |x: u8, y: u8| (x as f32 * k + y as f32 * (1.0 - k)).round() as u8;
  Rgba(m(a.0, b.0), m(a.1, b.1), m(a.2, b.2), 255)
}

const MUNECO: [&str; 14] = [
  "......F......", ".....fFf.....", ".....fff.....", "......o......", "...ooooooo...", "..obbbbbbbo..",
  ".obllbbbbbbo.", ".oblbbbbbbbo.", ".obbbbbbbbbo.", ".obbbbbbbbbo.", ".obcbbbbbcbo.", "..obbbbbbbo..",
  "...ooooooo...", "...oo...oo...",
];

/// Los píxeles del muñequito según lo que hace el asistente (`pixelesMuneco` sin animar).
fn muneco(estado: &str) -> Vec<(usize, usize, char)> {
  let mut g: Vec<Vec<char>> = MUNECO.iter().map(|f| f.chars().collect()).collect();
  let mut pon = |x: usize, y: usize, c: char| g[y][x] = c;
  match estado {
    "pausa" => [(3, 9), (4, 9), (8, 9), (9, 9)].into_iter().for_each(|(x, y)| pon(x, y, 'e')),
    "pensando" => [(4, 7), (4, 8), (8, 7), (8, 8)].into_iter().for_each(|(x, y)| pon(x, y, 'e')),
    "oyendo" | "confirmando" => [(4, 8), (5, 8), (4, 9), (5, 9), (7, 8), (8, 8), (7, 9), (8, 9)]
      .into_iter()
      .for_each(|(x, y)| pon(x, y, 'e')),
    "error" => [(3, 8), (4, 9), (3, 10), (8, 8), (9, 9), (8, 10)]
      .into_iter()
      .for_each(|(x, y)| pon(x, y, 'e')),
    _ => [(4, 8), (4, 9), (8, 8), (8, 9)].into_iter().for_each(|(x, y)| pon(x, y, 'e')),
  }
  if estado != "error" {
    pon(6, 10, 'm');
  }
  match estado {
    "pausa" => {
      pon(6, 0, '.');
      pon(5, 1, '.');
      pon(7, 1, '.');
      pon(6, 1, 'f');
    }
    "pensando" | "confirmando" => {
      pon(6, 0, '.');
      pon(5, 0, 'F');
    }
    "oyendo" => {
      pon(4, 1, 'f');
      pon(8, 1, 'f');
      pon(5, 0, 'f');
      pon(7, 0, 'f');
    }
    _ => {}
  }
  let mut r = Vec::new();
  for (y, fila) in g.iter().enumerate() {
    for (x, c) in fila.iter().enumerate() {
      if *c != '.' {
        r.push((x, y, *c));
      }
    }
  }
  r
}

/// Rectángulo con cada esquina redondeada a su radio: [arriba izq, arriba der, abajo der, abajo izq].
fn redondeado(x: f32, y: f32, w: f32, h: f32, r: [f32; 4]) -> Option<tiny_skia::Path> {
  let k = 0.552_284_8; // cubica que aproxima un cuarto de círculo
  let mut pb = PathBuilder::new();
  pb.move_to(x + r[0], y);
  pb.line_to(x + w - r[1], y);
  pb.cubic_to(
    x + w - r[1] * (1.0 - k),
    y,
    x + w,
    y + r[1] * (1.0 - k),
    x + w,
    y + r[1],
  );
  pb.line_to(x + w, y + h - r[2]);
  pb.cubic_to(
    x + w,
    y + h - r[2] * (1.0 - k),
    x + w - r[2] * (1.0 - k),
    y + h,
    x + w - r[2],
    y + h,
  );
  pb.line_to(x + r[3], y + h);
  pb.cubic_to(
    x + r[3] * (1.0 - k),
    y + h,
    x,
    y + h - r[3] * (1.0 - k),
    x,
    y + h - r[3],
  );
  pb.line_to(x, y + r[0]);
  pb.cubic_to(x, y + r[0] * (1.0 - k), x + r[0] * (1.0 - k), y, x + r[0], y);
  pb.close();
  pb.finish()
}

/// Recorta un texto con "…" hasta que quepa en `max` píxeles.
fn recortar(l: &Lienzo, texto: &str, tam: f32, fuente: u8, max: f32) -> String {
  if l.ancho_texto(texto, tam, fuente) <= max {
    return texto.to_string();
  }
  let mut letras: Vec<char> = texto.chars().collect();
  while !letras.is_empty() {
    letras.pop();
    let prueba: String = letras.iter().collect::<String>() + "…";
    if l.ancho_texto(&prueba, tam, fuente) <= max {
      return prueba;
    }
  }
  String::new()
}

/// Dibuja las piezas de un chip dentro de su parte [x, x + ancho] de la fila: a lo ancho con
/// separación 8 (pieza sola) o centradas con separación 4 (el chip de una pestaña).
fn dibujar_chip(l: &mut Lienzo, lista: Vec<Pieza>, x: f32, ancho: f32, cy: f32, p: &Paleta, entero: bool) {
  let s = l.s;
  let grupos = lista.iter().filter(|x| matches!(x, Pieza::Grupo(_))).count();
  if grupos > 0 {
    // los dispositivos se reparten el ancho, cada uno centrado en su parte
    let parte = ancho / grupos as f32;
    for (i, g) in lista.iter().enumerate() {
      let gx = x + parte * i as f32 + (parte - ancho_pieza(l, g)) / 2.0;
      dibujar_pieza(l, g, gx, cy, p);
    }
    return;
  }
  let hueco = if entero { 8.0 } else { 4.0 } * s;
  let mut lista = lista;
  let fijos = |l: &Lienzo, lista: &[Pieza]| {
    lista.iter().map(|x| ancho_pieza(l, x)).sum::<f32>() + hueco * (lista.len().saturating_sub(1)) as f32
  };
  // lo que no quepa (p. ej. el nombre de un documento) se recorta
  let sobra = fijos(l, &lista) - ancho;
  if sobra > 0.0 {
    if let Some(Pieza::Texto { texto, tam, fuente, .. }) =
      lista.iter_mut().filter(|x| matches!(x, Pieza::Texto { .. })).last()
    {
      let actual = l.ancho_texto(texto, *tam, *fuente);
      *texto = recortar(l, texto, *tam, *fuente, (actual - sobra).max(0.0));
    }
  }
  let rellenos = lista.iter().filter(|x| matches!(x, Pieza::Relleno)).count();
  let libre = (ancho - fijos(l, &lista)).max(0.0);
  let extra = if rellenos > 0 { libre / rellenos as f32 } else { 0.0 };
  let mut cx = if rellenos > 0 || entero { x } else { x + libre / 2.0 };
  for pieza in &lista {
    dibujar_pieza(l, pieza, cx, cy, p);
    cx += ancho_pieza(l, pieza) + hueco + if matches!(pieza, Pieza::Relleno) { extra } else { 0.0 };
  }
}

/// La fila de la píldora (sin fondo), horizontal, de `largo` × 38 lógicos: un chip por pieza,
/// centrados y separados 4 (`.b-fila.grupo` de web/estilo.css), o el de la única pieza a lo
/// ancho. Devuelve también dónde quedó cada pieza (lógico, a lo largo).
fn fila(
  f: &Forma,
  estado: &Value,
  ahora: f64,
  largo: f32,
  s: f32,
  fuentes: &Fuentes,
  p: &Paleta,
) -> Option<(Pixmap, bool, Partes)> {
  let (w, h) = ((largo * s).round() as u32, (ALTO * s).round() as u32);
  let mut px = Pixmap::new(w.max(1), h.max(1))?;
  let mut l = Lienzo {
    px: &mut px,
    f: fuentes,
    s,
  };
  let cy = h as f32 / 2.0;
  let mut partes = Vec::new();
  let mut alerta = false;
  if estado.is_null() || f.piezas.is_empty() {
    let es = estado["idioma"].as_str() != Some("en");
    let texto = if es { "Iniciando akari…" } else { "Starting akari…" };
    let tw = l.ancho_texto(texto, 11.0, 0);
    l.texto(texto, (w as f32 - tw) / 2.0, cy, 11.0, 0, p.texto_var);
    return Some((px, false, partes));
  }
  if let [pieza] = f.piezas {
    let margen = 14.0 * s;
    let (lista, a) = chip(pieza, estado, ahora, p, true);
    dibujar_chip(&mut l, lista, margen, w as f32 - 2.0 * margen, cy, p, true);
    partes.push((pieza.nombre.clone(), 0.0, largo));
    return Some((px, a, partes));
  }
  let entre = 4.0 * s;
  let total: f32 = f.piezas.iter().map(|x| x.ancho as f32 * s).sum::<f32>() + entre * (f.piezas.len() - 1) as f32;
  let mut x = ((w as f32 - total) / 2.0).max(0.0);
  for (i, pieza) in f.piezas.iter().enumerate() {
    let ancho = pieza.ancho as f32 * s;
    let (lista, a) = chip(pieza, estado, ahora, p, false);
    alerta |= a;
    dibujar_chip(&mut l, lista, x, ancho, cy, p, false);
    // la zona de la pieza llega hasta la mitad del espacio con sus vecinas
    let desde = if i == 0 { 0.0 } else { x - entre / 2.0 };
    let hasta = if i + 1 == f.piezas.len() {
      w as f32
    } else {
      x + ancho + entre / 2.0
    };
    partes.push((pieza.nombre.clone(), desde / s, hasta / s));
    x += ancho + entre;
  }
  Some((px, alerta, partes))
}

/// La píldora cerrada completa (fondo, borde y chips), en píxeles físicos (escala `s`), y
/// dónde queda cada pieza: (nombre, desde, hasta) en lógicos, a lo largo de la píldora (en
/// la pestaña vertical, de arriba abajo).
pub type Partes = Vec<(String, f32, f32)>;
pub fn dibujar(f: &Forma, estado: &Value, ahora: f64, s: f32, fuentes: &Fuentes) -> Option<(Pixmap, Partes)> {
  let p = paleta(estado);
  let largo = if f.vertical {
    (f.ancho as f32).max(156.0)
  } else {
    f.ancho as f32
  };
  let (fila, alerta, mut partes) = fila(f, estado, ahora, largo, s, fuentes, &p)?;
  if f.vertical && f.borde == "izquierda" {
    // girada: lo que estaba al principio de la fila queda abajo
    partes = partes.into_iter().map(|(n, a, b)| (n, largo - b, largo - a)).collect();
  }
  let (w, h) = if f.vertical {
    (fila.height(), fila.width())
  } else {
    (fila.width(), fila.height())
  };
  let mut px = Pixmap::new(w, h)?;
  let r = ALTO * s / 2.0;
  // el lado pegado a un borde de la pantalla queda recto (como en capsulas/Capsula.qml)
  let izq = f.borde == "izquierda";
  let der = f.borde == "derecha";
  let radios = [
    if f.pegada_arriba || izq { 0.0 } else { r },
    if f.pegada_arriba || der { 0.0 } else { r },
    if f.pegada_abajo || der { 0.0 } else { r },
    if f.pegada_abajo || izq { 0.0 } else { r },
  ];
  if let Some(forma) = redondeado(0.0, 0.0, w as f32, h as f32, radios) {
    px.fill_path(
      &forma,
      &pintura(alfa(p.superficie, 0.94)),
      FillRule::Winding,
      Transform::identity(),
      None,
    );
    let borde = Stroke {
      width: s,
      ..Default::default()
    };
    if let Some(dentro) = redondeado(
      0.5 * s,
      0.5 * s,
      w as f32 - s,
      h as f32 - s,
      radios.map(|x| (x - 0.5 * s).max(0.0)),
    ) {
      px.stroke_path(
        &dentro,
        &pintura(alfa(p.contorno_var, 0.7)),
        &borde,
        Transform::identity(),
        None,
      );
    }
  }
  let t = if !f.vertical {
    Transform::identity()
  } else if izq {
    // se lee de abajo arriba
    Transform::from_row(0.0, -1.0, 1.0, 0.0, 0.0, h as f32)
  } else {
    Transform::from_row(0.0, 1.0, -1.0, 0.0, w as f32, 0.0)
  };
  px.draw_pixmap(0, 0, fila.as_ref(), &PixmapPaint::default(), t, None);
  if alerta {
    // batería baja: línea roja bajo la cápsula
    let (lw, lh) = (w as f32 * 0.4, 2.0 * s);
    if let Some(linea) = tiny_skia::Rect::from_xywh((w as f32 - lw) / 2.0, h as f32 - lh, lw, lh) {
      px.fill_rect(linea, &pintura(p.error), Transform::identity(), None);
    }
  }
  Some((px, partes))
}

#[cfg(test)]
mod pruebas {
  use super::*;

  fn fuentes() -> Option<Fuentes> {
    let d = "/usr/share/fonts/truetype/dejavu/";
    Fuentes::cargar(
      &[&format!("{d}DejaVuSans.ttf")],
      &[&format!("{d}DejaVuSans-Bold.ttf")],
      &[&format!("{d}DejaVuSansMono.ttf")],
      &[&format!("{d}DejaVuSans.ttf")],
    )
  }

  fn estado() -> Value {
    serde_json::json!({
      "idioma": "es",
      "tema": { "colores": {} },
      "ia": { "principal": "claude", "claude": { "modelo_actual": "Opus 5.5",
              "limites": { "cinco_horas": { "libre": 62.0, "reinicia": 10_000.0 } }, "cinta": [{ "t": 9_990.0 }] } },
      "dispositivos": { "dispositivos": [
        { "tipo": "raton", "conectado": true, "bateria": 82 },
        { "tipo": "teclado", "conectado": true, "bateria": null, "conexion": "Cable / receptor USB" },
        { "tipo": "audifonos", "conectado": true, "bateria": 15 },
        { "tipo": "celular", "conectado": true, "bateria": 47, "cargando": true } ] },
      "habilidades": { "total": 3 },
      "herramientas": { "instaladas": 2, "total": 7, "lista": [] },
      "modelos": { "listo": true, "modo": "api", "modelo": "claude-haiku", "ollama": {} },
      "asistente": { "estado": "pausa", "historial": [] },
      "documentos": { "listo": false, "trabajos": [] },
      "audio": { "usa": true, "grabacion": {}, "trabajos": [{ "estado": "transcribiendo", "pct": 40 }] }
    })
  }

  #[test]
  fn cuenta_como_la_web() {
    assert_eq!(cuenta(2.0 * 3600.0 + 600.0), "2 h 10");
    assert_eq!(cuenta(45.0 * 60.0), "45 min");
    assert_eq!(cuenta(4.0 * 86400.0 + 3600.0), "4 d 1 h");
  }

  fn pieza(nombre: &str, icono: &str, ancho: f64) -> crate::forma::Pieza {
    crate::forma::Pieza {
      nombre: nombre.into(),
      titulo: nombre.into(),
      icono: icono.into(),
      ancho,
    }
  }

  #[test]
  fn dibuja_los_grupos() {
    let Some(fuentes) = fuentes() else { return }; // sin las fuentes de prueba no hay nada que mirar
    let carpeta = std::env::var("AKARI_CAPTURAS").ok();
    // los grupos de akari/grupos.py
    let equipo = vec![pieza("dispositivos", "devices", 254.0)];
    let ia = vec![
      pieza("asistente", "chat", 48.0),
      pieza("uso", "bolt", 92.0),
      pieza("modelos", "psychology", 44.0),
      pieza("habilidades", "auto_awesome", 58.0),
      pieza("herramientas", "construction", 64.0),
    ];
    let archivos = vec![pieza("documentos", "swap_horiz", 58.0), pieza("audio", "graphic_eq", 72.0)];
    let uso = vec![pieza("uso", "bolt", 300.0)];
    for (nombre, piezas, ancho, vertical, borde) in [
      ("equipo", &equipo, 274.0, false, ""),
      ("ia", &ia, 342.0, false, ""),
      ("archivos", &archivos, 154.0, false, ""),
      ("uso", &uso, 300.0, false, ""),
      ("ia-v", &ia, 342.0, true, "izquierda"),
    ] {
      let f = Forma {
        piezas,
        ancho,
        vertical,
        borde,
        pegada_arriba: !vertical,
        pegada_abajo: false,
      };
      let (px, partes) = dibujar(&f, &estado(), 10_000.0 - 7_800.0, 1.5, &fuentes).expect("dibujo");
      if vertical {
        assert_eq!((px.width(), px.height()), (57, 513));
      } else {
        assert_eq!((px.width(), px.height()), ((ancho * 1.5) as u32, 57));
        assert_eq!(px.pixel(0, px.height() - 1).unwrap().alpha(), 0); // esquina redondeada
      }
      assert!(px.data().chunks(4).filter(|c| c[3] > 0).count() > 100);
      // las zonas de las piezas cubren la píldora entera, en orden
      assert_eq!(partes.len(), piezas.len());
      let largo = ancho as f32;
      let (min, max) = partes
        .iter()
        .fold((f32::MAX, 0f32), |(a, b), (_, x, y)| (a.min(*x), b.max(*y)));
      assert!(min <= 0.01 && (max - largo).abs() < 0.5, "{partes:?}");
      if let Some(c) = &carpeta {
        px.save_png(format!("{c}/{nombre}.png")).unwrap();
      }
    }
    // la de IA: el asistente a la izquierda, luego el uso…
    let f = Forma {
      piezas: &ia,
      ancho: 342.0,
      vertical: false,
      borde: "",
      pegada_arriba: true,
      pegada_abajo: false,
    };
    let (_, partes) = dibujar(&f, &estado(), 0.0, 1.0, &fuentes).unwrap();
    assert_eq!(partes[1].0, "uso");
    assert!(partes[0].2 < partes[1].2);
    // …con los chips donde los pone la web: 10 de margen, cada uno de su ancho y 4 entre ellos
    assert!((partes[1].1 - (10.0 + 48.0 + 2.0)).abs() < 0.5, "{partes:?}");
    assert!(muneco("pausa").contains(&(3, 9, 'e')) && !muneco("hablando").contains(&(3, 9, 'e')));
    // sin servicio todavía
    assert!(dibujar(&f, &Value::Null, 0.0, 1.0, &fuentes).is_some());
  }
}
