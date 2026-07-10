{#
  Reduce el nombre crudo de producto (tal como viene de SISAP en las tablas del
  schema `ml`) a uno de los 6 slugs del MVP, o NULL si no es un producto MVP.

  Los slugs y su criterio (ver observatorio/canasta/productos.py):
    papa, cebolla, tomate, huevo, limon, pollo

  Cuidados:
    * "Papa seca" es un procesado: se descarta explícitamente ANTES de papa.
    * "Papaya" empieza con "papa" pero NO es papa → por eso papa/cebolla/tomate
      se anclan con `= slug` o `like 'slug %'` (palabra completa), no con prefijo.
    * SISAP escribe "Limon" sin tilde y "Huevos" en plural; se cubren ambos.
    * pollo aparece como "Carne de pollo (eviscerado)" → se busca por substring.
#}
{% macro slug_producto_mvp(columna) %}
case
    when lower({{ columna }}) like 'papa seca%' then null
    when lower({{ columna }}) = 'papa'    or lower({{ columna }}) like 'papa %'    then 'papa'
    when lower({{ columna }}) = 'cebolla' or lower({{ columna }}) like 'cebolla %' then 'cebolla'
    when lower({{ columna }}) = 'tomate'  or lower({{ columna }}) like 'tomate %'  then 'tomate'
    when lower({{ columna }}) like 'huevo%'                                        then 'huevo'
    when lower({{ columna }}) like 'limon%' or lower({{ columna }}) like 'limón%'  then 'limon'
    when lower({{ columna }}) like '%pollo%'                                       then 'pollo'
    else null
end
{% endmacro %}
