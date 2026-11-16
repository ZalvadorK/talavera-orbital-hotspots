/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * marca.js - "unusual" rule 6c-q (ADR-0006), exactly as specified:
 *   1. Type-6 quantile (Weibull, position (N+1)p, clipped to min/max) of the SAME calendar month
 *      in the base, excluding the evaluated year (the caller passes the base already without it).
 *   2. STRICT inequality: high if value > p90, low if value < p10. A value equal to a threshold is not marked.
 *   3. "Unusually low" only if p10 > 0 (tied zeros never give a low mark).
 *   4. "Base >= 5" means the MEDIAN of the same month in the base is >= 5 (not the maximum);
 *      otherwise the answer is "insufficient data" (same rule as 6a).
 *   5. I2: the rule is evaluated at both ends of the 80 % interval of the harmonised value:
 *        unusual   = both ends meet the rule (same direction)
 *        typical   = neither end meets it
 *        possibly  = anything else
 *      Observed VIIRS months have no harmonisation interval: two states (unusual / typical).
 *
 * Exactness (ADR-0006 step 2, strict inequality): every decision (value > p90, value < p10, p10 > 0, median >= 5) is
 * taken on the EXACT rational threshold, never on a floating-point approximation of it. The threshold is
 * q = a + (r/100)(b - a) with r an integer 0..99, so "value vs q" is the sign of 100(v - a) - r(b - a):
 *   - integer data (counts, the normal case): that expression is computed exactly in doubles;
 *   - any other finite data: it is computed exactly with BigInt on the binary value of each double.
 * Example that float arithmetic gets wrong: N = 13, p = 0.1 -> (N+1)*0.1 = 1.4000000000000001, so a value equal to the
 * exact p10 (e.g. base [1,6,...], p10 = 1 + 0.4*(6-1) = 3) would be marked "unusually low". Here it is "typical".
 * A Python reference must therefore use exact arithmetic too (fractions.Fraction with p = Fraction(10, 100), not 0.1).
 * The p10/p90/median numbers that are RETURNED (for the tooltip) are ordinary doubles; they are never used to decide.
 *
 * Works in the browser (window.FireMark) and in Node (module.exports). No dependencies.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireMark = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var MIN_MEDIAN = 5;      // 6a / 6c-q item 4
  var P_HIGH = 90;         // integer percents on purpose (exact position arithmetic)
  var P_LOW = 10;

  function finiteNumbers(arr) {
    var out = [];
    for (var i = 0; i < arr.length; i++) {
      var x = arr[i];
      if (typeof x === 'number' && isFinite(x)) out.push(x);
    }
    return out;
  }

  function sortedCopy(arr) {
    return finiteNumbers(arr).sort(function (a, b) { return a - b; });
  }

  /**
   * Type-6 (Weibull) quantile of an ASCENDING array, scaled by 100 so comparisons stay exact for
   * integer data. pct is an integer in [0, 100]. Position (1-based) h = (N+1) * pct / 100,
   * clipped to [1, N]. Returns 100 * quantile.
   */
  function quantile6x100(sorted, pct) {
    var n = sorted.length;
    if (n === 0) return NaN;
    var num = (n + 1) * pct;             // 100 * h, an exact integer
    if (num <= 100) return sorted[0] * 100;
    if (num >= 100 * n) return sorted[n - 1] * 100;
    var k = Math.floor(num / 100);       // 1-based lower position, 1 <= k <= n-1
    var r = num - 100 * k;               // 0..99, fractional part * 100
    var a = sorted[k - 1], b = sorted[k];
    return a * 100 + r * (b - a);
  }

  /** Type-6 quantile (unscaled). Accepts unsorted input. pct integer 0..100. */
  function quantile6(values, pct) {
    return quantile6x100(sortedCopy(values), pct) / 100;
  }

  function medianSorted(sorted) {
    var n = sorted.length;
    if (!n) return NaN;
    var mid = n >> 1;
    return (n % 2) ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }
  function median(values) { return medianSorted(sortedCopy(values)); }

  // ---- exact comparison of a value with a type-6 quantile ------------------------------------------------------
  var HAS_BIG = typeof BigInt === 'function';
  var DV = HAS_BIG ? new DataView(new ArrayBuffer(8)) : null;
  var SAFE_INT = 1e12;                       // 100 * |x| and r * |b - a| stay far below 2^53

  /** Finite double -> { m: signed BigInt mantissa, e: exponent } with x = m * 2^e (exact). */
  function decompose(x) {
    if (x === 0) return { m: BigInt(0), e: 0 };
    DV.setFloat64(0, x);
    var hi = DV.getUint32(0), lo = DV.getUint32(4);
    var neg = (hi >>> 31) === 1, ex = (hi >>> 20) & 0x7ff;
    var mant = (BigInt(hi & 0xfffff) << BigInt(32)) | BigInt(lo), e;
    if (ex === 0) { e = -1074; } else { mant = mant | (BigInt(1) << BigInt(52)); e = ex - 1075; }
    return { m: neg ? -mant : mant, e: e };
  }

  /** Exact sign of 100*(v - a) - r*(b - a) = 100 v + (r - 100) a - r b, for finite doubles and integer r. */
  function exactSign(v, a, b, r) {
    var tv = decompose(v), ta = decompose(a), tb = decompose(b);
    var e = Math.min(tv.e, ta.e, tb.e);
    var sum = BigInt(100) * (tv.m << BigInt(tv.e - e)) + BigInt(r - 100) * (ta.m << BigInt(ta.e - e)) - BigInt(r) * (tb.m << BigInt(tb.e - e));
    return sum > 0 ? 1 : (sum < 0 ? -1 : 0);
  }

  function sgn(x) { return x > 0 ? 1 : (x < 0 ? -1 : 0); }

  /**
   * Sign of (v - q), q = type-6 quantile (pct integer 0..100) of the ASCENDING array `sorted` (non-empty), EXACT.
   * v = +-Infinity is allowed (open-ended interval end). A non-finite v that is NaN returns 0 (no decision).
   */
  function cmpQuantile(sorted, pct, v) {
    var n = sorted.length;
    if (v !== v) return 0;
    if (v === Infinity) return 1;
    if (v === -Infinity) return -1;
    var num = (n + 1) * pct, a, b, r;
    if (num <= 100) { a = b = sorted[0]; r = 0; }
    else if (num >= 100 * n) { a = b = sorted[n - 1]; r = 0; }
    else { var k = Math.floor(num / 100); r = num - 100 * k; a = sorted[k - 1]; b = sorted[k]; }
    if (r === 0 || a === b) return sgn(v - a);            // IEEE subtraction: sign exact, zero iff equal
    if (Number.isInteger(v) && Number.isInteger(a) && Number.isInteger(b) &&
        Math.abs(v) < SAFE_INT && Math.abs(a) < SAFE_INT && Math.abs(b) < SAFE_INT) {
      return sgn(100 * (v - a) - r * (b - a));
    }
    if (HAS_BIG) return exactSign(v, a, b, r);
    return sgn(100 * (v - a) - r * (b - a));             // very old engine without BigInt: best effort
  }

  /**
   * Evaluate the rule for ONE value against the base (same calendar month, evaluated year already removed).
   * Returns { n, median, p10, p90, insufficient, high, low }.
   */
  function evaluate(value, baseValues) {
    var s = sortedCopy(baseValues || []);
    var n = s.length;
    var med = medianSorted(s);
    var out = { n: n, median: med, p10: NaN, p90: NaN, insufficient: false, high: false, low: false, value: value };
    if (n) { out.p10 = quantile6x100(s, P_LOW) / 100; out.p90 = quantile6x100(s, P_HIGH) / 100; }
    if (n === 0 || cmpQuantile(s, 50, MIN_MEDIAN) > 0) {   // insufficient = median < 5 (5 > q), exact
      out.insufficient = true;
      return out;
    }
    out.high = cmpQuantile(s, P_HIGH, value) > 0;                              // strict: value > p90
    out.low = cmpQuantile(s, P_LOW, 0) < 0 && cmpQuantile(s, P_LOW, value) < 0; // p10 > 0, and strict: value < p10
    return out;
  }

  /** Direction code of one evaluation: 'high' | 'low' | 'none'. */
  function dirOf(ev) { return ev.high ? 'high' : (ev.low ? 'low' : 'none'); }

  /**
   * Mark of one month/cell.
   *   opts.value : point value (observed count or harmonised estimate)
   *   opts.lo/hi : 80 % interval of a harmonised value (omit for observed months)
   *   opts.base  : array of same-month base values without the evaluated year
   * Returns { state, dir, label, n, median, p10, p90, ratio, interval:boolean, ends:{lo,hi} }
   *   state: 'unusual' | 'possibly' | 'typical' | 'insufficient'
   *   dir  : 'high' | 'low' | 'mixed' | null
   */
  function markMonth(opts) {
    var base = opts.base || [];
    // an interval may be open-ended (hi = Infinity when the harmonised estimate is 0, as in the Python reference)
    var hasInterval = (typeof opts.lo === 'number' && typeof opts.hi === 'number' && !isNaN(opts.lo) && !isNaN(opts.hi));
    if (!(typeof opts.value === 'number' && isFinite(opts.value))) {      // missing value (e.g. no data): no flag
      var eb = evaluate(0, base);
      return { state: 'incomplete', dir: null, label: 'incomplete', n: eb.n, median: eb.median, p10: eb.p10, p90: eb.p90, ratio: null,
               interval: hasInterval, ends: null, value: opts.value };
    }
    var mid = evaluate(opts.value, base);
    var res = { state: 'typical', dir: null, label: '', n: mid.n, median: mid.median, p10: mid.p10, p90: mid.p90,
                ratio: ratioOf(opts.value, mid.median), interval: hasInterval, ends: null, value: opts.value };
    if (mid.insufficient) {
      res.state = 'insufficient'; res.label = 'insufficient data';
      return res;
    }
    if (!hasInterval) {
      var d = dirOf(mid);
      if (d === 'none') { res.state = 'typical'; res.label = 'typical'; }
      else { res.state = 'unusual'; res.dir = d; res.label = 'unusually ' + d; }
      return res;
    }
    var lo = Math.min(opts.lo, opts.hi), hi = Math.max(opts.lo, opts.hi);
    var eLo = dirOf(evaluate(lo, base)), eHi = dirOf(evaluate(hi, base));
    res.ends = { lo: eLo, hi: eHi };
    if (eLo === 'none' && eHi === 'none') {
      res.state = 'typical'; res.label = 'typical';
    } else if (eLo === eHi) {                    // both ends meet the rule, same direction
      res.state = 'unusual'; res.dir = eLo; res.label = 'unusually ' + eLo;
    } else {
      res.state = 'possibly';
      if (eLo === 'none') res.dir = eHi;
      else if (eHi === 'none') res.dir = eLo;
      else res.dir = 'mixed';                    // low at one end and high at the other
      res.label = res.dir === 'mixed' ? 'possibly unusual' : 'possibly unusually ' + res.dir;
    }
    return res;
  }

  function ratioOf(value, med) {
    if (!(isFinite(value)) || !(isFinite(med))) return null;
    if (med === 0) return value === 0 ? 1 : Infinity;
    return value / med;
  }

  function fmtInt(x) {
    return Math.round(x).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /** "2.3× the 2012-2025 median" (RT-09). baseLabel e.g. "2012–2025". */
  function ratioText(value, med, baseLabel) {
    var tail = ' the ' + (baseLabel || 'base') + ' median';
    var r = ratioOf(value, med);
    if (r === null || !isFinite(med)) return 'no base median available';
    if (med === 0) {
      return value === 0 ? 'equal to the ' + (baseLabel || 'base') + ' median (0)'
                         : 'above a ' + (baseLabel || 'base') + ' median of 0';
    }
    var s = r.toFixed(1);                                    // always one decimal, like the Python reference
    return s + '×' + tail;
  }

  /**
   * "Unusual season" (ADR-0006): cumulative of the fire year up to day D above the p90 (type 6, strict) of the base
   * cumulatives at the same day. Only an empty base is "insufficient" (same as the Python reference). small=true flags
   * a base median below 5 (very early in the season) so the UI can say so.
   */
  function seasonMark(cum, baseCums) {
    var s = sortedCopy(baseCums || []);
    if (!s.length) return { state: 'insufficient', p90: NaN, median: NaN, n: 0, high: false, small: false };
    var q90 = quantile6x100(s, P_HIGH), med = medianSorted(s), high = cmpQuantile(s, P_HIGH, cum) > 0;   // exact, strict
    return { state: high ? 'unusual' : 'typical', p90: q90 / 100, median: med, n: s.length, high: high, small: med < MIN_MEDIAN };
  }

  /** Percentile rank (0-100) of value among base values, mid-rank for ties. null if no base. */
  function percentileRank(value, baseValues) {
    var b = finiteNumbers(baseValues || []);
    if (!b.length) return null;
    var below = 0, equal = 0;
    for (var i = 0; i < b.length; i++) { if (b[i] < value) below++; else if (b[i] === value) equal++; }
    return 100 * (below + 0.5 * equal) / b.length;
  }

  return {
    VERSION: '1.1.0',
    MIN_MEDIAN: MIN_MEDIAN,
    quantile6: quantile6,
    quantile6x100: quantile6x100,
    cmpQuantile: cmpQuantile,
    median: median,
    evaluate: evaluate,
    markMonth: markMonth,
    seasonMark: seasonMark,
    ratioText: ratioText,
    ratioOf: ratioOf,
    percentileRank: percentileRank,
    fmtInt: fmtInt
  };
});
