# Fixtures de respuestas reales

Capturas **reales** de las APIs/portales de origen, congeladas para tests de
parseo deterministas (issue #10). No se regeneran en cada corrida.

| Fixture | Origen | Captura |
|---|---|---|
| `marketplace/vtex_producto_arroz.json` | VTEX Catalog System de Plaza Vea (`/api/catalog_system/pub/products/search?fq=productId:101190089`) | 2026-06-11 |
| `sisap/sisap_lima_minorista_2026-05-15.html` | SISAP MIDAGRI (`/sisap/portal2/ciudades/resumenes/filtrar`, minorista, Lima, 15/05/2026) — 93 productos | 2026-06-11 |
| `sisap/sisap_sin_datos.html` | Misma fuente SISAP para una fecha sin datos publicados (respuesta "No existen datos") | 2026-06-11 |

## Re-captura

El SISAP geo-bloquea IPs fuera de Perú (ver `docs/ingesta_sisap_actions.md`), así
que la captura debe hacerse desde una IP peruana. Los parámetros usados son los
mismos que `observatorio/ingesta/sisap/run_ingesta_sisap.py` (region `150000`,
`variables[]=min_precio_prom`, `desde` = primer día del mes). El JSON de VTEX se
obtiene con el cliente legacy de `observatorio/ingesta/marketplace/client.py`.
