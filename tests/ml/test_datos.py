"""Tests del contrato de series (observatorio.ml.datos)."""

import pandas as pd
import pytest

from observatorio.ml.datos import Serie, construir_series


def _df(filas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(filas)


def test_construir_series_agrupa_por_grano_y_ordena_por_fecha():
    df = _df(
        [
            {"fecha_captura": "2026-01-03", "fuente": "sisap_minorista",
             "cod_departamento": "15", "producto": "PAPA", "precio_prom": 2.6},
            {"fecha_captura": "2026-01-01", "fuente": "sisap_minorista",
             "cod_departamento": "15", "producto": "PAPA", "precio_prom": 2.4},
            {"fecha_captura": "2026-01-01", "fuente": "sisap_minorista",
             "cod_departamento": "15", "producto": "CEBOLLA", "precio_prom": 3.0},
        ]
    )
    series = construir_series(df)

    assert len(series) == 2  # (PAPA) y (CEBOLLA)
    papa = next(s for s in series if s.producto == "PAPA")
    assert list(papa.obs["y"]) == [2.4, 2.6]  # ordenada ascendente por fecha
    assert list(papa.obs.columns) == ["ds", "y"]  # naming que espera Prophet
    assert pd.api.types.is_datetime64_any_dtype(papa.obs["ds"])


def test_construir_series_conserva_ambito_nacional_con_cod_nulo():
    df = _df(
        [
            {"fecha_captura": "2026-01-01", "fuente": "marketplace",
             "cod_departamento": None, "producto": "ARROZ", "precio_prom": 4.0},
            {"fecha_captura": "2026-01-02", "fuente": "marketplace",
             "cod_departamento": None, "producto": "ARROZ", "precio_prom": 4.2},
        ]
    )
    series = construir_series(df)

    assert len(series) == 1
    assert series[0].cod_departamento is None  # no se pierde el grupo con cod null
    assert series[0].clave == ("marketplace", None, "ARROZ")


def test_construir_series_es_determinista_ordenado_por_clave():
    df = _df(
        [
            {"fecha_captura": "2026-01-01", "fuente": "sisap_mayorista",
             "cod_departamento": "15", "producto": "PAPA", "precio_prom": 1.0},
            {"fecha_captura": "2026-01-01", "fuente": "sisap_minorista",
             "cod_departamento": "15", "producto": "PAPA", "precio_prom": 2.0},
        ]
    )
    claves = [s.clave for s in construir_series(df)]
    assert claves == sorted(claves)  # mayorista antes que minorista


def test_construir_series_falla_si_faltan_columnas():
    df = _df([{"fecha_captura": "2026-01-01", "fuente": "sisap_minorista"}])
    with pytest.raises(ValueError, match="Faltan columnas"):
        construir_series(df)


def _serie_diaria(n: int, fuente: str = "sisap_minorista") -> Serie:
    """Serie con n días consecutivos (span = n-1 días)."""
    obs = pd.DataFrame(
        {
            "ds": pd.date_range("2026-01-01", periods=n, freq="D"),
            "y": [2.0] * n,
        }
    )
    return Serie(fuente, "15", "PAPA", obs)


def test_span_y_n_obs():
    serie = _serie_diaria(10)
    assert serie.n_obs == 10
    assert serie.span_dias == 9  # 10 días consecutivos → span 9


def test_span_cero_con_menos_de_dos_obs():
    assert _serie_diaria(1).span_dias == 0


def test_es_modelable_exige_conteo_y_span():
    # 60 obs pero apretadas en 60 días (span < 90) → NO modelable
    apretada = _serie_diaria(60)
    assert apretada.n_obs == 60
    assert not apretada.es_modelable()

    # holgura de conteo y de span → modelable
    holgada = _serie_diaria(100)
    assert holgada.es_modelable()

    # umbrales personalizados
    assert apretada.es_modelable(min_obs=10, min_span=10)
