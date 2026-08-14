"""Tests de la interfaz de fecha unificada del scraper SISAP (issue #21).

Verifican que ``--fecha YYYY-MM-DD`` reemplaza al antiguo env var ``FECHA_OVERRIDE``:
se parsea a ``date``, el default es ``None`` (→ hoy en hora Lima dentro del pipeline)
y una fecha mal formada aborta con error de CLI. No hace red: ``ejecutar_ingesta_diaria``
se monkeypatchea para capturar la fecha resuelta.
"""

from __future__ import annotations

from datetime import date

import pytest

from observatorio.ingesta.sisap import run_ingesta_sisap as run


def _capturar_fecha(monkeypatch) -> dict:
    capturado: dict = {}
    monkeypatch.setattr(
        run, "ejecutar_ingesta_diaria", lambda fecha=None: capturado.update(fecha=fecha)
    )
    return capturado


class TestFlagFecha:
    def test_fecha_valida_se_parsea_a_date(self, monkeypatch):
        capturado = _capturar_fecha(monkeypatch)
        assert run.main(["--fecha", "2026-06-12"]) == 0
        assert capturado["fecha"] == date(2026, 6, 12)

    def test_sin_flag_pasa_none(self, monkeypatch):
        # None ⇒ el pipeline usa "hoy en hora Lima" (default de negocio).
        capturado = _capturar_fecha(monkeypatch)
        run.main([])
        assert capturado["fecha"] is None

    def test_fecha_invalida_aborta(self, monkeypatch):
        _capturar_fecha(monkeypatch)  # no debe llegar a ejecutarse
        with pytest.raises(SystemExit):
            run.main(["--fecha", "2026-13-40"])

    def test_fecha_formato_no_iso_aborta(self, monkeypatch):
        _capturar_fecha(monkeypatch)
        with pytest.raises(SystemExit):
            run.main(["--fecha", "12/06/2026"])
