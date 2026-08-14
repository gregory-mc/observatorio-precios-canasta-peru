"""Tests de la orquestación de la ingesta SENAMHI (issue #14, paso 3).

Sin red: monkeypatchea el catálogo y la descarga de series para verificar que
``recolectar`` toma solo la fila de la fecha objetivo por estación y que un fallo
puntual de una estación no aborta el barrido.
"""

from __future__ import annotations

from observatorio.ingesta.senamhi import run_ingesta_senamhi as run
from observatorio.ingesta.senamhi.models import Estacion

_EST_A = Estacion("111", "", "ALFA", "CO", "M", "REAL", -12.0, -77.0, region="lima")
_EST_B = Estacion("222", "", "BETA", "EMA", "M", "AUTOMATICA", -14.0, -75.7, region="ica")


def _html(categories, precip):
    cats = "categories: [" + ",".join(f"'{c}'" for c in categories) + ",]"
    arr = ",".join("null" if v is None else str(v) for v in precip)
    serie = "{ name: 'Precipitación', data: [" + arr + ",] }"
    return "<script>xAxis: [{" + cats + "}], series: [" + serie + "]</script>"


def test_recolectar_toma_solo_la_fecha_objetivo(monkeypatch):
    monkeypatch.setattr(run, "obtener_catalogo_curado", lambda: [_EST_A, _EST_B])
    # Cada estación devuelve una ventana de 3 días; recolectar debe quedarse con 1.
    html = _html(["2026-08-12", "2026-08-13", "2026-08-14"], [1.0, 2.0, 3.0])
    monkeypatch.setattr(run, "descargar_serie", lambda est, session=None: html)

    filas, errores = run.recolectar("2026-08-13")
    assert errores == 0
    assert len(filas) == 2  # una fila por estación para el 13
    assert {f.cod_estacion for f in filas} == {"111", "222"}
    assert all(f.fecha_captura == "2026-08-13" for f in filas)
    assert all(f.precip_mm == 2.0 for f in filas)


def test_recolectar_tolera_estacion_caida(monkeypatch):
    monkeypatch.setattr(run, "obtener_catalogo_curado", lambda: [_EST_A, _EST_B])

    def descarga(est, session=None):
        if est.cod == "111":
            raise RuntimeError("timeout")
        return _html(["2026-08-14"], [5.0])

    monkeypatch.setattr(run, "descargar_serie", descarga)
    filas, errores = run.recolectar("2026-08-14")
    assert errores == 1
    assert [f.cod_estacion for f in filas] == ["222"]


def test_fecha_invalida_aborta(monkeypatch):
    monkeypatch.setattr(run, "obtener_catalogo_curado", lambda: [])
    import pytest

    with pytest.raises(SystemExit):
        run.main(["--fecha", "2026-99-99"])
