// Capturas de cada paso del recorrido de bienvenida en modo demo, para el README y los PR.
//
//   AKARI_DEMO=1 AKARI_PUERTO=47891 python bin/akari.py servicio &      (con un HOME de prueba)
//   NODE_PATH=$(npm root -g) node herramientas/capturas-recorrido.js http://127.0.0.1:47891 docs/recorrido [es|en]
//
// Necesita Playwright (npm i -g playwright). No toca nada: el modo demo usa datos inventados.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const [base = "http://127.0.0.1:47830", salida = "docs/recorrido", idioma = "es"] = process.argv.slice(2);
  fs.mkdirSync(salida, { recursive: true });
  const enviar = (cuerpo) => fetch(`${base}/api/recorrido`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo) }).then((r) => r.json());
  await fetch(`${base}/api/ajustes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idioma }) });
  let r = (await enviar({ accion: "reiniciar" })).recorrido;
  const navegador = await chromium.launch();
  const pagina = await navegador.newPage({ viewport: { width: 420, height: 820 }, deviceScaleFactor: 2, locale: idioma });
  await pagina.goto(`${base}/`);
  while (r.activo) {
    await pagina.waitForTimeout(1200);
    const nombre = path.join(salida, `${String(r.n).padStart(2, "0")}-${r.paso.id}.png`);
    await pagina.screenshot({ path: nombre });
    console.log(nombre);
    r = (await enviar({ accion: "siguiente" })).recorrido;
  }
  await navegador.close();
})();
