// Firma de las actualizaciones del AppImage (app/actualizar.js): la misma de `tauri signer sign`.
// Datos de prueba con una clave desechable (aquí solo la pública y la firma).
//   node pruebas/app/prueba_actualizar.js
const assert = require("assert");
const Module = require("module");
const cargar = Module._load;
Module._load = function (pedido, ...resto) {
  return pedido === "electron" ? { app: { getVersion: () => "0.1.0" }, dialog: {} } : cargar.call(this, pedido, ...resto);
};
const { verificarFirma, mayor } = require("../../app/actualizar.js");

const DATOS = Buffer.from("akari: archivo de prueba para la firma de las actualizaciones\n");
const CLAVE = "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDhEMUE0QzNDMzk2NEZCREIKUldUYisyUTVQRXdhamZnaUttVXZrSjZmallZOXFReDlUOTBXOW5PUi9FSGdyUHh4Mnlnc2JsdmEK";
const FIRMA = "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkKUlVUYisyUTVQRXdhamVtRnI1N3F1anNEUXRDMW15dG9GTEJoY0VmbXJ3Q2tWdHJCdGxnS09sRHFwenJCL0pneVNRWWhETnNWMXJOUlQ3bTJVOXBwTGN5TkptME5FTDRiMlFnPQp0cnVzdGVkIGNvbW1lbnQ6IHRpbWVzdGFtcDoxNzkzMDczNTcxCWZpbGU6cHJ1ZWJhLnR4dAozZTlMamFRcGpwNVZvMWNNcHJ6QkFLaUtLMXNiZE5MbGdlY09BYUw5WUlJYURiaWZQdlFaUUYyTmRrbndTV3FpeHl4N1l2cDF3Mkhwc2ZiVG56VFZCUT09Cg==";

assert.strictEqual(verificarFirma(DATOS, FIRMA, CLAVE), true, "la firma buena pasa");
const cambiado = Buffer.from(DATOS);
cambiado[0] ^= 1;
assert.strictEqual(verificarFirma(cambiado, FIRMA, CLAVE), false, "un archivo cambiado no pasa");
assert.strictEqual(verificarFirma(DATOS, FIRMA, ""), false, "sin clave no pasa");
assert.strictEqual(verificarFirma(DATOS, "basura", CLAVE), false, "una firma rota no pasa");
assert.ok(mayor("0.2.0", "0.2.0-beta.3") && mayor("0.2.0-beta.10", "0.2.0-beta.9") && mayor("0.10.0", "0.9.9"));
assert.ok(!mayor("0.1.0", "0.1.0") && !mayor("0.2.0-beta.1", "0.2.0"));
console.log("ok");
