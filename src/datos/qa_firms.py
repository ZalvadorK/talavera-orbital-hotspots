#!/usr/bin/env python3
"""QA of the intermediate FIRMS table → docs/02-datos/qa-firms.md (descriptive diagnostics, NOT claims).

All numbers are hotspot detections (not fires), Mexico country summaries, UTC dates.
Ratios are descriptive (no model); they feed the D2 decision packages.
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
POPO = (19.023, -98.622)  # Smithsonian GVP 341090 (EVD-041)


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int) or (hasattr(v, "is_integer") and isinstance(v, float) and v.is_integer() and abs(v) >= 1000):
        return f"{int(v)}"
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 1000 else f"{v:.0f}"
    return str(v)


def md(con, sql: str) -> str:
    df = con.execute(sql).df()
    if not len(df):
        return "_(no rows)_"
    filas = [[_fmt(x.item() if hasattr(x, "item") else x) for x in fila] for fila in df.itertuples(index=False)]
    cab = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    return "\n".join([cab, sep] + ["| " + " | ".join(f) + " |" for f in filas])


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pais", default="Mexico")
    a = ap.parse_args(argv)
    PQ = RAIZ / "data" / "interim" / "firms" / f"firms_{a.pais.lower()}.parquet"
    OUT = RAIZ / "docs" / "02-datos" / ("qa-firms.md" if a.pais == "Mexico" else f"qa-firms-{a.pais.lower()}.md")
    if not PQ.exists():
        print("missing", PQ)
        return 1
    con = duckdb.connect()
    con.execute(f"CREATE VIEW f AS SELECT *, year(acq_date_utc) AS anio, month(acq_date_utc) AS mes, "
                f"((hour(acq_datetime_utc) + minute(acq_datetime_utc)/60.0 + longitude/15.0 + 48) % 24) AS hora_solar "
                f"FROM '{PQ}'")
    s = []
    s.append(f"# FIRMS QA — {a.pais} (yearly country summaries)\n\nGenerated: "
             f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')} by `src/datos/qa_firms.py` "
             f"from `{PQ.relative_to(RAIZ)}`. **Descriptive diagnostics, not claims.** "
             "Units: hotspot detections (not fires). UTC dates.\n")

    s.append("## 1. Rows per source and processing\n")
    s.append(md(con, "SELECT fuente, plataforma, procesamiento, count(*) n, min(acq_date_utc) first_date, "
                     "max(acq_date_utc) last_date FROM f GROUP BY ALL ORDER BY fuente, plataforma, procesamiento"))

    s.append("\n## 2. Detections per year and platform\n")
    s.append(md(con, "PIVOT (SELECT anio, plataforma FROM f) ON plataforma USING count(*) GROUP BY anio ORDER BY anio"))

    s.append("\n## 3. Values of satellite and version (T-03, T-04)\n")
    s.append(md(con, "SELECT fuente, satellite_raw, version, count(*) n FROM f GROUP BY ALL ORDER BY fuente, n DESC"))

    s.append("\n## 4. `type` field per platform (standard only; T-01, T-17)\n")
    s.append(md(con, "SELECT plataforma, coalesce(CAST(type AS VARCHAR),'NULL') AS t, count(*) AS n, "
                     "round(100.0*count(*)/sum(count(*)) OVER (PARTITION BY plataforma),2) AS pct "
                     "FROM f GROUP BY plataforma, t ORDER BY plataforma, t"))

    s.append("\n## 5. Yearly VIIRS/MODIS ratio in the overlap (all detections, type 0 where it exists)\n")
    s.append(f"Ratio = VIIRS detections / MODIS detections of the same year in {a.pais}. `_v0` uses only `type=0` "
             "(presumed vegetation) in both.\n")
    s.append(md(con, """
      WITH a AS (SELECT anio,
        count(*) FILTER (plataforma='Aqua') aqua, count(*) FILTER (plataforma='Terra') terra,
        count(*) FILTER (plataforma='S-NPP') snpp, count(*) FILTER (plataforma='NOAA-20') n20,
        count(*) FILTER (plataforma='NOAA-21') n21,
        count(*) FILTER (plataforma='Aqua' AND type=0) aqua_v0, count(*) FILTER (plataforma='S-NPP' AND type=0) snpp_v0
        FROM f WHERE anio>=2012 GROUP BY anio)
      SELECT anio, aqua, terra, snpp, n20, n21,
        round(snpp/nullif(aqua,0),2) snpp_aqua, round(snpp/nullif(aqua+terra,0),2) snpp_modis,
        round(snpp_v0/nullif(aqua_v0,0),2) snpp_aqua_v0,
        round(n20/nullif(snpp,0),2) n20_snpp, round(n21/nullif(snpp,0),2) n21_snpp
      FROM a ORDER BY anio"""))

    s.append("\n## 6. S-NPP/Aqua ratio per month (2013–2024, type=0) — does the ratio change with the season?\n")
    s.append(md(con, """
      SELECT mes, count(*) FILTER (plataforma='S-NPP') snpp, count(*) FILTER (plataforma='Aqua') aqua,
        round(count(*) FILTER (plataforma='S-NPP')/nullif(count(*) FILTER (plataforma='Aqua'),0),2) ratio
      FROM f WHERE anio BETWEEN 2013 AND 2024 AND type=0 GROUP BY mes ORDER BY mes"""))

    s.append("\n## 7. S-NPP/Aqua ratio per day/night (2013–2024, type=0)\n")
    s.append(md(con, """
      SELECT daynight, count(*) FILTER (plataforma='S-NPP') snpp, count(*) FILTER (plataforma='Aqua') aqua,
        round(count(*) FILTER (plataforma='S-NPP')/nullif(count(*) FILTER (plataforma='Aqua'),0),2) ratio
      FROM f WHERE anio BETWEEN 2013 AND 2024 AND type=0 GROUP BY daynight ORDER BY daynight"""))

    s.append("\n## 8. S-NPP/Aqua ratio by FRP threshold (2013–2024, type=0) — sensitivity\n")
    s.append("FRP in MW per pixel; the pixel sizes differ (375 m vs ≥1 km), so the threshold is not "
             "physically equivalent between sensors: it is a diagnostic, not a calibration.\n")
    s.append(md(con, """
      SELECT u AS frp_min_MW,
        count(*) FILTER (plataforma='S-NPP' AND frp>=u) snpp, count(*) FILTER (plataforma='Aqua' AND frp>=u) aqua,
        round(count(*) FILTER (plataforma='S-NPP' AND frp>=u)/nullif(count(*) FILTER (plataforma='Aqua' AND frp>=u),0),2) ratio
      FROM f, (SELECT unnest([0,5,10,20,50,100]) u) WHERE anio BETWEEN 2013 AND 2024 AND type=0 GROUP BY u ORDER BY u"""))

    s.append("\n## 9. Spatial heterogeneity of the ratio (1° cells, 2013–2024, type=0, ≥200 Aqua detections)\n")
    s.append(md(con, """
      WITH c AS (SELECT floor(latitude) la, floor(longitude) lo,
        count(*) FILTER (plataforma='S-NPP') snpp, count(*) FILTER (plataforma='Aqua') aqua
        FROM f WHERE anio BETWEEN 2013 AND 2024 AND type=0 GROUP BY ALL)
      SELECT count(*) cells, round(quantile_cont(snpp/aqua,0.1),2) p10, round(quantile_cont(snpp/aqua,0.25),2) p25,
        round(median(snpp/aqua),2) median, round(quantile_cont(snpp/aqua,0.75),2) p75,
        round(quantile_cont(snpp/aqua,0.9),2) p90, round(sum(snpp)/sum(aqua),2) global
      FROM c WHERE aqua>=200"""))

    s.append("\n## 10. Median local solar time of detection per platform and year (drift; T-10)\n")
    s.append(md(con, """
      PIVOT (SELECT anio, plataforma, hora_solar FROM f WHERE daynight='D')
      ON plataforma USING round(median(hora_solar),2) GROUP BY anio ORDER BY anio"""))

    s.append("\n## 11. MODIS pixel size (scan×track, km²) per year (T-07)\n")
    s.append(md(con, """
      SELECT anio, round(median(scan*track),2) median, round(quantile_cont(scan*track,0.9),2) p90
      FROM f WHERE familia='MODIS' GROUP BY anio ORDER BY anio"""))

    s.append("\n## 12. Popocatépetl: detections within ≤ 5 km of the crater (T-02)\n")
    la, lo = POPO
    s.append(md(con, f"""
      SELECT plataforma, coalesce(CAST(type AS VARCHAR),'NULL') type, count(*) n, min(anio) from_year, max(anio) to_year
      FROM f WHERE 6371*2*asin(sqrt(pow(sin(radians(latitude-{la})/2),2)+cos(radians({la}))*cos(radians(latitude))*
        pow(sin(radians(longitude-({lo}))/2),2))) <= 5 GROUP BY ALL ORDER BY plataforma, type"""))

    s.append("\n## 13. Confidence (T-09)\n")
    s.append(md(con, """
      SELECT familia, CASE WHEN familia='MODIS' THEN
          CASE WHEN TRY_CAST(confidence_raw AS INT) < 30 THEN 'MODIS <30'
               WHEN TRY_CAST(confidence_raw AS INT) < 80 THEN 'MODIS 30-79' ELSE 'MODIS ≥80' END
        ELSE confidence_raw END confidence_class, count(*) n
      FROM f GROUP BY ALL ORDER BY familia, confidence_class"""))

    if a.pais != "Mexico":
        s.append("\n## 14. Approximate box of the south-western Pampas (35–40 S, 61–66 W; includes Bahía Blanca) — type=0 detections per month, 2013–2024\n")
        s.append(md(con, """
      PIVOT (SELECT mes, plataforma FROM f WHERE latitude BETWEEN -40 AND -35 AND longitude BETWEEN -66 AND -61
             AND type=0 AND anio BETWEEN 2013 AND 2024 AND plataforma IN ('Aqua','Terra','S-NPP'))
      ON plataforma USING count(*) GROUP BY mes ORDER BY mes"""))
    else:
        s.append("\n## 14. Approximate box of Puebla (17.85–20.85 N, 99.1–96.7 W; not the state polygon) "
                 "— type=0 detections per month, 2013–2024\n")
        s.append(md(con, """
      PIVOT (SELECT mes, plataforma FROM f WHERE latitude BETWEEN 17.85 AND 20.85 AND longitude BETWEEN -99.1 AND -96.7
             AND type=0 AND anio BETWEEN 2013 AND 2024 AND plataforma IN ('Aqua','Terra','S-NPP'))
      ON plataforma USING count(*) GROUP BY mes ORDER BY mes"""))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(s) + "\n", encoding="utf-8")
    print("OK →", OUT.relative_to(RAIZ))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
