"""Cliente HTTP de Open-Meteo: baja el clima diario de todas las localidades.

Open-Meteo acepta coordenadas múltiples en una sola petición (lat/lon separadas
por coma) y responde una lista de objetos en el mismo orden — así que todo el
subset se trae en un request.
"""

from __future__ import annotations

import requests

from .config import (
    LOCALIDADES,
    PAST_DAYS,
    TIMEOUT,
    TIMEZONE,
    URL_FORECAST,
    VARIABLES_DIARIAS,
    Localidad,
)


def descargar(
    localidades: list[Localidad] | None = None,
    *,
    past_days: int = PAST_DAYS,
    session: requests.Session | None = None,
) -> list[dict]:
    """Baja el clima diario de las localidades. Devuelve una lista de dicts
    Open-Meteo (uno por localidad, en el mismo orden de entrada).
    """
    locs = localidades if localidades is not None else LOCALIDADES
    ses = session or requests.Session()
    params = {
        "latitude": ",".join(str(loc.lat) for loc in locs),
        "longitude": ",".join(str(loc.lon) for loc in locs),
        "daily": ",".join(VARIABLES_DIARIAS),
        "timezone": TIMEZONE,
        "past_days": past_days,
        "forecast_days": 1,
    }
    resp = ses.get(URL_FORECAST, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # Con múltiples coordenadas Open-Meteo devuelve una lista; con una sola, un
    # objeto. Normalizamos siempre a lista.
    return data if isinstance(data, list) else [data]
