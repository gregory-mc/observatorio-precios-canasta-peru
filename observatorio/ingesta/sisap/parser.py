"""Convierte el HTML crudo del SISAP a filas PrecioSisap (una por producto)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from .models import PrecioSisap


def _float_o_none(texto: str) -> float | None:
    """Convierte texto a float. Devuelve None si está vacío o no es numérico."""
    texto = texto.strip()
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def parsear_html(
    html: str,
    *,
    fecha_captura: str,
    tipo_mercado: str,
    region: str = "Lima",
) -> list[PrecioSisap]:
    """Parsea el HTML del SISAP y devuelve una lista de PrecioSisap.

    Cada <tr class='contenido'> tiene 4 columnas:
      0 → nombre del producto
      1 → unidad de medida (puede estar vacía)
      2 → equivalencia kg/lt (puede estar vacía)
      3 → precio promedio (puede estar vacía = sin reporte ese día)

    Filas con menos de 4 columnas o producto vacío se descartan silenciosamente.
    """
    soup = BeautifulSoup(html, "html.parser")
    filas_html = soup.find_all("tr", class_="contenido")

    resultados: list[PrecioSisap] = []
    for fila in filas_html:
        cols = fila.find_all("td")
        if len(cols) < 4:
            continue
        producto = cols[0].text.strip()
        if not producto:
            continue

        resultados.append(
            PrecioSisap(
                fecha_captura=fecha_captura,
                fuente="sisap_midagri",
                region=region,
                tipo_mercado=tipo_mercado,
                producto=producto,
                unidad_medida=cols[1].text.strip() or None,
                equiv_kg_lt=_float_o_none(cols[2].text),
                precio_prom=_float_o_none(cols[3].text),
            )
        )

    return resultados
