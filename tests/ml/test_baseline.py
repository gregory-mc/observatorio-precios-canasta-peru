"""Tests de los pronósticos de referencia (observatorio.ml.baseline)."""

import pandas as pd
import pytest

from observatorio.ml.baseline import pronostico_media_movil, pronostico_naive
from observatorio.ml.datos import Serie


def _serie(fechas: list[str], valores: list[float]) -> Serie:
    obs = pd.DataFrame({"ds": pd.to_datetime(fechas), "y": valores})
    return Serie("sisap_minorista", "15", "PAPA", obs)


def test_naive_proyecta_ultimo_valor_constante():
    serie = _serie(["2026-01-01", "2026-01-02", "2026-01-03"], [2.0, 2.5, 3.0])
    pred = pronostico_naive(serie, horizonte=3)

    assert list(pred["yhat"]) == [3.0, 3.0, 3.0]
    # las fechas arrancan el día siguiente a la última observación
    assert list(pred["ds"]) == list(pd.to_datetime(["2026-01-04", "2026-01-05", "2026-01-06"]))


def test_media_movil_promedia_solo_dentro_de_la_ventana_de_calendario():
    # 01-01 queda fuera de la ventana de 7 días respecto al 01-08
    serie = _serie(["2026-01-01", "2026-01-05", "2026-01-08"], [1.0, 2.0, 3.0])
    pred = pronostico_media_movil(serie, horizonte=1, ventana=7)

    assert round(pred["yhat"].iloc[0], 6) == 2.5  # media de 2.0 y 3.0


def test_media_movil_ventana_amplia_incluye_todo():
    serie = _serie(["2026-01-01", "2026-01-05", "2026-01-08"], [1.0, 2.0, 3.0])
    pred = pronostico_media_movil(serie, horizonte=1, ventana=30)
    assert round(pred["yhat"].iloc[0], 6) == 2.0  # media de 1, 2, 3


def test_horizonte_define_cantidad_de_filas():
    serie = _serie(["2026-01-01", "2026-01-02"], [1.0, 2.0])
    assert len(pronostico_naive(serie, horizonte=14)) == 14
    assert len(pronostico_media_movil(serie, horizonte=5)) == 5


def test_serie_vacia_es_error():
    vacia = _serie([], [])
    with pytest.raises(ValueError):
        pronostico_naive(vacia)
    with pytest.raises(ValueError):
        pronostico_media_movil(vacia)
