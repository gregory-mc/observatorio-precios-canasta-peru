-- =============================================================================
-- Esquema de la capa Gold del Observatorio de Precios — issue #19.
--
-- DDL versionado de referencia. Es idéntico al que generan en tiempo de ejecución
-- observatorio/canasta/construir_canasta.py (canasta_consumo_dept) y
-- observatorio/canasta/dim_departamento.py (dim_departamento): ambos hacen
-- CREATE SCHEMA/TABLE IF NOT EXISTS al correr, así que las tablas se autocrean.
-- Este archivo es la spec legible para revisión y para recrear el esquema a mano.
--
-- Contrato definido en docs/canasta_consumo_dept.md (diseño, issue #17). En S6
-- (dbt, M3) estas tablas se reescriben como modelos dbt manteniendo el mismo
-- contrato.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- Pesos de la canasta de alimentos del MVP por departamento, desde la ENAHO.
-- Una fila por (año de encuesta, departamento, producto). Tabla estructural,
-- sin fecha de precio: se recalcula al cambiar de año de ENAHO.
-- Idempotencia por año: DELETE WHERE anio_enaho = :anio; luego COPY.
CREATE TABLE IF NOT EXISTS gold.canasta_consumo_dept (
    anio_enaho             smallint          NOT NULL,  -- año de la ENAHO (p.ej. 2023)
    cod_departamento       char(2)           NOT NULL,  -- 2 díg. del ubigeo ('01'..'25')
    departamento           text              NOT NULL,  -- nombre (incl. Callao)
    producto               text              NOT NULL,  -- slug MVP: papa|limon|pollo|cebolla|huevo|tomate
    grupo_enaho            char(2)           NOT NULL,  -- grupo de 2 díg. de p601a (05,07,09,32,33,38)

    -- Agregados ponderados por factor07 (expandidos a población). Soles ANUALES.
    gasto_monetario_anual  double precision,            -- Σ(i601c · factor07): solo COMPRA
    gasto_total_anual      double precision,            -- Σ((i601c + i601e) · factor07): compra + autoconsumo
    cantidad_kg_anual      double precision,            -- Σ(i601b2 · factor07): kg comprados

    -- Soporte muestral (para fiabilidad; celdas con n_muestra < 30 = baja confianza).
    n_muestra              integer,                     -- nº de hogares en la muestra (SIN expandir)
    hogares_expandidos     double precision,            -- Σ(factor07): hogares representados

    -- Peso final usado por la canasta. Normalizado DENTRO del MVP por (anio, depto):
    -- Σ peso_canasta = 1.0 por cada (anio_enaho, cod_departamento). Base: gasto_monetario.
    peso_canasta           double precision  NOT NULL,

    fuente                 text              NOT NULL,  -- 'ENAHO <anio> Mód.601 (INEI)'
    computed_at            timestamptz       NOT NULL DEFAULT now(),

    PRIMARY KEY (anio_enaho, cod_departamento, producto)
);

-- Dimensión de departamentos: puente entre el ubigeo (llave canónica de la
-- canasta) y el nombre de región que usan las tablas de precios (SISAP).
-- region_sisap es best-effort (= nombre del depto por defecto); reconciliar
-- contra SELECT DISTINCT region FROM bronze.sisap_precios. Ver dim_departamento.py.
CREATE TABLE IF NOT EXISTS gold.dim_departamento (
    cod_departamento  char(2)  NOT NULL,  -- '01'..'25'
    departamento      text     NOT NULL,  -- nombre oficial INEI
    region_sisap      text,               -- nombre de región en bronze.sisap_precios
    PRIMARY KEY (cod_departamento)
);
