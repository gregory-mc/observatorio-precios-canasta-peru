{#
  Reduce el nombre crudo de producto de SISAP al slug de la canasta.

  Es el espejo SQL de `MAPEO_PRECIO_MVP` en
  `observatorio/validacion/canasta_vs_ipc.py`. **Las dos definiciones tienen que
  decir lo mismo**: la de Python alimenta la serie observada del dashboard y esta
  alimenta `fct_predicciones` y `fct_anomalias`. Si divergen, la página de
  evolución superpone una serie contra una banda calculada sobre otro conjunto de
  productos (ver docs/dashboard.md §8).

  Ampliado a 13 productos en #155. El orden importa: 'papa seca%' va antes que
  'papa %', que si no la capturaría. Las legumbres FRESCAS ('Arveja verde …',
  'Frijol verde canario') no necesitan exclusión: menestras usa una lista exacta
  de nombres secos, así que no las alcanza.
#}
{% macro slug_producto_mvp(columna) %}
case
    -- Exclusiones primero: procesados y frescos que no son el producto seco.
    when lower({{ columna }}) like 'papa seca%'                                then null

    -- Los 6 originales.
    when lower({{ columna }}) = 'papa'    or lower({{ columna }}) like 'papa %'    then 'papa'
    when lower({{ columna }}) = 'cebolla' or lower({{ columna }}) like 'cebolla %' then 'cebolla'
    when lower({{ columna }}) = 'tomate'  or lower({{ columna }}) like 'tomate %'  then 'tomate'
    when lower({{ columna }}) like 'huevo%'                                        then 'huevo'
    when lower({{ columna }}) like 'limon%' or lower({{ columna }}) like 'limón%'  then 'limon'
    when lower({{ columna }}) like '%pollo%'                                       then 'pollo'

    -- Ampliación (#155).
    when lower({{ columna }}) like 'arroz %'                                   then 'arroz'
    when lower({{ columna }}) like 'carne de vacuno%'
      or lower({{ columna }}) like 'carne de porcino%'
      or lower({{ columna }}) like 'carne de cerdo%'                           then 'carne_res'
    when lower({{ columna }}) like 'pescado %'                                 then 'pescado'
    when lower({{ columna }}) like 'leche %'                                   then 'leche'
    when lower({{ columna }}) like 'azucar %'
      or lower({{ columna }}) like 'azúcar %'                                  then 'azucar'
    when lower({{ columna }}) like 'aceite %'                                  then 'aceite'
    when lower({{ columna }}) in ('lenteja', 'frijol canario', 'frijol castilla',
                                  'garbanzo', 'pallar')                        then 'menestras'
    else null
end
{% endmacro %}
