"""Filtro de relevancia: decide si un SKU pertenece a la canasta de alimentos
según su **categoría raíz** de VTEX.

La búsqueda por token trae mucho ruido (un "ft=limon" devuelve lejía, silicona
de autos, etc.). Aquí nos quedamos solo con SKUs cuya raíz de categoría es de
alimentos. Las raíces salen del árbol real de Marketplace:
    /api/catalog_system/pub/category/tree/1

El raw (bronze) conserva todo; este filtro se aplica solo al CSV aplanado.
"""

from __future__ import annotations

import unicodedata

# Raíces de categoría consideradas "alimento de canasta".
CATEGORIAS_ALIMENTO: frozenset[str] = frozenset(
    {
        "Abarrotes",
        "Frutas y Verduras",
        "Carnes, Aves y Pescados",
        "Lácteos y Huevos",
        "Quesos y Fiambres",
        "Panadería y Pastelería",
        "Congelados",
        "Desayunos",
        "Mercado Saludable",
    }
)


def _norm(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar robusto."""
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return base.casefold().strip()


_ALIMENTO_NORM = frozenset(_norm(c) for c in CATEGORIAS_ALIMENTO)


def categoria_raiz(categoria: str | None) -> str | None:
    """Primer segmento de la ruta, ej. "Abarrotes/Arroz/..." -> "Abarrotes"."""
    if not categoria:
        return None
    return categoria.split("/")[0].strip() or None


def es_alimento(categoria: str | None) -> bool:
    """True si la categoría raíz está en la lista de alimentos de canasta."""
    raiz = categoria_raiz(categoria)
    return raiz is not None and _norm(raiz) in _ALIMENTO_NORM
