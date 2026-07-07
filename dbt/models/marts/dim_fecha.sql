-- Gold: dimensión de calendario que cubre el rango de fechas presente en
-- fct_precio_diario (spine continuo, sin huecos aunque un día no tenga precios).
-- Se deriva del hecho para no cablear fechas fijas.

with bounds as (
    select
        min(fecha_captura) as fecha_min,
        max(fecha_captura) as fecha_max
    from {{ ref('fct_precio_diario') }}
),

spine as (
    select generate_series(fecha_min, fecha_max, interval '1 day')::date as fecha
    from bounds
),

final as (
    select
        fecha,
        extract(year  from fecha)::int    as anio,
        extract(month from fecha)::int    as mes,
        extract(day   from fecha)::int    as dia,
        extract(quarter from fecha)::int  as trimestre,
        extract(isodow from fecha)::int   as dia_semana,        -- 1=lunes … 7=domingo
        extract(isodow from fecha)::int >= 6 as es_fin_semana,
        date_trunc('month', fecha)::date  as primer_dia_mes
    from spine
)

select * from final
