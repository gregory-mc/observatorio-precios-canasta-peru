"""Planifica qué categorías de alimento navegar en Marketplace.

El scraper baja el catálogo de alimentos navegando categorías (no buscando por
texto, que es ruidoso y pesado). El legacy de VTEX corta la paginación en ~2500
SKUs (``MAX_OFFSET``), así que una categoría más grande (ej. Abarrotes, 3253) se
parte en subcategorías usando la **ruta de IDs** del árbol: ``fq=C:431/432``.

`planificar` es puro y testeable (recibe los nodos y una función de conteo);
`categorias_a_navegar` hace el IO (trae el árbol y cuenta contra la API).
"""

from __future__ import annotations

from collections.abc import Callable

import requests

from .client import MAX_OFFSET, contar
from .relevancia import CATEGORIAS_ALIMENTO

TREE_URL = "https://www.plazavea.com.pe/api/catalog_system/pub/category/tree/3"

# (filtro fq para la API, etiqueta legible de la ruta de categoría)
Objetivo = tuple[str, str]


def _descender(nodo: dict, ruta_ids: str, ruta_nombre: str, contar_fn: Callable[[str], int],
               salida: list[Objetivo]) -> None:
    fq = f"C:{ruta_ids}"
    hijos = nodo.get("children") or []
    if contar_fn(fq) <= MAX_OFFSET or not hijos:
        salida.append((fq, ruta_nombre))  # cabe (o no hay cómo bajar más): se navega entera
        return
    for hijo in hijos:
        _descender(
            hijo, f"{ruta_ids}/{hijo['id']}", f"{ruta_nombre}/{hijo['name']}", contar_fn, salida
        )


def planificar(nodos_alimento: list[dict], contar_fn: Callable[[str], int]) -> list[Objetivo]:
    """Devuelve [(fq, etiqueta)] tal que cada fq trae <= MAX_OFFSET SKUs."""
    salida: list[Objetivo] = []
    for nodo in nodos_alimento:
        _descender(nodo, str(nodo["id"]), nodo["name"], contar_fn, salida)
    return salida


def _traer_arbol(session: requests.Session) -> list[dict]:
    resp = session.get(TREE_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def categorias_a_navegar(session: requests.Session) -> list[Objetivo]:
    """Raíces de alimento del árbol de Marketplace, descendiendo donde haga falta."""
    arbol = _traer_arbol(session)
    nodos = [c for c in arbol if c["name"] in CATEGORIAS_ALIMENTO]
    return planificar(nodos, lambda fq: contar(session, fq))


__all__ = ["Objetivo", "categorias_a_navegar", "planificar"]
