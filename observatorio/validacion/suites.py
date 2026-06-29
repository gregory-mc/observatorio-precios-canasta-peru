"""Suites de expectativas por fuente — issue #18.

Una suite por tabla bronze. La filosofía medallion manda: **bronze guarda lo crudo
tal cual** (ver docs/carga_supabase.md y bronze_schema.sql), así que estas suites
son conservadoras — chequean lo que delata un parser roto o una carga corrupta,
no la normalización fina (eso es trabajo de silver/dbt en S6):

  * estructura: columnas esperadas presentes, al menos una fila;
  * clave natural sin duplicados (la misma con la que el cargador hace idempotencia);
  * sanidad de magnitudes: precios/cantidades no negativos (error) y no absurdos (aviso);
  * dominios cerrados conocidos: ``tipo_mercado``, mes 1–12.

El registro ``SUITES`` se llavea con los mismos nombres de fuente que
``observatorio.carga.r2_a_supabase.FUENTES``, para engancharlas 1:1 en la carga.
"""

from __future__ import annotations

from .runner import (
    ClaveUnica,
    ColumnasPresentes,
    EnConjunto,
    EnRango,
    MinFilas,
    NoNulo,
    Suite,
)

# Cota superior de sanidad para precios en soles. No es un límite de negocio: solo
# atrapa errores de unidad/parseo (un precio de S/ 1e6 es casi seguro basura). Por
# eso es ``advertencia``, no ``error``: no bloquea la carga, la marca para revisión.
PRECIO_ABSURDO = 100_000.0


SUITE_MARKETPLACE = Suite(
    nombre="marketplace",
    expectativas=[
        ColumnasPresentes(["fecha_captura", "sku_id", "precio"]),
        MinFilas(1),
        NoNulo("fecha_captura"),
        NoNulo("sku_id"),
        # Clave natural del retail: un SKU por día (ver bronze_schema.sql).
        ClaveUnica(["fecha_captura", "sku_id"]),
        EnRango("precio", minimo=0),
        EnRango("precio", maximo=PRECIO_ABSURDO, severidad="advertencia"),
        EnRango("precio_lista", minimo=0),
    ],
)


SUITE_SISAP = Suite(
    nombre="sisap",
    expectativas=[
        ColumnasPresentes(
            ["fecha_captura", "region", "tipo_mercado", "producto", "precio_prom"]
        ),
        MinFilas(1),
        NoNulo("fecha_captura"),
        NoNulo("producto"),
        NoNulo("tipo_mercado"),
        # Grain documentado: una fila por producto/día/región/tipo_mercado.
        ClaveUnica(["fecha_captura", "region", "tipo_mercado", "producto"]),
        EnConjunto("tipo_mercado", {"minorista", "mayorista"}),
        EnRango("precio_prom", minimo=0),
        EnRango("precio_prom", maximo=PRECIO_ABSURDO, severidad="advertencia"),
        EnRango("equiv_kg_lt", minimo=0),
    ],
)


SUITE_INEI = Suite(
    nombre="inei",
    expectativas=[
        ColumnasPresentes(["base", "periodo", "anio", "mes", "indice"]),
        MinFilas(1),
        NoNulo("periodo"),
        NoNulo("base"),
        # Clave natural de la serie IPC (ver bronze_schema.sql): (base, periodo).
        ClaveUnica(["base", "periodo"]),
        # Serie continua desde 1994; cota alta holgada para no bloquear años futuros.
        EnRango("anio", minimo=1994, maximo=2100),
        EnRango("mes", minimo=1, maximo=12),
        # El IPC es un índice positivo; las variaciones (var_*) sí pueden ser negativas.
        EnRango("indice", minimo=0),
    ],
)


SUITE_OSINERGMIN = Suite(
    nombre="osinergmin",
    expectativas=[
        ColumnasPresentes(
            ["fecha_captura", "codigo_osi", "producto_codigo", "precio_soles_galon"]
        ),
        MinFilas(1),
        NoNulo("fecha_captura"),
        NoNulo("establecimiento"),
        NoNulo("producto"),
        # Un precio por establecimiento × producto × día. Facilito a veces lista
        # grifos sin codigo_osi (irMapa('null') → None → "" en el CSV), así que
        # NO basta con (fecha, codigo_osi, producto): varios grifos sin código
        # colapsarían a la misma clave. El establecimiento se identifica por su
        # codigo_osi cuando existe y, si no, por nombre + dirección.
        ClaveUnica(
            ["fecha_captura", "codigo_osi", "establecimiento", "direccion", "producto_codigo"]
        ),
        EnRango("precio_soles_galon", minimo=0),
        EnRango("precio_soles_galon", maximo=PRECIO_ABSURDO, severidad="advertencia"),
    ],
)


# Registro central, llaveado igual que FUENTES en la carga a bronze.
SUITES: dict[str, Suite] = {
    "marketplace": SUITE_MARKETPLACE,
    "sisap": SUITE_SISAP,
    "inei": SUITE_INEI,
    "osinergmin": SUITE_OSINERGMIN,
}
