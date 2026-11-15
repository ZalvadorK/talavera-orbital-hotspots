// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// notas-metodo.js - the "Method notes" block of the page, in plain English and WITHOUT internal decision identifiers (no "ADR-...",
// no list of decision records). It replaces the old "About the data" text and is always on.
//
//   construirNotas(manifest) -> { heading, summary, sections: [{ id, title, items: [string] }], items: [string], status, scenario }
//                                pure, tested in app/tests/fiabilidad.test.mjs and app/tests/notas-metodo.test.mjs
//   aplicarNotasMetodo(manifest) -> DOM: rewrites the heading, the summary and the sections of #about (manifest may be null)
//   describirExperimentos(manifest) -> the one-line description of the runs behind the data (row "Experiment runs" of the page)
//   marcadoresPendientes(manifest) -> the unresolved markers still present in the rendered text (see below)
//
// What the text states and where it comes from (the evidence ledger holds the evidence; the page carries no claim tags):
//   - how the series is built: the method as implemented (the exporter's manifest and the analysis core);
//   - validation: the status line, the key figures and the label of each country are READ from manifest.verdict (null = the
//     pre-registered test has not been run), which the exporter summarizes from runs/EXP-NNN/verdict.json and metricas.json. Nothing
//     is typed by hand. Only when a valid verdict exists does the page show ONE of the three pre-registered result texts (A, B or C),
//     chosen by the pre-registered rule (PREREGISTRATION section 1: number of countries with RT05_bloque3 true on the published scale:
//     2 -> A, 1 -> B, 0 -> C), and it always comes with the final prior-exposure declaration (PREREGISTRATION section 2, verbatim)
//     and the addendum written after the freeze;
//   - figures quoted, and the ledger claim that backs each one (the page itself carries no tags):
//       kappa, twin kappa and their ratio per country (P2) -> CLM-104 · P3 coverage -> CLM-106 · P4 skill -> CLM-107
//       exposure declaration -> CLM-119 · mask in Argentina -> CLM-120 · 26 data-rule days -> CLM-121 · Bahia Blanca -> CLM-122 (text verbatim)
//       MODIS file versions and sources -> CLM-112 · erratum on the label "Collection 6.1" of the pre-registration -> CLM-136 · addendum -> CLM-135
//       label rule -> CLM-124 · VIIRS gap rule -> CLM-125 · intended use -> CLM-126 · activity bias -> CLM-127 · Terra Mar-Apr 2002 -> CLM-128;
//   - limitations: the sentence on the activity-level bias is the one of the sign note, verbatim; the 26 data-rule gap days and the
//     Terra days of Mar-Apr 2002 are read from manifest.huecosModis (the exporter crosses our availability table with the FIRMS
//     missing-data table), with a number-free fallback if the manifest lacks them.
//
// PENDING MARKERS: none is left in the text. The guard `node app/tests/marcadores-pendientes.mjs` lists the unresolved-marker patterns
// (PENDING_MARKER_RE below) and exits 1 while any is found in the rendered notes or in index.html.

const PAIS_NOMBRE = (manifest, id) => (manifest.paises && manifest.paises[id] && manifest.paises[id].nombre) || id;
const PAISES_PRUEBA = ['mexico', 'argentina'];

/** Final prior-exposure declaration, verbatim from PREREGISTRATION section 2 (confirmed by the team 2026-11-15 ~14:25, before the freeze). */
export const EXPOSURE_DECLARATION =
  'Before the test, we had inspected aggregate diagnostics that include 2019–2025 for Terra, Aqua and the VIIRS satellites: country-level annual counts and ratios, the yearly median overpass time, a country-level monthly calendar of raw detections for Mexico (2000–2025), and 2013–2024 pooled monthly, day/night, FRP-threshold and 1°-cell ratio distributions (H0/H2 QA); the NOAA-20 series itself, which the app displays from April 2018 onward, was visible at full resolution throughout development. No cell-month or block-month comparison of harmonized MODIS against VIIRS for 2019 or later was computed before the frozen run.';

/** Addendum written AFTER the freeze: the pre-registration itself was not changed. This is the text of ledger claim CLM-135 VERBATIM, label
 *  included (the page shows it as one item, with nothing added before or after it); the test compares it with the ledger and with the
 *  addendum of the README and the submission form. Four groups of aggregate diagnostics, none of which compares harmonized MODIS with VIIRS. */
export const EXPOSURE_ADDENDUM =
  'Addendum (identified after the freeze): the prior-exposure statement omits further quality-control tables we had also seen before the test: ' +
  '(1) type-0 detection counts for Terra, Aqua and S-NPP by calendar month, pooled over 2013–2024, in two approximate boxes (Puebla, Mexico, and ' +
  'south-western Pampas including Bahía Blanca, Argentina); (2) counts of detections within 5 km of the Popocatépetl crater by platform and source ' +
  'type, with first and last year, up to 2025; (3) the yearly median and 90th-percentile MODIS pixel size, 2000–2025, for each country; ' +
  '(4) whole-record (2000–2025) country-level detection counts by platform, file version, source type and confidence class. None of them compares ' +
  'harmonized MODIS with VIIRS. The pre-registration was not changed.';

/** Bahía Blanca limitation, verbatim from the evidence ledger (CLM-122; measured post-test, descriptive: runs/EXP-010 D_aoi_anual). The jump is
 *  already in Terra's raw detections, so the page must not say that the method creates it; the test compares this text with the ledger. */
export const BAHIA_BLANCA_TEXT =
  'In the Bahía Blanca preset area, the harmonized estimates for 2001–2003 are about 5–7 times the 2004–2011 average (7.1×, 5.6× and 5.0×); ' +
  'Terra\'s own raw detections there were 4.4–6.7 times its 2004–2011 average, so the jump is already in the MODIS detections, not created by the conversion. ' +
  'We did not recalibrate for it; read that early period with caution. ' +
  'The Puebla/Popocatépetl preset shows no such jump (2001–2003 about 1.0× its 2004–2011 average).';

/** Erratum written AFTER the freeze: the text of ledger claim CLM-136 VERBATIM, label included (the frozen pre-registration calls the whole
 *  MODIS archive "Collection 6.1"; the FIRMS files we used carry Collection 6 labels for 2000-2022, see CLM-112). Shown as one item. */
export const COLLECTION_ERRATUM =
  'Erratum (identified after the freeze): the pre-registration\'s data section calls the MODIS archive "Collection 6.1"; the FIRMS standard files we used carry Collection 6 version labels ' +
  'for 2000–2022 (6.2 and 6.03, including the 2019–2021 test years) and Collection 6.1 (61.03) from 2023. The data, the code and the test did not change; ' +
  'only the label was wrong.';

/** The three pre-registered result texts (PREREGISTRATION section 1), verbatim. Only the one that matches the verdict is ever shown. */
export const RESULT_TEXTS = Object.freeze({
  A: 'In the 2019–2021 held-out test, harmonized MODIS met our pre-specified sensor-agreement, uncertainty-coverage and baseline-improvement criteria at the 3° block scale in the countries that passed. We report where these results support historical comparisons and where they do not.',
  B: 'Harmonized MODIS met the pre-specified validation criteria at the 3° block scale in one country, but not the other. Talavera Orbital makes that difference visible and labels historical estimates according to their demonstrated reliability.',
  C: 'In our held-out 2019–2021 test, harmonized MODIS did not meet the pre-specified criteria for interchangeable unusual-month classifications at the 3° block scale. The calendar remains useful for exploring historical hotspot detections, but its pre-2012 anomaly flags are indicative rather than validated.',
});

/** Markers that must not reach a public build. */
export const PENDING_MARKER_RE = /\[(?:SIGN-CHECK|VERIFICAR[^\]]*|TODO[^\]]*)\]/g;

/** Sentence on the activity-level bias, verbatim from the pre-registered limitation (docs/03-nucleo/PREREGISTRATION.md, section 3; development sign note). */
export const ACTIVITY_BIAS_TEXT =
  'Level bias depends on activity. In a development check (calibrated on 2012–2015 and compared with S-NPP in 2016–2018; run EXP-002, not the held-out test), for the third of 1° cell-months with the lowest harmonized estimates the observed VIIRS counts were about 1.3–1.5 times the estimate, and for the third with the highest estimates the estimate was too high by up to about 5 %. This pattern is consistent with regression toward the mean when an estimate rests on few MODIS detections; it was not seen in country-level monthly totals, and we did not recalibrate for it. Read low-activity months before 2012 as probably too low, and very active months as possibly slightly high.';

/**
 * Which pre-registered result text applies to a verdict summary (manifest.verdict), or null when there is no valid verdict.
 * THE PRE-REGISTERED RULE (PREREGISTRATION section 1): a country passes iff RT05_bloque3 is true on the published scale (the summary
 * carries that value in `paises.<country>.RT05_bloque3`); null counts as not passing. Count the passing countries among Mexico and
 * Argentina: 2 -> A, 1 -> B, 0 -> C. The other scale and the individual tests (P2, P3, P4) never choose the text.
 * A verdict that lacks one of the two countries is not a valid single test: no text.
 */
export function escenarioPreregistrado(manifest) {
  const v = manifest && manifest.verdict;
  if (!v || !v.paises) return null;
  if (!PAISES_PRUEBA.every((id) => v.paises[id] && typeof v.paises[id] === 'object')) return null;
  const pasan = PAISES_PRUEBA.filter((id) => v.paises[id].RT05_bloque3 === true).length;
  return pasan === 2 ? 'A' : pasan === 1 ? 'B' : 'C';
}

/** The result text of the verdict, or null. */
export function textoResultado(manifest) {
  const e = escenarioPreregistrado(manifest);
  return e ? RESULT_TEXTS[e] : null;
}

/**
 * Validation status line from the manifest. Never says "validated": it reports the label the exporter derived from the test.
 * Returns null when there is no manifest at all (the page is still loading or failed to load).
 */
export function estadoValidacion(manifest) {
  if (!manifest) return null;
  const v = manifest.verdict;
  if (v === null || v === undefined) {
    return 'Validation: the pre-registered test, one single run on 2019 to 2021 data held out of the fitting of the method (see "Prior exposure" below), has not been run yet, so every pre-2012 estimate is shown as "not yet tested".';
  }
  const etiquetas = Object.entries(v.paises || {})
    .map(([id, r]) => `${PAIS_NOMBRE(manifest, id)}: ${r.etiqueta_pais === 'reliable' ? 'reliable' : 'indicative'}`)
    .join('; ');
  return `Validation: the pre-registered test was run once on 2019 to 2021 data held out of the fitting of the method (see "Prior exposure" below). Label of the pre-2012 estimates, by country: ${etiquetas || 'n/a'}.`;
}

/* ---------- number and date formatting (pure) ---------- */
const MESES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MESES_LARGO = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
const k2 = (x) => x.toFixed(2);
const pct0 = (x) => `${Math.round(x * 100)} %`;
const pct1 = (x) => `${(x * 100).toFixed(1).replace('-', '−')} %`;
const miles = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const fecha = (iso) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? { y: +m[1], m: +m[2], d: +m[3] } : null; };
const fechaLarga = (iso) => { const f = fecha(iso); return f ? `${f.d} ${MESES[f.m - 1]} ${f.y}` : null; };
const una = (n, sing, plur) => `${n} ${n === 1 ? sing : plur}`;
const lista = (xs) => (xs.length <= 1 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);

/** "20 to 27 Mar 2002" / "15 Apr 2002" / "30 Mar to 3 Apr 2002" for a [from, to] pair of ISO dates (same year assumed by the data). */
function rangoLegible([a, b]) {
  const x = fecha(a), z = fecha(b);
  if (!x || !z) return null;
  if (a === b) return `${x.d} ${MESES[x.m - 1]} ${x.y}`;
  if (x.y === z.y && x.m === z.m) return `${x.d} to ${z.d} ${MESES[x.m - 1]} ${x.y}`;
  if (x.y === z.y) return `${x.d} ${MESES[x.m - 1]} to ${z.d} ${MESES[z.m - 1]} ${x.y}`;
  return `${x.d} ${MESES[x.m - 1]} ${x.y} to ${z.d} ${MESES[z.m - 1]} ${z.y}`;
}

/** "March and April 2002" for the months touched by a list of ranges (one year assumed; several years: no phrase). */
function mesesLegibles(rangos) {
  const set = new Set();
  const anios = new Set();
  for (const [a, b] of rangos) for (const f of [fecha(a), fecha(b)]) if (f) { set.add(f.m); anios.add(f.y); }
  if (!set.size || anios.size !== 1) return null;
  return `${lista([...set].sort((p, q) => p - q).map((m) => MESES_LARGO[m - 1]))} ${[...anios][0]}`;
}

/* ---------- key figures of the test (read from manifest.verdict.metricas) ---------- */
const CRITERIO = (b) => (b === true ? 'criterion met' : b === false ? 'criterion not met' : 'criterion not computed');

/**
 * Plain-language lines with the key figures of the single test: sensor agreement (P2), uncertainty ranges (P3) and baseline (P4),
 * read from manifest.verdict.metricas (copied by the exporter from runs/EXP-NNN/metricas.json) and the booleans of the verdict.
 * Returns [] when the manifest carries no figures. The pre-specified criteria are the ones of the pre-registration (section 4).
 */
export function cifrasClave(manifest) {
  const v = manifest && manifest.verdict;
  const M = v && v.metricas && v.metricas.paises;
  if (!M) return [];
  const ids = PAISES_PRUEBA.filter((id) => M[id] && v.paises && v.paises[id]);
  if (!ids.length) return [];
  const nombre = (id) => PAIS_NOMBRE(manifest, id);
  const out = [];

  const p2 = ids.map((id) => {
    const x = M[id];
    if (!x.kappa_cruzado || !x.kappa_gemelos || !x.cociente_pareado || !isNum(x.kappa_cruzado.punto)) return null;
    const ic = x.kappa_cruzado.ic95;
    return `${nombre(id)}: kappa ${k2(x.kappa_cruzado.punto)}${ic ? ` (95 % interval ${k2(ic[0])} to ${k2(ic[1])})` : ''} against ${k2(x.kappa_gemelos.punto)} for the twin pair, ratio ${k2(x.cociente_pareado.punto)}; ${CRITERIO(v.paises[id].P2)}`;
  }).filter(Boolean);
  if (p2.length) {
    out.push('Sensor agreement (P2). In 3-degree blocks, we compared the unusual-month flags (unusually high, typical, unusually low) of NOAA-20 with those of harmonized MODIS, using Cohen\'s kappa (1 means perfect agreement), and with those of its twin Suomi NPP as the yardstick. ' +
      `${p2.join('. ')}. Pre-specified criterion: a kappa of at least 0.60 and at least 0.75 times the twin value.`);
  }

  const p3 = ids.map((id) => {
    const c = M[id].P3 && M[id].P3.excluye_s0;
    if (!c || !isNum(c.cobertura)) return null;
    return `${nombre(id)}: ${pct0(c.cobertura)}${c.ic95 ? ` (95 % interval ${pct0(c.ic95[0])} to ${pct0(c.ic95[1])})` : ''}; ${CRITERIO(v.paises[id].P3)}`;
  }).filter(Boolean);
  if (p3.length) {
    const s0 = ids.map((id) => ({ id, a: M[id].P3 && M[id].P3.incluye_s0, n: M[id].P3 && M[id].P3.n_excluidos_Shat_cero })).filter((x) => x.a && isNum(x.a.cobertura) && isNum(x.n));
    out.push('Uncertainty ranges (P3). How often the 80 % range of a harmonized 1-degree cell-month contained the NOAA-20 count. ' +
      `${p3.join('. ')}. Pre-specified target: between 75 % and 85 %. ` +
      (s0.length ? `Cell-months where the estimate is zero (the range is then unbounded) are left out of these figures (${lista(s0.map((x) => `${miles(x.n)} in ${nombre(x.id)}`))}); counting them, the coverage is ${lista(s0.map((x) => `${pct0(x.a.cobertura)} in ${nombre(x.id)}`))}.` : '').trim());
  }

  const p4 = ids.map((id) => {
    const x = M[id].P4;
    if (!x || !isNum(x.skill) || !x.skill_ic95) return null;
    const [lo, hi] = x.skill_ic95;
    return `${nombre(id)}: ${(Math.abs(x.skill) * 100).toFixed(1)} % ${x.skill >= 0 ? 'lower' : 'higher'} error than the baseline (95 % interval for the improvement ${pct1(lo)} to ${pct1(hi)}; ${CRITERIO(v.paises[id].P4)})`;
  }).filter(Boolean);
  if (p4.length) {
    out.push('Better than a simple baseline (P4). The baseline is one overall MODIS-to-VIIRS count ratio per country. We compared the typical (median) relative error of the harmonized 1-degree monthly counts with the baseline\'s. ' +
      `${p4.join('. ')}. Pre-specified criterion: the interval of the improvement lies entirely above zero.`);
  }
  return out;
}

/** The one-line description of the runs behind the data (row "Experiment runs"); the run of the verdict is the single test. */
export function describirExperimentos(manifest) {
  const ids = (manifest && manifest.metodo && manifest.metodo.exp) || [];
  if (!ids.length) return 'n/a';
  const prueba = manifest.verdict && manifest.verdict.exp;
  const dev = ids.filter((e) => e !== prueba);
  const partes = [];
  if (dev.length) partes.push(`${lista(dev)}: development runs that fitted and checked the method on 2012 to 2018`);
  if (prueba && ids.includes(prueba)) partes.push(`${prueba}: the pre-registered single test on 2019 to 2021`);
  return partes.join('; ');
}

/* ---------- label rule ---------- */
function reglaEtiquetas(manifest) {
  const v = manifest && manifest.verdict;
  let cola;
  if (v === null || v === undefined) {
    cola = 'Without a valid test result every pre-2012 estimate reads "Not yet tested".';
  } else {
    const ok = Object.entries(v.paises || {}).filter(([, r]) => r && r.etiqueta_pais === 'reliable').map(([id]) => PAIS_NOMBRE(manifest, id));
    cola = ok.length === 0
      ? 'In this test neither country passed P2 and P2b, so no area is labelled "reliable": the pre-2012 estimates read "indicative".'
      : `In this test only ${lista(ok)} passed P2 and P2b, so only areas in ${lista(ok)} that meet the other conditions can be labelled "reliable".`;
  }
  return '"Reliable" is shown only where the country passed the sensor-agreement tests P2 and P2b (P2b is the three-state version of the unusual-month test and decides only this label), ' +
    'the area covers at least one 3-degree block (about 300 km), its typical number of MODIS detections per month is at least 10 and falls in a count class that also passed, and the months are estimated from Terra and Aqua together. ' +
    'Smaller areas, such as the Puebla / Popocatépetl and Paraná Delta presets, can at most be "indicative" even in a country that passed, and months estimated from Terra alone (Dec 2000 to Jun 2002) are always "indicative". ' +
    cola;
}

/* ---------- data gaps (read from manifest.huecosModis; number-free fallback) ---------- */
function textoDiasFaltantes(h) {
  const r = h && h.regla_datos;
  if (!r || !isNum(r.dias) || !isNum(r.en_firms_missing_data) || !isNum(r.no_en_firms_missing_data)) {
    return 'Missing MODIS days: besides the days covered by official outage notices, some days of missing Terra or Aqua data (2002 to 2018) were flagged by our data rule (a platform reported no detections while the other was active); not all of them are listed in the FIRMS missing-data table.';
  }
  const consulta = fechaLarga(h.consulta_firms_utc);
  const ejemplo = (r.no_en_firms || []).map((x) => fechaLarga(x[1])).filter(Boolean).slice(-1)[0];
  return `Missing MODIS days: besides the days covered by official outage notices, ${r.dias} days of missing Terra or Aqua data (2002 to 2018; ${r.terra} Terra, ${r.aqua} Aqua) were flagged by our data rule (a platform reported no detections while the other was active). ` +
    `${r.en_firms_missing_data} of those ${r.dias} days are also listed in the FIRMS missing-data table (standard products${consulta ? `, queried ${consulta}` : ''}) and ${r.no_en_firms_missing_data} ${r.no_en_firms_missing_data === 1 ? 'is' : 'are'} not` +
    `${ejemplo ? ` (for example ${ejemplo})` : ''}; ${r.no_en_firms_missing_data === 1 ? 'that one is' : `those ${r.no_en_firms_missing_data} are`} not confirmed by FIRMS.`;
}

function textoMesesIncompletos(h) {
  const base = 'Incomplete months: a month is flagged incomplete only when our availability table lists a day on which no MODIS platform had data; a day with only one platform missing is covered by the other. ' +
    'For the Terra-only period (Dec 2000 to Jun 2002) the table holds official outage notices only, because the data rule needs a second platform. ';
  const f = h && h.firms_sin_marcar_en_tabla;
  const rangos = f && Array.isArray(f.terra) ? f.terra : [];
  const dias = rangos.map(rangoLegible).filter(Boolean);
  if (!dias.length) {
    return base + 'The FIRMS missing-data table may list further days without Terra data in that period that the calendar does not flag; a low count there may reflect missing data.';
  }
  const meses = mesesLegibles(rangos);
  return base + `The FIRMS missing-data table lists further days without Terra data in that period (${lista(dias)}) that the calendar does not flag, ` +
    `so ${meses ? `${meses} ${meses.includes(' and ') ? 'are' : 'is'} not marked incomplete` : 'those months are not marked incomplete'} even though a low count there may reflect missing data, and the 2002 total in the annual trend can come out low.`;
}

export function construirNotas(manifest) {
  const status = estadoValidacion(manifest);
  const resultado = textoResultado(manifest);
  const huecos = (manifest && manifest.huecosModis) || null;

  const validacion = [];
  if (status) validacion.push(status);
  validacion.push(...cifrasClave(manifest));
  if (resultado) validacion.push(resultado);
  validacion.push(`Prior exposure. ${EXPOSURE_DECLARATION}`);
  validacion.push(EXPOSURE_ADDENDUM);
  validacion.push(COLLECTION_ERRATUM);
  validacion.push(reglaEtiquetas(manifest));
  validacion.push(
    'Test months in which the FIRMS missing-data tables (standard products of Terra, Aqua, NOAA-20 and Suomi NPP) list three or more days ' +
    'without data are excluded from the test. The tables were queried on 15 Nov 2026 and no month of the 2019 to 2021 window met this rule, ' +
    'so none was excluded.');

  const sections = [
    {
      id: 'series',
      title: 'How the series is built',
      items: [
        'Series: Terra only (Dec 2000 to Jun 2002), Terra and Aqua (Jul 2002 to Dec 2011), Suomi NPP (Jan 2012 to Mar 2018), NOAA-20 (Apr 2018 onward; near-real-time months are provisional and can change).',
        'From 2012 the counts are VIIRS detections as observed. Before 2012 the series uses MODIS detections converted to VIIRS-equivalent counts; those values are estimates, drawn hatched and shown with an 80 % range.',
        'Each MODIS detection is multiplied by a weight that depends on the country, the calendar month, day or night, the 1 degree cell and the era (Terra alone, or Terra and Aqua together). The weights are estimated from the years when MODIS and VIIRS flew together (Feb 2012 to Dec 2018) and are smoothed toward simpler values where a cell has few detections.',
        'A static mask removes volcano and industrial sources (cells where Suomi NPP detected non-vegetation heat sources in 2012 to 2018, plus their neighbours). The switch above shows what it excluded: in the Puebla / Popocatépetl preset, for example, "All thermal anomalies" adds back the detections that the mask removed.',
        '"Unusually high" means above the 90th percentile of the same calendar month in the VIIRS years, the year itself left out; "unusually low" means below the 10th, only where the typical value of that month is at least 5. When the 80 % range straddles the line the month is "possibly unusual".',
      ],
    },
    {
      id: 'counts',
      title: 'Counts, dates and areas',
      items: [
        'Counts are satellite hotspot detections, not individual fires. Zero detections do not mean zero fire (clouds, smoke and overpass timing matter).',
        'Dates are UTC as given by NASA FIRMS and are whole months, so the counts and the CSV agree exactly.',
        'Areas are a spatial approximation. Your shape is turned into 0.1 degree cells (about 11 km) and a cell is used when its center falls inside the shape, so edges are coarse and the cells can reach a few kilometres beyond what you drew. A cell counts as inside the processed coverage when its center is inside the country outline or when the outline (coast or border) crosses it; such a cell is used whole, but it only holds detections inside the country. Outside Mexico and Argentina the app shows "outside processed coverage", never zero.',
      ],
    },
    { id: 'validation', title: 'Validation', items: validacion },
    {
      id: 'limits',
      title: 'Known limitations',
      items: [
        ACTIVITY_BIAS_TEXT,
        BAHIA_BLANCA_TEXT,
        'The static mask is incomplete. In Argentina it removes only part of the non-vegetation detections that MODIS reports, so some of them stay in the counts.',
        textoDiasFaltantes(huecos),
        textoMesesIncompletos(huecos),
        'Raw annual totals mix MODIS (until Dec 2011) and VIIRS (from Jan 2012): they are not comparable across 2012. The trends shown are descriptive, not tested results.',
      ],
    },
    {
      id: 'use',
      title: 'Intended use',
      items: [
        'This calendar is for historical analysis, research and planning. It is not a tactical or real-time response tool: the NASA LANCE disclaimer says that using these data for tactical decision-making, or to inform about conditions at a local scale, is not advised (https://www.earthdata.nasa.gov/data/projects/lance/disclaimer).',
      ],
    },
    {
      id: 'sources',
      title: 'Data sources and references',
      items: [
        'MODIS active fire detections, Terra and Aqua (1 km): NASA FIRMS standard archive MCD14ML (DOI https://doi.org/10.5067/FIRMS/MODIS/MCD14ML; the landing page of this DOI was unavailable on 15 Nov 2026), whose files carry the version labels 6.2 (2000–2017), 6.03 (2018–2022) and 61.03 (2023 onward), that is Collection 6 for 2000–2022, including the 2019–2021 test years, and Collection 6.1 from 2023 under the MCD14ML naming convention; near-real-time MCD14DL, Collection 6.1 (DOI https://doi.org/10.5067/FIRMS/MODIS/MCD14DL.NRT.0061). Complementary references to the NASA LP DAAC MODIS Collection 6.1 fire products, which we did not download: MOD14 (Terra) https://doi.org/10.5067/MODIS/MOD14.061 and MYD14 (Aqua) https://doi.org/10.5067/MODIS/MYD14.061',
        'VIIRS 375 m, Collection 2: NASA FIRMS standard files VNP14IMGTML (Suomi NPP) and VJ114IMGTML (NOAA-20), which have no FIRMS DOI; source products VNP14IMG v002 (https://doi.org/10.5067/VIIRS/VNP14IMG.002) and VJ114IMG v002 (https://doi.org/10.5067/VIIRS/VJ114IMG.002). Near-real-time: VNP14IMGT_NRT.002 (https://doi.org/10.5067/FIRMS/VIIRS/VNP14IMGT_NRT.002) and VJ114IMGT_NRT.002 (https://doi.org/10.5067/FIRMS/VIIRS/VJ114IMGT_NRT.002).',
        'Algorithms: Giglio, Schroeder and Justice (2016), Remote Sensing of Environment 178, 31-41 (https://doi.org/10.1016/j.rse.2016.02.054); Schroeder, Oliva, Giglio and Csiszar (2014), Remote Sensing of Environment 143, 85-96 (https://doi.org/10.1016/j.rse.2013.12.008).',
      ],
    },
  ];

  return {
    heading: 'Method notes',
    summary: 'Method notes, validation, limits and sources',
    sections,
    items: sections.flatMap((s) => s.items),
    status,
    scenario: escenarioPreregistrado(manifest),
  };
}

/** Markers still present in the text the page renders for this manifest. Empty = nothing pending. */
export function marcadoresPendientes(manifest) {
  const n = construirNotas(manifest);
  const todo = [n.heading, n.summary, ...n.items].join('\n');
  return [...new Set(todo.match(PENDING_MARKER_RE) || [])];
}

/** Splits a text into plain and URL parts (a trailing full stop is not part of the URL). Pure: tested in Node. */
export function partirEnlaces(texto) {
  const partes = [];
  const re = /https?:\/\/[^\s;,)]+/g;
  let i = 0, m;
  while ((m = re.exec(texto))) {
    let url = m[0];
    let cola = '';
    while (/[.:]$/.test(url)) { cola = url.slice(-1) + cola; url = url.slice(0, -1); }
    if (m.index > i) partes.push({ t: 'text', v: texto.slice(i, m.index) });
    partes.push({ t: 'url', v: url });
    if (cola) partes.push({ t: 'text', v: cola });
    i = m.index + m[0].length;
  }
  if (i < texto.length) partes.push({ t: 'text', v: texto.slice(i) });
  return partes;
}

function llenarItem(li, texto, doc) {
  for (const p of partirEnlaces(texto)) {
    if (p.t === 'url') {
      const a = doc.createElement('a');
      a.href = p.v;
      a.textContent = p.v;
      a.rel = 'noopener noreferrer';
      a.target = '_blank';
      li.append(a);
    } else {
      li.append(doc.createTextNode(p.v));
    }
  }
}

/** DOM: replaces the heading, the summary and the sections of the Method notes block. The key-value rows are filled by estado-ui.js. */
export function aplicarNotasMetodo(manifest, doc = document) {
  const n = construirNotas(manifest);
  const h = doc.getElementById('h-about');
  if (h) h.textContent = n.heading;
  const resumen = doc.querySelector('#about summary');
  if (resumen) resumen.textContent = n.summary;
  const cuerpo = doc.getElementById('notes-body');
  if (cuerpo) {
    cuerpo.replaceChildren(...n.sections.flatMap((s) => {
      const h3 = doc.createElement('h3');
      h3.textContent = s.title;
      h3.id = `notes-${s.id}`;
      const ul = doc.createElement('ul');
      ul.className = 'plain';
      ul.setAttribute('aria-labelledby', h3.id);
      for (const t of s.items) {
        const li = doc.createElement('li');
        llenarItem(li, t, doc);
        ul.append(li);
      }
      return [h3, ul];
    }));
  }
  return n;
}
