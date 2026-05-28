"""Esquema de una fila de precio capturada (una por SKU)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProductoPrecio:
    """Un precio observado de un SKU en una fecha.

    `unidad_medida`/`multiplicador_unidad` vienen tal cual de VTEX. Ojo: para
    productos empacados suele ser ``("un", 1.0)`` y el peso/volumen real queda
    en el nombre (ej. "... Bolsa 10Kg"). Derivar precio por kg/lt es trabajo de
    la capa silver (dbt), no de la ingesta: bronze guarda lo crudo.
    """

    fecha_captura: str  # YYYY-MM-DD en hora de Lima (UTC-5)
    fuente: str  # "marketplace"
    product_id: str
    sku_id: str
    nombre: str
    marca: str | None
    categoria: str | None  # ruta completa de categoría, ej. "Abarrotes/Arroz/Arroz Extra"
    categoria_raiz: str | None  # raíz de la categoría, ej. "Abarrotes" (filtro de relevancia)
    ean: str | None
    unidad_medida: str  # measurementUnit: "un", "kg", "lt", ...
    multiplicador_unidad: float
    precio: float | None  # commertialOffer.Price (precio de venta actual)
    precio_lista: float | None  # commertialOffer.ListPrice (antes de descuento)
    disponible: bool
    cantidad_disponible: int
    vendedor: str | None
    url: str | None
    consulta: str  # de qué target salió la fila (trazabilidad)
