-- #26 · Unicidad de grano: stg_osinergmin_precios por (fecha_captura,
-- codigo_osi, producto_codigo) — un grifo × combustible × día.
select fecha_captura, codigo_osi, producto_codigo
from {{ ref('stg_osinergmin_precios') }}
group by fecha_captura, codigo_osi, producto_codigo
having count(*) > 1
