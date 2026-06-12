"""Parseo del SISAP contra HTML real congelado + casos borde (issue #10).

Cierra el hueco de cobertura de SISAP: el parser no tenía tests reales.
"""

from pathlib import Path

from observatorio.ingesta.sisap.models import PrecioSisap
from observatorio.ingesta.sisap.parser import parsear_html

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sisap"


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def test_parsea_fixture_real_minorista():
    html = _leer("sisap_lima_minorista_2026-05-15.html")
    filas = parsear_html(html, fecha_captura="2026-05-15", tipo_mercado="minorista")

    assert len(filas) == 93
    assert all(isinstance(f, PrecioSisap) for f in filas)
    assert all(f.fuente == "sisap_midagri" and f.region == "Lima" for f in filas)
    assert all(
        f.tipo_mercado == "minorista" and f.fecha_captura == "2026-05-15" for f in filas
    )

    por_nombre = {f.producto: f for f in filas}

    # Fila con datos completos.
    arroz = por_nombre["Arroz extra"]
    assert arroz.unidad_medida == "Kilogramo"
    assert arroz.equiv_kg_lt == 1.0
    assert arroz.precio_prom == 4.64

    # Fila con celdas vacías → None (producto sin reporte ese día).
    sin_dato = por_nombre["Arroz corriente"]
    assert sin_dato.unidad_medida is None
    assert sin_dato.equiv_kg_lt is None
    assert sin_dato.precio_prom is None

    # Caracteres especiales preservados (UTF-8), no se ignoran las cabeceras.
    assert "Piña criolla" in por_nombre
    assert "Carne de porcino (corte único)" in por_nombre


def test_fixture_sin_datos_devuelve_vacio():
    html = _leer("sisap_sin_datos.html")
    filas = parsear_html(html, fecha_captura="2026-06-11", tipo_mercado="minorista")
    assert filas == []


def test_descarta_filas_invalidas():
    # Casos que el HTML real no incluía: fila con <4 columnas y producto vacío.
    html = """
    <table>
      <tr class='contenido'><td>Solo dos</td><td>columnas</td></tr>
      <tr class='contenido'><td></td><td>Kilogramo</td><td>1.00</td><td>5.00</td></tr>
      <tr class='contenido'><td>Papa válida</td><td>Kilogramo</td><td>1.00</td><td>3.00</td></tr>
    </table>
    """
    filas = parsear_html(html, fecha_captura="2026-05-15", tipo_mercado="mayorista")
    assert len(filas) == 1
    assert filas[0].producto == "Papa válida"
    assert filas[0].tipo_mercado == "mayorista"
    assert filas[0].precio_prom == 3.0


def test_precio_no_numerico_es_none():
    html = (
        "<table><tr class='contenido'>"
        "<td>Raro</td><td>Kilogramo</td><td>n/a</td><td>--</td>"
        "</tr></table>"
    )
    filas = parsear_html(html, fecha_captura="2026-05-15", tipo_mercado="minorista")
    assert len(filas) == 1
    assert filas[0].equiv_kg_lt is None
    assert filas[0].precio_prom is None
