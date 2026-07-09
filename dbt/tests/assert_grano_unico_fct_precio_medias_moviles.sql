-- #26 · Unicidad de grano: fct_precio_medias_moviles (mismo grano que el hecho
-- de origen, una fila por día observado × serie).
select fecha_captura, fuente, cod_departamento, producto
from {{ ref('fct_precio_medias_moviles') }}
group by fecha_captura, fuente, cod_departamento, producto
having count(*) > 1
