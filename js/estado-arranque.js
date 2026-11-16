// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// estado-arranque.js - entry point of the app (<script type="module"> in index.html).
// Connects map, controls, data, state and the CSV download.
//
// Contract with the calendar (app-2): set CONFIG.CALENDAR_MODULE = './calendario.js' in
// datos-config.js; that module must export  montar(ctx)  with
//   ctx = {container: <section id="calendar">, store, datos: <datos.js module>, config: CONFIG}
// and read store.get().aoi / .range / .scope / .data.rows (see estado.js). The states
// of the section (data-state="pending" | "loading" | "empty" | "error" | "ready") are set by the module.
//
// URL test hooks:  ?screen=loading|empty|error
//                  ?debug=1 (exposes window.__app)  ?calendar=1 (mounts ./calendario-montar.js).

import { CONFIG } from './datos-config.js';
import * as D from './datos.js';
import { polygonsOfGeojson, cellsInBbox, cellsInPolygon, splitCoverage, bboxOfCells, validateBbox, normalizeBbox, estimateTiles, ringBbox } from './aoi.js';
import { countMonthly, checkCap, validateRange, incompleteMonthsInRange } from './csv.js';
import { crearEstado, rangoCompleto, rangosRapidos } from './estado.js';
import { construirCsv, descargarBlob } from './csv-descarga.js';
import { crearMapa } from './mapa.js';
import * as UI from './estado-ui.js';

const $ = UI.$;
const store = crearEstado();
const polys = {}; // paisId -> polygons of the outline
let mapa = null;
let ultimo = null; // last month with data {y,m}
let rapidos = [];
let loadToken = 0;
let csvToken = 0;

const paisActual = () => {
  const s = store.get();
  return s.manifest.paises[s.pais];
};

function render() {
  const s = store.get();
  UI.renderScreen(s);
  if (s.aoi && s.data.summary) {
    UI.renderSummary(s, CONFIG.CSV_MAX_ROWS);
    UI.renderDownloads(s, CONFIG.CSV_MAX_ROWS, checkCap(s.data.summary.rows, CONFIG.CSV_MAX_ROWS));
  }
}
store.subscribe(render);

/* ---------- startup ---------- */

async function arrancar() {
  store.patch('load', { status: 'loading', error: null });
  UI.renderMethodNotesBase();
  try {
    if (!mapa) {
      mapa = crearMapa('map', {
        config: CONFIG,
        onShape: (shape) => aplicarForma(shape, { desdeMapa: true }),
        onCleared: () => limpiarAoi({ borrarMapa: false }),
        onBasemapFailed: () => {
          $('basemap-toggle').checked = false;
          UI.mensajeBasemap('The OpenStreetMap background could not be loaded. The app keeps working with country outlines only.');
        },
        onError: (e) => console.error(e),
      });
      $('basemap-toggle').checked = mapa.hayBasemap();
    }
    const { manifest, base } = await D.cargarManifest();
    const ids = Object.keys(manifest.paises);
    const gjs = await Promise.all(ids.map((id) => D.cargarContorno(base, id)));
    ids.forEach((id, i) => {
      polys[id] = polygonsOfGeojson(gjs[i]);
      mapa.agregarContorno(id, gjs[i]);
    });
    ultimo = D.ultimoMes(manifest.datosHasta);
    if (!ultimo) throw new D.DataError('manifest.json has no valid "datos_hasta" date');

    store.set({
      manifest,
      base,
      pais: ids[0],
      range: rangoCompleto(CONFIG.SERIES_START, ultimo),
      load: { status: 'ready', error: null },
    });
    UI.mostrarBannerSynthetic(manifest.synthetic, manifest.banner);
    if (manifest.synthetic) document.title = `[SYNTHETIC] ${document.title.replace(/^\[SYNTHETIC\] /, '')}`;
    UI.renderAbout(manifest);
    UI.llenarPaises(manifest, ids[0]);
    UI.llenarPresets(manifest.paises[ids[0]], null);
    UI.limitesCampos(manifest.paises[ids[0]].bbox);
    UI.llenarFechas(CONFIG.SERIES_START, ultimo);
    UI.escribirRango(store.get().range);
    UI.acotarMeses(CONFIG.SERIES_START, ultimo);
    rapidos = rangosRapidos(CONFIG.SERIES_START, ultimo);
    UI.llenarRapidos(rapidos);
    mapa.resaltarPais(ids[0]);
    const b = mapa.boundsDePaises();
    if (b) mapa.map.fitBounds(b, { padding: [20, 20], animate: false });
    mapa.invalidar();
    montarCalendario();
  } catch (e) {
    console.error(e);
    store.patch('load', { status: 'error', error: e });
  }
}

async function montarCalendario() {
  // By default the #calendar section stays "pending" (the wave order). It is activated with
  // CONFIG.CALENDAR_MODULE or, to test the integration without touching the config, with ?calendar=1.
  const modulo = CONFIG.CALENDAR_MODULE || (new URLSearchParams(location.search).get('calendar') === '1' ? './calendario-montar.js' : null);
  if (!modulo) return;
  const cont = $('calendar');
  try {
    const mod = await import(modulo);
    await mod.montar({ container: cont, store, datos: D, config: CONFIG });
  } catch (e) {
    console.error(e);
    cont.dataset.state = 'error';
  }
}

/* ---------- AOI ---------- */

function limpiarAoi({ borrarMapa = true } = {}) {
  loadToken++;
  csvToken++;
  if (borrarMapa && mapa) mapa.limpiar();
  UI.escribirBounds(null);
  UI.mostrarErroresBounds([]);
  $('preset').value = '';
  store.set({
    aoi: null,
    aoiSource: null,
    presetId: null,
    data: { status: 'idle', rows: null, summary: null, error: null, progress: 0 },
    csv: { status: 'idle', progress: 0, message: '', error: null, last: null },
  });
}

/**
 * Snaps a shape (box or polygon) to the 0.1 degree grid and loads the monthly data.
 * shape: {kind:'bbox', bbox} | {kind:'polygon', ring}
 */
function aplicarForma(shape, { presetId = null, desdeMapa = false } = {}) {
  const s0 = store.get();
  const envolvente = shape.kind === 'polygon' ? ringBbox(shape.ring) : normalizeBbox(shape.bbox);
  const nTeselas = estimateTiles(envolvente);
  if (nTeselas > CONFIG.MAX_TILES) {
    UI.mostrarErroresBounds([
      { field: 'bbox', message: `That area is too large: it spans ${nTeselas} one-degree tiles (limit ${CONFIG.MAX_TILES}). Draw or enter a smaller area.` },
    ]);
    return;
  }
  let cells;
  try {
    const opts = { maxCells: CONFIG.MAX_CELLS };
    cells = shape.kind === 'polygon' ? cellsInPolygon(shape.ring, opts) : cellsInBbox(shape.bbox, opts);
  } catch (e) {
    UI.mostrarErroresBounds([{ field: 'bbox', message: 'That area is too large. Draw or enter a smaller area (a few degrees across).' }]);
    return;
  }
  UI.mostrarErroresBounds([]);

  // Country: the one that covers more cells with its outline; if none, the selected one is kept.
  const dentro = {};
  let mejor = s0.pais;
  let mejorN = -1;
  for (const id of Object.keys(s0.manifest.paises)) {
    dentro[id] = splitCoverage(cells, polys[id]);
    const n = dentro[id].covered.length;
    if (n > mejorN || (n === mejorN && id === s0.pais)) {
      mejor = id;
      mejorN = n;
    }
  }
  if (mejorN <= 0) mejor = s0.pais;
  if (mejor !== s0.pais) seleccionarPais(mejor, { limpiar: false, vista: false });

  // A country without exported data (disponible:false) never counts cells: everything is "outside processed coverage".
  const disponible = s0.manifest.paises[mejor].disponible;
  const covered = disponible ? dentro[mejor].covered : [];
  const outside = disponible ? dentro[mejor].outside : cells;
  const aoi = {
    kind: shape.kind,
    cells,
    covered,
    outside,
    unavailable: !disponible && dentro[mejor].covered.length > 0,
    bbox: bboxOfCells(cells),
    coveredBbox: bboxOfCells(covered),
    tiles: new Set(covered.map((c) => c.tile)),
    cellSet: new Set(covered.map((c) => c.id)),
  };
  loadToken++;
  csvToken++;
  store.set({
    aoi,
    aoiSource: shape,
    presetId,
    data: { status: 'idle', rows: null, summary: null, error: null, progress: 0 },
    csv: { status: 'idle', progress: 0, message: '', error: null, last: null },
  });
  if (!presetId) $('preset').value = '';
  if (aoi.bbox) UI.escribirBounds(aoi.bbox);
  mapa.pintarFormaOriginal(shape);
  mapa.pintarCeldas(aoi);
  if (!desdeMapa && aoi.bbox) mapa.ajustarA(aoi.bbox, { maxZoom: 9 });
  cargarDatosAoi();
}

/** Summary of the current range and scope (incomplete months from disponibilidad.json if it exists). */
function calcularResumen(cur, rows, disp) {
  const r = countMonthly(rows, cur.aoi.cellSet, cur.range, cur.scope);
  const inc = incompleteMonthsInRange(disp, cur.range);
  if (inc !== null) r.incompleteMonths = inc;
  return r;
}

async function cargarDatosAoi() {
  const s = store.get();
  const token = ++loadToken;
  if (!s.aoi || !s.aoi.covered.length) return;
  store.patch('data', { status: 'loading', rows: null, summary: null, error: null, progress: 0, disp: null });
  try {
    const [{ rows }, disp] = await Promise.all([
      D.cargarMensualAoi(s.base, paisActual(), s.aoi.covered, (done, n) => {
        if (token === loadToken) store.patch('data', { progress: done / n });
      }, { allowReserved: !!s.manifest.verdict }),   // raw 2019+ counts exist only after the verdict
      D.cargarDisponibilidad(s.base, s.pais).catch(() => null),
    ]);
    if (token !== loadToken) return;
    const cur = store.get();
    store.patch('data', { status: 'ready', rows, disp, progress: 1, summary: calcularResumen(cur, rows, disp) });
  } catch (e) {
    console.error(e);
    if (token === loadToken) store.patch('data', { status: 'error', error: e });
  }
}

/** Recomputes the summary when dates or scope change (without downloading tiles again). */
function recomputar() {
  const s = store.get();
  csvToken++;
  store.patch('csv', { status: 'idle', progress: 0, error: null, last: null });
  if (s.aoi && s.data.status === 'ready' && s.data.rows) {
    store.patch('data', { summary: calcularResumen(s, s.data.rows, s.data.disp) });
  }
}

function seleccionarPais(id, { limpiar = true, vista = true } = {}) {
  const s = store.get();
  if (!s.manifest.paises[id]) return;
  const p = s.manifest.paises[id];
  store.set({ pais: id });
  $('country').value = id;
  UI.llenarPresets(p, null);
  UI.limitesCampos(p.bbox);
  mapa.resaltarPais(id);
  if (limpiar) limpiarAoi();
  if (vista) mapa.ajustarA(p.bbox, { maxZoom: 6 });
}

/* ---------- controls ---------- */

function onFechasChange({ desdeRapido = false } = {}) {
  UI.acotarMeses(CONFIG.SERIES_START, ultimo);
  const range = UI.leerRango();
  const v = validateRange(range, { minMonth: CONFIG.SERIES_START, maxMonth: ultimo });
  const err = $('err-range');
  if (!v.ok) {
    err.textContent = v.errors.join('. ');
    err.hidden = false;
    return;
  }
  err.hidden = true;
  if (!desdeRapido) $('quick-range').value = '';
  store.set({ range });
  recomputar();
}

function cablearControles() {
  $('country').addEventListener('change', (e) => seleccionarPais(e.target.value));

  $('preset').addEventListener('change', (e) => {
    const id = e.target.value;
    if (!id) return;
    const a = paisActual().aoiPredef.find((x) => x.id === id);
    if (a) aplicarForma({ kind: 'bbox', bbox: a.bbox }, { presetId: id });
  });

  $('apply-bounds').addEventListener('click', () => {
    const raw = UI.leerBounds();
    const check = validateBbox(raw, paisActual().bbox);
    UI.mostrarErroresBounds(check.errors);
    if (!check.ok) return;
    aplicarForma({ kind: 'bbox', bbox: normalizeBbox(raw) });
  });
  $('selection-form').addEventListener('submit', (e) => e.preventDefault());

  $('clear-aoi').addEventListener('click', () => limpiarAoi());

  for (const id of ['from-year', 'from-month', 'to-year', 'to-month']) {
    $(id).addEventListener('change', () => onFechasChange());
  }
  $('quick-range').addEventListener('change', (e) => {
    const r = rapidos.find((x) => x.id === e.target.value);
    if (!r) return;
    UI.escribirRango(r.range);
    onFechasChange({ desdeRapido: true });
  });

  for (const el of document.querySelectorAll('input[name="scope"]')) {
    el.addEventListener('change', () => {
      if (!el.checked) return;
      store.set({ scope: el.value });
      recomputar();
    });
  }

  $('basemap-toggle').addEventListener('change', (e) => {
    UI.mensajeBasemap('');
    if (e.target.checked) mapa.activarBasemap();
    else mapa.desactivarBasemap();
  });

  $('status-retry').addEventListener('click', () => {
    const s = store.get();
    if (s.load.status === 'error') arrancar();
    else cargarDatosAoi();
  });

  $('btn-csv').addEventListener('click', descargarCsv);
  $('btn-meta').addEventListener('click', () => {
    const l = store.get().csv.last;
    if (l) descargarBlob(l.metaBlob, l.metaFilename);
  });
}

async function descargarCsv() {
  const s = store.get();
  const sum = s.data.summary;
  if (!sum || !checkCap(sum.rows, CONFIG.CSV_MAX_ROWS).ok) return;
  const token = ++csvToken;
  store.patch('csv', { status: 'building', progress: 0, error: null, last: null });
  try {
    const res = await construirCsv({
      base: s.base,
      pais: paisActual(),
      aoi: s.aoi,
      range: s.range,
      scope: s.scope,
      manifest: s.manifest.raw,
      shownCount: sum.rows,
      onProgreso: (done, n) => {
        if (token === csvToken) store.patch('csv', { progress: done / n });
      },
    });
    if (token !== csvToken) return; // the selection changed while it was being built
    store.patch('csv', { status: 'done', last: res });
    descargarBlob(res.csvBlob, res.filename);
  } catch (e) {
    console.error(e);
    if (token === csvToken) store.patch('csv', { status: 'error', error: e });
  }
}

/* ---------- start ---------- */

$('csv-limit').textContent = CONFIG.CSV_MAX_ROWS.toLocaleString('en-US');
const params = new URLSearchParams(location.search);
const forced = params.get('screen');
if (forced) store.set({ forceScreen: forced });
cablearControles();
render();
arrancar();

if (params.get('debug') === '1') {
  window.__app = { store, D, mapa: () => mapa, aplicarForma, limpiarAoi, seleccionarPais, descargarCsv, polys };
}
