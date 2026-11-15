/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * calendario.js - harmonised fire-activity calendar (year x month), A4 portrait.
 *
 *   window.FireCalendar.render(el, input)        draw (or redraw) the calendar into el; handles loading / empty / error / ready
 *   window.FireCalendar.exportPNG(el)  -> Promise<Blob>   PNG of the figure on screen, with "SI-generated (AI)" and "Data: NASA FIRMS"
 *   window.FireCalendar.renderToString(input)    SVG string (no DOM; used by tests)
 *   window.FireCalendar.buildModel(input)        pure model (marks, base, seasons, ranking)
 *
 * Input contract: see app/tests/calendario-INTERFAZ.md. Marks follow ADR-0006 (marca.js); the rest ADR-0010.
 * The figure is SVG with inline attributes only, so it exports to PNG without style sheets.
 */
(function (root, factory) {
  'use strict';
  var req = (typeof module === 'object' && typeof require === 'function');
  var FM = req ? require('./marca.js') : root.FireMark;
  var M = req ? require('./calendario-modelo.js') : root.FireCalendarModel;
  var P = req ? require('./calendario-paleta.js') : root.FirePalette;
  var C = req ? require('./graficos.js') : root.FireCharts;
  var GM = null, FV = null;
  try { GM = req ? require('./graficos-modelo.js') : root.FireChartsModel; FV = req ? require('./graficos-vistas.js') : root.FireChartsViews; } catch (e) { GM = null; FV = null; }
  var api = factory(FM, M, P, C, root, GM, FV);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireCalendar = api;
})(typeof window !== 'undefined' ? window : globalThis, function (FM, M, P, C, root, GM, FV) {
  'use strict';

  var uid = 0;
  var G = { w: 840, ml: 24, labW: 58, cw: 44, ch: 24 };
  G.x0 = G.ml + G.labW + 2;
  G.gridW = 12 * G.cw;
  G.rx = G.x0 + G.gridW + 14;
  G.rw = G.w - G.ml - G.rx;
  G.rankW = 46;                                       // rank column: "#12" and, for a year built from MODIS estimates, its label under it
  // Tag of a ranked year that holds MODIS estimates (model row.quality): the ranking never mixes estimated and observed years silently.
  var RANK_TAG = { indicative: 'indicative', 'not-tested': 'not tested', reliable: 'reliable est.' };

  var esc = C.esc, text = C.text;

  // ------------------------------------------------------------------------------------------- glyphs
  function glyph(kind, dir, cx, cy, s) {
    var pts;
    if (dir === 'high') pts = [[cx, cy - s], [cx - s, cy + s * 0.8], [cx + s, cy + s * 0.8]];
    else if (dir === 'low') pts = [[cx, cy + s], [cx - s, cy - s * 0.8], [cx + s, cy - s * 0.8]];
    else pts = [[cx, cy - s], [cx + s, cy], [cx, cy + s], [cx - s, cy]];
    var d = pts.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ');
    var col = dir === 'high' ? P.STATES.unusual_high.fill : (dir === 'low' ? P.STATES.unusual_low.fill : '#1A1A1A');
    if (kind === 'unusual') {
      return '<polygon points="' + d + '" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="3" stroke-linejoin="round"/>' +
             '<polygon points="' + d + '" fill="' + col + '" stroke="#1A1A1A" stroke-width="0.9" stroke-linejoin="round"/>';
    }
    return '<polygon points="' + d + '" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="3.4" stroke-linejoin="round"/>' +
           '<polygon points="' + d + '" fill="#FFFFFF" stroke="' + col + '" stroke-width="1.7" stroke-linejoin="round"/>';
  }

  // ------------------------------------------------------------------------------------------- colour logic
  function countT(v, vmax) { return vmax > 0 ? Math.log10(1 + v) / Math.log10(1 + vmax) : 0; }

  function cellLook(c, model) {
    var mode = model.opts.mode;
    var o = { fill: '#FFFFFF', pat: null, label: '' };
    if (c.status !== 'ok') { o.pat = 'nd'; return o; }
    if (mode === 'counts') {
      if (c.value === 0) { o.fill = '#FFFFFF'; o.pat = c.incomplete ? 'in' : 'zr'; o.label = c.incomplete ? '' : '0'; return o; }
      o.fill = P.seqColor(countT(c.value, model.vmax));
    } else {
      if (c.pct === null) { o.fill = P.STATES.insufficient.fill; o.pat = 'sf'; o.label = 'n/a'; return o; }
      o.fill = P.divColor(c.pct / 100);
      o.label = 'p' + Math.round(c.pct);
    }
    return o;
  }

  function lightVariant(fill) { return P.luminance(fill) < 0.18 ? 'l' : 'd'; }

  // ------------------------------------------------------------------------------------------- one cell
  function cellSvg(c, g, model, idp, rowIdx, col) {
    var look = cellLook(c, model);
    var x = g.x, y = g.y, w = g.w, h = g.h;
    var s = '<g class="fc-cell" data-k="' + c.key + '" data-r="' + rowIdx + '" data-c="' + col + '">';
    s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="' + look.fill + '" stroke="#FFFFFF" stroke-width="1"/>';
    var v = lightVariant(look.fill), ink = P.inkOn(look.fill);
    if (c.status === 'ok' && c.estimated) {
      s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="url(#' + idp + (c.tramo === 'T' ? 'hT' : 'hA') + v + ')"/>';
    }
    if (look.pat) {
      var pv = look.fill === '#FFFFFF' || look.fill === P.STATES.insufficient.fill ? 'd' : v;
      s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="url(#' + idp + look.pat + pv + ')"/>';
    }
    if (c.status === 'ok' && c.incomplete && look.pat !== 'in' && !c.estimated) {
      s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="url(#' + idp + 'in' + v + ')"/>';
    }
    // borders (never colour alone); line colour chosen for contrast with the fill
    var bx = x + 1.5, by = y + 1.5, bw = w - 3, bh = h - 3;
    if (c.status === 'ok') {
      var ov = P.OVERLAYS, bc = ink;
      if (c.tramo === 'T') s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="none" stroke="' + bc + '" stroke-width="' + ov.lower_confidence.width + '" stroke-dasharray="' + ov.lower_confidence.dash + '"/>';
      else if (c.estimated) s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="none" stroke="' + bc + '" stroke-width="1"/>';
      if (c.incomplete) s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="none" stroke="' + bc + '" stroke-width="' + ov.incomplete.width + '" stroke-dasharray="' + ov.incomplete.dash + '"/>';
      if (c.provisional) s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="none" stroke="' + ov.provisional.stroke + '" stroke-width="' + ov.provisional.width + '" stroke-dasharray="' + ov.provisional.dash + '"/>';
    } else {
      s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="none" stroke="#6B6B6B" stroke-width="1"/>';
    }
    // value text
    var shown = (c.status !== 'ok') ? '' : (model.opts.mode === 'counts' ? (c.value === 0 ? '0' : M.compact(c.value, c.estimated)) : look.label);
    if (shown) {
      var hasG = !!(c.mark && (c.mark.state === 'unusual' || c.mark.state === 'possibly'));
      s += '<text x="' + (x + w / 2 - (hasG ? 3 : 0)) + '" y="' + (y + h / 2 + 4.4) + '" text-anchor="middle" font-family="' + C.FONT + '" font-size="10" fill="' + ink + '"' +
           ' stroke="' + look.fill + '" stroke-width="2.6" paint-order="stroke" stroke-linejoin="round">' + esc(shown) + '</text>';
    }
    // mark glyph, provisional P, partial half
    if (c.mark && (c.mark.state === 'unusual' || c.mark.state === 'possibly')) {
      s += glyph(c.mark.state, c.mark.dir, x + w - 7, y + 7, 3.9);
    }
    if (c.provisional && c.status === 'ok') s += text(x + w - 4.5, y + h - 3.5, 'P', { size: 8.5, weight: 800, anchor: 'end', fill: '#1A1A1A', halo: true });
    if (c.partial) s += text(x + 3.5, y + 9.5, '½', { size: 9, weight: 800, fill: '#1A1A1A', halo: true });
    return s + '</g>';
  }

  // ------------------------------------------------------------------------------------------- legend pieces
  function swatch(x, y, o, idp) {
    var s = '<rect x="' + x + '" y="' + y + '" width="26" height="15" fill="' + (o.fill || '#CFCFCF') + '" stroke="#FFFFFF" stroke-width="1"/>';
    if (o.pat) s += '<rect x="' + x + '" y="' + y + '" width="26" height="15" fill="url(#' + idp + o.pat + (o.light ? 'l' : 'd') + ')"/>';
    var bx = x + 1.5, by = y + 1.5;
    if (o.border) s += '<rect x="' + bx + '" y="' + by + '" width="23" height="12" fill="none" stroke="' + o.border + '" stroke-width="' + (o.bw || 1) + '"' + (o.dash ? ' stroke-dasharray="' + o.dash + '"' : '') + '/>';
    if (o.letter) s += text(x + (o.lx || 22), y + 12, o.letter, { size: 9, weight: 800, anchor: 'end', halo: true });
    if (o.glyph) s += o.glyph;
    return s;
  }

  function presence(model) {
    var f = { observed: false, T: false, TA: false, zero: false, inc: false, nodata: false, insuff: false, prov: false, partial: false,
              high: false, low: false, possU: false, possM: false };
    Object.keys(model.cells).forEach(function (ks) {
      var c = model.cells[ks];
      if (c.status !== 'ok') { f.nodata = true; return; }
      if (c.tramo === 'T') f.T = true; else if (c.tramo === 'TA') f.TA = true; else f.observed = true;
      if (c.value === 0 && !c.incomplete) f.zero = true;
      if (c.incomplete) f.inc = true;
      if (c.provisional) f.prov = true;
      if (c.partial) f.partial = true;
      if (c.mark && c.mark.state === 'insufficient') f.insuff = true;
      if (c.mark && c.mark.state === 'unusual') { if (c.mark.dir === 'high') f.high = true; else f.low = true; }
      if (c.mark && c.mark.state === 'possibly') { if (c.mark.dir === 'mixed') f.possM = true; else f.possU = true; }
    });
    if (model.opts.mode === 'anomaly') f.insuff = true;
    // cells without any rows inside the range also count as no data
    return f;
  }

  function legendSvg(model, idp, y) {
    var s = '', f = presence(model), mode = model.opts.mode;
    // colour bar
    var bx = G.ml, bw = 300, bh = 12;
    s += text(bx, y + 11, mode === 'counts' ? 'Hotspot detections per month (VIIRS-equivalent, log scale)' : 'Percentile of the same month in ' + model.base.label + ' (this year excluded)', { size: 11, weight: 700 });
    var gid = idp + 'grad';
    var stops = mode === 'counts' ? P.SEQ : P.DIV;
    s += '<defs><linearGradient id="' + gid + '" x1="0" x2="1" y1="0" y2="0">' + stops.map(function (c, i) {
      return '<stop offset="' + (i / (stops.length - 1)).toFixed(3) + '" stop-color="' + c + '"/>'; }).join('') + '</linearGradient></defs>';
    var by = y + 18;
    s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="url(#' + gid + ')" stroke="#4D4D4D" stroke-width="0.8"/>';
    var ticks = [];
    if (mode === 'counts') {
      var vmax = model.vmax;
      ticks.push({ t: 0, l: '0' });
      for (var p = 1; p <= vmax; p *= 10) ticks.push({ t: countT(p, vmax), l: p >= 1000 ? (p / 1000) + 'k' : String(p) });
      ticks.push({ t: 1, l: M.compact(vmax, false) });
    } else {
      [0, 10, 25, 50, 75, 90, 100].forEach(function (q) { ticks.push({ t: q / 100, l: String(q) }); });
    }
    var lastX = -99;
    ticks.forEach(function (tk, i) {
      var tx = bx + tk.t * bw;
      s += '<line x1="' + tx + '" x2="' + tx + '" y1="' + (by + bh) + '" y2="' + (by + bh + 4) + '" stroke="#4D4D4D" stroke-width="1"/>';
      if (tx - lastX >= 22 || i === ticks.length - 1) { s += text(tx, by + bh + 15, tk.l, { size: 9.5, anchor: 'middle', fill: P.INK2 }); lastX = tx; }
    });
    // state swatches (only those present)
    var items = [];
    items.push({ lbl: 'Observed by VIIRS (S-NPP, NOAA-20)', o: { fill: '#9B9476' } });
    if (f.TA) items.push({ lbl: 'Estimated from MODIS · Terra+Aqua', o: { fill: '#9B9476', pat: 'hA', border: '#000000', bw: 1 } });
    if (f.T) items.push({ lbl: 'Estimated · Terra only (lower confidence)', o: { fill: '#9B9476', pat: 'hT', border: '#000000', bw: 2, dash: '6 2 1 2' } });
    if (f.zero && mode === 'counts') items.push({ lbl: '0 detected (not necessarily zero fire)', o: { fill: '#FFFFFF', pat: 'zr', border: '#6B6B6B' } });
    if (f.inc) items.push({ lbl: 'Incomplete (satellite outage): no mark', o: { fill: '#FFFFFF', pat: 'in', border: '#000000', bw: 2, dash: '2 2' } });
    if (f.nodata) items.push({ lbl: 'No data (not zero)', o: { fill: '#FFFFFF', pat: 'nd', border: '#6B6B6B' } });
    if (f.prov) items.push({ lbl: 'Provisional (near-real-time) · “P”', o: { fill: '#9B9476', border: '#CC79A7', bw: 3, dash: '5 3', letter: 'P' } });
    if (f.partial) items.push({ lbl: 'Partial month · “½”', o: { fill: '#9B9476', letter: '½', lx: 9 } });
    if (f.insuff) items.push({ lbl: 'Insufficient data (base median < 5)', o: { fill: P.STATES.insufficient.fill, pat: 'sf', border: '#B0B0B0' } });
    if (f.high) items.push({ lbl: 'Unusually high', g: 'high' });
    if (f.low) items.push({ lbl: 'Unusually low', g: 'low' });
    if (f.possU) items.push({ lbl: 'Possibly unusual (hollow marker)', g: 'possU' });
    if (f.possM) items.push({ lbl: 'Possibly unusual (either direction)', g: 'possM' });
    var cols = 3, colW = 264, iy = by + bh + 50, rowH = 22;
    s += text(G.ml, iy - 8, 'Cell states', { size: 11, weight: 700 });
    items.forEach(function (it, i) {
      var cx = G.ml + (i % cols) * colW, cy = iy + Math.floor(i / cols) * rowH;
      var o = it.o;
      if (it.g) {
        var gl = it.g === 'high' ? glyph('unusual', 'high', 13, 7.5, 4.6)
          : (it.g === 'low' ? glyph('unusual', 'low', 13, 7.5, 4.6)
          : (it.g === 'possU' ? glyph('possibly', 'high', 13, 7.5, 4.6) : glyph('possibly', 'mixed', 13, 7.5, 4.6)));
        o = { fill: '#CFCFCF', glyph: '<g transform="translate(' + cx + ',' + cy + ')">' + gl + '</g>' };
      }
      s += swatch(cx, cy, o, idp);
      s += text(cx + 33, cy + 12, it.lbl, { size: 10.5 });
    });
    var rows = Math.ceil(items.length / cols);
    return { svg: s, height: (iy - y) + rows * rowH + 4 };
  }

  // ------------------------------------------------------------------------------------------- header text
  function infoLines(model) {
    var out = [], se = model.season;
    if (se && se.core) {
      out.push({ t: 'Core fire season: ' + se.core.text + (se.extended ? ' · Extended season: ' + se.extended.text : '') + ' (typical year, VIIRS ' + se.baseLabel + ').', w: 700 });
    } else if (!se) out.push({ t: 'Fire season: not available (no VIIRS base).', w: 400 });
    if (model.opts.range) {
      var rg = model.opts.range, fk = rg.from === null ? model.firstKey : rg.from, tk = rg.to === null ? model.lastKey : rg.to;
      out.push({ t: 'Showing ' + M.MON3[fk % 12] + ' ' + Math.floor(fk / 12) + ' \u2013 ' + M.MON3[tk % 12] + ' ' + Math.floor(tk / 12) + '. Marks and seasons still use the whole series; ranks compare only the years shown.', w: 400 });
    }
    if (model.axis.reason) out.push({ t: model.axis.reason, w: 400 });
    if (model.mtd) {
      var c = model.cells[M.keyOf(model.mtd.y, model.mtd.m)];
      var mk = c && c.mark ? (c.mark.state === 'insufficient' ? 'insufficient data for a mark' : c.mark.label) : 'no mark';
      out.push({ t: 'Month to date, provisional (' + model.mtd.text + ' ' + model.mtd.y + ', last data ' + model.mtd.lastDate + '): ' + FM.fmtInt(model.mtd.value) + ' detections, ' +
        (c && c.base ? FM.ratioText(model.mtd.value, c.base.median, model.mtd.baseLabel) + ' for the same days' : 'no base') + ' — ' + mk + '.', w: 700 });
    }
    return out;
  }

  function noteLines(model) {
    var n = [];
    n.push('Counts are satellite hotspot detections, not individual fires or ground-reported incidents. Zero detections do not mean zero fire (clouds, smoke, timing).');
    n.push('Unusually high: above the 90th percentile of the same month in ' + model.base.label + ' (this year excluded); unusually low: below the 10th, only when the base median is at least 5. “Possibly unusual”: the answer depends on the harmonisation uncertainty (80 % range).' +
      (model.base.key === 'B1' ? ' Base B1 uses harmonised estimates as they are (their uncertainty is not propagated into the base).' : ''));
    n.push('Core fire season: the shortest run of months holding at least 50 % of the typical yearly detections; extended: at least 80 %. Year totals of estimated years carry the summed 80 % range (conservative).');
    model.notices.forEach(function (x) { n.push(x.text); });
    return n;
  }

  // ------------------------------------------------------------------------------------------- calendar figure
  function drawCalendar(model, o) {
    o = o || {};
    var idp = o.idp || ('fc' + (++uid) + '-');
    var body = '';
    var aoiName = (model.aoi && model.aoi.name) || 'Selected area';
    var title = aoiName + (model.aoi && model.aoi.country ? ' (' + (model.aoi.country === 'mexico' ? 'Mexico' : (model.aoi.country === 'argentina' ? 'Argentina' : model.aoi.country)) + ')' : '') + ' — fire-activity calendar';
    var ty = 28;
    if (model.synthetic) { body += C.synthBanner(model, G.ml, 8); ty = 54; }
    var tl = C.textLines(G.ml, ty, title, 62, { size: 18, weight: 700, lineHeight: 22 });
    body += tl.svg;
    var sub = model.opts.mode === 'counts'
      ? 'Monthly ' + M.UNIT + (model.useVm ? ' (all thermal anomalies)' : ' (vegetation fires only; static volcano/industry mask applied)') + ' · log colour scale'
      : 'Anomaly: percentile of each month against the same calendar month in ' + model.base.label + ' (this year excluded)' + (model.useVm ? ' · all thermal anomalies' : ' · vegetation fires only');
    var sl = C.textLines(G.ml, ty + tl.height + 2, sub, 132, { size: 12, fill: P.INK2, lineHeight: 15 });
    body += sl.svg;
    var y = ty + tl.height + 2 + sl.height + 4;
    infoLines(model).forEach(function (ln) {
      var t = C.textLines(G.ml, y + 10, ln.t, 112, { size: 11, weight: ln.w === 700 ? 600 : 400, lineHeight: 14 });
      body += t.svg; y += t.height + 2;
    });
    var yH = y + 18;                  // month header baseline
    var y0 = yH + 8;                  // first row top
    // header
    body += text(G.x0 - 6, yH, model.axis.used === 'fire' ? 'Fire year' : 'Year', { size: 10.5, weight: 700, anchor: 'end', fill: P.INK2 });
    model.colMonths.forEach(function (m, i) {
      body += text(G.x0 + i * G.cw + G.cw / 2, yH, M.MON3[m - 1], { size: 11, weight: 700, anchor: 'middle' });
    });
    // ranking header
    body += text(G.rx, yH - 12, 'Year total (rank)', { size: 10.5, weight: 700 });
    body += text(G.rx, yH, model.opts.mode === 'counts' ? 'VIIRS-equivalent detections' : 'VIIRS-eq. detections', { size: 9.5, fill: P.INK2 });
    // rows
    var maxTot = 0;
    model.rows.forEach(function (r) { var t = r.range ? r.range.hi : r.total; if (t > maxTot) maxTot = t; });
    var barX = G.rx + G.rankW + 4, barMax = G.rw - G.rankW - 4 - 34;
    model.rows.forEach(function (r, ri) {
      var ry = y0 + ri * G.ch;
      body += text(G.x0 - 6, ry + G.ch / 2 + 4, r.label, { size: 11, anchor: 'end', weight: r.complete ? 400 : 400, fill: r.complete ? P.INK : P.INK2 });
      r.slots.forEach(function (c, ci) {
        if (c.outside) return;
        body += cellSvg(c, { x: G.x0 + ci * G.cw, y: ry, w: G.cw, h: G.ch }, model, idp, ri, ci);
      });
      // ranking bar
      if (r.total > 0 || r.complete) {
        var bwid = maxTot > 0 ? Math.max(1, r.total / maxTot * barMax) : 1;
        var by2 = ry + 4, bh2 = G.ch - 8;
        if (r.complete) {
          body += '<rect x="' + barX + '" y="' + by2 + '" width="' + bwid.toFixed(1) + '" height="' + bh2 + '" fill="' + (r.flags.estimated ? '#7D7C78' : '#000000') + '"/>';
          if (r.flags.estimated) body += '<rect x="' + barX + '" y="' + by2 + '" width="' + bwid.toFixed(1) + '" height="' + bh2 + '" fill="url(#' + idp + 'hAl)"/>';
          if (r.range) {
            var xl = barX + r.range.lo / maxTot * barMax, xh = barX + r.range.hi / maxTot * barMax, ym = by2 + bh2 / 2;
            body += '<line x1="' + xl.toFixed(1) + '" x2="' + xh.toFixed(1) + '" y1="' + ym + '" y2="' + ym + '" stroke="#CC79A7" stroke-width="2"/>' +
                    '<line x1="' + xl.toFixed(1) + '" x2="' + xl.toFixed(1) + '" y1="' + (ym - 4) + '" y2="' + (ym + 4) + '" stroke="#CC79A7" stroke-width="2"/>' +
                    '<line x1="' + xh.toFixed(1) + '" x2="' + xh.toFixed(1) + '" y1="' + (ym - 4) + '" y2="' + (ym + 4) + '" stroke="#CC79A7" stroke-width="2"/>';
          }
          var tag = RANK_TAG[r.quality];
          if (tag) {                                   // two lines: the rank, and under it the label of the estimated year
            body += text(G.rx + G.rankW, ry + 10.5, '#' + r.rank, { size: 10, anchor: 'end', weight: r.rank <= 3 ? 800 : 400 });
            body += text(G.rx + G.rankW, ry + 20.5, tag, { size: 8.5, anchor: 'end', weight: 600, fill: P.INK2 });
          } else body += text(G.rx + G.rankW, ry + G.ch / 2 + 3.6, '#' + r.rank, { size: 10, anchor: 'end', weight: r.rank <= 3 ? 800 : 400 });
          var endX = barX + (r.range ? Math.max(bwid, r.range.hi / maxTot * barMax) : bwid) + 4;
          body += text(endX, ry + G.ch / 2 + 3.6, M.compact(r.total, !!r.flags.estimated) + (r.flags.partial ? ' ½' : '') + (r.flags.incomplete ? ' +' : ''), { size: 9.5, fill: P.INK2 });
        } else {
          body += '<rect x="' + barX + '" y="' + by2 + '" width="' + bwid.toFixed(1) + '" height="' + bh2 + '" fill="#FFFFFF" stroke="#4D4D4D" stroke-width="1" stroke-dasharray="3 2"/>';
          body += text(G.rx + G.rankW, ry + G.ch / 2 + 3.6, 'n/r', { size: 9, anchor: 'end', fill: P.INK2 });
          body += text(barX + bwid + 4, ry + G.ch / 2 + 3.6, M.compact(r.total, false) + ' ' + (r.flags.provisional ? 'to date' : 'partial'), { size: 9, fill: P.INK2 });
        }
      }
    });
    var yEnd = y0 + model.rows.length * G.ch;
    body += text(G.rx, yEnd + 12, 'n/r = not ranked (incomplete or', { size: 8.5, fill: P.INK2 });
    body += text(G.rx, yEnd + 23, 'provisional year). ½ = partial Jan 2012;', { size: 8.5, fill: P.INK2 });
    body += text(G.rx, yEnd + 34, '+ = has incomplete months.', { size: 8.5, fill: P.INK2 });
    var yLg = yEnd + 48;
    if (model.rankingTagged > 0) {                       // what the tags under the ranks mean (only when a ranked year carries one)
      ['Tagged years hold MODIS estimates (see', 'the label above the figure). Their rank', 'sits among observed years: read it as a', 'guide, not as a firm ordering.'].forEach(function (ln, i) {
        body += text(G.rx, yEnd + 48 + i * 11, ln, { size: 8.5, fill: P.INK2 });
      });
      yLg = yEnd + 48 + 4 * 11 + 6;
    }
    // legend
    var lg = legendSvg(model, idp, yLg);
    body += lg.svg;
    var ny = yLg + lg.height + 10;
    body += text(G.ml, ny, 'Notes', { size: 11, weight: 700 }); ny += 4;
    noteLines(model).forEach(function (n) {
      var t = C.textLines(G.ml + 8, ny + 12, n, 136, { size: 10, fill: P.INK2, lineHeight: 12.5 });
      body += '<circle cx="' + (G.ml + 3) + '" cy="' + (ny + 8.5) + '" r="1.6" fill="' + P.INK2 + '"/>' + t.svg;
      ny += t.height + 4;
    });
    var ft = C.footer(model, G.w, ny + 8);
    body += ft.svg;
    var H = Math.ceil(ny + 8 + ft.height + 14);
    var desc = 'Heat-map calendar with one row per ' + (model.axis.used === 'fire' ? 'fire year' : 'year') + ' and one column per month. ' +
      (model.season && model.season.core ? model.season.core.text + '. ' : '') +
      (model.rankingTagged > 0 ? 'The year totals are ranked; a year that holds MODIS estimates is tagged indicative, not tested or reliable next to its rank. ' : '') +
      'Use the arrow keys on the figure to move between months and hear each value.';
    var svg = C.frame({ w: G.w, h: H, idp: idp, title: title, desc: desc, body: body });
    return { svg: svg, w: G.w, h: H, idp: idp };
  }

  // ------------------------------------------------------------------------------------------- string render (tests)
  function renderToString(input) {
    var model = M.buildModel(input);
    if (model.empty) return '';
    return drawCalendar(model).svg;
  }

  // ------------------------------------------------------------------------------------------- DOM (browser only)
  var STATE = (typeof WeakMap === 'function') ? new WeakMap() : null;
  var domId = 0;

  function el$(el, sel) { return el.querySelector(sel); }

  function renderState(el, kind, msg, extra) {
    var html;
    extra = extra || {};
    if (kind === 'loading') {
      html = '<div class="fc fc--loading" role="status" aria-live="polite" aria-busy="true">' +
        '<div class="fc-skel" aria-hidden="true">' + new Array(60).join('<i></i>') + '</div>' +
        '<p class="fc-state__msg"><span class="fc-spin" aria-hidden="true"></span> ' + esc(msg || 'Loading the fire calendar…') + '</p></div>';
    } else if (kind === 'error') {
      html = '<div class="fc fc--error" role="alert"><p class="fc-state__title">The calendar could not be built</p>' +
        '<p class="fc-state__msg">' + esc(msg || 'Something went wrong while reading the data for this area.') + '</p>' +
        '<p class="fc-state__hint">Check your connection and try again. If it keeps failing, pick a different area or date range.</p>' +
        (extra.retry ? '<button type="button" class="fc-btn" data-fc-retry>Try again</button>' : '') + '</div>';
    } else {
      html = '<div class="fc fc--empty" role="status"><p class="fc-state__title">' + esc(extra.title || 'No hotspot data for this selection') + '</p>' +
        '<p class="fc-state__msg">' + esc(msg || 'There are no processed detections for this area and period. Try a larger area or a different date range.') + '</p></div>';
    }
    el.innerHTML = html;
    var btn = el.querySelector('[data-fc-retry]');
    if (btn && extra.retry) btn.addEventListener('click', extra.retry);
    if (STATE) { var st = STATE.get(el); if (st) { st.kind = kind; st.model = null; } }
  }

  function controlsHtml(st, model) {
    var id = st.id, o = model.opts, view = viewOf(model);
    function radio(name, val, label, checked) {
      return '<label class="fc-opt"><input type="radio" name="' + id + name + '" value="' + val + '" data-opt="' + name + '"' + (checked ? ' checked' : '') + '> <span>' + label + '</span></label>';
    }
    var h = '<form class="fc-controls" aria-label="Calendar options" onsubmit="return false">';
    if (model.hasDaily && GM && FV) {
      h += '<fieldset class="fc-group"><legend>View</legend>' + radio('view', 'calendar', 'Calendar', view === 'calendar') +
        radio('view', 'season', 'Season so far', view === 'season') + radio('view', 'daily', 'Daily pattern', view === 'daily') + '</fieldset>';
    }
    if (view === 'calendar') {
      h += '<fieldset class="fc-group"><legend>Colour by</legend>' + radio('mode', 'counts', 'Counts', o.mode === 'counts') + radio('mode', 'anomaly', 'Anomaly', o.mode === 'anomaly') + '</fieldset>';
    }
    h += '<fieldset class="fc-group"><legend>Detections</legend>' + radio('veg', 'veg', 'Vegetation fires only', o.vegetationOnly) + radio('veg', 'all', 'All thermal anomalies', !o.vegetationOnly) + '</fieldset>';
    if (view === 'calendar') {
      h += '<div class="fc-group"><label for="' + id + 'axis">Rows</label><select id="' + id + 'axis" data-opt="axis">' +
        '<option value="auto"' + (o.axis === 'auto' ? ' selected' : '') + '>Automatic</option>' +
        '<option value="calendar"' + (o.axis === 'calendar' ? ' selected' : '') + '>Calendar year</option>' +
        '<option value="fire"' + (o.axis === 'fire' ? ' selected' : '') + '>Fire year</option></select></div>';
      h += '<div class="fc-group"><label for="' + id + 'base">Base period</label><select id="' + id + 'base" data-opt="base">' +
        '<option value="B2"' + (o.base === 'B2' ? ' selected' : '') + '>2012\u20132025 VIIRS (default)</option>' +
        '<option value="B1"' + (o.base === 'B1' ? ' selected' : '') + '>2003\u20132025 harmonised (sensitivity)</option></select></div>';
    }
    if (view === 'season' && GM) {
      var fys = GM.listFireYears(model), cur = GM.seasonToDate(model);
      var sel = cur.available ? cur.evalFY : null;
      h += '<div class="fc-group"><label for="' + id + 'ey">Season shown</label><select id="' + id + 'ey" data-opt="evalYear">' +
        fys.slice().reverse().map(function (f) { return '<option value="' + f.fy + '"' + (f.fy === sel ? ' selected' : '') + '>' + f.label + '</option>'; }).join('') + '</select></div>';
    }
    return h + '</form>';
  }

  function viewOf(model) {
    var v = model.opts.view;
    if ((v === 'season' || v === 'daily') && (!model.hasDaily || !GM || !FV)) return 'calendar';
    return v;
  }

  function noticesHtml(model) {
    var items = model.notices.filter(function (n) { return n.level === 'warn'; });
    if (!items.length) return '';
    return '<ul class="fc-notices" role="status">' + items.map(function (n) { return '<li class="fc-notice fc-notice--' + n.level + '">' + esc(n.text) + '</li>'; }).join('') + '</ul>';
  }

  /** Label of the pre-2012 estimates (verdict of the single test): shown above the figure whenever estimated months are on screen. */
  function reliabilityHtml(model) {
    var r = model.reliability;
    if (!r || !model.rows.some(function (x) { return x.flags.estimated; })) return '';
    var tag = r.state === 'reliable' ? 'Reliable' : (r.state === 'indicative' ? 'Indicative' : 'Not yet tested');
    return '<p class="fc-reliab fc-reliab--' + r.state + '" role="status"><span class="fc-reliab__tag">' + esc(tag) + '</span> ' + esc(r.headline) + '</p>';
  }

  function tipHtml(tp) {
    var h = '<div class="fc-tip__title">' + esc(tp.title) + '</div>';
    tp.lines.forEach(function (l) {
      if (l.k === 'v') h += '<div class="fc-tip__value">' + esc(l.t) + '</div>';
      else if (l.k === 'h') h += '<div class="fc-tip__h">' + esc(l.t) + '</div>';
      else if (l.k === 'kv') h += '<div class="fc-tip__kv"><span>' + esc(l.a) + '</span> ' + esc(l.b) + '</div>';
      else if (l.k === 'warn') h += '<div class="fc-tip__warn">' + esc(l.t) + '</div>';
      else h += '<div class="fc-tip__p">' + esc(l.t) + '</div>';
    });
    return h;
  }

  function findCell(model, k) { return model.cells[k]; }

  function drawView(model, st) {
    var view = viewOf(model);
    st.viewKind = view; st.sm = null; st.km = null;
    if (view === 'season') {
      var sm = GM.seasonToDate(model);
      if (sm.available) { st.sm = sm; return FV.drawSeason(model, sm).svg; }
      return '<p class="fc-notice fc-notice--info">The season view needs daily VIIRS data and at least one complete base fire year (' + esc(sm.reason || '') + ').</p>';
    }
    if (view === 'daily') {
      var km = GM.dailyPattern(model);
      if (km.available) { st.km = km; return FV.drawDaily(model, km).svg; }
      return '<p class="fc-notice fc-notice--info">The daily pattern is not available for this area' + (km.reason === 'all-year' ? ': activity is spread over the whole year, so there is no season window.' : ' (' + esc(km.reason || '') + ').') + '</p>';
    }
    return drawCalendar(model, { idp: st.id + 'f-' }).svg;
  }

  function paint(el, st) {
    var model = st.model;
    var stage = el.querySelector('.fc-stage');
    stage.querySelector('.fc-fig').innerHTML = drawView(model, st);
    el.querySelector('.fc-controls-wrap').innerHTML = controlsHtml(st, model);
    el.querySelector('.fc-notices-wrap').innerHTML = noticesHtml(model) + reliabilityHtml(model);
    st.svg = stage.querySelector('svg');
    st.active = null; st.slot = null;
    if (st.svg) {
      st.svg.setAttribute('tabindex', '0');
      st.svg.setAttribute('focusable', 'true');
      var f = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      f.setAttribute('class', 'fc-focus'); f.setAttribute('fill', 'none'); f.setAttribute('stroke', '#E69F00'); f.setAttribute('stroke-width', '3');
      f.setAttribute('visibility', 'hidden'); f.setAttribute('pointer-events', 'none');
      st.svg.appendChild(f); st.focusRect = f;
    } else { st.focusRect = null; }
    hideTip(el, st);
  }

  function showTip(el, st, cellG, clientX, clientY) {
    var tip = el.querySelector('.fc-tip'), stage = el.querySelector('.fc-stage');
    var k = +cellG.getAttribute('data-k'), c = findCell(st.model, k);
    if (!c) return;
    var tp = M.tooltip(c, st.model);
    tip.innerHTML = tipHtml(tp);
    tip.hidden = false;
    var sr = stage.getBoundingClientRect();
    var x = (clientX - sr.left) + 14, y = (clientY - sr.top) + 14;
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    if (x + tw > sr.width - 4) x = Math.max(4, (clientX - sr.left) - tw - 14);
    if (y + th > sr.height - 4) y = Math.max(4, (clientY - sr.top) - th - 14);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    var live = el.querySelector('.fc-live'); if (live) live.textContent = tp.aria;
  }
  function hideTip(el, st) {
    var tip = el.querySelector('.fc-tip'); if (tip) tip.hidden = true;
    if (st && st.focusRect) st.focusRect.setAttribute('visibility', 'hidden');
  }

  function showChartTip(el, st, i, clientX, clientY) {
    var tip = el.querySelector('.fc-tip'), stage = el.querySelector('.fc-stage');
    var tp = st.sm ? FV.seasonTip(st.sm, i) : FV.dailyTip(st.km, i);
    tip.innerHTML = tipHtml(tp); tip.hidden = false;
    var sr = stage.getBoundingClientRect(), x = (clientX - sr.left) + 14, y = (clientY - sr.top) + 14;
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    if (x + tw > sr.width - 4) x = Math.max(4, (clientX - sr.left) - tw - 14);
    if (y + th > sr.height - 4) y = Math.max(4, (clientY - sr.top) - th - 14);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    var live = el.querySelector('.fc-live'); if (live) live.textContent = tp.aria;
  }

  function moveActive(el, st, dr, dc) {
    var model = st.model, rows = model.rows;
    var r = st.active ? st.active.r : rows.length - 1, c = st.active ? st.active.c : 0;
    if (!st.active) {                         // first focus: last row that has data
      for (var i = rows.length - 1; i >= 0; i--) {
        for (var j = 11; j >= 0; j--) if (rows[i].slots[j] && !rows[i].slots[j].outside) { r = i; c = j; i = -1; break; }
      }
    } else {
      var nr = r, nc = c;
      for (var guard = 0; guard < 400; guard++) {
        nc += dc; nr += dr;
        if (dc !== 0) { if (nc > 11) { nc = 0; nr++; } if (nc < 0) { nc = 11; nr--; } }
        if (nr < 0 || nr >= rows.length) return;          // stay on the edge
        var s = rows[nr].slots[nc];
        if (s && !s.outside) { r = nr; c = nc; break; }
      }
    }
    st.active = { r: r, c: c };
    var g = st.svg.querySelector('.fc-cell[data-r="' + r + '"][data-c="' + c + '"]');
    if (!g) return;
    var rect = g.querySelector('rect');
    st.focusRect.setAttribute('x', rect.getAttribute('x')); st.focusRect.setAttribute('y', rect.getAttribute('y'));
    st.focusRect.setAttribute('width', rect.getAttribute('width')); st.focusRect.setAttribute('height', rect.getAttribute('height'));
    st.focusRect.setAttribute('visibility', 'visible');
    var br = g.getBoundingClientRect();
    showTip(el, st, g, br.left + br.width / 2, br.top + br.height);
  }

  function bind(el, st) {
    if (st.bound) return; st.bound = true;
    el.addEventListener('change', function (e) {
      var t = e.target; if (!t || !t.getAttribute) return;
      var opt = t.getAttribute('data-opt'); if (!opt) return;
      var o = st.options;
      if (opt === 'mode') o.mode = t.value;
      else if (opt === 'veg') o.vegetationOnly = (t.value === 'veg');
      else if (opt === 'axis') o.axis = t.value;
      else if (opt === 'base') o.base = t.value;
      else if (opt === 'view') o.view = t.value;
      else if (opt === 'evalYear') o.evalYear = +t.value;
      if (opt === 'view' && t.value !== 'season') o.evalYear = null;
      update(el, st);
      var again = el.querySelector('[data-opt="' + opt + '"]' + (t.type === 'radio' ? '[value="' + t.value + '"]' : ''));
      if (again && again.focus) again.focus();
      if (typeof st.input.onOptionsChange === 'function') st.input.onOptionsChange(Object.assign({}, o));
    });
    var stage = null;
    el.addEventListener('mousemove', function (e) {
      if (!st.model) return;
      var hit = e.target && e.target.closest ? e.target.closest('.fc-hit') : null;
      if (hit && (st.sm || st.km)) {
        var r = hit.getBoundingClientRect(), nn = (st.sm || st.km).slots.length;
        var i = Math.max(0, Math.min(nn - 1, Math.round((e.clientX - r.left) / r.width * (nn - 1))));
        showChartTip(el, st, i, e.clientX, e.clientY); return;
      }
      var g = e.target && e.target.closest ? e.target.closest('.fc-cell') : null;
      if (!g) { hideTip(el, st); return; }
      showTip(el, st, g, e.clientX, e.clientY);
    });
    el.addEventListener('mouseleave', function () { hideTip(el, st); });
    el.addEventListener('keydown', function (e) {
      if (!st.svg || e.target !== st.svg) return;
      var d = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
      if (e.key === 'Escape') { hideTip(el, st); return; }
      if (st.sm || st.km) {                       // chart views: left / right move by a day (shift: a week)
        var step = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
        if (!step) return;
        e.preventDefault();
        var cm = st.sm || st.km, nn = cm.slots.length;
        var cur = (st.slot === null || st.slot === undefined) ? (st.sm ? st.sm.lastSlot : cm.peak) : st.slot;
        st.slot = Math.max(0, Math.min(nn - 1, cur + step * (e.shiftKey ? 7 : 1)));
        var sr = st.svg.getBoundingClientRect();
        showChartTip(el, st, st.slot, sr.left + (FV.X0 + st.slot / (nn - 1) * FV.PW) / 840 * sr.width, sr.top + sr.height * 0.25);
        return;
      }
      if (!d) return;
      e.preventDefault(); moveActive(el, st, d[0], d[1]);
    });
    el.addEventListener('focusout', function (e) { if (e.target === st.svg) hideTip(el, st); });
  }

  function update(el, st) {
    try {
      st.model = M.buildModel(Object.assign({}, st.input, { options: st.options }));
    } catch (err) {
      renderState(el, 'error', 'Could not process the data: ' + (err && err.message ? err.message : err), { retry: st.input.onRetry });
      return;
    }
    if (st.model.empty) { renderState(el, 'empty'); return; }
    paint(el, st);
  }

  function render(el, input) {
    input = input || {};
    var st = STATE ? STATE.get(el) : null;
    if (!st) { st = { id: 'fc' + (++domId) + '-', options: {} }; if (STATE) STATE.set(el, st); }
    st.input = input;
    st.options = Object.assign({}, st.options, input.options || {});
    var retry = typeof input.onRetry === 'function' ? input.onRetry : null;
    if (input.status === 'loading') { renderState(el, 'loading', input.message); return; }
    if (input.status === 'error' || input.error) { renderState(el, 'error', typeof input.error === 'string' ? input.error : (input.error && input.error.message) || input.message, { retry: retry }); return; }
    if (input.outsideCoverage || (input.aoi && input.aoi.outside)) {
      renderState(el, 'empty', 'The calendar covers Mexico and Argentina. Move the area inside one of them.', { title: 'Outside processed coverage' }); return;
    }
    if (!Array.isArray(input.monthly) || !input.monthly.length) { renderState(el, 'empty', input.emptyMessage, { title: input.emptyTitle }); return; }
    var model;
    try { model = M.buildModel(Object.assign({}, input, { options: st.options })); }
    catch (err) { renderState(el, 'error', 'Could not process the data: ' + (err && err.message ? err.message : err), { retry: retry }); return; }
    if (model.empty) { renderState(el, 'empty'); return; }
    st.model = model; st.kind = 'ready';
    el.innerHTML = '<div class="fc fc--ready"><div class="fc-controls-wrap"></div><div class="fc-notices-wrap"></div>' +
      '<div class="fc-stage"><div class="fc-fig"></div><div class="fc-tip" role="tooltip" hidden></div></div>' +
      '<div class="fc-live" aria-live="polite"></div></div>';
    bind(el, st);
    paint(el, st);
  }

  // ------------------------------------------------------------------------------------------- PNG export
  function exportPNG(el) {
    return new Promise(function (resolve, reject) {
      try {
        var svg = el && el.querySelector ? el.querySelector('svg.fc-figure') : null;
        if (!svg) { reject(new Error('Nothing to export: the calendar is not showing data.')); return; }
        var clone = svg.cloneNode(true);
        var f = clone.querySelector('.fc-focus'); if (f && f.parentNode) f.parentNode.removeChild(f);
        clone.removeAttribute('tabindex');
        var vb = (svg.getAttribute('viewBox') || '0 0 840 1188').split(/\s+/).map(Number);
        var w = vb[2], h = vb[3], scale = 2;
        var xml = new XMLSerializer().serializeToString(clone);
        var url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
        var img = new Image();
        img.onload = function () {
          try {
            var cv = document.createElement('canvas'); cv.width = w * scale; cv.height = h * scale;
            var cx = cv.getContext('2d'); cx.fillStyle = '#FFFFFF'; cx.fillRect(0, 0, cv.width, cv.height);
            cx.drawImage(img, 0, 0, cv.width, cv.height);
            URL.revokeObjectURL(url);
            cv.toBlob(function (b) { if (b) resolve(b); else reject(new Error('The browser could not create the PNG.')); }, 'image/png');
          } catch (e) { URL.revokeObjectURL(url); reject(e); }
        };
        img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('The figure could not be rasterised.')); };
        img.src = url;
      } catch (e) { reject(e); }
    });
  }

  return { render: render, exportPNG: exportPNG, renderToString: renderToString, renderState: renderState,
           buildModel: M.buildModel, drawCalendar: drawCalendar, tooltip: M.tooltip, VERSION: '1.0.0' };
});
