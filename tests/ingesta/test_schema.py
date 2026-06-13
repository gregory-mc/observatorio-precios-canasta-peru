"""Validación del esquema de las dataclasses de ingesta (issue #10).

Congela el conjunto de campos de ProductoPrecio y PrecioSisap: si alguien
agrega/quita/renombra una columna sin querer, estos tests fallan. El esquema
debe mantenerse en sintonía con las tablas bronze (ver bronze_schema.sql).
"""

from dataclasses import fields

from observatorio.ingesta.inei.models import IpcInei
from observatorio.ingesta.marketplace.models import ProductoPrecio
from observatorio.ingesta.sisap.models import PrecioSisap

PRODUCTOPRECIO_CAMPOS = {
    "fecha_captura",
    "fuente",
    "product_id",
    "sku_id",
    "nombre",
    "marca",
    "categoria",
    "categoria_raiz",
    "ean",
    "unidad_medida",
    "multiplicador_unidad",
    "precio",
    "precio_lista",
    "disponible",
    "cantidad_disponible",
    "vendedor",
    "url",
    "consulta",
}

PRECIOSISAP_CAMPOS = {
    "fecha_captura",
    "fuente",
    "region",
    "tipo_mercado",
    "producto",
    "unidad_medida",
    "equiv_kg_lt",
    "precio_prom",
}

IPCINEI_CAMPOS = {
    "fuente",
    "ambito",
    "base",
    "periodo",
    "anio",
    "mes",
    "indice",
    "var_mensual",
    "var_acumulada",
    "var_anual",
}


def test_esquema_productoprecio():
    assert {f.name for f in fields(ProductoPrecio)} == PRODUCTOPRECIO_CAMPOS


def test_esquema_preciosisap():
    assert {f.name for f in fields(PrecioSisap)} == PRECIOSISAP_CAMPOS


def test_esquema_ipcinei():
    assert {f.name for f in fields(IpcInei)} == IPCINEI_CAMPOS


def test_tipos_productoprecio_runtime():
    fila = ProductoPrecio(
        fecha_captura="2026-05-15",
        fuente="marketplace",
        product_id="1",
        sku_id="9",
        nombre="x",
        marca=None,
        categoria=None,
        categoria_raiz=None,
        ean=None,
        unidad_medida="un",
        multiplicador_unidad=1.0,
        precio=None,
        precio_lista=None,
        disponible=False,
        cantidad_disponible=0,
        vendedor=None,
        url=None,
        consulta="x",
    )
    assert isinstance(fila.disponible, bool)
    assert isinstance(fila.cantidad_disponible, int)
    assert isinstance(fila.multiplicador_unidad, float)


def test_tipos_preciosisap_runtime():
    fila = PrecioSisap(
        fecha_captura="2026-05-15",
        fuente="sisap_midagri",
        region="Lima",
        tipo_mercado="minorista",
        producto="Papa",
        unidad_medida="Kilogramo",
        equiv_kg_lt=1.0,
        precio_prom=3.0,
    )
    assert fila.equiv_kg_lt == 1.0
    assert fila.precio_prom == 3.0
