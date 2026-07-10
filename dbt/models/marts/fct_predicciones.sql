-- Gold: pronóstico de precio reducido a los 6 productos MVP (slug), issue #27.
--
-- Lee la salida cruda del modelado (ml.predicciones_raw, una fila por variedad
-- cruda de SISAP × día pronosticado × corrida) y la agrega al slug MVP. Varias
-- variedades ("Papa blanca", "Papa amarilla"…) colapsan en un slug ("papa"): el
-- precio pronosticado es el promedio de sus variedades, y la banda, el promedio
-- de las bandas. Las variedades que no son MVP se descartan (slug null).
--
-- Grain: (fecha_corrida, fuente, cod_departamento, producto, fecha_pred). Se
-- conservan TODAS las corridas; el consumidor (dashboard) filtra la más reciente.

with base as (
    select
        fecha_corrida,
        fuente,
        cod_departamento,
        fecha_pred,
        producto                            as producto_crudo,
        {{ slug_producto_mvp('producto') }} as producto,
        yhat,
        yhat_lower,
        yhat_upper,
        modelo
    from {{ source('ml', 'predicciones_raw') }}
),

mvp as (
    select * from base where producto is not null
),

final as (
    select
        fecha_corrida,
        fuente,
        cod_departamento,
        producto,
        fecha_pred,
        avg(yhat)                          as precio_pred,
        avg(yhat_lower)                    as precio_pred_inf,
        avg(yhat_upper)                    as precio_pred_sup,
        -- modelo del grano: único si todas las variedades usaron el mismo, si no 'mixto'.
        case when count(distinct modelo) = 1 then max(modelo) else 'mixto' end as modelo,
        count(distinct producto_crudo)     as n_variedades
    from mvp
    group by fecha_corrida, fuente, cod_departamento, producto, fecha_pred
)

select * from final
