// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// csv-descarga.js - CSV I/O: downloads the point tiles (Parquet snappy) of the AOI cells,
// reads them with hyparquet (lazy loading) and builds the CSV. The pure logic lives in csv.js.
//
// Guarantee RT-11: the number of rows of the CSV is compared with the displayed count (countMonthly).

import { DataError, conLimite } from './datos.js';
import { CONFIG } from './datos-config.js';
import {
  CSV_HEADER,
  buildMetadata,
  csvFilename,
  filterPoints,
  pointToCsvLine,
  rangeToDates,
} from './csv.js';

let hyparquetPromise = null;

/** Imports hyparquet only when needed (local vendor, ES modules). */
function cargarHyparquet() {
  if (!hyparquetPromise) {
    hyparquetPromise = import('../vendor/hyparquet/src/index.js').catch((e) => {
      hyparquetPromise = null;
      throw new DataError('Could not load the Parquet reader (vendor/hyparquet).', { cause: e });
    });
  }
  return hyparquetPromise;
}

async function leerTesela(base, pais, tesela, hp) {
  const url = `${base}${pais.id}/puntos/${tesela}.parquet`;
  let res;
  try {
    res = await fetch(url);
  } catch (e) {
    throw new DataError(`Network error while loading ${url}`, { url, cause: e });
  }
  if (!res.ok) throw new DataError(`Could not load ${url} (HTTP ${res.status})`, { url, status: res.status });
  const buf = await res.arrayBuffer();
  try {
    return await hp.parquetReadObjects({ file: buf });
  } catch (e) {
    throw new DataError(`Could not read ${url} as Parquet (snappy expected).`, { url, cause: e });
  }
}

/**
 * Builds the CSV of the AOI.
 * ctx: {base, pais (parsed), aoi, range, scope, manifest, shownCount, onProgreso}
 * Returns {text, rows, csvBlob, metaBlob, filename, metaFilename, metadata, match}.
 */
export async function construirCsv(ctx) {
  const { base, pais, aoi, range, scope, manifest, shownCount, onProgreso } = ctx;
  const hp = await cargarHyparquet();
  const { fromDate, toDate } = rangeToDates(range);
  const cellSet = new Set(aoi.covered.map((c) => c.id));
  const tiles = [...aoi.tiles].filter((t) => (pais.teselasPuntos || pais.teselas).has(t));
  if (tiles.length > CONFIG.MAX_TILES) {
    throw new DataError(`Area too large (${tiles.length} tiles; maximum ${CONFIG.MAX_TILES}).`);
  }

  const entradas = []; // [key, line]
  await conLimite(
    tiles,
    Math.min(CONFIG.FETCH_CONCURRENCY, 4),
    async (t) => {
      const recs = await leerTesela(base, pais, t, hp);
      const pts = filterPoints(recs, { cellSet, fromDate, toDate, scope });
      for (const p of pts) {
        entradas.push([`${p.date}|${p.time}|${p.lat.toFixed(5)}|${p.lon.toFixed(5)}|${p.platform}`, pointToCsvLine(p)]);
      }
    },
    onProgreso,
  );
  entradas.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));

  const lineas = new Array(entradas.length + 1);
  lineas[0] = CSV_HEADER.join(',');
  for (let i = 0; i < entradas.length; i++) lineas[i + 1] = entradas[i][1];
  const text = `${lineas.join('\n')}\n`;
  const rows = entradas.length;

  const filename = csvFilename({ pais: pais.id, aoiBbox: aoi.coveredBbox || aoi.bbox, range, scope, synthetic: manifest.synthetic });
  const metaFilename = filename.replace(/\.csv$/, '_metadata.json');
  const metadata = buildMetadata({
    manifest,
    pais: pais.id,
    aoi,
    range,
    scope,
    shownCount,
    csvRows: rows,
    generatedUtc: new Date().toISOString(),
    filename,
  });
  return {
    text,
    rows,
    filename,
    metaFilename,
    metadata,
    match: rows === shownCount,
    csvBlob: new Blob([text], { type: 'text/csv;charset=utf-8' }),
    metaBlob: new Blob([`${JSON.stringify(metadata, null, 2)}\n`], { type: 'application/json' }),
  };
}

/** Triggers the download of a Blob (browser only). */
export function descargarBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
