-- Gold: hecho de precio diario unificado y conformado desde las fuentes de
-- precios de alimentos (silver). Grain: (fecha_captura, fuente, cod_departamento,
-- producto). Faithful — conserva los productos tal como vienen; la reducción a
-- los 6 slugs del MVP y el cruce con gold.canasta_consumo_dept (costo canasta)
-- se harán en un mart posterior.
--
-- Fuentes: SISAP (minorista/mayorista, solo Lima) y Marketplace (retail online,
-- ámbito nacional). OSINERGMIN queda fuera: es combustible (soles/galón), no
-- alimento — irá a su propio hecho si se necesita.

with sisap as (
    select
        fecha_captura,
        'sisap_' || tipo_mercado as fuente,
        '15'::char(2)            as cod_departamento,  -- SISAP se scrapea solo para Lima (dep. 15)
        producto,
        -- Normalización de unidad a S/ por kg (o litro). SISAP mayorista cotiza
        -- muchos productos por cajón/bolsa/millar, no por kg: el tomate viene en
        -- "Cajón chico" de 27 kg (S/63/cajón), el limón en bolsa de 45 kg. Sin
        -- dividir por equiv_kg_lt —el factor de conversión que la propia fuente
        -- publica— el hecho mezclaba unidades: tomate mayorista a S/63 convivía con
        -- el minorista a S/4.6/kg. Toda fila con precio trae equiv_kg_lt (verificado:
        -- 0 nulos entre las priceadas); el coalesce es defensivo. MVP minorista tiene
        -- equiv=1.0, así que su precio no cambia. Ver docs/validacion_canasta_vs_ipc.md.
        precio_prom / coalesce(nullif(equiv_kg_lt, 0), 1.0) as precio
    from {{ ref('stg_sisap_precios') }}
),

marketplace as (
    select
        fecha_captura,
        'marketplace'  as fuente,
        null::char(2)  as cod_departamento,  -- retail online: ámbito nacional, sin departamento
        nombre         as producto,
        precio
    from {{ ref('stg_marketplace_precios') }}
),

unificado as (
    select * from sisap
    union all
    select * from marketplace
),

final as (
    select
        fecha_captura,
        fuente,
        cod_departamento,
        producto,
        avg(precio) as precio_prom,
        min(precio) as precio_min,
        max(precio) as precio_max,
        count(*)    as n_obs
    from unificado
    group by fecha_captura, fuente, cod_departamento, producto
)

select * from final
