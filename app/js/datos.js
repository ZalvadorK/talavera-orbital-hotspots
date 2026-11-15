// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// datos.js - loads the artifacts that src/exportar_demo.py writes (contract:
// app/data/CONTRATO-DATOS.md). Relative paths; no keys. The parsing functions are pure
// and are tested in app/tests/datos.test.mjs.

import { CONFIG } from './datos-config.js';
import { normalizeBbox, normalizeCellId } from './aoi.js';
import { assertMonthlyNoLeak } from './csv.js';

export class DataError extends Error {
  constructor(message, { url, status, cause } = {}) {
    super(message);
    this.name = 'DataError';
    this.url = url;
    this.status = status;
    this.cause = cause;
  }
}

/* ---------- parsing (pure) ---------- */

const MENSUAL_NUM = ['y', 'm', 'v', 'vm', 't', 'a', 's', 'n20', 'xm', 'inc', 'prov'];

/** Simple CSV (no quotes in the tiles): returns {header, rows:[string[]]}. */
export function splitCsv(text) {
  const lines = text.split(/\r?\n/);
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  if (!lines.length) return { header: [], rows: [] };
  const header = lines[0].split(',').map((h) => h.trim());
  const rows = new Array(lines.length - 1);
  for (let i = 1; i < lines.length; i++) rows[i - 1] = lines[i].split(',');
  return { header, rows };
}

/**
 * Parses a monthly tile. Empty values -> null (t, a, s are empty if y >= 2019 until the verdict exists).
 * Normalizes c and applies the anti-leak assertion (skipped with { allowReserved: true }, i.e. manifest.verdict is not null).
 */
export function parseMensual(text, { allowReserved = false } = {}) {
  const { header, rows } = splitCsv(text);
  const ix = {};
  header.forEach((h, i) => (ix[h] = i));
  for (const need of ['c', 'y', 'm', 'tramo']) {
    if (!(need in ix)) throw new DataError(`Monthly tile is missing column "${need}"`);
  }
  const out = [];
  for (const f of rows) {
    if (f.length < 4) continue;
    const r = {};
    for (const h of header) {
      const raw = f[ix[h]];
      if (MENSUAL_NUM.includes(h)) r[h] = raw === undefined || raw === '' ? null : Number(raw);
      else r[h] = raw === undefined ? '' : raw.trim();
    }
    r.c = normalizeCellId(r.c) ?? r.c;
    out.push(r);
  }
  assertMonthlyNoLeak(out, { allowReserved });
  return out;
}

/** Parses the manifest and validates it minimally (contract: app/data/CONTRATO-DATOS.md §2). */
export function validarManifest(m) {
  if (!m || typeof m !== 'object') throw new DataError('manifest.json is empty or not an object');
  if (!m.paises || typeof m.paises !== 'object' || !Object.keys(m.paises).length) {
    throw new DataError('manifest.json has no countries');
  }
  if (m.contrato !== undefined && Number(m.contrato) !== CONFIG.CONTRACT_VERSION) {
    throw new DataError(
      `This dataset uses data format ${m.contrato}, but this app reads format ${CONFIG.CONTRACT_VERSION}. Reload the page; if it persists, the dataset and the app are out of sync.`,
    );
  }
  const paises = {};
  for (const [id, p] of Object.entries(m.paises)) {
    const teselas = new Set((p.teselas || []).map(String));
    paises[id] = {
      id,
      nombre: p.nombre || id,
      bbox: normalizeBbox(p.bbox),
      disponible: p.disponible !== false, // false = country without data files (outside processed coverage)
      synthetic: p.synthetic ?? null,
      pesos: p.pesos ?? null,
      nota: p.nota ?? null,
      datosHasta: p.datos_hasta ?? null,
      nrtDesde: p.nrt_desde ?? null,
      inicioSerie: p.inicio_serie ?? null,
      teselas,
      teselasPuntos: new Set((p.teselas_puntos || [...teselas]).map(String)),
      teselasDiario: new Set((p.teselas_diario || []).map(String)),
      aoiPredef: (p.aoi_predef || [])
        .map((a) => ({
          id: a.id,
          nombre: a.nombre || a.id,
          bbox: normalizeBbox(a.bbox),
          bboxCeldas: normalizeBbox(a.bbox_celdas),
          nCeldas: a.n_celdas ?? null,
          nota: a.nota ?? null,
        }))
        .filter((a) => a.bbox),
    };
    if (!paises[id].bbox) throw new DataError(`manifest.json: country "${id}" has no valid bbox`);
  }
  return {
    contrato: m.contrato ?? null,
    version: m.version ?? null,
    generadoUtc: m.generado_utc ?? null,
    commit: m.commit ?? null,
    synthetic: !!m.synthetic,
    banner: m.banner ?? null,
    datosHasta: m.datos_hasta ?? null,
    metodo: m.metodo ?? { adr: [], exp: [] },
    verdict: m.verdict ?? null,
    huecosModis: m.huecos_modis ?? null,   // cross of our availability table with the FIRMS missing-data table (Method notes)
    paises,
    raw: m,
  };
}

/** Final month {y,m} of the dataset from datos_hasta ("YYYY-MM-DD" or "YYYY-MM"). */
export function ultimoMes(datosHasta) {
  const r = /^(\d{4})-(\d{2})/.exec(datosHasta || '');
  if (!r) return null;
  return { y: +r[1], m: +r[2] };
}

/* ---------- network ---------- */

async function getText(url) {
  let res;
  try {
    res = await fetch(url, { cache: 'no-cache' });
  } catch (e) {
    throw new DataError(`Network error while loading ${url}`, { url, cause: e });
  }
  if (!res.ok) throw new DataError(`Could not load ${url} (HTTP ${res.status})`, { url, status: res.status });
  return res.text();
}

async function getJson(url) {
  const t = await getText(url);
  try {
    return JSON.parse(t);
  } catch (e) {
    throw new DataError(`Invalid JSON in ${url}`, { url, cause: e });
  }
}

/**
 * Loads the manifest from CONFIG.DATA_BASE (written by src/exportar_demo.py). There is no fallback to any fixture:
 * if it is missing, it is a visible error (synthetic data is never shown "just in case"; ADR-0009).
 * Returns {manifest, base}.
 */
export async function cargarManifest() {
  const base = CONFIG.DATA_BASE;
  try {
    return { base, manifest: validarManifest(await getJson(`${base}manifest.json`)) };
  } catch (e) {
    if (e instanceof DataError && e.status === 404) {
      throw new DataError('The dataset is not available (data/manifest.json was not found).', { cause: e, url: e.url, status: 404 });
    }
    throw e;
  }
}

export function cargarContorno(base, paisId) {
  return getJson(`${base}${paisId}/contorno.geojson`);
}

export function cargarIntervalos(base, paisId) {
  return getJson(`${base}${paisId}/intervalos.json`);
}

const cacheDisp = new Map();

/** disponibilidad.json with cache. Returns null if it does not exist (the app then uses the `inc` indicator of the rows). */
export function cargarDisponibilidad(base, paisId) {
  const key = `${base}${paisId}`;
  if (!cacheDisp.has(key)) {
    cacheDisp.set(
      key,
      getJson(`${base}${paisId}/disponibilidad.json`).catch((e) => {
        if (e instanceof DataError && e.status === 404) return null;
        cacheDisp.delete(key);
        throw e;
      }),
    );
  }
  return cacheDisp.get(key);
}

const cacheMensual = new Map();

/** Loads and parses a monthly tile (cached). Tiles outside the list = no data ([]). */
export async function cargarTeselaMensual(base, pais, tesela, { allowReserved = false } = {}) {
  if (!pais.teselas.has(tesela)) return [];
  const key = `${base}${pais.id}/${tesela}|${allowReserved ? 'open' : 'closed'}`;
  if (!cacheMensual.has(key)) {
    cacheMensual.set(
      key,
      getText(`${base}${pais.id}/mensual/${tesela}.csv`).then((t) => parseMensual(t, { allowReserved }), (e) => {
        cacheMensual.delete(key);
        throw e;
      }),
    );
  }
  return cacheMensual.get(key);
}

/** Runs tasks with limited concurrency, reporting progress. */
export async function conLimite(items, limite, tarea, onProgreso) {
  const results = new Array(items.length);
  let next = 0;
  let done = 0;
  const worker = async () => {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      results[i] = await tarea(items[i], i);
      done++;
      if (onProgreso) onProgreso(done, items.length);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limite, items.length) }, worker));
  return results;
}

/**
 * Loads the monthly tiles of an AOI and returns the records of its cells (all dates).
 * covered: covered cells; cellSet: Set of ids. { allowReserved: true } only when manifest.verdict exists (raw 2019+ counts).
 */
export async function cargarMensualAoi(base, pais, covered, onProgreso, { allowReserved = false } = {}) {
  const tiles = [...new Set(covered.map((c) => c.tile))];
  if (tiles.length > CONFIG.MAX_TILES) {
    throw new DataError(`Area too large (${tiles.length} tiles; maximum ${CONFIG.MAX_TILES}). Draw a smaller area.`);
  }
  const cellSet = new Set(covered.map((c) => c.id));
  const parts = await conLimite(tiles, CONFIG.FETCH_CONCURRENCY, (t) => cargarTeselaMensual(base, pais, t, { allowReserved }), onProgreso);
  const rows = [];
  for (const part of parts) for (const r of part) if (cellSet.has(r.c)) rows.push(r);
  return { rows, cellSet, tiles };
}
