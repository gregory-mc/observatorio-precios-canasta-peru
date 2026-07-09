-- =============================================================================
-- Esquema de la capa ML del Observatorio de Precios — Milestone M4.
--
-- DDL versionado de referencia. Es idéntico al que crea en tiempo de ejecución
-- observatorio/ml/persistencia.py (CREATE SCHEMA/TABLE IF NOT EXISTS al correr),
-- así que las tablas se autocrean. Este archivo es la spec legible para revisión
-- y para recrear el esquema a mano.
--
-- Contrato con el medallion: esta capa es la SALIDA CRUDA del modelado (la
-- escribe Python). dbt la lee como source `ml` y construye los marts gold
-- (gold.fct_predicciones, gold.fct_anomalias) en un PR posterior — igual que
-- bronze.* alimenta silver/gold. Python nunca escribe gold.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS ml;

-- Pronósticos de precio por serie y corrida. Una fila por
-- (fecha_corrida, fuente, cod_departamento, producto, fecha_pred).
-- Idempotente por corrida: DELETE WHERE fecha_corrida = :fecha; luego insert.
CREATE TABLE IF NOT EXISTS ml.predicciones_raw (
    fecha_corrida         date              NOT NULL,  -- día en que se corrió el batch (hora Lima)
    fuente                text              NOT NULL,  -- sisap_minorista | sisap_mayorista | ...
    cod_departamento      char(2),                     -- '15' Lima (SISAP); null = nacional
    producto              text              NOT NULL,  -- nombre crudo de la fuente (grano de fct_precio_diario)
    fecha_pred            date              NOT NULL,  -- día pronosticado (futuro respecto a fecha_corrida)

    yhat                  double precision  NOT NULL,  -- pronóstico central
    yhat_lower            double precision,            -- banda inferior (null para baseline)
    yhat_upper            double precision,            -- banda superior (null para baseline)

    modelo                text              NOT NULL,  -- 'prophet' | 'media_movil' | 'naive'
    n_obs_entrenamiento   integer           NOT NULL,  -- nº de observaciones que vio el modelo
    computed_at           timestamptz       NOT NULL DEFAULT now(),

    -- OJO: al entrar cod_departamento en el PK, Postgres lo fuerza a NOT NULL.
    -- En el MVP no molesta (solo se modela SISAP, cod '15'). Si más adelante se
    -- modela una fuente de ámbito nacional (cod null), habrá que darle un
    -- sentinel (p.ej. '00') o cambiar el PK por un índice único con COALESCE.
    PRIMARY KEY (fecha_corrida, fuente, cod_departamento, producto, fecha_pred)
);
