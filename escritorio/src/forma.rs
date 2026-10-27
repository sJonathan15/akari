//! Geometría de una burbuja: dónde va, cuánto mide cerrada y abierta, hacia dónde se
//! despliega y cuándo se vuelve pestaña vertical. Es la misma lógica que capsulas/Capsula.qml
//! y app/main.js, en unidades lógicas (píxeles de CSS) relativas al área de trabajo.
use serde::{Deserialize, Serialize};

pub const ALTO: f64 = 38.0; // grosor de la burbuja cerrada
pub const MARGEN_BORDE: f64 = 40.0; // a esta distancia de un lado se vuelve pestaña vertical
const CERCA_BORDE: f64 = 200.0; // cerca de un borde se despliega hacia el otro lado

/// Lo que dice el servicio de cada burbuja (GET /api/burbujas).
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Medidas {
  pub nombre: String,
  #[serde(default = "derecha")]
  pub lado: String,
  #[serde(default = "ocho")]
  pub hueco: f64,
  #[serde(default = "ancho_cerrado")]
  pub ancho_cerrado: f64,
  #[serde(default = "ancho_abierto")]
  pub ancho_abierto: f64,
  #[serde(default = "alto_maximo")]
  pub alto_maximo: f64,
  #[serde(default)]
  pub teclado: bool,
  #[serde(default)]
  pub titulo: String,
}
fn derecha() -> String {
  "derecha".into()
}
fn ocho() -> f64 {
  8.0
}
fn ancho_cerrado() -> f64 {
  250.0
}
fn ancho_abierto() -> f64 {
  380.0
}
fn alto_maximo() -> f64 {
  640.0
}

/// Las tres de siempre, por si el servicio es de una versión sin /api/burbujas.
pub fn de_fabrica() -> Vec<Medidas> {
  let m = |nombre: &str, lado: &str, hueco, cerrado, abierto, maximo, teclado| Medidas {
    nombre: nombre.into(),
    lado: lado.into(),
    hueco,
    ancho_cerrado: cerrado,
    ancho_abierto: abierto,
    alto_maximo: maximo,
    teclado,
    titulo: nombre.into(),
  };
  vec![
    m("dispositivos", "izquierda", 8.0, 262.0, 384.0, 700.0, false),
    m("ia", "derecha", 8.0, 262.0, 360.0, 760.0, true),
    m("habilidades", "derecha", 380.0, 136.0, 380.0, 640.0, false),
  ]
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rect {
  pub x: f64,
  pub y: f64,
  pub w: f64,
  pub h: f64,
}

/// Lo que se guarda en posiciones.json (el mismo formato que las cápsulas).
#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
pub struct Posicion {
  pub x: f64,
  pub y: f64,
  #[serde(default)]
  pub borde: String,
}

#[derive(Clone, Debug)]
pub struct Burbuja {
  pub m: Medidas,
  /// None = posición de fábrica
  pub cx: Option<f64>,
  pub cy: f64,
  pub borde: String,
  pub abierta: bool,
  pub moviendo: bool,
  pub alto_cuerpo: f64,
  inicio: (f64, f64),
}

fn limitar(v: f64, min: f64, max: f64) -> f64 {
  v.max(min).min(max.max(min))
}

impl Burbuja {
  pub fn new(m: Medidas, guardada: Option<&Posicion>) -> Self {
    Burbuja {
      cx: guardada.map(|p| p.x),
      cy: guardada.map(|p| p.y).unwrap_or(0.0),
      borde: guardada.map(|p| p.borde.clone()).unwrap_or_default(),
      m,
      abierta: false,
      moviendo: false,
      alto_cuerpo: 0.0,
      inicio: (0.0, 0.0),
    }
  }

  pub fn vertical(&self) -> bool {
    !self.borde.is_empty()
  }
  fn izquierda(&self) -> bool {
    self.borde == "izquierda"
  }
  pub fn largo_v(&self) -> f64 {
    self.m.ancho_cerrado.max(156.0)
  }
  fn w_c(&self) -> f64 {
    if self.vertical() {
      ALTO
    } else {
      self.m.ancho_cerrado
    }
  }
  fn h_c(&self) -> f64 {
    if self.vertical() {
      self.largo_v()
    } else {
      ALTO
    }
  }
  pub fn desplegada(&self) -> bool {
    self.abierta && !self.moviendo
  }

  pub fn x(&self, ancho: f64) -> f64 {
    self.cx.unwrap_or(if self.m.lado == "derecha" {
      (ancho / 2.0 + self.m.hueco).round()
    } else {
      (ancho / 2.0 - self.m.hueco - self.m.ancho_cerrado).round()
    })
  }
  pub fn hacia_derecha(&self, ancho: f64) -> bool {
    let x = self.x(ancho);
    let mut d = if x < CERCA_BORDE {
      true
    } else if ancho - (x + self.m.ancho_cerrado) < CERCA_BORDE {
      false
    } else {
      self.m.lado == "derecha"
    };
    if d && x + self.m.ancho_abierto > ancho {
      d = false;
    }
    if !d && x + self.m.ancho_cerrado - self.m.ancho_abierto < 0.0 {
      d = true;
    }
    d
  }
  pub fn hacia_arriba(&self, alto: f64) -> bool {
    self.cy + ALTO / 2.0 > alto / 2.0
  }
  fn alto_abierto(&self, alto: f64) -> f64 {
    let disponible = ALTO.max(self.m.alto_maximo.min(if self.hacia_arriba(alto) {
      self.cy + ALTO
    } else {
      alto - self.cy
    }));
    disponible.min(ALTO + self.alto_cuerpo)
  }
  fn alto_panel_v(&self, alto: f64) -> f64 {
    alto.min(self.largo_v().max(self.alto_cuerpo + 20.0))
  }
  fn top_panel_v(&self, alto: f64) -> f64 {
    let h = self.alto_panel_v(alto);
    limitar((self.cy + self.largo_v() / 2.0 - h / 2.0).round(), 0.0, alto - h)
  }

  /// Rectángulo de la ventana dentro del área de trabajo (ancho × alto).
  pub fn limites(&self, ancho: f64, alto: f64) -> Rect {
    if !self.desplegada() {
      return if self.vertical() {
        Rect {
          x: if self.izquierda() { 0.0 } else { ancho - ALTO },
          y: self.cy,
          w: ALTO,
          h: self.largo_v(),
        }
      } else {
        Rect {
          x: self.x(ancho),
          y: self.cy,
          w: self.m.ancho_cerrado,
          h: ALTO,
        }
      };
    }
    if self.vertical() {
      let w = ALTO + self.m.ancho_abierto;
      return Rect {
        x: if self.izquierda() { 0.0 } else { ancho - w },
        y: self.top_panel_v(alto),
        w,
        h: self.alto_panel_v(alto),
      };
    }
    let h = self.alto_abierto(alto);
    let x = self.x(ancho);
    Rect {
      x: if self.hacia_derecha(ancho) {
        x
      } else {
        x + self.m.ancho_cerrado - self.m.ancho_abierto
      },
      y: if self.hacia_arriba(alto) {
        self.cy + ALTO - h
      } else {
        self.cy
      },
      w: self.m.ancho_abierto,
      h,
    }
  }

  /// Lo que la página necesita para dibujar la forma (el mismo objeto que manda app/main.js).
  pub fn forma(&self, ancho: f64, alto: f64, ventana_cerrada: bool) -> serde_json::Value {
    serde_json::json!({
      "abierta": self.desplegada(), "ventanaCerrada": ventana_cerrada, "moviendo": self.moviendo,
      "vertical": self.vertical(), "borde": self.borde,
      "haciaDerecha": self.hacia_derecha(ancho), "haciaArriba": self.hacia_arriba(alto),
      "pegadaArriba": !self.vertical() && self.cy <= 0.0, "pegadaAbajo": !self.vertical() && self.cy + ALTO >= alto,
      "altoCerrado": ALTO, "anchoCerrado": self.m.ancho_cerrado, "anchoAbierto": self.m.ancho_abierto,
      "largoV": self.largo_v(),
      "cerrada": { "w": self.w_c(), "h": self.h_c(),
                   "y": if self.vertical() { self.cy - self.top_panel_v(alto) } else { 0.0 } },
    })
  }

  pub fn empezar_mover(&mut self, ancho: f64) {
    self.moviendo = true;
    self.inicio = (self.x(ancho), self.cy);
  }
  pub fn mover(&mut self, dx: f64, dy: f64, ancho: f64, alto: f64) {
    if !self.moviendo {
      return;
    }
    self.cx = Some(limitar(self.inicio.0 + dx, 0.0, ancho - self.w_c()));
    self.cy = limitar(self.inicio.1 + dy, 0.0, alto - self.h_c());
  }
  /// Al soltar: pegada a un lado → pestaña vertical; si no → horizontal.
  pub fn soltar(&mut self, ancho: f64, alto: f64) {
    if !self.moviendo {
      return;
    }
    let x = self.x(ancho);
    if x <= MARGEN_BORDE {
      self.borde = "izquierda".into();
      self.cx = Some(0.0);
    } else if x + self.w_c() >= ancho - MARGEN_BORDE {
      self.borde = "derecha".into();
      self.cx = Some(ancho - ALTO);
    } else {
      self.borde.clear();
      self.cx = Some(limitar(x, 0.0, ancho - self.m.ancho_cerrado));
    }
    self.cy = limitar(self.cy, 0.0, alto - self.h_c());
    self.moviendo = false;
  }
  pub fn fabrica(&mut self) {
    self.cx = None;
    self.cy = 0.0;
    self.borde.clear();
  }
  /// La pantalla cambió: que siga dentro.
  pub fn recolocar(&mut self, ancho: f64, alto: f64) {
    if let Some(x) = self.cx {
      self.cx = Some(if self.borde == "derecha" {
        ancho - ALTO
      } else {
        limitar(x, 0.0, ancho - self.w_c())
      });
    }
    self.cy = limitar(self.cy, 0.0, alto - self.h_c());
  }
  pub fn posicion(&self) -> Option<Posicion> {
    self.cx.map(|x| Posicion {
      x: x.round(),
      y: self.cy.round(),
      borde: self.borde.clone(),
    })
  }
}

#[cfg(test)]
mod pruebas {
  use super::*;

  fn ia() -> Burbuja {
    Burbuja::new(de_fabrica().remove(1), None)
  }

  #[test]
  fn fabrica_cuelga_del_centro() {
    let b = ia();
    assert_eq!(
      b.limites(1920.0, 1040.0),
      Rect {
        x: 968.0,
        y: 0.0,
        w: 262.0,
        h: ALTO
      }
    );
    let d = Burbuja::new(de_fabrica().remove(0), None);
    assert_eq!(d.limites(1920.0, 1040.0).x, 960.0 - 8.0 - 262.0);
  }

  #[test]
  fn abierta_mide_su_contenido() {
    let mut b = ia();
    b.abierta = true;
    b.alto_cuerpo = 400.0;
    assert_eq!(
      b.limites(1920.0, 1040.0),
      Rect {
        x: 968.0,
        y: 0.0,
        w: 360.0,
        h: 438.0
      }
    );
    b.alto_cuerpo = 5000.0; // no pasa de su máximo
    assert_eq!(b.limites(1920.0, 1040.0).h, 760.0);
  }

  #[test]
  fn cerca_del_borde_derecho_abre_hacia_la_izquierda() {
    let mut b = ia();
    b.cx = Some(1700.0);
    b.abierta = true;
    b.alto_cuerpo = 100.0;
    assert!(!b.hacia_derecha(1920.0));
    assert_eq!(b.limites(1920.0, 1040.0).x, 1700.0 + 262.0 - 360.0);
  }

  #[test]
  fn abajo_abre_hacia_arriba() {
    let mut b = ia();
    b.cy = 1000.0;
    b.abierta = true;
    b.alto_cuerpo = 300.0;
    assert!(b.hacia_arriba(1040.0));
    let r = b.limites(1920.0, 1040.0);
    assert_eq!(r.y + r.h, 1000.0 + ALTO);
  }

  #[test]
  fn soltar_contra_un_lado_la_vuelve_pestana() {
    let mut b = ia();
    b.empezar_mover(1920.0);
    b.mover(-2000.0, 280.0, 1920.0, 1040.0);
    b.soltar(1920.0, 1040.0);
    assert_eq!((b.borde.as_str(), b.cx, b.cy), ("izquierda", Some(0.0), 280.0));
    assert_eq!(
      b.limites(1920.0, 1040.0),
      Rect {
        x: 0.0,
        y: 280.0,
        w: ALTO,
        h: 262.0
      }
    );
    b.abierta = true;
    b.alto_cuerpo = 600.0;
    assert_eq!(
      b.limites(1920.0, 1040.0),
      Rect {
        x: 0.0,
        y: 280.0 + 131.0 - 310.0,
        w: ALTO + 360.0,
        h: 620.0
      }
    );
    assert_eq!(
      b.posicion(),
      Some(Posicion {
        x: 0.0,
        y: 280.0,
        borde: "izquierda".into()
      })
    );
    // y de vuelta al medio: horizontal otra vez
    b.abierta = false;
    b.empezar_mover(1920.0);
    b.mover(700.0, -100.0, 1920.0, 1040.0);
    b.soltar(1920.0, 1040.0);
    assert_eq!((b.borde.as_str(), b.cx), ("", Some(700.0)));
  }

  #[test]
  fn forma_para_la_pagina() {
    let b = ia();
    let f = b.forma(1920.0, 1040.0, true);
    assert_eq!(f["pegadaArriba"], true);
    assert_eq!(f["cerrada"]["w"], 262.0);
    assert_eq!(f["haciaDerecha"], true);
  }

  #[test]
  fn medidas_del_servicio() {
    let m: Vec<Medidas> = serde_json::from_str(
      r#"[{"nombre":"voz","lado":"izquierda","hueco":300,"anchoCerrado":120,"anchoAbierto":340,"altoMaximo":500,"teclado":false,"icono":"mic","titulo":"Voz"}]"#,
    )
    .unwrap();
    assert_eq!(
      (m[0].nombre.as_str(), m[0].ancho_cerrado, m[0].hueco),
      ("voz", 120.0, 300.0)
    );
    let minimo: Vec<Medidas> = serde_json::from_str(r#"[{"nombre":"x"}]"#).unwrap();
    assert_eq!(minimo[0].ancho_abierto, 380.0);
  }
}
