-- #14 · Unicidad de grano: stg_clima por (fecha_captura, cod_estacion) —
-- una medición × estación × día.
select fecha_captura, cod_estacion
from {{ ref('stg_clima') }}
group by fecha_captura, cod_estacion
having count(*) > 1
