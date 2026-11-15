// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// datos-config.js - the single CONFIG object of the frontend. Only RELATIVE paths, no keys.

export const CONFIG = Object.freeze({
  // Where the exporter (src/exportar_demo.py) writes the data. Relative to index.html. It is the ONLY source:
  // the app knows no fixture (the SYNTHETIC fixture lives only in app/tests/ and the tests serve it
  // mounted on /data/; ADR-0009: never SYNTHETIC in public).
  DATA_BASE: 'data/',
  // Version of the data contract (app/data/CONTRATO-DATOS.md, manifest.contrato) that this app can read.
  CONTRACT_VERSION: 1,

  // CSV cap. The wave order marked it "pending lot-2 decision"; lot 2 settled it:
  // 500000 rows (ADR-0010 "CSV cap"), message "narrow the date range". Change only with an ADR.
  CSV_MAX_ROWS: 500000,
  // Cap of 1-degree tiles per AOI and of cells per box (browser protection).
  MAX_TILES: 150,
  MAX_CELLS: 60000,
  // Simultaneous requests while loading tiles.
  FETCH_CONCURRENCY: 6,

  // Start of the series (ADR-0002: Nov 2000 is out).
  SERIES_START: { y: 2000, m: 12 },


  BASEMAP: {
    enabledByDefault: true,
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 12,
    // After this many tile errors it is switched off and the user is told (the app keeps working without a basemap).
    errorLimit: 3,
  },

  MAP: { center: [5, -80], zoom: 3, minZoom: 2 },

  // Module that mounts the analysis views (estado-arranque.js imports it and calls montar({container, store, datos, config})).
  // './tendencia-enlace.js' mounts the calendar (./calendario-montar.js, in #calendar) and the descriptive annual trend
  // (./tendencia-montar.js, in #trend) with ONE call, without touching the shell. Calendar only: './calendario-montar.js'.
  // null = both sections stay "pending".
  CALENDAR_MODULE: './tendencia-enlace.js',

  // ---- Reliability of the pre-2012 estimates (js/fiabilidad.js) ---------------------------------------------------------
  // The exporter summarizes the verdict of the single pre-registered test in manifest.verdict (null until the test is run).
  // With verdict = null every estimated month shows "not yet tested"; with a verdict it shows "reliable" or "indicative"
  // (rule I-05 3b: the country passed P2 and P2b, the area covers at least one 3-degree block, and the era is not Terra only).
  //
  // M1 (rule "too few MODIS"): minimum EXPECTED MODIS detections per month of an area, one number per era:
  //   T  = Terra only (Dec 2000 to Jun 2002)      TA = Terra + Aqua (Jul 2002 to Dec 2011)
  // Expected count = median monthly count of the area (outside the static mask, zeros included, incomplete months left out) over
  // the calibration window below. An area under the minimum gets the notice "Too few MODIS detections here for a reliable
  // pre-2012 estimate" and its estimated months are "indicative".
  //   The number is the one frozen in the pre-registration (config/validacion.yaml, umbrales.M1.min_modis_por_mes = 10; the same
  //   value travels in manifest.verdict.M1 and the e2e test checks that they agree). null would switch the rule off.
  MIN_MODIS_PER_MONTH: Object.freeze({ T: 10, TA: 10 }),
  RELIABILITY: Object.freeze({
    // Smallest area (cells of 0.1 degree) that can be "reliable". null = use manifest.verdict.min_celdas_aoi, which the
    // exporter fixes at 900 (30 x 30 cells = one 3-degree block, the scale of the test).
    MIN_AOI_CELLS: null,
    // Window of the expected MODIS count: the calibration window of the single test (config/validacion.yaml).
    EXPECTED_COUNT_WINDOW: Object.freeze({ from: Object.freeze({ y: 2012, m: 2 }), to: Object.freeze({ y: 2018, m: 12 }) }),
  }),

  // DESCRIPTIVE annual trend (ADR-0012, option 2): Sen slope of the annual totals of COMPLETE years.
  // Everything is configurable; none of these values is a decision threshold (the view runs no significance test).
  TREND: Object.freeze({
    // Minimum complete years to compute a slope (the kit warns "n < 8: very little power").
    MIN_YEARS: 8,
    // Confidence level of the slope interval: 0.8, 0.9, 0.95 or 0.99.
    CI_LEVEL: 0.95,
    // Serial-autocorrelation adjustment of the CI: 'hamed_rao' (as toolkit/sakit/tendencias.py) or 'none'.
    AUTOCORRELATION: 'hamed_rao',
    // Visible label next to every slope (the final wording is decided in H5).
    LABEL: 'descriptive trend, not a tested result',
  }),
});
