"""Tests para la lógica de 'fuente esperada por día' en la carga a bronze.

Asegura que la ausencia de datos SISAP en días no hábiles NO se trate como fallo,
mientras que marketplace (diario) y la falta de SISAP en día hábil sí lo son.
"""

from observatorio.carga.r2_a_supabase import FUENTES, _sisap_esperada


class TestSisapEsperada:
    def test_dia_habil_se_espera(self):
        assert _sisap_esperada("2026-06-12") is True  # viernes

    def test_sabado_no_se_espera(self):
        assert _sisap_esperada("2026-06-13") is False  # sábado

    def test_domingo_no_se_espera(self):
        assert _sisap_esperada("2026-06-14") is False  # domingo

    def test_feriado_no_se_espera(self):
        assert _sisap_esperada("2026-07-28") is False  # Independencia del Perú


class TestSpecFuentes:
    def test_sisap_declara_predicado_esperada(self):
        assert FUENTES["sisap"]["esperada"] is _sisap_esperada

    def test_marketplace_no_declara_esperada(self):
        # Sin predicado => se espera todos los días (su ausencia siempre es fallo).
        assert "esperada" not in FUENTES["marketplace"]
