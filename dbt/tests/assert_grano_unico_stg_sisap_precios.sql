-- #26 · Unicidad de grano: stg_sisap_precios por (fecha_captura, tipo_mercado,
-- producto) — el dedup de la capa silver debe garantizarlo.
select fecha_captura, tipo_mercado, producto
from {{ ref('stg_sisap_precios') }}
group by fecha_captura, tipo_mercado, producto
having count(*) > 1
