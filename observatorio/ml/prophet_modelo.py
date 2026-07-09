"""Pronóstico por serie: Prophet para historia holgada, baseline para el resto.

`pronosticar_serie` es el punto de entrada del modelado: decide, según el umbral
de historia (`Serie.es_modelable`), si entrena Prophet o cae al baseline, y
normaliza la salida al contrato de ``ml.predicciones_raw`` (una fila por día del
horizonte, con bandas de incertidumbre e identificación del modelo usado).

Prophet se importa de forma **lazy** dentro de `pronosticar_prophet` (igual que
psycopg en ``datos.py``): así el resto de la capa —dispatcher, fallback a
baseline, persistencia— es utilizable y testeable sin tener Prophet instalado.
"""

from __future__ import annotations

import logging

import pandas as pd

from . import config
from .baseline import pronostico_media_movil
from .datos import Serie

log = logging.getLogger("ml.prophet")

# Columnas de salida de pronosticar_serie (contrato hacia persistencia).
COLUMNAS_PRED = (
    "fecha_pred",
    "yhat",
    "yhat_lower",
    "yhat_upper",
    "modelo",
    "n_obs_entrenamiento",
)


def pronosticar_prophet(serie: Serie, horizonte: int = config.HORIZONTE_DIAS) -> pd.DataFrame:
    """Entrena Prophet con la serie y devuelve el pronóstico de los próximos días.

    Estacionalidad semanal activada; anual y diaria desactivadas (no hay años de
    historia propia y el grano ya es diario). Devuelve solo las filas futuras
    (``ds`` posterior a la última observación), con columnas ``ds, yhat,
    yhat_lower, yhat_upper``.
    """
    from prophet import Prophet

    # Prophet/cmdstanpy son muy ruidosos en stdout; los bajamos a WARNING.
    logging.getLogger("prophet").setLevel(logging.WARNING)
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

    modelo = Prophet(
        weekly_seasonality=True,
        yearly_seasonality=False,
        daily_seasonality=False,
    )
    modelo.fit(serie.obs)
    futuro = modelo.make_future_dataframe(periods=horizonte)
    forecast = modelo.predict(futuro)

    ultima = serie.obs["ds"].iloc[-1]
    fut = forecast.loc[
        forecast["ds"] > ultima, ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ]
    return fut.reset_index(drop=True)


def pronosticar_serie(serie: Serie, horizonte: int = config.HORIZONTE_DIAS) -> pd.DataFrame:
    """Pronostica una serie eligiendo modelo según su historia.

    - Serie modelable (≥ umbral de `config`): **Prophet**, con bandas.
    - Serie corta: **media móvil** como fallback; sin bandas (``yhat_lower/upper``
      nulos), ya que el baseline no las produce.

    Devuelve un DataFrame con las columnas de `COLUMNAS_PRED`, una fila por día
    del horizonte. No incluye la identidad de la serie (fuente/depto/producto):
    eso lo adjunta el orquestador (``run_entrenamiento``).
    """
    if serie.es_modelable():
        pred = pronosticar_prophet(serie, horizonte)
        modelo = "prophet"
    else:
        pred = pronostico_media_movil(serie, horizonte)
        pred = pred.assign(yhat_lower=pd.NA, yhat_upper=pd.NA)
        modelo = "media_movil"

    salida = pred.rename(columns={"ds": "fecha_pred"})
    salida["modelo"] = modelo
    salida["n_obs_entrenamiento"] = serie.n_obs
    return salida[list(COLUMNAS_PRED)]
