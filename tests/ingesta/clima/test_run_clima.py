"""Tests de la orquestación de la ingesta de clima (issue #14).

Sin red: monkeypatchea la descarga de Open-Meteo y verifica que ``main`` escriba
el CSV de la fecha objetivo y valide el flag ``--fecha``.
"""

from __future__ import annotations

import csv

import pytest

from observatorio.ingesta.clima import run_ingesta_clima as run
from observatorio.ingesta.clima.config import LOCALIDADES


def _resp_para(fecha_lista):
    # Una respuesta Open-Meteo por localidad, todas con las mismas fechas.
    n = len(fecha_lista)
    return [
        {"daily": {
            "time": fecha_lista,
            "precipitation_sum": [0.0] * n,
            "temperature_2m_max": [22.0] * n,
            "temperature_2m_min": [18.0] * n,
        }}
        for _ in LOCALIDADES
    ]


def test_escribe_csv_de_la_fecha(monkeypatch, tmp_path):
    resp = _resp_para(["2026-08-12", "2026-08-13"])
    monkeypatch.setattr(run, "descargar", lambda locs=None: resp)
    rc = run.main(["--fecha", "2026-08-13", "--salida", str(tmp_path)])
    assert rc == 0
    csv_path = tmp_path / "clima" / "2026-08-13_clima.csv"
    assert csv_path.exists()
    filas = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(filas) == len(LOCALIDADES)
    assert {f["fecha_captura"] for f in filas} == {"2026-08-13"}
    assert set(filas[0].keys()) >= {"localidad", "region", "precip_mm", "temp_max_c", "temp_min_c"}


def test_sin_dato_para_la_fecha_falla(monkeypatch, tmp_path):
    # Open-Meteo no trae la fecha pedida -> 0 filas -> exit 1.
    monkeypatch.setattr(run, "descargar", lambda locs=None: _resp_para(["2026-08-10"]))
    assert run.main(["--fecha", "2026-08-13", "--salida", str(tmp_path)]) == 1


def test_fecha_invalida_aborta(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "descargar", lambda locs=None: _resp_para(["2026-08-13"]))
    with pytest.raises(SystemExit):
        run.main(["--fecha", "2026-13-99", "--salida", str(tmp_path)])
