"""Convierte la respuesta de Open-Meteo en filas ``MedicionClima`` (issue #14).

Cada elemento de la respuesta corresponde (por orden) a una ``Localidad`` pedida.
Su bloque ``daily`` trae arreglos paralelos: ``time`` (fechas) y las variables.
Se toma la fila de la ``fecha`` objetivo por localidad.
"""

from __future__ import annotations

from .config import Localidad
from .models import MedicionClima


def _valor(bloque: dict, clave: str, i: int) -> float | None:
    arr = bloque.get(clave) or []
    if i >= len(arr):
        return None
    v = arr[i]
    return None if v is None else float(v)


def parsear(
    respuesta: list[dict],
    localidades: list[Localidad],
    fecha: str,
) -> list[MedicionClima]:
    """Extrae una fila por localidad para la ``fecha`` dada.

    Alinea la respuesta con ``localidades`` por índice (Open-Meteo preserva el
    orden). Descarta localidades sin la fecha o sin ninguna medición ese día.
    """
    filas: list[MedicionClima] = []
    for loc, item in zip(localidades, respuesta, strict=False):
        diario = item.get("daily") or {}
        tiempos = diario.get("time") or []
        if fecha not in tiempos:
            continue
        i = tiempos.index(fecha)
        pp = _valor(diario, "precipitation_sum", i)
        tx = _valor(diario, "temperature_2m_max", i)
        tn = _valor(diario, "temperature_2m_min", i)
        if pp is None and tx is None and tn is None:
            continue
        filas.append(
            MedicionClima(
                fecha_captura=fecha,
                fuente="open-meteo",
                localidad=loc.nombre,
                region=loc.region,
                latitud=loc.lat,
                longitud=loc.lon,
                precip_mm=pp,
                temp_max_c=tx,
                temp_min_c=tn,
            )
        )
    return filas
