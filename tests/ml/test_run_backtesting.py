"""Tests de la orquestación de backtesting (observatorio.ml.run_backtesting)."""

import pandas as pd

from observatorio.ml import run_backtesting
from observatorio.ml.backtesting import ResultadoBacktest
from observatorio.ml.datos import Serie


def _serie(producto: str) -> Serie:
    obs = pd.DataFrame(
        {"ds": pd.date_range("2026-01-01", periods=3, freq="D"), "y": [1.0, 2.0, 3.0]}
    )
    return Serie("sisap_minorista", "15", producto, obs)


def _resultados(serie: Serie) -> list[ResultadoBacktest]:
    return [
        ResultadoBacktest("sisap_minorista", "15", serie.producto, "prophet", 3, 30, 5.0, 0.5),
        ResultadoBacktest("sisap_minorista", "15", serie.producto, "media_movil", 3, 30, 8.0, 0.9),
    ]


def test_evaluar_todas_concatena_y_agrega_horizonte(monkeypatch):
    monkeypatch.setattr(run_backtesting, "comparar_serie", lambda s, horizonte: _resultados(s))
    df = run_backtesting.evaluar_todas([_serie("PAPA"), _serie("CEBOLLA")], horizonte=14)

    assert len(df) == 4  # 2 series × 2 modelos
    assert (df["horizonte"] == 14).all()
    assert set(df["producto"]) == {"PAPA", "CEBOLLA"}
    assert set(df["modelo"]) == {"prophet", "media_movil"}


def test_evaluar_todas_sin_resultados_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(run_backtesting, "comparar_serie", lambda s, horizonte: [])
    assert run_backtesting.evaluar_todas([_serie("PAPA")], horizonte=14).empty


def test_loguear_veredicto_no_falla_sin_prophet(monkeypatch):
    # grupo sin fila 'prophet' no debe romper el conteo
    df = pd.DataFrame(
        [
            {
                "fuente": "sisap_minorista",
                "cod_departamento": "15",
                "producto": "PAPA",
                "modelo": "media_movil",
                "mape": 8.0,
            },
        ]
    )
    run_backtesting._loguear_veredicto(df)  # no exception


# --- Techo a la resiliencia: comparar_serie descarta el modelo que se cae, así
# que un Prophet roto dejaba métricas solo de baselines y exit 0.


def _metricas(modelos: list[str], productos: list[str]) -> pd.DataFrame:
    filas = [
        {
            "fuente": "sisap_minorista",
            "cod_departamento": "15",
            "producto": p,
            "modelo": m,
            "mape": 5.0,
            "rmse": 0.5,
        }
        for p in productos
        for m in modelos
    ]
    return pd.DataFrame(filas)


def test_esperado_es_una_fila_por_serie_evaluable_y_modelo():
    df = _metricas(["prophet", "media_movil", "naive"], ["PAPA", "CEBOLLA"])
    assert run_backtesting._esperado(df) == {"prophet": 2, "media_movil": 2, "naive": 2}


def test_obtenido_refleja_el_modelo_ausente():
    df = _metricas(["media_movil", "naive"], ["PAPA", "CEBOLLA"])
    assert run_backtesting._obtenido(df) == {"media_movil": 2, "naive": 2}
    assert run_backtesting._esperado(df)["prophet"] == 2  # se esperaba y no salió


class _Args:
    fecha_corrida = None
    fuente = None
    horizonte = 14
    db_url = None


def test_ejecutar_falla_si_prophet_no_produjo_ninguna_serie(monkeypatch):
    monkeypatch.setattr(run_backtesting, "cargar_series", lambda **kw: [_serie("PAPA")])
    monkeypatch.setattr(
        run_backtesting,
        "evaluar_todas",
        lambda series, horizonte: _metricas(["media_movil", "naive"], ["PAPA"]),
    )
    escrituras = []
    monkeypatch.setattr(
        run_backtesting,
        "escribir_backtest_metricas",
        lambda df, fecha, db_url=None: escrituras.append(len(df)) or len(df),
    )

    assert run_backtesting.ejecutar(_Args()) == 1
    assert escrituras == []


def test_ejecutar_ok_con_los_tres_modelos(monkeypatch):
    monkeypatch.setattr(run_backtesting, "cargar_series", lambda **kw: [_serie("PAPA")])
    monkeypatch.setattr(
        run_backtesting,
        "evaluar_todas",
        lambda series, horizonte: _metricas(["prophet", "media_movil", "naive"], ["PAPA"]),
    )
    escrituras = []
    monkeypatch.setattr(
        run_backtesting,
        "escribir_backtest_metricas",
        lambda df, fecha, db_url=None: escrituras.append(len(df)) or len(df),
    )

    assert run_backtesting.ejecutar(_Args()) == 0
    assert escrituras == [3]
