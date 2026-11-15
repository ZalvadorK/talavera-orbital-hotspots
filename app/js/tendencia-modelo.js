/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * tendencia-modelo.js - pure logic of the DESCRIPTIVE annual trend view (ADR-0012, option 2). No DOM, testable in Node.
 *
 *   buildTrend(input) -> model: yearly totals of one area, "harmonized (VIIRS-equivalent)" next to "raw, as detected by each
 *                        sensor" (MODIS raw until Dec 2011, VIIRS raw from Jan 2012), the status of every year
 *                        (complete | incomplete | provisional), and the Sen slope with its confidence interval of the
 *                        COMPLETE years only. Nothing here is a significance test: the view says "descriptive trend, not a
 *                        tested result".
 *   senTrend(t, x, opts) -> Sen slope (median of pairwise slopes) + interval of Gilbert (1987), optionally widened with the
 *                        Hamed & Rao (1998) correction for serial correlation. Same algorithm and index rule as
 *                        toolkit/sakit/tendencias.py (sen + mann_kendall); parity is tested against it.
 *
 * Input (all months already summed over the cells of the area, one row per month, zero-filled like calendario-agregar.js):
 *   monthly [{y, m, tramo, v, vm, t, a, s, n20, xm, inc, prov}]   contract of app/data/CONTRATO-DATOS.md section 5
 *   range   {from:{y,m}, to:{y,m}} | null     months the user chose (years only partly inside are "incomplete")
 *   vegetationOnly  bool                      true: v (outside the static mask); false: vm (all thermal anomalies)
 *   last    'YYYY-MM-DD' | {y, m}             last day with data (month to date is flagged)
 *   ranges  {<year>: {lo, hi}} | null         80 % range of the harmonized total of complete estimated years (optional)
 *   verdictOpen bool, synthetic bool, aoi {name, country}, manifest {...}, options {minYears, ci, autocorrelation, show, label}
 *
 * ANTI-LEAK (ADR-0005): the raw MODIS line uses t + a only for months before 2012 (tramo T / TA); Terra, Aqua and S-NPP raw
 * counts of 2019 onward are never read, whatever the input contains. VIIRS raw = the observed count v (weight 1).
 * Units: "hotspot detections, not fires". Works in the browser (window.FireTrendModel) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireTrendModel = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var MON3 = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var UNIT = 'hotspot detections, not fires';
  var START = { y: 2000, m: 12 };                    // Dec 2000 (Nov 2000 is out of the series, ADR-0002)
  var LEAK_YEAR = 2019;                               // Terra / Aqua / S-NPP raw counts from here on are withheld (ADR-0005)
  var DEFAULTS = { minYears: 8, ci: 0.95, autocorrelation: 'hamed_rao', show: 'both',
                   label: 'descriptive trend, not a tested result' };
  // two-sided normal quantiles for the supported confidence levels (no p-value is ever computed)
  var Z = { '0.8': 1.2815515655446004, '0.9': 1.6448536269514722, '0.95': 1.959963984540054, '0.99': 2.5758293035489004 };

  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function keyOf(y, m) { return y * 12 + (m - 1); }
  function yOf(k) { return Math.floor(k / 12); }
  function mOf(k) { return (k % 12) + 1; }
  function dim(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); }
  function fmtInt(x) { return Math.round(x).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  function minus(s) { return s.replace('-', '−'); }

  // ---------------------------------------------------------------------------------------------- statistics
  function median(arr) {
    var a = arr.slice().sort(function (p, q) { return p - q; }), n = a.length;
    if (!n) return NaN;
    return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2;
  }

  /** Ranks (1-based) with the average of tied ranks (scipy.stats.rankdata default). */
  function rankAverage(x) {
    var idx = x.map(function (v, i) { return i; }).sort(function (p, q) { return x[p] - x[q]; });
    var r = new Array(x.length), i = 0;
    while (i < idx.length) {
      var j = i;
      while (j + 1 < idx.length && x[idx[j + 1]] === x[idx[i]]) j++;
      var avg = (i + j) / 2 + 1;
      for (var k = i; k <= j; k++) r[idx[k]] = avg;
      i = j + 1;
    }
    return r;
  }

  /** Variance of the Kendall S statistic with the tie correction (sakit _s_y_var). */
  function kendallVar(x) {
    var n = x.length, groups = {}, tie = 0, key;
    x.forEach(function (v) { groups[v] = (groups[v] || 0) + 1; });
    for (key in groups) { var t = groups[key]; if (t > 1) tie += t * (t - 1) * (2 * t + 5); }
    return (n * (n - 1) * (2 * n + 5) - tie) / 18;
  }

  /** Sen slope + Gilbert interval (sakit.tendencias.sen). varS overrides the Kendall variance (Hamed-Rao). */
  function senEstimate(t, x, z, varS) {
    var n = x.length, slopes = [], i, j;
    for (i = 0; i < n - 1; i++) for (j = i + 1; j < n; j++) { var dt = t[j] - t[i]; if (dt !== 0) slopes.push((x[j] - x[i]) / dt); }
    var b = median(slopes);
    var v = (varS === undefined || varS === null) ? kendallVar(x) : varS;
    var c = z * Math.sqrt(v), N = slopes.length;
    var ps = slopes.slice().sort(function (p, q) { return p - q; });
    var m1 = Math.min(Math.max(Math.floor((N - c) / 2) - 1, 0), N - 1);
    var m2 = Math.min(Math.max(Math.ceil((N + c) / 2), 0), N - 1);
    var resid = x.map(function (xi, k) { return xi - b * t[k]; });
    return { slope: b, lo: ps[m1], hi: ps[m2], intercept: median(resid), pairs: N };
  }

  /**
   * Sen trend of the series x(t). opts: {ci: 0.8|0.9|0.95|0.99, autocorrelation: 'hamed_rao'|'none'}.
   * Returns {ok:true, n, slope, lo, hi, intercept, ci, method, ratio, mean} or {ok:false, reason, n}.
   * Hamed-Rao (as in sakit): only from n >= 10; ratio n/n* is bounded below by 1 (it can only widen the interval).
   */
  function senTrend(t, x, opts) {
    opts = opts || {};
    var ci = opts.ci === undefined ? DEFAULTS.ci : opts.ci;
    var z = Z[String(ci)];
    if (!z) throw new Error('Unsupported confidence level ' + ci + ' (use 0.8, 0.9, 0.95 or 0.99).');
    var ac = opts.autocorrelation === undefined ? DEFAULTS.autocorrelation : opts.autocorrelation;
    var tt = [], xx = [];
    for (var i = 0; i < x.length; i++) if (isNum(x[i]) && isNum(t[i])) { tt.push(t[i]); xx.push(x[i]); }
    var n = xx.length;
    if (n < 2) return { ok: false, reason: 'few-years', n: n };
    var est = senEstimate(tt, xx, z), ratio = 1, method = 'Sen slope, Gilbert (1987) interval';
    if (ac === 'hamed_rao' && n >= 10) {
      var detr = xx.map(function (xi, k) { return xi - est.slope * tt[k]; });
      var r = rankAverage(detr), mean = r.reduce(function (a, b) { return a + b; }, 0) / n;
      r = r.map(function (v) { return v - mean; });
      var denom = r.reduce(function (a, b) { return a + b * b; }, 0), lim = z / Math.sqrt(n), sum = 0;
      if (denom > 0) {
        for (var k = 1; k <= n - 2; k++) {
          var s = 0;
          for (var q = 0; q < n - k; q++) s += r[q] * r[q + k];
          var acf = s / denom;
          if (Math.abs(acf) > lim) sum += (n - k) * (n - k - 1) * (n - k - 2) * acf;
        }
      }
      var bruto = 1 + 2 / (n * (n - 1) * (n - 2)) * sum;
      ratio = Math.max(1, bruto);
      if (ratio !== 1) est = senEstimate(tt, xx, z, kendallVar(xx) * ratio);
      method += ', Hamed-Rao (1998) serial-correlation correction';
    }
    var tot = xx.reduce(function (a, b) { return a + b; }, 0);
    return { ok: true, n: n, slope: est.slope, lo: est.lo, hi: est.hi, intercept: est.intercept, ci: ci, method: method,
             ratio: ratio, mean: tot / n, pairs: est.pairs };
  }

  // ---------------------------------------------------------------------------------------------- months and years
  /** Tramo implied by the date (ADR-0002); used only when the row does not say (same rule as calendario-modelo.js). */
  function expectedTramo(y, m) {
    var k = keyOf(y, m);
    if (k < keyOf(2002, 7)) return 'T';
    if (k < keyOf(2012, 1)) return 'TA';
    if (k < keyOf(2018, 4)) return 'S';
    if (k < keyOf(2026, 8)) return 'N';
    return 'NP';
  }
  function tramoOf(r) {
    var t = r && r.tramo ? String(r.tramo).toUpperCase() : null;
    return (t === 'T' || t === 'TA' || t === 'S' || t === 'N' || t === 'NP') ? t : expectedTramo(r.y, r.m);
  }

  function monthKeyOf(x) {
    if (!x) return null;
    if (typeof x === 'string') { var m = /^(\d{4})-(\d{2})/.exec(x); return m ? keyOf(+m[1], +m[2]) : null; }
    return (isNum(x.y) && isNum(x.m)) ? keyOf(x.y, x.m) : null;
  }

  /** "Jun", "Jun–Jul", "Jan, Mar–May" from a list of month numbers. */
  function monthsText(ms) {
    var a = ms.slice().sort(function (p, q) { return p - q; }), out = [], i = 0;
    while (i < a.length) {
      var j = i;
      while (j + 1 < a.length && a[j + 1] === a[j] + 1) j++;
      out.push(j > i ? MON3[a[i] - 1] + '–' + MON3[a[j] - 1] : MON3[a[i] - 1]);
      i = j + 1;
    }
    return out.join(', ');
  }

  /** Values of one month row: harmonized value, raw value and the sensor that produced the raw one. */
  function monthValues(r, veg, y) {
    var tramo = tramoOf(r), harm = veg ? r.v : (isNum(r.vm) ? r.vm : r.v);
    var out = { tramo: tramo, harmonized: isNum(harm) ? harm : null, raw: null, sensor: null, estimated: false };
    if (tramo === 'T' || tramo === 'TA') {
      out.sensor = 'MODIS'; out.estimated = true;
      // ANTI-LEAK: MODIS raw counts exist in the data only up to 2011 (calibration support until 2018); never 2019+
      if (y < LEAK_YEAR && isNum(r.t) && isNum(r.a)) {
        var masked = veg ? 0 : (isNum(r.xm) ? r.xm : null);
        out.raw = masked === null ? null : r.t + r.a + masked;
      }
    } else {
      out.sensor = 'VIIRS';
      out.raw = out.harmonized;                        // VIIRS counts are observed with weight 1: harmonized = raw
    }
    return out;
  }

  function normOptions(o) {
    o = o || {};
    return {
      minYears: isNum(o.minYears) ? o.minYears : DEFAULTS.minYears,
      ci: isNum(o.ci) ? o.ci : DEFAULTS.ci,
      autocorrelation: o.autocorrelation === 'none' ? 'none' : DEFAULTS.autocorrelation,
      show: (o.show === 'harmonized' || o.show === 'raw') ? o.show : DEFAULTS.show,
      label: o.label ? String(o.label) : DEFAULTS.label
    };
  }

  function lastDateOf(last) {
    if (!last) return null;
    if (typeof last === 'string') {
      var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(last);
      return m ? { y: +m[1], m: +m[2], d: m[3] ? +m[3] : null } : null;
    }
    return (isNum(last.y) && isNum(last.m)) ? { y: last.y, m: last.m, d: isNum(last.d) ? last.d : null } : null;
  }

  function pctText(ci) { return Math.round(ci * 100) + ' %'; }
  function signed(x) {
    var a = Math.abs(x), s = a >= 100 ? fmtInt(a) : (a >= 10 ? a.toFixed(1) : a.toFixed(2));
    if (/^0(\.0+)?$/.test(s)) return '0';
    return (x < 0 ? '−' : '+') + s;
  }

  function yearRangeText(ys) {
    if (!ys.length) return '';
    return ys[0] === ys[ys.length - 1] ? String(ys[0]) : ys[0] + '–' + ys[ys.length - 1];
  }

  function statRow(key, label, years, values, o, extra) {
    var res = senTrend(years, values, { ci: o.ci, autocorrelation: o.autocorrelation });
    var row = { key: key, label: label, years: years.slice(), n: years.length, scope: yearRangeText(years), minYears: o.minYears };
    for (var k in (extra || {})) row[k] = extra[k];
    if (years.length < o.minYears || !res.ok) {
      row.ok = false;
      row.reason = 'few-years';
      row.text = 'not computed: ' + years.length + ' complete ' + (years.length === 1 ? 'year' : 'years') + ' in the selected dates, at least ' + o.minYears + ' needed';
      return row;
    }
    row.ok = true; row.slope = res.slope; row.lo = res.lo; row.hi = res.hi; row.intercept = res.intercept; row.mean = res.mean;
    row.ci = res.ci; row.method = res.method; row.ratio = res.ratio; row.pairs = res.pairs;
    row.text = signed(res.slope) + ' detections per year (' + pctText(res.ci) + ' CI ' + signed(res.lo) + ' to ' + signed(res.hi) +
      '); mean ' + fmtInt(res.mean) + ' per year';
    return row;
  }

  // ---------------------------------------------------------------------------------------------- the model
  function buildTrend(input) {
    input = input || {};
    var o = normOptions(input.options), veg = input.vegetationOnly !== false;
    var rows = {}, maxKey = -1;
    (input.monthly || []).forEach(function (r) {
      if (!r || !isNum(r.y) || !isNum(r.m)) return;
      var k = keyOf(r.y, r.m);
      rows[k] = r;
      if (k > maxKey) maxKey = k;
    });
    var startKey = keyOf(START.y, START.m), ld = lastDateOf(input.last);
    var lastKey = ld ? keyOf(ld.y, ld.m) : maxKey;
    var base = { empty: true, opts: o, unit: UNIT, synthetic: !!input.synthetic, aoi: input.aoi || {}, manifest: input.manifest || {},
                 verdictOpen: !!input.verdictOpen, vegetationOnly: veg, notices: [] };
    if (lastKey < startKey) { base.reason = 'no-data'; return base; }
    var rg = input.range || null, rFrom = rg ? monthKeyOf(rg.from) : null, rTo = rg ? monthKeyOf(rg.to) : null;
    var from = rFrom === null ? startKey : Math.max(startKey, rFrom), to = rTo === null ? lastKey : Math.min(lastKey, rTo);
    if (from > to) { base.reason = 'no-months'; return base; }
    var monthToDate = !!(ld && ld.d && ld.d < dim(ld.y, ld.m));

    var years = [], y;
    for (y = yOf(from); y <= yOf(to); y++) {
      var used = 0, outage = [], partial = [], prov = [], missing = [], outside = 0, before = 0, after = 0, estimated = false;
      var harm = 0, raw = 0, rawOk = true, harmOk = true, tramos = {}, sensors = {};
      for (var m = 1; m <= 12; m++) {
        var k = keyOf(y, m);
        if (k < startKey) { before++; continue; }
        if (k > lastKey) { after++; continue; }
        if ((rFrom !== null && k < rFrom) || (rTo !== null && k > rTo)) { outside++; continue; }
        var r = rows[k];
        if (!r) { missing.push(m); continue; }
        var mv = monthValues(Object.assign({}, r, { y: y, m: m }), veg, y);
        used++;
        tramos[mv.tramo] = true; sensors[mv.sensor] = true;
        if (mv.estimated) estimated = true;
        if (mv.harmonized === null) harmOk = false; else harm += mv.harmonized;
        if (mv.raw === null) rawOk = false; else raw += mv.raw;
        if (r.inc === 1 || r.inc === true) {
          if (y === 2012 && m === 1 && mv.tramo === 'S') partial.push(m); else outage.push(m);
        }
        if (r.prov === 1 || r.prov === true || mv.tramo === 'NP') prov.push(m);
      }
      if (!used && !missing.length) continue;                               // nothing of this year in the shown period
      var reasons = [];
      if (before) reasons.push('the series starts in ' + MON3[START.m - 1] + ' ' + START.y);
      if (outage.length) reasons.push('satellite outage in ' + monthsText(outage));
      if (partial.length) reasons.push('partial month: S-NPP data start on 20 Jan 2012');
      if (missing.length) reasons.push('no data rows for ' + monthsText(missing));
      if (after) {
        var lastM = mOf(lastKey);
        reasons.push('year in progress: data to ' + (monthToDate && yOf(lastKey) === y ? ld.d + ' ' : '') + MON3[lastM - 1] + ' ' + yOf(lastKey));
      } else if (monthToDate && y === yOf(lastKey) && used && mOf(lastKey) === 12) {
        reasons.push('month to date (' + ld.d + ' ' + MON3[11] + ')');
      }
      if (outside) reasons.push('only ' + used + ' of 12 months are inside the selected dates');
      if (prov.length) reasons.push('provisional near-real-time data in ' + monthsText(prov));
      var status = prov.length ? 'provisional' : (reasons.length ? 'incomplete' : 'complete');
      var sensorList = Object.keys(sensors);
      var sensor = sensorList.length === 1 ? sensorList[0] : (sensorList.length ? 'mixed' : null);
      var rr = input.ranges && input.ranges[y];
      years.push({ y: y, status: status, reasons: reasons, months: used, estimated: estimated, tramos: Object.keys(tramos),
                   harmonized: harmOk && used ? harm : null, raw: rawOk && used && sensor !== 'mixed' ? raw : null, sensor: sensor,
                   range: (status === 'complete' && estimated && rr && isNum(rr.lo) && isNum(rr.hi)) ? { lo: rr.lo, hi: rr.hi } : null });
    }
    if (!years.length) { base.reason = 'no-years'; return base; }

    // ---- statistics: COMPLETE years only (incomplete and provisional years stay out of every slope) ----------------------------
    var complete = years.filter(function (a) { return a.status === 'complete'; });
    var hy = complete.filter(function (a) { return a.harmonized !== null; });
    var vy = hy.filter(function (a) { return !a.estimated && a.sensor === 'VIIRS'; });
    var ry = complete.filter(function (a) { return a.raw !== null; });
    var nEst = hy.filter(function (a) { return a.estimated; }).length;
    var stats = {
      harmonized: statRow('harmonized', 'Harmonized (VIIRS-equivalent)', hy.map(function (a) { return a.y; }), hy.map(function (a) { return a.harmonized; }), o,
        { nEstimated: nEst, nObserved: hy.length - nEst }),
      viirs: statRow('viirs', 'Harmonized, VIIRS era only (observed)', vy.map(function (a) { return a.y; }), vy.map(function (a) { return a.harmonized; }), o, {}),
      raw: statRow('raw', 'Raw, as detected by each sensor', ry.map(function (a) { return a.y; }), ry.map(function (a) { return a.raw; }), o,
        { sensors: Object.keys(ry.reduce(function (acc, a) { acc[a.sensor] = 1; return acc; }, {})) })
    };
    var anySensorChange = years.some(function (a) { return a.sensor === 'MODIS'; }) && years.some(function (a) { return a.sensor === 'VIIRS'; });
    var changeYear = null;                                      // first year observed by VIIRS after MODIS years (the step)
    if (anySensorChange) {
      var lastModis = Math.max.apply(null, years.filter(function (a) { return a.sensor === 'MODIS'; }).map(function (a) { return a.y; }));
      var nextV = years.filter(function (a) { return a.sensor === 'VIIRS' && a.y > lastModis; }).map(function (a) { return a.y; });
      changeYear = nextV.length ? Math.min.apply(null, nextV) : null;
    }
    var excluded = years.filter(function (a) { return a.status !== 'complete'; }).map(function (a) {
      return { y: a.y, status: a.status, reasons: a.reasons.slice() };
    });

    var notices = [];
    if (base.synthetic) notices.push({ id: 'synthetic', level: 'warn', text: 'SYNTHETIC demo data: generated for testing, not real detections.' });
    if (!base.verdictOpen) notices.push({ id: 'leak', level: 'info', text: 'Raw Terra, Aqua and S-NPP counts from 2019 onward are withheld until the pre-registered validation test has been run. This view never needs them: the raw line is MODIS until 2011 and VIIRS from 2012.' });
    if (!anySensorChange) notices.push({ id: 'no-step', level: 'info', text: 'The selected dates do not include the change from MODIS to VIIRS (Jan 2012): there is no sensor step to show.' });

    return {
      empty: false, opts: o, unit: UNIT, synthetic: base.synthetic, aoi: base.aoi, manifest: base.manifest, verdictOpen: base.verdictOpen,
      vegetationOnly: veg, years: years, firstYear: years[0].y, lastYear: years[years.length - 1].y, firstKey: from, lastKey: to,
      stats: stats, excluded: excluded, changeYear: changeYear, anySensorChange: anySensorChange, monthToDate: monthToDate,
      daily: null, notices: notices, label: o.label
    };
  }

  /** The Sen line of a statistics row evaluated at year yv (for drawing). Null when the row was not computed. */
  function lineAt(row, yv) { return row && row.ok ? row.intercept + row.slope * yv : null; }

  return { buildTrend: buildTrend, senTrend: senTrend, senEstimate: senEstimate, kendallVar: kendallVar, rankAverage: rankAverage, median: median,
           monthValues: monthValues, monthsText: monthsText, signed: signed, fmtInt: fmtInt, lineAt: lineAt, minus: minus, yearRangeText: yearRangeText,
           MON3: MON3, UNIT: UNIT, START: START, LEAK_YEAR: LEAK_YEAR, DEFAULTS: DEFAULTS, Z: Z };
});
