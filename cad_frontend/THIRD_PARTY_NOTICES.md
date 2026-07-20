# Local CAD viewer third-party notices

The WMS CAD preview is built from the pinned packages in `package-lock.json`.
It operates entirely in the user's browser and does not transmit drawings to an
external service.

- `@mlightcad/cad-simple-viewer` 1.5.8 and
  `@mlightcad/cad-simple-ui-plugin` 1.5.8 — MIT; source:
  <https://github.com/mlightcad/cad-viewer/tree/v1.5.8>
- `@mlightcad/data-model` 1.11.1 — MIT; source:
  <https://github.com/mlightcad/realdwg-web>
- `@mlightcad/dxf-json-converter` 1.11.1 — package metadata declares GPL-3.0;
  source: <https://github.com/mlightcad/realdwg-web>
- The DWG WebAssembly worker is based on GNU LibreDWG and is distributed under
  GPL-3.0; source: <https://github.com/LibreDWG/libredwg>
- Three.js 0.172.0 and Lodash 4.17.21 — MIT.
- Poppins Regular is distributed under the SIL Open Font License 1.1. Its license
  is included at `vendor/fonts/OFL.txt`; source:
  <https://github.com/google/fonts/tree/main/ofl/poppins>.

The generated files in `static/cad_viewer/` can be reproduced with:

```powershell
cd cad_frontend
npm.cmd install
npm.cmd run build
```

When distributing WMS outside your organization, retain these notices and comply
with the GPL-3.0 source-distribution requirements for the CAD parser components.
