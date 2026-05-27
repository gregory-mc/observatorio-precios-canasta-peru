"""Aplana la respuesta cruda de VTEX a filas ``ProductoPrecio`` (una por SKU)."""

from __future__ import annotations

from . import relevancia
from .models import ProductoPrecio


def _primera_categoria(categorias: list[str] | None) -> str | None:
    """``['/Abarrotes/Arroz/Arroz Extra/', ...]`` -> ``'Abarrotes/Arroz/Arroz Extra'``."""
    if not categorias:
        return None
    return categorias[0].strip("/") or None


def aplanar(producto: dict, *, fecha_captura: str, consulta: str) -> list[ProductoPrecio]:
    """Convierte un producto VTEX (con sus SKUs) en filas, una por SKU.

    Tolera SKUs sin vendedor/oferta: en ese caso precio queda en ``None`` y
    ``disponible`` en ``False`` (no revienta).
    """
    filas: list[ProductoPrecio] = []
    for item in producto.get("items", []):
        sellers = item.get("sellers") or []
        primer_seller = sellers[0] if sellers else {}
        oferta = primer_seller.get("commertialOffer") or {}
        nombre = item.get("nameComplete") or item.get("name") or producto.get("productName", "")
        # disponible: usamos IsAvailable y caemos a AvailableQuantity por robustez.
        cantidad = int(oferta.get("AvailableQuantity", 0) or 0)
        disponible = bool(oferta.get("IsAvailable")) or cantidad > 0
        categoria = _primera_categoria(producto.get("categories"))

        filas.append(
            ProductoPrecio(
                fecha_captura=fecha_captura,
                fuente="marketplace",
                product_id=str(producto.get("productId", "")),
                sku_id=str(item.get("itemId", "")),
                nombre=nombre,
                marca=producto.get("brand") or None,
                categoria=categoria,
                categoria_raiz=relevancia.categoria_raiz(categoria),
                ean=item.get("ean") or None,
                unidad_medida=item.get("measurementUnit", ""),
                multiplicador_unidad=float(item.get("unitMultiplier", 1) or 1),
                precio=oferta.get("Price"),
                precio_lista=oferta.get("ListPrice"),
                disponible=disponible,
                cantidad_disponible=cantidad,
                vendedor=primer_seller.get("sellerName") or None,
                url=producto.get("link") or None,
                consulta=consulta,
            )
        )
    return filas
