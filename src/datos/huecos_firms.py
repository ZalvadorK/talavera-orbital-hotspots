#!/usr/bin/env python3
# SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
"""FIRMS "missing data" metadata: which days have no data, per source, aggregated by month (W2 window 2019-01..2021-12).

PURPOSE (lot-3 point 7): give Salvador the list of months with a VIIRS gap in the test window W2, to decide
`meses_excluidos_huecos_viirs` (config/validacion.yaml). This script NEVER edits that config and NEVER picks the day threshold.

WHAT IT READS: availability METADATA only (dates on which FIRMS has no data), not detections.
  - It never uses detections. The optional cross-check with data/processed/disponibilidad_plataforma_dia.csv uses only the columns
    fecha, plataforma, sin_datos, fuente; it drops Terra/Aqua/S-NPP rows dated >= 2019-01-01 before using them (anti-leak) and never
    uses the count columns n_mx / n_ar.  Run it under the shared lock, without a pipe:
        flock data/.pesado.lock .venv/bin/python src/datos/huecos_firms.py

ABOUT THE ENDPOINT (verified 2026-11-15 by plain GET of the documentation pages; copies in data/raw/firms/missing_data/doc_*):
  - https://firms.modaps.eosdis.nasa.gov/api/  lists `missing_data` = "View dates with missing satellite data" -> /api/missing_data/
  - /api/missing_data/ is an HTML page ("Standard Data" and "Near Real Time Data" tables, columns "Date Missing" and
    "Satellite (Sensor)"). Its body is filled by the page's own JavaScript with GET <page>?action=fetch_data, which returns JSON
    {success, html, rowCount}. The page says NRT rows are listed ONLY past the last standard (SP) date of each satellite.
  - Nothing in those pages asks for a MAP_KEY for this service, so THIS SCRIPT NEITHER READS NOR SENDS ANY KEY (the task text assumed one
    was needed). If a keyed variant is ever confirmed, add it explicitly; do not guess URLs with a credential.
  - The live query is OFF by default (`--consultar` turns it on). The format of the real response is NOT verified: the parser is
    tolerant but fails loudly (exit 3) instead of reporting "no gaps" when it cannot read rows.

CACHE (idempotent): data/raw/firms/missing_data/
    respuesta_<UTC>.raw   raw response, immutable
    <FUENTE>.csv          one file per source (fecha, fuente, satelite_texto, consulta_utc, sha256_respuesta)
    registro.csv          query log: UTC date/time, URL (masked), HTTP code, bytes, sha256, file, note
  A new `--consultar` reuses the last valid cached response (sha256 re-checked) unless `--refrescar` is given.

EXIT CODES: 0 = response read and document written; 3 = response unreadable or partly unreadable; 4 = no response in the cache (pending);
            network/HTTP failure on --consultar stops with a message (and a row in registro.csv).

USAGE
    python src/datos/huecos_firms.py                       # process the cache and write the doc (pending state if there is no response)
    python src/datos/huecos_firms.py --consultar           # live query (only with authorization), then process
    python src/datos/huecos_firms.py --importar ARCHIVO --tipo respuesta --etiqueta "SYNTHETIC test" --cache-dir X --doc Y.md  # offline test
SI-generated (AI): Claude Code wrote this script during the event; reviewed by the team.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw" / "firms" / "missing_data"
DOC = RAIZ / "docs" / "02-datos" / "huecos-firms-missing-data.md"
DISPONIBILIDAD = RAIZ / "data" / "processed" / "disponibilidad_plataforma_dia.csv"
URL_PAGINA = "https://firms.modaps.eosdis.nasa.gov/api/missing_data/"
URL_DATOS = URL_PAGINA + "?action=fetch_data"
W2 = (dt.date(2019, 1, 1), dt.date(2021, 12, 31))
FUENTES = ["VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT", "MODIS_SP", "MODIS_NRT"]
UMBRALES = (1, 3, 7)          # reference only; the threshold is Salvador's decision
CAMPOS_REGISTRO = ["consulta_utc", "tipo", "origen", "http", "bytes", "sha256", "archivo", "nota"]
RE_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")


# ───────────────────────────── utilities ─────────────────────────────
def ahora_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def enmascarar(texto: str) -> str:
    """Defence in depth: if a MAP_KEY is in this process's environment, it never reaches a file or the screen."""
    k = os.environ.get("FIRMS_MAP_KEY", "").strip()
    return texto.replace(k, "<MAP_KEY>") if k else texto


def registrar(cache: Path, fila: dict) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    reg = cache / "registro.csv"
    nuevo = not reg.exists()
    with reg.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS_REGISTRO)
        if nuevo:
            w.writeheader()
        w.writerow({c: fila.get(c, "") for c in CAMPOS_REGISTRO})


def leer_registro(cache: Path) -> list[dict]:
    reg = cache / "registro.csv"
    return list(csv.DictReader(reg.open(encoding="utf-8"))) if reg.exists() else []


def ultima_respuesta(cache: Path) -> dict | None:
    """Last logged response whose file still exists and whose sha256 still matches (cache integrity)."""
    for fila in reversed(leer_registro(cache)):
        if fila["tipo"] != "respuesta" or not fila["archivo"]:
            continue
        ruta = cache / fila["archivo"]
        if ruta.exists() and sha256_bytes(ruta.read_bytes()) == fila["sha256"]:
            return fila
        raise SystemExit(f"Cache corrupted: {ruta} is missing or its sha256 differs from registro.csv")
    return None


# ───────────────────────────── acquisition ─────────────────────────────
def consultar(cache: Path, refrescar: bool, etiqueta: str) -> dict:
    previa = ultima_respuesta(cache)
    if previa and not refrescar:
        print(f"cache hit: {previa['archivo']} (query {previa['consulta_utc']}, sha256 {previa['sha256'][:12]}...); no network")
        return previa
    ts = ahora_utc()
    # Plain GET, honest User-Agent, no key, no spoofed headers.
    req = urllib.request.Request(URL_DATOS, headers={"User-Agent": "spaceapps2026-hotspots/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            estado, datos = r.status, r.read()
    except urllib.error.HTTPError as e:
        cuerpo = enmascarar(e.read()[:300].decode("utf-8", "replace")).replace("\n", " ")
        registrar(cache, {"consulta_utc": ts.isoformat(timespec="seconds"), "tipo": "error", "origen": URL_DATOS, "http": e.code,
                          "nota": cuerpo})
        raise SystemExit(f"missing_data: HTTP {e.code}. Body start: {cuerpo}")
    except Exception as e:  # noqa: BLE001
        nota = f"{type(e).__name__}: {enmascarar(str(e))[:200]}"
        registrar(cache, {"consulta_utc": ts.isoformat(timespec="seconds"), "tipo": "error", "origen": URL_DATOS, "http": 0, "nota": nota})
        raise SystemExit(f"missing_data: no response ({nota})")
    return guardar_respuesta(cache, datos, ts, URL_DATOS, estado, etiqueta)


def guardar_respuesta(cache: Path, datos: bytes, ts: dt.datetime, origen: str, http: int | str, etiqueta: str) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    nombre = f"respuesta_{ts.strftime('%Y%m%dT%H%M%SZ')}.raw"
    (cache / nombre).write_bytes(datos)
    fila = {"consulta_utc": ts.isoformat(timespec="seconds"), "tipo": "respuesta", "origen": origen, "http": http, "bytes": len(datos),
            "sha256": sha256_bytes(datos), "archivo": nombre, "nota": etiqueta}
    registrar(cache, fila)
    print(f"saved {nombre}: {len(datos)} bytes, sha256 {fila['sha256'][:12]}...")
    return fila


def importar(cache: Path, ruta: Path, tipo: str, etiqueta: str) -> dict:
    datos = ruta.read_bytes()
    h = sha256_bytes(datos)
    for f in leer_registro(cache):
        if f["sha256"] == h and f["tipo"] == tipo:
            print(f"import: already in cache ({f['archivo']}); nothing to do")
            return f
    if tipo == "respuesta":
        return guardar_respuesta(cache, datos, ahora_utc(), f"archivo_local:{ruta.name}", "n/a", etiqueta)
    destino = cache / f"doc_{ruta.name}"
    shutil.copyfile(ruta, destino)
    fila = {"consulta_utc": ahora_utc().isoformat(timespec="seconds"), "tipo": "doc", "origen": f"archivo_local:{ruta.name}", "http": "n/a",
            "bytes": len(datos), "sha256": h, "archivo": destino.name, "nota": etiqueta}
    registrar(cache, fila)
    return fila


# ───────────────────────────── parsing ─────────────────────────────
class _Tabla(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.filas: list[list[str]] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag == "tr":
            self._fila = []
        elif tag in ("td", "th") and self._fila is not None:
            self._celda = []

    def handle_data(self, data):  # noqa: ANN001
        if self._celda is not None:
            self._celda.append(data)

    def handle_endtag(self, tag):  # noqa: ANN001
        if tag in ("td", "th") and self._celda is not None and self._fila is not None:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            self.filas.append(self._fila)
            self._fila = None


def clasificar(etiqueta: str, nrt: bool) -> str | None:
    t = etiqueta.lower()
    if re.search(r"noaa[-\s]?21|jpss[-\s]?2|\bn21\b", t):
        base = "VIIRS_NOAA21"
    elif re.search(r"noaa[-\s]?20|jpss[-\s]?1\b|\bn20\b", t):
        base = "VIIRS_NOAA20"
    elif re.search(r"suomi|s-?npp|\bnpp\b", t):
        base = "VIIRS_SNPP"
    elif re.search(r"terra|aqua|modis", t):
        base = "MODIS"
    else:
        return None
    return f"{base}_{'NRT' if nrt else 'SP'}"


def dias_de_celda(celda: str) -> list[dt.date]:
    """One ISO date -> [day]; two ISO dates (a range) -> every day inclusive; anything else -> []."""
    f = RE_FECHA.findall(celda)
    try:
        if len(f) == 1:
            return [dt.date.fromisoformat(f[0])]
        if len(f) == 2:
            a, b = dt.date.fromisoformat(f[0]), dt.date.fromisoformat(f[1])
            return [a + dt.timedelta(days=i) for i in range((b - a).days + 1)] if b >= a else []
    except ValueError:
        pass
    return []


def parsear(datos: bytes) -> tuple[list[tuple[str, str, dt.date]], list[str], dict]:
    """-> (rows [(source, satellite label, date)], unparsed rows (text), meta). Never silently returns 'no gaps'."""
    texto = datos.decode("utf-8", "replace")
    meta: dict = {"formato": "html", "rowCount_declarado": None}
    try:
        d = json.loads(texto)
    except ValueError:
        d = None
    if d is not None:
        if not (isinstance(d, dict) and d.get("success") is True and isinstance(d.get("html"), str)):
            raise ValueError("JSON without success=true / html string; first 200 chars: " + enmascarar(texto[:200]))
        meta.update(formato="json{success,html,rowCount}", rowCount_declarado=d.get("rowCount"))
        texto = d["html"]
    p = _Tabla()
    p.feed(texto)
    filas, sin_leer, entradas = [], [], 0
    for celdas in p.filas:
        if not any(celdas) or any(re.search(r"date missing|standard data|near real time", c, re.I) for c in celdas):
            continue
        if len(celdas) != 4:
            sin_leer.append(" | ".join(celdas)[:160])
            continue
        for fecha_c, sat_c, nrt in ((celdas[0], celdas[1], False), (celdas[2], celdas[3], True)):
            if not fecha_c and not sat_c:
                continue
            dias, fuente = dias_de_celda(fecha_c), clasificar(sat_c, nrt)
            if not dias or not sat_c:
                sin_leer.append(f"{fecha_c} | {sat_c} | nrt={nrt}"[:160])
                continue
            entradas += 1
            for dia in dias:
                filas.append((fuente or "OTRO", sat_c, dia))
    meta["entradas_tabla"] = entradas
    return filas, sin_leer, meta


def escribir_por_fuente(cache: Path, filas: list, resp: dict) -> None:
    por: dict[str, list] = defaultdict(list)
    for fuente, sat, dia in filas:
        por[fuente].append((dia, sat))
    for fuente, items in por.items():
        with (cache / f"{fuente}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fecha", "fuente", "satelite_texto", "consulta_utc", "sha256_respuesta"])
            for dia, sat in sorted(set(items)):
                w.writerow([dia.isoformat(), fuente, sat, resp["consulta_utc"], resp["sha256"]])


# ───────────────────────────── aggregation ─────────────────────────────
def meses_w2() -> list[str]:
    out, d = [], W2[0]
    while d <= W2[1]:
        out.append(d.strftime("%Y-%m"))
        d = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return out


def agregar(filas: list) -> dict[str, dict[str, set]]:
    """source -> month 'YYYY-MM' -> set of distinct days with a gap (W2 only)."""
    out: dict[str, dict[str, set]] = {f: defaultdict(set) for f in FUENTES}
    for fuente, _sat, dia in filas:
        if fuente in out and W2[0] <= dia <= W2[1]:
            out[fuente][dia.strftime("%Y-%m")].add(dia)
    return out


def rangos(dias: list[dt.date]) -> list[tuple[dt.date, dt.date]]:
    out: list[tuple[dt.date, dt.date]] = []
    for d in sorted(set(dias)):
        if out and d - out[-1][1] == dt.timedelta(days=1):
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


def dias_sensor(agr: dict, sensor: str) -> dict[str, set]:
    """Distinct days per month for a sensor (SP union NRT)."""
    out: dict[str, set] = defaultdict(set)
    for sufijo in ("SP", "NRT"):
        for m, ds in agr[f"{sensor}_{sufijo}"].items():
            out[m] |= ds
    return out


def meses_con_hueco(por_mes: dict[str, set], k: int) -> list[str]:
    return [m for m in meses_w2() if len(por_mes.get(m, ())) >= k]


# ───────────────────────────── cross-check (metadata only) ─────────────────────────────
def leer_disponibilidad(ruta: Path) -> dict:
    """Coverage of disponibilidad_plataforma_dia.csv. Uses only fecha/plataforma/sin_datos/fuente; applies the anti-leak filter first."""
    if not ruta.exists():
        return {"existe": False}
    cob: dict[str, dict] = {}
    omitidas = 0
    sin_datos: dict[tuple[str, dt.date], str] = {}
    with ruta.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            plat, fecha = r["plataforma"], dt.date.fromisoformat(r["fecha"])
            if fecha >= dt.date(2019, 1, 1) and re.search(r"terra|aqua|npp", plat, re.I):
                omitidas += 1       # anti-leak: not used for anything
                continue
            c = cob.setdefault(plat, {"min": fecha, "max": fecha, "dias": 0, "sin_datos": 0})
            c["min"], c["max"], c["dias"] = min(c["min"], fecha), max(c["max"], fecha), c["dias"] + 1
            if r["sin_datos"].strip().lower() == "true":
                c["sin_datos"] += 1
                sin_datos[(plat, fecha)] = r["fuente"]
    return {"existe": True, "cobertura": cob, "omitidas_antifuga": omitidas, "sin_datos": sin_datos,
            "cubre_viirs": any(re.search(r"npp|noaa|viirs", p, re.I) for p in cob)}


def cruce_modis_pre2019(filas: list, disp: dict) -> dict | None:
    if not disp.get("existe") or not filas:
        return None
    falta = {(("Terra" if "terra" in s.lower() else "Aqua" if "aqua" in s.lower() else "?"), d)
             for f, s, d in filas if f == "MODIS_SP" and d < dt.date(2019, 1, 1)}
    tabla = disp["sin_datos"]
    ambos, solo_md = [], []
    for plat, d in sorted(falta, key=lambda x: x[1]):
        hit = [(p, d) for p in ("Terra", "Aqua") if (p, d) in tabla and (plat in (p, "?"))]
        (ambos if hit else solo_md).append((plat, d))
    solo_tabla = [(p, d, fu) for (p, d), fu in sorted(tabla.items(), key=lambda x: x[0][1])
                  if (p, d) not in falta and ("?", d) not in falta]
    return {"n_missing_data": len(falta), "n_tabla": len(tabla), "ambos": len(ambos), "solo_missing_data": solo_md,
            "solo_tabla": solo_tabla}


# ───────────────────────────── document ─────────────────────────────
def fmt_rangos(rs: list[tuple[dt.date, dt.date]], tope: int = 40) -> str:
    if not rs:
        return "none"
    txt = ", ".join(a.isoformat() if a == b else f"{a.isoformat()}..{b.isoformat()} ({(b - a).days + 1} d)" for a, b in rs[:tope])
    return txt + (f", ... (+{len(rs) - tope} more ranges; full list in the per-source CSV)" if len(rs) > tope else "")


def render(resp: dict | None, filas: list | None, sin_leer: list[str], meta: dict, disp: dict, cache: Path, etiqueta: str,
           problema: str = "", cabeza: str = "") -> str:
    L: list[str] = []
    L += ["# Huecos de datos en FIRMS (`missing_data`) — ventana de prueba W2 (2019-01..2021-12)", ""]
    L += ["> Generado por `src/datos/huecos_firms.py` (SI-generated: Claude Code). **Metadatos de disponibilidad, no detecciones.** "
          "No modifica `config/validacion.yaml`: el umbral de días y la lista final son decisión de Salvador (lote 3, punto 7).", ""]
    if etiqueta:
        L += [f"> **Etiqueta de la respuesta: {etiqueta}.** Si dice SYNTHETIC, esto es una prueba del código, no un resultado.", ""]
    L += ["## 1. Estado de la consulta", ""]
    if resp is None:
        L += ["**SIN RESPUESTA REAL.** No hay ninguna respuesta de `missing_data` en la caché "
              f"(`{rel(cache)}`). Las secciones 3 y 4 quedan vacías y `meses_excluidos_huecos_viirs` sigue siendo `[]` con [VERIFICAR]. "
              "Una lista vacía por falta de consulta **no** significa «sin huecos».", ""]
    else:
        if filas is None:
            L += [f"**RESPUESTA EN CACHÉ NO INTERPRETABLE** — {problema}. No se reporta ninguna lista de meses; no equivale a «sin huecos».",
                  "Primeros 300 caracteres de la respuesta (clave enmascarada):", "```", enmascarar(cabeza[:300]), "```", ""]
        L += [f"- Consulta (UTC): `{resp['consulta_utc']}` · origen: `{resp['origen']}` · HTTP: `{resp['http']}` · "
              f"{resp['bytes']} bytes · sha256 `{resp['sha256']}` · archivo: `{resp['archivo']}`"]
        if filas is not None:
            L += [f"- Formato: {meta.get('formato')} · entradas de tabla leídas (fecha+satélite, un rango cuenta 1): {meta.get('entradas_tabla')} · "
              f"días×fuente tras expandir rangos: {len(filas or [])} · `rowCount` declarado por el servidor: {meta.get('rowCount_declarado')} "
              f"(su unidad no está documentada: no se exige que coincida) · entradas no interpretadas: {len(sin_leer)}"]
        for s in sin_leer[:10]:
            L.append(f"  - no interpretada: `{enmascarar(s)}`")
        L.append("")
    for f in [f for f in leer_registro(cache) if f["tipo"] in ("nota", "error")]:
        L.append(f"- Registro {f['tipo']} ({f['consulta_utc']}): {enmascarar(f['nota'])}" + (f" · HTTP {f['http']}" if f['http'] else ""))
    L.append("")
    L += ["## 2. Lo que dice la documentación de FIRMS (verificado con GET simple; copias en `data/raw/firms/missing_data/doc_*`)", ""]
    registro_docs = [f for f in leer_registro(cache) if f["tipo"] == "doc"]
    L += ["- `https://firms.modaps.eosdis.nasa.gov/api/` lista `missing_data` como «View dates with missing satellite data» y enlaza a "
          "`/api/missing_data/`. En esa fila no se menciona MAP_KEY (sí se usa en `area` y `data_availability`; `country` aparece como no disponible).",
          "- `/api/missing_data/` es una **página HTML** con dos tablas («Standard Data» y «Near Real Time Data»; columnas «Date Missing» y "
          "«Satellite (Sensor)»). Su cuerpo lo rellena el JavaScript de la propia página con `GET <página>?action=fetch_data` (JSON `{success, html, rowCount}`). "
          "No es una API documentada con parámetros de fecha ni de fuente: **hay que filtrar 2019–2021 localmente**.",
          "- La página aclara que los datos NRT «solo se muestran después de la última fecha estándar (SP) de cada satélite». Por tanto, para 2019–2021 "
          "las fuentes `*_NRT` no pueden aportar huecos por construcción; el hueco relevante es el de `*_SP`.",
          "- Premisa del encargo («`/api/missing_data/` requiere MAP_KEY»): **no se sostiene con esas páginas**. Este script no lee ni envía ninguna clave.",
          "- Observación de método: la tabla lista días sin datos en la base de FIRMS. Puede deberse a una caída del sensor o a un hueco de procesamiento "
          "de FIRMS; la tabla no distingue la causa."]
    for f in registro_docs:
        L.append(f"- Copia de página: `{f['archivo']}` · {f['bytes']} bytes · sha256 `{f['sha256']}` · {f['consulta_utc']}")
    L.append("")
    L += ["## 3. Días con hueco por mes y fuente (2019-01-01..2021-12-31)", ""]
    if filas is None:
        L += ["_Pendiente de respuesta real._", "",
              "## 4. Meses de W2 con algún hueco de NOAA-20 o S-NPP (umbral SIN decidir)", "",
              "_Pendiente de respuesta real. Se mostrará la lista para ≥ 1, ≥ 3 y ≥ 7 días (NOAA-20, S-NPP y unión)._", ""]
    else:
        agr = agregar(filas)
        L += ["| Mes | " + " | ".join(FUENTES) + " |", "|---|" + "---:|" * len(FUENTES)]
        for m in meses_w2():
            vals = [len(agr[f].get(m, ())) for f in FUENTES]
            L.append(f"| {m} | " + " | ".join(str(v) if v else "·" for v in vals) + " |")
        L += ["", "(`·` = 0 días con hueco.) Rangos de días con hueco dentro de W2, por fuente:", ""]
        for f in FUENTES:
            ds = [d for ms in agr[f].values() for d in ms]
            L.append(f"- **{f}**: {len(ds)} días · {fmt_rangos(rangos(ds))}")
        otros = sorted({s for fu, s, _d in filas if fu == "OTRO"})
        extra = sorted({fu for fu, _s, _d in filas if fu not in FUENTES and fu != "OTRO"})
        if otros or extra:
            L += ["", f"Etiquetas no clasificadas como fuente de interés: {otros or '—'} · otras fuentes presentes (sin tabla): {extra or '—'}"]
        L.append("")
        L += ["## 4. Meses de W2 con algún hueco de NOAA-20 o S-NPP (umbral SIN decidir)", ""]
        n20, snpp = dias_sensor(agr, "VIIRS_NOAA20"), dias_sensor(agr, "VIIRS_SNPP")
        union = {m: n20.get(m, set()) | snpp.get(m, set()) for m in meses_w2()}
        L += ["| Umbral (días con hueco en el mes) | NOAA-20 | S-NPP | Unión (cualquiera de los dos) |", "|---|---|---|---|"]
        for k in UMBRALES:
            a, b, u = (meses_con_hueco(x, k) for x in (n20, snpp, union))
            L.append(f"| ≥ {k} | {', '.join(a) or '—'} ({len(a)}) | {', '.join(b) or '—'} ({len(b)}) | {', '.join(u) or '—'} ({len(u)}) |")
        L += ["", "Formato de `config/validacion.yaml` (solo como ejemplo para una decisión futura; **no aplicado**):", "```yaml"]
        for k in UMBRALES:
            L.append(f"# umbral >= {k} día(s): meses_excluidos_huecos_viirs: {json.dumps(meses_con_hueco(union, k))}")
        L += ["```", "",
              "Notas: la unión cuenta un mes si NOAA-20 **o** S-NPP supera el umbral; la prueba usa NOAA-20 como VIIRS objetivo, por lo que "
              "S-NPP solo entra si se decide que cuenta como referencia. Las columnas ya excluyen NRT en 2019–2021 por construcción (§2).", ""]
    L += ["## 5. Cruce con `data/processed/disponibilidad_plataforma_dia.csv`", ""]
    if not disp.get("existe"):
        L += ["El archivo no existe; sin cruce.", ""]
    else:
        L += ["Solo se usan las columnas `fecha`, `plataforma`, `sin_datos`, `fuente`; `n_mx` y `n_ar` (conteos de detecciones) no se usan para nada. Antes de usar cualquier fila se descartaron las de "
              f"Terra/Aqua/S-NPP con fecha ≥ 2019-01-01 (anti-fuga): {disp['omitidas_antifuga']} filas descartadas.", "",
              "| Plataforma | Primer día | Último día | Días en tabla | Días `sin_datos` |", "|---|---|---|---:|---:|"]
        for p, c in sorted(disp["cobertura"].items()):
            L.append(f"| {p} | {c['min']} | {c['max']} | {c['dias']} | {c['sin_datos']} |")
        L += ["", f"**¿Cubre VIIRS?** {'sí' if disp['cubre_viirs'] else 'NO'}. **¿Cubre W2 (2019–2021)?** "
              f"{'sí' if any(c['max'] >= W2[0] for c in disp['cobertura'].values()) else 'NO'} (la tabla termina en 2018-12-31 por diseño anti-fuga, ADR-0005). "
              "Coincidencias con huecos de VIIRS en W2: **no hay cruce posible** (0 días en común por cobertura, no por ausencia de huecos).", ""]
        cr = cruce_modis_pre2019(filas or [], disp)
        L += ["### Cruce adicional MODIS < 2019 (verificación de la regla R1; no es parte de W2)", ""]
        if cr is None:
            L += ["_Pendiente de respuesta real._", ""]
        else:
            L += [f"- Días MODIS_SP con hueco en `missing_data` antes de 2019: {cr['n_missing_data']} · días `sin_datos` en la tabla: {cr['n_tabla']} · coinciden: {cr['ambos']}",
                  f"- Solo en `missing_data` (la tabla no los marca): {len(cr['solo_missing_data'])}"
                  + (f" · primeros: {[(p, d.isoformat()) for p, d in cr['solo_missing_data'][:10]]}" if cr['solo_missing_data'] else ""),
                  f"- Solo en la tabla (`missing_data` no los lista): {len(cr['solo_tabla'])}"
                  + (f" · primeros: {[(p, d.isoformat(), f) for p, d, f in cr['solo_tabla'][:10]]}" if cr['solo_tabla'] else ""),
                  "- Útil para el [VERIFICAR] abierto de 2017-04-24 (Terra marcado por la regla de datos).", ""]
    L += ["## 6. Reproducir", "", "```bash",
          "# 1) (con autorización) consulta en vivo + proceso; sin tubería",
          "flock data/.pesado.lock .venv/bin/python src/datos/huecos_firms.py --consultar",
          "# 2) solo reprocesar la caché (segunda corrida: cache hit, sin red)",
          "flock data/.pesado.lock .venv/bin/python src/datos/huecos_firms.py", "```", "",
          "Registro de consultas: `data/raw/firms/missing_data/registro.csv` (no versionado). Procedencia: `docs/02-datos/fuentes.md` "
          "(añadir la fila cuando exista una respuesta real).", ""]
    return enmascarar("\n".join(L))


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(RAIZ))
    except ValueError:
        return str(p)


# ───────────────────────────── main ─────────────────────────────
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--consultar", action="store_true", help="live query (OFF by default; needs authorization). Uses the cache if it exists")
    ap.add_argument("--refrescar", action="store_true", help="with --consultar: ignore the cache and query again")
    ap.add_argument("--importar", type=Path, help="copy a local file into the cache (offline tests / documentation pages)")
    ap.add_argument("--tipo", choices=["respuesta", "doc"], default="respuesta")
    ap.add_argument("--etiqueta", default="", help="note stored in the log (e.g. 'SYNTHETIC test fixture')")
    ap.add_argument("--nota", default="", help="append a free-text note row to registro.csv (e.g. why a live query was not run)")
    ap.add_argument("--cache-dir", type=Path, default=CACHE)
    ap.add_argument("--doc", type=Path, default=DOC)
    ap.add_argument("--disponibilidad", type=Path, default=DISPONIBILIDAD)
    a = ap.parse_args(argv)

    resp = None
    if a.nota:
        registrar(a.cache_dir, {"consulta_utc": ahora_utc().isoformat(timespec="seconds"), "tipo": "nota", "origen": "manual", "nota": a.nota})
    if a.importar:
        resp = importar(a.cache_dir, a.importar, a.tipo, a.etiqueta)
        resp = resp if a.tipo == "respuesta" else None
    if a.consultar:
        resp = consultar(a.cache_dir, a.refrescar, a.etiqueta)
    if resp is None:
        resp = ultima_respuesta(a.cache_dir)
    filas, sin_leer, meta, codigo, problema, cabeza = None, [], {}, 0, "", ""
    if resp is not None:
        crudo = (a.cache_dir / resp["archivo"]).read_bytes()
        cabeza = crudo[:300].decode("utf-8", "replace")
        try:
            filas, sin_leer, meta = parsear(crudo)
        except ValueError as e:
            problema = f"formato inesperado: {enmascarar(str(e))[:200]}"
            print(f"ERROR parsing the cached response: {problema}", file=sys.stderr)
            filas, codigo = None, 3
        if filas is not None:
            if not filas:
                problema = "la respuesta no contiene filas legibles"
                print("ERROR: the response contains no readable rows; NOT interpreted as 'no gaps'", file=sys.stderr)
                filas, codigo = None, 3
            else:
                escribir_por_fuente(a.cache_dir, filas, resp)
    if codigo == 0 and sin_leer:
        codigo = 3
        print(f"WARNING: {len(sin_leer)} rows not interpreted (see the document, section 1)", file=sys.stderr)
    if resp is None:
        codigo = 4      # pending: no response in the cache (never a silent success)
    disp = leer_disponibilidad(a.disponibilidad)
    etiqueta = resp["nota"] if resp else ""
    a.doc.parent.mkdir(parents=True, exist_ok=True)
    a.doc.write_text(render(resp, filas, sin_leer, meta, disp, a.cache_dir, etiqueta, problema, cabeza), encoding="utf-8")
    print(f"doc: {rel(a.doc)} · response: {resp['archivo'] if resp else 'NONE (pending state)'} · exit {codigo}")
    return codigo


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
