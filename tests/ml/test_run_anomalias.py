"""Tests de la orquestación de anomalías (observatorio.ml.run_anomalias)."""

import pandas as pd

from observatorio.ml import run_anomalias
from observatorio.ml.anomalias import METODO
from observatorio.ml.datos import Serie


def _serie(producto: str) -> Serie:
    obs = pd.DataFrame(
        {"ds": pd.date_range("2026-01-01", periods=3, freq="D"), "y": [1.0, 2.0, 3.0]}
    )
    return Serie("sisap_minorista", "15", producto, obs)


def _anom_stub(serie: Serie, umbral: float) -> pd.DataFrame:
    # una anomalía si el producto es PAPA, ninguna si no.
    if serie.producto != "PAPA":
        return pd.DataFrame(columns=["fecha", "precio", "esperado", "residuo", "z_score"])
    return pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2026-01-03"]),
            "precio": [3.0],
            "esperado": [1.5],
            "residuo": [1.5],
            "z_score": [3.1],
        }
    )


def test_detectar_todas_adjunta_identidad_metodo_y_umbral(monkeypatch):
    monkeypatch.setattr(run_anomalias, "detectar_anomalias_serie", _anom_stub)
    df = run_anomalias.detectar_todas([_serie("PAPA"), _serie("CEBOLLA")], umbral=2.5)

    assert len(df) == 1  # solo PAPA aportó anomalía
    fila = df.iloc[0]
    assert fila["producto"] == "PAPA"
    assert fila["fuente"] == "sisap_minorista"
    assert fila["cod_departamento"] == "15"
    assert fila["metodo"] == METODO
    assert fila["umbral_sigma"] == 2.5


def test_detectar_todas_sin_anomalias_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(
        run_anomalias,
        "detectar_anomalias_serie",
        lambda s, umbral: pd.DataFrame(
            columns=["fecha", "precio", "esperado", "residuo", "z_score"]
        ),
    )
    assert run_anomalias.detectar_todas([_serie("PAPA")], umbral=2.5).empty
