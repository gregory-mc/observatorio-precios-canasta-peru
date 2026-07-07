-- Silver: precios SISAP (MIDAGRI) de Lima, uno por producto × tipo de mercado y
-- fecha. Dedup por grano y filtrado a filas con precio reportado. El cruce
-- minorista/mayorista y la normalización de unidades se hacen en marts (#24).

with source as (
    select * from {{ source('bronze', 'sisap_precios') }}
),

deduplicado as (
    select
        *,
        row_number() over (
            partition by fecha_captura, tipo_mercado, producto
            order by ingested_at desc
        ) as _rn
    from source
),

final as (
    select
        fecha_captura,
        fuente,
        nullif(trim(region), '')        as region,
        tipo_mercado,
        nullif(trim(producto), '')      as producto,
        nullif(trim(unidad_medida), '') as unidad_medida,
        equiv_kg_lt,
        precio_prom,
        ingested_at
    from deduplicado
    where _rn = 1
      and precio_prom is not null
      and precio_prom > 0
)

select * from final
