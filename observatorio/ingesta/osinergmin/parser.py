"""Convierte el HTML de resultados de Facilito a filas PrecioCombustible.

El HTML lo entrega ``client.py`` (respuesta cruda del POST a la Action, con la
tabla ``#tblPreciosAutomotor`` ya renderizada del lado servidor — todas las
filas, antes de que DataTables las pagine en el navegador).

Estructura de cada ``<tr>`` de datos (verificada en junio 2026):
    <tr class="enlace" onclick="javascript:irMapa('148481',0);">
      <th scope="row">LURIGANCHO</th>              <- distrito
      <td>ESTACION ... E.I.R.L</td>                 <- establecimiento
      <td>AV. LAS TORRES LOTE 13 A, ...</td>        <- dirección (puede ir vacía)
      <td>954904070/970964070</td>                  <- teléfono (puede ir vacío)
      <td><strong><div align="center">15.80</div></strong></td>  <- precio (puede ir vacío)
    </tr>

El producto, departamento y provincia no están en la fila: son el contexto de la
consulta y se pasan como argumentos (igual que ``tipo_mercado`` en SISAP).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .models import PrecioCombustible

# Primer argumento de irMapa('<codigoOSI>', <allResults>): el código OSINERGMIN
# del establecimiento. Cuando Facilito no lo tiene, viene literalmente 'null'.
_RE_CODIGO_OSI = re.compile(r"irMapa\(\s*'([^']*)'")


def _texto_o_none(valor: str) -> str | None:
    """Normaliza texto: colapsa espacios y devuelve None si queda vacío."""
    valor = " ".join(valor.split())
    return valor or None


def _precio_o_none(texto: str) -> float | None:
    """Convierte el texto del precio a float. None si está vacío o no es numérico."""
    texto = texto.strip().replace(",", "")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _codigo_osi(onclick: str | None) -> str | None:
    """Extrae el código OSINERGMIN del atributo onclick (irMapa)."""
    if not onclick:
        return None
    m = _RE_CODIGO_OSI.search(onclick)
    if not m:
        return None
    codigo = m.group(1).strip()
    return codigo or None if codigo.lower() != "null" else None


def parsear_html(
    html: str,
    *,
    fecha_captura: str,
    departamento: str,
    provincia: str,
    producto: str,
    producto_codigo: str,
) -> list[PrecioCombustible]:
    """Parsea el HTML de resultados y devuelve una lista de PrecioCombustible.

    Devuelve ``[]`` cuando la tabla no existe o trae la fila "No existen
    registros." (combinación departamento/provincia/producto sin grifos).
    Filas con menos de 5 celdas o sin establecimiento se descartan.
    """
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", id="tblPreciosAutomotor")
    if tabla is None:
        return []
    cuerpo = tabla.find("tbody")
    if cuerpo is None:
        return []

    resultados: list[PrecioCombustible] = []
    for fila in cuerpo.find_all("tr"):
        # Fila vacía de DataTables ("No existen registros.").
        if fila.find("td", class_="dataTables_empty"):
            continue

        celdas = fila.find_all(["th", "td"])
        if len(celdas) < 5:
            continue

        distrito = _texto_o_none(celdas[0].get_text())
        establecimiento = _texto_o_none(celdas[1].get_text())
        if not establecimiento:
            continue

        resultados.append(
            PrecioCombustible(
                fecha_captura=fecha_captura,
                fuente="osinergmin_facilito",
                departamento=departamento,
                provincia=provincia,
                distrito=distrito or "",
                codigo_osi=_codigo_osi(fila.get("onclick")),
                establecimiento=establecimiento,
                direccion=_texto_o_none(celdas[2].get_text()),
                telefono=_texto_o_none(celdas[3].get_text()),
                producto=producto,
                producto_codigo=producto_codigo,
                precio_soles_galon=_precio_o_none(celdas[4].get_text()),
            )
        )

    return resultados
