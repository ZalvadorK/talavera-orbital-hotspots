/*
 * SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
 *
 * calendario-paleta.js - colour tokens for the fire calendar. Values copied from figures/paleta.json
 * (the app is deployed on its own, so it cannot read figures/ at run time). Colour-blind safe:
 *   - counts: cividis (sequential, log scale), no rainbow
 *   - anomaly: ColorBrewer RdBu reversed, centred on the median (percentile 50)
 *   - states never depend on colour alone: every state also has a pattern, border style or letter.
 * Works in the browser (window.FirePalette) and in Node (module.exports).
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  root.FirePalette = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var SEQ = ['#00224e', '#1a386f', '#434e6c', '#61656f', '#7d7c78', '#9b9476', '#bcae6c', '#dec958', '#fee838'];
  var DIV = ['#053061', '#2065ab', '#4393c3', '#90c4dd', '#d1e5f0', '#f7f6f6', '#fddbc7', '#f3a481', '#d6604d', '#b1182b', '#67001f'];

  var INK = '#1A1A1A', INK2 = '#4D4D4D', GRID = '#D9D9D9', BG = '#FFFFFF';

  var STATES = {
    unusual_high: { fill: '#D55E00', stroke: '#7A3600', text: '#FFFFFF', label: 'Unusually high' },
    unusual_low: { fill: '#0072B2', stroke: '#00334F', text: '#FFFFFF', label: 'Unusually low' },
    possibly_unusual: { fill: '#F6D2B0', stroke: '#D55E00', text: '#1A1A1A', label: 'Possibly unusual' },
    typical: { fill: '#CFCFCF', stroke: '#8C8C8C', text: '#1A1A1A', label: 'Typical' },
    no_data: { fill: '#FFFFFF', stroke: '#6B6B6B', text: '#1A1A1A', label: 'No data' },
    insufficient: { fill: '#F5F5F5', stroke: '#B0B0B0', text: '#1A1A1A', label: 'Insufficient data' }
  };
  var OVERLAYS = {
    provisional: { stroke: '#CC79A7', width: 3, dash: '5 3', label: 'Provisional (NRT)' },
    estimated: { stroke: '#000000', width: 1, label: 'Estimated (from MODIS)' },
    incomplete: { stroke: '#000000', width: 2, dash: '2 2', label: 'Incomplete month' },
    lower_confidence: { stroke: '#000000', width: 2, dash: '6 2 1 2', label: 'Lower confidence (indicative)' }
  };

  function hexToRgb(h) {
    var s = h.replace('#', '');
    return [parseInt(s.substr(0, 2), 16), parseInt(s.substr(2, 2), 16), parseInt(s.substr(4, 2), 16)];
  }
  function rgbToHex(c) {
    return '#' + c.map(function (x) { var v = Math.max(0, Math.min(255, Math.round(x))); return (v < 16 ? '0' : '') + v.toString(16); }).join('');
  }
  function ramp(stops, t) {
    if (!(t === t)) return stops[0];
    t = Math.max(0, Math.min(1, t));
    var pos = t * (stops.length - 1), i = Math.floor(pos), f = pos - i;
    if (i >= stops.length - 1) return stops[stops.length - 1];
    var a = hexToRgb(stops[i]), b = hexToRgb(stops[i + 1]);
    return rgbToHex([a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2])]);
  }
  function seqColor(t) { return ramp(SEQ, t); }
  function divColor(t) { return ramp(DIV, t); }

  function luminance(hex) {
    var c = hexToRgb(hex).map(function (x) { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  /** Black or white text/lines, whichever has the higher contrast against hex. */
  function inkOn(hex) { return luminance(hex) > 0.179 ? INK : '#FFFFFF'; }

  return { SEQ: SEQ, DIV: DIV, INK: INK, INK2: INK2, GRID: GRID, BG: BG, STATES: STATES, OVERLAYS: OVERLAYS,
           seqColor: seqColor, divColor: divColor, inkOn: inkOn, luminance: luminance, ramp: ramp };
});
