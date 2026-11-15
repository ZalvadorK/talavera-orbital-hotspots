// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// estado.js - app state store (no DOM) and derivation of the FOUR screen states:
// loading | empty | error | ready.
//
// Public API for the calendar (app-2), via estado-arranque.js:
//   const store = crearEstado(); store.get() -> snapshot; store.subscribe(fn) -> unsubscribe.
//   snapshot.manifest   parsed manifest (see datos.js validarManifest)
//   snapshot.pais       id of the active country ("mexico" | "argentina")
//   snapshot.aoi        null | {kind, cells, covered, outside, bbox, tiles, unavailable}  (AOI already snapped to 0.1 degrees;
//                        unavailable=true if the country is in the manifest but has no exported data)
//   snapshot.range      {from:{y,m}, to:{y,m}}  (whole months, UTC)
//   snapshot.scope      'veg' (vegetation fires only, outside the mask) | 'all' (all thermal anomalies)
//   snapshot.data       {status, rows (monthly records of the AOI cells, ALL dates),
//                        summary (count of the chosen range and scope), error}
// The monthly records have the columns of the contract: c,y,m,tramo,v,vm,t,a,s,n20,xm,inc,prov.

export const SCREENS = Object.freeze(['loading', 'empty', 'error', 'ready']);

export function estadoInicial() {
  return {
    load: { status: 'loading', error: null }, // initial load (manifest + outlines)
    manifest: null,
    base: null,
    pais: null,
    aoi: null,
    aoiSource: null, // {kind:'bbox'|'polygon'|'preset', ...} what was drawn / typed
    presetId: null,
    range: null,
    scope: 'veg',
    data: { status: 'idle', rows: null, summary: null, error: null, progress: 0 },
    csv: { status: 'idle', progress: 0, message: '', error: null },
    forceScreen: null, // test hook: ?screen=loading|empty|error
  };
}

/** Derives the screen state and its reason. Pure. */
export function computeScreen(s) {
  if (s.forceScreen && SCREENS.includes(s.forceScreen)) return { screen: s.forceScreen, reason: 'forced' };
  if (s.load.status === 'loading') return { screen: 'loading', reason: 'initial' };
  if (s.load.status === 'error') return { screen: 'error', reason: 'initial', error: s.load.error };
  if (!s.aoi) return { screen: 'empty', reason: 'no-aoi' };
  if (!s.aoi.cells.length) return { screen: 'empty', reason: 'no-cells' };
  if (s.aoi.unavailable) return { screen: 'empty', reason: 'country-unavailable' };
  if (!s.aoi.covered.length) return { screen: 'empty', reason: 'outside-coverage' };
  if (s.data.status === 'loading' || s.data.status === 'idle') return { screen: 'loading', reason: 'aoi-data' };
  if (s.data.status === 'error') return { screen: 'error', reason: 'aoi-data', error: s.data.error };
  if (s.data.summary && s.data.summary.rows === 0) {
    return { screen: 'empty', reason: 'no-detections' };
  }
  return { screen: 'ready', reason: 'ok' };
}

export function crearEstado(inicial = estadoInicial()) {
  let state = inicial;
  const subs = new Set();
  return {
    get: () => state,
    /** Merges a shallow patch (and known nested keys) and notifies. */
    set(patch) {
      state = { ...state, ...patch };
      for (const fn of [...subs]) fn(state, patch);
    },
    patch(key, sub) {
      state = { ...state, [key]: { ...state[key], ...sub } };
      for (const fn of [...subs]) fn(state, { [key]: state[key] });
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}

/** Default range: the whole series up to the last month with data. */
export function rangoCompleto(serieInicio, ultimoMes) {
  return { from: { ...serieInicio }, to: { ...ultimoMes } };
}

/** Quick ranges for the selector. Returns [{id,label,range}] bounded to the series. */
export function rangosRapidos(serieInicio, ultimoMes) {
  const idx = (r) => r.y * 12 + (r.m - 1);
  const fromIdx = (i) => ({ y: Math.floor(i / 12), m: (i % 12) + 1 });
  const lastIdx = idx(ultimoMes);
  const startIdx = idx(serieInicio);
  const clampFrom = (i) => fromIdx(Math.max(i, startIdx));
  const out = [
    { id: 'all', label: 'Entire series', range: rangoCompleto(serieInicio, ultimoMes) },
    { id: 'last12', label: 'Last 12 months', range: { from: clampFrom(lastIdx - 11), to: { ...ultimoMes } } },
    { id: 'last5y', label: 'Last 5 years', range: { from: clampFrom(lastIdx - 59), to: { ...ultimoMes } } },
    { id: 'viirs', label: 'VIIRS era (2012 onward)', range: { from: clampFrom(2012 * 12), to: { ...ultimoMes } } },
    { id: 'modis', label: 'MODIS era (2000-12 to 2011-12)', range: { from: { ...serieInicio }, to: { y: 2011, m: 12 } } },
  ];
  return out.filter((r) => idx(r.range.from) <= idx(r.range.to));
}
