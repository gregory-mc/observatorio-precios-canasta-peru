-- #28 · Unicidad de grano: fct_anomalias debe tener una sola fila por
-- (fecha_corrida, fuente, cod_departamento, producto, fecha). El test pasa si no
-- devuelve filas (dbt considera fallo cualquier fila retornada).
select fecha_corrida, fuente, cod_departamento, producto, fecha
from {{ ref('fct_anomalias') }}
group by fecha_corrida, fuente, cod_departamento, producto, fecha
having count(*) > 1
