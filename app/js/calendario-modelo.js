/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * calendario-modelo.js - pure logic of the fire calendar (no DOM, testable in Node).
 *   buildModel(input) -> model used by calendario.js (render) and graficos.js (daily views)
 *
 * Implements ADR-0010 (6a, 6d K1, 6e base B2/B1, 6g axis G2, 6h provisional H2) and ADR-0006 (6c/6c-q via marca.js).
 * Anti-leak: Terra / Aqua / S-NPP raw counts from 2019 onward are never exposed unless manifest.verdict is not null.
 * Reliability (fiabilidad.js): each estimated month gets "not yet tested" | "reliable" | "indicative" from manifest.verdict, and the area
 * gets the rule M1 notice ("too few MODIS") from input.aoi.tooFewModis / tooFewBy.
 * Units: "VIIRS-equivalent hotspot detections" (hotspot detections, not individual fires).
 *
 * Works in the browser (window.FireCalendarModel) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var FM = (typeof module === 'object' && typeof require === 'function') ? require('./marca.js') : root.FireMark;
  var FI = (typeof module === 'object' && typeof require === 'function') ? require('./intervalos.js') : root.FireIntervals;
  var FR = (typeof module === 'object' && typeof require === 'function') ? require('./fiabilidad.js') : (root.FireReliability || null);
  var api = factory(FM, FI, FR);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireCalendarModel = api;
})(typeof window !== 'undefined' ? window : globalThis, function (FM, FI, FR) {
  'use strict';

  var MON3 = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var MONL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var UNIT = 'VIIRS-equivalent hotspot detections';
  var START = { y: 2000, m: 12 };                   // Dec 2000 (Nov 2000 is out, ADR-0002)
  var BASES = { B2: { start: 2012, end: 2025, label: '2012–2025' }, B1: { start: 2003, end: 2025, label: '2003–2025' } };
  var LEAK_YEAR = 2019;                              // Terra/Aqua/S-NPP raw counts from here on are withheld

  var TRAMO = {
    T: { estimated: true, sat: 'Terra', name: 'estimated · Terra only' },
    TA: { estimated: true, sat: 'Terra + Aqua', name: 'estimated · Terra+Aqua' },
    S: { estimated: false, sat: 'S-NPP', name: 'observed · S-NPP' },
    N: { estimated: false, sat: 'NOAA-20', name: 'observed · NOAA-20' },
    NP: { estimated: false, sat: 'NOAA-20 (near-real-time)', name: 'provisional · NOAA-20 NRT' }
  };

  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function keyOf(y, m) { return y * 12 + (m - 1); }
  function yOf(key) { return Math.floor(key / 12); }
  function mOf(key) { return (key % 12) + 1; }
  function dim(y, m) { return new Date(Date.UTC(y, m, 0)).getUTCDate(); }
  function dateStr(y, m, d) { return y + '-' + pad2(m) + '-' + pad2(d); }
  function fmtInt(x) { return FM.fmtInt(x); }

  /** Tramo implied by the date (ADR-0002); used only when the row does not say. */
  function expectedTramo(y, m) {
    var k = keyOf(y, m);
    if (k < keyOf(2002, 7)) return 'T';
    if (k < keyOf(2012, 1)) return 'TA';
    if (k < keyOf(2018, 4)) return 'S';
    if (k < keyOf(2026, 8)) return 'N';
    return 'NP';
  }
  function normTramo(row, y, m) {
    var t = row && row.tramo ? String(row.tramo).toUpperCase() : null;
    if (t && TRAMO[t]) return t;
    return expectedTramo(y, m);
  }

  function fmtVal(x, estimated) {
    if (!isNum(x)) return '–';
    if (estimated && Math.abs(x) < 10 && x !== 0) return x.toFixed(1);
    return fmtInt(x);
  }
  /** Compact text for a cell: 842, 1.2k, 12k, 1.2M (estimated gets "~"). */
  function compact(x, estimated) {
    if (!isNum(x)) return '';
    var s;
    var a = Math.abs(x);
    if (a < 1000) s = (estimated && a < 10 && x !== 0) ? x.toFixed(1) : String(Math.round(x));
    else if (a < 10000) s = (x / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    else if (a < 1e6) s = Math.round(x / 1000) + 'k';
    else s = (x / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    return (estimated ? '~' : '') + s;
  }

  function seasonLabel(start, len) {
    if (len >= 12) return 'all year';
    var a = MON3[start % 12], b = MON3[(start + len - 1) % 12];
    return len === 1 ? a : a + '–' + b;
  }
  function pctText(share) { return Math.round(share * 100) + ' %'; }

  /**
   * K1 (6d): shortest circular run of months whose base medians hold >= threshold of the total.
   * Ties among runs of the same length: highest share; then the first one starting from January.
   */
  function circularWindow(medians, threshold) {
    var total = 0, i;
    for (i = 0; i < 12; i++) total += medians[i];
    if (!(total > 0)) return null;
    for (var len = 1; len <= 12; len++) {
      var best = null;
      for (var s = 0; s < 12; s++) {
        var sum = 0;
        for (i = 0; i < len; i++) sum += medians[(s + i) % 12];
        var share = sum / total;
        if (share >= threshold - 1e-12 && (!best || share > best.share + 1e-12)) best = { start: s, len: len, share: share };
      }
      if (best) {
        best.label = seasonLabel(best.start, best.len);
        best.crossesYear = (best.start + best.len > 12);
        best.text = best.label + (best.len === 1 ? ' holds ' : ' hold ') + pctText(best.share) + ' of detections';
        return best;
      }
    }
    return null;
  }

  /** Fire year starts the month after the FIRST minimum of the 12 monthly medians (6b; same as the Python reference). */
  function fireYearStartMonth(medians) {
    var min = Infinity, idx = 0;
    for (var i = 0; i < 12; i++) if (medians[i] < min) { min = medians[i]; idx = i; }
    return { minMonth: idx + 1, startMonth: ((idx + 1) % 12) + 1 };
  }

  function monthKeyOf(x) {
    if (!x) return null;
    if (typeof x === 'string') { var m = /^(\d{4})-(\d{2})/.exec(x); return m ? keyOf(+m[1], +m[2]) : null; }
    return (isNum(x.y) && isNum(x.m)) ? keyOf(x.y, x.m) : null;
  }
  /** options.range = { from: {y,m} | 'YYYY-MM', to: ... }: which months to SHOW. Marks and seasons always use the whole series. */
  function normRange(r) {
    if (!r || typeof r !== 'object') return null;
    var a = monthKeyOf(r.from), b = monthKeyOf(r.to);
    return (a === null && b === null) ? null : { from: a, to: b };
  }

  function normOptions(o) {
    o = o || {};
    return {
      mode: o.mode === 'anomaly' ? 'anomaly' : 'counts',
      base: o.base === 'B1' ? 'B1' : 'B2',
      axis: (o.axis === 'calendar' || o.axis === 'fire') ? o.axis : 'auto',
      vegetationOnly: o.vegetationOnly === false ? false : true,
      evalYear: isNum(o.evalYear) ? o.evalYear : null,
      range: normRange(o.range),
      view: (o.view === 'season' || o.view === 'daily') ? o.view : 'calendar'
    };
  }

  function buildModel(input) {
    input = input || {};
    var opts = normOptions(input.options);
    var manifest = input.manifest || {};
    var verdictOpen = (manifest.verdict !== null && manifest.verdict !== undefined);
    var notices = [];
    var synthetic = !!(input.synthetic || manifest.synthetic);
    var baseDef = BASES[opts.base];
    var b2 = BASES.B2;
    if (manifest.baseline && manifest.baseline.b2_end) b2 = { start: b2.start, end: manifest.baseline.b2_end, label: b2.start + '–' + manifest.baseline.b2_end };
    baseDef = opts.base === 'B1' ? BASES.B1 : b2;

    // reliability of the estimated months (verdict of the single test + rule M1); the verdict is read only when it exists
    var aoiIn = input.aoi || {};
    var relArgs = { verdict: verdictOpen ? manifest.verdict : null, country: aoiIn.country, nCells: aoiIn.nCells, tooFew: aoiIn.tooFewBy || null,
                    minAoiCells: input.reliability && input.reliability.minAoiCells, expected: aoiIn.expectedModis || null };
    function relFor(tramo) { return FR ? FR.assess({ verdict: relArgs.verdict, country: relArgs.country, nCells: relArgs.nCells, tooFew: relArgs.tooFew, minAoiCells: relArgs.minAoiCells, expected: relArgs.expected, tramo: tramo }) : null; }

    var norm = FI.normalize(input.intervals);
    var intervalLevel = (input.aoi && input.aoi.intervalLevel) || 'aoi';      // '1deg' | 'pais' | 'aoi' (a drawn AOI = 'aoi')
    if (!norm.ok) notices.push({ id: 'intervals-missing', level: 'warn',
      text: norm.placeholder ? '80 % ranges are only a SYNTHETIC placeholder in this export: months estimated from MODIS are drawn hatched but have no unusual / typical mark.'
                             : '80 % ranges are unavailable: months estimated from MODIS are drawn hatched but have no unusual / typical mark.' });
    else if (norm.placeholder) notices.push({ id: 'intervals-placeholder', level: 'warn',
      text: 'SYNTHETIC placeholder ranges (not real intervals): marks on estimated months only exercise the rule.' });

    // ---- rows ---------------------------------------------------------------------------------
    var rows = {};
    var anyVm = false, lastKey = -1, firstKey = keyOf(START.y, START.m);
    (input.monthly || []).forEach(function (r) {
      if (!r || !isNum(r.y) || !isNum(r.m)) return;
      var k = keyOf(r.y, r.m);
      if (k < firstKey) return;                      // Nov-2000 and earlier are out of the series
      rows[k] = r;
      if (isNum(r.vm)) anyVm = true;
      if (k > lastKey) lastKey = k;
    });
    var useVm = (opts.vegetationOnly === false);
    if (useVm && !anyVm) {
      useVm = false;
      notices.push({ id: 'vm-missing', level: 'warn', text: 'The "all thermal anomalies" series is not in this export; showing vegetation fires only.' });
    }
    function val(r) { if (!r) return null; var x = useVm ? (isNum(r.vm) ? r.vm : r.v) : r.v; return isNum(x) ? x : null; }

    // ---- daily (VIIRS only) -------------------------------------------------------------------
    var dailyMap = {}, lastDate = null, nDaily = 0;
    (Array.isArray(input.daily) ? input.daily : []).forEach(function (d) {
      if (!d || typeof d.d !== 'string') return;
      var x = useVm ? (isNum(d.vm) ? d.vm : d.v) : d.v;
      if (!isNum(x)) return;
      dailyMap[d.d] = { v: x, prov: !!d.prov };
      nDaily++;
      if (lastDate === null || d.d > lastDate) lastDate = d.d;
    });
    if (lastDate) {
      var ldk = keyOf(+lastDate.slice(0, 4), +lastDate.slice(5, 7));
      if (ldk > lastKey) lastKey = ldk;
    }
    if (lastKey < firstKey) {
      return { empty: true, opts: opts, notices: notices, unit: UNIT, synthetic: synthetic, aoi: input.aoi || {} };
    }

    // ---- base ---------------------------------------------------------------------------------
    function isB2Row(r, y, m) {
      var t = normTramo(r, y, m);
      if (t !== 'S' && t !== 'N') return false;
      if (r.prov) return false;
      if (y === 2012 && m === 1) return false;       // partial month (S-NPP starts 20 Jan 2012)
      if (r.inc === 1 || r.inc === true) return false; // satellite outage: a low count is not a low fire count
      return y >= b2.start && y <= b2.end && val(r) !== null;
    }
    function isB1Row(r, y, m) {
      var t = normTramo(r, y, m);
      if (t !== 'TA' && t !== 'S' && t !== 'N') return false;
      if (r.prov) return false;
      if (y === 2012 && m === 1) return false;
      if (r.inc === 1 || r.inc === true) return false;
      return y >= BASES.B1.start && y <= BASES.B1.end && val(r) !== null;
    }
    var baseByMonth = [], b2ByMonth = [], mm;
    for (mm = 0; mm < 12; mm++) { baseByMonth.push([]); b2ByMonth.push([]); }
    Object.keys(rows).forEach(function (ks) {
      var k = +ks, r = rows[k], y = yOf(k), m = mOf(k);
      if (isB2Row(r, y, m)) b2ByMonth[m - 1].push({ y: y, v: val(r) });
      if ((opts.base === 'B1' ? isB1Row(r, y, m) : isB2Row(r, y, m))) baseByMonth[m - 1].push({ y: y, v: val(r) });
    });
    function baseVals(m, exceptYear) {
      return baseByMonth[m - 1].filter(function (b) { return b.y !== exceptYear; }).map(function (b) { return b.v; });
    }

    // ---- cells ----------------------------------------------------------------------------------
    var cells = {}, vmax = 0;
    for (var k = firstKey; k <= lastKey; k++) {
      var y = yOf(k), m = mOf(k), r = rows[k];
      var c = { key: k, y: y, m: m, label: MON3[m - 1] + ' ' + y, longLabel: MONL[m - 1] + ' ' + y, hasRow: !!r, row: r || null,
                status: r ? 'ok' : 'nodata', tramo: null, estimated: false, provisional: false, partial: false, incomplete: false,
                value: null, interval: null, mark: null, markReason: null, pct: null, base: null, mtd: null, reliability: null };
      if (r) {
        c.tramo = normTramo(r, y, m);
        c.estimated = TRAMO[c.tramo].estimated;
        if (c.estimated) c.reliability = relFor(c.tramo);
        c.provisional = (c.tramo === 'NP') || !!r.prov;
        c.partial = (y === 2012 && m === 1 && c.tramo === 'S');
        c.incomplete = (r.inc === 1 || r.inc === true) && !c.partial;     // the contract sets inc = 1 on Jan-2012 (partial, not an outage)
        c.value = val(r);
        if (c.value === null) { c.status = 'nodata'; }
        else if (c.value > vmax) vmax = c.value;
        if (c.estimated && c.value !== null && norm.ok) c.interval = FI.intervalFor(norm, c.tramo, c.value, intervalLevel);
      }
      cells[k] = c;
    }

    // ---- month to date (H2) ------------------------------------------------------------------
    var mtd = null;
    if (lastDate) {
      var ly = +lastDate.slice(0, 4), lm = +lastDate.slice(5, 7), ld = +lastDate.slice(8, 10);
      if (ld < dim(ly, lm)) {
        var sumTo = function (yy, mm2, upTo) {
          var s = 0, any = false;
          for (var d = 1; d <= upTo; d++) { var e = dailyMap[dateStr(yy, mm2, d)]; if (e) { s += e.v; any = true; } }
          return { s: s, any: any };
        };
        var cur = sumTo(ly, lm, ld);
        var bvals = [];
        b2ByMonth[lm - 1].forEach(function (b) {
          if (b.y === ly) return;
          var sb = sumTo(b.y, lm, Math.min(ld, dim(b.y, lm)));
          if (sb.any) bvals.push(sb.s);
        });
        mtd = { lastDate: lastDate, y: ly, m: lm, d: ld, value: cur.s, base: bvals, baseLabel: b2.label,
                text: '1–' + ld + ' ' + MON3[lm - 1] };
        var kc = keyOf(ly, lm), cc = cells[kc];
        if (cc) {
          cc.mtd = mtd; cc.value = cur.s; cc.status = 'ok'; cc.provisional = true; cc.hasRow = true;
          if (!cc.tramo) cc.tramo = 'NP';
          if (cur.s > vmax) vmax = cur.s;
        }
      }
    }

    // ---- marks (U1 + I2) ------------------------------------------------------------------------
    var baseLabel = baseDef.label;
    Object.keys(cells).forEach(function (ks) {
      var c = cells[+ks];
      if (c.status !== 'ok' || c.value === null) return;
      var base = c.mtd ? c.mtd.base : baseVals(c.m, c.y);
      var ev = FM.evaluate(c.value, base);
      c.base = { n: ev.n, median: ev.median, p10: ev.p10, p90: ev.p90, label: c.mtd ? c.mtd.baseLabel : baseLabel,
                 scope: c.mtd ? 'same days' : 'month' };
      c.pct = ev.insufficient ? null : FM.percentileRank(c.value, base);
      if (c.incomplete) { c.markReason = 'incomplete'; return; }
      if (c.partial) { c.markReason = 'partial'; return; }
      if (c.estimated) {
        if (!c.interval) {
          if (ev.insufficient) c.mark = FM.markMonth({ value: c.value, base: base });
          else c.markReason = 'no-interval';
          return;
        }
        c.mark = FM.markMonth({ value: c.value, lo: c.interval.lo, hi: c.interval.hi, base: base });
      } else {
        c.mark = FM.markMonth({ value: c.value, base: base });
      }
    });

    // ---- K1 on the VIIRS base (B2), always -----------------------------------------------------------
    var medians = [], haveBase = false;
    for (mm = 0; mm < 12; mm++) {
      var arr = b2ByMonth[mm].map(function (b) { return b.v; });
      if (arr.length) haveBase = true;
      medians.push(arr.length ? FM.median(arr) : 0);
    }
    var season = null;
    if (haveBase) {
      var core = circularWindow(medians, 0.5), ext = circularWindow(medians, 0.8);
      var fy = fireYearStartMonth(medians);
      season = { core: core, extended: ext, medians: medians, minMonth: fy.minMonth, fireStartMonth: fy.startMonth,
                 crossesYear: !!(ext && ext.crossesYear), baseLabel: b2.label, nYears: Math.max.apply(null, b2ByMonth.map(function (a) { return a.length; })) };
    } else {
      notices.push({ id: 'no-base', level: 'warn', text: 'No VIIRS base years are available, so marks and seasons cannot be computed.' });
    }

    // ---- axis (G2) ------------------------------------------------------------------------------------
    var startMonth = 1, axisRequested = opts.axis, axisUsed = 'calendar', axisReason = '';
    if (season && season.extended) {
      if (opts.axis === 'fire' || (opts.axis === 'auto' && season.crossesYear)) {
        startMonth = season.fireStartMonth;
        axisUsed = startMonth === 1 ? 'calendar' : 'fire';
        axisReason = 'Rows show fire years (' + MON3[startMonth - 1] + '–' + MON3[(startMonth + 10) % 12] +
          ') because this area’s fire season crosses New Year. Switch to calendar years at any time.';
        if (opts.axis === 'fire' && !season.crossesYear) axisReason = 'Fire years start in ' + MON3[startMonth - 1] + ' (the month after the quietest month).';
      }
    } else if (opts.axis === 'fire') {
      notices.push({ id: 'no-fire-year', level: 'info', text: 'Fire year is unavailable without a VIIRS base; showing calendar years.' });
    }

    // ---- rows layout -----------------------------------------------------------------------------------
    var rowYearOf = function (y, m) { return startMonth === 1 ? y : (m >= startMonth ? y : y - 1); };
    var firstRow = rowYearOf(yOf(firstKey), mOf(firstKey)), lastRow = rowYearOf(yOf(lastKey), mOf(lastKey));
    var layout = [], colMonths = [], col;
    for (col = 0; col < 12; col++) colMonths.push(((startMonth - 1 + col) % 12) + 1);
    for (var ry = firstRow; ry <= lastRow; ry++) {
      var slots = [], total = 0, totLo = 0, totHi = 0, nOk = 0, rangeOk = true, flags = {};
      for (col = 0; col < 12; col++) {
        var cm = colMonths[col], cy = startMonth === 1 ? ry : (cm >= startMonth ? ry : ry + 1);
        var ck = keyOf(cy, cm), cell = cells[ck];
        if (!cell || (opts.range && ((opts.range.from !== null && ck < opts.range.from) || (opts.range.to !== null && ck > opts.range.to)))) { slots.push({ outside: true, y: cy, m: cm }); continue; }
        slots.push(cell);
        if (cell.status === 'ok' && cell.value !== null) {
          nOk++; total += cell.value;
          if (cell.estimated) { flags.estimated = true; if (cell.interval && isFinite(cell.interval.hi)) { totLo += cell.interval.lo; totHi += cell.interval.hi; } else rangeOk = false; }
          else { totLo += cell.value; totHi += cell.value; }
          if (cell.partial) flags.partial = true;
          if (cell.incomplete) flags.incomplete = true;
          if (cell.provisional) flags.provisional = true;
          if (cell.tramo === 'T') flags.terraOnly = true;
        }
      }
      var complete = slots.every(function (s) { return !s.outside && s.status === 'ok'; }) && !flags.provisional;
      layout.push({ key: ry, label: startMonth === 1 ? String(ry) : ry + '–' + pad2((ry + 1) % 100), slots: slots,
                    total: total, range: (flags.estimated && rangeOk && complete) ? { lo: totLo, hi: totHi } : null,
                    complete: complete, flags: flags, rank: null });
    }
    if (opts.range) layout = layout.filter(function (r) { return r.slots.some(function (sl) { return !sl.outside; }); });
    var ranked = layout.filter(function (r) { return r.complete; }).sort(function (a, b) { return b.total - a.total; });
    var rk = 0, prev = null;
    ranked.forEach(function (r, i) { if (prev === null || r.total !== prev) rk = i + 1; r.rank = rk; prev = r.total; });
    // The ranking puts years built from MODIS estimates (pre-2012) next to observed VIIRS years. It must not do so silently: every year that
    // holds an estimated month carries its label (the weakest label among its estimated months): 'indicative' | 'not-tested' | 'reliable';
    // a year of observed months only is 'observed'. A missing reliability module counts as 'indicative' (the conservative reading).
    layout.forEach(function (r) {
      var q = 'observed';
      if (r.flags.estimated) {
        q = 'reliable';
        r.slots.forEach(function (sl) {
          if (sl.outside || sl.status !== 'ok' || !sl.estimated || sl.value === null) return;
          var st = sl.reliability ? sl.reliability.state : 'indicative';
          if (st === 'indicative') q = 'indicative';
          else if (st === 'not-tested' && q !== 'indicative') q = 'not-tested';
        });
      }
      r.quality = q;
    });
    var rankedEstimated = ranked.filter(function (r) { return r.quality !== 'observed'; }).length;
    var rankMixed = rankedEstimated > 0 && rankedEstimated < ranked.length;

    // ---- notices from the data ------------------------------------------------------------------------------
    var anyEstimated = false, anyProv = false, anyInc = false, anyPartial = false;
    Object.keys(cells).forEach(function (ks) {
      var c = cells[+ks];
      if (c.status !== 'ok') return;
      if (c.estimated) anyEstimated = true;
      if (c.provisional) anyProv = true;
      if (c.incomplete) anyInc = true;
      if (c.partial) anyPartial = true;
    });
    if (synthetic) notices.push({ id: 'synthetic', level: 'warn', text: 'SYNTHETIC demo data: generated for testing, not real detections.' });
    if (input.aoi && input.aoi.tooFewModis) notices.push({ id: 'few-modis', level: 'warn', text: 'Too few MODIS detections here for a reliable pre-2012 estimate.' });
    var reliability = (FR && anyEstimated) ? FR.areaSummary(relArgs) : null;
    if (reliability) notices.push({ id: 'reliability', level: 'info', text: reliability.headline });
    if (anyEstimated && norm.ok) notices.push({ id: 'interval-approx', level: 'info', text: 'The 80 % range of an area you draw is an approximation that has not been validated.' });
    if (!verdictOpen) notices.push({ id: 'leak', level: 'info', text: 'Raw Terra, Aqua and S-NPP counts from 2019 onward are withheld until the pre-registered validation test has been run.' });

    return {
      empty: false, opts: opts, unit: UNIT, synthetic: synthetic, aoi: input.aoi || {}, manifest: manifest, verdictOpen: verdictOpen, reliability: reliability,
      useVm: useVm, base: { key: opts.base, label: baseLabel, start: baseDef.start, end: baseDef.end, b2Label: b2.label },
      norm: norm, cells: cells, firstKey: firstKey, lastKey: lastKey, vmax: vmax,
      season: season, axis: { requested: axisRequested, used: axisUsed, startMonth: startMonth, reason: axisReason },
      colMonths: colMonths, rows: layout, ranking: ranked, rankingTagged: rankedEstimated, rankingMixed: rankMixed, mtd: mtd,
      daily: { map: dailyMap, lastDate: lastDate, n: nDaily }, hasDaily: (nDaily > 0 && !!season), b2ByMonth: b2ByMonth, b2: b2,
      flags: { anyEstimated: anyEstimated, anyProv: anyProv, anyInc: anyInc, anyPartial: anyPartial },
      notices: notices
    };
  }

  // ---- tooltip content (pure, testable; respects anti-leak) -------------------------------------------------------
  function rawBySatellite(cell, model) {
    var r = cell.row || {}, out = [], withheld = false;
    var late = cell.y >= LEAK_YEAR;
    [['Terra', 't'], ['Aqua', 'a'], ['S-NPP', 's']].forEach(function (p) {
      if (late && !model.verdictOpen) { if (isNum(r[p[1]])) withheld = true; return; }
      if (isNum(r[p[1]])) out.push({ sat: p[0], n: r[p[1]] });
    });
    if (isNum(r.n20)) out.push({ sat: 'NOAA-20', n: r.n20 });
    return { items: out, withheld: withheld || (late && !model.verdictOpen) };
  }

  function tooltip(cell, model) {
    var lines = [], t = cell.tramo && TRAMO[cell.tramo];
    var title = cell.longLabel;
    if (cell.status !== 'ok') {
      return { title: title, lines: [{ k: 'p', t: 'No data for this month in the export. Missing data is not zero fire.' }],
               aria: title + ': no data' };
    }
    var est = cell.estimated;
    var valueTxt = (est ? '~' : '') + fmtVal(cell.value, est) + ' ' + UNIT;
    if (cell.mtd) lines.push({ k: 'h', t: 'Month to date (' + cell.mtd.text + ', last data ' + cell.mtd.lastDate + ')' });
    lines.push({ k: 'v', t: valueTxt });
    if (cell.value === 0 && !cell.incomplete) lines.push({ k: 'p', t: '0 detected (satellite hotspot detections only; zero detections do not mean zero fire).' });
    if (t) lines.push({ k: 'kv', a: 'Source', b: t.name });
    if (est && cell.interval) {
      lines.push({ k: 'kv', a: '80 % range', b: fmtVal(cell.interval.lo, true) + ' – ' + (isFinite(cell.interval.hi) ? fmtVal(cell.interval.hi, true) : 'no upper limit') });
      if (cell.interval.zero) lines.push({ k: 'p', t: 'The estimate is 0, so MODIS cannot rule out a higher true value: the upper limit is open.' });
    } else if (est && !model.norm.ok) {
      lines.push({ k: 'p', t: '80 % range unavailable (no interval table loaded).' });
    }
    if (cell.tramo === 'T') lines.push({ k: 'warn', t: 'Lower confidence (indicative): Terra only, Dec 2000 – Jun 2002.' });
    if (est && cell.reliability) lines.push({ k: 'kv', a: 'Validation label', b: cell.reliability.short });
    // raw counts per satellite (anti-leak)
    var raw = rawBySatellite(cell, model);
    if (raw.items.length) {
      lines.push({ k: 'kv', a: 'Raw detections' + (model.useVm ? '' : ' (outside mask)'), b: raw.items.map(function (i) { return i.sat + ' ' + fmtInt(i.n); }).join(' · ') });
    }
    if (raw.withheld) lines.push({ k: 'p', t: 'Raw Terra, Aqua and S-NPP counts for 2019 onward are withheld until the pre-registered validation test has been run.' });
    if (cell.row && isNum(cell.row.xm)) lines.push({ k: 'kv', a: 'Inside static mask (raw)', b: fmtInt(cell.row.xm) + (model.useVm ? ' (included above)' : ' (excluded above)') });
    // flags
    if (cell.partial) lines.push({ k: 'warn', t: 'Partial month: S-NPP data start on 20 Jan 2012.' });
    if (cell.incomplete) lines.push({ k: 'warn', t: 'Incomplete (satellite outage): a low or zero count here may reflect missing data, not absence of fire. No mark is given.' });
    if (cell.provisional) lines.push({ k: 'warn', t: 'Provisional: near-real-time (NRT) data; FIRMS replaces it with standard data after about 2–5 months, so this value and mark can change. Never used in a base.' });
    // mark
    if (cell.base && cell.base.n > 0) {
      var bl = cell.base.label;
      if (cell.mark) {
        var mk = cell.mark;
        if (mk.state === 'insufficient') lines.push({ k: 'kv', a: 'Mark', b: 'insufficient data (median of the same month in ' + bl + ' is below 5)' });
        else {
          var txt = mk.label;
          if (mk.state === 'possibly') txt += ' – the answer depends on the harmonisation uncertainty';
          if (cell.provisional) txt += ' (provisional)';
          lines.push({ k: 'kv', a: 'Mark', b: txt });
          if (mk.state !== 'typical') {
            var thr = mk.dir === 'low' ? 'below the 10th' : (mk.dir === 'high' ? 'above the 90th' : 'outside the 10th–90th');
            lines.push({ k: 'p', t: 'Rule: ' + thr + ' percentile of the same ' + (cell.mtd ? 'days' : 'month') + ' in ' + bl + ' (this year excluded).' });
          }
        }
        lines.push({ k: 'kv', a: 'Compared with', b: FM.ratioText(cell.value, cell.base.median, bl) + (cell.mtd ? ' for the same days' : '') });
        lines.push({ k: 'kv', a: 'Base', b: bl + ', ' + cell.base.n + ' years, p10 ' + fmtVal(cell.base.p10, false) + ' · median ' + fmtVal(cell.base.median, false) + ' · p90 ' + fmtVal(cell.base.p90, false) });
      } else if (cell.markReason === 'no-interval') {
        lines.push({ k: 'p', t: 'No mark: the 80 % range of this estimate is unavailable.' });
      } else if (cell.markReason === 'partial') {
        lines.push({ k: 'p', t: 'No mark for a partial month.' });
      }
    } else if (cell.markReason === 'incomplete') {
      /* already explained above */
    } else if (!cell.base || cell.base.n === 0) {
      lines.push({ k: 'p', t: 'No mark: no base years for this month.' });
    }
    var aria = cell.longLabel + ': ' + (est ? 'about ' : '') + fmtVal(cell.value, est) + ' ' + UNIT + (cell.mark ? ', ' + cell.mark.label : '') +
      (est ? ', estimated' : '') + (cell.provisional ? ', provisional' : '') + (cell.incomplete ? ', incomplete' : '');
    return { title: title, lines: lines, aria: aria };
  }

  return {
    MON3: MON3, MONL: MONL, UNIT: UNIT, BASES: BASES, TRAMO: TRAMO, START: START, LEAK_YEAR: LEAK_YEAR,
    buildModel: buildModel, tooltip: tooltip, circularWindow: circularWindow, fireYearStartMonth: fireYearStartMonth,
    seasonLabel: seasonLabel, pctText: pctText, compact: compact, fmtVal: fmtVal, expectedTramo: expectedTramo,
    keyOf: keyOf, dim: dim, dateStr: dateStr, rawBySatellite: rawBySatellite, isNum: isNum
  };
});
