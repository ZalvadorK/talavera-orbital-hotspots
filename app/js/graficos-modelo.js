/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * graficos-modelo.js - pure logic of the daily views (extras of ADR-0010), no DOM:
 *   seasonToDate(model)  D2: cumulative detections since the start of the fire year vs the p10-p90 envelope and
 *                        median of the base (B2: VIIRS 2012-2025, evaluated year excluded), the current month compared
 *                        at the same day; plus the "unusual season" mark (cumulative above the p90 of the same day).
 *   dailyPattern(model)  K3: typical daily activity (mean of base years, 31-day circular moving average) and the
 *                        FWHM dates of the core season (days where the smoothed curve is >= 50 % of its peak).
 * Daily data are VIIRS only (2012 onward). Days missing from the file count as 0 inside valid base months.
 * Works in the browser (window.FireChartsModel) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var req = (typeof module === 'object' && typeof require === 'function');
  var FM = req ? require('./marca.js') : root.FireMark;
  var M = req ? require('./calendario-modelo.js') : root.FireCalendarModel;
  var api = factory(FM, M);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireChartsModel = api;
})(typeof window !== 'undefined' ? window : globalThis, function (FM, M) {
  'use strict';

  var MON3 = M.MON3;
  var LEAP = 2000;                                    // reference leap year for the 366 slots

  function slotsFrom(startMonth) {
    var out = [], idx = {};
    for (var i = 0; i < 12; i++) {
      var m = ((startMonth - 1 + i) % 12) + 1, n = M.dim(LEAP, m);
      for (var d = 1; d <= n; d++) { idx[m * 100 + d] = out.length; out.push({ m: m, d: d }); }
    }
    return { slots: out, idx: idx };
  }
  function slotLabel(sl) { return sl.d + ' ' + MON3[sl.m - 1]; }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  /** Fire-year start year of the date (y,m) given the start month. */
  function fireYearOf(y, m, startMonth) { return startMonth === 1 ? y : (m >= startMonth ? y : y - 1); }
  function fireYearLabel(fy, startMonth) { return startMonth === 1 ? String(fy) : fy + '–' + pad2((fy + 1) % 100); }

  function dateFor(fy, sl, startMonth) {
    var y = (startMonth === 1) ? fy : (sl.m >= startMonth ? fy : fy + 1);
    return { y: y, m: sl.m, d: sl.d, valid: sl.d <= M.dim(y, sl.m) };
  }

  /** Is every month of the fire year part of the B2 base (standard VIIRS, no outage, no partial/NRT)? */
  function eligibleBaseYear(model, fy, startMonth) {
    for (var i = 0; i < 12; i++) {
      var m = ((startMonth - 1 + i) % 12) + 1, y = (startMonth === 1) ? fy : (m >= startMonth ? fy : fy + 1);
      var ok = model.b2ByMonth[m - 1].some(function (b) { return b.y === y; });
      if (!ok) return false;
    }
    return true;
  }

  function dayValue(model, y, m, d) {
    var e = model.daily.map[y + '-' + pad2(m) + '-' + pad2(d)];
    return e ? e.v : 0;
  }
  function dayProv(model, y, m, d) {
    var e = model.daily.map[y + '-' + pad2(m) + '-' + pad2(d)];
    return !!(e && e.prov);
  }

  /** Cumulative curve of one fire year over the 366 slots, up to and including upTo (slot index); null after. */
  function cumCurve(model, fy, startMonth, S, upTo) {
    var out = new Array(S.slots.length), acc = 0;
    for (var i = 0; i < S.slots.length; i++) {
      if (i > upTo) { out[i] = null; continue; }
      var dt = dateFor(fy, S.slots[i], startMonth);
      if (dt.valid) acc += dayValue(model, dt.y, dt.m, dt.d);
      out[i] = acc;
    }
    return out;
  }

  function listFireYears(model) {
    if (!model || model.empty || !model.season || !model.daily.lastDate) return [];
    var sm = model.season.fireStartMonth, seen = {}, out = [];
    Object.keys(model.daily.map).forEach(function (k) {
      var y = +k.slice(0, 4), m = +k.slice(5, 7), fy = fireYearOf(y, m, sm);
      if (!seen[fy]) { seen[fy] = true; out.push(fy); }
    });
    out.sort(function (a, b) { return a - b; });
    return out.map(function (fy) { return { fy: fy, label: fireYearLabel(fy, sm) }; });
  }

  // ------------------------------------------------------------------ D2 + unusual season
  function seasonToDate(model) {
    var res = { available: false, reason: null };
    if (!model || model.empty) { res.reason = 'no-model'; return res; }
    if (!model.season) { res.reason = 'no-base'; return res; }
    if (!model.daily.lastDate || model.daily.n === 0) { res.reason = 'no-daily'; return res; }
    var sm = model.season.fireStartMonth, S = slotsFrom(sm);
    var ly = +model.daily.lastDate.slice(0, 4), lm = +model.daily.lastDate.slice(5, 7), ld = +model.daily.lastDate.slice(8, 10);
    var evalFY = (typeof model.opts.evalYear === 'number') ? model.opts.evalYear : fireYearOf(ly, lm, sm);
    var lastSlot = S.slots.length - 1, current = false;
    if (fireYearOf(ly, lm, sm) === evalFY) { lastSlot = S.idx[lm * 100 + ld]; current = true; }
    var baseYears = [];
    var years = {};
    Object.keys(model.daily.map).forEach(function (k) { years[fireYearOf(+k.slice(0, 4), +k.slice(5, 7), sm)] = true; });
    Object.keys(years).map(Number).sort(function (a, b) { return a - b; }).forEach(function (fy) {
      if (fy !== evalFY && eligibleBaseYear(model, fy, sm)) baseYears.push(fy);
    });
    if (!baseYears.length) { res.reason = 'no-base-years'; return res; }
    var curves = baseYears.map(function (fy) { return cumCurve(model, fy, sm, S, S.slots.length - 1); });
    var n = S.slots.length, p10 = new Array(n), med = new Array(n), p90 = new Array(n);
    for (var i = 0; i < n; i++) {
      var vals = curves.map(function (c) { return c[i]; });
      p10[i] = FM.quantile6(vals, 10); med[i] = FM.median(vals); p90[i] = FM.quantile6(vals, 90);
    }
    var cum = cumCurve(model, evalFY, sm, S, lastSlot);
    var prov = new Array(n);
    for (i = 0; i <= lastSlot; i++) { var dt = dateFor(evalFY, S.slots[i], sm); prov[i] = dt.valid && dayProv(model, dt.y, dt.m, dt.d); }
    var valueNow = cum[lastSlot], baseAtSlot = curves.map(function (c) { return c[lastSlot]; });
    var ev = FM.seasonMark(valueNow, baseAtSlot);
    var unusual = { state: ev.state === 'typical' ? 'not-unusual' : ev.state, p90: ev.p90, median: ev.median, n: ev.n, small: ev.small,
                    ratio: FM.ratioOf(valueNow, ev.median), value: valueNow };
    var endDt = dateFor(evalFY, S.slots[lastSlot], sm);
    var asOfText = S.slots[lastSlot].d + ' ' + MON3[S.slots[lastSlot].m - 1];
    return { available: true, startMonth: sm, slots: S.slots, idx: S.idx, evalFY: evalFY, evalLabel: fireYearLabel(evalFY, sm), current: current,
             lastSlot: lastSlot, asOf: endDt.y + '-' + pad2(endDt.m) + '-' + pad2(endDt.d), asOfText: asOfText,
             baseYears: baseYears, baseLabels: baseYears.map(function (fy) { return fireYearLabel(fy, sm); }),
             baseLabel: baseYears.length ? fireYearLabel(baseYears[0], sm) + ' to ' + fireYearLabel(baseYears[baseYears.length - 1], sm) : '',
             p10: p10, median: med, p90: p90, cum: cum, prov: prov, value: valueNow, unusual: unusual,
             ratioText: FM.ratioText(valueNow, ev.median, model.base.b2Label) + ' (same day)',
             unusualText: (unusual.state === 'unusual' ? 'Unusually active season so far: above the 90th percentile of the same day in ' + model.base.b2Label + ' (this year excluded).'
               : (unusual.state === 'insufficient' ? 'Season mark not available: there are no base years.' : 'Not unusually active so far.')) +
               (unusual.small ? ' Early in the season the totals are small (base median below 5): read this mark with care.' : '') };
  }

  // ------------------------------------------------------------------ K3 FWHM
  function dailyPattern(model) {
    var res = { available: false };
    if (!model || model.empty || !model.season) { res.reason = 'no-base'; return res; }
    if (!model.daily.lastDate || model.daily.n === 0) { res.reason = 'no-daily'; return res; }
    var sm = model.season.fireStartMonth, S = slotsFrom(sm), n = S.slots.length;
    var sum = new Array(n), cnt = new Array(n), i;
    for (i = 0; i < n; i++) { sum[i] = 0; cnt[i] = 0; }
    for (var mi = 1; mi <= 12; mi++) {
      model.b2ByMonth[mi - 1].forEach(function (b) {
        var dm = M.dim(b.y, mi);
        for (var d = 1; d <= dm; d++) {
          var k = S.idx[mi * 100 + d]; sum[k] += dayValue(model, b.y, mi, d); cnt[k] += 1;
        }
      });
    }
    var mean = new Array(n);
    var anyYears = 0; for (i = 0; i < n; i++) { mean[i] = cnt[i] ? sum[i] / cnt[i] : 0; if (cnt[i] > anyYears) anyYears = cnt[i]; }
    if (!anyYears) { res.reason = 'no-base-years'; return res; }
    var smooth = new Array(n), half = 15;                 // 31-day centred circular moving average
    for (i = 0; i < n; i++) { var s = 0; for (var j = -half; j <= half; j++) s += mean[(i + j + n) % n]; smooth[i] = s / 31; }
    var peak = 0; for (i = 1; i < n; i++) if (smooth[i] > smooth[peak]) peak = i;
    if (!(smooth[peak] > 0)) { res.reason = 'flat'; return res; }
    var thr = smooth[peak] * 0.5, a = peak, b = peak, guard = 0;
    while (smooth[(a - 1 + n) % n] >= thr && guard++ < n) a = (a - 1 + n) % n;
    guard = 0;
    while (smooth[(b + 1) % n] >= thr && guard++ < n) b = (b + 1) % n;
    var wraps = (guard >= n) || ((b - a + n) % n + 1 >= n);
    if (wraps) { res.reason = 'all-year'; res.available = false; return res; }
    var len = (b - a + n) % n + 1;
    return { available: true, startMonth: sm, slots: S.slots, mean: mean, smooth: smooth, peak: peak, start: a, end: b, length: len, threshold: thr,
             nYears: anyYears, baseLabel: model.base.b2Label,
             startText: slotLabel(S.slots[a]), peakText: slotLabel(S.slots[peak]), endText: slotLabel(S.slots[b]),
             text: 'The season typically runs ' + slotLabel(S.slots[a]) + ' → ' + slotLabel(S.slots[b]) + ' (peak ' + slotLabel(S.slots[peak]) + ')' };
  }

  return { slotsFrom: slotsFrom, slotLabel: slotLabel, seasonToDate: seasonToDate, dailyPattern: dailyPattern, listFireYears: listFireYears,
           fireYearOf: fireYearOf, fireYearLabel: fireYearLabel, eligibleBaseYear: eligibleBaseYear, cumCurve: cumCurve };
});
