-- =============================================================================
-- Esquema de la capa Bronze del Observatorio de Precios.
--
-- DDL versionado de referencia (issue #54). Es idéntico al que genera en
-- tiempo de ejecución observatorio/carga/r2_a_supabase.py (función ddl_tabla):
-- el cargador hace CREATE SCHEMA/TABLE IF NOT EXISTS al correr, así que estas
-- tablas se autocrean. Este archivo sirve como spec legible, para revisión y
-- para recrear el esquema a mano si hiciera falta.
--
-- Convenciones:
--   * fecha_captura: YYYY-MM-DD en hora de Lima (UTC-5).
--   * fuente: columna de auditoría con el origen del dato.
--   * ingested_at: columna de auditoría, instante de carga a bronze.
--   * Columnas anulables salvo ingested_at: bronze guarda lo crudo tal cual;
--     la normalización/no-nulos es trabajo de la capa silver (dbt).
--
-- Clave natural e idempotencia (ver docs/carga_supabase.md):
--   * marketplace_precios: (fecha_captura, sku_id). Carga idempotente por
--     fecha → DELETE WHERE fecha_captura = :fecha; luego COPY.
--   * sisap_precios: (fecha_captura, tipo_mercado, producto). Carga idempotente
--     por (fecha, tipo_mercado) → DELETE WHERE fecha_captura = :fecha
--     AND tipo_mercado = :tipo; luego COPY.
--   DELETE + COPY van en una sola transacción por archivo.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;

-- Precios retail de Marketplace (VTEX / Plaza Vea). Una fila por SKU/día.
CREATE TABLE IF NOT EXISTS bronze.marketplace_precios (
    fecha_captura         date,
    fuente                text,
    product_id            text,
    sku_id                text,
    nombre                text,
    marca                 text,
    categoria             text,
    categoria_raiz        text,
    ean                   text,
    unidad_medida         text,
    multiplicador_unidad  double precision,
    precio                double precision,
    precio_lista          double precision,
    disponible            boolean,
    cantidad_disponible   integer,
    vendedor              text,
    url                   text,
    consulta              text,
    ingested_at           timestamptz NOT NULL DEFAULT now()
);

-- Precios de la canasta básica del SISAP (MIDAGRI). Una fila por
-- producto/día/región/tipo_mercado (minorista | mayorista).
CREATE TABLE IF NOT EXISTS bronze.sisap_precios (
    fecha_captura  date,
    fuente         text,
    region         text,
    tipo_mercado   text,
    producto       text,
    unidad_medida  text,
    equiv_kg_lt    double precision,
    precio_prom    double precision,
    ingested_at    timestamptz NOT NULL DEFAULT now()
);
