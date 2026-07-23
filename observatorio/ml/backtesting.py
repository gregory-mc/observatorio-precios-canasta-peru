"""Backtesting walk-forward de los pronósticos — Milestone M4 (ml-4).

Valida la premisa del modelado: **que Prophet le gane a los baselines**
(naive / media móvil). Sin esa prueba, usar Prophet en vez del baseline no se
justifica (ver ``baseline.py``).

El backtest es *walk-forward* (ventana expansiva): para varios **cortes**
temporales se entrena con la historia hasta el corte y se pronostica hacia
adelante, comparando contra las observaciones reales posteriores. Las métricas
—**MAPE** y **RMSE**— se acumulan sobre todos los puntos de test de todos los
folds.

``evaluar_serie`` es **agnóstico del modelo**: recibe una función de pronóstico
(``Serie → DataFrame`` con ``ds``/``yhat``), así que evalúa Prophet y baseline
con la misma maquinaria y sobre los **mismos cortes** — por eso son comparables.
Todo el módulo es puro y testeable sin Prophet ni base de datos (Prophet se
importa lazy, igual que en ``prophet_modelo.py``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from . import config
from .baseline import pronostico_media_movil, pronostico_naive
from .datos import Serie

# Una función de pronóstico: recibe la serie de entrenamiento y el horizonte y
# devuelve un DataFrame con al menos las columnas ``ds`` (fecha) e ``yhat``.
PronosticarFn = Callable[[Serie, int], pd.DataFrame]


@dataclass(frozen=True)
class ResultadoBacktest:
    """Métricas de un modelo sobre una serie, acumuladas en el walk-forward."""

    fuente: str
    cod_departamento: str | None
    producto: str
    modelo: str
    n_folds: int  # cortes efectivamente evaluados (con puntos de test)
    n_puntos: int  # observaciones reales comparadas en total
    mape: float  # error porcentual absoluto medio (%)
    rmse: float  # raíz del error cuadrático medio (unidades de precio)


def mape(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Error porcentual absoluto medio (%) — ``mean(|(y - ŷ) / y|) · 100``.

    Los precios de ``fct_precio_diario`` son siempre > 0, así que no hay división
    por cero. Lanza ``ValueError`` si no hay puntos.

    >>> round(mape([10.0, 20.0], [11.0, 18.0]), 2)
    10.0
    """
    yt = pd.Series(y_true, dtype="float64")
    yp = pd.Series(y_pred, dtype="float64")
    if yt.empty:
        raise ValueError("MAPE indefinido sobre 0 puntos.")
    return float((yt - yp).abs().div(yt.abs()).mean() * 100)


def rmse(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Raíz del error cuadrático medio, en unidades de precio.

    Lanza ``ValueError`` si no hay puntos.

    >>> round(rmse([10.0, 20.0], [12.0, 20.0]), 4)
    1.4142
    """
    yt = pd.Series(y_true, dtype="float64")
    yp = pd.Series(y_pred, dtype="float64")
    if yt.empty:
        raise ValueError("RMSE indefinido sobre 0 puntos.")
    return float(((yt - yp) ** 2).mean() ** 0.5)


def _truncar(serie: Serie, hasta: pd.Timestamp) -> Serie:
    """Serie recortada a las observaciones con ``ds <= hasta`` (misma identidad)."""
    obs = serie.obs.loc[serie.obs["ds"] <= hasta].reset_index(drop=True)
    return Serie(serie.fuente, serie.cod_departamento, serie.producto, obs)


def generar_cortes(
    serie: Serie,
    horizonte: int = config.HORIZONTE_DIAS,
    n_folds: int = config.N_FOLDS_BACKTEST,
    paso: int = config.PASO_BACKTEST_DIAS,
    min_obs: int = config.MIN_OBSERVACIONES,
    min_span: int = config.MIN_SPAN_DIAS,
) -> list[pd.Timestamp]:
    """Cortes de entrenamiento para el walk-forward, del más antiguo al más reciente.

    El corte más reciente deja ``horizonte`` días de calendario por delante (para
    tener observaciones reales que comparar); los anteriores retroceden ``paso``
    días. Un corte solo se conserva si el tramo de entrenamiento (``ds <= corte``)
    tiene historia suficiente para un modelo temporal (mismos umbrales que
    ``Serie.es_modelable``) **y** existe al menos una observación real en la
    ventana ``(corte, corte + horizonte]`` para evaluar.

    Devolver los mismos cortes para todos los modelos es lo que hace comparables
    sus métricas.
    """
    if serie.n_obs == 0:
        return []

    fin = serie.obs["ds"].iloc[-1]
    cortes: list[pd.Timestamp] = []
    for k in range(n_folds):
        corte = fin - pd.Timedelta(days=horizonte + k * paso)
        train = _truncar(serie, corte)
        if train.n_obs < min_obs or train.span_dias < min_span:
            continue
        ventana = serie.obs["ds"].between(
            corte + pd.Timedelta(days=1), corte + pd.Timedelta(days=horizonte)
        )
        if not ventana.any():
            continue
        cortes.append(corte)

    return sorted(cortes)


def evaluar_serie(
    serie: Serie,
    pronosticar_fn: PronosticarFn,
    cortes: Sequence[pd.Timestamp],
    modelo: str,
    horizonte: int = config.HORIZONTE_DIAS,
) -> ResultadoBacktest | None:
    """Corre el walk-forward de un modelo sobre una serie y acumula las métricas.

    Para cada corte entrena con la historia hasta ese punto, pronostica y cruza el
    pronóstico con las observaciones reales por fecha (``ds``). Acumula los pares
    (real, pronóstico) de todos los cortes y calcula MAPE/RMSE sobre el total.

    Devuelve ``None`` si no hubo ningún punto comparable (p. ej. sin cortes
    válidos), para que el orquestador la omita sin abortar.
    """
    reales: list[float] = []
    pronosticados: list[float] = []
    folds_con_puntos = 0

    for corte in cortes:
        train = _truncar(serie, corte)
        pred = pronosticar_fn(train, horizonte)[["ds", "yhat"]].copy()
        pred["ds"] = pd.to_datetime(pred["ds"])

        test = serie.obs.loc[serie.obs["ds"] > corte, ["ds", "y"]]
        cruce = test.merge(pred, on="ds", how="inner")
        if cruce.empty:
            continue

        folds_con_puntos += 1
        reales.extend(cruce["y"].astype(float).tolist())
        pronosticados.extend(cruce["yhat"].astype(float).tolist())

    if not reales:
        return None

    return ResultadoBacktest(
        fuente=serie.fuente,
        cod_departamento=serie.cod_departamento,
        producto=serie.producto,
        modelo=modelo,
        n_folds=folds_con_puntos,
        n_puntos=len(reales),
        mape=mape(reales, pronosticados),
        rmse=rmse(reales, pronosticados),
    )


# Modelos que compara el backtest. Se expone el nombre (no las funciones) porque
# el runner necesita saber qué esperaba obtener para detectar un modelo caído
# (ver cobertura.py); un test verifica que no se desalinee de _modelos_por_defecto.
NOMBRES_MODELOS: tuple[str, ...] = ("prophet", "media_movil", "naive")


def _modelos_por_defecto() -> dict[str, PronosticarFn]:
    """Modelos a comparar: Prophet vs los dos baselines.

    Prophet se envuelve para importarse lazy (no está instalado en todos los
    entornos): así ``comparar_serie`` con los baselines corre sin él.
    """

    def prophet_fn(serie: Serie, horizonte: int) -> pd.DataFrame:
        from .prophet_modelo import pronosticar_prophet

        return pronosticar_prophet(serie, horizonte)

    return {
        "prophet": prophet_fn,
        "media_movil": pronostico_media_movil,
        "naive": pronostico_naive,
    }


def comparar_serie(
    serie: Serie,
    horizonte: int = config.HORIZONTE_DIAS,
    modelos: dict[str, PronosticarFn] | None = None,
    n_folds: int = config.N_FOLDS_BACKTEST,
    paso: int = config.PASO_BACKTEST_DIAS,
) -> list[ResultadoBacktest]:
    """Evalúa varios modelos sobre una serie con los **mismos cortes** y devuelve
    una fila de métricas por modelo.

    Por defecto compara Prophet contra media móvil y naive. Si la serie no tiene
    historia para generar cortes válidos devuelve lista vacía. Los modelos que no
    logren ningún punto comparable (p. ej. Prophet que no converge) se omiten.
    """
    modelos = modelos if modelos is not None else _modelos_por_defecto()
    cortes = generar_cortes(serie, horizonte=horizonte, n_folds=n_folds, paso=paso)
    if not cortes:
        return []

    resultados: list[ResultadoBacktest] = []
    for nombre, fn in modelos.items():
        try:
            res = evaluar_serie(serie, fn, cortes, nombre, horizonte)
        except Exception:  # noqa: BLE001 — un modelo caído no tumba la comparación
            res = None
        if res is not None:
            resultados.append(res)
    return resultados
