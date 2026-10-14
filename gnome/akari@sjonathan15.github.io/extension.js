// akari para GNOME Shell (45+): tres indicadores en la barra superior con lo mismo que las
// cápsulas: uso de la IA (Claude Code / Codex), batería de los periféricos y habilidades.
// Los datos vienen del servicio de akari (127.0.0.1:47830); el 3D se abre en el panel.
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Soup from 'gi://Soup?version=3.0';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BASE = 'http://127.0.0.1:47830';
const ES = GLib.get_language_names().some(l => l.startsWith('es'));
const t = (es, en) => (ES ? es : en);

const ICONOS = {
    raton: 'input-mouse-symbolic', teclado: 'input-keyboard-symbolic', audifonos: 'audio-headphones-symbolic',
    celular: 'phone-symbolic', mando: 'input-gaming-symbolic', otro: 'drive-removable-media-symbolic',
};

function corto(n) {
    if (n === null || n === undefined) return '—';
    if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 1 : 2)} M`;
    if (n >= 1e3) return `${Math.round(n / 1e3)} k`;
    return String(Math.round(n));
}
function hora(ts) {
    return GLib.DateTime.new_from_unix_local(Math.round(ts)).format('%H:%M');
}
function iconoBateria(b, cargando) {
    if (b === null || b === undefined) return 'battery-missing-symbolic';
    const nivel = Math.max(0, Math.min(100, Math.round(b / 10) * 10));
    return `battery-level-${nivel}${cargando ? '-charging' : ''}-symbolic`;
}

// ------------------------------------------------------------------ indicador base
const Indicador = GObject.registerClass(
class Indicador extends PanelMenu.Button {
    _init(nombre, extension) {
        super._init(0.5, `akari ${nombre}`);
        this._ext = extension;
        this._caja = new St.BoxLayout({style_class: 'akari-caja'});
        this.add_child(this._caja);
        this.menu.connect('open-state-changed', (_m, abierto) => {
            if (abierto) this._llenarMenu();
        });
    }

    estado() {
        return this._ext.estado;
    }

    etiqueta(texto, clase = '') {
        return new St.Label({text: texto, y_align: Clutter.ActorAlign.CENTER, style_class: `akari-etiqueta ${clase}`});
    }

    icono(nombre, clase = '') {
        return new St.Icon({icon_name: nombre, style_class: `system-status-icon akari-icono ${clase}`});
    }

    item(texto, icono = null, alPulsar = null) {
        const it = new PopupMenu.PopupImageMenuItem(texto, icono || '');
        if (!icono)
            it._icon.hide();
        if (alPulsar)
            it.connect('activate', alPulsar);
        else
            it.setSensitive(false);
        return it;
    }

    titulo(texto) {
        const it = new PopupMenu.PopupMenuItem(texto, {reactive: false, style_class: 'akari-titulo'});
        return it;
    }

    pie() {
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addMenuItem(this.item(t('Abrir panel (con 3D)', 'Open panel (with 3D)'), 'view-reveal-symbolic', () => this._ext.abrirPanel()));
    }
});

// ------------------------------------------------------------------ IA
const IndicadorIA = GObject.registerClass(
class IndicadorIA extends Indicador {
    _init(ext) {
        super._init('IA', ext);
        this._caja.add_child(this.icono('starred-symbolic'));
        this._texto = this.etiqueta('—');
        this._caja.add_child(this._texto);
    }

    proveedor() {
        const ia = this.estado()?.ia;
        return ia && ia.principal ? ia[ia.principal] : null;
    }

    actualizar() {
        const p = this.proveedor();
        const v = p?.limites?.cinco_horas;
        this._texto.text = v ? `${Math.round(v.libre)}%` : '—';
        this._texto.style_class = `akari-etiqueta ${!v ? '' : v.libre <= 10 ? 'akari-mal' : v.libre <= 25 ? 'akari-medio' : ''}`;
    }

    _llenarMenu() {
        this.menu.removeAll();
        const ia = this.estado()?.ia;
        const nombres = {claude: 'Claude Code', codex: 'Codex'};
        const provs = ia ? ['claude', 'codex'].filter(p => ia[p]) : [];
        if (!provs.length) {
            this.menu.addMenuItem(this.item(t('No encontré Claude Code ni Codex.', 'Neither Claude Code nor Codex was found.')));
            return this.pie();
        }
        for (const clave of provs) {
            const p = ia[clave];
            const cuenta = p.cuenta ? ` · ${[p.cuenta.nombre, p.cuenta.plan].filter(Boolean).join(' · ')}` : '';
            this.menu.addMenuItem(this.titulo(nombres[clave] + cuenta));
            for (const [titulo, v] of [[t('5 horas', '5 hours'), p.limites.cinco_horas], [t('Semanal', 'Weekly'), p.limites.siete_dias]]) {
                let texto = `${titulo}: ${v ? t(`te queda el ${Math.round(v.libre)} %`, `${Math.round(v.libre)}% left`) : t('sin lectura', 'no data')}`;
                if (v?.agotado_en)
                    texto += t(` · se acaba a las ${hora(v.agotado_en)}`, ` · runs out at ${hora(v.agotado_en)}`);
                else if (v?.reinicia)
                    texto += t(` · se renueva a las ${hora(v.reinicia)}`, ` · renews at ${hora(v.reinicia)}`);
                this.menu.addMenuItem(this.item(texto, 'content-loading-symbolic'));
            }
            this.menu.addMenuItem(this.item(`${t('Hoy', 'Today')}: ${corto(p.tokens.hoy.nuevos)} tokens · ${p.modelo_actual || '—'}`, 'view-continuous-symbolic'));
            if (clave === 'claude' && p.activador) {
                this.menu.addMenuItem(this.item(t('Activar ventana de 5 horas', 'Start 5-hour window'), 'media-playback-start-symbolic',
                    () => this._ext.enviar('/api/ia/activar', {mensaje: ''})));
            }
        }
        this.pie();
    }
});

// ------------------------------------------------------------------ dispositivos
const IndicadorDispositivos = GObject.registerClass(
class IndicadorDispositivos extends Indicador {
    _init(ext) {
        super._init('dispositivos', ext);
        this._clave = '';
    }

    actualizar() {
        const lista = (this.estado()?.dispositivos?.dispositivos || []).filter(d => d.conectado).slice(0, 4);
        const clave = JSON.stringify(lista.map(d => [d.tipo, d.bateria]));
        if (clave === this._clave)
            return;
        this._clave = clave;
        this._caja.destroy_all_children();
        if (!lista.length) {
            this._caja.add_child(this.icono('input-mouse-symbolic', 'akari-apagado'));
            return;
        }
        for (const d of lista) {
            this._caja.add_child(this.icono(ICONOS[d.tipo] || ICONOS.otro, d.bateria !== null && d.bateria <= 20 ? 'akari-mal' : ''));
            if (d.bateria !== null)
                this._caja.add_child(this.etiqueta(`${d.bateria}%`, d.bateria <= 20 ? 'akari-mal' : ''));
        }
    }

    _llenarMenu() {
        this.menu.removeAll();
        const D = this.estado()?.dispositivos;
        const lista = D?.dispositivos || [];
        if (!lista.length)
            this.menu.addMenuItem(this.item(t('Sin periféricos todavía.', 'No devices yet.')));
        for (const d of lista) {
            const estado = d.conectado
                ? `${d.conexion}${d.bateria !== null ? ` · ${d.bateria} %` : ''}${d.cargando ? t(' · cargando', ' · charging') : ''}`
                : t('desconectado', 'disconnected');
            const sub = new PopupMenu.PopupSubMenuMenuItem(`${d.nombre} — ${estado}`, true);
            sub.icon.icon_name = ICONOS[d.tipo] || ICONOS.otro;
            for (const [k, v] of d.detalles.slice(0, 5))
                sub.menu.addMenuItem(this.item(`${k}: ${v}`));
            if (d.horas_restantes)
                sub.menu.addMenuItem(this.item(t(`Quedan unas ${d.horas_restantes} h`, `About ${d.horas_restantes} h left`), iconoBateria(d.bateria, false)));
            for (const a of d.acciones) {
                sub.menu.addMenuItem(this.item(a.etiqueta, 'emblem-system-symbolic',
                    () => this._ext.enviar('/api/dispositivos', {id: d.id, accion: a.id})));
            }
            sub.menu.addMenuItem(this.item(t('Cambiar tipo', 'Change type'), 'object-flip-horizontal-symbolic',
                () => this._ext.enviar('/api/dispositivos', {id: d.id, accion: 'tipo'})));
            sub.menu.addMenuItem(this.item(t('Ocultar', 'Hide'), 'view-conceal-symbolic',
                () => this._ext.enviar('/api/dispositivos', {id: d.id, accion: 'ocultar'})));
            if (!d.conectado)
                sub.setSensitive(true);
            this.menu.addMenuItem(sub);
        }
        if (D?.equipo) {
            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            this.menu.addMenuItem(this.item(`${t('Equipo', 'Laptop')}: ${D.equipo.bateria} %`, iconoBateria(D.equipo.bateria, D.equipo.estado === 'cargando')));
        }
        this.pie();
    }
});

// ------------------------------------------------------------------ habilidades
const IndicadorHabilidades = GObject.registerClass(
class IndicadorHabilidades extends Indicador {
    _init(ext) {
        super._init('habilidades', ext);
        this._caja.add_child(this.icono('applications-science-symbolic'));
        this._texto = this.etiqueta('—');
        this._caja.add_child(this._texto);
    }

    actualizar() {
        const H = this.estado()?.habilidades;
        this._texto.text = H ? String(H.total) : '—';
    }

    _llenarMenu() {
        this.menu.removeAll();
        const H = this.estado()?.habilidades;
        if (!H) {
            this.menu.addMenuItem(this.item(t('akari no responde.', 'akari is not responding.')));
            return this.pie();
        }
        this.menu.addMenuItem(this.titulo(t(`Recomendadas (${H.recomendadas_instaladas}/10 instaladas)`, `Recommended (${H.recomendadas_instaladas}/10 installed)`)));
        for (const r of H.recomendadas) {
            const lista = r.instalada_en.length > 0 && r.falta_en.length === 0;
            const instalando = r.tarea?.estado === 'instalando';
            const texto = `${r.nombre} — ${instalando ? t('instalando…', 'installing…') : lista ? t('instalada', 'installed') : r.detalle}`;
            const it = this.item(texto, lista ? 'emblem-ok-symbolic' : 'folder-download-symbolic',
                lista || instalando || !r.agentes.length ? null : () => this._ext.enviar('/api/habilidades', {id: r.id, accion: 'instalar'}));
            this.menu.addMenuItem(it);
        }
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const usadas = H.instaladas.filter(s => s.usos_7d).slice(0, 5);
        this.menu.addMenuItem(this.titulo(t(`Tienes ${H.total} habilidades · más usadas (7 días)`, `You have ${H.total} skills · most used (7 days)`)));
        for (const s of usadas)
            this.menu.addMenuItem(this.item(`${s.nombre} · ${s.usos_7d}`));
        if (!usadas.length)
            this.menu.addMenuItem(this.item(t('Ninguna usada esta semana.', 'None used this week.')));
        this.pie();
    }
});

// ------------------------------------------------------------------ extensión
export default class AkariExtension extends Extension {
    enable() {
        this.estado = null;
        this._sesion = new Soup.Session({timeout: 3});
        this._indicadores = [new IndicadorDispositivos(this), new IndicadorIA(this), new IndicadorHabilidades(this)];
        this._indicadores.forEach((ind, i) => Main.panel.addToStatusArea(`akari-${i}`, ind, i, 'right'));
        this._pedir();
        this._reloj = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 3, () => {
            this._pedir();
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        if (this._reloj)
            GLib.source_remove(this._reloj);
        this._reloj = null;
        this._indicadores?.forEach(ind => ind.destroy());
        this._indicadores = null;
        this._sesion?.abort();
        this._sesion = null;
        this.estado = null;
    }

    _pedir() {
        const msg = Soup.Message.new('GET', `${BASE}/api/estado`);
        this._sesion.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null, (sesion, res) => {
            try {
                const bytes = sesion.send_and_read_finish(res);
                if (msg.get_status() !== 200)
                    throw new Error('estado');
                this.estado = JSON.parse(new TextDecoder().decode(bytes.get_data()));
            } catch (e) {
                this.estado = null;
            }
            this._indicadores?.forEach(ind => ind.actualizar());
        });
    }

    enviar(ruta, cuerpo) {
        const msg = Soup.Message.new('POST', `${BASE}${ruta}`);
        msg.set_request_body_from_bytes('application/json', new GLib.Bytes(new TextEncoder().encode(JSON.stringify(cuerpo))));
        this._sesion.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, null, (sesion, res) => {
            try {
                sesion.send_and_read_finish(res);
            } catch (e) {}
            this._pedir();
        });
    }

    abrirPanel() {
        const akari = GLib.find_program_in_path('akari') || `${GLib.get_home_dir()}/.local/bin/akari`;
        try {
            Gio.Subprocess.new([akari, 'abrir'], Gio.SubprocessFlags.NONE);
        } catch (e) {
            Gio.AppInfo.launch_default_for_uri(`${BASE}/`, null);
        }
    }
}
