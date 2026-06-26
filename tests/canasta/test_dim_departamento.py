"""Tests de la dimensión de departamentos (issue #19)."""

from observatorio.canasta.dim_departamento import (
    CODIGOS_DEPARTAMENTO,
    DEPARTAMENTOS,
    dim_departamento_df,
    nombre_departamento,
    region_sisap,
)


class TestDepartamentos:
    def test_son_25(self):
        assert len(DEPARTAMENTOS) == 25

    def test_codigos_de_dos_digitos_unicos(self):
        assert all(len(c) == 2 and c.isdigit() for c in DEPARTAMENTOS)
        assert len(set(DEPARTAMENTOS)) == 25

    def test_casos_que_confunden(self):
        # Lima = 15, Callao = 07 (no 07/15 cruzados).
        assert nombre_departamento("15") == "Lima"
        assert nombre_departamento("07") == "Callao"

    def test_codigo_inexistente(self):
        assert nombre_departamento("99") is None
        assert region_sisap("99") is None

    def test_region_sisap_por_defecto_es_el_nombre(self):
        assert region_sisap("04") == "Arequipa"


class TestDataFrame:
    def test_estructura(self):
        df = dim_departamento_df()
        assert len(df) == 25
        assert list(df.columns) == ["cod_departamento", "departamento", "region_sisap"]
        assert df.region_sisap.notna().all()

    def test_codigos_coinciden(self):
        df = dim_departamento_df()
        assert set(df.cod_departamento) == set(CODIGOS_DEPARTAMENTO)
