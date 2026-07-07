-- Silver: serie mensual del IPC de Lima Metropolitana (INEI), una fila por mes.
-- No es un precio sino el índice de referencia usado para validar la canasta
-- vs. IPC (#20). Dedup por periodo y se agrega `fecha_mes` (primer día del mes)
-- para facilitar joins temporales con las series de precios diarios.

with source as (
    select * from {{ source('bronze', 'inei_ipc') }}
),

deduplicado as (
    select
        *,
        row_number() over (
            partition by periodo
            order by ingested_at desc
        ) as _rn
    from source
),

final as (
    select
        fuente,
        nullif(trim(ambito), '')   as ambito,
        nullif(trim(base), '')     as base,
        periodo,
        anio,
        mes,
        make_date(anio, mes, 1)    as fecha_mes,
        indice,
        var_mensual,
        var_acumulada,
        var_anual
    from deduplicado
    where _rn = 1
      and indice is not null
)

select * from final
