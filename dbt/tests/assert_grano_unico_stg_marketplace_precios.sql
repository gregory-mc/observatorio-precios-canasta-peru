-- #26 · Unicidad de grano: stg_marketplace_precios por (fecha_captura, sku_id).
select fecha_captura, sku_id
from {{ ref('stg_marketplace_precios') }}
group by fecha_captura, sku_id
having count(*) > 1
