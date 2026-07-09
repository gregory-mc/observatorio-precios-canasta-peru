"""Pronósticos de referencia (baseline) — Milestone M4.

Dos modelos triviales que sirven como **piso de comparación** para el backtesting
(ml-4): si Prophet no le gana al naive, no vale la pena. También son el fallback
para las series sin historia suficiente para Prophet (``Serie.es_modelable`` False).

  * **Naive**: el último precio observado se proyecta constante hacia adelante.
  * **Media móvil**: el promedio de los últimos ``ventana`` días de calendario se
    proyecta constante. Ventana de calendario (no de N filas) por coherencia con
    ``fct_precio_medias_moviles``: las fuentes publican esparso.

Ambos devuelven un DataFrame ``(ds, yhat)`` con una fila por día del horizonte,
mismo contrato de salida que tendrá el forecast de Prophet.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .datos import Serie


def _fechas_futuras(ultima: pd.Timestamp, horizonte: int) -> pd.DatetimeIndex:
    """``horizonte`` días diarios y consecutivos a partir del día siguiente a ``ultima``."""
    return pd.date_range(start=ultima + pd.Timedelta(days=1), periods=horizonte, freq="D")


def pronostico_naive(serie: Serie, horizonte: int = config.HORIZONTE_DIAS) -> pd.DataFrame:
    """Proyecta el último precio observado, constante, ``horizonte`` días.

    >>> import pandas as pd
    >>> from observatorio.ml.datos import Serie
    >>> obs = pd.DataFrame({"ds": pd.to_datetime(["2026-01-01", "2026-01-02"]), "y": [2.0, 3.0]})
    >>> pred = pronostico_naive(Serie("f", "15", "PAPA", obs), horizonte=2)
    >>> list(pred["yhat"])
    [3.0, 3.0]
    """
    if serie.n_obs == 0:
        raise ValueError("No se puede pronosticar una serie vacía.")
    ultimo = float(serie.obs["y"].iloc[-1])
    fechas = _fechas_futuras(serie.obs["ds"].iloc[-1], horizonte)
    return pd.DataFrame({"ds": fechas, "yhat": ultimo})


def pronostico_media_movil(
    serie: Serie,
    horizonte: int = config.HORIZONTE_DIAS,
    ventana: int = config.VENTANA_MEDIA_MOVIL_DIAS,
) -> pd.DataFrame:
    """Proyecta el promedio de los últimos ``ventana`` días de calendario, constante.

    La ventana se cuenta hacia atrás desde la última observación en días de
    calendario, así que incluye entre 1 y N puntos según cuán densa sea la serie.

    >>> import pandas as pd
    >>> from observatorio.ml.datos import Serie
    >>> obs = pd.DataFrame({
    ...     "ds": pd.to_datetime(["2026-01-01", "2026-01-05", "2026-01-08"]),
    ...     "y": [1.0, 2.0, 3.0],
    ... })
    >>> pred = pronostico_media_movil(Serie("f", "15", "PAPA", obs), horizonte=1, ventana=7)
    >>> float(round(pred["yhat"].iloc[0], 3))  # media de 2.0 y 3.0 (01-01 fuera de 7 días)
    2.5
    """
    if serie.n_obs == 0:
        raise ValueError("No se puede pronosticar una serie vacía.")
    ultima_fecha = serie.obs["ds"].iloc[-1]
    corte = ultima_fecha - pd.Timedelta(days=ventana - 1)
    en_ventana = serie.obs.loc[serie.obs["ds"] >= corte, "y"]
    promedio = float(en_ventana.mean())
    fechas = _fechas_futuras(ultima_fecha, horizonte)
    return pd.DataFrame({"ds": fechas, "yhat": promedio})
