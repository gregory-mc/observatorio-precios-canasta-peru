# Fuentes de datos

Documentación de las fuentes que alimentan el observatorio.
Última actualización: 2026-05-29

---

## ✅ Fuentes vivas (ingesta diaria activa)

| Fuente | Qué publica | Frecuencia | Formato real | URL | Código |
|---|---|---|---|---|---|
| **SISAP — MIDAGRI** | Precios de referencia de la canasta básica en mercados minoristas de Lima Metropolitana | Diaria | HTML (scraping AJAX) | `http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar` | `observatorio/ingesta/sisap/` |
| **Marketplace — Plaza Vea (VTEX)** | Precios retail por SKU (nombre, marca, categoría, unidad, precio) | Diaria | JSON → CSV | `https://www.plazavea.com.pe/api/catalog_system/pub/products/search` | `observatorio/ingesta/marketplace/` |

### Notas de acceso y limitaciones

**SISAP — MIDAGRI**
- El servidor `sistemas.midagri.gob.pe` bloquea IPs de centros de datos extranjeros (Azure, AWS). Requiere **self-hosted runner con IP peruana** para ejecutarse desde GitHub Actions.
- El parámetro `desde` debe apuntar obligatoriamente al primer día del mes actual; `hasta` debe ser el día de hoy exacto — consultar fechas futuras devuelve tabla vacía sin error visible.
- El MIDAGRI no siempre publica antes de las 8 AM. El cron está ajustado a las **10:30 AM hora Perú (15:30 UTC)**.
- Infraestructura estatal con intermitencias frecuentes. La sesión HTTP tiene política de 3 reintentos con backoff de 2s.

**Marketplace — Plaza Vea (VTEX)**
- API pública sin autenticación requerida.
- Tope de **2,500 SKUs por búsqueda** en el endpoint legacy. Categorías con más SKUs deben consultarse por subcategorías.
- El endpoint moderno *Intelligent Search* regionaliza resultados y devuelve 0 para frescos (cebolla, huevos). Se usa el **endpoint legacy** `catalog_system`.
- Cron configurado a las **04:00 AM hora Perú (09:00 UTC)**.

---

## 🔲 Fuentes pendientes de implementar

### Fuentes vivas (diarias)

| Fuente | Qué publica | Frecuencia | Formato esperado | URL | Issue |
|---|---|---|---|---|---|
| **SENAMHI** | Clima diario por estación (lluvia, temp. mín/máx) | Diaria | API / boletín | `https://www.senamhi.gob.pe` | #14 |
| **OSINERGMIN** | Precios de combustible por departamento | Diaria | Web (tabla HTML) | `https://www.osinergmin.gob.pe` | #15 |

### Fuentes históricas / complementarias

| Fuente | Qué publica | Frecuencia | Formato esperado | URL | Issue |
|---|---|---|---|---|---|
| **INEI — IPC** | Índice de Precios al Consumidor, series de alimentos (base 2009) | Mensual | Excel / CSV | `https://www.inei.gob.pe` | #12 |
| **ENAHO — INEI** | Microdatos de gasto de hogares por departamento | Anual | SPSS / CSV | `https://www.inei.gob.pe/microdatos` | #13, #17, #19 |
| **MIDAGRI histórico** | Series históricas de precios al productor | One-shot | Web / Excel | `http://sistemas.midagri.gob.pe` | #16 |

---

## ❌ Fuentes descartadas

| Fuente | Motivo |
|---|---|
| **SIMA-PM (PRODUCE)** | Reemplazada por SISAP (precios de mercados) + Marketplace (precios retail). El formato PDF con `tabula-py` resultó innecesario. Ver issue #4. |

> **Nota técnica:** `tabula-py` quedó como dependencia sin uso en `pyproject.toml`. Evaluar eliminación si SIMA-PM no se retoma.

---

## Productos prioritarios (MVP)

Papa, limón, pollo, cebolla, huevo, tomate — por confirmar contra taxonomía SISAP en `observatorio/ingesta/canasta_productos.json`.

## Notas generales de extracción

- Los archivos crudos (HTML, JSON) se respaldan en **Cloudflare R2** para permitir reproceso sin volver a consultar la fuente.
- El cron de SISAP usa **self-hosted runner** (PC local con IP peruana). El de Marketplace usa runner estándar `ubuntu-latest`.
- Taxonomía de la canasta: `observatorio/ingesta/canasta_productos.json` (códigos producto/variedad SISAP).
