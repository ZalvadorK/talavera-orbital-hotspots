// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// csv.js - PURE functions: monthly count of the AOI, point filter, CSV serialization,
// metadata and the guarantee CSV = displayed count (RT-11). Tested in app/tests/csv.test.mjs.
//
// Definitions (ADR-0002, ADR-0004, ADR-0010 I-06):
//  - Series by era (tramo): T = Terra | TA = Terra+Aqua | S = S-NPP | N = NOAA-20 standard | NP = NOAA-20 NRT.
//  - Series rows outside the mask in a month = t (T) | t+a (TA) | s (S) | n20 (N, NP).
//  - With scope "all" (all thermal anomalies) xm (inside the mask) is added too.
//  - Date range of the UI = whole months (UTC): so the monthly count is exact.
//  - ANTI-LEAK (ADR-0005): Terra/Aqua/S-NPP dated >= 2019-01-01 are reserved; here they are
//    rejected with an error (LeakError), not silently filtered.

import { cellIdOfPoint, normalizeCellId } from './aoi.js';

export const RESERVED_FROM = '2019-01-01';
export const RESERVED_PLATFORMS = Object.freeze(['Terra', 'Aqua', 'S-NPP']);
export const TRAMOS = Object.freeze(['T', 'TA', 'S', 'N', 'NP']);

export class LeakError extends Error {
  constructor(message) {
    super(message);
    this.name = 'LeakError';
  }
}

/* ---------- months ---------- */

/** {y,m} -> integer month index. */
export function monthIndex(y, m) {
  return y * 12 + (m - 1);
}

export function monthKey(y, m) {
  return `${y}-${String(m).padStart(2, '0')}`;
}

/** Parses "YYYY-MM" -> {y,m} or null. */
export function parseMonthKey(s) {
  const r = /^(\d{4})-(\d{2})$/.exec(s || '');
  if (!r) return null;
  const y = +r[1];
  const m = +r[2];
  return m >= 1 && m <= 12 ? { y, m } : null;
}

/** Last day (1-31) of a month. */
export function daysInMonth(y, m) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

/** Range {from:{y,m}, to:{y,m}} -> inclusive ISO dates {fromDate, toDate}. */
export function rangeToDates(range) {
  const { from, to } = range;
  return {
    fromDate: `${from.y}-${String(from.m).padStart(2, '0')}-01`,
    toDate: `${to.y}-${String(to.m).padStart(2, '0')}-${String(daysInMonth(to.y, to.m)).padStart(2, '0')}`,
  };
}

export function validateRange(range, { minMonth, maxMonth } = {}) {
  const errors = [];
  if (!range || !range.from || !range.to) return { ok: false, errors: ['Date range is incomplete'] };
  const a = monthIndex(range.from.y, range.from.m);
  const b = monthIndex(range.to.y, range.to.m);
  if (a > b) errors.push('"From" must not be after "To"');
  if (minMonth && a < monthIndex(minMonth.y, minMonth.m)) errors.push('"From" is before the start of the series');
  if (maxMonth && b > monthIndex(maxMonth.y, maxMonth.m)) errors.push('"To" is after the last month with data');
  return { ok: errors.length === 0, errors };
}

/* ---------- monthly count ---------- */

const num = (v) => (v === null || v === undefined || v === '' || Number.isNaN(+v) ? 0 : +v);

/** Raw series rows, outside the mask, of a monthly record (according to its era). */
export function rawOutsideMask(r) {
  switch (r.tramo) {
    case 'T':
      return num(r.t);
    case 'TA':
      return num(r.t) + num(r.a);
    case 'S':
      return num(r.s);
    case 'N':
    case 'NP':
      return num(r.n20);
    default:
      return 0;
  }
}

/** CSV rows that correspond to a monthly record according to the scope ('veg' | 'all'). */
export function rowsOfMonthly(r, scope) {
  return rawOutsideMask(r) + (scope === 'all' ? num(r.xm) : 0);
}

/** Scope -> text. */
export const SCOPES = Object.freeze({
  veg: 'Vegetation fires only (outside the static mask)',
  all: 'All thermal anomalies (including masked detections)',
});

/**
 * Anti-leak assertion on monthly records: t, a, s must be EMPTY if y >= 2019. Throws LeakError otherwise.
 * With { allowReserved: true } (manifest.verdict exists: the single test has been run and the exporter writes the raw counts of
 * 2019 onward) the assertion is skipped. The point tiles keep their own strict check (assertPointNoLeak): they never hold them.
 */
export function assertMonthlyNoLeak(rows, { allowReserved = false } = {}) {
  if (allowReserved) return true;
  for (const r of rows) {
    if (r.y >= 2019 && (isFilled(r.t) || isFilled(r.a) || isFilled(r.s))) {
      throw new LeakError(
        `Reserved data found in monthly tile (${r.c} ${r.y}-${r.m}): Terra/Aqua/S-NPP counts must be empty from 2019 on.`,
      );
    }
  }
  return true;
}
const isFilled = (v) => v !== null && v !== undefined && v !== '' && !Number.isNaN(+v);

/**
 * Counts over monthly records that are already parsed.
 * rows: records {c,y,m,tramo,v,vm,t,a,s,n20,xm,inc,prov}; cellSet: Set of "lat_lon" ids.
 * Returns {rows, veq, vmAll, masked, provisionalRows, incompleteMonths, months, perMonth}.
 */
export function countMonthly(rows, cellSet, range, scope) {
  const a = monthIndex(range.from.y, range.from.m);
  const b = monthIndex(range.to.y, range.to.m);
  const out = {
    rows: 0, // rows the CSV will have
    veq: 0, // VIIRS-eq sum outside the mask (v)
    vmAll: 0, // including masked ones (vm)
    masked: 0, // raw detections inside the mask (xm)
    provisionalRows: 0, // rows that come from provisional NRT months
    incompleteMonths: 0,
    months: 0,
    perMonth: new Map(),
  };
  const incSet = new Set();
  for (const r of rows) {
    if (!cellSet.has(r.c)) continue;
    const mi = monthIndex(r.y, r.m);
    if (mi < a || mi > b) continue;
    const n = rowsOfMonthly(r, scope);
    out.rows += n;
    out.veq += num(r.v);
    out.vmAll += num(r.vm);
    out.masked += num(r.xm);
    if (+r.prov === 1) out.provisionalRows += n;
    const k = monthKey(r.y, r.m);
    if (+r.inc === 1) incSet.add(k);
    let pm = out.perMonth.get(k);
    if (!pm) {
      pm = { y: r.y, m: r.m, rows: 0, veq: 0, vmAll: 0, masked: 0, inc: 0, prov: 0 };
      out.perMonth.set(k, pm);
    }
    pm.rows += n;
    pm.veq += num(r.v);
    pm.vmAll += num(r.vm);
    pm.masked += num(r.xm);
    if (+r.inc === 1) pm.inc = 1;
    if (+r.prov === 1) pm.prov = 1;
  }
  out.incompleteMonths = incSet.size;
  out.months = out.perMonth.size;
  return out;
}

/**
 * Incomplete months of the range according to disponibilidad.json (CONTRATO-DATOS.md §9): union of
 * meses_incompletos (MODIS outage without backup) and meses_parciales (Jan 2012), counted once.
 * Returns null if there is no availability information (the UI then uses the indicator of the rows).
 */
export function incompleteMonthsInRange(disp, range) {
  if (!disp || typeof disp !== 'object') return null;
  const a = monthIndex(range.from.y, range.from.m);
  const b = monthIndex(range.to.y, range.to.m);
  const set = new Set();
  for (const lista of [disp.meses_incompletos, disp.meses_parciales]) {
    if (!Array.isArray(lista)) continue;
    for (const r of lista) {
      const mi = monthIndex(Number(r.y), Number(r.m));
      if (mi >= a && mi <= b) set.add(mi);
    }
  }
  return set.size;
}

/** CSV cap. Returns {ok, message}. */
export function checkCap(rowCount, maxRows) {
  if (rowCount > maxRows) {
    return {
      ok: false,
      message: `This selection has ${rowCount.toLocaleString('en-US')} rows; the download limit is ${maxRows.toLocaleString('en-US')}. Narrow the date range or the area.`,
    };
  }
  return { ok: true, message: '' };
}

/* ---------- points ---------- */

/** ISO date "YYYY-MM-DD" from Date | string | number (days since 1970) | bigint (ms or us). */
export function toIsoDate(v) {
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? '' : v.toISOString().slice(0, 10);
  if (typeof v === 'string') return v.slice(0, 10);
  if (typeof v === 'bigint') v = Number(v);
  if (typeof v === 'number') {
    if (Math.abs(v) < 1e6) return new Date(v * 86400000).toISOString().slice(0, 10); // DATE32 (days)
    if (Math.abs(v) > 1e14) return new Date(v / 1000).toISOString().slice(0, 10); // microseconds
    return new Date(v).toISOString().slice(0, 10); // milliseconds
  }
  return '';
}

/** Time "HH:MM" from string "HHMM"/"HH:MM"/"HH:MM:SS" or integer HHMM. */
export function toTimeHHMM(v) {
  if (v === null || v === undefined || v === '') return '';
  if (v instanceof Date) return v.toISOString().slice(11, 16);
  if (typeof v === 'bigint') v = Number(v);
  if (typeof v === 'number') {
    const s = String(Math.trunc(v)).padStart(4, '0');
    return `${s.slice(0, 2)}:${s.slice(2, 4)}`;
  }
  const s = String(v).trim();
  if (/^\d{1,2}:\d{2}/.test(s)) return s.slice(0, 5).padStart(5, '0');
  if (/^\d{3,4}$/.test(s)) return `${s.padStart(4, '0').slice(0, 2)}:${s.padStart(4, '0').slice(2, 4)}`;
  return s;
}

const nz = (v) => (typeof v === 'bigint' ? Number(v) : v);
const bool = (v) => v === true || v === 1 || v === '1' || v === 'true' || v === 'True' || v === 'TRUE';

/** Normalizes a Parquet row into a flat object with simple JS types. */
export function normalizePoint(rec) {
  return {
    lat: Number(nz(rec.lat)),
    lon: Number(nz(rec.lon)),
    date: toIsoDate(rec.fecha_utc),
    time: toTimeHHMM(rec.hora_utc),
    platform: rec.plataforma ?? '',
    processing: rec.procesamiento ?? '',
    weight: nz(rec.peso) ?? '',
    inMask: bool(rec.en_mascara),
    multipass: bool(rec.flag_multipaso),
    frp: nz(rec.frp) ?? '',
    confidence: nz(rec.confidence) ?? '',
    type: nz(rec.type) ?? '',
    segment: rec.tramo ?? '',
  };
}

/** Anti-leak assertion on a normalized point. */
export function assertPointNoLeak(p) {
  if (RESERVED_PLATFORMS.includes(p.platform) && p.date >= RESERVED_FROM) {
    throw new LeakError(
      `Reserved data found in a point tile (${p.platform} ${p.date}): not allowed before the validation verdict.`,
    );
  }
  return true;
}

/**
 * Filters rows of a point tile (raw Parquet objects).
 * opts: {cellSet:Set<string>, fromDate, toDate, scope}
 * Returns normalized rows.
 */
export function filterPoints(records, { cellSet, fromDate, toDate, scope }) {
  const out = [];
  for (const rec of records) {
    const p = normalizePoint(rec);
    assertPointNoLeak(p); // leak: error, not a silent filter
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon)) continue;
    if (!cellSet.has(cellIdOfPoint(p.lat, p.lon))) continue;
    if (p.date < fromDate || p.date > toDate) continue;
    if (scope !== 'all' && p.inMask) continue;
    out.push(p);
  }
  return out;
}

/* ---------- serialization ---------- */

export const CSV_HEADER = Object.freeze([
  'latitude',
  'longitude',
  'acq_date_utc',
  'acq_time_utc',
  'platform',
  'processing',
  'viirs_eq_weight',
  'in_static_mask',
  'multipass_flag',
  'frp_mw',
  'confidence_raw',
  'type',
  'series_segment',
]);

function esc(v) {
  if (v === null || v === undefined) return '';
  const s = typeof v === 'boolean' ? (v ? 'true' : 'false') : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** CSV row (no line break) from a normalized point. */
export function pointToCsvLine(p) {
  return [
    p.lat,
    p.lon,
    p.date,
    p.time,
    p.platform,
    p.processing,
    p.weight,
    p.inMask,
    p.multipass,
    p.frp,
    p.confidence,
    p.type,
    p.segment,
  ]
    .map(esc)
    .join(',');
}

/** Header + rows -> CSV text (LF). The number of data rows = rows.length. */
export function toCsv(rows) {
  const lines = [CSV_HEADER.join(',')];
  for (const p of rows) lines.push(pointToCsvLine(p));
  return `${lines.join('\n')}\n`;
}

/** Counts the data rows of a CSV text (without the header). */
export function countCsvDataRows(text) {
  const lines = text.split('\n').filter((l) => l.length > 0);
  return Math.max(0, lines.length - 1);
}

/** Stable order: date, time, lat, lon. */
export function sortPoints(rows) {
  return rows.sort(
    (a, b) =>
      a.date.localeCompare(b.date) || a.time.localeCompare(b.time) || a.lat - b.lat || a.lon - b.lon,
  );
}

/** File name. */
export function csvFilename({ pais, aoiBbox, range, scope, synthetic }) {
  const f = (x) => String(x).replace('-', 'm').replace('.', 'p');
  const b = aoiBbox ? `${f(aoiBbox.south)}_${f(aoiBbox.west)}_${f(aoiBbox.north)}_${f(aoiBbox.east)}` : 'aoi';
  const r = `${monthKey(range.from.y, range.from.m)}_${monthKey(range.to.y, range.to.m)}`;
  return `${synthetic ? 'SYNTHETIC_' : ''}hotspots_${pais}_${b}_${r}_${scope === 'all' ? 'all' : 'veg'}.csv`;
}

/**
 * Metadata of the CSV (a separate JSON file so as not to alter the number of rows, RT-11).
 */
export function buildMetadata({ manifest, pais, aoi, range, scope, shownCount, csvRows, generatedUtc, filename }) {
  const { fromDate, toDate } = rangeToDates(range);
  return {
    file: filename,
    synthetic: !!manifest.synthetic,
    note: 'Counts are hotspot detections, not individual fires. Dates are UTC.',
    generated_with: 'SI-generated (AI): Claude Code wrote this app during the event; reviewed by the team.',
    generated_utc: generatedUtc,
    data_source: 'NASA FIRMS (MODIS and VIIRS active-fire detections), harmonized series. Credit: NASA FIRMS.',
    series_definition:
      'Terra only (2000-12 to 2002-06), Terra+Aqua (2002-07 to 2011-12), S-NPP (2012-01 to 2018-03), NOAA-20 (2018-04 onward; NRT from 2026-08 is provisional).',
    scope: SCOPES[scope] || scope,
    country: pais,
    aoi_snapped_bbox: aoi.bbox,
    aoi_cells_covered: aoi.covered.length,
    aoi_cells_outside_coverage: aoi.outside.length,
    coverage_rule:
      'A 0.1-degree cell is covered if its center is inside the country outline or the outline (coast or border) crosses it; other cells are outside processed coverage and are not counted.',
    date_from_utc: fromDate,
    date_to_utc: toDate,
    rows_shown_on_screen: shownCount,
    rows_in_csv: csvRows,
    rows_match: shownCount === csvRows,
    dataset_version: manifest.version ?? null,
    dataset_generated_utc: manifest.generado_utc ?? null,
    dataset_commit: manifest.commit ?? null,
    dataset_last_data_date: manifest.datos_hasta ?? null,
    columns: CSV_HEADER,
  };
}

/** Normalizes the cell id of a monthly record (for robustness against "19_-98.7"). */
export function normalizeMonthlyCell(r) {
  const id = normalizeCellId(r.c);
  return id ?? r.c;
}
