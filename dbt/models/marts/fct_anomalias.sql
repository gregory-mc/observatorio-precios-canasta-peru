-- Gold: anomalías de precio reducidas a los 6 productos MVP (slug), issue #28.
--
-- Lee ml.anomalias_raw (una fila por variedad cruda de SISAP × día anómalo ×
-- corrida) y la agrega al slug MVP. Si varias variedades de un slug son anómalas
-- el mismo día, colapsan en una fila: se reporta la desviación más fuerte
-- (z_abs_max) y los promedios de precio/esperado/residuo. Grano:
-- (fecha_corrida, fuente, cod_departamento, producto, fecha).

with base as (
    select
        fecha_corrida,
        fuente,
        cod_departamento,
        fecha,
        producto                            as producto_crudo,
        {{ slug_producto_mvp('producto') }} as producto,
        precio,
        esperado,
        residuo,
        z_score,
        metodo,
        umbral_sigma
    from {{ source('ml', 'anomalias_raw') }}
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
        fecha,
        count(distinct producto_crudo) as n_variedades_anomalas,
        max(abs(z_score))              as z_abs_max,
        avg(precio)                    as precio_prom,
        avg(esperado)                  as esperado_prom,
        avg(residuo)                   as residuo_prom,
        max(umbral_sigma)              as umbral_sigma,
        max(metodo)                    as metodo
    from mvp
    group by fecha_corrida, fuente, cod_departamento, producto, fecha
)

select * from final
