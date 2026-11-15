// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// tendencia-montar.js - ES module that mounts the DESCRIPTIVE annual trend view (ADR-0012, option 2) in a section of the page.
// Same contract as calendario-montar.js, so the app shell can mount it with the same call:
//
//   export async function montar({container, store, datos, config})     container = <section id="trend">
//   export function destruir()
//   export function exportarPNG()                                      Promise<Blob> of the full figure (chart, slopes, notes, marks)
//
// It reads the store (aoi, range, scope, data.rows), loads intervalos.json (80 % ranges of the estimated years) and
// disponibilidad.json (months flagged incomplete), sums the cells with calendario-agregar.js (same numbers as the calendar),
// builds the model (tendencia-modelo.js) and draws it (tendencia-vista.js). container.dataset.state = loading | empty | error | ready.
// Controls: "Series shown" (both | harmonized only | raw only) and "Download PNG". Dates, area and "what to count" come from the
// selection form of the page (the same store), so the view never asks for a value twice.

import { CONFIG } from './datos-config.js';
import { descargarBlob } from './csv-descarga.js';

const SCRIPTS = ['marca.js', 'intervalos.js', 'fiabilidad.js', 'calendario-paleta.js', 'calendario-modelo.js', 'graficos.js', 'calendario-agregar.js',
  'tendencia-modelo.js', 'tendencia-vista.js'];

let loaded = null;
let unsubscribe = null;
let host = null;
let token = 0;
let current = null;                       // {model, ctx} of the figure on screen
const ui = { show: 'both' };
const cache = { intervals: new Map() };

function cargarScripts() {
  if (!loaded) {
    loaded = (async () => {
      for (const s of SCRIPTS) await import(new URL('./' + s, import.meta.url).href);   // classic UMD files attach to window
    })().catch((e) => { loaded = null; throw e; });
  }
  return loaded;
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function estado(container, kind) { container.dataset.state = kind; }

function montarHost(container) {
  const pend = container.querySelector('.status[data-screen="pending"]');
  if (pend) pend.hidden = true;
  host = container.querySelector('.tr-host');
  if (!host) { host = document.createElement('div'); host.className = 'tr-host'; container.appendChild(host); }
  return host;
}

/* ---------- the four states ---------- */

function pintarEstado(kind, title, message, retry) {
  if (kind === 'loading') {
    host.innerHTML = '<div class="tr tr--loading" role="status" aria-live="polite" aria-busy="true"><div class="tr-skel" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></div>' +
      `<p class="tr-state-msg"><span class="tr-spin" aria-hidden="true"></span> ${esc(message || 'Loading the annual totals for your area…')}</p></div>`;
  } else if (kind === 'error') {
    host.innerHTML = '<div class="tr tr--error" role="alert"><p class="tr-state-title">The trend could not be built</p>' +
      `<p class="tr-state-msg">${esc(message || 'Something went wrong while reading the data for this area.')}</p>` +
      '<p class="tr-state-hint">Check your connection and try again. If it keeps failing, pick a different area or dates.</p>' +
      (retry ? '<button type="button" class="btn" data-tr-retry>Try again</button>' : '') + '</div>';
    const b = host.querySelector('[data-tr-retry]');
    if (b && retry) b.addEventListener('click', retry);
  } else {
    host.innerHTML = '<div class="tr tr--empty" role="status">' +
      `<p class="tr-state-title">${esc(title || 'No annual totals for this selection')}</p><p class="tr-state-msg">${esc(message || 'There is nothing to show for this area and these dates.')}</p></div>`;
  }
}

/* ---------- ready ---------- */

/** 80 % range of the harmonized total of each complete estimated calendar year, from the calendar model (same sum as its ranking). */
function rangosAnuales(input, scope) {
  try {
    const m = window.FireCalendarModel.buildModel({ ...input, options: { mode: 'counts', base: 'B2', axis: 'calendar', vegetationOnly: scope !== 'all' } });
    if (m.empty || !m.rows) return null;
    const out = {};
    for (const r of m.rows) if (r.range) out[r.key] = r.range;
    return out;
  } catch (e) {
    console.error(e);
    return null;
  }
}

function opcionesModelo() {
  const t = CONFIG.TREND || {};
  return { minYears: t.MIN_YEARS, ci: t.CI_LEVEL, autocorrelation: t.AUTOCORRELATION, label: t.LABEL, show: ui.show };
}

function tablaHtml(model) {
  const f = window.FireTrendModel.fmtInt;
  const rows = model.years.map((a) => {
    const rg = a.range ? `${f(a.range.lo)} to ${isFinite(a.range.hi) ? f(a.range.hi) : 'no upper limit'}` : '';
    const st = a.status === 'complete' ? 'complete (in the slopes)' : `${a.status} (left out: ${a.reasons.join('; ')})`;
    return `<tr data-y="${a.y}" data-status="${a.status}"><th scope="row">${a.y}</th><td>${a.harmonized === null ? '–' : (a.estimated ? '~' : '') + f(a.harmonized)}</td>` +
      `<td>${esc(rg)}</td><td>${a.raw === null ? '–' : f(a.raw)}</td><td>${a.sensor === 'MODIS' ? 'MODIS' : (a.sensor === 'VIIRS' ? 'VIIRS' : '–')}</td><td>${esc(st)}</td></tr>`;
  }).join('');
  return '<table class="tr-table"><caption class="sr-only">Annual hotspot detections: harmonized (VIIRS-equivalent) and raw, with the status of each year</caption>' +
    '<thead><tr><th scope="col">Year</th><th scope="col">Harmonized (VIIRS-eq.)</th><th scope="col">80 % range</th><th scope="col">Raw</th><th scope="col">Raw sensor</th><th scope="col">Status</th></tr></thead>' +
    `<tbody>${rows}</tbody></table>`;
}

function controlesHtml() {
  const radio = (v, label) => `<label class="tr-opt"><input type="radio" name="tr-show" value="${v}" data-tr-show${ui.show === v ? ' checked' : ''}> <span>${label}</span></label>`;
  return '<fieldset class="tr-controls"><legend>Series shown</legend>' +
    radio('both', 'Both') + radio('harmonized', 'Harmonized only') + radio('raw', 'Raw only') + '</fieldset>';
}

function pintarListo() {
  const { model } = current;
  model.opts = { ...model.opts, show: ui.show };
  const TV = window.FireTrendView;
  const d = TV.describe(model);
  const warn = model.notices.filter((n) => n.level === 'warn').map((n) => `<li class="tr-notice">${esc(n.text)}</li>`).join('');
  const fig = TV.draw(model, { chartOnly: true });
  host.innerHTML = '<div class="tr tr--ready">' +
    `<div class="tr-bar">${controlesHtml()}<div class="tr-actions"><button type="button" class="btn btn-primary" data-tr-png>Download PNG</button><span class="tr-msg" role="status" aria-live="polite"></span></div></div>` +
    (warn ? `<ul class="tr-notices" role="status">${warn}</ul>` : '') +
    `<p class="tr-badge"><strong>${esc(d.headline)}</strong></p><p class="note tr-sub">${esc(d.subtitle)}</p>` +
    `<div class="tr-fig">${fig.svg}</div>` +
    `<ul class="tr-rows">${d.rows.map((r) => `<li data-key="${r.key}" data-ok="${r.ok}">${esc(r.text)}</li>`).join('')}</ul>` +
    (d.excluded.length ? `<p class="note tr-excluded">Years left out of the slopes: ${esc(d.excluded.join('; '))}.</p>` : '') +
    `<p class="note tr-method">${esc(d.method)}</p>` +
    '<details class="tr-details"><summary>Yearly numbers (table)</summary>' + tablaHtml(model) + '</details>' +
    `<ul class="plain note tr-notes">${d.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` +
    '</div>';
  host.querySelectorAll('[data-tr-show]').forEach((el) => el.addEventListener('change', (e) => {
    if (!e.target.checked) return;
    ui.show = e.target.value;
    pintarListo();
    const again = host.querySelector(`[data-tr-show][value="${ui.show}"]`);
    if (again) again.focus();
  }));
  host.querySelector('[data-tr-png]').addEventListener('click', descargarPNG);
}

/* ---------- PNG ---------- */

function rasterizar(svg, w, h, escala = 2) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
    const img = new Image();
    img.onload = () => {
      try {
        const cv = document.createElement('canvas');
        cv.width = w * escala; cv.height = h * escala;
        const cx = cv.getContext('2d');
        cx.fillStyle = '#FFFFFF'; cx.fillRect(0, 0, cv.width, cv.height);
        cx.drawImage(img, 0, 0, cv.width, cv.height);
        URL.revokeObjectURL(url);
        cv.toBlob((b) => (b ? resolve(b) : reject(new Error('The browser could not create the PNG.'))), 'image/png');
      } catch (e) { URL.revokeObjectURL(url); reject(e); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('The figure could not be rasterised.')); };
    img.src = url;
  });
}

/** PNG of the full figure (title, chart, slopes, notes, "SI-generated (AI)" and "Data: NASA FIRMS"), 2x. */
export function exportarPNG() {
  if (!current) return Promise.reject(new Error('Nothing to export: the trend is not showing data.'));
  const m = current.model;
  m.opts = { ...m.opts, show: ui.show };
  const f = window.FireTrendView.draw(m);
  return rasterizar(f.svg, f.w, f.h);
}

function nombrePNG() {
  const s = current.ctx.store.get(), m = current.model;
  const aoi = (s.presetId || 'custom-area').replace(/[^a-z0-9_-]/gi, '-');
  return `${m.synthetic ? 'SYNTHETIC_' : ''}hotspot-trend_${s.pais}_${aoi}_${m.firstYear}-${m.lastYear}_${ui.show}_SI-generated.png`;
}

async function descargarPNG() {
  const msg = host.querySelector('.tr-msg');
  const btn = host.querySelector('[data-tr-png]');
  if (btn) btn.disabled = true;
  try {
    const blob = await exportarPNG();
    descargarBlob(blob, nombrePNG());
    if (msg) msg.textContent = 'PNG downloaded. It carries the marks "SI-generated (AI)" and "Data: NASA FIRMS".';
  } catch (e) {
    console.error(e);
    if (msg) { msg.textContent = `The PNG could not be created: ${e.message || e}`; msg.classList.add('tr-msg--bad'); }
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ---------- refresh from the store ---------- */

async function refrescar(ctx) {
  const my = ++token;
  const { container, store, datos } = ctx;
  const s = store.get();
  current = null;
  if (s.load.status === 'loading') { estado(container, 'loading'); pintarEstado('loading'); return; }
  // data errors: the page already has its own "Try again" (it reloads the tiles); the trend button presses it
  const reintentar = () => { const b = document.getElementById('status-retry'); if (b && !b.hidden) b.click(); else refrescar(ctx); };
  if (s.load.status === 'error') { estado(container, 'error'); pintarEstado('error', null, 'The app could not load its data.', reintentar); return; }
  if (!s.aoi) { estado(container, 'empty'); pintarEstado('empty', 'Choose an area', 'Draw an area on the map or pick a preset to see its annual totals and trend.'); return; }
  if (s.aoi.unavailable || !s.aoi.covered.length) {
    estado(container, 'empty'); pintarEstado('empty', 'Outside processed coverage', 'The trend covers Mexico and Argentina. Move the area inside one of them. That is not "zero fires": there is no data here.'); return;
  }
  if (s.data.status === 'loading' || s.data.status === 'idle') { estado(container, 'loading'); pintarEstado('loading', null, 'Loading the monthly data for your area…'); return; }
  if (s.data.status === 'error') { estado(container, 'error'); pintarEstado('error', null, (s.data.error && s.data.error.message) || 'The data for this area could not be loaded.', reintentar); return; }
  estado(container, 'loading'); pintarEstado('loading');
  try {
    const FA = window.FireCalendarAggregate, TM = window.FireTrendModel;
    const pais = s.manifest.paises[s.pais];
    const [intervals, disponibilidad] = await Promise.all([
      cache.intervals.get(s.base + s.pais) || (cache.intervals.set(s.base + s.pais, datos.cargarIntervalos(s.base, s.pais).catch(() => null)), cache.intervals.get(s.base + s.pais)),
      datos.cargarDisponibilidad(s.base, s.pais).catch(() => null),
    ]);
    if (my !== token) return;
    const input = FA.buildInput(store.get(), { intervals, disponibilidad, dailyRows: [] });
    const ranges = rangosAnuales(input, s.scope);
    const model = TM.buildTrend({
      monthly: input.monthly, range: s.range, vegetationOnly: s.scope !== 'all', last: pais.datosHasta || s.manifest.datosHasta,
      ranges: ranges || null, verdictOpen: input.manifest.verdict !== null, synthetic: input.synthetic, aoi: input.aoi, manifest: input.manifest,
      options: opcionesModelo(),
    });
    if (model.empty) {
      estado(container, 'empty');
      pintarEstado('empty', 'No annual totals for this selection', model.reason === 'no-months' || model.reason === 'no-years'
        ? 'The dates you chose contain no month of the series. Pick a wider date range.' : 'There are no processed detections for this area.');
      return;
    }
    if (model.years.every((a) => !a.harmonized && !a.raw)) {            // like the page's own "no detections" screen
      estado(container, 'empty');
      pintarEstado('empty', 'No hotspot detections for this selection', 'The cells and dates you chose have no detections in the series, so there is no annual total to draw. Try a wider date range or area.');
      return;
    }
    if (!ranges && model.years.some((a) => a.estimated)) {
      model.notices.push({ id: 'no-ranges', level: 'info', text: 'The 80 % ranges of the harmonization are unavailable (no interval table was loaded), so the estimated years are drawn without them.' });
    }
    current = { model, ctx };
    estado(container, 'ready');
    pintarListo();
  } catch (e) {
    if (my !== token) return;
    console.error(e);
    estado(container, 'error');
    pintarEstado('error', null, e.message || String(e), () => refrescar(ctx));
  }
}

export async function montar(ctx) {
  estado(ctx.container, 'loading');
  await cargarScripts();
  montarHost(ctx.container);
  pintarEstado('loading');
  let prev = null;
  unsubscribe = ctx.store.subscribe((st) => {
    const sig = [st.load.status, st.pais, st.presetId, st.scope, st.data.status, st.data.rows, st.aoi,
      st.range && st.range.from && (st.range.from.y * 12 + st.range.from.m), st.range && st.range.to && (st.range.to.y * 12 + st.range.to.m)];
    if (prev && sig.every((v, i) => v === prev[i])) return;
    prev = sig;
    refrescar(ctx);
  });
  refrescar(ctx);
}

export function destruir() {
  if (unsubscribe) unsubscribe();
  unsubscribe = null; token++; current = null;
  if (host) host.innerHTML = '';
}

// Test hook, like window.__app of estado-arranque.js: ?debug=1 exposes the model of the figure on screen.
if (new URLSearchParams(location.search).get('debug') === '1') {
  window.__tendencia = { modelo: () => (current ? current.model : null), mostrar: (v) => { ui.show = v; if (current) pintarListo(); } };
}
