"""Esquema de una fila de precio de combustible capturada de Facilito (OSINERGMIN).

Una fila = un establecimiento (grifo/estación) × un producto × una fecha. Es el
nivel crudo (bronze): la agregación a precio por departamento/distrito es trabajo
de la capa silver (dbt). Por eso se conserva el grifo individual, su ubicación y
el ``codigo_osi`` (identificador OSINERGMIN del establecimiento, estable en el
tiempo y útil para deduplicar y cruzar entre días).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PrecioCombustible:
    """Precio reportado por un establecimiento para un producto, en una fecha.

    ``telefono`` y ``precio_soles_galon`` pueden ser None: Facilito a veces lista
    el grifo sin teléfono, y un establecimiento puede aparecer sin precio vigente
    para ese producto (celda vacía). El precio del GLP/GNV no entra acá: este
    modelo cubre el buscador de combustible automotor líquido (gasoholes + diésel).
    """

    fecha_captura: str  # YYYY-MM-DD en hora de Lima (UTC-5)
    fuente: str  # "osinergmin_facilito"
    departamento: str  # nombre del departamento (p.ej. "TUMBES")
    provincia: str  # nombre de la provincia (p.ej. "TUMBES")
    distrito: str  # nombre del distrito tal cual viene del HTML
    codigo_osi: str | None  # código OSINERGMIN del establecimiento (de irMapa)
    establecimiento: str  # razón social / nombre del grifo
    direccion: str | None  # dirección reportada (puede venir vacía)
    telefono: str | None  # teléfono(s) reportado(s) (puede venir vacío)
    producto: str  # "Gasohol Regular" | "Gasohol Premium" | "DB5 S-50 UV"
    producto_codigo: str  # código del producto en Facilito ("126" | "127" | "40")
    precio_soles_galon: float | None  # precio en soles por galón (None = sin reporte)
