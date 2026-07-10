"""Detección de anomalías de precio — Milestone M4 (ml-5).

Marca los días cuyo precio se aparta demasiado de su nivel local reciente, según
el criterio del PLAN: **residuo normalizado > 2.5σ** (``config.UMBRAL_SIGMA``).

Método (control-chart sobre la desviación del nivel local, sin depender de
Prophet):

  1. **Nivel esperado** de cada día = media móvil de los ``ventana`` días de
     calendario *previos* (excluye el propio día, para que un pico no infle su
     propia expectativa). Un día sin historia previa en la ventana no es
     evaluable y se descarta.
  2. **Residuo** = precio − esperado.
  3. **Residuo normalizado** (z-score) = ``(residuo − media) / desvío`` sobre
     todos los residuos de la serie.
  4. Es **anomalía** el día con ``|z| > umbral``.

Todo es puro y testeable (sin DB ni Prophet). La escritura a ``ml.anomalias_raw``
la hace ``persistencia.escribir_anomalias``; el mart ``gold.fct_anomalias`` lo
construye dbt en un PR posterior.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .datos import Serie

# Nº mínimo de residuos definidos para que el desvío sea estimable con sentido.
# Debajo de esto no se evalúan anomalías (evita z-scores sobre 2-3 puntos).
MIN_RESIDUOS: int = 10

# Etiqueta del método, persistida en ml.anomalias_raw.
METODO: str = "residuo_vs_media_movil"

# Columnas de salida de detectar_anomalias_serie (contrato hacia persistencia).
COLUMNAS_ANOMALIA = ("fecha", "precio", "esperado", "residuo", "z_score")


def puntuar_serie(
    serie: Serie,
    ventana: int = config.VENTANA_MEDIA_MOVIL_DIAS,
    min_residuos: int = MIN_RESIDUOS,
) -> pd.DataFrame:
    """Calcula esperado, residuo y z-score de cada día evaluable de la serie.

    Devuelve un DataFrame con columnas ``ds, y, esperado, residuo, z_score``, una
    fila por observación con nivel esperado definido (las que tienen al menos un
    día previo dentro de la ventana). Devuelve un DataFrame vacío si la serie no
    llega a ``min_residuos`` residuos o si el desvío de los residuos es 0 (serie
    plana: nada que normalizar).
    """
    if serie.n_obs == 0:
        return pd.DataFrame(columns=["ds", "y", "esperado", "residuo", "z_score"])

    obs = serie.obs.sort_values("ds").reset_index(drop=True)
    fechas = obs["ds"]
    valores = obs["y"].astype(float)

    esperados: list[float] = []
    for i in range(len(obs)):
        dia = fechas.iloc[i]
        inf = dia - pd.Timedelta(days=ventana)
        previos = valores[(fechas >= inf) & (fechas < dia)]
        esperados.append(float(previos.mean()) if not previos.empty else float("nan"))

    marco = pd.DataFrame({"ds": fechas, "y": valores, "esperado": esperados})
    marco = marco.loc[marco["esperado"].notna()].reset_index(drop=True)
    if len(marco) < min_residuos:
        return _vacio()

    marco["residuo"] = marco["y"] - marco["esperado"]
    desvio = marco["residuo"].std(ddof=1)
    if not (desvio > 0):  # 0, NaN o negativo imposible → serie plana, sin anomalías
        return _vacio()

    marco["z_score"] = (marco["residuo"] - marco["residuo"].mean()) / desvio
    return marco


def _vacio() -> pd.DataFrame:
    return pd.DataFrame(columns=["ds", "y", "esperado", "residuo", "z_score"])


def detectar_anomalias_serie(
    serie: Serie,
    ventana: int = config.VENTANA_MEDIA_MOVIL_DIAS,
    umbral: float = config.UMBRAL_SIGMA,
    min_residuos: int = MIN_RESIDUOS,
) -> pd.DataFrame:
    """Días anómalos de la serie: ``|z-score| > umbral``.

    Devuelve un DataFrame con las columnas de ``COLUMNAS_ANOMALIA`` (``fecha,
    precio, esperado, residuo, z_score``), una fila por día anómalo. Vacío si la
    serie no es evaluable o no hay ningún día por encima del umbral. No incluye la
    identidad de la serie (fuente/depto/producto): la adjunta el orquestador.
    """
    puntuada = puntuar_serie(serie, ventana=ventana, min_residuos=min_residuos)
    if puntuada.empty:
        return pd.DataFrame(columns=list(COLUMNAS_ANOMALIA))

    anomalas = puntuada.loc[puntuada["z_score"].abs() > umbral].copy()
    anomalas = anomalas.rename(columns={"ds": "fecha", "y": "precio"})
    return anomalas[list(COLUMNAS_ANOMALIA)].reset_index(drop=True)
