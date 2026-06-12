"""Parseo end-to-end del marketplace contra una respuesta VTEX real (issue #10).

La fixture es una captura real congelada, así que las aserciones de valores
(precio, ean, etc.) son contra el snapshot, no contra la API en vivo.
"""

import json
from pathlib import Path

from observatorio.ingesta.marketplace.models import ProductoPrecio
from observatorio.ingesta.marketplace.parser import aplanar

FIXTURES = Path(__file__).parent.parent / "fixtures" / "marketplace"


def _cargar(nombre: str) -> list[dict]:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


def test_aplanar_fixture_real_vtex():
    productos = _cargar("vtex_producto_arroz.json")
    assert isinstance(productos, list) and productos

    filas: list[ProductoPrecio] = []
    for p in productos:
        filas.extend(aplanar(p, fecha_captura="2026-06-11", consulta="ids:101190089"))
    assert filas

    arroz = next(f for f in filas if f.sku_id == "11566644")
    assert arroz.product_id == "101190089"
    assert arroz.nombre.startswith("Arroz Extra")
    assert arroz.marca == "FARAON"
    assert arroz.categoria == "Abarrotes/Arroz/Arroz Extra"
    assert arroz.categoria_raiz == "Abarrotes"
    assert arroz.ean == "7758950000146"
    assert arroz.unidad_medida == "un"
    assert arroz.multiplicador_unidad == 1.0
    assert arroz.precio == 46.4
    assert arroz.precio_lista == 47.9
    assert arroz.disponible is True
    assert arroz.cantidad_disponible == 57
    assert arroz.vendedor == "Plaza Vea"
    assert arroz.fuente == "marketplace"
    assert arroz.consulta == "ids:101190089"


def test_todas_las_filas_son_productoprecio_validas():
    productos = _cargar("vtex_producto_arroz.json")
    for p in productos:
        for f in aplanar(p, fecha_captura="2026-06-11", consulta="x"):
            assert isinstance(f, ProductoPrecio)
            assert f.product_id and f.sku_id
            assert isinstance(f.disponible, bool)
            assert isinstance(f.cantidad_disponible, int)
            assert f.precio is None or isinstance(f.precio, (int, float))
            assert f.precio_lista is None or isinstance(f.precio_lista, (int, float))
