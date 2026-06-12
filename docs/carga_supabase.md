# Carga Bronze: Cloudflare R2 → Supabase Postgres

Componente que cierra el `TODO(S2)` del pipeline: toma los CSV crudos que los
scrapers dejaron en **Cloudflare R2** y los inserta en **Supabase Postgres**
bajo el schema `bronze`. Desde ahí dbt construye las capas silver/gold.

- **Código:** [`observatorio/carga/r2_a_supabase.py`](../observatorio/carga/r2_a_supabase.py)
- **Conexión:** `psycopg` directo al pooler de Supabase (no PostgREST). Usa `COPY`
  para carga masiva y permite escribir en el schema `bronze`, que es además el
  que consumirá `dbt-postgres`.

## Mapeo de archivos

| Clave en R2 | Tabla destino |
|---|---|
| `marketplace/<fecha>.csv` | `bronze.marketplace_precios` |
| `sisap/<fecha>_sisap_lima_minorista.csv` | `bronze.sisap_precios` |
| `sisap/<fecha>_sisap_lima_mayorista.csv` | `bronze.sisap_precios` |

Las columnas de cada tabla se derivan del mismo esquema que define el COPY
(una sola fuente de verdad), espejando las dataclasses `ProductoPrecio` y
`PrecioSisap` de la ingesta. Cada tabla añade `ingested_at timestamptz`.

## Esquema de las tablas

El DDL versionado de referencia vive en
[`observatorio/carga/sql/bronze_schema.sql`](../observatorio/carga/sql/bronze_schema.sql).
Es idéntico al que el cargador genera y ejecuta en runtime (`CREATE SCHEMA/TABLE
IF NOT EXISTS`), así que las tablas se autocrean en la primera corrida.

### `bronze.marketplace_precios` — una fila por SKU/día

| columna | tipo | nota |
|---|---|---|
| `fecha_captura` | `date` | YYYY-MM-DD hora Lima |
| `fuente` | `text` | auditoría — origen (`marketplace`) |
| `product_id`, `sku_id` | `text` | identificadores VTEX |
| `nombre`, `marca` | `text` | |
| `categoria`, `categoria_raiz` | `text` | ruta y raíz de categoría |
| `ean` | `text` | código de barras |
| `unidad_medida` | `text` | `measurementUnit` VTEX |
| `multiplicador_unidad` | `double precision` | |
| `precio`, `precio_lista` | `double precision` | venta / antes de descuento |
| `disponible` | `boolean` | |
| `cantidad_disponible` | `integer` | |
| `vendedor`, `url`, `consulta` | `text` | `consulta` = trazabilidad del target |
| `ingested_at` | `timestamptz NOT NULL DEFAULT now()` | auditoría — instante de carga |

### `bronze.sisap_precios` — una fila por producto/día/región/tipo_mercado

| columna | tipo | nota |
|---|---|---|
| `fecha_captura` | `date` | YYYY-MM-DD hora Lima |
| `fuente` | `text` | auditoría — origen (`sisap_midagri`) |
| `region` | `text` | p. ej. `Lima` |
| `tipo_mercado` | `text` | `minorista` \| `mayorista` |
| `producto` | `text` | nombre tal cual del HTML |
| `unidad_medida` | `text` | puede venir vacío |
| `equiv_kg_lt` | `double precision` | equivalencia kg/lt (anulable) |
| `precio_prom` | `double precision` | promedio en soles (anulable = sin reporte) |
| `ingested_at` | `timestamptz NOT NULL DEFAULT now()` | auditoría — instante de carga |

Todas las columnas son anulables salvo `ingested_at`: bronze guarda lo crudo tal
cual; la normalización y los no-nulos son trabajo de la capa silver (dbt).

## Clave natural e idempotencia

| tabla | clave natural | partición de carga (idempotencia) |
|---|---|---|
| `bronze.marketplace_precios` | `(fecha_captura, sku_id)` | por `fecha_captura` |
| `bronze.sisap_precios` | `(fecha_captura, tipo_mercado, producto)` | por `(fecha_captura, tipo_mercado)` |

La carga es idempotente **por fecha** (y por tipo de mercado en SISAP), igual
que el scraper sobreescribe el CSV del día en R2: antes de insertar, borra las
filas de esa partición con un `DELETE` y luego hace `COPY`. Ambos van en una
misma transacción, así que un fallo a mitad no deja la tabla en estado
intermedio. Re-correr un día es seguro (no duplica).

## Variables de entorno

```
R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
SUPABASE_DB_URL   # connection string del pooler de Supabase, puerto 6543
```

El `SUPABASE_DB_URL` se obtiene en Supabase → *Project Settings → Database →
Connection string → Transaction pooler*, con la forma:

```
postgresql://postgres.<ref>:<password>@<host>:6543/postgres?sslmode=require
```

> ⚠️ Es un **secret nuevo** del repo (`Settings → Secrets and variables → Actions`),
> distinto de los `SUPABASE_URL`/`SUPABASE_KEY` del handshake REST existente.

## Uso

```bash
pip install -e ".[carga]"   # boto3; psycopg ya viene en las deps base

python -m observatorio.carga.r2_a_supabase                      # ambas fuentes, hoy (Lima)
python -m observatorio.carga.r2_a_supabase --fuente marketplace
python -m observatorio.carga.r2_a_supabase --fuente sisap --fecha 2026-06-01
```

`--fuente` acepta `marketplace`, `sisap` o `ambas` (default). `--fecha` por
defecto es hoy en hora de Lima (UTC-5), el mismo criterio que los scrapers.
`SIMULAR_FALLO=true` fuerza un fallo intencional para probar la alerta, igual
que en los scrapers.

## Workflow

Corre en su **propio workflow** independiente de los scrapers:
[`.github/workflows/carga-supabase.yml`](../.github/workflows/carga-supabase.yml).

- **Horario:** cron `0 21 * * *` = **16:00 hora Lima (UTC-5)**, después de que
  ambos scrapers (marketplace 09:00, SISAP 14:00) ya dejaron los CSV del día
  en R2.
- **Runner:** `ubuntu-latest`. Solo habla con R2 (Cloudflare) y Supabase, ambos
  públicos, así que no aplica el geo-bloqueo del MIDAGRI que obliga al
  self-hosted en la ingesta SISAP.
- **Fuente:** carga `ambas` por defecto. El `workflow_dispatch` permite elegir
  `fuente` y `fecha` para re-cargas manuales puntuales.
- Si la carga falla, el job termina en error y el step de alerta crea el issue
  automático en GitHub (mismo patrón que los scrapers).
