/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * intervalos.js - 80 % interval of the harmonised value (I2, ADR-0006; single interval model I-03).
 *
 * The interval comes from empirical leave-one-year-out residual quantiles, grouped by class of the predicted value
 * S-hat x era (T = Terra only, TA = Terra+Aqua) x level (1deg | pais | aoi) x country. A drawn AOI uses level "aoi"
 * (an approximation that has NOT been validated, I-03; the UI says so).
 *
 * Formats accepted (see app/tests/calendario-INTERFAZ.md):
 *   1. REAL  (app/data/<country>/intervalos.json copied from lane A, contract section 8):
 *        relojes.{TA|T|A}.{1deg|pais|aoi} = { cortes_log1p_S_hat: [...], clases: [{q10, q90, ...}, ...] }
 *        class b = number of cuts <= log1p(S-hat)  (numpy searchsorted side="right")
 *        absolute interval = [max(0, expm1(log1p(S-hat) + q10)), expm1(log1p(S-hat) + q90)]
 *        S-hat <= 0  ->  [0, Infinity)   (MODIS saw nothing: the method cannot bound the truth from above)
 *      Same arithmetic as nucleo.factores.intervalo() (parity test: app/tests/paridad-intervalos.json).
 *   2. SYNTHETIC placeholder: ic80_multiplicativo_placeholder.{T|TA}.{1deg|pais|aoi} = [lo, hi] (multiplicative; NOT real
 *      intervals; norm.placeholder = true so the UI labels it SYNTHETIC).
 *   3. Generic classes (used by our own tests): classes[{lt, T:{q10,q90}, TA:{...}}], residual "ratio" | "diff".
 *
 * Works in the browser (window.FireIntervals) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireIntervals = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var LEVELS = ['aoi', 'pais', '1deg'];

  function num(x) { return (typeof x === 'number' && isFinite(x)) ? x : null; }
  function firstNum(o, keys) {
    for (var i = 0; i < keys.length; i++) { var v = num(o && o[keys[i]]); if (v !== null) return v; }
    return null;
  }
  function bounds(o) {
    if (!o || typeof o !== 'object') return null;
    var a = firstNum(o, ['q10', 'p10', 'lo', 'low']);
    var b = firstNum(o, ['q90', 'p90', 'hi', 'high']);
    return (a === null || b === null) ? null : { q10: a, q90: b };
  }
  function empty(reason) { return { ok: false, reason: reason, kind: null, placeholder: false, level: 0.8, mode: 'ratio', byEra: {}, tab: {}, eras: [] }; }

  /** Normalise whatever the exporter wrote. Returns { ok, kind, placeholder, level, eras, ... }. */
  function normalize(raw) {
    if (!raw || typeof raw !== 'object') return empty('missing');
    var out = empty('no-classes');
    out.level = firstNum(raw, ['nivel_nominal', 'level', 'nivel']) || 0.8;
    out.note = raw.note || raw.nota || null;

    // 1. REAL: relojes.<era>.<nivel>
    if (raw.relojes && typeof raw.relojes === 'object') {
      out.kind = 'loyo-log1p';
      Object.keys(raw.relojes).forEach(function (era) {
        var lv = raw.relojes[era];
        Object.keys(lv || {}).forEach(function (nv) {
          var t = lv[nv];
          if (!t || !Array.isArray(t.clases) || !t.clases.length) return;
          var cuts = (t.cortes_log1p_S_hat || []).map(Number);
          var cls = t.clases.map(function (c) { return { q10: Number(c.q10), q90: Number(c.q90) }; });
          if (cls.some(function (c) { return !isFinite(c.q10) || !isFinite(c.q90); })) return;
          (out.tab[era] = out.tab[era] || {})[nv] = { cuts: cuts, cls: cls };
        });
      });
      out.eras = Object.keys(out.tab);
      out.ok = out.eras.length > 0; out.reason = out.ok ? null : 'no-tables';
      return out;
    }
    // 2. SYNTHETIC placeholder (multiplicative)
    var ph = raw.ic80_multiplicativo_placeholder;
    if (ph && typeof ph === 'object') {
      out.kind = 'placeholder'; out.placeholder = true;
      Object.keys(ph).forEach(function (era) {
        Object.keys(ph[era] || {}).forEach(function (nv) {
          var p = ph[era][nv];
          if (Array.isArray(p) && num(p[0]) !== null && num(p[1]) !== null) (out.tab[era] = out.tab[era] || {})[nv] = { mult: [p[0], p[1]] };
        });
      });
      out.eras = Object.keys(out.tab);
      out.ok = out.eras.length > 0; out.reason = out.ok ? null : 'no-tables';
      return out;
    }
    // 3. generic classes
    var mode = (raw.residual || raw.mode || raw.tipo || 'ratio').toString().toLowerCase();
    out.mode = /diff|dif|resta|add/.test(mode) ? 'diff' : 'ratio';
    out.kind = 'generic';
    var classes = raw.classes || raw.clases || raw.bins;
    if (Array.isArray(classes)) {
      classes.forEach(function (c) {
        var lt = (c.lt === null || c.hasta === null || c.max === null || c.upper === null) ? Infinity : firstNum(c, ['lt', 'hasta', 'max', 'upper']);
        if (lt === null) lt = Infinity;
        ['T', 'TA'].forEach(function (era) {
          var b = bounds(c[era] || (c.tramos && c.tramos[era]));
          if (b) { (out.byEra[era] = out.byEra[era] || []).push({ lt: lt, q10: b.q10, q90: b.q90 }); }
        });
      });
    }
    out.eras = Object.keys(out.byEra);
    out.eras.forEach(function (e) { out.byEra[e].sort(function (a, b) { return a.lt - b.lt; }); });
    out.ok = out.eras.length > 0; out.reason = out.ok ? null : 'no-classes';
    if (!out.ok && (raw.placeholder || raw.synthetic)) { out.placeholder = true; out.reason = 'placeholder-without-numbers'; }
    return out;
  }

  function tableFor(norm, era, level) {
    var t = norm.tab[era]; if (!t) return null;
    var order = [level].concat(LEVELS.filter(function (l) { return l !== level; }));
    for (var i = 0; i < order.length; i++) if (order[i] && t[order[i]]) return { t: t[order[i]], level: order[i] };
    return null;
  }

  /**
   * Absolute interval for one harmonised value v (VIIRS-equivalent). era: 'T' | 'TA' ('A' accepted for real tables).
   * level: '1deg' | 'pais' | 'aoi' (default 'aoi'; falls back to the next available level).
   * Returns { lo, hi, cls, level, mode, zero } or null when no interval is available.
   */
  function intervalFor(norm, era, v, level) {
    if (!norm || !norm.ok || typeof v !== 'number' || !isFinite(v)) return null;
    level = level || 'aoi';
    if (norm.kind === 'generic') {
      if (!norm.byEra[era]) return null;
      var cl = norm.byEra[era], k = cl.length - 1;
      for (var i = 0; i < cl.length; i++) { if (v < cl[i].lt) { k = i; break; } }
      var c = cl[k], lo, hi;
      if (norm.mode === 'diff') { lo = Math.max(0, v + c.q10); hi = v + c.q90; }
      else { lo = v * c.q10; hi = v * c.q90; }
      if (lo > v) lo = v;             // the 80 % range of an estimate always contains the estimate
      if (hi < v) hi = v;
      var zg = (v === 0 && norm.mode === 'ratio');
      if (zg) hi = Infinity;
      return { lo: lo, hi: hi, cls: k, level: null, mode: norm.mode, zero: zg };
    }
    var tf = tableFor(norm, era, level);
    if (!tf) return null;
    if (!(v > 0)) return { lo: 0, hi: Infinity, cls: null, level: tf.level, mode: norm.kind, zero: true };   // S-hat <= 0 -> (0, inf)
    if (norm.kind === 'placeholder') return { lo: v * tf.t.mult[0], hi: v * tf.t.mult[1], cls: null, level: tf.level, mode: 'placeholder', zero: false };
    var lp = Math.log1p(v), b = 0;
    for (var j = 0; j < tf.t.cuts.length; j++) { if (tf.t.cuts[j] <= lp) b++; else break; }   // searchsorted side="right" (cuts ascending)
    var q = tf.t.cls[Math.min(b, tf.t.cls.length - 1)];
    return { lo: Math.max(0, Math.expm1(lp + q.q10)), hi: Math.expm1(lp + q.q90), cls: b, level: tf.level, mode: norm.kind, zero: false };
  }

  return { normalize: normalize, intervalFor: intervalFor, LEVELS: LEVELS };
});
