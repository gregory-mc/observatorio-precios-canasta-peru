"""Tests de la detección de anomalías (observatorio.ml.anomalias)."""

import pandas as pd

from observatorio.ml.anomalias import (
    COLUMNAS_ANOMALIA,
    detectar_anomalias_serie,
    puntuar_serie,
)
from observatorio.ml.datos import Serie


def _serie(valores: list[float], producto: str = "PAPA") -> Serie:
    fechas = pd.date_range("2026-01-01", periods=len(valores), freq="D")
    obs = pd.DataFrame({"ds": fechas, "y": [float(v) for v in valores]})
    return Serie("sisap_minorista", "15", producto, obs)


def test_serie_estable_con_un_pico_marca_solo_el_pico():
    # 30 días en ~10.0 con ruido chico y un pico gigante en el día 20.
    valores = [10.0 + (0.1 if i % 2 else -0.1) for i in range(30)]
    valores[20] = 40.0
    serie = _serie(valores)

    anom = detectar_anomalias_serie(serie, ventana=7, umbral=2.5)

    assert list(anom.columns) == list(COLUMNAS_ANOMALIA)
    assert len(anom) == 1
    fila = anom.iloc[0]
    assert fila["fecha"] == pd.Timestamp("2026-01-21")  # día índice 20
    assert fila["precio"] == 40.0
    assert fila["residuo"] > 0
    assert abs(fila["z_score"]) > 2.5


def test_serie_plana_no_tiene_anomalias():
    serie = _serie([5.0] * 30)
    assert detectar_anomalias_serie(serie).empty


def test_serie_corta_no_es_evaluable():
    # menos de MIN_RESIDUOS residuos definidos ⇒ no se evalúa
    serie = _serie([10.0, 11.0, 9.0, 10.5, 40.0])
    assert detectar_anomalias_serie(serie).empty
    assert puntuar_serie(serie).empty


def test_puntuar_serie_excluye_el_primer_dia_sin_historia_previa():
    serie = _serie([10.0 + (0.1 if i % 2 else -0.1) for i in range(20)])
    puntuada = puntuar_serie(serie, ventana=7)
    # el primer día no tiene ventana previa ⇒ queda fuera
    assert puntuada["ds"].min() > serie.obs["ds"].min()
    assert {"ds", "y", "esperado", "residuo", "z_score"}.issubset(puntuada.columns)


def test_esperado_no_incluye_el_dia_evaluado():
    # nivel 10 durante 15 días; el día 15 salta a 20. Su esperado debe ser ~10
    # (media de los previos), no arrastrar su propio valor.
    valores = [10.0] * 15 + [20.0]
    serie = _serie(valores)
    puntuada = puntuar_serie(serie, ventana=7, min_residuos=1)
    ultimo = puntuada.iloc[-1]
    assert ultimo["y"] == 20.0
    assert round(ultimo["esperado"], 6) == 10.0
    assert round(ultimo["residuo"], 6) == 10.0
