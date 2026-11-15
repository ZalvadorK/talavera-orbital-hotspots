/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * graficos-vistas.js - SVG of the two daily views (extras of ADR-0010), built as strings with inline attributes
 * (so they export to PNG exactly like the calendar):
 *   drawSeason(model, sm)  D2: cumulative detections since the start of the fire year vs the p10-p90 envelope + median
 *   drawDaily(model, km)   K3: typical daily activity (31-day smoothing) with the FWHM season dates
 * sm / km come from graficos-modelo.js. Works in the browser (window.FireChartsViews) and in Node.
 */
(function (root, factory) {
  'use strict';
  var req = (typeof module === 'object' && typeof require === 'function');
  var P = req ? require('./calendario-paleta.js') : root.FirePalette;
  var M = req ? require('./calendario-modelo.js') : root.FireCalendarModel;
  var C = req ? require('./graficos.js') : root.FireCharts;
  var FM = req ? require('./marca.js') : root.FireMark;
  var api = factory(P, M, C, FM);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireChartsViews = api;
})(typeof window !== 'undefined' ? window : globalThis, function (P, M, C, FM) {
  'use strict';

  var W = 840, X0 = 84, X1 = 800, PW = X1 - X0, PH = 330;
  var uid = 0, text = C.text;

  function niceMax(v) {
    if (!(v > 0)) return 1;
    var e = Math.pow(10, Math.floor(Math.log10(v))), f = v / e;
    var nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return nf * e;
  }
  function fmt(x) { return FM.fmtInt(x); }

  function header(model, title, sub, y0) {
    var b = '', ty = 28;
    if (model.synthetic) { b += C.synthBanner(model, 24, 8); ty = 54; }
    var tl = C.textLines(24, ty, title, 62, { size: 18, weight: 700, lineHeight: 22 });
    b += tl.svg;
    var sl = C.textLines(24, ty + tl.height + 2, sub, 130, { size: 12, fill: P.INK2, lineHeight: 15 });
    b += sl.svg;
    return { svg: b, y: ty + tl.height + 2 + sl.height + 8 };
  }

  function axes(sm, slots, yTop, ymax, yLabel) {
    var b = '', n = slots.length, i, t;
    var ticks = 5;
    for (i = 0; i <= ticks; i++) {
      var v = ymax * i / ticks, y = yTop + PH - (v / ymax) * PH;
      b += '<line x1="' + X0 + '" x2="' + X1 + '" y1="' + y + '" y2="' + y + '" stroke="' + P.GRID + '" stroke-width="1"/>';
      b += text(X0 - 6, y + 4, v >= 1000 ? (v / 1000) + 'k' : (v % 1 ? v.toFixed(1) : String(v)), { size: 10, anchor: 'end', fill: P.INK2 });
    }
    for (i = 0; i < n; i++) {
      if (slots[i].d === 1) {
        var x = X0 + i / (n - 1) * PW;
        b += '<line x1="' + x + '" x2="' + x + '" y1="' + yTop + '" y2="' + (yTop + PH + 5) + '" stroke="' + (i === 0 ? '#4D4D4D' : P.GRID) + '" stroke-width="1"/>';
        b += text(x + 3, yTop + PH + 17, M.MON3[slots[i].m - 1], { size: 10.5, fill: P.INK });
      }
    }
    b += '<line x1="' + X0 + '" x2="' + X1 + '" y1="' + (yTop + PH) + '" y2="' + (yTop + PH) + '" stroke="#1A1A1A" stroke-width="1.2"/>';
    b += '<line x1="' + X0 + '" x2="' + X0 + '" y1="' + yTop + '" y2="' + (yTop + PH) + '" stroke="#1A1A1A" stroke-width="1.2"/>';
    b += '<text transform="translate(24,' + (yTop + PH / 2) + ') rotate(-90)" text-anchor="middle" font-family="' + C.FONT + '" font-size="11" fill="' + P.INK + '">' + C.esc(yLabel) + '</text>';
    return b;
  }

  function finish(model, body, yEnd, notes, title, desc) {
    var idp = 'fv' + (++uid) + '-', ny = yEnd + 12;
    body += text(24, ny, 'Notes', { size: 11, weight: 700 }); ny += 4;
    notes.forEach(function (n) {
      var t = C.textLines(32, ny + 12, n, 136, { size: 10, fill: P.INK2, lineHeight: 12.5 });
      body += '<circle cx="27" cy="' + (ny + 8.5) + '" r="1.6" fill="' + P.INK2 + '"/>' + t.svg; ny += t.height + 4;
    });
    var ft = C.footer(model, W, ny + 8); body += ft.svg;
    var H = Math.ceil(ny + 8 + ft.height + 14);
    return { svg: C.frame({ w: W, h: H, idp: idp, title: title, desc: desc, body: body }), w: W, h: H, idp: idp };
  }

  // ------------------------------------------------------------------ D2
  function drawSeason(model, sm) {
    var aoi = (model.aoi && model.aoi.name) || 'Selected area';
    var title = aoi + ' — season so far, fire year ' + sm.evalLabel;
    var sub = 'Cumulative ' + M.UNIT + ' since the start of the fire year (' + M.MON3[sm.startMonth - 1] + ' 1, the month after the quietest month) against the ' + sm.baseLabel + ' base, this year excluded.';
    var h = header(model, title, sub);
    var body = h.svg, y = h.y;
    var t1 = C.textLines(24, y + 10, sm.unusualText, 120, { size: 11.5, weight: 700, lineHeight: 14 }); body += t1.svg; y += t1.height + 2;
    var t2 = C.textLines(24, y + 10, (sm.current ? 'To ' + sm.asOfText + ' (last data ' + sm.asOf + (sm.prov[sm.lastSlot] ? ', provisional' : '') + '): ' : 'Full year: ') +
      fmt(sm.value) + ' detections, ' + sm.ratioText + '.', 120, { size: 11, lineHeight: 14 }); body += t2.svg; y += t2.height + 14;
    var yTop = y + 6, n = sm.slots.length;
    var ymax = niceMax(Math.max(sm.p90[n - 1], sm.cum[sm.lastSlot] || 0) * 1.05);
    body += axes(sm, sm.slots, yTop, ymax, 'Cumulative VIIRS-equivalent detections');
    function X(i) { return X0 + i / (n - 1) * PW; }
    function Y(v) { return yTop + PH - Math.min(v, ymax) / ymax * PH; }
    var up = [], dn = [], i;
    for (i = 0; i < n; i++) { up.push(X(i).toFixed(1) + ',' + Y(sm.p90[i]).toFixed(1)); dn.push(X(i).toFixed(1) + ',' + Y(sm.p10[i]).toFixed(1)); }
    body += '<polygon points="' + up.join(' ') + ' ' + dn.slice().reverse().join(' ') + '" fill="#D9D9D9" fill-opacity="0.75" stroke="none"/>';
    body += '<polyline points="' + up.join(' ') + '" fill="none" stroke="#8C8C8C" stroke-width="1" stroke-dasharray="4 3"/>';
    body += '<polyline points="' + dn.join(' ') + '" fill="none" stroke="#8C8C8C" stroke-width="1" stroke-dasharray="4 3"/>';
    var med = []; for (i = 0; i < n; i++) med.push(X(i).toFixed(1) + ',' + Y(sm.median[i]).toFixed(1));
    body += '<polyline points="' + med.join(' ') + '" fill="none" stroke="#4D4D4D" stroke-width="1.8"/>';
    // evaluated year: solid black (standard) and dashed magenta (provisional)
    var seg = [], cur = null;
    for (i = 0; i <= sm.lastSlot; i++) {
      var pv = !!sm.prov[i];
      if (!cur || cur.prov !== pv) { if (cur) seg.push(cur); cur = { prov: pv, pts: (cur ? [cur.pts[cur.pts.length - 1]] : []) }; }
      cur.pts.push(X(i).toFixed(1) + ',' + Y(sm.cum[i]).toFixed(1));
    }
    if (cur) seg.push(cur);
    seg.forEach(function (s) {
      body += '<polyline points="' + s.pts.join(' ') + '" fill="none" stroke="' + (s.prov ? '#CC79A7' : '#000000') + '" stroke-width="' + (s.prov ? 3.4 : 2.6) + '"' + (s.prov ? ' stroke-dasharray="6 3"' : '') + ' stroke-linejoin="round"/>';
    });
    var ex = X(sm.lastSlot), ey = Y(sm.cum[sm.lastSlot]);
    body += '<circle cx="' + ex + '" cy="' + ey + '" r="5" fill="#FFFFFF" stroke="#000000" stroke-width="2"/>';
    var lx = ex > X1 - 150 ? ex - 8 : ex + 8, anc = ex > X1 - 150 ? 'end' : 'start';
    body += text(lx, ey - 10, fmt(sm.value) + ' on ' + sm.asOfText, { size: 11, weight: 700, anchor: anc, halo: true });
    if (sm.unusual.state === 'unusual') body += text(lx, ey - 24, 'Unusually active', { size: 11, weight: 700, anchor: anc, fill: '#7A3600', halo: true });
    // legend
    var ly = yTop + PH + 38;
    body += '<line x1="24" x2="54" y1="' + ly + '" y2="' + ly + '" stroke="#000000" stroke-width="2.6"/>' + text(60, ly + 4, 'This fire year (' + sm.evalLabel + ')', { size: 10.5 });
    body += '<line x1="250" x2="280" y1="' + ly + '" y2="' + ly + '" stroke="#CC79A7" stroke-width="3.4" stroke-dasharray="6 3"/>' + text(286, ly + 4, 'Provisional days (NRT)', { size: 10.5 });
    body += '<line x1="440" x2="470" y1="' + ly + '" y2="' + ly + '" stroke="#4D4D4D" stroke-width="1.8"/>' + text(476, ly + 4, 'Median of ' + sm.baseYears.length + ' base years', { size: 10.5 });
    body += '<rect x="640" y="' + (ly - 6) + '" width="30" height="12" fill="#D9D9D9" fill-opacity="0.75" stroke="#8C8C8C" stroke-dasharray="4 3"/>' + text(676, ly + 4, '10th–90th percentile', { size: 10.5 });
    // hover surface
    body += '<rect class="fc-hit" data-view="season" x="' + X0 + '" y="' + yTop + '" width="' + PW + '" height="' + PH + '" fill="#FFFFFF" fill-opacity="0" />';
    var notes = [
      'The fire year starts the month after the quietest month of a typical year (VIIRS ' + model.base.b2Label + ' medians), so a season is not split in two.',
      'Base: ' + sm.baseYears.length + ' complete fire years of standard VIIRS data (' + sm.baseLabel + '); months with outages, the partial January 2012 and near-real-time data never enter it. Envelope = type-6 10th and 90th percentiles per day.',
      '“Unusually active”: the cumulative total on this day is above the 90th percentile of the base on the same day (strict inequality; needs a base median of at least 5).',
      'Counts are satellite hotspot detections, not individual fires. Dates in UTC. Daily data are VIIRS only (from 2012).'
    ];
    model.notices.forEach(function (x) { if (x.id === 'synthetic') notes.push(x.text); });
    var desc = 'Line chart of cumulative detections through the fire year ' + sm.evalLabel + ' with a base envelope. ' + sm.unusualText;
    return finish(model, body, yTop + PH + 52, notes, title, desc);
  }

  function seasonTip(sm, i) {
    var sl = sm.slots[i], lines = [];
    if (i <= sm.lastSlot) lines.push({ k: 'v', t: fmt(sm.cum[i]) + ' cumulative detections (' + sm.evalLabel + (sm.prov[i] ? ', provisional' : '') + ')' });
    else lines.push({ k: 'p', t: 'No data yet for this day of ' + sm.evalLabel + '.' });
    lines.push({ k: 'kv', a: 'Base median', b: fmt(sm.median[i]) });
    lines.push({ k: 'kv', a: '10th–90th percentile', b: fmt(sm.p10[i]) + ' – ' + fmt(sm.p90[i]) });
    return { title: sm.evalLabel + ' to ' + sl.d + ' ' + M.MON3[sl.m - 1], lines: lines,
             aria: sl.d + ' ' + M.MON3[sl.m - 1] + ': ' + (i <= sm.lastSlot ? fmt(sm.cum[i]) + ' cumulative detections; ' : '') + 'base median ' + fmt(sm.median[i]) };
  }

  // ------------------------------------------------------------------ K3
  function drawDaily(model, km) {
    var aoi = (model.aoi && model.aoi.name) || 'Selected area';
    var title = aoi + ' — typical daily activity and season dates';
    var sub = 'Mean ' + M.UNIT + ' per day over ' + km.nYears + ' VIIRS years (' + km.baseLabel + '), smoothed with a 31-day moving average. Season dates = days at or above half of the peak (full width at half maximum).';
    var h = header(model, title, sub);
    var body = h.svg, y = h.y;
    var t1 = C.textLines(24, y + 10, km.text + ' (' + km.length + ' days).', 120, { size: 11.5, weight: 700, lineHeight: 14 }); body += t1.svg; y += t1.height + 14;
    var yTop = y + 6, n = km.slots.length;
    var ymax = niceMax(Math.max.apply(null, km.smooth) * 1.15);
    var yMeanMax = Math.max.apply(null, km.mean);
    if (yMeanMax > ymax) ymax = niceMax(yMeanMax * 1.05);
    body += axes(km, km.slots, yTop, ymax, 'Detections per day (VIIRS-equivalent)');
    function X(i) { return X0 + i / (n - 1) * PW; }
    function Y(v) { return yTop + PH - Math.min(v, ymax) / ymax * PH; }
    // FWHM window (may wrap around the ends of the fire year)
    var a = km.start, b = km.end;
    function band(i0, i1) { return '<rect x="' + X(i0) + '" y="' + yTop + '" width="' + Math.max(2, X(i1) - X(i0)) + '" height="' + PH + '" fill="#F0E442" fill-opacity="0.35" stroke="#7A3600" stroke-width="1" stroke-dasharray="5 3"/>'; }
    if (a <= b) body += band(a, b); else { body += band(a, n - 1); body += band(0, b); }
    var mpts = [], spts = [], i;
    for (i = 0; i < n; i++) { mpts.push(X(i).toFixed(1) + ',' + Y(km.mean[i]).toFixed(1)); spts.push(X(i).toFixed(1) + ',' + Y(km.smooth[i]).toFixed(1)); }
    body += '<polyline points="' + mpts.join(' ') + '" fill="none" stroke="#8C8C8C" stroke-width="0.9"/>';
    body += '<polyline points="' + spts.join(' ') + '" fill="none" stroke="#000000" stroke-width="2.6" stroke-linejoin="round"/>';
    body += '<line x1="' + X0 + '" x2="' + X1 + '" y1="' + Y(km.threshold) + '" y2="' + Y(km.threshold) + '" stroke="#7A3600" stroke-width="1" stroke-dasharray="2 3"/>';
    body += text(X1 - 4, Y(km.threshold) - 4, 'half of the peak', { size: 9.5, anchor: 'end', fill: '#7A3600' });
    [[a, 'start ' + km.startText, 'end'], [km.peak, 'peak ' + km.peakText, 'middle'], [b, 'end ' + km.endText, 'start']].forEach(function (p) {
      var px = X(p[0]), py = Y(km.smooth[p[0]]);
      body += '<circle cx="' + px + '" cy="' + py + '" r="4.2" fill="#FFFFFF" stroke="#000000" stroke-width="2"/>';
      body += text(p[2] === 'end' ? px - 7 : (p[2] === 'start' ? px + 7 : px), p[2] === 'middle' ? py - 10 : py - 8, p[1], { size: 11, weight: 700, anchor: p[2], halo: true });
    });
    var ly = yTop + PH + 38;
    body += '<line x1="24" x2="54" y1="' + ly + '" y2="' + ly + '" stroke="#000000" stroke-width="2.6"/>' + text(60, ly + 4, '31-day smoothed mean', { size: 10.5 });
    body += '<line x1="250" x2="280" y1="' + ly + '" y2="' + ly + '" stroke="#8C8C8C" stroke-width="1"/>' + text(286, ly + 4, 'Daily mean (unsmoothed)', { size: 10.5 });
    body += '<rect x="450" y="' + (ly - 6) + '" width="30" height="12" fill="#F0E442" fill-opacity="0.35" stroke="#7A3600" stroke-dasharray="5 3"/>' + text(486, ly + 4, 'Season window (FWHM)', { size: 10.5 });
    body += '<rect class="fc-hit" data-view="daily" x="' + X0 + '" y="' + yTop + '" width="' + PW + '" height="' + PH + '" fill="#FFFFFF" fill-opacity="0" />';
    var notes = [
      'If an area has two seasons, only the main one (around the highest peak) is reported. Smoothing and the half-maximum rule are fixed (31 days, 50 %).',
      'Computed on the VIIRS base only (standard data; partial January 2012, outage months and near-real-time data excluded), so it does not depend on the MODIS harmonisation.',
      'Counts are satellite hotspot detections, not individual fires. Dates in UTC; days are shown from the start of the fire year (' + M.MON3[km.startMonth - 1] + ' 1).'
    ];
    model.notices.forEach(function (x) { if (x.id === 'synthetic') notes.push(x.text); });
    return finish(model, body, yTop + PH + 52, notes, title, 'Line chart of the typical daily activity with the season window. ' + km.text);
  }

  function dailyTip(km, i) {
    var sl = km.slots[i];
    return { title: sl.d + ' ' + M.MON3[sl.m - 1], aria: sl.d + ' ' + M.MON3[sl.m - 1] + ': smoothed mean ' + km.smooth[i].toFixed(1) + ' per day',
             lines: [{ k: 'v', t: km.smooth[i].toFixed(1) + ' detections per day (31-day mean)' }, { k: 'kv', a: 'Unsmoothed mean', b: km.mean[i].toFixed(1) },
                     { k: 'p', t: i >= Math.min(km.start, km.end) && ((km.start <= km.end && i >= km.start && i <= km.end) || (km.start > km.end && (i >= km.start || i <= km.end))) ? 'Inside the season window.' : 'Outside the season window.' }] };
  }

  return { drawSeason: drawSeason, drawDaily: drawDaily, seasonTip: seasonTip, dailyTip: dailyTip, PW: PW, X0: X0 };
});
