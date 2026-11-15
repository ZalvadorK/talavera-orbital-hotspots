# Vendored third-party libraries

SI-generated (AI): Claude Code wrote this during the event; reviewed by the team.

All libraries are copied unmodified into `app/vendor/` so the app does not depend on a CDN
in the judge's network. Versions are exact and were published more than two weeks before
the download (2026-11-14).

Integrity method:
1. Each file was downloaded into a brand-new empty folder from **jsDelivr** (`cdn.jsdelivr.net/npm`)
   and again, into a second empty folder, from **unpkg** (`unpkg.com`).
2. The SHA-256 of all 47 downloaded files was compared: identical on both hosts (46 are kept, plus `echarts/licenses/LICENSE-d3` added later and compared the same way: 47 files in `SHA256SUMS`; `leaflet-draw/package.json` and `hyparquet/src/types.d.ts` are not needed at runtime and were left out; the Leaflet.draw license text comes from the GitHub tag through jsDelivr).
3. The downloaded content was treated as untrusted data: only copied, never executed with Node.
4. `cd app/vendor && sha256sum -c SHA256SUMS` re-checks every file (list of all hashes in `SHA256SUMS`).
5. `descargar_vendor.sh <empty-folder> <jsdelivr|unpkg>` repeats the download for an independent comparison.

| Library | Exact version | Published (npm) | License | Used for |
|---|---|---|---|---|
| Leaflet | 1.9.4 | 2023-05-18 | BSD-2-Clause | Map |
| Leaflet.draw | 1.0.4 | 2018-10-24 | MIT | Rectangle and polygon drawing |
| ECharts | 5.5.1 | 2024-06-27 | Apache-2.0 | Calendar charts (loaded by the calendar module, not by the page shell) |
| hyparquet | 1.29.2 | 2026-08-26 | MIT | Reads the point tiles (Parquet, snappy) only when the CSV is requested |

## Files, source URLs and SHA-256

Source URL pattern: `https://cdn.jsdelivr.net/npm/<package>@<version>/<path>` (same bytes at
`https://unpkg.com/<package>@<version>/<path>`).

| Local file | Source (package path) | SHA-256 |
|---|---|---|
| `leaflet/leaflet.js` | `leaflet@1.9.4/dist/leaflet.js` | `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a` |
| `leaflet/leaflet.css` | `leaflet@1.9.4/dist/leaflet.css` | see `SHA256SUMS` |
| `leaflet/images/*.png` | `leaflet@1.9.4/dist/images/` | see `SHA256SUMS` |
| `leaflet/LICENSE` | `leaflet@1.9.4/LICENSE` | `53e8dc25862014e4324741ca18fbe3611e11d42ef69f59f86ea8c5389647d4cb` |
| `leaflet-draw/leaflet.draw.js` | `leaflet-draw@1.0.4/dist/leaflet.draw.js` | `b22a1f7385308e5adadd85a4c2d84e9fc523ebd70d37868cba0fe2387362460b` |
| `leaflet-draw/leaflet.draw.css` | `leaflet-draw@1.0.4/dist/leaflet.draw.css` | see `SHA256SUMS` |
| `leaflet-draw/images/*` | `leaflet-draw@1.0.4/dist/images/` | see `SHA256SUMS` |
| `leaflet-draw/LICENSE` | `https://cdn.jsdelivr.net/gh/Leaflet/Leaflet.draw@v1.0.4/MIT-LICENSE.md` (the npm package ships no license file; `package.json` declares MIT) | `320f2c68ac27b7f7f2a78c490470a273d297e753ab37ba026944616bf0a62f47` |
| `echarts/echarts.min.js` | `echarts@5.5.1/dist/echarts.min.js` | `e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf` |
| `echarts/LICENSE`, `echarts/NOTICE` | `echarts@5.5.1/LICENSE`, `/NOTICE` | see `SHA256SUMS` |
| `echarts/licenses/LICENSE-d3` | `echarts@5.5.1/licenses/LICENSE-d3` (BSD-3-Clause text of d3, copyright 2010-2016 Mike Bostock; the ECharts `LICENSE` points to it: "See `/licenses/LICENSE-d3` for details of the license") | `e1211892da0b0e0585b7aebe8f98c1274fba15bafe47fa1f4ee8a7a502c06304` |
| `hyparquet/src/*.js` (27 ES modules, `types.d.ts` omitted) | `hyparquet@1.29.2/src/` | see `SHA256SUMS` |
| `hyparquet/LICENSE`, `hyparquet/package.json` | `hyparquet@1.29.2/LICENSE`, `/package.json` | see `SHA256SUMS` |

## Notes

- hyparquet ships as ES modules (no bundle). The app imports `vendor/hyparquet/src/index.js`
  dynamically, only when the user asks for the CSV. It reads uncompressed and snappy Parquet
  without extra decompressors; the point tiles must therefore be written with **snappy**
  (zstd would need `hyparquet-compressors`, which is not vendored).
- Leaflet.draw 1.0.4 is from 2018. Some bundler setups report `type is not defined` in the area
  read-out (`showArea: true`); it did not reproduce with this classic-script build, but the app
  sets `showArea: false` as a precaution. Smoke test with Leaflet 1.9.4: `app/humo/index.html`
  (rectangle and polygon drawn with a real mouse in headless Chromium: `app/tests/e2e-navegador.mjs`).
- `echarts/licenses/LICENSE-d3` (2026-11-15): the ECharts 5.5.1 `LICENSE` lists d3.js (BSD-3-Clause) as an embedded subcomponent and refers to `/licenses/LICENSE-d3`, which was missing from the vendored copy. It was downloaded with `curl` (no `-k`) from `https://cdn.jsdelivr.net/npm/echarts@5.5.1/licenses/LICENSE-d3` into an empty folder and again from `https://unpkg.com/echarts@5.5.1/licenses/LICENSE-d3` into a second one; both gave the same 1475 bytes and the same SHA-256 (above). It is plain text, copied unmodified and never executed.
- No NASA logos or insignia are included in any vendored file.
