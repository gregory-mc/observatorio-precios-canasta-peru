"""Tests del backtesting walk-forward (observatorio.ml.backtesting), sin Prophet."""

import pandas as pd
import pytest

from observatorio.ml import backtesting as bt
from observatorio.ml.datos import Serie


def _serie(n: int = 200, freq: str = "D", producto: str = "PAPA") -> Serie:
    """Serie diaria larga (supera holgado el umbral de historia)."""
    obs = pd.DataFrame(
        {"ds": pd.date_range("2026-01-01", periods=n, freq=freq), "y": range(1, n + 1)}
    )
    obs["y"] = obs["y"].astype(float)
    return Serie("sisap_minorista", "15", producto, obs)


def test_mape_y_rmse_valores_conocidos():
    assert round(bt.mape([10.0, 20.0], [11.0, 18.0]), 4) == 10.0  # (0.1 + 0.1)/2 * 100
    assert round(bt.rmse([10.0, 20.0], [12.0, 20.0]), 4) == round(2**0.5, 4)


def test_metricas_sobre_cero_puntos_es_error():
    with pytest.raises(ValueError):
        bt.mape([], [])
    with pytest.raises(ValueError):
        bt.rmse([], [])


def test_generar_cortes_respeta_historia_minima_y_deja_horizonte_por_delante():
    serie = _serie(n=200)
    cortes = bt.generar_cortes(serie, horizonte=14, n_folds=5, paso=7)
    assert len(cortes) == 5
    assert cortes == sorted(cortes)  # ascendente
    # el corte más reciente deja al menos un día de test dentro del horizonte
    fin = serie.obs["ds"].iloc[-1]
    assert cortes[-1] <= fin - pd.Timedelta(days=1)


def test_generar_cortes_serie_corta_no_produce_cortes():
    corta = _serie(n=10)  # < MIN_OBSERVACIONES
    assert bt.generar_cortes(corta, horizonte=14) == []


def test_evaluar_serie_pronostico_perfecto_da_error_cero():
    """Un modelo que 've' el futuro (yhat = y real) debe dar MAPE y RMSE = 0."""
    serie = _serie(n=200)
    reales = serie.obs.set_index("ds")["y"]

    def oraculo(train: Serie, horizonte: int) -> pd.DataFrame:
        ultima = train.obs["ds"].iloc[-1]
        fechas = pd.date_range(ultima + pd.Timedelta(days=1), periods=horizonte, freq="D")
        return pd.DataFrame({"ds": fechas, "yhat": reales.reindex(fechas).values})

    cortes = bt.generar_cortes(serie, horizonte=14, n_folds=3, paso=7)
    res = bt.evaluar_serie(serie, oraculo, cortes, "oraculo", horizonte=14)
    assert res is not None
    assert res.n_puntos > 0
    assert round(res.mape, 9) == 0.0
    assert round(res.rmse, 9) == 0.0


def test_evaluar_serie_sin_cortes_devuelve_none():
    serie = _serie(n=200)
    assert bt.evaluar_serie(serie, lambda s, h: pd.DataFrame(), [], "x", 14) is None


def test_comparar_serie_usa_mismos_cortes_para_todos_los_modelos():
    """Modelos evaluados sobre los mismos cortes ⇒ mismo n_puntos (comparables)."""
    serie = _serie(n=200)

    def constante(valor: float):
        def fn(train: Serie, horizonte: int) -> pd.DataFrame:
            ultima = train.obs["ds"].iloc[-1]
            fechas = pd.date_range(ultima + pd.Timedelta(days=1), periods=horizonte, freq="D")
            return pd.DataFrame({"ds": fechas, "yhat": valor})

        return fn

    modelos = {"bajo": constante(1.0), "alto": constante(1000.0)}
    resultados = bt.comparar_serie(serie, horizonte=14, modelos=modelos, n_folds=3, paso=7)

    assert {r.modelo for r in resultados} == {"bajo", "alto"}
    assert len({r.n_puntos for r in resultados}) == 1  # mismos puntos evaluados
    # el modelo con pronóstico más cercano a la realidad tiene menor MAPE
    por_modelo = {r.modelo: r.mape for r in resultados}
    assert por_modelo["bajo"] < por_modelo["alto"]


def test_comparar_serie_corta_devuelve_lista_vacia():
    assert bt.comparar_serie(_serie(n=10)) == []
