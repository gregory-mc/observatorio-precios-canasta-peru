-- #26 · Unicidad de grano: fct_precio_diario debe tener una sola fila por
-- (fecha_captura, fuente, cod_departamento, producto). El test pasa si no
-- devuelve filas (dbt considera fallo cualquier fila retornada).
select fecha_captura, fuente, cod_departamento, producto
from {{ ref('fct_precio_diario') }}
group by fecha_captura, fuente, cod_departamento, producto
having count(*) > 1
