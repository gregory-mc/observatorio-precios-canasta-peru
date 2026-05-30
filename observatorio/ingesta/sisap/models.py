"""Esquema de una fila de precio capturada del SISAP (una por producto)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PrecioSisap:
    """Un precio observado de un producto en el SISAP para una fecha y tipo de mercado.

    `equiv_kg_lt` y `precio_prom` pueden ser None cuando el MIDAGRI no reporta
    ese producto ese día (celda vacía en el HTML). La normalización y el cruce
    entre minorista/mayorista es trabajo de la capa silver (dbt).
    """

    fecha_captura: str        # YYYY-MM-DD en hora de Lima (UTC-5)
    fuente: str               # "sisap_midagri"
    region: str               # "Lima"
    tipo_mercado: str         # "minorista" | "mayorista"
    producto: str             # nombre tal cual viene del HTML
    unidad_medida: str | None # "Kilogramo", "Litro", "Lata", etc. (puede ser vacío)
    equiv_kg_lt: float | None # equivalencia en kg/lt (puede ser vacío)
    precio_prom: float | None # precio promedio en soles (None = sin reporte ese día)
