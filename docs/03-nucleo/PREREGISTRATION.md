> Frozen copy: after these two lines, this file is byte for byte `docs/03-nucleo/PREREGISTRATION-draft.md` as committed in git tag `prereg-v1` @ 90e10ce, before the held-out test was run; its own "DRAFT" status lines belong to that frozen text. These two lines were added by Claude Code (SI-generated, AI).
> sha256 of everything below these two lines: 2a9ee27e02f2270cb9d02ee5671285478702ac0225f2e58d366e1059486bd1ba (check: `tail -n +3 PREREGISTRATION.md | sha256sum`).
# PREREGISTRATION (DRAFT): sensor-swap test for the harmonized MODIS→VIIRS hotspot calendar

> **Status: DRAFT. Not frozen and not published.** The team fixed the thresholds and the open choices on **2026-11-15 ~13:45 (UTC−6), lot 3**, before the held-out run (ADR-0014). The freeze is planned for **~15:00 (Sun 15 Nov 2026, UTC−6)**. This draft becomes `PREREGISTRATION.md` once the hashes are recorded and the git tag `prereg-v1` is created. No held-out (2019–2021) test has been run.
> SI-generated (AI): Claude Code drafted this text during the event. The team reviews it, and the team makes every decision in it.
> Units are **hotspot detections, not fires**. All dates are UTC.

## 1. Question
After harmonization, does the sensor of origin still matter? We test whether converting MODIS (Terra+Aqua) detections into **VIIRS-equivalent** counts produces the same monthly "unusual / typical" flags as VIIRS itself. The comparison is VIIRS against harmonized MODIS, measured against the ceiling set by swapping one VIIRS for its twin (NOAA-20 vs Suomi NPP).

**Central question (A, "sensor-swap"; ADR-0012):** Does a harmonization calibrated by country, overpass clock (Terra morning, Aqua afternoon), month and day/night on the 2012–2018 overlap make the monthly hotspot-detection calendar (level, seasonality and unusual months) stop depending on the sensor of origin in Mexico and in Argentina? From which spatial scale on?
- Answered by the single held-out test in §4 (twin ceiling, by country and by scale), with the verdict rule in §5.

**Secondary pre-registered question (C; ADR-0012):** Which part of the equivalence (level, season, day/night) transfers from one country to the other?
- Answered by T1/T2 in §4 (T1 transfers all parameters; T2 transfers the shape and takes the level from the target country), with the factors by clock, month, day/night and country and their CIs.

**Pre-registered result texts (fixed 2026-11-15 ~13:45 UTC−6, before the held-out run).** Exactly one is used, chosen mechanically from `verdict.json`. A country "passes" iff `veredicto.por_pais.<country>.<escala_publicada_7gbis>.RT05_bloque3` is `true` (RT05_bloque3 = P2, P3 and P4 all pass at the 3° block scale, §5; the scale is the published one, E1c, or E1b only if J2 at block scale failed, 7g-bis); `null` counts as not passing.

| Case in `verdict.json` | Text (used verbatim) |
|---|---|
| **A** · both countries pass P2, P3 and P4 | "In the 2019–2021 held-out test, harmonized MODIS met our pre-specified sensor-agreement, uncertainty-coverage and baseline-improvement criteria at the 3° block scale in the countries that passed. We report where these results support historical comparisons and where they do not." |
| **B** · one country passes, the other fails | "Harmonized MODIS met the pre-specified validation criteria at the 3° block scale in one country, but not the other. Talavera Orbital makes that difference visible and labels historical estimates according to their demonstrated reliability." |
| **C** · both countries fail | "In our held-out 2019–2021 test, harmonized MODIS did not meet the pre-specified criteria for interchangeable unusual-month classifications at the 3° block scale. The calendar remains useful for exploring historical hotspot detections, but its pre-2012 anomaly flags are indicative rather than validated." |

- **Selection rule:** a country passes iff `veredicto.por_pais.<country>.<escala_publicada_7gbis>.RT05_bloque3` is `true`; `null` counts as not passing. Count the passing countries among `mexico` and `argentina` (2 → A, 1 → B, 0 → C). The other scale's RT05_bloque3 is reported but never used to choose the text. The text is not edited after the run; P5, J1/J2, T1/T2 and the "reliable" label are reported with their own pre-registered labels (§4, §5).
- **Every use of the selected text is accompanied by the prior-exposure statement of §2.**

## 2. Data and partition (no leakage)
- **Source:** NASA FIRMS standard-processing active-fire detections: MODIS Collection 6.1 (Terra, Aqua) and VIIRS 375 m (Suomi NPP, NOAA-20). Short names, versions and DOIs are listed in `docs/02-datos/fuentes.md`.
- **Filter:** standard processing; all confidence levels; detections inside the static volcano/industry mask are removed. The mask was built from S-NPP `type≠0` detections from **2012-01-20 to 2018-12-31**, using 0.01° cells plus their 3×3 neighbours. 2012-01-20 is used only to build the mask.
- **Calibration:** **2012-02-01** → 2018-12-31, by country (Mexico, Argentina), with S-NPP as the target. January 2012 is a partial month and is not used for calibration.
- **Test window (W2):** **2019-01-01 → 2021-12-31**, run **once**.
  - Target: **NOAA-20**, the VIIRS series shown in the app from April 2018.
  - Witness: **Suomi NPP**, which the series does not use after March 2018.
  - Sub-analysis: W1 (2019-01 → 2020-02), reported but not used for the verdict.
- **Prior exposure (it accompanies every result text; confirmed by the team 2026-11-15 ~14:25 UTC−6):** "Before the test, we had inspected aggregate diagnostics that include 2019–2025 for Terra, Aqua and the VIIRS satellites: country-level annual counts and ratios, the yearly median overpass time, a country-level monthly calendar of raw detections for Mexico (2000–2025), and 2013–2024 pooled monthly, day/night, FRP-threshold and 1°-cell ratio distributions (H0/H2 QA); the NOAA-20 series itself, which the app displays from April 2018 onward, was visible at full resolution throughout development. No cell-month or block-month comparison of harmonized MODIS against VIIRS for 2019 or later was computed before the frozen run."
- **Known difference:** the whole test window uses MODIS file version `6.03`, while the product era (2000–2011) uses `6.2`. Check C-V (§4) looks for a step at the version change.

## 3. Method under test (frozen in `src/nucleo/`)
- Stratified, shrunken ratio with clocks: VIIRS-eq = k(clock, month, day/night, country) × s(1° cell, day/night) × MODIS detections.
  - Clock TA (Terra+Aqua) is used from Jul 2002; clock T (Terra only) before that.
  - Single-platform days fall back to that platform (rule R1).
- **Baseline M1:** the global count ratio S/(T+A) per country (`nucleo.baseline.global_count_ratio`, the in-event rewrite of the kit's `razon_conteos`, golden-tested bit-identical), using the same predictor.
- **Controls:** M0 (no harmonization), which must fail, and M1 with Aqua only (pilot reference).
- **Intervals:** 80 % empirical intervals from leave-one-year-out residuals, by class of predicted value × era × country (a single residual model, I-03, ratified in lot 3).
- **Method choices confirmed before the freeze (lot 3, 2026-11-15):**
  - The method of ADR-0003 is kept as implemented. The empirical-Bayes Gamma-Poisson shrinkage and its estimated λ are reported only as complementary evidence; they are not used by the method under test.
  - The unusual-flag rule of ADR-0006 is kept.
  - The plan-v3 "noise-floor ratio" R is reported descriptively only; P2 decides.
  - No pixel-area factor is applied.
- **Known limitation declared before the test:** level bias depends on activity. In a development check (calibration 2012-02 → 2015-12, comparison with S-NPP 2016–2018; run EXP-002, not the held-out test), the 1° cell-months with a non-zero harmonized estimate were split into thirds by that estimate (bias = ΣS/ΣŜ − 1, S = observed S-NPP, Ŝ = estimate). In the lowest third the observed counts were about 1.3–1.5 times the estimate (the estimate is **too low**); in the highest third the estimate was **too high by up to about 5 %**. Cell-months with Ŝ = 0 are not in these thirds and add further underestimation at low activity. This is consistent with regression toward the mean when an estimate rests on few MODIS detections. It is declared as a limitation; the method is not recalibrated for it (see `docs/03-nucleo/nota-sesgo-actividad.md`).

## 4. Tests (the pre-registered core)
**Bootstrap:** resampling unit = **3° block × year**, 1,000 replicates, seed 42. 6° × year is reported as a sensitivity. Results are also reported by year, and for Argentina without 2020 (about 55 % of the W2 detections). The effective sample is **3 fire seasons**.

**Months excluded from all tests (data-gap rule, fixed before the freeze):**
- Rule: a month of 2019–2021 is excluded from **every** test if Terra, Aqua, NOAA-20 or S-NPP has **≥ 3 days without data** in the FIRMS `/api/missing_data/` **Standard** tables.
- Query: `https://firms.modaps.eosdis.nasa.gov/api/missing_data/?action=fetch_data`, **2026-11-15T19:51:09Z**, HTTP 200, 24,401 bytes, SHA-256 `60ab8a4d35394d116378ba11747f6a4286d7303c9a8a77b8ec7ac01757f1b3e1` (availability metadata only, not detections). Report: `docs/02-datos/huecos-firms-missing-data.md`.
- Result: **0 days** with missing data in W2 for the four platforms, so **0 months** are excluded. Frozen list: `meses_excluidos_huecos_viirs: []` (verified).

**Unusual flag (identical to the app, rule 6c-q):**
- Base: the same calendar month in the VIIRS series 2012-02 → 2018-12 (S-NPP until 2018-03, NOAA-20 after), excluding the evaluated year (N = 7; January N = 6).
- Quantile: Hyndman–Fan **type 6**, clamped to the minimum and maximum.
- Strict inequalities: high if value > p90; low if value < p10, and only when p10 > 0.
- A month gets no flag if the base median is < 5.
- Expected flag rate with no regime change: about 12.5 % per side.
- Python/JS parity file: `tests/paridad_marca.json`.

| ID | What | Unit | Metric | Pass threshold (**fixed 2026-11-15 ~13:45 UTC−6, lot 3; unchanged from D2-S-07 table 4.3**) |
|---|---|---|---|---|
| **P2** | Same anomalies | 3° block × month, base median ≥ 5 | κ_cross = Cohen's κ of the **three-class** U1 flag (high / none / low), NOAA-20 vs harmonized MODIS; κ_twin = NOAA-20 vs S-NPP on the same block-months | κ_cross ≥ **0.60** and κ_cross ≥ **0.75** × κ_twin (point estimates; 95 % CI reported) |
| **P2b** | Three-state flag (unusual / possibly unusual / typical) | as P2, using the 80 % interval of harmonized MODIS | precision of "unusual" and "typical" against NOAA-20; % indeterminate; 80 % interval coverage at 3° | precision ≥ **0.80** / ≥ **0.95**, coverage in **[0.75, 0.85]**, indeterminate ("possibly unusual") ≤ **0.50** (7c-bis). This test decides only the "reliable" label |
| **P3** | Honest uncertainty | 1° cell × month, evaluable cell-months (≥ 200 Terra+Aqua detections in calibration); observed S = 0 is included. **Verdict population: cell-months with Ŝ > 0** (`p3.poblacion: excluye_s0`). Where Ŝ = 0 the interval is (0, ∞) and always covers. **Reported in parallel:** the coverage on the full population (including Ŝ = 0) and the number of excluded Ŝ = 0 cell-months; each coverage with its 95 % CI | empirical coverage of the 80 % interval against NOAA-20 (point estimate) | in **[0.75, 0.85]** |
| **P4** | Better than baseline | 1° cell × month | skill = 1 − MdALE_method / MdALE_M1, with ALE = \|log((S+1)/(Ŝ+1))\| | lower bound of the 95 % CI **> 0** |
| **J1** | Jul-2002 splice (internal consistency) | country × month, **2003-01 → 2011-12**, excluding the months with any day without Terra (4 months, as implemented) | mean log(H_TA / H_T), 95 % CI by year bootstrap | \|mean\| ≤ **0.10**, CI inside ±**0.15**, each year ≤ **0.15** |
| **J2** | Apr-2018 splice (twins) | 3° block × month (decides); country × month (check only) | mean log((NOAA-20+1)/(S-NPP+1)) | \|mean\| ≤ **0.05** at block level |
| **T1 / T2** | Transfer Mexico ↔ Argentina | 1° cell and 3° block × month | B = ΣS/ΣŜ, G = MdALE_transfer / MdALE_local, Δκ = κ_transfer − κ_local. T1 transfers all parameters; T2 transfers the shape and takes the level from the target country's own overlap | transferable if \|log B\| ≤ **0.10**, G ≤ **1.15**, Δκ ≥ **−0.05** |
| **P5** | Terra-only era (Dec 2000 → Jun 2002), **own verdict** | as P2, P2b and P3, with the Terra-only predictor H_T (clock-T factors applied to Terra detections only, as in J1) and the clock-T 80 % intervals, on the same block-months and cell-months; months with any day without Terra are excluded | as P2, P2b and P3. References: M1 with Terra (global S/T ratio) and raw Terra | **same criteria as P2, P2b and P3** (`umbrales.P5.criterio: mismos_que_P2_P2b_P3`): P5 passes if all three pass with H_T. The verdict applies to that era only; **the Terra-only era stays "indicative (Terra only)" even if P5 passes** |
| P1 | Level (consistency check; **does not decide**) | country, window and year | B = ΣNOAA-20 / ΣŜ, 90 % CI | reference band: CI inside [0.90, 1.11]; each year in [0.80, 1.25] |
| C-V | MODIS file-version check | country × month, 2016–2018 | Pettitt test on the deseasonalized log(S-NPP/(T+A)); step at 2018-01 | reported |

**Count classes (I-05) and minimum AOI (M1) — active:**
- P2 and P2b are also computed by expected MODIS count class: median monthly Terra+Aqua count of the unit in calibration, classes **< 10, 10–30, 30–100, ≥ 100** (1° cells and 3° blocks pooled per class), with LOYO residuals by class (`pruebas.clases_I05: run`). The verdict reports P2/P2b and the "reliable" label by class.
- **M1 (minimum AOI):** an AOI whose median monthly MODIS detection count is **< 10** shows its pre-2012 estimate hatched, with "too few MODIS detections here for a reliable pre-2012 estimate". In the Terra-only era (2000-11 → 2002-06) the median uses the Terra count, the only MODIS in that era (team-ratified 2026-11-15 ~14:25 UTC−6); that era is "indicative" in any case.
- Rule 3b of I-05 stays in force: "reliable" only for AOIs of at least one 3° block (≥ 900 cells of 0.1°) in a country that passed P2 and P2b.

**Published model (7g / 7g-bis):**
- The tested model (E1c scale) is the one published.
- P1–P3 are also computed in the same run on the **E1b** scale (S-NPP × f and MODIS × k × f, with f = ΣNOAA-20/ΣS-NPP over Apr–Dec 2018). E1b is published **only if J2 (block) fails**.
- If J1 fails, the Terra-only era is labelled "indicative (Terra only), not continuous with Jul 2002".
- Any other change after the test is published as "adjusted after the test; not re-validated".

**Reported, never decisive** (status = `config/validacion.yaml → pruebas`; a test set to `not_run` is reported as "not run"):
- **S1–S7 · sensitivities** (D2-S-07 §4.3; ADR-0005 7b: 2022–2025 is a reported stress test that does not decide; ADR-0005 7e and ADR-0004: 1° cell and country are only reported, figures are validated at ≥ 0.5°, de-duplication C2 is only a sensitivity). S1 break or drift of the ratio · S2 seasonal pattern · S3 P2/P2b at 1° cell and country · S4 stress test 2022–2025 (RT-06) · S5 filter `type=0` · S6 inverse direction · S7 witness (S-NPP) as target. Status: `not_run`.
- **S8 · trend: run, reported only, not decisive (ADR-0012 option 2).** Seasonal Sen slope of log(x + 1) per year, by 3° block, for the target VIIRS series (NOAA-20 in the test; S-NPP in development runs, since NOAA-20 starts in Apr 2018) and for H_TA (also M1 and M0); block-median difference with a 95 % block-bootstrap CI and the country aggregate. `s8.decide: false`: it never enters the verdict.
- **R · noise-floor ratio (plan v3):** descriptive only.

## 5. Verdict rule
- "RT-05 is met at 3° block scale in country Y in a forward test on 2019–2021" if P2, P3 and P4 pass in Y.
- The **"reliable"** label requires P2 and P2b (7c-bis, including the coverage and indeterminate conditions) in the country on the published scale (7g-bis), rule 3b and a reliable count class (§4); it does not require P3 or P4. The reference rule is `etiqueta_estimacion()` in the script; the class-level field `clases_I05.<scope>.<class>.etiqueta` in the verdict is an input to that rule, not the label of an AOI.
- The Terra-only era stays **"indicative"** whatever the result, including a P5 pass.
- The public result text is selected from §1 by the number of countries that pass.
- A failure is reported as a negative finding. Example: "a count-based harmonization leaves sensor-dependent anomalies at ≤ 300 km in Mexico".

**Original pre-registered expectation** (ADR-0005, commit `5bc3104`, 2026-11-14 20:54 UTC−6; translated, all six points, unchanged in substance):
> - **Argentina:** probably passes P2 at 3° (paired κ 0.674, ratio 0.84).
> - **Mexico:** probably **fails** P2 at 3° (κ 0.553 < 0.60, ratio 0.68 < 0.75).
> - **1° scale:** both countries probably fail P2.
> - **P5 (Terra only):** probably does not pass P2b.
> - **Transfer T1:** probably fails on level.
> - **P3:** coverage against NOAA-20 is probably lower than against S-NPP.
> - If anything fails, it is reported as is.

**Revision (2026-11-15, before the held-out run)** — decided by the team at ~13:45 UTC−6, before any computation on the held-out window:
- **Revised expectation:**
  - Mexico probably fails P2 at 3°.
  - Argentina is borderline at 3° and probably fails P2.
  - P4 probably passes in Mexico and fails in Argentina.
  - We do not attribute to the method any improvement in which months are flagged unusual: in development the method improves the **level**, not the flags (Δκ against M1 ≈ 0 in both countries).
  - The other original items (1° scale: both countries probably fail P2; P5 probably does not pass P2b; T1 probably fails on level; P3 coverage against NOAA-20 probably lower than against S-NPP) are unchanged.
- **Reason:** the development pilots EXP-003 to EXP-005 (calibration 2012-02 → 2015-12, evaluation 2016–2018, rule 6c-q). Exploratory development figures, not results: Mexico κ_cross 0.54, ratio to the twin ceiling 0.70; Argentina κ_cross 0.59–0.60, ratio 0.73–0.78 (threshold 0.75); P4 skill Mexico +0.10 [+0.06, +0.14], Argentina −0.02 [−0.05, +0.02].
- **This revision changes no threshold, no test and no verdict rule.**
- The original wording says "before any 2019+ look"; what had actually been inspected before the test is described by the prior-exposure statement in §2.

## 6. Script, configuration and freeze
- **Script:** `src/nucleo/validacion_rt05.py`. **Flag rule:** `src/nucleo/validacion_marca.py`. **Configuration:** `config/validacion.yaml`.
- **Configuration values expected in the frozen YAML (lot 3; checked before `--registrar-hashes`):** `umbrales.pendiente_lote3: false`; thresholds as in §4; `p3.poblacion: excluye_s0`; `marca.kappa: u1_3clases`; `pruebas.P5: run` with `umbrales.P5.criterio: mismos_que_P2_P2b_P3`; `pruebas.clases_I05: run` with cuts [10, 30, 100]; M1 threshold 10; `meses_excluidos_huecos_viirs: []`; `j1.ventana: [2003-01-01, 2011-12-31]` with `excluir_meses_con_hueco_terra: true`; `modos.prueba.calibracion` from 2012-02-01; `s8.decide: false`.
- **Test command (run once; needs the team's explicit authorization):**
  `flock data/.pesado.lock .venv/bin/python src/nucleo/validacion_rt05.py --modo prueba --prueba-unica --exp EXP-NNN`
- **Built-in guard.** The script refuses to run in test mode unless all of these hold:
  - the `--prueba-unica` flag is given;
  - the git tag `prereg-v1` exists;
  - the SHA-256 of the `src/nucleo/` tree, of the YAML and of the frozen factor and interval tables match `config/validacion.hashes.json` as committed in the tag;
  - no threshold is still marked pending;
  - the real factor module (not the development stub) is in use;
  - no earlier test run exists.
- **Development mode** calibrates 2012-02 → 2015-12 and evaluates 2016–2018 only. It asserts that no date ≥ 2019-01-01 is read.
- **Hashes:** recorded in `config/validacion.hashes.json` (tree hash of `src/nucleo/`, SHA-256 of `config/validacion.yaml`, of the frozen `factores_*` and `intervalos_*` tables and of the test inputs), committed in the commit that carries the git tag `prereg-v1`. The tag identifies that commit; this file does not repeat it.

## 7. Freeze procedure (planned ~15:00, Sun 15 Nov 2026, UTC−6)
1. The team fixed the thresholds and the open choices on 2026-11-15 ~13:45 (lot 3, ADR-0014). They are written in `config/validacion.yaml`, then `pendiente_lote3: false` is set. The team confirmed the prior-exposure statement of §2 on 2026-11-15 ~14:25 UTC−6; no pending-confirmation line remains in this file.
2. Run `.venv/bin/python src/nucleo/validacion_rt05.py --registrar-hashes`. This writes `config/validacion.hashes.json`.
3. Run one development pass to confirm that the frozen tree executes.
4. Commit, then `git tag prereg-v1`. Publish this file, with the hashes filled in, in the public repository.
5. Make `src/nucleo/` and the YAML read-only until the single run. Any change requires a documented re-freeze before the single run.
