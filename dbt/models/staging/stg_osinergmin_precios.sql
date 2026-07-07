-- Silver: precios de combustible por establecimiento (OSINERGMIN/Facilito), uno
-- por grifo × producto y fecha. Dedup por grano y filtrado a filas con precio.
-- Se conserva el establecimiento individual y su ubicación cruda; la agregación
-- a precio por departamento/distrito y la normalización de nombres geográficos
-- (hoy en MAYÚSCULAS) se hacen en marts (#24).

with source as (
    select * from {{ source('bronze', 'osinergmin_precios') }}
),

deduplicado as (
    select
        *,
        row_number() over (
            partition by fecha_captura, codigo_osi, producto_codigo
            order by ingested_at desc
        ) as _rn
    from source
),

final as (
    select
        fecha_captura,
        fuente,
        nullif(trim(departamento), '')   as departamento,
        nullif(trim(provincia), '')      as provincia,
        nullif(trim(distrito), '')       as distrito,
        codigo_osi,
        nullif(trim(establecimiento), '') as establecimiento,
        nullif(trim(direccion), '')      as direccion,
        nullif(trim(telefono), '')       as telefono,
        nullif(trim(producto), '')       as producto,
        producto_codigo,
        precio_soles_galon
    from deduplicado
    where _rn = 1
      and precio_soles_galon is not null
      and precio_soles_galon > 0
)

select * from final
