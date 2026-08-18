"""Tests del parser de clima Open-Meteo (issue #14).

Sin red: construyen respuestas Open-Meteo sintéticas (una por localidad, con su
bloque ``daily``) y verifican la selección por fecha, el alineamiento por índice,
el manejo de null y el descarte de localidades sin dato.
"""

from __future__ import annotations

from observatorio.ingesta.clima.config import Localidad
from observatorio.ingesta.clima.parser import parsear

_LOCS = [
    Localidad("Lima", "lima", -12.05, -77.04),
    Localidad("Ica", "ica", -14.07, -75.73),
]


def _item(tiempos, precip, tmax, tmin):
    return {"daily": {
        "time": tiempos,
        "precipitation_sum": precip,
        "temperature_2m_max": tmax,
        "temperature_2m_min": tmin,
    }}


class TestParsear:
    def test_toma_la_fecha_objetivo_por_localidad(self):
        fechas = ["2026-08-12", "2026-08-13", "2026-08-14"]
        resp = [
            _item(fechas, [0.0, 1.5, 3.0], [23.5, 22.0, 21.0], [19.0, 18.5, 18.0]),
            _item(fechas, [0.0, 0.0, 0.2], [30.0, 29.0, 28.0], [16.0, 15.5, 15.0]),
        ]
        filas = parsear(resp, _LOCS, "2026-08-13")
        assert len(filas) == 2
        assert {f.localidad for f in filas} == {"Lima", "Ica"}
        lima = next(f for f in filas if f.localidad == "Lima")
        assert (lima.precip_mm, lima.temp_max_c, lima.temp_min_c) == (1.5, 22.0, 18.5)
        assert lima.region == "lima" and lima.fuente == "open-meteo"

    def test_precip_cero_se_conserva(self):
        resp = [_item(["2026-08-13"], [0.0], [22.0], [18.0])]
        filas = parsear(resp, _LOCS[:1], "2026-08-13")
        assert len(filas) == 1 and filas[0].precip_mm == 0.0

    def test_null_pasa_a_none(self):
        resp = [_item(["2026-08-13"], [None], [22.0], [None])]
        filas = parsear(resp, _LOCS[:1], "2026-08-13")
        assert filas[0].precip_mm is None and filas[0].temp_min_c is None

    def test_descarta_localidad_sin_la_fecha(self):
        resp = [
            _item(["2026-08-13"], [1.0], [22.0], [18.0]),
            _item(["2026-08-12"], [0.0], [30.0], [16.0]),  # no tiene el 13
        ]
        filas = parsear(resp, _LOCS, "2026-08-13")
        assert [f.localidad for f in filas] == ["Lima"]

    def test_descarta_dia_todo_null(self):
        resp = [_item(["2026-08-13"], [None], [None], [None])]
        assert parsear(resp, _LOCS[:1], "2026-08-13") == []
