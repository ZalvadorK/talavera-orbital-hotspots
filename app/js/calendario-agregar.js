/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * calendario-agregar.js - turns the per-cell rows of the app data contract (app/data/CONTRATO-DATOS.md, sections 5 and 6)
 * into the input of FireCalendar.render:
 *   aggregateMonthly(rows, { last, disponibilidad })  sum over the cells of the AOI, one row per month from Dec 2000 to `last`.
 *        A month with no row is 0 detections (contract section 5: "ausencia de fila = 0"), NOT "no data", except the months the
 *        availability table lists as incomplete / partial (inc = 1). t, a, s stay null from 2019 (anti-leak) unless o.verdictOpen
 *        (manifest.verdict exists: the exporter then writes the raw counts of 2019 onward).
 *   aggregateDaily(rows)                              sum over the cells of the AOI, one row per day with detections (missing day = 0).
 *   buildInput(snapshot, parts)                       full input from the store snapshot of estado.js (aoi, range, scope, data.rows, manifest).
 *        It also computes the rule M1 ("too few MODIS": expected MODIS count of the area against CONFIG.MIN_MODIS_PER_MONTH, null = off)
 *        and passes the size of the area, so that fiabilidad.js can label the estimated months from manifest.verdict.
 * Works in the browser (window.FireCalendarAggregate) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var M = (typeof module === 'object' && typeof require === 'function') ? require('./calendario-modelo.js') : root.FireCalendarModel;
  var FR = (typeof module === 'object' && typeof require === 'function') ? require('./fiabilidad.js') : (root.FireReliability || null);
  var api = factory(M, FR);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireCalendarAggregate = api;
})(typeof window !== 'undefined' ? window : globalThis, function (M, FR) {
  'use strict';

  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function key(y, m) { return y * 12 + (m - 1); }
  function parseLast(x) {
    if (!x) return null;
    if (typeof x === 'string') { var r = /^(\d{4})-(\d{2})/.exec(x); return r ? { y: +r[1], m: +r[2] } : null; }
    return (isNum(x.y) && isNum(x.m)) ? { y: x.y, m: x.m } : null;
  }
  function sumNullable(rows, f) {
    var s = 0, any = false;
    rows.forEach(function (r) { if (isNum(r[f])) { s += r[f]; any = true; } });
    return any ? s : null;
  }

  function aggregateMonthly(rows, o) {
    o = o || {};
    rows = rows || [];
    var disp = o.disponibilidad || null, flagged = {};
    if (disp) {
      (disp.meses_incompletos || []).forEach(function (e) { flagged[key(e.y, e.m)] = true; });
      (disp.meses_parciales || []).forEach(function (e) { flagged[key(e.y, e.m)] = true; });
    }
    var groups = {}, maxKey = -1;
    rows.forEach(function (r) {
      if (!isNum(r.y) || !isNum(r.m)) return;
      var k = key(r.y, r.m);
      (groups[k] = groups[k] || []).push(r);
      if (k > maxKey) maxKey = k;
    });
    var last = parseLast(o.last || o.datosHasta);
    var lastKey = last ? key(last.y, last.m) : maxKey;
    if (lastKey < 0) return [];
    var out = [];
    for (var k = key(M.START.y, M.START.m); k <= lastKey; k++) {
      var y = Math.floor(k / 12), m = (k % 12) + 1, rs = groups[k] || [];
      var tramo = rs.length && rs[0].tramo ? String(rs[0].tramo).toUpperCase() : M.expectedTramo(y, m);
      var late = y >= M.LEAK_YEAR && !o.verdictOpen;
      var row = { y: y, m: m, tramo: tramo,
        v: sumNullable(rs, 'v') || 0, vm: sumNullable(rs, 'vm') || 0, xm: sumNullable(rs, 'xm') || 0, n20: sumNullable(rs, 'n20') || 0,
        t: late ? null : (sumNullable(rs, 't') || 0), a: late ? null : (sumNullable(rs, 'a') || 0), s: late ? null : (sumNullable(rs, 's') || 0),
        inc: (flagged[k] || rs.some(function (r) { return r.inc === 1 || r.inc === true; })) ? 1 : 0,
        prov: (tramo === 'NP' || rs.some(function (r) { return r.prov === 1 || r.prov === true; })) ? 1 : 0 };
      out.push(row);
    }
    return out;
  }

  function aggregateDaily(rows) {
    var by = {};
    (rows || []).forEach(function (r) {
      if (!r || typeof r.d !== 'string') return;
      var e = by[r.d] || (by[r.d] = { d: r.d, v: 0, vm: 0, prov: 0 });
      e.v += isNum(r.v) ? r.v : 0; e.vm += isNum(r.vm) ? r.vm : (isNum(r.v) ? r.v : 0);
      if (r.prov === 1 || r.prov === true) e.prov = 1;
    });
    return Object.keys(by).sort().map(function (d) { return by[d]; });
  }

  /**
   * snapshot: store.get() of estado.js. parts: { intervals, disponibilidad, dailyRows, config (CONFIG of datos-config.js, optional) }.
   * Returns the input of FireCalendar.render (without callbacks).
   */
  function buildInput(snapshot, parts) {
    parts = parts || {};
    var man = snapshot.manifest || {}, pais = (man.paises || {})[snapshot.pais] || {};
    var preset = (pais.aoiPredef || []).filter(function (a) { return a.id === snapshot.presetId; })[0];
    var nCells = snapshot.aoi && snapshot.aoi.covered ? snapshot.aoi.covered.length : 0;
    var last = pais.datosHasta || man.datosHasta;
    var rg = snapshot.range ? { from: snapshot.range.from, to: snapshot.range.to } : null;
    var verdictOpen = man.verdict !== null && man.verdict !== undefined;
    var cfg = FR ? FR.settings(parts.config) : null;                         // thresholds of the rule M1 (null = rule off)
    var expected = FR ? FR.expectedModis(snapshot.data && snapshot.data.rows, { disponibilidad: parts.disponibilidad, window: cfg.window }) : null;
    var few = FR ? FR.tooFew(expected, cfg.minModis) : { T: null, TA: null, any: false };
    return {
      aoi: { id: snapshot.presetId || 'custom', name: preset ? preset.nombre : 'Selected area (' + nCells + ' cells of 0.1°)', country: snapshot.pais,
             intervalLevel: 'aoi', nCells: nCells, expectedModis: expected ? { T: expected.T, TA: expected.TA } : null,
             tooFewModis: few.any, tooFewBy: { T: few.T, TA: few.TA } },
      reliability: { minAoiCells: cfg ? cfg.minAoiCells : null },
      monthly: aggregateMonthly(snapshot.data && snapshot.data.rows, { last: last, disponibilidad: parts.disponibilidad, verdictOpen: verdictOpen }),
      daily: aggregateDaily(parts.dailyRows),
      intervals: parts.intervals || null,
      manifest: { verdict: man.verdict === undefined ? null : man.verdict, synthetic: !!(man.synthetic || pais.synthetic), banner: man.banner || null,
                  exp: man.version || null, generated: man.generadoUtc || null, si_assisted: true },
      synthetic: !!(man.synthetic || pais.synthetic),
      options: { vegetationOnly: snapshot.scope !== 'all', range: rg }
    };
  }

  return { aggregateMonthly: aggregateMonthly, aggregateDaily: aggregateDaily, buildInput: buildInput };
});
