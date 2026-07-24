{% test no_negativo(model, column_name) %}
-- Test genérico: la columna no debe tener valores negativos.
--
-- Un precio (o su banda) por debajo de 0 no existe en el mundo real. Nace de
-- #27: Prophet, al ser aditivo y sin cota inferior, extrapolaba precios negativos
-- (hasta -3.84 soles en gold.fct_predicciones el 22-jul). Se apagó y se sirve el
-- baseline —que recorta la banda en 0—, pero este test blinda contra una futura
-- reactivación. Los NULL no cuentan (las bandas del baseline pueden ser nulas).
select {{ column_name }}
from {{ model }}
where {{ column_name }} < 0
{% endtest %}
