// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// tendencia-enlace.js - links the two analysis views to the page with ONE call of the app shell (estado-arranque.js calls
// CONFIG.CALENDAR_MODULE with {container: <section id="calendar">, store, datos, config}):
//   - the calendar  -> ./calendario-montar.js  (same container)
//   - the annual trend (ADR-0012, descriptive) -> ./tendencia-montar.js  (container: <section id="trend">, same store)
// Neither module is changed. If the page has no #trend section, only the calendar is mounted. A failure of the trend never
// stops the calendar (and the other way round): each view shows its own error state.
//
// To mount the calendar alone, set CONFIG.CALENDAR_MODULE = './calendario-montar.js' in datos-config.js.

import * as calendario from './calendario-montar.js';
import * as tendencia from './tendencia-montar.js';

export async function montar(ctx) {
  const trend = document.getElementById('trend');
  const [cal, tr] = await Promise.allSettled([
    calendario.montar(ctx),
    trend ? tendencia.montar({ ...ctx, container: trend }) : Promise.resolve(),
  ]);
  if (tr.status === 'rejected') {
    console.error(tr.reason);
    if (trend) trend.dataset.state = 'error';
  }
  if (cal.status === 'rejected') throw cal.reason;          // the shell marks #calendar as "error"
}

export function destruir() {
  calendario.destruir();
  tendencia.destruir();
}

/** PNG of the calendar on screen (calendario-montar.js) and of the trend figure. */
export const exportarPNG = calendario.exportarPNG;
export const exportarPNGTendencia = tendencia.exportarPNG;
