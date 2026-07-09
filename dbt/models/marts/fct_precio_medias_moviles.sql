-- Gold: medias móviles de precio a 7 / 30 / 90 días por (fuente,
-- cod_departamento, producto) — issue #25. Deriva de fct_precio_diario.
--
-- La ventana es de CALENDARIO (últimos N días), no de N observaciones: las
-- fuentes publican de forma esparsa (SISAP es interdiario; el backfill histórico
-- va muestreado), así que promediar "las últimas N filas" mezclaría spans
-- temporales muy distintos. Se incluye el conteo de observaciones dentro de cada
-- ventana (n_obs_*) para interpretar la confiabilidad cuando la ventana es rala.
--
-- Grain: (fecha_captura, fuente, cod_departamento, producto), igual que el hecho
-- de origen (una fila por día observado, sin rellenar días sin dato).

with base as (
    select
        fecha_captura,
        fuente,
        cod_departamento,
        producto,
        precio_prom
    from {{ ref('fct_precio_diario') }}
),

moviles as (
    select
        fecha_captura,
        fuente,
        cod_departamento,
        producto,
        precio_prom,
        avg(precio_prom) over w7  as precio_ma_7d,
        avg(precio_prom) over w30 as precio_ma_30d,
        avg(precio_prom) over w90 as precio_ma_90d,
        count(*) over w7  as n_obs_7d,
        count(*) over w30 as n_obs_30d,
        count(*) over w90 as n_obs_90d
    from base
    window
        w7 as (
            partition by fuente, cod_departamento, producto
            order by fecha_captura
            range between interval '6 days' preceding and current row
        ),
        w30 as (
            partition by fuente, cod_departamento, producto
            order by fecha_captura
            range between interval '29 days' preceding and current row
        ),
        w90 as (
            partition by fuente, cod_departamento, producto
            order by fecha_captura
            range between interval '89 days' preceding and current row
        )
)

select * from moviles
