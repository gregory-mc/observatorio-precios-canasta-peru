-- Silver: clima diario por estación (SENAMHI), una fila por estación × día.
-- Dedup por grano (fecha_captura, cod_estacion). Conserva nulls a propósito: la
-- precipitación 0 es válida y muchas estaciones pluviométricas no miden
-- temperatura. La agregación por región/departamento y el cruce con precios se
-- hace en marts (gold), no acá.

with source as (
    select * from {{ source('bronze', 'clima_senamhi') }}
),

deduplicado as (
    select
        *,
        row_number() over (
            partition by fecha_captura, cod_estacion
            order by ingested_at desc
        ) as _rn
    from source
),

final as (
    select
        fecha_captura,
        fuente,
        cod_estacion,
        nullif(trim(nombre), '')    as nombre,
        nullif(trim(categoria), '') as categoria,
        nullif(trim(estado), '')    as estado,
        latitud,
        longitud,
        nullif(trim(region), '')    as region,
        precip_mm,
        temp_max_c,
        temp_min_c
    from deduplicado
    where _rn = 1
)

select * from final
