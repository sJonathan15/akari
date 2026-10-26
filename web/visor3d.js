// Visor 3D del panel: el mismo modelo .glb y la misma luz de estudio que las cápsulas.
// Se agarra con el ratón: gira 1:1 con la mano, al soltarlo conserva el impulso y luego
// vuelve a su giro lento.
import * as THREE from "three";
import { GLTFLoader } from "./vendor/GLTFLoader.js";
import { RGBELoader } from "./vendor/RGBELoader.js";

// misma orientación que capsulas/Visor3D.qml (grados; tam = tamaño relativo)
const AJUSTES = {
  mouse: { rx: 0, ry: 210, inclinacion: -40, tam: 1.0 },
  headphones: { rx: 0, ry: 25, inclinacion: -10, tam: 1.04 },
  keyboard: { rx: 0, ry: 20, inclinacion: -45, tam: 1.22 },
  phone: { rx: 0, ry: 20, inclinacion: -8, tam: 0.92 },
};
const RAD = Math.PI / 180;
const reducido = matchMedia("(prefers-reduced-motion: reduce)").matches;

export class Visor {
  constructor(lienzo) {
    this.lienzo = lienzo;
    this.render = new THREE.WebGLRenderer({ canvas: lienzo, antialias: true, alpha: true });
    this.render.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.render.toneMapping = THREE.ACESFilmicToneMapping;
    this.render.toneMappingExposure = 1.15;
    this.escena = new THREE.Scene();
    this.camara = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
    this.camara.position.set(0, 0, 2.3);
    this.escena.add(new THREE.DirectionalLight(0xffffff, 1.6).translateX(1).translateY(1.4).translateZ(1.2));
    this.contraluz = new THREE.DirectionalLight(0xffffff, 1.4);
    this.contraluz.position.set(-0.6, 0.5, -1.5);
    this.escena.add(this.contraluz);
    this.relleno = new THREE.DirectionalLight(0xb7c4ff, 0.6);
    this.relleno.position.set(1.5, 0.2, 0.3);
    this.escena.add(this.relleno);
    new RGBELoader().load("modelos/studio.hdr", (hdr) => {
      hdr.mapping = THREE.EquirectangularReflectionMapping;
      this.escena.environment = hdr;
      this.escena.environmentIntensity = 0.9;
    });

    this.inclinacion = new THREE.Group();
    this.giro = new THREE.Group();
    this.base = new THREE.Group();
    this.inclinacion.add(this.giro);
    this.giro.add(this.base);
    this.escena.add(this.inclinacion);

    this.cargador = new GLTFLoader();
    this.cache = {};
    this.modelo = null;
    this.angulo = 0;
    this.velocidad = reducido ? 0 : 20;
    this.lento = reducido ? 0 : 20;
    this.agarrado = false;
    this.aparicion = 1;
    this.encendido = true;
    this._eventos();
    new ResizeObserver(() => this._medir()).observe(lienzo);
    this._medir();
    this.ultimo = performance.now();
    requestAnimationFrame((t) => this._cuadro(t));
  }

  _medir() {
    const { clientWidth: w, clientHeight: h } = this.lienzo;
    if (!w || !h) return;
    this.render.setSize(w, h, false);
    this.camara.aspect = w / h;
    this.camara.updateProjectionMatrix();
  }

  mostrar(nombre, encendido) {
    this.encendido = encendido;
    this._opacidad();
    if (nombre === this.modelo) return;
    this.modelo = nombre;
    this.base.clear();
    if (!nombre) return;
    const poner = (gltf) => {
      if (this.modelo !== nombre) return;
      const a = AJUSTES[nombre] || AJUSTES.mouse;
      const objeto = gltf.scene.clone(true);
      this.base.clear();
      this.base.add(objeto);
      // los .glb ya vienen centrados y de 1 unidad de lado (herramientas/modelos.py)
      this.base.scale.setScalar(a.tam);
      this.base.rotation.set(a.rx * RAD, a.ry * RAD, 0, "YXZ");
      this.inclinacion.rotation.x = -a.inclinacion * RAD;
      this.aparicion = 0;
      this._opacidad();
    };
    if (this.cache[nombre]) poner(this.cache[nombre]);
    else this.cargador.load(`modelos/${nombre}.glb`, (g) => { this.cache[nombre] = g; poner(g); });
  }

  _opacidad() {
    this.lienzo.style.opacity = this.encendido ? 1 : 0.4;
  }

  _eventos() {
    let x0 = 0, historial = [];
    this.lienzo.addEventListener("pointerdown", (e) => {
      this.agarrado = true;
      this.velocidad = 0;
      x0 = e.clientX;
      historial = [{ t: performance.now(), a: this.angulo }];
      this.lienzo.setPointerCapture(e.pointerId);
    });
    this.lienzo.addEventListener("pointermove", (e) => {
      if (!this.agarrado) return;
      this.angulo += (e.clientX - x0) * 0.6;
      x0 = e.clientX;
      const ahora = performance.now();
      historial = historial.concat([{ t: ahora, a: this.angulo }]).filter((p) => ahora - p.t < 100);
    });
    const soltar = () => {
      if (!this.agarrado) return;
      if (historial.length >= 2) {
        const dt = (historial.at(-1).t - historial[0].t) / 1000;
        if (dt > 0) this.velocidad = (historial.at(-1).a - historial[0].a) / dt;
      }
      this.agarrado = false;
    };
    this.lienzo.addEventListener("pointerup", soltar);
    this.lienzo.addEventListener("pointercancel", soltar);
  }

  _cuadro(t) {
    const dt = Math.min((t - this.ultimo) / 1000, 1 / 30);
    this.ultimo = t;
    if (!this.agarrado) {
      // el impulso decae como el desplazamiento de iOS (0,998 por ms) hacia el giro lento
      this.velocidad = this.lento + (this.velocidad - this.lento) * Math.pow(0.998, dt * 1000);
      this.angulo = (this.angulo + this.velocidad * dt) % 360;
    }
    this.aparicion += (1 - this.aparicion) * (1 - Math.exp(-dt * 8));
    this.giro.rotation.y = this.angulo * RAD;
    this.inclinacion.scale.setScalar(0.9 + 0.1 * this.aparicion);
    // pausado: la burbuja de dispositivos está cerrada (no gastar GPU en algo que no se ve)
    if (this.lienzo.offsetParent && !this.pausado) this.render.render(this.escena, this.camara);
    requestAnimationFrame((x) => this._cuadro(x));
  }
}
