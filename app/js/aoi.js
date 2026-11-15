// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// aoi.js - PURE functions (no DOM, no network) for the AOI on the 0.1 degree grid.
// Tested in app/tests/aoi.test.mjs (node).
//
// Rules (ADR-0004, ADR-0009):
//  - The AOI is the set of 0.1 degree cells whose CENTER falls inside the drawing or the box.
//    Box: center >= minimum and center < maximum on each axis (CONTRATO-DATOS.md §4).
//  - Cell = lower-left corner with 1 decimal, id "lat_lon" (e.g. "19.0_-98.7").
//  - Integer cell index = floor(round(coord*1e5)/1e4) (formula of the data contract), so that the point CSV
//    and the monthly count agree by construction with what the exporter writes.
//  - Tile = "<floor(lat)>_<floor(lon)>" (1 degree).
//  - Outside the country polygons: "outside processed coverage" (never 0). A cell is covered if its center
//    falls inside the outline or if the outline crosses it (coast/border); see splitCoverage.

export const GRID_DEG = 0.1;
const EPS = 1e-9;

/**
 * Integer index of the cell that contains the coordinate. Formula of the contract (CONTRATO-DATOS.md §4):
 * lat_sw = floor(round(lat*1e5)/1e4)/10  (avoids floating-point errors; FIRMS gives 5 decimals).
 */
export function cellIndex(deg) {
  return Math.floor(Math.round(deg * 1e5) / 1e4);
}

/** Cell id "lat_lon" with 1 decimal from integer indices. */
export function cellId(ilat, ilon) {
  return `${fmt1(ilat)}_${fmt1(ilon)}`;
}

function fmt1(i) {
  // i/10 with one decimal; avoids "-0.0" because i=0 is not negative
  return (i / 10).toFixed(1);
}

/** Parses "lat_lon" -> {ilat, ilon}. Returns null if the format is invalid. */
export function parseCellId(id) {
  if (typeof id !== 'string') return null;
  const m = /^(-?\d+(?:\.\d+)?)_(-?\d+(?:\.\d+)?)$/.exec(id.trim());
  if (!m) return null;
  return { ilat: Math.round(parseFloat(m[1]) * 10), ilon: Math.round(parseFloat(m[2]) * 10) };
}

/** Normalizes an id (in case the exporter writes "19_-98.7" or "-0.0"). */
export function normalizeCellId(id) {
  const p = parseCellId(id);
  return p ? cellId(p.ilat, p.ilon) : null;
}

/** 1 degree tile id for cell indices. */
export function tileOfIndex(ilat, ilon) {
  return `${Math.floor(ilat / 10)}_${Math.floor(ilon / 10)}`;
}

/** Tile id for a point (degrees). */
export function tileOfPoint(lat, lon) {
  return `${Math.floor(lat)}_${Math.floor(lon)}`;
}

/** Cell key of a point, same as cellId but from coordinates. */
export function cellIdOfPoint(lat, lon) {
  return cellId(cellIndex(lat), cellIndex(lon));
}

/** Accepts [W,S,E,N] or {west,south,east,north} (also oeste/sur/este/norte, minLon...). */
export function normalizeBbox(b) {
  if (!b) return null;
  let west, south, east, north;
  if (Array.isArray(b) && b.length === 4) {
    [west, south, east, north] = b.map(Number);
  } else if (typeof b === 'object') {
    west = Number(b.west ?? b.oeste ?? b.minLon ?? b.min_lon ?? b.xmin);
    south = Number(b.south ?? b.sur ?? b.minLat ?? b.min_lat ?? b.ymin);
    east = Number(b.east ?? b.este ?? b.maxLon ?? b.max_lon ?? b.xmax);
    north = Number(b.north ?? b.norte ?? b.maxLat ?? b.max_lat ?? b.ymax);
  } else {
    return null;
  }
  if (![west, south, east, north].every(Number.isFinite)) return null;
  return { west, south, east, north };
}

/**
 * Validates a box against limits {south,north,west,east}.
 * Returns {ok, errors:[{field,message}]} (fields: south|north|west|east|bbox).
 */
export function validateBbox(bbox, limits) {
  const errors = [];
  const b = normalizeBbox(bbox);
  const fields = ['south', 'north', 'west', 'east'];
  if (!b) {
    for (const f of fields) {
      const v = bbox && typeof bbox === 'object' ? bbox[f] : undefined;
      if (v === undefined || v === null || v === '' || !Number.isFinite(Number(v))) {
        errors.push({ field: f, message: `${cap(f)} must be a number` });
      }
    }
    if (!errors.length) errors.push({ field: 'bbox', message: 'Bounds are incomplete' });
    return { ok: false, errors };
  }
  const lim = limits ? normalizeLimits(limits) : null;
  if (lim) {
    const chk = (f, v, lo, hi) => {
      if (v < lo || v > hi) errors.push({ field: f, message: `${cap(f)} must be between ${lo} and ${hi}` });
    };
    chk('south', b.south, lim.south, lim.north);
    chk('north', b.north, lim.south, lim.north);
    chk('west', b.west, lim.west, lim.east);
    chk('east', b.east, lim.west, lim.east);
  }
  if (b.south >= b.north) errors.push({ field: 'north', message: 'North must be greater than South' });
  if (b.west >= b.east) errors.push({ field: 'east', message: 'East must be greater than West' });
  return { ok: errors.length === 0, errors };
}

function normalizeLimits(l) {
  const b = normalizeBbox(l);
  return b;
}

function cap(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Number of cells that cellsInBbox would enumerate (to reject huge areas before iterating).
 */
export function estimateCells(bbox) {
  const b = normalizeBbox(bbox);
  if (!b) return 0;
  const nlat = Math.max(0, cellIndex(b.north) - cellIndex(b.south) + 1);
  const nlon = Math.max(0, cellIndex(b.east) - cellIndex(b.west) + 1);
  return nlat * nlon;
}

/** Number of 1 degree tiles that a box touches (to reject huge areas before computing cells). */
export function estimateTiles(bbox) {
  const b = normalizeBbox(bbox);
  if (!b) return 0;
  const nlat = Math.max(0, Math.floor(b.north) - Math.floor(b.south) + 1);
  const nlon = Math.max(0, Math.floor(b.east) - Math.floor(b.west) + 1);
  return nlat * nlon;
}

function makeCell(ilat, ilon) {
  return {
    id: cellId(ilat, ilon),
    ilat,
    ilon,
    lat: (ilat + 0.5) / 10, // center
    lon: (ilon + 0.5) / 10,
    tile: tileOfIndex(ilat, ilon),
  };
}

/** Cells whose center is inside the box: center >= minimum and center < maximum (tolerance 1e-9). */
export function cellsInBbox(bbox, { maxCells = 200000 } = {}) {
  const b = normalizeBbox(bbox);
  if (!b || b.south >= b.north || b.west >= b.east) return [];
  if (estimateCells(b) > maxCells) {
    throw new RangeError(`Area too large (${estimateCells(b)} cells > ${maxCells})`);
  }
  const out = [];
  for (let ilat = cellIndex(b.south) - 1; ilat <= cellIndex(b.north) + 1; ilat++) {
    const cy = (ilat + 0.5) / 10;
    if (cy < b.south - EPS || cy >= b.north - EPS) continue;
    for (let ilon = cellIndex(b.west) - 1; ilon <= cellIndex(b.east) + 1; ilon++) {
      const cx = (ilon + 0.5) / 10;
      if (cx < b.west - EPS || cx >= b.east - EPS) continue;
      out.push(makeCell(ilat, ilon));
    }
  }
  return out;
}

/** Point in ring (ray casting). ring: [[lon,lat],...] (open or closed). */
export function pointInRing(lon, lat, ring) {
  let inside = false;
  const n = ring.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** bbox of a ring. */
export function ringBbox(ring) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [x, y] of ring) {
    if (x < west) west = x;
    if (x > east) east = x;
    if (y < south) south = y;
    if (y > north) north = y;
  }
  return { west, south, east, north };
}

/** Cells whose center falls inside a simple polygon (ring [[lon,lat],...]). */
export function cellsInPolygon(ring, { maxCells = 200000 } = {}) {
  if (!Array.isArray(ring) || ring.length < 3) return [];
  const bb = ringBbox(ring);
  if (estimateCells(bb) > maxCells) {
    throw new RangeError(`Area too large (${estimateCells(bb)} cells > ${maxCells})`);
  }
  const out = [];
  for (let ilat = cellIndex(bb.south) - 1; ilat <= cellIndex(bb.north) + 1; ilat++) {
    const cy = (ilat + 0.5) / 10;
    if (cy < bb.south || cy > bb.north) continue;
    for (let ilon = cellIndex(bb.west) - 1; ilon <= cellIndex(bb.east) + 1; ilon++) {
      const cx = (ilon + 0.5) / 10;
      if (cx < bb.west || cx > bb.east) continue;
      if (pointInRing(cx, cy, ring)) out.push(makeCell(ilat, ilon));
    }
  }
  return out;
}

/** Extracts polygons from a GeoJSON (FeatureCollection | Feature | Geometry). Returns [[outer ring, ...holes]]. */
export function polygonsOfGeojson(gj) {
  const polys = [];
  const visit = (g) => {
    if (!g) return;
    if (g.type === 'FeatureCollection') g.features.forEach(visit);
    else if (g.type === 'Feature') visit(g.geometry);
    else if (g.type === 'GeometryCollection') g.geometries.forEach(visit);
    else if (g.type === 'Polygon') polys.push(g.coordinates);
    else if (g.type === 'MultiPolygon') g.coordinates.forEach((p) => polys.push(p));
  };
  visit(gj);
  return polys.map((rings) => ({ rings, bbox: ringBbox(rings[0]) }));
}

/** Point inside a set of polygons (with holes). polys comes from polygonsOfGeojson. */
export function pointInPolygons(lon, lat, polys) {
  for (const p of polys) {
    const b = p.bbox;
    if (lon < b.west || lon > b.east || lat < b.south || lat > b.north) continue;
    if (!pointInRing(lon, lat, p.rings[0])) continue;
    let inHole = false;
    for (let k = 1; k < p.rings.length; k++) {
      if (pointInRing(lon, lat, p.rings[k])) {
        inHole = true;
        break;
      }
    }
    if (!inHole) return true;
  }
  return false;
}

/**
 * Ids of the 0.1 degree cells that the border of the polygons CROSSES (coast and frontier). The edges are
 * sampled every `paso` degrees (0.02 = one fifth of a cell) and the cell of each sample is recorded.
 * With real data, the cells that only touch the country by its border hold detections: covering only the cells
 * with the CENTER inside the outline left out 1.2 % of the detections of Mexico and 0.48 % of
 * Argentina (measured, see app/tests/PRUEBA-INTEGRACION.md); with the border included 0.012 % and 0.003 % remain.
 */
export function boundaryCellIds(polys, paso = 0.02) {
  const ids = new Set();
  for (const p of polys) {
    for (const ring of p.rings) {
      for (let i = 1; i < ring.length; i++) {
        const [x0, y0] = ring[i - 1];
        const [x1, y1] = ring[i];
        const n = Math.max(1, Math.ceil(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) / paso));
        for (let k = 0; k <= n; k++) {
          const x = x0 + ((x1 - x0) * k) / n;
          const y = y0 + ((y1 - y0) * k) / n;
          ids.add(cellId(cellIndex(y), cellIndex(x)));
        }
      }
    }
  }
  return ids;
}

const cacheBorde = new WeakMap();

/**
 * Splits cells into inside / outside the coverage of a country. A cell is covered if its center falls inside
 * the outline or if the outline (coast or frontier) crosses it; the rest is "outside processed coverage".
 * {borde: false} uses only the center (previous rule).
 */
export function splitCoverage(cells, polys, { borde = true } = {}) {
  let tocadas = null;
  if (borde) {
    tocadas = cacheBorde.get(polys);
    if (!tocadas) cacheBorde.set(polys, (tocadas = boundaryCellIds(polys)));
  }
  const covered = [];
  const outside = [];
  for (const c of cells) (pointInPolygons(c.lon, c.lat, polys) || (tocadas && tocadas.has(c.id)) ? covered : outside).push(c);
  return { covered, outside };
}

/** Bounding box of cells (outer edges of the grid). null if there are no cells. */
export function bboxOfCells(cells) {
  if (!cells.length) return null;
  let a = Infinity;
  let b = -Infinity;
  let c = Infinity;
  let d = -Infinity;
  for (const x of cells) {
    if (x.ilat < a) a = x.ilat;
    if (x.ilat > b) b = x.ilat;
    if (x.ilon < c) c = x.ilon;
    if (x.ilon > d) d = x.ilon;
  }
  return { south: a / 10, north: (b + 1) / 10, west: c / 10, east: (d + 1) / 10 };
}

/** Groups cells by tile -> Map<tile, cells[]>. */
export function groupByTile(cells) {
  const m = new Map();
  for (const c of cells) {
    if (!m.has(c.tile)) m.set(c.tile, []);
    m.get(c.tile).push(c);
  }
  return m;
}

/** Runs per row for drawing: [{ilat, ilon0, ilon1}] (reduces the number of rectangles). */
export function rowRuns(cells) {
  const byRow = new Map();
  for (const c of cells) {
    if (!byRow.has(c.ilat)) byRow.set(c.ilat, []);
    byRow.get(c.ilat).push(c.ilon);
  }
  const runs = [];
  for (const [ilat, lons] of [...byRow.entries()].sort((x, y) => x[0] - y[0])) {
    lons.sort((x, y) => x - y);
    let start = lons[0];
    let prev = lons[0];
    for (let i = 1; i <= lons.length; i++) {
      const v = lons[i];
      if (v === prev + 1) {
        prev = v;
        continue;
      }
      runs.push({ ilat, ilon0: start, ilon1: prev });
      start = v;
      prev = v;
    }
  }
  return runs;
}

/**
 * Full snapping of an AOI to the grid.
 * fuente: {kind:'bbox', bbox} | {kind:'polygon', ring}
 * paisPolys: polygons (polygonsOfGeojson) of the target country, or null to skip the coverage classification.
 * Returns {cells, covered, outside, bbox (snapped, of all cells), coveredBbox, tiles (Set of the tiles of covered)}.
 */
export function snapAoi(fuente, paisPolys, opts = {}) {
  let cells = [];
  if (fuente.kind === 'polygon') cells = cellsInPolygon(fuente.ring, opts);
  else cells = cellsInBbox(fuente.bbox, opts);
  const { covered, outside } = paisPolys ? splitCoverage(cells, paisPolys) : { covered: cells, outside: [] };
  const tiles = new Set(covered.map((c) => c.tile));
  return { cells, covered, outside, bbox: bboxOfCells(cells), coveredBbox: bboxOfCells(covered), tiles };
}
