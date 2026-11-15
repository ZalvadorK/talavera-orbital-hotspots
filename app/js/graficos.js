/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * graficos.js - shared SVG helpers (frame, header, footer, patterns) for the fire calendar figures.
 * SVG is built as a string with inline attributes only (no CSS), so the same markup can be shown on screen
 * and rasterised to PNG without depending on style sheets. Works in the browser (window.FireCharts) and in Node.
 */
(function (root, factory) {
  'use strict';
  var P = (typeof module === 'object' && typeof require === 'function') ? require('./calendario-paleta.js') : root.FirePalette;
  var M = (typeof module === 'object' && typeof require === 'function') ? require('./calendario-modelo.js') : root.FireCalendarModel;
  var api = factory(P, M);
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FireCharts = api;
})(typeof window !== 'undefined' ? window : globalThis, function (P, M) {
  'use strict';

  var FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";
  var SI_MARK = 'SI-generated (AI)';
  var DATA_LINE = 'Data: NASA FIRMS (MODIS and VIIRS hotspot detections)';

  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  /** Greedy word wrap by character count (monospace-ish estimate). */
  function wrap(text, maxChars) {
    var words = String(text).split(/\s+/), lines = [], cur = '';
    words.forEach(function (w) {
      if ((cur + ' ' + w).trim().length > maxChars) { if (cur) lines.push(cur); cur = w; }
      else cur = (cur + ' ' + w).trim();
    });
    if (cur) lines.push(cur);
    return lines;
  }
  function text(x, y, s, o) {
    o = o || {};
    return '<text x="' + x + '" y="' + y + '" font-family="' + FONT + '" font-size="' + (o.size || 11) + '"' +
      (o.weight ? ' font-weight="' + o.weight + '"' : '') + ' fill="' + (o.fill || P.INK) + '"' +
      (o.anchor ? ' text-anchor="' + o.anchor + '"' : '') + (o.halo ? ' stroke="#FFFFFF" stroke-width="2.4" paint-order="stroke" stroke-linejoin="round"' : '') +
      (o.cls ? ' class="' + o.cls + '"' : '') + (o.extra ? ' ' + o.extra : '') + '>' + esc(s) + '</text>';
  }
  function textLines(x, y, str, maxChars, o) {
    o = o || {};
    var out = '', lh = o.lineHeight || 14;
    wrap(str, maxChars).forEach(function (ln, i) { out += text(x, y + i * lh, ln, o); });
    return { svg: out, lines: wrap(str, maxChars).length, height: wrap(str, maxChars).length * lh };
  }

  /** Pattern definitions. idp is a unique prefix per figure. dark/light variants for readable lines on any fill. */
  function patternDefs(idp) {
    var d = '';
    [['d', '#1A1A1A'], ['l', '#FFFFFF']].forEach(function (v) {
      var c = v[1], s = v[0];
      d += '<pattern id="' + idp + 'hT' + s + '" patternUnits="userSpaceOnUse" width="3" height="3" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="3" stroke="' + c + '" stroke-width="1.3"/></pattern>';
      d += '<pattern id="' + idp + 'hA' + s + '" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="' + c + '" stroke-width="1.1"/></pattern>';
      d += '<pattern id="' + idp + 'zr' + s + '" patternUnits="userSpaceOnUse" width="4" height="4"><line x1="2" y1="0" x2="2" y2="4" stroke="' + c + '" stroke-width="0.8"/></pattern>';
      d += '<pattern id="' + idp + 'in' + s + '" patternUnits="userSpaceOnUse" width="6" height="6"><line x1="3" y1="0" x2="3" y2="6" stroke="' + c + '" stroke-width="1"/><line x1="0" y1="3" x2="6" y2="3" stroke="' + c + '" stroke-width="1"/></pattern>';
      d += '<pattern id="' + idp + 'nd' + s + '" patternUnits="userSpaceOnUse" width="6" height="6"><line x1="0" y1="0" x2="6" y2="6" stroke="' + c + '" stroke-width="0.9"/><line x1="6" y1="0" x2="0" y2="6" stroke="' + c + '" stroke-width="0.9"/></pattern>';
      d += '<pattern id="' + idp + 'sf' + s + '" patternUnits="userSpaceOnUse" width="5" height="5"><circle cx="2.5" cy="2.5" r="0.9" fill="' + c + '"/></pattern>';
    });
    return '<defs>' + d + '</defs>';
  }

  function periodText(model) {
    var a = model.firstKey, b = model.lastKey;
    var ya = Math.floor(a / 12), ma = (a % 12), yb = Math.floor(b / 12), mb = (b % 12);
    var last = model.daily && model.daily.lastDate ? model.daily.lastDate : null;
    return M.MON3[ma] + ' ' + ya + ' – ' + (last ? last : M.MON3[mb] + ' ' + yb);
  }

  function synthBanner(model, x, y) {
    if (!model.synthetic) return '';
    var t = 'SYNTHETIC DEMO DATA';
    return '<g><rect x="' + x + '" y="' + y + '" width="190" height="22" fill="#F0E442" stroke="#1A1A1A" stroke-width="1.5"/>' +
      text(x + 95, y + 15, t, { size: 12, weight: 700, anchor: 'middle' }) + '</g>';
  }

  /** Footer used by every figure (source, period, SI mark). Returns {svg, height}. */
  function footer(model, w, y) {
    var man = model.manifest || {};
    var run = man.exp || man.experimento || man.run || null;
    var gen = man.generated || man.generado || man.fecha || null;
    var line1 = (model.synthetic ? 'SYNTHETIC DATA for testing. ' : '') + DATA_LINE + ', ' + periodText(model) +
      '; harmonized to VIIRS-equivalent units (hotspot detections, not individual fires); dates in UTC; analysis: this project.';
    var s = '<line x1="24" x2="' + (w - 24) + '" y1="' + y + '" y2="' + y + '" stroke="' + P.GRID + '" stroke-width="1"/>';
    var t = textLines(24, y + 16, line1, 128, { size: 10, fill: P.INK2, lineHeight: 12 });
    s += t.svg;
    var y2 = y + 16 + t.height + 2;
    s += text(24, y2, (run ? 'Run: ' + run + (gen ? ' · ' + gen : '') + ' · ' : '') + 'Built with SI assistance (Claude Code). Not endorsed by NASA.', { size: 10, fill: P.INK2 });
    // visible SI mark (pill)
    s += '<rect x="' + (w - 24 - 118) + '" y="' + (y2 - 12) + '" width="118" height="17" rx="8" fill="#FFFFFF" stroke="#1A1A1A" stroke-width="1"/>' +
         text(w - 24 - 59, y2 + 0.5, SI_MARK, { size: 10.5, weight: 700, anchor: 'middle' });
    return { svg: s, height: (y2 + 10) - y };
  }

  function frame(o) {
    var w = o.w, h = o.h;
    return '<svg xmlns="http://www.w3.org/2000/svg" class="fc-figure" role="img" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h +
      '" aria-labelledby="' + o.idp + 'title ' + o.idp + 'desc" font-family="' + FONT + '">' +
      '<title id="' + o.idp + 'title">' + esc(o.title) + '</title><desc id="' + o.idp + 'desc">' + esc(o.desc) + '</desc>' +
      patternDefs(o.idp) + '<rect x="0" y="0" width="' + w + '" height="' + h + '" fill="#FFFFFF"/>' + o.body + '</svg>';
  }

  return { FONT: FONT, esc: esc, wrap: wrap, text: text, textLines: textLines, patternDefs: patternDefs, footer: footer,
           frame: frame, synthBanner: synthBanner, periodText: periodText, SI_MARK: SI_MARK, DATA_LINE: DATA_LINE };
});
