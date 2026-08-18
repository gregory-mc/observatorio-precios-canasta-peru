-- #14 · Unicidad de grano: stg_clima por (fecha_captura, localidad) —
-- una medición × localidad × día.
select fecha_captura, localidad
from {{ ref('stg_clima') }}
group by fecha_captura, localidad
having count(*) > 1
