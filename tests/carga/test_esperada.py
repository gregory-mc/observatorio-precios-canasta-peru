"""Tests para la lógica de 'fuente esperada por día' en la carga a bronze.

Asegura que la ausencia de datos SISAP u OSINERGMIN en días no hábiles NO se trate
como fallo, mientras que marketplace (diario) y la falta de SISAP/OSINERGMIN en día
hábil sí lo son.
"""

from dataclasses import fields

from observatorio.carga.r2_a_supabase import FUENTES, FUENTES_DIARIAS, _esperada_dia_habil
from observatorio.ingesta.osinergmin.models import PrecioCombustible
from observatorio.ingesta.senamhi.models import MedicionClima


class TestEsperadaDiaHabil:
    def test_dia_habil_se_espera(self):
        assert _esperada_dia_habil("2026-06-12") is True  # viernes

    def test_sabado_no_se_espera(self):
        assert _esperada_dia_habil("2026-06-13") is False  # sábado

    def test_domingo_no_se_espera(self):
        assert _esperada_dia_habil("2026-06-14") is False  # domingo

    def test_feriado_no_se_espera(self):
        assert _esperada_dia_habil("2026-07-28") is False  # Independencia del Perú


class TestSpecFuentes:
    def test_sisap_declara_predicado_esperada(self):
        assert FUENTES["sisap"]["esperada"] is _esperada_dia_habil

    def test_marketplace_no_declara_esperada(self):
        # Sin predicado => se espera todos los días (su ausencia siempre es fallo).
        assert "esperada" not in FUENTES["marketplace"]

    def test_osinergmin_declara_predicado_esperada(self):
        # OSINERGMIN se opera como diaria-hábil: ausencia en finde/feriado no es
        # fallo (ver #97). Un solo día faltante ya no tumba toda la carga.
        assert FUENTES["osinergmin"]["esperada"] is _esperada_dia_habil

    def test_osinergmin_columnas_coinciden_con_modelo(self):
        # El CSV se escribe desde los campos del dataclass; las columnas del
        # cargador deben ir en el mismo orden y con los mismos nombres.
        nombres_carga = [c for c, _ in FUENTES["osinergmin"]["columnas"]]
        nombres_modelo = [f.name for f in fields(PrecioCombustible)]
        assert nombres_carga == nombres_modelo

    def test_clima_columnas_coinciden_con_modelo(self):
        nombres_carga = [c for c, _ in FUENTES["clima"]["columnas"]]
        nombres_modelo = [f.name for f in fields(MedicionClima)]
        assert nombres_carga == nombres_modelo

    def test_clima_es_fuente_diaria(self):
        # SENAMHI publica todos los días => entra en la corrida diaria (`ambas`).
        assert "clima" in FUENTES_DIARIAS

    def test_clima_tarea_apunta_al_csv_por_fecha(self):
        (clave, where, params), *resto = FUENTES["clima"]["tareas"]("2026-08-14")
        assert clave == "clima/2026-08-14_senamhi.csv"
        assert where == "fecha_captura = %s"
        assert params == ("2026-08-14",)
        assert resto == []
