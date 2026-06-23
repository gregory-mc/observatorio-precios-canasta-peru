"""Parseo de Facilito (OSINERGMIN) contra HTML real congelado + casos borde (issue #15).

El fixture ``eess_tumbes_gasohol_regular_2026-06-23.html`` es la tabla
``#tblPreciosAutomotor`` tal cual la devolvió Facilito para Tumbes / provincia
TUMBES / Gasohol Regular (14 grifos). Se eligió un departamento chico a propósito
para que el fixture sea legible.
"""

from pathlib import Path

from observatorio.ingesta.osinergmin.models import PrecioCombustible
from observatorio.ingesta.osinergmin.parser import parsear_html

FIXTURES = Path(__file__).parent.parent / "fixtures" / "osinergmin"


def _leer(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def _parsear_tumbes() -> list[PrecioCombustible]:
    html = _leer("eess_tumbes_gasohol_regular_2026-06-23.html")
    return parsear_html(
        html,
        fecha_captura="2026-06-23",
        departamento="TUMBES",
        provincia="TUMBES",
        producto="Gasohol Regular",
        producto_codigo="126",
    )


def test_parsea_fixture_real_tumbes():
    filas = _parsear_tumbes()

    assert len(filas) == 14
    assert all(isinstance(f, PrecioCombustible) for f in filas)
    assert all(f.fuente == "osinergmin_facilito" for f in filas)
    assert all(f.departamento == "TUMBES" and f.provincia == "TUMBES" for f in filas)
    assert all(f.producto == "Gasohol Regular" and f.producto_codigo == "126" for f in filas)
    assert all(f.fecha_captura == "2026-06-23" for f in filas)


def test_campos_de_la_primera_fila():
    primera = _parsear_tumbes()[0]

    assert primera.distrito == "TUMBES"
    assert primera.establecimiento == "ESTACION DE SERVICIOS EL GIRASOL EIRL"
    assert primera.direccion == "PANAMERICANA NORTE NRO. 1267 PJ PUEBLO NUEVO"
    assert primera.telefono == "972919225/998497688"
    assert primera.precio_soles_galon == 19.00
    # codigo_osi extraído del onclick irMapa('40067',0)
    assert primera.codigo_osi == "40067"


def test_distritos_y_precios_variados():
    por_codigo = {f.codigo_osi: f for f in _parsear_tumbes()}

    # Un grifo en distrito distinto (Corrales), con código y precio propios.
    corrales = por_codigo["16814"]
    assert corrales.distrito == "CORRALES"
    assert corrales.precio_soles_galon == 19.00

    # Todos los precios son floats positivos en este fixture (todos reportaron).
    assert all(f.precio_soles_galon and f.precio_soles_galon > 0 for f in por_codigo.values())


def test_sin_registros_devuelve_vacio():
    html = _leer("eess_sin_registros.html")
    filas = parsear_html(
        html,
        fecha_captura="2026-06-23",
        departamento="MADRE DE DIOS",
        provincia="TAMBOPATA",
        producto="Gasohol Premium",
        producto_codigo="127",
    )
    assert filas == []


def test_tabla_ausente_devuelve_vacio():
    filas = parsear_html(
        "<html><body><p>error</p></body></html>",
        fecha_captura="2026-06-23",
        departamento="LIMA",
        provincia="LIMA",
        producto="Gasohol Regular",
        producto_codigo="126",
    )
    assert filas == []


def test_celdas_vacias_y_precio_no_numerico():
    # Fila sin teléfono ni dirección, con precio no numérico, y otra válida.
    html = """
    <table id="tblPreciosAutomotor"><tbody>
      <tr class="enlace" onclick="javascript:irMapa('null',0);">
        <th scope="row">LIMA</th>
        <td>GRIFO SIN DATOS</td>
        <td></td>
        <td>   </td>
        <td><strong><div align="center">n/d</div></strong></td>
      </tr>
      <tr onclick="javascript:irMapa('999',0);">
        <th scope="row">MIRAFLORES</th>
        <td>GRIFO OK</td>
        <td>AV. SIEMPRE VIVA 123</td>
        <td>014445566</td>
        <td><strong><div align="center">16.30</div></strong></td>
      </tr>
    </tbody></table>
    """
    filas = parsear_html(
        html,
        fecha_captura="2026-06-23",
        departamento="LIMA",
        provincia="LIMA",
        producto="DB5 S-50 UV",
        producto_codigo="40",
    )
    assert len(filas) == 2

    sin_datos = filas[0]
    assert sin_datos.codigo_osi is None  # 'null' → None
    assert sin_datos.direccion is None
    assert sin_datos.telefono is None
    assert sin_datos.precio_soles_galon is None  # 'n/d' → None

    ok = filas[1]
    assert ok.codigo_osi == "999"
    assert ok.precio_soles_galon == 16.30


def test_descarta_fila_sin_establecimiento():
    html = """
    <table id="tblPreciosAutomotor"><tbody>
      <tr onclick="irMapa('1',0)"><th>LIMA</th><td></td><td>dir</td><td>tel</td>
        <td><div>10.00</div></td></tr>
      <tr onclick="irMapa('2',0)"><th>LIMA</th><td>VALIDO</td><td>dir</td><td>tel</td>
        <td><div>11.00</div></td></tr>
    </tbody></table>
    """
    filas = parsear_html(
        html,
        fecha_captura="2026-06-23",
        departamento="LIMA",
        provincia="LIMA",
        producto="Gasohol Regular",
        producto_codigo="126",
    )
    assert len(filas) == 1
    assert filas[0].establecimiento == "VALIDO"
