-- Silver: clima diario por localidad (Open-Meteo), una fila por localidad × día.
-- Dedup por grano (fecha_captura, localidad). Conserva nulls a propósito: la
-- precipitación 0 es válida. La agregación por región y el cruce con precios se
-- hace en marts (gold), no acá.

with source as (
    select * from {{ source('bronze', 'clima') }}
),

deduplicado as (
    select
        *,
        row_number() over (
            partition by fecha_captura, localidad
            order by ingested_at desc
        ) as _rn
    from source
),

final as (
    select
        fecha_captura,
        fuente,
        nullif(trim(localidad), '') as localidad,
        nullif(trim(region), '')    as region,
        latitud,
        longitud,
        precip_mm,
        temp_max_c,
        temp_min_c
    from deduplicado
    where _rn = 1
)

select * from final
