"""Tests del techo a la resiliencia del batch (sin DB).

El caso de referencia es el fallo real del 2026-07-22: las 15 series de Prophet
se cayeron por un problema de entorno y la corrida terminó en éxito escribiendo
solo baseline.
"""

import logging

from observatorio.ml.backtesting import NOMBRES_MODELOS, _modelos_por_defecto
from observatorio.ml.cobertura import evaluar_cobertura, reportar


def test_modelo_caido_entero_marca_la_corrida_como_fallida():
    v = evaluar_cobertura({"prophet": 15, "media_movil": 148}, {"media_movil": 148})
    assert v.modelos_perdidos == ("prophet",)
    assert not v.ok


def test_corrida_completa_es_ok():
    v = evaluar_cobertura({"prophet": 15, "media_movil": 148}, {"prophet": 15, "media_movil": 148})
    assert v.ok
    assert v.n_perdido == 0
    assert v.tasa_fallo == 0.0


def test_perdida_difusa_por_encima_del_umbral_falla():
    # 60 de 100 series caídas, ningún modelo perdido del todo.
    v = evaluar_cobertura({"media_movil": 100}, {"media_movil": 40})
    assert v.modelos_perdidos == ()
    assert v.tasa_fallo == 0.6
    assert not v.ok


def test_perdida_pequena_se_tolera():
    v = evaluar_cobertura({"media_movil": 100}, {"media_movil": 95})
    assert v.ok
    assert v.n_perdido == 5


def test_umbral_es_configurable():
    assert not evaluar_cobertura({"m": 100}, {"m": 80}, umbral=0.1).ok
    assert evaluar_cobertura({"m": 100}, {"m": 80}, umbral=0.5).ok


def test_modelo_esperado_en_cero_no_cuenta_como_perdido():
    # Sin series modelables con Prophet, no haber producido Prophet no es un fallo.
    v = evaluar_cobertura({"prophet": 0, "media_movil": 20}, {"media_movil": 20})
    assert v.modelos_perdidos == ()
    assert v.ok


def test_desglose_muestra_obtenido_sobre_esperado():
    v = evaluar_cobertura({"prophet": 15, "media_movil": 148}, {"media_movil": 148})
    assert v.desglose() == "media_movil 148/148 · prophet 0/15"


def test_reportar_devuelve_exit_code_y_loguea(caplog):
    v = evaluar_cobertura({"prophet": 15, "media_movil": 148}, {"media_movil": 148})
    with caplog.at_level(logging.INFO):
        codigo = reportar(v, logging.getLogger("test.cobertura"))

    assert codigo == 1
    mensajes = " ".join(r.getMessage() for r in caplog.records)
    assert "prophet 0/15" in mensajes  # el desglose se loguea siempre
    assert "prophet" in mensajes


def test_reportar_ok_devuelve_cero_y_loguea_el_desglose(caplog):
    v = evaluar_cobertura({"media_movil": 20}, {"media_movil": 20})
    with caplog.at_level(logging.INFO):
        codigo = reportar(v, logging.getLogger("test.cobertura"))

    assert codigo == 0
    assert "media_movil 20/20" in " ".join(r.getMessage() for r in caplog.records)


def test_nombres_modelos_no_se_desalinea_del_registro_real():
    """Guarda: si alguien agrega un modelo al backtest, tiene que aparecer acá."""
    assert tuple(_modelos_por_defecto()) == NOMBRES_MODELOS
