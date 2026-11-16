<!-- SI-generated (AI): Claude Code wrote this during the event; reviewed by the team. -->

# Data license: derived data in this folder

This file is copied here by `src/exportar_demo.py` from the template `src/plantillas_publicas/LICENSE-DATA.md`. It covers the files
that the exporter writes in this folder (`manifest.json`, and for each country: `contorno.geojson`, `intervalos.json`,
`disponibilidad.json`, `export_manifiesto.json`, and the tiles `mensual/`, `diario/` and `puntos/`).

The NASA texts below are copied as published on the NASA pages named next to each one (read on 2026-11-15, including the punctuation
of the FIRMS acknowledgment, which has no comma before "and NASA's Earth Science Data and Information System (ESDIS)").

## License of the derived data

The derived data in this folder (monthly and daily aggregates of hotspot detections, per-detection VIIRS-equivalent weights,
uncertainty ranges, availability tables and the manifest) are licensed under
**Creative Commons Attribution 4.0 International (CC BY 4.0)**: <https://creativecommons.org/licenses/by/4.0/>.

You may share and adapt them, including commercially, if you give appropriate credit, link to the license and indicate if you made changes.

Suggested attribution:

> Talavera Orbital team (2026). MODIS and VIIRS hotspot detections harmonized into one monthly series for Mexico and Argentina.
> Derived from NASA FIRMS data. CC BY 4.0.

This grant covers **only the work of the team**. It does not re-license the underlying NASA FIRMS data, which keep the terms that
NASA sets for them (see the LANCE disclaimer quoted below and its page: <https://www.earthdata.nasa.gov/data/projects/lance/disclaimer>).

## Origin of the data and credits

- **Hotspot detections:** NASA FIRMS (Fire Information for Resource Management System), distributed through NASA Earthdata and LANCE.
  Products used: MODIS active fire (Terra and Aqua, 1 km) and VIIRS 375 m active fire (Suomi NPP and NOAA-20). Short names and DOIs
  (read from NASA CMR, DataCite and the FIRMS pages on 2026-11-15):

  | Platform | Standard product (FIRMS name) | DOI of the standard product | Near-real-time (NRT) product | DOI of the NRT product |
  |---|---|---|---|---|
  | Terra and Aqua (MODIS Collection 6 (2000–2022) and 6.1 (2023 on)) | `MCD14ML` | `10.5067/FIRMS/MODIS/MCD14ML` | `MCD14DL`, version `6.1NRT` | `10.5067/FIRMS/MODIS/MCD14DL.NRT.0061` |
  | Suomi NPP (VIIRS 375 m, Collection 2) | `VNP14IMGTML` | No FIRMS DOI exists for it; its source product `VNP14IMG` V002 has `10.5067/VIIRS/VNP14IMG.002` | `VNP14IMGTDL_NRT`, version 2 | `10.5067/FIRMS/VIIRS/VNP14IMGT_NRT.002` |
  | NOAA-20 (VIIRS 375 m, Collection 2) | `VJ114IMGTML` | No FIRMS DOI exists for it; its source product `VJ114IMG` V002 has `10.5067/VIIRS/VJ114IMG.002` | `VJ114IMGTDL_NRT`, version 2 | `10.5067/FIRMS/VIIRS/VJ114IMGT_NRT.002` |

  The `version` column of the FIRMS files carries labels such as `6.03` and `61.03` (MODIS standard), `6.1NRT` (MODIS NRT), `2` (VIIRS
  standard) and `2.0NRT` (VIIRS NRT). They are file labels, not the version of a DOI.
- **Acknowledgment (FIRMS)**, official text from the "Acknowledgments" section of <https://www.earthdata.nasa.gov/data/tools/firms>:

  > We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS)
  > (https://earthdata.nasa.gov/firms), part of NASA's Land, Atmosphere Near real-time Capability for Earth observations (LANCE)
  > (https://earthdata.nasa.gov/lance) and NASA's Earth Science Data and Information System (ESDIS).

- **Acknowledgment (LANCE)**, official text from <https://www.earthdata.nasa.gov/data/projects/lance>:

  > We acknowledge the use of data and/or imagery from NASA's Land, Atmosphere Near real-time Capability for Earth observations (LANCE)
  > (https://earthdata.nasa.gov/lance), part of NASA's Earth Science Data and Information System (ESDIS).
- **Disclaimer (LANCE, which covers FIRMS)**, quoted from <https://www.earthdata.nasa.gov/data/projects/lance/disclaimer>. These are
  fragments of the page, joined by "…", not the whole text:

  > "The information presented through LANCE, GIBS, Worldview, and FIRMS" … "provided "as is" and users bear all responsibility and
  > liability for their use of data"
  >
  > "ESDIS makes no representations or warranties of any kind, express or implied"
  >
  > "their use for tactical decision-making or informing about conditions at a local scale are not advised"

  The current disclaimer page does not ask to repeat it when data are redistributed; it is quoted here so that the limits of the data
  are visible next to them.
- **Country outlines** (`contorno.geojson`): Natural Earth 1:10m Admin-0 Countries, public domain, simplified by the exporter.
- **Optional background map in the app:** (c) OpenStreetMap contributors. It is not part of these data.

**This project is independent and is not endorsed by NASA.** No NASA logo or insignia is used.

## What the numbers are, and what they are not

- Counts are satellite **hotspot detections**, not individual fires. One fire can produce several detections or none.
- Values before 2012 come from MODIS and are **estimates** converted to VIIRS-equivalent detections; they carry an uncertainty range.
- Months marked provisional use near-real-time data that FIRMS later replaces; they can change.
- Terra, Aqua and S-NPP counts for 2019 onward are included **only** when `manifest.json` carries a `verdict` (the pre-registered
  validation test has been run). Without a verdict they are empty by design.
- The "reliable" / "indicative" label of the pre-2012 estimates exists only when `manifest.json` carries a `verdict`.
  Without it the estimates are "not yet tested".

## Use of SI (AI)

The export script, the analysis core and the app that reads these data were written with SI assistance (Claude Code) during the event
and reviewed by the team. `manifest.json` repeats this with `"si_assisted": true` and the text `si_declaration`. The decisions are made by the team.

## Provenance

`manifest.json` records the dataset version, the generation time, the code commit and the experiments the data come from.
Each country folder holds `export_manifiesto.json` with the command, the SHA-256 of every input and the sizes of the outputs.
