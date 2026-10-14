// Solo para pruebas: espera a que akari tenga datos, abre cada menú y guarda una captura en /salida.
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const esperar = s => new Promise(r => GLib.timeout_add(GLib.PRIORITY_DEFAULT, s * 1000, () => { r(); return GLib.SOURCE_REMOVE; }));

async function capturar(nombre) {
    const archivo = Gio.File.new_for_path(`/salida/${nombre}.png`);
    const flujo = archivo.replace(null, false, Gio.FileCreateFlags.NONE, null);
    const sh = new Shell.Screenshot();
    await new Promise(r => sh.screenshot(false, flujo, (_o, res) => { try { sh.screenshot_finish(res); } catch (e) { log(e); } r(); }));
    flujo.close(null);
}

export default class Prueba extends Extension {
    enable() {
        (async () => {
            await esperar(8);
            Main.overview.hide();
            await esperar(2);
            await capturar('gnome-barra');
            for (let i = 0; i < 3; i++) {
                const ind = Main.panel.statusArea[`akari-${i}`];
                if (!ind) { log(`akari-${i} no está`); continue; }
                ind.menu.open(false);
                await esperar(2);
                // además, el texto de cada fila del menú (por si el menú no puede abrirse sin teclado ni ratón)
                const textos = [];
                const recorrer = actor => {
                    if (actor instanceof St.Label && actor.text) textos.push(actor.text);
                    actor.get_children().forEach(recorrer);
                };
                ind._llenarMenu();
                recorrer(ind.menu.box);
                GLib.file_set_contents(`/salida/menu-${i}.txt`, `abierto=${ind.menu.isOpen}\n` + textos.join('\n'));
                await capturar(`gnome-menu-${i}`);
                ind.menu.close(false);
                await esperar(1);
            }
            GLib.file_set_contents('/salida/listo', 'ok');
        })();
    }
    disable() {}
}
