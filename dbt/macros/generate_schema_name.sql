{#
    Override del comportamiento por defecto de dbt, que prefija el schema del
    target (p.ej. `silver_staging`). Para la arquitectura medallion queremos que
    `+schema: silver` / `+schema: gold` aterricen en esos schemas tal cual.

    - Si el modelo no declara schema custom → usa el schema del target.
    - Si lo declara (silver/gold) → lo usa literal, sin prefijo.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema | trim }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
