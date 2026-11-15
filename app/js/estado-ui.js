// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// estado-ui.js - DOM utilities: paints the four screen states, the summary, the bounds fields
// and the date selectors. No business logic (that lives in aoi.js / csv.js / estado.js).

import { computeScreen } from './estado.js';
import { SCOPES, monthKey } from './csv.js';
import { aplicarNotasMetodo, describirExperimentos } from './notas-metodo.js';

export const $ = (id) => document.getElementById(id);

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtInt = (n) => Math.round(n).toLocaleString('en-US');
const fmtDec = (n) => n.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmtDeg = (n) => (Math.round(n * 10) / 10).toFixed(1);

/* ---------- state texts ---------- */

const REASON_TEXT = {
  initial: { title: 'Loading data', detail: 'Reading the dataset description and the country outlines.' },
  'aoi-data': { title: 'Loading monthly counts for your area', detail: 'Only the 1-degree tiles that cover your area are downloaded.' },
  'no-aoi': {
    title: 'No area selected yet',
    detail: 'Draw a rectangle or polygon on the map, pick a preset area, or enter bounds and press "Apply bounds".',
  },
  'no-cells': {
    title: 'The area is too small',
    detail: 'No 0.1-degree cell center falls inside your shape. Draw a slightly larger area.',
  },
  'outside-coverage': {
    title: 'Outside processed coverage',
    detail: 'This area is outside Mexico and Argentina, the only countries processed. That is not "zero fires": there is simply no data here.',
  },
  'no-detections': {
    title: 'No hotspot detections for this selection',
    detail: 'The cells and dates you chose have no detections in the series. Try a wider date range or area.',
  },
  'country-unavailable': {
    title: 'This country is not processed yet',
    detail: 'Its data has not been exported in this build, so the area is outside processed coverage. That is not "zero fires": there is no data.',
  },
  forced: { title: 'Forced state (test hook)', detail: 'This state was forced with the "screen" URL parameter.' },
  ok: { title: 'Ready', detail: '' },
};

/** Paints the #status panel according to the derived screen state. Returns {screen, reason}. */
export function renderScreen(state) {
  const info = computeScreen(state);
  const st = $('status');
  st.dataset.screen = info.screen;
  const t = REASON_TEXT[info.reason] || REASON_TEXT.ok;
  let title = t.title;
  let detail = t.detail;
  if (info.screen === 'error') {
    title = info.reason === 'initial' ? 'The app could not load its data' : 'Could not load the data for your area';
    detail = info.error ? errorMessage(info.error) : 'Unknown error.';
    if (info.reason === 'forced') detail = REASON_TEXT.forced.detail;
  }
  if (info.reason === 'forced') {
    title = `${title}: ${info.screen}`;
    detail = REASON_TEXT.forced.detail;
  }
  $('status-title').textContent = title;
  $('status-detail').textContent = detail;
  st.setAttribute('role', info.screen === 'error' ? 'alert' : 'status');
  $('status-retry').hidden = info.screen !== 'error';
  const prog = $('data-progress');
  prog.hidden = !(info.screen === 'loading' && info.reason === 'aoi-data');
  if (!prog.hidden) prog.value = state.data.progress || 0;
  $('summary').hidden = !(info.screen === 'ready');
  document.body.dataset.screen = info.screen;
  return info;
}

export function errorMessage(e) {
  if (!e) return 'Unknown error.';
  if (e.name === 'LeakError') return `Data integrity check failed: ${e.message}`;
  return e.message || String(e);
}

/* ---------- summary ---------- */

export function renderSummary(state, csvLimit) {
  const { aoi, range, scope, data, manifest } = state;
  const s = data.summary;
  if (!aoi || !s) return;
  const pais = manifest.paises[state.pais];
  $('sum-country').textContent = pais.nombre;
  const b = aoi.coveredBbox || aoi.bbox;
  let area = `${fmtInt(aoi.covered.length)} cells (${fmtDeg(b.south)} to ${fmtDeg(b.north)} N, ${fmtDeg(b.west)} to ${fmtDeg(b.east)} E)`;
  if (aoi.outside.length) area += `; ${fmtInt(aoi.outside.length)} more cells are outside processed coverage and not counted`;
  $('sum-area').textContent = area;
  $('sum-dates').textContent = `${monthKey(range.from.y, range.from.m)} to ${monthKey(range.to.y, range.to.m)}`;
  $('sum-rows').textContent = fmtInt(s.rows);
  $('sum-veq').textContent = fmtDec(scope === 'all' ? s.vmAll : s.veq);
  $('sum-masked-label').textContent = scope === 'all' ? 'Masked detections (included above)' : 'Masked detections (excluded)';
  $('sum-masked').textContent = fmtInt(s.masked);
  $('sum-prov').textContent = fmtInt(s.provisionalRows);
  $('sum-inc').textContent = fmtInt(s.incompleteMonths);
  $('csv-limit').textContent = fmtInt(csvLimit);
}

/* ---------- download buttons ---------- */

export function renderDownloads(state, csvLimit, capCheck) {
  const btn = $('btn-csv');
  const msg = $('csv-msg');
  const s = state.data.summary;
  const prog = $('csv-progress');
  const building = state.csv.status === 'building';
  prog.hidden = !building;
  if (building) prog.value = state.csv.progress || 0;
  if (!s) {
    btn.disabled = true;
    return;
  }
  btn.textContent = building ? 'Preparing CSV...' : `Download CSV (${fmtInt(s.rows)} rows)`;
  btn.disabled = building || !capCheck.ok || s.rows === 0;
  $('btn-meta').disabled = !(state.csv.last && state.csv.status !== 'building');
  msg.className = 'csv-msg';
  if (!capCheck.ok) {
    msg.textContent = capCheck.message;
    msg.classList.add('bad');
  } else if (state.csv.status === 'error') {
    msg.textContent = `The CSV could not be built: ${errorMessage(state.csv.error)}`;
    msg.classList.add('bad');
  } else if (state.csv.last) {
    const l = state.csv.last;
    if (l.match) {
      msg.textContent = `Downloaded ${fmtInt(l.rows)} rows. The file matches the count shown. Save the metadata file with it.`;
    } else {
      msg.textContent = `Warning: the file has ${fmtInt(l.rows)} rows but the screen shows ${fmtInt(s.rows)}. Please report this mismatch (details are in the metadata file).`;
      msg.classList.add('warn');
    }
  } else {
    msg.textContent = '';
  }
}

/* ---------- bounds fields ---------- */

const BOUND_IDS = { south: 'b-south', north: 'b-north', west: 'b-west', east: 'b-east' };

export function leerBounds() {
  const out = {};
  for (const [k, id] of Object.entries(BOUND_IDS)) {
    const el = $(id);
    out[k] = el.value === '' ? null : Number(el.value);
  }
  return out;
}

export function escribirBounds(bbox) {
  for (const [k, id] of Object.entries(BOUND_IDS)) $(id).value = bbox ? fmtDeg(bbox[k]) : '';
}

/** Sets min/max of the fields to the active country. */
export function limitesCampos(limits) {
  $('b-south').min = $('b-north').min = String(Math.floor(limits.south));
  $('b-south').max = $('b-north').max = String(Math.ceil(limits.north));
  $('b-west').min = $('b-east').min = String(Math.floor(limits.west));
  $('b-west').max = $('b-east').max = String(Math.ceil(limits.east));
}

export function mostrarErroresBounds(errors) {
  for (const [k, id] of Object.entries(BOUND_IDS)) {
    $(id).removeAttribute('aria-invalid');
    $(`err-${k}`).hidden = true;
    $(`err-${k}`).textContent = '';
  }
  $('err-bounds').hidden = true;
  $('err-bounds').textContent = '';
  for (const e of errors) {
    if (BOUND_IDS[e.field]) {
      $(BOUND_IDS[e.field]).setAttribute('aria-invalid', 'true');
      $(`err-${e.field}`).textContent = e.message;
      $(`err-${e.field}`).hidden = false;
    } else {
      $('err-bounds').textContent = e.message;
      $('err-bounds').hidden = false;
    }
  }
}

/* ---------- selectors ---------- */

export function llenarPaises(manifest, selected) {
  const sel = $('country');
  sel.replaceChildren();
  for (const p of Object.values(manifest.paises)) {
    sel.add(new Option(p.disponible ? p.nombre : `${p.nombre} (not processed yet)`, p.id, false, p.id === selected));
  }
  sel.disabled = false;
}

export function llenarPresets(pais, selectedId) {
  const sel = $('preset');
  sel.replaceChildren(new Option('Select a preset area', ''));
  for (const a of pais.aoiPredef) sel.add(new Option(a.nombre, a.id, false, a.id === selectedId));
  sel.disabled = false;
  if (!selectedId) sel.value = '';
}

export function llenarFechas(serieInicio, ultimoMes) {
  for (const w of ['from', 'to']) {
    const ys = $(`${w}-year`);
    ys.replaceChildren();
    for (let y = serieInicio.y; y <= ultimoMes.y; y++) ys.add(new Option(String(y), String(y)));
    const ms = $(`${w}-month`);
    ms.replaceChildren();
    MONTHS.forEach((n, i) => ms.add(new Option(n, String(i + 1))));
    ys.disabled = ms.disabled = false;
  }
}

/** Enables only the valid months of the chosen year (start of the series / last month with data). */
export function acotarMeses(serieInicio, ultimoMes) {
  for (const w of ['from', 'to']) {
    const y = Number($(`${w}-year`).value);
    const ms = $(`${w}-month`);
    for (const o of ms.options) {
      const m = Number(o.value);
      o.disabled = (y === serieInicio.y && m < serieInicio.m) || (y === ultimoMes.y && m > ultimoMes.m);
    }
    if (ms.selectedOptions[0] && ms.selectedOptions[0].disabled) {
      const first = [...ms.options].find((o) => !o.disabled);
      if (first) ms.value = first.value;
    }
  }
}

export function escribirRango(range) {
  $('from-year').value = String(range.from.y);
  $('from-month').value = String(range.from.m);
  $('to-year').value = String(range.to.y);
  $('to-month').value = String(range.to.m);
}

export function leerRango() {
  return {
    from: { y: Number($('from-year').value), m: Number($('from-month').value) },
    to: { y: Number($('to-year').value), m: Number($('to-month').value) },
  };
}

export function llenarRapidos(rapidos) {
  const sel = $('quick-range');
  sel.replaceChildren(new Option('Custom range', ''));
  for (const r of rapidos) sel.add(new Option(r.label, r.id));
  sel.disabled = false;
  sel.value = 'all';
}

/* ---------- about ---------- */

export function renderAbout(manifest) {
  const kv = $('about-kv');
  kv.replaceChildren();
  const add = (k, v) => {
    const d = document.createElement('div');
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = k;
    dd.textContent = v;
    d.append(dt, dd);
    kv.append(d);
  };
  add('Dataset version', manifest.version ?? 'n/a');
  add('Generated (UTC)', manifest.generadoUtc ?? 'n/a');
  add('Last data date', manifest.datosHasta ?? 'n/a');
  add('Code commit', manifest.commit ?? 'n/a');
  add('Experiment runs', describirExperimentos(manifest));
  add('Data origin', manifest.synthetic ? 'SYNTHETIC' : 'Exported from the analysis core');
  // "Method notes" (js/notas-metodo.js): plain-English text with the validation status read from the manifest; no decision identifiers.
  aplicarNotasMetodo(manifest);
}

/** Method notes before the manifest is known (also the text that stays on screen if the data fail to load). */
export function renderMethodNotesBase() {
  aplicarNotasMetodo(null);
}

export function mostrarBannerSynthetic(on, texto) {
  $('banner-synthetic').hidden = !on;
  if (on && texto) $('banner-text').textContent = texto;
}

export function mensajeBasemap(texto) {
  const n = $('basemap-note');
  n.textContent = texto || '';
  n.hidden = !texto;
}

export { SCOPES };
