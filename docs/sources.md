# Fuentes de datos

Documentación de las fuentes que alimentan el observatorio. Completar durante S1 (tarea `area:datos`).

## Fuentes vivas (actualización diaria)

| Fuente | Qué publica | Frecuencia | Formato | URL | Método de extracción |
|---|---|---|---|---|---|
| **SIMA-PM** (PRODUCE) | Precios y volúmenes mayoristas (Santa Anita, Frutas La Victoria, regionales) | Diaria | PDF / HTML | _(por documentar)_ | scraping + `tabula-py` |
| **SENAMHI** | Clima (lluvia, temp. mín/máx) por estación | Diaria | API / boletín | _(por documentar)_ | API o scraping |
| **OSINERGMIN** | Precios de combustible por departamento | Diaria | Web | _(por documentar)_ | scraping |

## Fuentes históricas / complementarias

| Fuente | Qué publica | Frecuencia | Formato | URL | Notas |
|---|---|---|---|---|---|
| **INEI – IPC** | Índice de precios al consumidor, series de alimentos | Mensual | Excel / CSV | _(por documentar)_ | Histórico base 2009 |
| **MIDAGRI (SISAP)** | Precios al productor y consumidor | Semanal | Web / Excel | _(por documentar)_ | Contexto de cosechas |
| **ENAHO (INEI)** | Microdatos de gasto de hogares | Anual | SPSS / CSV | _(por documentar)_ | Para construir la canasta por departamento |

## Productos prioritarios (MVP)

Por confirmar. Sugeridos: papa, limón, pollo, cebolla, huevo, tomate.

## Notas de extracción

- Cron de ingesta: 04:00 UTC-5 (datos del día anterior, publicados al cierre del mercado).
- PDFs crudos se respaldan en Cloudflare R2 para permitir reproceso.
