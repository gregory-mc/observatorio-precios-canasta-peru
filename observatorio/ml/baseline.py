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

Como el baseline no produce bandas de incertidumbre propias (a diferencia de
Prophet), ``agregar_bandas`` las estima de la volatilidad histórica de la serie.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import config
from .datos import Serie

# Factor que convierte la desviación absoluta mediana (MAD) en una estimación de
# σ para una normal. Se usa MAD en vez de la desviación típica porque las series
# de precio traen saltos atípicos que inflarían la banda de todos los días.
_MAD_A_SIGMA = 1.4826


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


def volatilidad_diaria(serie: Serie) -> float:
    """Estima cuánto se mueve el precio de la serie en un día, en soles.

    Las fuentes publican esparso, así que no se puede promediar el cambio entre
    filas consecutivas sin más: entre dos observaciones pueden haber pasado 1 día
    o 40. Cada cambio se normaliza dividiéndolo por la raíz del hueco en días,
    que es como escala el error de un paseo aleatorio — el comportamiento que el
    backtesting le encontró a estas series (por eso el naive gana; ver
    ``docs/ml.md``).

    Devuelve ``nan`` si la serie no tiene suficientes cambios para estimarla.

    >>> import pandas as pd
    >>> from observatorio.ml.datos import Serie
    >>> obs = pd.DataFrame({
    ...     "ds": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
    ...     "y": [2.0, 3.0, 2.0],
    ... })
    >>> round(volatilidad_diaria(Serie("f", "15", "PAPA", obs)), 3)  # saltos de ±1 sol/día
    1.483
    """
    if serie.n_obs < 3:
        return float("nan")

    cambios = serie.obs["y"].diff().iloc[1:]
    huecos = serie.obs["ds"].diff().dt.days.iloc[1:]
    validos = huecos > 0
    if int(validos.sum()) < 2:
        return float("nan")

    por_dia = cambios[validos] / np.sqrt(huecos[validos].astype(float))
    mad = float((por_dia - por_dia.median()).abs().median())
    sigma = _MAD_A_SIGMA * mad
    if sigma <= 0:  # serie plana o casi: la MAD colapsa a 0, se cae a la desviación típica
        sigma = float(por_dia.std(ddof=1))
    return sigma if math.isfinite(sigma) and sigma > 0 else float("nan")


def agregar_bandas(
    pred: pd.DataFrame,
    serie: Serie,
    nivel: float = config.NIVEL_BANDA,
) -> pd.DataFrame:
    """Añade ``yhat_lower``/``yhat_upper`` a un pronóstico de baseline.

    La banda se ensancha con la raíz del horizonte (``σ·√h``): pronosticar a 14
    días es más incierto que a 1, y un intervalo de ancho constante daría una
    falsa sensación de precisión en el dashboard (#38). El nivel por defecto es
    el mismo 80% que usa Prophet, para que apagarlo no cambie la lectura.

    Si la volatilidad no se puede estimar (serie demasiado corta o plana), las
    bandas quedan nulas: es el mismo contrato que tenía el baseline antes, y el
    mart las promedia como nulas en vez de inventar un intervalo.
    """
    sigma = volatilidad_diaria(serie)
    if not math.isfinite(sigma):
        return pred.assign(yhat_lower=pd.NA, yhat_upper=pd.NA)

    z = NormalDist().inv_cdf(0.5 + nivel / 2)
    dias_adelante = (pred["ds"] - serie.obs["ds"].iloc[-1]).dt.days.astype(float)
    margen = z * sigma * np.sqrt(dias_adelante)
    return pred.assign(
        # El precio no puede ser negativo, por muy ancha que salga la banda.
        yhat_lower=(pred["yhat"] - margen).clip(lower=0.0),
        yhat_upper=pred["yhat"] + margen,
    )
