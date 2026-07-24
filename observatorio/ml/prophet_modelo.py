"""Pronóstico por serie: baseline por defecto, Prophet si se enciende.

`pronosticar_serie` es el punto de entrada del modelado: decide qué modelo usa
la serie (`modelo_de`) y normaliza la salida al contrato de
``ml.predicciones_raw`` (una fila por día del horizonte, con bandas de
incertidumbre e identificación del modelo usado).

Prophet está **apagado** por defecto (`config.USAR_PROPHET`): el backtesting
sobre las 157 series de producción lo dejó 2–3× peor que repetir el último
precio. El código sigue aquí porque el backtesting lo compara en cada corrida.

Prophet se importa de forma **lazy** dentro de `pronosticar_prophet` (igual que
psycopg en ``datos.py``): así el resto de la capa —dispatcher, fallback a
baseline, persistencia— es utilizable y testeable sin tener Prophet instalado.
"""

from __future__ import annotations

import logging

import pandas as pd

from . import config
from .baseline import agregar_bandas, pronostico_media_movil, pronostico_naive
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


_BASELINES = {
    "naive": pronostico_naive,
    "media_movil": pronostico_media_movil,
}


def modelo_de(serie: Serie) -> str:
    """Nombre del modelo que le toca a la serie.

    Única fuente de verdad de la decisión: la usan tanto ``pronosticar_serie``
    para pronosticar como ``run_entrenamiento`` para saber cuántas series espera
    de cada modelo (``cobertura``). Si las dos se calcularan por separado, apagar
    Prophet haría que el batch esperase series que ya nadie produce y abortaría
    la corrida.
    """
    if config.USAR_PROPHET and serie.es_modelable():
        return "prophet"
    return config.MODELO_SERVIDO


def pronosticar_serie(serie: Serie, horizonte: int = config.HORIZONTE_DIAS) -> pd.DataFrame:
    """Pronostica una serie eligiendo modelo según la config y su historia.

    - Con ``config.USAR_PROPHET`` y serie modelable (≥ umbral): **Prophet**.
    - En cualquier otro caso: el baseline de ``config.MODELO_SERVIDO``, con las
      bandas estimadas de la volatilidad de la propia serie.

    Hoy Prophet está apagado por defecto: perdió contra el naive en el
    backtesting sobre las 157 series de producción (ver ``config.USAR_PROPHET``).

    Devuelve un DataFrame con las columnas de `COLUMNAS_PRED`, una fila por día
    del horizonte. No incluye la identidad de la serie (fuente/depto/producto):
    eso lo adjunta el orquestador (``run_entrenamiento``).
    """
    modelo = modelo_de(serie)
    if modelo == "prophet":
        pred = pronosticar_prophet(serie, horizonte)
    else:
        pred = _BASELINES[modelo](serie, horizonte)
        pred = agregar_bandas(pred, serie)

    salida = pred.rename(columns={"ds": "fecha_pred"})
    salida["modelo"] = modelo
    salida["n_obs_entrenamiento"] = serie.n_obs
    return salida[list(COLUMNAS_PRED)]
