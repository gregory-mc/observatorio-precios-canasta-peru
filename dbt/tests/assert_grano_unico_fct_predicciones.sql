-- #27 · Unicidad de grano: fct_predicciones debe tener una sola fila por
-- (fecha_corrida, fuente, cod_departamento, producto, fecha_pred). El test pasa
-- si no devuelve filas (dbt considera fallo cualquier fila retornada).
select fecha_corrida, fuente, cod_departamento, producto, fecha_pred
from {{ ref('fct_predicciones') }}
group by fecha_corrida, fuente, cod_departamento, producto, fecha_pred
having count(*) > 1
