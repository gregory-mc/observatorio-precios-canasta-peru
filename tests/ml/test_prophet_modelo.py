"""Tests del dispatcher de pronóstico (observatorio.ml.prophet_modelo).

Prophet no se ejecuta acá: se monkeypatchea `pronosticar_prophet` para no
depender de tenerlo instalado. Lo que se prueba es la lógica de decisión
(modelable → Prophet; corta → baseline) y la forma de la salida.
"""

import pandas as pd

from observatorio.ml import config, prophet_modelo
from observatorio.ml.datos import Serie
from observatorio.ml.prophet_modelo import COLUMNAS_PRED, pronosticar_serie


def _serie(n: int) -> Serie:
    obs = pd.DataFrame(
        {"ds": pd.date_range("2026-01-01", periods=n, freq="D"), "y": [2.0] * n}
    )
    return Serie("sisap_minorista", "15", "PAPA", obs)


def _serie_variable(n: int) -> Serie:
    """Serie con precio que se mueve, para que la volatilidad no sea 0."""
    obs = pd.DataFrame(
        {
            "ds": pd.date_range("2026-01-01", periods=n, freq="D"),
            "y": [2.0 + (i % 3) * 0.5 for i in range(n)],
        }
    )
    return Serie("sisap_minorista", "15", "PAPA", obs)


def test_serie_corta_usa_baseline_con_bandas():
    serie = _serie_variable(5)  # muy corta → no modelable
    assert not serie.es_modelable()

    pred = pronosticar_serie(serie, horizonte=3)

    assert list(pred.columns) == list(COLUMNAS_PRED)
    assert len(pred) == 3
    assert (pred["modelo"] == "naive").all()
    # el baseline ya no va sin bandas: se estiman de la volatilidad de la serie
    assert pred["yhat_lower"].notna().all()
    assert pred["yhat_upper"].notna().all()
    assert (pred["n_obs_entrenamiento"] == 5).all()


def test_serie_plana_deja_las_bandas_nulas():
    """Sin variación no hay volatilidad que estimar: mejor nulo que un cero falso."""
    pred = pronosticar_serie(_serie(5), horizonte=3)

    assert pred["yhat_lower"].isna().all()
    assert pred["yhat_upper"].isna().all()


def test_prophet_apagado_no_se_usa_ni_en_series_largas(monkeypatch):
    """El default de producción: Prophet perdió el backtesting y no debe servirse."""
    serie = _serie_variable(120)
    assert serie.es_modelable()

    def _explota(s, horizonte):
        raise AssertionError("Prophet no debería invocarse con USAR_PROPHET=False")

    monkeypatch.setattr(prophet_modelo, "pronosticar_prophet", _explota)

    pred = pronosticar_serie(serie, horizonte=4)

    assert (pred["modelo"] == "naive").all()


def test_serie_modelable_usa_prophet(monkeypatch):
    serie = _serie(120)  # historia holgada → modelable
    assert serie.es_modelable()
    monkeypatch.setattr(config, "USAR_PROPHET", True)

    def _fake_prophet(s, horizonte):
        fechas = pd.date_range("2026-06-01", periods=horizonte, freq="D")
        return pd.DataFrame(
            {"ds": fechas, "yhat": 2.0, "yhat_lower": 1.5, "yhat_upper": 2.5}
        )

    monkeypatch.setattr(prophet_modelo, "pronosticar_prophet", _fake_prophet)

    pred = pronosticar_serie(serie, horizonte=4)

    assert len(pred) == 4
    assert (pred["modelo"] == "prophet").all()
    assert pred["yhat_lower"].notna().all()  # Prophet sí trae bandas
    assert list(pred.columns) == list(COLUMNAS_PRED)
