/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * fiabilidad.js - pure logic (no DOM, testable in Node) of two rules about the pre-2012 estimates (harmonized MODIS months):
 *
 *  1. M1, "too few MODIS" (ADR-0004): an area whose EXPECTED MODIS count is below a minimum gets the notice "Too few MODIS detections
 *     here for a reliable pre-2012 estimate". Expected count = median, over the calibration window of the test (2012-02 .. 2018-12),
 *     of the monthly count of the area outside the static mask, zeros included and incomplete months left out (same definition as
 *     conteo_esperado in src/nucleo/validacion_rt05.py): Terra + Aqua ("TA", Jul 2002 - Dec 2011 era) or Terra alone ("T", era before).
 *     The minimum is read from CONFIG.MIN_MODIS_PER_MONTH = { T, TA }. A null value turns the rule OFF for that era (the number is
 *     decision #9 of lot 3; it goes ONLY in app/js/datos-config.js).
 *
 *  2. Label "reliable" / "indicative" of each estimated month, from the verdict of the single pre-registered test, which the exporter
 *     summarizes in manifest.verdict (src/exportar_demo.py: resumir_verdict). Rule (ADR-0005 7e/7f, ADR-0006, route I-05 point 3b):
 *       - no verdict (manifest.verdict = null)  -> "not yet tested" (nothing is invented);
 *       - Terra-only months (Dec 2000 - Jun 2002) -> always "indicative" (with or without a verdict);
 *       - Terra+Aqua months -> "reliable" only if the country passed P2 and P2b (manifest.verdict.paises.<country>.etiqueta_pais)
 *         AND the area covers at least one 3-degree block (manifest.verdict.min_celdas_aoi cells of 0.1 deg); else "indicative";
 *       - an area flagged by rule 1 is "indicative" whatever the verdict says.
 *       - the count class (I-05, run in the single test): the typical number of MODIS detections per month of the area (the expected
 *         count of rule 1, Terra + Aqua) falls in one of the classes < 10, 10-30, 30-100, >= 100; "reliable" also needs that class to be
 *         reliable in the country (manifest.verdict.paises.<country>.clases_I05.juntas.<class>.reliable). A verdict without clases_I05
 *         skips this step, as the core's reference rule (etiqueta_estimacion in src/nucleo/validacion_rt05.py) does.
 *     The label of an AOI never comes from a class alone: a country that did not pass P2 and P2b is "indicative" even if one class passed.
 *
 * Works in the browser (window.FireReliability) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireReliability = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var DEFAULT_MIN_AOI_CELLS = 900;                                   // 3 deg x 3 deg = 30 x 30 cells of 0.1 deg
  var DEFAULT_WINDOW = { from: { y: 2012, m: 2 }, to: { y: 2018, m: 12 } };

  var TEXT = {
    notTested: 'Not yet tested',
    notTestedLong: 'Pre-2012 estimates: not yet tested. The pre-registered validation test has not been run, so no month is labelled reliable. Months estimated from Terra alone (Dec 2000 to Jun 2002) are indicative by design.',
    reasons: {
      'too-few-modis': 'too few MODIS detections here for a reliable estimate',
      'country-test-not-passed': 'the pre-registered sensor-agreement tests (P2 and P2b) were not passed in this country',
      'aoi-smaller-than-block': 'this area is smaller than one 3-degree block, the scale at which the estimate was tested',
      'count-class-not-reliable': 'areas with this many MODIS detections per month did not pass the tests in this country',
      'count-class-unknown': 'the typical number of MODIS detections of this area is not known yet',
      'country-not-in-verdict': 'the validation test has no result for this country'
    }
  };

  function isNum(x) { return typeof x === 'number' && isFinite(x); }
  function key(y, m) { return y * 12 + (m - 1); }
  function median(a) {
    if (!a.length) return null;
    var s = a.slice().sort(function (x, y) { return x - y; }), n = s.length;
    return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
  }
  function posNum(x) { return isNum(x) && x >= 0 ? x : null; }

  // Count classes of I-05 (config/validacion.yaml: cortes_conteo_modis [10, 30, 100]); each cut belongs to the class above it.
  var COUNT_CLASSES = [{ name: '<10', min: -Infinity }, { name: '10-30', min: 10 }, { name: '30-100', min: 30 }, { name: '>=100', min: 100 }];
  function countClass(x) {
    if (!isNum(x)) return null;
    var name = COUNT_CLASSES[0].name;
    COUNT_CLASSES.forEach(function (c) { if (x >= c.min) name = c.name; });
    return name;
  }

  /** CONFIG -> normalized settings. Missing or invalid values turn the M1 rule off (null) or fall back to the documented defaults. */
  function settings(cfg) {
    cfg = cfg || {};
    var mm = cfg.MIN_MODIS_PER_MONTH || {}, rl = cfg.RELIABILITY || {};
    var w = rl.EXPECTED_COUNT_WINDOW;
    var win = (w && w.from && w.to && isNum(w.from.y) && isNum(w.from.m) && isNum(w.to.y) && isNum(w.to.m)) ? w : DEFAULT_WINDOW;
    return {
      minModis: { T: posNum(mm.T), TA: posNum(mm.TA) },               // null = rule off
      minAoiCells: (isNum(rl.MIN_AOI_CELLS) && rl.MIN_AOI_CELLS >= 1) ? rl.MIN_AOI_CELLS : null,   // null = use the manifest value
      window: win
    };
  }

  /**
   * Expected MODIS count of an area. rows: monthly records of the area's cells (all dates); disponibilidad: optional (incomplete and
   * partial months are left out of the median). Returns { T, TA, months } or null when the rows were not loaded.
   * A cell-month without a row counts as 0 (data contract: no row = 0 detections).
   */
  function expectedModis(rows, o) {
    if (!rows) return null;
    o = o || {};
    var win = o.window || DEFAULT_WINDOW, flagged = {}, disp = o.disponibilidad || null;
    if (disp) {
      (disp.meses_incompletos || []).forEach(function (e) { flagged[key(e.y, e.m)] = true; });
      (disp.meses_parciales || []).forEach(function (e) { flagged[key(e.y, e.m)] = true; });
    }
    var from = key(win.from.y, win.from.m), to = key(win.to.y, win.to.m), tByM = {}, aByM = {};
    rows.forEach(function (r) {
      if (!r || !isNum(r.y) || !isNum(r.m)) return;
      var k = key(r.y, r.m);
      if (k < from || k > to) return;
      if (r.inc === 1 || r.inc === true) flagged[k] = true;
      tByM[k] = (tByM[k] || 0) + (isNum(r.t) ? r.t : 0);
      aByM[k] = (aByM[k] || 0) + (isNum(r.a) ? r.a : 0);
    });
    var t = [], ta = [];
    for (var k = from; k <= to; k++) {
      if (flagged[k]) continue;
      t.push(tByM[k] || 0);
      ta.push((tByM[k] || 0) + (aByM[k] || 0));
    }
    return { T: median(t), TA: median(ta), months: t.length };
  }

  /** Rule M1: { T, TA, any }; each value is true / false, or null when the rule is off for that era (or the count is unknown). */
  function tooFew(expected, minModis) {
    minModis = minModis || {};
    function one(era) {
      var min = posNum(minModis[era]);
      if (min === null || !expected || !isNum(expected[era])) return null;
      return expected[era] < min;
    }
    var T = one('T'), TA = one('TA');
    return { T: T, TA: TA, any: T === true || TA === true };
  }

  function verdictCountry(verdict, country) {
    return (verdict && verdict.paises && country && verdict.paises[country]) || null;
  }

  /**
   * Label of one estimated month. a = { verdict, country, tramo ('T' | 'TA'), nCells, tooFew {T, TA}, minAoiCells, expected {T, TA} }.
   * Returns null for observed months (VIIRS), else { state: 'not-tested' | 'reliable' | 'indicative', reasons [...], short, text }.
   */
  function assess(a) {
    a = a || {};
    if (a.tramo !== 'T' && a.tramo !== 'TA') return null;
    if (a.verdict === null || a.verdict === undefined) {
      if (a.tramo === 'T') {                                          // Terra only is 'indicative' whatever the test says (ADR-0005 7f)
        return { state: 'indicative', reasons: ['terra-only', 'not-tested'], short: 'indicative (Terra only); ' + TEXT.notTested.toLowerCase(),
                 text: 'Lower confidence: Terra only (indicative by design); the validation test has not been run.' };
      }
      return { state: 'not-tested', reasons: [], short: TEXT.notTested, text: TEXT.notTestedLong };
    }
    var pc = verdictCountry(a.verdict, a.country);
    if (!pc) return indicative(['country-not-in-verdict'], null);
    var reasons = [];
    if (a.tooFew && a.tooFew[a.tramo] === true) reasons.push('too-few-modis');
    if (a.tramo === 'T') {
      reasons.push('terra-only');
      return indicative(reasons, pc.etiqueta_terra_sola || 'indicative (Terra only)');
    }
    var minCells = isNum(a.minAoiCells) ? a.minAoiCells : (isNum(a.verdict.min_celdas_aoi) ? a.verdict.min_celdas_aoi : DEFAULT_MIN_AOI_CELLS);
    if (pc.etiqueta_pais !== 'reliable') reasons.push('country-test-not-passed');
    if (!isNum(a.nCells) || a.nCells < minCells) reasons.push('aoi-smaller-than-block');
    var classes = pc.clases_I05 && (pc.clases_I05.juntas || null);
    if (classes) {                                                    // I-05 was run: the count class must be reliable too
      var cl = a.expected && isNum(a.expected.TA) ? countClass(a.expected.TA) : null;
      if (cl === null) reasons.push('count-class-unknown');
      else if (!classes[cl] || classes[cl].reliable !== true) reasons.push('count-class-not-reliable');
    }
    if (reasons.length) return indicative(reasons, null);
    return { state: 'reliable', reasons: [], short: 'reliable',
             text: 'Reliable: the pre-registered sensor-agreement tests P2 and P2b were passed in this country, the area covers at least one 3-degree block and its count class passed too.' };
  }

  function indicative(reasons, terraText) {
    var parts = reasons.filter(function (r) { return TEXT.reasons[r]; }).map(function (r) { return TEXT.reasons[r]; });
    var why = terraText || parts.join('; ');
    if (terraText && parts.length) why = terraText + '; ' + parts.join('; ');
    return { state: 'indicative', reasons: reasons, short: terraText ? terraText : 'indicative (' + parts.join('; ') + ')',
             text: terraText ? ('Lower confidence: ' + why + '.') : 'Indicative: ' + why + '.' };
  }

  /**
   * Label of the whole area for the header of the calendar: { state, headline, ta, t }.
   * headline always starts with "Pre-2012 estimates" and never says "reliable" without a verdict.
   */
  function areaSummary(a) {
    var ta = assess({ verdict: a.verdict, country: a.country, tramo: 'TA', nCells: a.nCells, tooFew: a.tooFew, minAoiCells: a.minAoiCells, expected: a.expected });
    var t = assess({ verdict: a.verdict, country: a.country, tramo: 'T', nCells: a.nCells, tooFew: a.tooFew, minAoiCells: a.minAoiCells, expected: a.expected });
    var headline;
    if (ta.state === 'not-tested') headline = TEXT.notTestedLong;
    else if (ta.state === 'reliable') headline = 'Pre-2012 estimates: reliable for Jul 2002 to Dec 2011 (' + ta.text.replace(/^Reliable: /, '').replace(/\.$/, '') + '). Dec 2000 to Jun 2002 (Terra only): indicative.';
    else {
      // The headline gives the decisive reasons: when the country did not pass, the size of the area and its count class are moot (the
      // tooltip of each month still lists every reason).
      var why = ta.reasons.indexOf('country-test-not-passed') >= 0
        ? ta.reasons.filter(function (r) { return r === 'country-test-not-passed' || r === 'too-few-modis'; })
        : ta.reasons;
      headline = 'Pre-2012 estimates: indicative for Jul 2002 to Dec 2011 (' + why.map(function (r) { return TEXT.reasons[r]; }).filter(Boolean).join('; ') + '). Dec 2000 to Jun 2002 (Terra only): indicative.';
    }
    return { state: ta.state, headline: headline, ta: ta, t: t };
  }

  return {
    TEXT: TEXT, DEFAULT_MIN_AOI_CELLS: DEFAULT_MIN_AOI_CELLS, DEFAULT_WINDOW: DEFAULT_WINDOW,
    settings: settings, expectedModis: expectedModis, tooFew: tooFew, verdictCountry: verdictCountry, countClass: countClass,
    assess: assess, areaSummary: areaSummary, median: median
  };
});
