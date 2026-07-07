-- Silver: precios del marketplace, uno por SKU y fecha.
-- Limpieza ligera sobre bronze: dedup por grano, trim de texto y filtrado a
-- observaciones con precio válido. La derivación de precio por kg/lt y los
-- cruces son trabajo de marts (#24).

with source as (
    select * from {{ source('bronze', 'marketplace_precios') }}
),

deduplicado as (
    -- bronze es idempotente por fecha, pero un mismo SKU puede repetirse dentro
    -- del snapshot; nos quedamos con la captura más reciente por grano.
    select
        *,
        row_number() over (
            partition by fecha_captura, sku_id
            order by ingested_at desc
        ) as _rn
    from source
),

final as (
    select
        fecha_captura,
        fuente,
        product_id,
        sku_id,
        nullif(trim(nombre), '')               as nombre,
        nullif(trim(marca), '')                as marca,
        nullif(trim(categoria), '')            as categoria,
        nullif(trim(categoria_raiz), '')       as categoria_raiz,
        nullif(trim(ean), '')                  as ean,
        lower(nullif(trim(unidad_medida), '')) as unidad_medida,
        multiplicador_unidad,
        precio,
        precio_lista,
        disponible,
        cantidad_disponible,
        nullif(trim(vendedor), '')             as vendedor,
        url,
        ingested_at
    from deduplicado
    where _rn = 1
      and precio is not null
      and precio > 0
)

select * from final
