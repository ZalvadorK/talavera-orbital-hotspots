// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// calendario-montar.js - adapter ES module between the app shell (estado-arranque.js, CONFIG.CALENDAR_MODULE) and the
// calendar component (window.FireCalendar, classic UMD scripts). Optional: app-1 can instead call FireCalendar.render
// directly with the input documented in app/tests/calendario-INTERFAZ.md.
//
//   CONFIG.CALENDAR_MODULE = './calendario-montar.js'        (datos-config.js, owned by app-1)
//   export async function montar({container, store, datos, config})
//   export function destruir()
//
// It loads the component scripts, reads the store (aoi, range, scope, data.rows), loads intervalos.json and
// disponibilidad.json (and, lazily, the daily VIIRS tiles for the season views), builds the input with
// FireCalendarAggregate.buildInput and renders. container.dataset.state = loading | empty | error | ready.

const SCRIPTS = ['marca.js', 'intervalos.js', 'fiabilidad.js', 'calendario-paleta.js', 'calendario-modelo.js', 'graficos.js', 'graficos-modelo.js',
  'graficos-vistas.js', 'calendario-agregar.js', 'calendario.js'];

let loaded = null;
let unsubscribe = null;
let host = null;
let token = 0;
const cache = { intervals: new Map(), disp: new Map(), daily: new Map() };

function cargarScripts() {
  if (!loaded) {
    loaded = (async () => {
      for (const s of SCRIPTS) await import(new URL('./' + s, import.meta.url).href);   // classic UMD files attach to window
    })();
  }
  return loaded;
}

function asegurarCss() {
  const href = new URL('../css/calendario.css', import.meta.url).href;
  if (![...document.querySelectorAll('link[rel="stylesheet"]')].some((l) => l.href === href)) {
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href; document.head.appendChild(l);
  }
}

function parseDiario(text) {
  const lines = text.split(/\r?\n/);
  const head = lines[0].split(',');
  const ix = { d: head.indexOf('d'), v: head.indexOf('v'), vm: head.indexOf('vm'), prov: head.indexOf('prov') };
  const out = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i]) continue;
    const f = lines[i].split(',');
    out.push({ c: f[0], d: f[ix.d], v: Number(f[ix.v]), vm: ix.vm >= 0 ? Number(f[ix.vm]) : Number(f[ix.v]), prov: ix.prov >= 0 ? Number(f[ix.prov]) : 0 });
  }
  return out;
}

async function cargarDiario(base, pais, covered) {
  const tiles = [...new Set(covered.map((c) => c.tile))].filter((t) => pais.teselasDiario && pais.teselasDiario.has(t));
  const cellSet = new Set(covered.map((c) => c.id));
  const parts = await Promise.all(tiles.map((t) => {
    const key = `${base}${pais.id}/${t}`;
    if (!cache.daily.has(key)) {
      cache.daily.set(key, fetch(`${base}${pais.id}/diario/${t}.csv`).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} for the daily tile ${t}`);
        return r.text();
      }).then(parseDiario, (e) => { cache.daily.delete(key); throw e; }));
    }
    return cache.daily.get(key);
  }));
  const rows = [];
  for (const p of parts) for (const r of p) if (cellSet.has(r.c)) rows.push(r);
  return rows;
}

function estado(container, kind) { container.dataset.state = kind; }

function montarHost(container) {
  const pend = container.querySelector('.status[data-screen="pending"]');
  if (pend) pend.hidden = true;
  host = container.querySelector('.fc-host');
  if (!host) { host = document.createElement('div'); host.className = 'fc-host'; container.appendChild(host); }
  return host;
}

async function refrescar(ctx) {
  const my = ++token;
  const { container, store, datos } = ctx;
  const s = store.get();
  const FC = window.FireCalendar, FA = window.FireCalendarAggregate;
  if (s.load.status === 'loading') { estado(container, 'loading'); FC.render(host, { status: 'loading' }); return; }
  if (s.load.status === 'error') { estado(container, 'error'); FC.render(host, { status: 'error', error: 'The app could not load its data.' }); return; }
  if (!s.aoi) { estado(container, 'empty'); FC.render(host, { monthly: [], emptyTitle: 'Choose an area', emptyMessage: 'Draw an area on the map or pick a preset to see its calendar.' }); return; }
  if (s.aoi.unavailable || !s.aoi.covered.length) { estado(container, 'empty'); FC.render(host, { outsideCoverage: true }); return; }
  if (s.data.status === 'loading' || s.data.status === 'idle') { estado(container, 'loading'); FC.render(host, { status: 'loading', message: 'Loading the monthly data for your area…' }); return; }
  if (s.data.status === 'error') { estado(container, 'error'); FC.render(host, { status: 'error', error: (s.data.error && s.data.error.message) || 'The data for this area could not be loaded.' }); return; }
  const pais = s.manifest.paises[s.pais];
  const base = s.base;
  try {
    const [intervals, disponibilidad] = await Promise.all([
      cache.intervals.get(base + s.pais) || (cache.intervals.set(base + s.pais, datos.cargarIntervalos(base, s.pais).catch(() => null)), cache.intervals.get(base + s.pais)),
      datos.cargarDisponibilidad(base, s.pais).catch(() => null),
    ]);
    if (my !== token) return;
    const parts = { intervals, disponibilidad, dailyRows: [], config: ctx.config };       // config: thresholds of the rule M1 (null = off)
    const draw = () => {
      const input = FA.buildInput(store.get(), parts);
      input.onOptionsChange = () => {};
      input.onRetry = () => refrescar(ctx);
      estado(container, input.monthly.length ? 'ready' : 'empty');
      FC.render(host, input);
    };
    draw();
    if (pais.teselasDiario && pais.teselasDiario.size) {                       // daily tiles: lazy, only for the season views
      cargarDiario(base, pais, s.aoi.covered).then((rows) => { if (my === token) { parts.dailyRows = rows; draw(); } }, () => {});
    }
  } catch (e) {
    if (my !== token) return;
    estado(container, 'error');
    FC.render(host, { status: 'error', error: e.message || String(e), onRetry: () => refrescar(ctx) });
  }
}

export async function montar(ctx) {
  estado(ctx.container, 'loading');
  await cargarScripts();
  asegurarCss();
  montarHost(ctx.container);
  window.FireCalendar.renderState(host, 'loading');
  let prev = null;
  unsubscribe = ctx.store.subscribe((st) => {
    const sig = [st.load.status, st.pais, st.presetId, st.scope, st.data.status, st.data.rows, st.aoi, st.range && st.range.from && (st.range.from.y * 12 + st.range.from.m), st.range && st.range.to && (st.range.to.y * 12 + st.range.to.m)];
    if (prev && sig.every((v, i) => v === prev[i])) return;
    prev = sig;
    refrescar(ctx);
  });
  refrescar(ctx);
}

export function destruir() {
  if (unsubscribe) unsubscribe();
  unsubscribe = null; token++;
  if (host) host.innerHTML = '';
}

/** PNG of the figure on screen (for the app's download button): resolves with a Blob. */
export function exportarPNG() { return window.FireCalendar.exportPNG(host); }
