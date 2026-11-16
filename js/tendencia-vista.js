/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * tendencia-vista.js - SVG of the descriptive annual trend view (see tendencia-modelo.js), built as a string with inline
 * attributes only (no CSS), so the same markup is shown on screen and rasterised to PNG. Every figure carries the visible
 * mark "SI-generated (AI)" and "Data: NASA FIRMS" (footer of graficos.js), plus "SYNTHETIC DEMO DATA" for synthetic data.
 *
 *   draw(model, opts)   -> {svg, w, h, idp}   the figure (chart, slopes, excluded years, notes, footer)
 *   describe(model)     -> {headline, subtitle, rows, excluded, method, notes}   the same texts, for the HTML next to the figure
 *   yearTip(model, y)   -> string             one-line text of a year (SVG <title>, table, tests)
 *
 * Series: "harmonized" (blue, circles; estimated years carry the 80 % range) and "raw, as detected by each sensor"
 * (orange; squares = MODIS, triangles = VIIRS). Hollow markers = years left out of the slope (incomplete or provisional).
 * Nothing is told by colour alone: shapes, fills, dashes and text labels carry every distinction.
 * Works in the browser (window.FireTrendView) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var req = (typeof module === 'object' && typeof require === 'function');
  var P = req ? require('./calendario-paleta.js') : root.FirePalette;
  var C = req ? require('./graficos.js') : root.FireCharts;
  var T = req ? require('./tendencia-modelo.js') : root.FireTrendModel;
  var api = factory(P, C, T);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireTrendView = api;
})(typeof window !== 'undefined' ? window : globalThis, function (P, C, T) {
  'use strict';

  var W = 840, X0 = 84, X1 = 672, PH = 300;
  var BLUE = '#0072B2', BLUE_D = '#00334F', ORANGE = '#E69F00', ORANGE_D = '#7A3600', RANGE = '#CC79A7';
  var uid = 0, text = C.text, esc = C.esc;

  function niceMax(v) {
    if (!(v > 0)) return 1;
    var e = Math.pow(10, Math.floor(Math.log10(v))), f = v / e;
    var nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return nf * e;
  }
  function fmt(x) { return T.fmtInt(x); }
  function axisLabel(v) { return v >= 1000 ? (Math.round(v / 100) / 10) + 'k' : String(Math.round(v * 10) / 10); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function showH(model) { return model.opts.show !== 'raw'; }
  function showR(model) { return model.opts.show !== 'harmonized'; }

  // ---------------------------------------------------------------------------------------------- texts
  function yearTip(model, y) {
    var a = model.years.filter(function (z) { return z.y === y; })[0];
    if (!a) return String(y) + ': no data in the selected dates.';
    var parts = [];
    if (a.harmonized !== null) {
      parts.push('harmonized ' + (a.estimated ? '~' : '') + fmt(a.harmonized) + ' (VIIRS-equivalent' + (a.estimated ? ', estimated from MODIS' : ', observed') + ')');
      if (a.range) parts.push('80 % range ' + fmt(a.range.lo) + ' to ' + (isFinite(a.range.hi) ? fmt(a.range.hi) : 'no upper limit'));
    }
    if (a.raw !== null) parts.push('raw ' + (a.sensor === 'MODIS' ? 'MODIS' : 'VIIRS') + ' ' + fmt(a.raw));
    var st = a.status === 'complete' ? 'complete year, used in the slopes'
      : (a.status === 'provisional' ? 'provisional year, left out of the slopes' : 'incomplete year, left out of the slopes') +
        (a.reasons.length ? ' (' + a.reasons.join('; ') + ')' : '');
    return y + ': ' + parts.join('; ') + '; ' + st + '. ' + (a.status === 'complete' ? '' : 'The totals shown cover only ' + a.months + ' month' + (a.months === 1 ? '' : 's') + '.');
  }

  function rowText(model, row) {
    var s = row.label + ': ' + row.text + '.';
    if (row.ok || row.n) s += ' n = ' + row.n + ' complete ' + (row.n === 1 ? 'year' : 'years') + (row.scope ? ' (' + row.scope + ')' : '') + '.';
    if (row.key === 'harmonized' && row.ok) s += ' ' + row.nEstimated + ' estimated from MODIS, ' + row.nObserved + ' observed by VIIRS.';
    if (row.key === 'raw' && row.sensors && row.sensors.length > 1) s += ' Not comparable across 2012: it mixes MODIS (until Dec 2011) and VIIRS (from Jan 2012).';
    return s;
  }

  function describe(model) {
    var aoi = (model.aoi && model.aoi.name) || 'Selected area';
    var headline = 'Sen slope of the annual totals, complete years only: ' + model.label + '.';
    var subtitle = 'Calendar years (UTC), ' + T.UNIT + '. Harmonized = one VIIRS-equivalent scale; raw = as each sensor detected them ' +
      '(MODIS until Dec 2011, VIIRS from Jan 2012).';
    var rows = [];
    ['harmonized', 'viirs', 'raw'].forEach(function (k) {
      var row = model.stats[k];
      if (k === 'raw' ? !showR(model) : !showH(model)) return;
      rows.push({ key: k, label: row.label, text: rowText(model, row), ok: row.ok, stat: row });
    });
    var excluded = model.excluded.map(function (e) { return e.y + ' (' + e.reasons.join('; ') + ')'; });
    var any = rows.filter(function (r) { return r.ok; })[0];
    var method = any ? any.stat.method + '. The interval reflects year-to-year variation only: it does not include the harmonization uncertainty (the 80 % ranges). No significance test is made here.'
      : 'No slope could be computed for the selected dates.';
    var notes = [
      'Counts are satellite hotspot detections, not individual fires or ground-reported incidents. Zero detections do not mean zero fire.',
      'Harmonized: MODIS detections converted to VIIRS-equivalent counts before 2012 (estimates, drawn with their 80 % range), VIIRS counts observed with weight 1 afterwards.',
      'Raw: the detections as each sensor reported them. MODIS (1 km pixels) until Dec 2011 and VIIRS (375 m) from Jan 2012 are different instruments, so the raw line can change level at the change of sensor. From 2012 VIIRS is counted with weight 1, so the two lines coincide.',
      'Incomplete and provisional years (series start, satellite outage, partial month, near-real-time data, year in progress) are drawn with hollow markers and never enter a slope.',
      'Known limitation: in the Bahía Blanca preset area the harmonized estimates for 2001–2003 are about 5–7 times the 2004–2011 average, and Terra\'s own raw detections there were already 4.4–6.7 times its 2004–2011 average, so the jump is in the MODIS detections, not created by the conversion. The method was not recalibrated for this; read that early period with caution (see Method notes).',
      'Known limitation: the FIRMS missing-data table lists days without Terra data in March and April 2002 that the calendar does not flag as incomplete, so the 2002 total can come out low (see Method notes).'
    ];
    model.notices.forEach(function (n) { notes.push(n.text); });
    return { headline: headline, subtitle: subtitle, aoi: aoi, rows: rows, excluded: excluded, method: method, notes: notes };
  }

  // ---------------------------------------------------------------------------------------------- shapes
  function marker(shape, cx, cy, color, filled) {
    var s = '';
    var fill = filled ? color : '#FFFFFF', stroke = filled ? '#1A1A1A' : color, sw = filled ? 0.9 : 2;
    if (shape === 'square') s = '<rect x="' + (cx - 3.8).toFixed(1) + '" y="' + (cy - 3.8).toFixed(1) + '" width="7.6" height="7.6" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '"/>';
    else if (shape === 'triangle') s = '<polygon points="' + cx.toFixed(1) + ',' + (cy - 4.8).toFixed(1) + ' ' + (cx - 4.6).toFixed(1) + ',' + (cy + 3.6).toFixed(1) + ' ' + (cx + 4.6).toFixed(1) + ',' + (cy + 3.6).toFixed(1) + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '" stroke-linejoin="round"/>';
    else s = '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="4.2" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '"/>';
    return s;
  }

  function lineSeg(x1, y1, x2, y2, color, w, dash) {
    return '<line x1="' + x1.toFixed(1) + '" y1="' + y1.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y2.toFixed(1) + '" stroke="' + color + '" stroke-width="' + w + '"' +
      (dash ? ' stroke-dasharray="' + dash + '"' : '') + ' stroke-linecap="round"/>';
  }

  // ---------------------------------------------------------------------------------------------- the figure
  function draw(model, o) {
    o = o || {};
    var chartOnly = !!o.chartOnly;                 // on screen: chart + legend only (the page prints the texts as HTML)
    var idp = 'tr' + (++uid) + '-', d = describe(model), body = '', ty = chartOnly ? 14 : 28;
    if (model.synthetic) { body += C.synthBanner(model, 24, 8); ty = chartOnly ? 38 : 54; }
    var title = d.aoi + (model.aoi && model.aoi.country ? ' (' + (model.aoi.country === 'mexico' ? 'Mexico' : (model.aoi.country === 'argentina' ? 'Argentina' : model.aoi.country)) + ')' : '') +
      ' — annual hotspot detections, harmonized and raw';
    var y;
    if (chartOnly) y = ty + 16;
    else {
      var tl = C.textLines(24, ty, title, 62, { size: 18, weight: 700, lineHeight: 22 });
      body += tl.svg;
      var sl = C.textLines(24, ty + tl.height + 2, d.subtitle, 106, { size: 12, fill: P.INK2, lineHeight: 15 });
      body += sl.svg;
      y = ty + tl.height + 2 + sl.height + 6;
      // badge: the view is descriptive
      var badgeTxt = cap(model.label);
      body += '<rect x="24" y="' + y + '" width="' + (badgeTxt.length * 6.9 + 18).toFixed(0) + '" height="20" rx="4" fill="#FFFFFF" stroke="#1A1A1A" stroke-width="1.2"/>' + text(33, y + 14, badgeTxt, { size: 11.5, weight: 700 });
      y += 40;
    }

    var yearsAll = model.years, n = model.lastYear - model.firstYear + 1, step = (X1 - X0) / n;
    var idx = function (yr) { return yr - model.firstYear; };
    var cx = function (yr) { return X0 + (idx(yr) + 0.5) * step; };
    var maxV = 0;
    yearsAll.forEach(function (a) {
      if (showH(model) && a.harmonized !== null) maxV = Math.max(maxV, a.harmonized, a.range && isFinite(a.range.hi) ? a.range.hi : 0);
      if (showR(model) && a.raw !== null) maxV = Math.max(maxV, a.raw);
    });
    var ymax = niceMax(maxV * 1.06), yTop = y + 6;
    var Y = function (v) { return yTop + PH - Math.min(Math.max(v, 0), ymax) / ymax * PH; };

    // era band + labels (estimated from MODIS | observed by VIIRS)
    var est = yearsAll.filter(function (a) { return a.estimated; });
    if (est.length) {
      var i0 = idx(est[0].y), i1 = idx(est[est.length - 1].y);
      body += '<rect x="' + (X0 + i0 * step).toFixed(1) + '" y="' + yTop + '" width="' + ((i1 - i0 + 1) * step).toFixed(1) + '" height="' + PH + '" fill="#F0F0F0"/>';
      body += text(X0 + (i0 + (i1 - i0 + 1) / 2) * step, yTop - 6, showH(model) ? 'harmonized: estimated from MODIS' : 'raw: MODIS detections', { size: 10, anchor: 'middle', fill: P.INK2 });
      var obs = yearsAll.filter(function (a) { return a.sensor === 'VIIRS'; });
      if (obs.length) body += text(X0 + (idx(obs[0].y) + (idx(obs[obs.length - 1].y) - idx(obs[0].y) + 1) / 2) * step, yTop - 6, showH(model) ? 'harmonized: observed by VIIRS' : 'raw: VIIRS detections', { size: 10, anchor: 'middle', fill: P.INK2 });
    } else {
      body += text((X0 + X1) / 2, yTop - 6, 'observed by VIIRS (no MODIS estimate in the selected dates)', { size: 10, anchor: 'middle', fill: P.INK2 });
    }
    // grid and axes
    var i, ticks = 5;
    for (i = 0; i <= ticks; i++) {
      var v = ymax * i / ticks, yy = Y(v);
      body += '<line x1="' + X0 + '" x2="' + X1 + '" y1="' + yy.toFixed(1) + '" y2="' + yy.toFixed(1) + '" stroke="' + P.GRID + '" stroke-width="1"/>';
      body += text(X0 - 6, yy + 4, axisLabel(v), { size: 10, anchor: 'end', fill: P.INK2 });
    }
    var lblEvery = n <= 14 ? 1 : (n <= 30 ? 2 : 5);
    for (i = 0; i < n; i++) {
      var xt = X0 + (i + 0.5) * step;
      body += '<line x1="' + xt.toFixed(1) + '" x2="' + xt.toFixed(1) + '" y1="' + (yTop + PH) + '" y2="' + (yTop + PH + 4) + '" stroke="#4D4D4D" stroke-width="1"/>';
      if (i % lblEvery === 0) body += text(xt, yTop + PH + 16, String(model.firstYear + i), { size: 10, anchor: 'middle' });
    }
    body += '<line x1="' + X0 + '" x2="' + X1 + '" y1="' + (yTop + PH) + '" y2="' + (yTop + PH) + '" stroke="#1A1A1A" stroke-width="1.2"/>';
    body += '<line x1="' + X0 + '" x2="' + X0 + '" y1="' + yTop + '" y2="' + (yTop + PH) + '" stroke="#1A1A1A" stroke-width="1.2"/>';
    body += '<text transform="translate(26,' + (yTop + PH / 2) + ') rotate(-90)" text-anchor="middle" font-family="' + C.FONT + '" font-size="11" fill="' + P.INK + '">' +
      esc('Hotspot detections per year' + (showH(model) && !showR(model) ? ' (VIIRS-equivalent)' : '')) + '</text>';
    body += text((X0 + X1) / 2, yTop + PH + 32, 'Calendar year (UTC)', { size: 10.5, anchor: 'middle', fill: P.INK2 });
    // sensor change line
    if (model.changeYear !== null && model.changeYear > model.firstYear) {
      var xc = X0 + idx(model.changeYear) * step;
      body += '<line x1="' + xc.toFixed(1) + '" x2="' + xc.toFixed(1) + '" y1="' + yTop + '" y2="' + (yTop + PH) + '" stroke="#1A1A1A" stroke-width="1.2" stroke-dasharray="5 3"/>';
      body += text(xc + 4, yTop + 12, 'sensor change: MODIS → VIIRS', { size: 10, weight: 700, halo: true });
      if (showH(model) && showR(model)) body += text(xc + 4, yTop + 25, 'from here VIIRS counts with weight 1: raw = harmonized', { size: 9.5, fill: P.INK2, halo: true });
    }

    // series ---------------------------------------------------------------------------------------------------------------------------
    function connectors(vals, color, sensorKey) {
      var s = '', prev = null;
      yearsAll.forEach(function (a) {
        var val = vals(a);
        if (a.status !== 'complete' || val === null) { prev = null; return; }
        if (prev) {
          var gap = a.y - prev.a.y, change = sensorKey && a.sensor !== prev.a.sensor;
          s += lineSeg(cx(prev.a.y), Y(prev.v), cx(a.y), Y(val), color, 1.8, change ? '1.5 4' : (gap > 1 ? '5 3' : null));
        }
        prev = { a: a, v: val };
      });
      return s;
    }
    if (showH(model)) {
      yearsAll.forEach(function (a) {                                          // 80 % ranges of estimated complete years
        if (!a.range) return;
        var x = cx(a.y), yl = Y(a.range.lo), yh = isFinite(a.range.hi) ? Y(a.range.hi) : yTop;
        body += lineSeg(x, yl, x, yh, RANGE, 2) + lineSeg(x - 3.5, yl, x + 3.5, yl, RANGE, 2) + lineSeg(x - 3.5, yh, x + 3.5, yh, RANGE, 2);
      });
      var sh = model.stats.harmonized;
      if (sh.ok) body += lineSeg(cx(sh.years[0]), Y(T.lineAt(sh, sh.years[0])), cx(sh.years[sh.years.length - 1]), Y(T.lineAt(sh, sh.years[sh.years.length - 1])), BLUE_D, 1.6, '7 4');
      body += connectors(function (a) { return a.harmonized; }, BLUE, false);
    }
    if (showR(model)) {
      var sr = model.stats.raw;
      if (sr.ok) body += lineSeg(cx(sr.years[0]), Y(T.lineAt(sr, sr.years[0])), cx(sr.years[sr.years.length - 1]), Y(T.lineAt(sr, sr.years[sr.years.length - 1])), ORANGE_D, 1.6, '2 4');
      body += connectors(function (a) { return a.raw; }, ORANGE, true);
    }
    var endPts = { h: null, r: null };
    yearsAll.forEach(function (a) {
      var done = a.status === 'complete', g = '';
      if (showH(model) && a.harmonized !== null) { g += marker('circle', cx(a.y), Y(a.harmonized), BLUE, done); endPts.h = { x: cx(a.y), y: Y(a.harmonized) }; }
      if (showR(model) && a.raw !== null) { g += marker(a.sensor === 'MODIS' ? 'square' : 'triangle', cx(a.y), Y(a.raw), ORANGE, done); endPts.r = { x: cx(a.y), y: Y(a.raw) }; }
      body += '<g class="tr-year" data-y="' + a.y + '"><title>' + esc(yearTip(model, a.y)) + '</title>' +
        '<rect x="' + (X0 + idx(a.y) * step).toFixed(1) + '" y="' + yTop + '" width="' + step.toFixed(1) + '" height="' + PH + '" fill="#FFFFFF" fill-opacity="0"/>' + g + '</g>';
    });
    // direct labels at the right end
    var labs = [];
    if (showH(model) && endPts.h) labs.push({ y: endPts.h.y, lines: ['Harmonized', '(VIIRS-equivalent)'], color: BLUE_D });
    if (showR(model) && endPts.r) labs.push({ y: endPts.r.y, lines: ['Raw, as detected', 'by each sensor'], color: ORANGE_D });
    labs.sort(function (p, q) { return p.y - q.y; });
    if (labs.length === 2 && labs[1].y - labs[0].y < 30) { var mid = (labs[0].y + labs[1].y) / 2; labs[0].y = mid - 16; labs[1].y = mid + 16; }
    labs.forEach(function (l) {
      body += text(X1 + 8, l.y - 2, l.lines[0], { size: 10.5, weight: 700, fill: l.color });
      body += text(X1 + 8, l.y + 11, l.lines[1], { size: 10, fill: P.INK2 });
    });

    // legend ----------------------------------------------------------------------------------------------------------------------------
    var ly = yTop + PH + 52, items = [];
    if (showH(model)) {
      items.push({ draw: function (x, yv) { return marker('circle', x + 6, yv, BLUE, true); }, lbl: 'Harmonized, complete year (used in the slope)' });
      items.push({ draw: function (x, yv) { return marker('circle', x + 6, yv, BLUE, false); }, lbl: 'Year left out of the slopes (incomplete or provisional)' });
      if (yearsAll.some(function (a) { return a.range; })) items.push({ draw: function (x, yv) { return lineSeg(x + 6, yv - 5, x + 6, yv + 5, RANGE, 2) + lineSeg(x + 2.5, yv - 5, x + 9.5, yv - 5, RANGE, 2) + lineSeg(x + 2.5, yv + 5, x + 9.5, yv + 5, RANGE, 2); }, lbl: '80 % range of the harmonization (estimated years)' });
      if (model.stats.harmonized.ok) items.push({ draw: function (x, yv) { return lineSeg(x, yv, x + 13, yv, BLUE_D, 1.6, '5 3'); }, lbl: 'Sen line of the harmonized series' });
    }
    if (showR(model)) {
      if (yearsAll.some(function (a) { return a.sensor === 'MODIS' && a.raw !== null; })) items.push({ draw: function (x, yv) { return marker('square', x + 6, yv, ORANGE, true); }, lbl: 'Raw MODIS (until Dec 2011)' });
      if (yearsAll.some(function (a) { return a.sensor === 'VIIRS' && a.raw !== null; })) items.push({ draw: function (x, yv) { return marker('triangle', x + 6, yv, ORANGE, true); }, lbl: 'Raw VIIRS (from Jan 2012)' });
      if (model.stats.raw.ok) items.push({ draw: function (x, yv) { return lineSeg(x, yv, x + 13, yv, ORANGE_D, 1.6, '2 4'); }, lbl: 'Sen line of the raw series (two sensors)' });
    }
    var colW = 396;
    items.forEach(function (it, k) {
      var x = 24 + (k % 2) * colW, yv = ly + Math.floor(k / 2) * 20;
      body += it.draw(x, yv) + text(x + 20, yv + 4, it.lbl, { size: 10.5 });
    });
    y = ly + Math.ceil(items.length / 2) * 20 + 10;
    if (chartOnly) {
      var Hc = Math.ceil(y + 2);
      var anyc = d.rows.filter(function (r) { return r.ok; })[0];
      return { svg: C.frame({ w: W, h: Hc, idp: idp, title: title, desc: 'Line chart of the yearly hotspot detections of ' + d.aoi + ' from ' + model.firstYear + ' to ' + model.lastYear +
        ', harmonized (VIIRS-equivalent) and raw as detected by each sensor. ' + (anyc ? anyc.text + ' ' : '') + cap(model.label) + '. The yearly numbers are also given in a table below the figure.', body: body }), w: W, h: Hc, idp: idp };
    }

    // slopes -------------------------------------------------------------------------------------------------------------------------------
    body += text(24, y, d.headline, { size: 12, weight: 700 }); y += 6;
    d.rows.forEach(function (r) {
      var t = C.textLines(44, y + 12, r.text, 118, { size: 11, lineHeight: 14 });
      var sw = r.key === 'raw' ? marker('triangle', 31, y + 8, ORANGE, true) : marker('circle', 31, y + 8, BLUE, true);
      body += sw + t.svg;
      y += t.height + 6;
    });
    if (d.excluded.length) {
      var ex = C.textLines(24, y + 12, 'Years left out of the slopes: ' + d.excluded.join('; ') + '.', 128, { size: 10.5, fill: P.INK2, lineHeight: 13 });
      body += ex.svg; y += ex.height + 6;
    }
    var mt = C.textLines(24, y + 12, d.method, 128, { size: 10.5, fill: P.INK2, lineHeight: 13 });
    body += mt.svg; y += mt.height + 12;
    body += text(24, y, 'Notes', { size: 11, weight: 700 }); y += 4;
    d.notes.forEach(function (nn) {
      var t = C.textLines(32, y + 12, nn, 136, { size: 10, fill: P.INK2, lineHeight: 12.5 });
      body += '<circle cx="27" cy="' + (y + 8.5) + '" r="1.6" fill="' + P.INK2 + '"/>' + t.svg; y += t.height + 4;
    });
    var ft = C.footer(model, W, y + 8);
    body += ft.svg;
    var H = Math.ceil(y + 8 + ft.height + 14);
    var any = d.rows.filter(function (r) { return r.ok; })[0];
    var desc = 'Line chart of the yearly hotspot detections of ' + d.aoi + ' from ' + model.firstYear + ' to ' + model.lastYear + ', harmonized (VIIRS-equivalent) and raw as detected by each sensor. ' +
      (any ? any.text + ' ' : '') + cap(model.label) + '. The yearly numbers are also given in a table below the figure.';
    return { svg: C.frame({ w: W, h: H, idp: idp, title: title, desc: desc, body: body }), w: W, h: H, idp: idp };
  }

  return { draw: draw, describe: describe, yearTip: yearTip, rowText: rowText, W: W };
});
