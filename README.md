# Talavera Orbital — Hotspot Calendar

**One calendar. Different sensors. Visible uncertainty.**

> **SI-generated (AI):** this README was drafted by Claude Code during the event and reviewed and approved by the team. See [Use of SI](#use-of-super-intelligence-si).
> Units are **hotspot detections, not fires**. For historical analysis, research and planning, not for real-time tactical response. This project is not endorsed by NASA.

**NASA Space Apps Challenge** · Challenge: *Harmonization of MODIS and VIIRS Hot Spots* · Team **Talavera Orbital** (Puebla, Mexico) · Local event: Bahía Blanca, Argentina (online)

**App:** https://zalvadork.github.io/talavera-orbital-hotspots/ · **Pre-registration:** [docs/03-nucleo/PREREGISTRATION.md](docs/03-nucleo/PREREGISTRATION.md) (byte-identical copy of the file frozen under git tag `prereg-v1` before the single test) · **Single-test result:** [runs/EXP-009/](runs/EXP-009/)

## Summary

Talavera Orbital puts NASA FIRMS hotspot detections from MODIS and VIIRS on one monthly calendar, in one unit, from the start of the MODIS record to today, for any area of Mexico and Argentina.

MODIS and VIIRS see heat differently: VIIRS has smaller pixels and detects smaller and cooler fires, and the satellites pass at different times of day. Raw counts therefore mix real change with sensor change. We convert each MODIS detection into **VIIRS-equivalent** detections with factors learned where both sensors overlap, by satellite clock, month, day/night and country, and every estimate carries its uncertainty range.

**A volcano is not a wildfire.** Popocatépetl and industrial heat sources are removed with a mask the user can switch off to see what it removed.

The challenge says harmonization succeeds when "the sensor of origin no longer matters". We turned that sentence into a test against the agreement between the twin VIIRS satellites, written down before running it and run once on 2019–2021, years held out from calibration.

**Result:** In our held-out 2019–2021 test, harmonized MODIS did not meet the pre-specified criteria for interchangeable unusual-month classifications at the 3° block scale. The calendar remains useful for exploring historical hotspot detections, but its pre-2012 anomaly flags are indicative rather than validated.

**Prior exposure (pre-registration §2, verbatim):** "Before the test, we had inspected aggregate diagnostics that include 2019–2025 for Terra, Aqua and the VIIRS satellites: country-level annual counts and ratios, the yearly median overpass time, a country-level monthly calendar of raw detections for Mexico (2000–2025), and 2013–2024 pooled monthly, day/night, FRP-threshold and 1°-cell ratio distributions (H0/H2 QA); the NOAA-20 series itself, which the app displays from April 2018 onward, was visible at full resolution throughout development. No cell-month or block-month comparison of harmonized MODIS against VIIRS for 2019 or later was computed before the frozen run."

**Addendum (identified after the freeze):** the prior-exposure statement above omits further quality-control tables we had also seen before the test: (1) type-0 detection counts for Terra, Aqua and S-NPP by calendar month, pooled over 2013–2024, in two approximate boxes (Puebla, Mexico, and south-western Pampas including Bahía Blanca, Argentina); (2) counts of detections within 5 km of the Popocatépetl crater by platform and source type, with first and last year, up to 2025; (3) the yearly median and 90th-percentile MODIS pixel size, 2000–2025, for each country; (4) whole-record (2000–2025) country-level detection counts by platform, file version, source type and confidence class. None of them compares harmonized MODIS with VIIRS. The pre-registration was not changed.

Full results by country are under [Validation](#validation).

## How to use

1. Open the app. No login, no installation.
2. Choose a preset area (**Puebla / Popocatépetl**, Mexico, or **Bahía Blanca**, Argentina), draw a rectangle on the map, or type latitude/longitude limits. The area snaps to the app's 0.1° grid and is shown snapped.
3. Choose a date range.
4. Read the **calendar** (years × months, in VIIRS-equivalent hotspot detections):
   - solid cells: observed by VIIRS;
   - hatched cells: estimated from MODIS ("estimated · Terra only" or "estimated · Terra+Aqua"), labeled "indicative"; the tooltip shows the uncertainty range, the raw count of each satellite and the satellite of origin;
   - dotted border and "P": provisional near-real-time data, later replaced by FIRMS;
   - "0 detected", "insufficient data", "partial month" and "incomplete (satellite outage)" are shown as such, never as zero activity.
5. Switch between **Counts** and **Anomaly** (percentile against the base years); each month is flagged **unusual**, **possibly unusual** or **typical**.
6. See the **critical season** of the area and **this month vs the historical median of the same month**, to date.
7. Use the toggle **"Vegetation fires only / All thermal anomalies"** to see what the volcano and industry mask removes.
8. Download the **CSV** (its rows match the count shown; very long requests ask you to narrow the date range) and the **PNG** of the calendar.
9. Outside the processed coverage the app says "outside processed coverage".

## Method notes

### One series, by era

| Period | Source in the series | Status in the app |
|---|---|---|
| Dec 2000 – Jun 2002 | Terra (MODIS), converted | estimated · Terra only · **indicative** |
| Jul 2002 – Dec 2011 | Terra + Aqua (MODIS), converted | estimated · Terra+Aqua · **indicative** |
| Jan 2012 – Mar 2018 | Suomi NPP (VIIRS 375 m), observed | observed |
| Apr 2018 – today | NOAA-20 (VIIRS 375 m), observed; near-real-time months provisional | observed / provisional |

All dates are UTC. NOAA-21 is used only for quality control. MODIS data after the orbital drift of Terra and Aqua are not used for calibration.

### Satellite clocks and the VIIRS-equivalent scale

- Terra observes in the morning and Aqua in the afternoon, so each clock gets its own MODIS→VIIRS factors.
- For each country, each MODIS detection gets a weight: **VIIRS-equivalent = k(clock, month, day/night, country) × s(1° cell, day/night) × MODIS detection**.
  - **Clock:** Terra only, Terra+Aqua, or the remaining platform alone on outage days (so nothing is counted twice).
  - **k** is a count ratio shrunk toward the country and day/night level when a month has few detections; **s** is a local multiplier shrunk toward 1.
- Factors are learned on the overlap with Suomi NPP, Feb 2012 – Dec 2018, separately for Mexico and Argentina; no later year was used to fit them.
- VIIRS counts with weight 1, so the unit of the whole calendar is "VIIRS-equivalent hotspot detections".
- **Uncertainty:** 80 % ranges from leave-one-year-out residuals, by clock and predicted level.
- **Baseline:** a single overall count ratio per country.
- All confidence levels are kept; MODIS and VIIRS confidence classes are not comparable and are not mapped onto each other.

### The mask: "a volcano is not a wildfire"

- Popocatépetl and industrial sources produce many thermal anomalies that are not vegetation fires.
- One static mask: 0.01° cells (plus their 3 × 3 neighbors) where Suomi NPP standard data flagged a volcano or other static source in 2012–2018.
- The same mask is applied to every sensor and to near-real-time data, which carries no source type.
- In Argentina the mask catches only part of the MODIS detections that FIRMS classes as non-vegetation (volcano, other static or offshore sources): about half in 2000–2011, when the calendar uses MODIS (details under Limitations).

### Area of interest

- Your area snaps to the 0.1° grid: the cells whose center is inside it are used, so the edges follow the grid rather than the outline. The snapped area is the one shown, counted and downloaded.
- Along coasts and borders, a cell counts as covered if its center is inside the country or the border crosses it; such a cell is used whole but only holds detections inside the country. Outside Mexico and Argentina the app shows "outside processed coverage", never zero.

### Calendar rules

- **Unusual:** above the 90th percentile (high) or below the 10th percentile (low) of the same calendar month in the base years, without the evaluated year; no flag when the base median is too small.
- For estimated months the rule is applied to both ends of the uncertainty range: unusual if both meet it, typical if neither does, possibly unusual otherwise.
- **Base:** VIIRS standard years, without near-real-time months.
- **Reliability labels for pre-2012 estimates:** "reliable" only for an area of at least one 3° block (900 cells of 0.1°) in a country that passed the pre-registered unusual-month agreement tests (P2 and P2b); "indicative" otherwise. Neither country passed, so every pre-2012 estimate is "indicative". Terra-only months are always "indicative".
- **Trends:** raw trends are descriptive only, shown with and without harmonization and labeled "Not comparable across 2012".

## Validation

**Status: run once.** The design, thresholds, code hash and factor tables were frozen in a pre-registration under git tag `prereg-v1` ([docs/03-nucleo/PREREGISTRATION.md](docs/03-nucleo/PREREGISTRATION.md)), and the single test was then run once ([runs/EXP-009/](runs/EXP-009/): `verdict.json`, `metricas.json`, `informe.md`, `manifiesto.json`). Any change after the run is published as "adjusted after the test; not re-validated".

- **Test years:** Jan 2019 – Dec 2021 (three fire seasons), run **once**, held out from calibration.
- **Target and witness:** the series uses NOAA-20 from April 2018, so Suomi NPP is free to act as an independent **twin** in the test years.
- **Sensor-swap vs twin-swap (the core test, P2):** at a primary scale of 3° blocks (~300 km), we compare the agreement of the unusual-month flags between NOAA-20 and harmonized MODIS with the agreement between NOAA-20 and Suomi NPP (Cohen's κ).
- **Verdict rule:** a country passes if P2, P3 and P4 all pass at the 3° block scale; the "reliable" label needs P2 and P2b.
- **VIIRS data gaps:** a 2019–2021 month is excluded from every test if Terra, Aqua, NOAA-20 or Suomi NPP has 3 or more days without data in the FIRMS standard missing-data tables. The query of 2026-11-15 19:51:09 UTC listed no such day: no month was excluded.
- **Uncertainty:** bootstrap by 3° block × year (95 % intervals); results also by year.

### Result (pre-registered text, verbatim)

In our held-out 2019–2021 test, harmonized MODIS did not meet the pre-specified criteria for interchangeable unusual-month classifications at the 3° block scale. The calendar remains useful for exploring historical hotspot detections, but its pre-2012 anomaly flags are indicative rather than validated.

**Prior exposure (pre-registration §2, verbatim):** "Before the test, we had inspected aggregate diagnostics that include 2019–2025 for Terra, Aqua and the VIIRS satellites: country-level annual counts and ratios, the yearly median overpass time, a country-level monthly calendar of raw detections for Mexico (2000–2025), and 2013–2024 pooled monthly, day/night, FRP-threshold and 1°-cell ratio distributions (H0/H2 QA); the NOAA-20 series itself, which the app displays from April 2018 onward, was visible at full resolution throughout development. No cell-month or block-month comparison of harmonized MODIS against VIIRS for 2019 or later was computed before the frozen run."

**Addendum (identified after the freeze):** the prior-exposure statement above omits further quality-control tables we had also seen before the test: (1) type-0 detection counts for Terra, Aqua and S-NPP by calendar month, pooled over 2013–2024, in two approximate boxes (Puebla, Mexico, and south-western Pampas including Bahía Blanca, Argentina); (2) counts of detections within 5 km of the Popocatépetl crater by platform and source type, with first and last year, up to 2025; (3) the yearly median and 90th-percentile MODIS pixel size, 2000–2025, for each country; (4) whole-record (2000–2025) country-level detection counts by platform, file version, source type and confidence class. None of them compares harmonized MODIS with VIIRS. The pre-registration was not changed.

### Results by country

3° block × month unless stated; 95 % intervals in parentheses; published model E1c (both splice checks passed).

| Test and pre-registered pass rule | Mexico | Argentina |
|---|---|---|
| **P2 · same unusual months.** Cohen's κ, NOAA-20 vs harmonized MODIS (cross), compared with NOAA-20 vs Suomi NPP (twins). Pass: cross κ ≥ 0.60 and cross/twin ratio ≥ 0.75 | **fail** · cross κ 0.51 (0.46–0.57) vs twins 0.75 (0.71–0.79); ratio 0.68 (0.61–0.75) | **fail** · cross κ 0.59 (0.53–0.65) vs twins 0.80 (0.76–0.84); ratio 0.74 (0.66–0.80) |
| **P2b · three-state flag** (decides "reliable"). Pass: "unusual" precision ≥ 0.80, "typical" precision ≥ 0.95, 80 % coverage 0.75–0.85, "possibly unusual" ≤ 50 % | **fail** · 67 % "possibly unusual"; "unusual" precision 0.69 | **fail** · 52 % "possibly unusual" |
| **P3 · honest 80 % ranges**, 1° cell × month. Pass: coverage 0.75–0.85 on cell-months with a non-zero estimate | **pass** · 0.80 (0.78–0.82), n = 4,545; including zero estimates 0.85 (0.83–0.86), n = 5,868; 1,323 zero-estimate cell-months left out | **pass** · 0.79 (0.78–0.81), n = 5,153; including zero estimates 0.83 (0.81–0.85), n = 6,300; 1,147 left out |
| **P4 · better than the baseline**, 1° cell × month. Skill = 1 − error of method / error of baseline. Pass: lower 95 % bound > 0 | **pass** · skill 0.08 (0.05–0.12) | **fail** · skill 0.01 (−0.02 to 0.06) |
| **J1 / J2 · Jul 2002 and Apr 2018 splices** | pass / pass | pass / pass |
| **P5 · Terra-only era** (Dec 2000 – Jun 2002), same rules as P2, P2b and P3 | **fail** · cross κ 0.41 (0.35–0.47), ratio 0.55; P3 passes | **fail** · cross κ 0.40 (0.33–0.47), ratio 0.50; P3 passes |
| **Transfer into this country** from the other one. T1 = all factors; T2 = shape only, level from the target country. Pass: \|log B\| ≤ 0.10, G ≤ 1.15, Δκ ≥ −0.05 (point estimates) | T1 fail · T2 pass | T1 fail · T2 fail |
| **RT-05 at 3° (P2 + P3 + P4)** | **not met** | **not met** |

- **What this means:** in Mexico the harmonized level beats the baseline, and in both countries the 80 % ranges hold their coverage, but which months look unusual still depends on the sensor at the 3° block scale. Against the baseline, harmonization changed the unusual-month agreement only a little (cross κ 0.51 vs 0.48 in Mexico, 0.59 vs 0.54 in Argentina); the unharmonized control scored 0.03 and 0.14.
- **Transfer:** full transfer (T1) failed in both directions; transferring only the shape (T2) worked from Argentina to Mexico but not from Mexico to Argentina. Calibration should stay regional.
- **Labels:** neither country passed P2 and P2b, so no area is "reliable". In Argentina, the class of areas with 30–100 MODIS detections per month passed P2 and P2b on its own, but the country-level failure keeps those areas "indicative".
- **Against our pre-registered expectation:** we expected both countries to probably fail P2 and the method to beat the baseline in Mexico but not in Argentina, as happened; we also expected the 80 % ranges to cover NOAA-20 less often than Suomi NPP, which did not happen (on all cell-months, coverage against NOAA-20 was not lower than against Suomi NPP in either country).
- Not run (pre-registered as reported-only sensitivities S1–S7): the 1° cell and country scales of P2, the 2022–2025 stress test and the other sensitivities.

## Limitations

- **Hotspot detections are not fires.** One fire can produce many detections or none; clouds, smoke, canopy and the time between overpasses hide fires; zero detections is not zero fire.
- **Pre-2012 unusual-month flags are indicative, not validated:** in the single test they did not agree with VIIRS as closely as our pre-specified criteria required, in either country.
- **Argentina, P2:** it failed on the point estimates, which is how the pre-registration decides (cross κ 0.59 vs the 0.60 threshold; ratio 0.74 vs 0.75); the 95 % intervals contain both thresholds (κ 0.53–0.65; ratio 0.66–0.80). We apply the pre-registered rule as written.
- Months before VIIRS are **estimates**. Using the factors for 2000–2011 assumes the 2012–2018 relation held then; this is checked only by internal consistency (the Jul 2002 splice check).
- **Level bias depends on activity.** In a development check (calibrated on 2012–2015 and compared with S-NPP in 2016–2018; run EXP-002, not the held-out test), for the third of 1° cell-months with the lowest harmonized estimates the observed VIIRS counts were about 1.3–1.5 times the estimate, and for the third with the highest estimates the estimate was too high by up to about 5 %. This pattern is consistent with regression toward the mean when an estimate rests on few MODIS detections; it was not seen in country-level monthly totals, and we did not recalibrate for it. Read low-activity months before 2012 as probably too low, and very active months as possibly slightly high.
- The Terra-only months (Dec 2000 – Jun 2002) are **indicative** whatever the test says; their own check (P5) also failed.
- **"Reliable"** requires an area of at least one 3° block in a country that passed P2 and P2b. Neither country did, so no area is "reliable". The Puebla/Popocatépetl and Paraná Delta demonstration areas would stay "indicative" in any case, because they are smaller than one block.
- **Area of interest:** a spatial approximation on the 0.1° grid (cells whose center is inside your area; see Area of interest in Method notes).
- **Mask in Argentina:** it catches only part of the MODIS detections that FIRMS classes as non-vegetation (volcano, other static or offshore sources): about half in 2000–2011 (Terra 52 %, Aqua 47 %), when the calendar uses MODIS, and 6–17 % per year from 2018, after FIRMS typing changed with the MODIS file version (11–14 % in 2017–2018), so some industrial heat can remain in the Argentine MODIS series.
- **Bahía Blanca, 2001–2003:** in the Bahía Blanca preset area, the harmonized estimates for 2001–2003 are about 5–7 times the 2004–2011 average (7.1×, 5.6× and 5.0×); Terra's own raw detections there were 4.4–6.7 times its 2004–2011 average, so the jump is already in the MODIS detections, not created by the conversion. We did not recalibrate for it; read that early period with caution. The Puebla/Popocatépetl preset shows no such jump (2001–2003 about 1.0× its 2004–2011 average).
- **Outage days:** 26 MODIS platform-days (13 Terra, 13 Aqua, Jul 2002 – Apr 2017) are treated as missing because our data rule flagged them; 19 of the 26 are also listed in the FIRMS missing-data table, 7 are not.
- **March and April 2002:** the FIRMS missing-data table lists 9 Terra days in the Terra-only period (2002-03-20 to 2002-03-27 and 2002-04-15) that our availability table does not flag, so those months are not marked incomplete and may be undercounted.
- **VIIRS data gaps:** the rule (Terra, Aqua, NOAA-20 or Suomi NPP with 3 or more missing days in the FIRMS standard tables) excluded no month in 2019–2021.
- The test years use a different MODIS file version than the early product years; we checked for a step at the version change in 2016–2018 and the test did not detect one.
- The test covers three fire seasons (2019–2021) in two countries.
- Near-real-time months are provisional and change when FIRMS publishes standard data.
- Coverage: Mexico and Argentina. Full transfer of the factors between the two countries failed in the test.
- Raw trends are descriptive, labeled "Not comparable across 2012", and not tested for significance beyond the pre-registered report.
- **Not a real-time tool.** The LANCE disclaimer states that, given their spatial resolution, the use of these data "for tactical decision-making or informing about conditions at a local scale are not advised". Talavera Orbital is for historical analysis, research and planning.

## Data & credits

### NASA data

| Product (NASA FIRMS / LANCE) | Short name (standard / near real time) | Versions seen | DOI |
|---|---|---|---|
| MODIS active fire, Terra and Aqua (1 km): standard archive Collection 6 for 2000–2022 (including the 2019–2021 test years) and Collection 6.1 from 2023; near real time Collection 6.1 | MCD14ML / MCD14DL | 6.2 (2000–2017) and 6.03 (2018–2022) = Collection 6; 61.03 (2023 onward) and 6.1NRT = Collection 6.1 | 10.5067/FIRMS/MODIS/MCD14ML · 10.5067/FIRMS/MODIS/MCD14DL.NRT.0061 |
| VIIRS 375 m active fire, Suomi NPP | VNP14IMGTML / VNP14IMGTDL_NRT | 2, 2.0NRT | NRT: 10.5067/FIRMS/VIIRS/VNP14IMGT_NRT.002 · standard: no FIRMS DOI; source product VNP14IMG V002, 10.5067/VIIRS/VNP14IMG.002 |
| VIIRS 375 m active fire, NOAA-20 | VJ114IMGTML / VJ114IMGTDL_NRT | 2, 2.0NRT | NRT: 10.5067/FIRMS/VIIRS/VJ114IMGT_NRT.002 · standard: no FIRMS DOI; source product VJ114IMG V002, 10.5067/VIIRS/VJ114IMG.002 |
| VIIRS 375 m active fire, NOAA-21 (quality control only) | VJ214IMGTDL_NRT | 2, 2.0NRT | NRT: 10.5067/FIRMS/VIIRS/VJ214IMGT_NRT.002 · standard: no FIRMS DOI; source product VJ214IMG V002, 10.5067/VIIRS/VJ214IMG.002 |

- **Erratum (identified after the freeze):** the pre-registration's data section calls the MODIS archive "Collection 6.1"; the FIRMS standard files we used carry Collection 6 version labels for 2000–2022 (6.2 and 6.03, including the 2019–2021 test years) and Collection 6.1 (61.03) from 2023. The data, the code and the test did not change; only the label was wrong.
- **Complementary references (not the files we used):** the Collection 6.1 MODIS active fire swath products at LP DAAC, MOD14 (Terra), DOI 10.5067/MODIS/MOD14.061, and MYD14 (Aqua), DOI 10.5067/MODIS/MYD14.061, cited as background on the MODIS active fire product family. Our MODIS detections come from the FIRMS files listed above, which are Collection 6 for 2000–2022.
- **Access:** FIRMS yearly summaries by country (standard processing) up to the last full year, and the FIRMS Area API for the current year up to the download date; the FIRMS data-availability endpoint fixed the standard / near-real-time cut, and the FIRMS missing-data tables were checked for gaps in the test years. Download logs with SHA-256 checksums were recorded at download time (development repository).
- **Acknowledgment (FIRMS):** "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS) (https://earthdata.nasa.gov/firms), part of NASA's Land, Atmosphere Near real-time Capability for Earth observations (LANCE) (https://earthdata.nasa.gov/lance) and NASA's Earth Science Data and Information System (ESDIS)."
- **Acknowledgment (LANCE):** "We acknowledge the use of data and/or imagery from NASA's Land, Atmosphere Near real-time Capability for Earth observations (LANCE) (https://earthdata.nasa.gov/lance), part of NASA's Earth Science Data and Information System (ESDIS)."
- **Disclaimer:** from the LANCE disclaimer: "The information presented through LANCE, GIBS, Worldview, and FIRMS … provided "as is" and users bear all responsibility and liability for their use of data"; "ESDIS makes no representations or warranties of any kind, express or implied"; and, given their spatial resolution, "their use for tactical decision-making or informing about conditions at a local scale are not advised". Full text: https://www.earthdata.nasa.gov/data/projects/lance/disclaimer
- **This project is not endorsed by NASA.** In the app and figures, the data credit is text only ("Hotspot data: NASA FIRMS"); no NASA logos or insignia are used.

### Algorithm and background references

- Giglio, L., Schroeder, W., Justice, C. O. The Collection 6 MODIS active fire detection algorithm and fire products. Remote Sensing of Environment (2016). doi:10.1016/j.rse.2016.02.054.
- Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. The New VIIRS 375 m active fire detection data product. Remote Sensing of Environment (2014). doi:10.1016/j.rse.2013.12.008.
- VIIRS Collection 2 375 m Active Fire User Guide (NASA Earthdata).
- Román, M. O. et al. Continuity between NASA MODIS Collection 6.1 and VIIRS Collection 2 land products. Remote Sensing of Environment (2024). doi:10.1016/j.rse.2023.113963.

### Other data

- **Natural Earth** Admin-0 countries, 1:10m, version 5.1.1 — public domain; used to clip the API data to Mexico and Argentina.
- **Background map (optional):** OpenStreetMap tiles, © OpenStreetMap contributors, credited in the app. The app also works without it, using its own country outlines.

### Third-party licenses

- Browser libraries, vendored unmodified with their license files: Leaflet (BSD license), Leaflet.draw (MIT), ECharts (Apache License), hyparquet (MIT). Exact versions, licenses, sources and checksums: [app/vendor/VERSIONS.md](app/vendor/VERSIONS.md).
- Python: DuckDB, pandas, NumPy, SciPy, GeoPandas, Shapely, PyYAML and Matplotlib, with PyArrow as the Parquet engine (each under its own open-source license). Pinned versions: [requirements.txt](requirements.txt).

## Use of Super Intelligence (SI)

We used SI tools throughout the project and declare them here, in the submission form and inside the project.

**What the SI did (Claude Code, Anthropic):**
- Drafted every decision package (facts, alternatives, recommendation and confidence) for each scientific and engineering decision.
- Wrote the code for data download, quality control, harmonization, validation, export and the web app; ran exploratory probes on the calibration years only, and ran the single frozen test after the team authorized it.
- Drafted documentation, the pre-registration, this README and the demo script; checked English and consistency.
- Ran independent verification passes and kept the evidence ledger that links every public number to a source or an experiment.

**What the team decided (Salvador Martínez Ayala and Saúl):**
- Every decision: scope, which detections and satellites enter the series, the harmonization method, the units, the validation design and its thresholds, the "unusual" rule, the three pre-registered result texts, the differentiator, hosting, licenses, the central question and claim, the demo format and the project name.
- Reviewing results and approving every public text. The team logo was made by the team without SI.

**Demo voice:** the narration of the demo video is SI-generated with ElevenLabs text-to-speech from the team-approved script, using an ElevenLabs library/designed voice; it is not a voice clone of any real person. This is stated in the video, its description and the file metadata.

**Where the SI marks are:**
- App footer: "Built with SI assistance (Claude Code)".
- Every code file: a header starting with "SI-generated (AI)".
- Figures and the PNG exported by the app: visible "SI-generated (AI)" mark.
- CSV downloads: an SI metadata file next to the CSV (no extra rows in the CSV).
- Data manifest: `"si_assisted": true`.
- Demo video and slides: visible "SI-generated (AI)" watermark.

No SI-generated content uses or modifies NASA logos, insignia, flags or mission identifiers.

## Pre-existing tools

Built **before the event**, with SI, and used only as development infrastructure:

- **sakit**, the team's analysis and evidence toolkit (data profiling, analysis, simulation and an evidence ledger audit).
- **Agent skills and document templates** used to organize the work (decision packages, ledger, checklists).
- A **matrix of generic approach notes** for each official challenge, written before the event; for this challenge it suggested calibrating on the sensor overlap, validating on held-out years and a percentile-based calendar.

This repository does **not** include sakit, the skills or the templates. The few functions the product needs (the count-ratio baseline with confidence intervals and the leakage audit) were rewritten in English during the event inside the product code (`src/nucleo/baseline.py` and `src/nucleo/leak_audit.py`). All project-specific code, data products and decisions were made during the event.

## License — MIT (code) · CC BY 4.0 (aggregates, figures and texts)

- Code: MIT, see [LICENSE](LICENSE). Copyright holder: "Talavera Orbital team".
- Aggregated data, figures and texts: Creative Commons Attribution, see [app/data/LICENSE-DATA.md](app/data/LICENSE-DATA.md), which also states the origin of the data (NASA FIRMS; Natural Earth).
- NASA FIRMS data keep their own terms (see Data & credits).

## Reproduce

1. Install the pinned packages: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
2. Check the environment without reading any data: `bash scripts/reproducir.sh --solo-comprobar`.
3. The raw FIRMS files are not stored in this repository. Get a free FIRMS MAP_KEY, store it in a local `.env` file as `FIRMS_MAP_KEY` (do not commit it; the logs record URLs with `<MAP_KEY>` instead of the key) and run `REPRO_NET=1 bash scripts/reproducir.sh`: it downloads the FIRMS files again with the same frozen cut (country summaries 2000–2025 and the Area API up to 2026-11-14) and rebuilds the tables, factors, development experiments, figures and app data. Without `REPRO_NET=1` the script runs offline and needs the raw files already in place.
4. The script writes the development experiments to a new `runs/repro-<UTC>/` directory and never overwrites an existing run. The single validation run is not part of it: `src/nucleo/validacion_rt05.py` refuses to run in test mode unless the `prereg-v1` tag exists, the hashes of the method code and its configuration match the frozen ones, no threshold is pending and no earlier test run exists.
