"""Tests de la orquestación batch (observatorio.ml.run_entrenamiento.entrenar_todas)."""

import pandas as pd

from observatorio.ml import run_entrenamiento
from observatorio.ml.datos import Serie
from observatorio.ml.prophet_modelo import COLUMNAS_PRED


def _serie(producto: str, n: int = 5) -> Serie:
    obs = pd.DataFrame(
        {"ds": pd.date_range("2026-01-01", periods=n, freq="D"), "y": [2.0] * n}
    )
    return Serie("sisap_minorista", "15", producto, obs)


def _pred_stub(horizonte: int) -> pd.DataFrame:
    fechas = pd.date_range("2026-06-01", periods=horizonte, freq="D")
    return pd.DataFrame(
        {
            "fecha_pred": fechas,
            "yhat": 2.0,
            "yhat_lower": pd.NA,
            "yhat_upper": pd.NA,
            "modelo": "media_movil",
            "n_obs_entrenamiento": 5,
        }
    )[list(COLUMNAS_PRED)]


def test_entrenar_todas_adjunta_identidad_y_concatena(monkeypatch):
    monkeypatch.setattr(
        run_entrenamiento, "pronosticar_serie", lambda s, horizonte: _pred_stub(horizonte)
    )
    series = [_serie("PAPA"), _serie("CEBOLLA")]

    df = run_entrenamiento.entrenar_todas(series, horizonte=3)

    assert len(df) == 6  # 2 series × 3 días
    assert set(df["producto"]) == {"PAPA", "CEBOLLA"}
    assert (df["fuente"] == "sisap_minorista").all()
    assert (df["cod_departamento"] == "15").all()
    # trae identidad + columnas de pronóstico
    for col in (*COLUMNAS_PRED, "fuente", "cod_departamento", "producto"):
        assert col in df.columns


def test_una_serie_que_falla_no_tumba_el_batch(monkeypatch):
    def _pronosticar(serie, horizonte):
        if serie.producto == "PAPA":
            raise RuntimeError("Prophet no convergió")
        return _pred_stub(horizonte)

    monkeypatch.setattr(run_entrenamiento, "pronosticar_serie", _pronosticar)
    series = [_serie("PAPA"), _serie("CEBOLLA")]

    df = run_entrenamiento.entrenar_todas(series, horizonte=2)

    assert set(df["producto"]) == {"CEBOLLA"}  # PAPA se omitió, no abortó


def test_sin_series_devuelve_dataframe_vacio(monkeypatch):
    monkeypatch.setattr(
        run_entrenamiento, "pronosticar_serie", lambda s, horizonte: _pred_stub(horizonte)
    )
    df = run_entrenamiento.entrenar_todas([], horizonte=3)
    assert df.empty
