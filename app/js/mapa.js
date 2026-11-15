// SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
//
// mapa.js - Leaflet map + Leaflet.draw. Uses the global `L` (app/vendor/leaflet, app/vendor/leaflet-draw).
// Works WITHOUT a basemap: the country outlines come from our own GeoJSON.
// The OSM layer is optional and has a fallback: after CONFIG.BASEMAP.errorLimit tile errors it is
// removed and the user is told.

import { rowRuns } from './aoi.js';

const COLOR = {
  mexico: '#CC79A7', // paleta.json: paises.Mexico
  argentina: '#332288', // paleta.json: paises.Argentina
  covered: '#0072B2',
  coveredStroke: '#00334F',
  outside: '#6B6B6B',
  drawn: '#D55E00',
};

/**
 * Creates the map.
 * opts: {config, onShape(shape), onCleared(), onBasemapFailed(), onError(err)}
 * shape: {kind:'bbox', bbox:{west,south,east,north}} | {kind:'polygon', ring:[[lon,lat],...]}
 */
export function crearMapa(elementId, opts) {
  const L = window.L;
  if (!L) throw new Error('Leaflet is not loaded');
  const cfg = opts.config;
  const map = L.map(elementId, {
    center: cfg.MAP.center,
    zoom: cfg.MAP.zoom,
    minZoom: cfg.MAP.minZoom,
    zoomControl: true,
    preferCanvas: true,
    attributionControl: true,
  });
  map.attributionControl.setPrefix('Leaflet');

  /* --- optional basemap with fallback --- */
  let basemap = null;
  let tileErrors = 0;
  const bm = cfg.BASEMAP;
  function activarBasemap() {
    if (basemap) return;
    tileErrors = 0;
    basemap = L.tileLayer(bm.url, { attribution: bm.attribution, maxZoom: bm.maxZoom, crossOrigin: false });
    basemap.on('tileerror', () => {
      tileErrors++;
      if (tileErrors >= bm.errorLimit) {
        desactivarBasemap();
        if (opts.onBasemapFailed) opts.onBasemapFailed();
      }
    });
    basemap.addTo(map);
    basemap.bringToBack();
  }
  function desactivarBasemap() {
    if (!basemap) return;
    map.removeLayer(basemap);
    basemap = null;
  }

  /* --- outlines --- */
  const contornos = new Map(); // paisId -> L.GeoJSON
  const contornosGrupo = L.featureGroup().addTo(map);

  function agregarContorno(paisId, geojson) {
    if (contornos.has(paisId)) contornosGrupo.removeLayer(contornos.get(paisId));
    const layer = L.geoJSON(geojson, {
      interactive: false,
      style: { color: COLOR[paisId] || '#4D4D4D', weight: 2, fillColor: COLOR[paisId] || '#4D4D4D', fillOpacity: 0.06 },
    });
    contornos.set(paisId, layer);
    contornosGrupo.addLayer(layer);
  }

  function resaltarPais(paisId) {
    for (const [id, layer] of contornos) {
      layer.setStyle({ weight: id === paisId ? 3 : 1.5, fillOpacity: id === paisId ? 0.1 : 0.03, opacity: id === paisId ? 1 : 0.6 });
    }
  }

  function ajustarA(bbox, { padding = [20, 20], maxZoom = 9 } = {}) {
    if (!bbox) return;
    // animate:false -> Leaflet drops a zoom request if another animation is still running;
    // without animation the adjustment is always applied.
    map.fitBounds([[bbox.south, bbox.west], [bbox.north, bbox.east]], { padding, maxZoom, animate: false });
  }

  /* --- drawing --- */
  const dibujados = new L.FeatureGroup().addTo(map);
  const celdasGrupo = L.featureGroup().addTo(map);

  const drawControl = new L.Control.Draw({
    position: 'topleft',
    draw: {
      polyline: false,
      circle: false,
      circlemarker: false,
      marker: false,
      // showArea:false avoids the error "type is not defined" of Leaflet.draw 1.0.4 with Leaflet 1.9
      rectangle: { showArea: false, shapeOptions: { color: COLOR.drawn, weight: 2, dashArray: '6 4', fillOpacity: 0.05 } },
      polygon: {
        showArea: false,
        allowIntersection: false,
        drawError: { color: '#B00020', message: 'Polygon edges cannot cross' },
        shapeOptions: { color: COLOR.drawn, weight: 2, dashArray: '6 4', fillOpacity: 0.05 },
      },
    },
    edit: { featureGroup: dibujados, edit: false, remove: true },
  });
  map.addControl(drawControl);

  map.on(L.Draw.Event.CREATED, (ev) => {
    try {
      dibujados.clearLayers();
      dibujados.addLayer(ev.layer);
      let shape;
      if (ev.layerType === 'rectangle') {
        const b = ev.layer.getBounds();
        shape = { kind: 'bbox', bbox: { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() } };
      } else if (ev.layerType === 'polygon') {
        const ll = ev.layer.getLatLngs()[0];
        shape = { kind: 'polygon', ring: ll.map((p) => [p.lng, p.lat]) };
      } else {
        return;
      }
      opts.onShape(shape);
    } catch (e) {
      if (opts.onError) opts.onError(e);
      else throw e;
    }
  });

  map.on(L.Draw.Event.DELETED, () => {
    celdasGrupo.clearLayers();
    if (opts.onCleared) opts.onCleared();
  });

  /* --- snapped cells --- */
  /** Draws covered cells (blue fill) and cells outside coverage (dashed gray). */
  function pintarCeldas({ covered, outside }) {
    celdasGrupo.clearLayers();
    const dibujar = (cells, style, forzarCeldas) => {
      if (!cells.length) return;
      if (forzarCeldas || cells.length <= 800) {
        for (const c of cells) {
          L.rectangle([[c.ilat / 10, c.ilon / 10], [(c.ilat + 1) / 10, (c.ilon + 1) / 10]], { ...style, interactive: false }).addTo(celdasGrupo);
        }
      } else {
        for (const r of rowRuns(cells)) {
          L.rectangle([[r.ilat / 10, r.ilon0 / 10], [(r.ilat + 1) / 10, (r.ilon1 + 1) / 10]], { ...style, weight: 0, interactive: false }).addTo(celdasGrupo);
        }
      }
    };
    dibujar(outside, { color: COLOR.outside, weight: 1, dashArray: '3 3', fillColor: COLOR.outside, fillOpacity: 0.12 });
    dibujar(covered, { color: COLOR.coveredStroke, weight: 0.6, fillColor: COLOR.covered, fillOpacity: 0.35 });
  }

  /** Shows the drawn/typed shape (original box) to compare with the snapped cells. */
  function pintarFormaOriginal(shape) {
    dibujados.clearLayers();
    if (!shape) return;
    const estilo = { color: COLOR.drawn, weight: 2, dashArray: '6 4', fillOpacity: 0.05 };
    if (shape.kind === 'bbox') {
      const b = shape.bbox;
      L.rectangle([[b.south, b.west], [b.north, b.east]], estilo).addTo(dibujados);
    } else if (shape.kind === 'polygon') {
      L.polygon(shape.ring.map(([x, y]) => [y, x]), estilo).addTo(dibujados);
    }
  }

  function limpiar() {
    dibujados.clearLayers();
    celdasGrupo.clearLayers();
  }

  if (bm.enabledByDefault) activarBasemap();

  return {
    map,
    agregarContorno,
    resaltarPais,
    ajustarA,
    pintarCeldas,
    pintarFormaOriginal,
    limpiar,
    activarBasemap,
    desactivarBasemap,
    hayBasemap: () => !!basemap,
    invalidar: () => map.invalidateSize(),
    boundsDePaises: () => (contornosGrupo.getLayers().length ? contornosGrupo.getBounds() : null),
  };
}
