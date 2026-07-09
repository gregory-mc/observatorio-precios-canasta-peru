"""Tests de la construcción de filas para ml.predicciones_raw (sin DB)."""

from datetime import date

import pandas as pd

from observatorio.ml.persistencia import _COLS_INSERT, _filas_para_insertar


def _pred(**over) -> pd.DataFrame:
    base = {
        "fuente": ["sisap_minorista"],
        "cod_departamento": ["15"],
        "producto": ["PAPA"],
        "fecha_pred": pd.to_datetime(["2026-02-01"]),
        "yhat": [2.5],
        "yhat_lower": [2.0],
        "yhat_upper": [3.0],
        "modelo": ["prophet"],
        "n_obs_entrenamiento": [120],
    }
    base.update(over)
    return pd.DataFrame(base)


def test_filas_respetan_el_orden_de_columnas_del_insert():
    filas = _filas_para_insertar(_pred(), date(2026, 1, 31))
    assert len(filas) == 1
    fila = filas[0]
    assert len(fila) == len(_COLS_INSERT)
    # fecha_corrida, fuente, cod, producto, fecha_pred
    assert fila[0] == date(2026, 1, 31)
    assert fila[1] == "sisap_minorista"
    assert fila[4] == date(2026, 2, 1)  # convertida a date de Python
    assert isinstance(fila[4], date)


def test_bandas_nulas_del_baseline_salen_como_none():
    df = _pred(yhat_lower=[pd.NA], yhat_upper=[pd.NA], modelo=["media_movil"])
    fila = _filas_para_insertar(df, date(2026, 1, 31))[0]
    # posiciones de yhat_lower (6) y yhat_upper (7) en _COLS_INSERT
    assert fila[6] is None
    assert fila[7] is None
    assert fila[5] == 2.5  # yhat sí tiene valor


def test_varias_filas():
    df = pd.concat([_pred(), _pred(producto=["CEBOLLA"])], ignore_index=True)
    filas = _filas_para_insertar(df, date(2026, 1, 31))
    assert len(filas) == 2
    assert {f[3] for f in filas} == {"PAPA", "CEBOLLA"}
