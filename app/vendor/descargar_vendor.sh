#!/usr/bin/env bash
# SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.
# Descarga (solo bytes, sin ejecutar) las librerias fijadas a un directorio NUEVO y VACIO.
# Uso: descargar_vendor.sh <destino> <jsdelivr|unpkg>
set -euo pipefail
DEST="$1"; HOST="$2"
[ -z "$(ls -A "$DEST" 2>/dev/null || true)" ] || { echo "destino no vacio: $DEST" >&2; exit 2; }
mkdir -p "$DEST"
base() { # paquete@version  -> prefijo URL
  case "$HOST" in
    jsdelivr) echo "https://cdn.jsdelivr.net/npm/$1" ;;
    unpkg)    echo "https://unpkg.com/$1" ;;
  esac
}
get() { # paquete@version ruta_en_paquete ruta_destino
  mkdir -p "$(dirname "$DEST/$3")"
  curl -fsS --max-time 60 --retry 2 -o "$DEST/$3" "$(base "$1")/$2"
}
L=leaflet@1.9.4
for f in dist/leaflet.js dist/leaflet.css LICENSE dist/images/layers.png dist/images/layers-2x.png dist/images/marker-icon.png dist/images/marker-icon-2x.png dist/images/marker-shadow.png; do
  get $L $f "leaflet/${f#dist/}"
done
D=leaflet-draw@1.0.4
for f in dist/leaflet.draw.js dist/leaflet.draw.css dist/images/spritesheet.png dist/images/spritesheet-2x.png dist/images/spritesheet.svg package.json; do
  get $D $f "leaflet-draw/${f#dist/}"
done
E=echarts@5.5.1
for f in dist/echarts.min.js LICENSE NOTICE licenses/LICENSE-d3; do get $E $f "echarts/${f#dist/}"; done
H=hyparquet@1.29.2
for f in LICENSE package.json src/assemble.js src/bloom.js src/column.js src/constants.js src/convert.js src/datapage.js src/delta.js src/encoding.js src/filter.js src/geoparquet.js src/index.js src/indexes.js src/metadata.js src/node.js src/plain.js src/plan.js src/query.js src/read.js src/rowgroup.js src/scan.js src/schema.js src/snappy.js src/thrift.js src/types.d.ts src/utils.js src/variant.js src/wkb.js src/xxhash.js; do
  get $H $f "hyparquet/$f"
done
echo "ok $HOST"
