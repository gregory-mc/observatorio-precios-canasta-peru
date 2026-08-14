"""Parsea la serie diaria de una estación SENAMHI a filas ``MedicionClima``.

La respuesta de ``map_red_graf.php`` es HTML con un gráfico Highcharts que trae
todo inline (issue #14; ver docs/sources.md §SENAMHI). El grano es diario:

    xAxis.categories: ['2026-07-15', ..., '2026-08-14']   <- fechas
    series: [
      { name: 'Precipitaci\\u00F3n', data: [0.0, ..., null] },  <- mm/día
      { name: 'Temp. max',           data: [29.8, ..., null] },  <- °C
      { name: 'Temp. min',           data: [15.4, ..., 12.8] },  <- °C
    ]

Las tres series comparten el índice de ``categories``. El parseo es por regex
(no se ejecuta JS): faltando una serie, esa variable queda en None. Se descartan
las filas sin ninguna medición (día sin dato en las tres variables).
"""

from __future__ import annotations

import re

from .models import Estacion, MedicionClima

_RE_CATEGORIES = re.compile(r"categories:\s*\[([^\]]*)\]", re.S)
# name: '...'  ... (props)  ... data: [ ... ]  — non-greedy hasta el primer data.
_RE_SERIE = re.compile(r"name:\s*'([^']*)'.*?data:\s*\[([^\]]*)\]", re.S)


def _fechas(html: str) -> list[str]:
    """Lista de fechas de ``categories`` (ignora vacíos por coma final)."""
    m = _RE_CATEGORIES.search(html)
    if not m:
        return []
    return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip().strip("'\"")]


def _valores(bruto: str) -> list[float | None]:
    """Parsea un ``data: [...]`` de Highcharts: número o ``null`` -> None.

    El token vacío que deja la coma final NO es un punto de dato y se ignora;
    los ``null`` internos sí cuentan (como None) para no desalinear el índice.
    """
    valores: list[float | None] = []
    for token in bruto.split(","):
        t = token.strip()
        if t == "":
            continue
        if t.lower() == "null":
            valores.append(None)
            continue
        try:
            valores.append(float(t))
        except ValueError:
            valores.append(None)
    return valores


def _series_por_variable(html: str) -> dict[str, list[float | None]]:
    """Mapea cada serie Highcharts a su variable canónica (precip/tmax/tmin)."""
    out: dict[str, list[float | None]] = {}
    for nombre, bruto in _RE_SERIE.findall(html):
        if "Precipitaci" in nombre:
            out["precip"] = _valores(bruto)
        elif nombre == "Temp. max":
            out["tmax"] = _valores(bruto)
        elif nombre == "Temp. min":
            out["tmin"] = _valores(bruto)
    return out


def parsear_serie(html: str, estacion: Estacion) -> list[MedicionClima]:
    """Convierte el HTML de la serie de una estación en filas ``MedicionClima``.

    Alinea ``categories`` con las tres series por índice. Devuelve una fila por
    fecha con al menos una medición; descarta días completamente vacíos.
    """
    fechas = _fechas(html)
    if not fechas:
        return []

    series = _series_por_variable(html)
    precip = series.get("precip", [])
    tmax = series.get("tmax", [])
    tmin = series.get("tmin", [])

    def en(arr: list[float | None], i: int) -> float | None:
        return arr[i] if i < len(arr) else None

    filas: list[MedicionClima] = []
    for i, fecha in enumerate(fechas):
        pp, tx, tn = en(precip, i), en(tmax, i), en(tmin, i)
        if pp is None and tx is None and tn is None:
            continue  # día sin ninguna medición: no aporta a bronze
        filas.append(
            MedicionClima(
                fecha_captura=fecha,
                fuente="senamhi",
                cod_estacion=estacion.cod,
                nombre=estacion.nombre,
                categoria=estacion.categoria,
                estado=estacion.estado,
                latitud=estacion.lat,
                longitud=estacion.lon,
                region=estacion.region or "",
                precip_mm=pp,
                temp_max_c=tx,
                temp_min_c=tn,
            )
        )
    return filas
