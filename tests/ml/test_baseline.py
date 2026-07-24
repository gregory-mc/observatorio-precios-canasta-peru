"""Tests de los pronósticos de referencia (observatorio.ml.baseline)."""

import math

import pandas as pd
import pytest

from observatorio.ml.baseline import (
    agregar_bandas,
    pronostico_media_movil,
    pronostico_naive,
    volatilidad_diaria,
)
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


def test_volatilidad_normaliza_por_el_hueco_entre_observaciones():
    """Dos series con el mismo salto pero huecos distintos no son igual de volátiles.

    Las fuentes publican esparso: un salto de 1 sol en 1 día es mucho más
    volatilidad que el mismo salto repartido en 9 días.
    """
    densa = _serie(["2026-01-01", "2026-01-02", "2026-01-03"], [2.0, 3.0, 2.0])
    esparsa = _serie(["2026-01-01", "2026-01-10", "2026-01-19"], [2.0, 3.0, 2.0])

    assert volatilidad_diaria(densa) > volatilidad_diaria(esparsa)
    # el escalado es √hueco: 9 días de hueco reducen la volatilidad diaria a 1/3
    assert volatilidad_diaria(densa) / volatilidad_diaria(esparsa) == pytest.approx(3.0)


def test_volatilidad_es_nan_si_no_hay_suficiente_historia():
    assert math.isnan(volatilidad_diaria(_serie(["2026-01-01", "2026-01-02"], [2.0, 3.0])))


def test_bandas_se_ensanchan_con_el_horizonte():
    # precio alto a propósito: así la banda inferior no toca el clip en 0 y se
    # puede comprobar el escalado limpio.
    serie = _serie(["2026-01-01", "2026-01-02", "2026-01-03"], [20.0, 21.0, 20.0])
    pred = agregar_bandas(pronostico_naive(serie, horizonte=4), serie)

    ancho = pred["yhat_upper"] - pred["yhat_lower"]
    assert list(ancho) == sorted(ancho)  # monótono creciente
    # crece como √h: el día 4 es el doble de ancho que el día 1
    assert ancho.iloc[3] / ancho.iloc[0] == pytest.approx(2.0)


def test_bandas_encierran_al_pronostico_y_no_bajan_de_cero():
    serie = _serie(["2026-01-01", "2026-01-02", "2026-01-03"], [0.5, 8.0, 0.5])
    pred = agregar_bandas(pronostico_naive(serie, horizonte=14), serie)

    assert (pred["yhat_lower"] <= pred["yhat"]).all()
    assert (pred["yhat"] <= pred["yhat_upper"]).all()
    assert (pred["yhat_lower"] >= 0).all()  # un precio negativo no existe


def test_bandas_nulas_si_la_serie_es_plana():
    serie = _serie(["2026-01-01", "2026-01-02", "2026-01-03"], [2.0, 2.0, 2.0])
    pred = agregar_bandas(pronostico_naive(serie, horizonte=3), serie)

    assert pred["yhat_lower"].isna().all()
    assert pred["yhat_upper"].isna().all()
