// Actualizaciones del AppImage, con el mismo latest.json firmado que usa la app de Windows
// (plugin updater de Tauri). El servicio decide si hay versión nueva (akari/actualizacion.py: una
// vez al día, canal estable o beta, "actualizar": false lo apaga, «Ahora no» la pospone); aquí se
// baja el AppImage de esa release, se comprueba su firma minisign con la clave pública que el CI
// pone en clave-actualizar.pub (la privada solo está en los secretos del CI) y se reemplaza el
// archivo. Sin clave pública o sin firma válida no se instala nada.
const { app, dialog } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const https = require("https");
const path = require("path");

const REPO = "https://github.com/sJonathan15/akari";
const ARQ = { x64: "linux-x86_64", arm64: "linux-aarch64" }[process.arch];
let ocupado = false;

function clavePublica() {
  try {
    return fs.readFileSync(path.join(__dirname, "clave-actualizar.pub"), "utf8").trim();
  } catch {
    return "";
  }
}

// --- minisign (lo que firma `tauri signer sign`) -------------------------------------------
// clave: base64 de "untrusted comment: …\n<base64: 'Ed' + id(8) + clave(32)>"
// firma: base64 de "untrusted comment: …\n<base64: 'Ed'|'ED' + id(8) + firma(64)>\ntrusted comment: …\n<base64: firma global(64)>"
function lineas(b64) {
  return Buffer.from(String(b64).trim(), "base64").toString("utf8").split(/\r?\n/).filter(Boolean);
}
function verificarFirma(datos, firmaB64, claveB64) {
  const clave = Buffer.from(lineas(claveB64)[1] || "", "base64");
  const [, lineaFirma, comentario, global] = lineas(firmaB64);
  const firma = Buffer.from(lineaFirma || "", "base64");
  if (clave.length !== 42 || firma.length !== 74 || !comentario || !global) return false;
  if (clave.subarray(0, 2).toString() !== "Ed" || !firma.subarray(2, 10).equals(clave.subarray(2, 10))) return false;
  const pk = crypto.createPublicKey({ key: Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"), clave.subarray(10)]), format: "der", type: "spki" });
  const alg = firma.subarray(0, 2).toString();
  const mensaje = alg === "ED" ? crypto.createHash("blake2b512").update(datos).digest() : alg === "Ed" ? datos : null;
  if (!mensaje || !crypto.verify(null, mensaje, pk, firma.subarray(10))) return false;
  const confiable = Buffer.from(comentario.replace(/^trusted comment: /, ""), "utf8");
  return crypto.verify(null, Buffer.concat([firma.subarray(10), confiable]), pk, Buffer.from(global, "base64"));
}

// --- red -----------------------------------------------------------------------------------
function bajar(url, saltos = 5) {
  return new Promise((ok, mal) => {
    https.get(url, { headers: { "User-Agent": `akari/${app.getVersion()}` } }, (r) => {
      if ([301, 302, 303, 307, 308].includes(r.statusCode) && r.headers.location && saltos > 0) {
        r.resume();
        return ok(bajar(new URL(r.headers.location, url).toString(), saltos - 1));
      }
      if (r.statusCode !== 200) { r.resume(); return mal(new Error(`HTTP ${r.statusCode}`)); }
      const partes = [];
      r.on("data", (p) => partes.push(p));
      r.on("end", () => ok(Buffer.concat(partes)));
      r.on("error", mal);
    }).on("error", mal);
  });
}

const mayor = (a, b) => {
  // semver sencillo: 0.2.0-beta.1 < 0.2.0-beta.2 < 0.2.0
  const partes = (v) => { const [n, pre] = String(v).replace(/^v/, "").split("-"); return [n.split(".").map(Number), pre]; };
  const [na, pa] = partes(a), [nb, pb] = partes(b);
  for (let i = 0; i < 3; i++) if ((na[i] || 0) !== (nb[i] || 0)) return (na[i] || 0) > (nb[i] || 0);
  if (!pa || !pb) return !pa && !!pb;
  const ia = pa.split("."), ib = pb.split(".");
  for (let i = 0; i < Math.max(ia.length, ib.length); i++) {
    if (ia[i] === undefined) return false;
    if (ib[i] === undefined) return true;
    const x = /^\d+$/.test(ia[i]), y = /^\d+$/.test(ib[i]);
    if (ia[i] !== ib[i]) return x && y ? Number(ia[i]) > Number(ib[i]) : x !== y ? !x : ia[i] > ib[i];
  }
  return false;
};

// --- lo que ve el usuario --------------------------------------------------------------------
async function ofrecer({ version, t, preguntar, avisarServicio }) {
  const archivo = process.env.APPIMAGE;
  const clave = clavePublica();
  if (ocupado || !archivo || !clave || !ARQ) return false;
  ocupado = true;
  try {
    const ultimo = JSON.parse((await bajar(`${REPO}/releases/download/v${version}/latest.json`)).toString("utf8"));
    const plat = (ultimo.platforms || {})[ARQ];
    if (!plat || !plat.url || !plat.signature || !mayor(ultimo.version, app.getVersion())) return false;
    if (preguntar) {
      const { response } = await dialog.showMessageBox({
        type: "info", title: "akari", buttons: [t("Actualizar", "Update"), t("Ahora no", "Not now")], defaultId: 0, cancelId: 1,
        message: t("Hay una versión nueva", "A new version is available"),
        detail: t(`akari ${ultimo.version} (tienes la ${app.getVersion()}). Tu configuración se conserva.`,
                  `akari ${ultimo.version} (you have ${app.getVersion()}). Your settings are kept.`),
      });
      if (response !== 0) { avisarServicio("ahora-no"); return false; }
    }
    const datos = await bajar(plat.url);
    if (!verificarFirma(datos, plat.signature, clave)) throw new Error(t("la firma no coincide", "the signature does not match"));
    // se escribe al lado y se cambia de un golpe: si algo falla, el AppImage de antes sigue entero
    const nuevo = archivo + ".nuevo";
    fs.writeFileSync(nuevo, datos, { mode: 0o755 });
    fs.renameSync(nuevo, archivo);
    app.relaunch({ execPath: archivo, args: process.argv.slice(1) });
    app.exit(0);
    return true;
  } catch (e) {
    dialog.showErrorBox("akari", t(`No pude actualizar: ${e.message}`, `Could not update: ${e.message}`));
    return false;
  } finally {
    ocupado = false;
  }
}

module.exports = { ofrecer, verificarFirma, mayor, clavePublica };
