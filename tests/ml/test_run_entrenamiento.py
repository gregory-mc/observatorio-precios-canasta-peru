"""Tests de la orquestación batch (observatorio.ml.run_entrenamiento.entrenar_todas)."""

import pandas as pd

from observatorio.ml import config, run_entrenamiento
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


# --- Techo a la resiliencia: un modelo caído entero debe fallar la corrida ------
# Reproduce el fallo real del 2026-07-22 (todas las series de Prophet caídas por
# un problema de entorno, batch terminado en éxito con solo baseline).


def _serie_larga(producto: str) -> Serie:
    """Serie que supera el umbral de historia → se espera Prophet."""
    obs = pd.DataFrame(
        {"ds": pd.date_range("2024-01-01", periods=120, freq="D"), "y": [2.0] * 120}
    )
    return Serie("sisap_minorista", "15", producto, obs)


def test_esperado_sigue_la_config_no_solo_el_umbral(monkeypatch):
    """Con Prophet apagado (el default), ninguna serie se espera por Prophet.

    Regresión: `_esperado` calculaba el modelo por su cuenta, así que al apagar
    Prophet esperaba series que ya nadie producía y la cobertura abortaba una
    corrida sana.
    """
    series = [_serie_larga("PAPA"), _serie("CEBOLLA")]

    monkeypatch.setattr(config, "USAR_PROPHET", False)
    assert run_entrenamiento._esperado(series) == {"naive": 2}

    monkeypatch.setattr(config, "USAR_PROPHET", True)
    assert run_entrenamiento._esperado(series) == {"prophet": 1, "naive": 1}


def test_obtenido_cuenta_series_distintas_no_filas():
    df = pd.concat(
        [
            _pred_stub(3).assign(fuente="sisap_minorista", cod_departamento="15", producto="PAPA"),
            _pred_stub(3).assign(
                fuente="sisap_minorista", cod_departamento="15", producto="CEBOLLA"
            ),
        ],
        ignore_index=True,
    )
    # 6 filas, 2 series
    assert run_entrenamiento._obtenido(df) == {"media_movil": 2}


class _Args:
    fecha_corrida = None
    fuente = None
    horizonte = 3
    db_url = None


def test_ejecutar_falla_si_se_cae_el_modelo_entero(monkeypatch):
    """Prophet se cae en todas sus series: la corrida NO debe escribir ni salir 0."""
    series = [_serie_larga("PAPA"), _serie("CEBOLLA")]
    monkeypatch.setattr(config, "USAR_PROPHET", True)  # el escenario exige a Prophet encendido
    monkeypatch.setattr(run_entrenamiento, "cargar_series", lambda **kw: series)

    def _pronosticar(serie, horizonte):
        if serie.es_modelable():
            raise RuntimeError("stan_backend no cargó")
        return _pred_stub(horizonte)

    monkeypatch.setattr(run_entrenamiento, "pronosticar_serie", _pronosticar)

    escrituras = []
    monkeypatch.setattr(
        run_entrenamiento,
        "escribir_predicciones",
        lambda df, fecha, db_url=None: escrituras.append(len(df)) or len(df),
    )

    codigo = run_entrenamiento.ejecutar(_Args())

    assert codigo == 1
    assert escrituras == []  # no se escribe una corrida a medias


def test_ejecutar_ok_cuando_todos_los_modelos_responden(monkeypatch):
    series = [_serie_larga("PAPA"), _serie("CEBOLLA")]
    monkeypatch.setattr(config, "USAR_PROPHET", True)
    monkeypatch.setattr(run_entrenamiento, "cargar_series", lambda **kw: series)
    monkeypatch.setattr(
        run_entrenamiento,
        "pronosticar_serie",
        lambda s, horizonte: _pred_stub(horizonte).assign(
            modelo="prophet" if s.es_modelable() else config.MODELO_SERVIDO
        ),
    )
    escrituras = []
    monkeypatch.setattr(
        run_entrenamiento,
        "escribir_predicciones",
        lambda df, fecha, db_url=None: escrituras.append(len(df)) or len(df),
    )

    assert run_entrenamiento.ejecutar(_Args()) == 0
    assert escrituras == [6]  # 2 series × 3 días
