"""Tests de la agregación de la canasta (issue #19).

Datos sintéticos del Módulo 601 (sin .dta ni base): verifican la ponderación por
factor07, la normalización de pesos, el conteo muestral a nivel de hogar y el
filtrado de productos no-MVP/procesados, además de la suite de calidad (§7).
"""

import pandas as pd
import pytest

from observatorio.canasta.construir_canasta import (
    SUITE_CANASTA,
    construir_pesos,
)
from observatorio.validacion import validar

ANIO = 2023


def _modulo_601() -> pd.DataFrame:
    """601 sintético: Lima (papa+pollo) y Arequipa (limón), con ruido a filtrar.

    Lima:
      H1 (factor 10): papa 501 (gasto 100, kg 50); pollo 901 (gasto 300, kg 30)
      H2 (factor 20): papa 501 (gasto 200, autoconsumo 50, kg 80);
                      papa 502 (gasto 40, kg 10)   ← 2ª presentación del MISMO hogar
    Arequipa:
      H3 (factor 5):  limón 3801 (gasto 20, kg 4)
    Ruido (debe descartarse): harina 1804 (otro grupo), papa seca 0507 (procesado).
    """
    filas = [
        # conglome, vivienda, hogar, ubigeo, p601a, i601c, i601e, i601b2, factor07
        (1, 1, 1, "150101", 501, 100, 0, 50, 10),
        (1, 1, 1, "150101", 901, 300, 0, 30, 10),
        (1, 1, 1, "150101", 1804, 999, 0, 99, 10),  # harina → descartar
        (1, 1, 2, "150101", 501, 200, 50, 80, 20),
        (1, 1, 2, "150101", 502, 40, 0, 10, 20),
        (1, 1, 2, "150101", "0507", 999, 0, 99, 20),  # papa seca → descartar
        (2, 1, 1, "040101", 3801, 20, 0, 4, 5),
    ]
    cols = [
        "conglome", "vivienda", "hogar", "ubigeo", "p601a",
        "i601c", "i601e", "i601b2", "factor07",
    ]
    return pd.DataFrame(filas, columns=cols)


@pytest.fixture
def canasta() -> pd.DataFrame:
    return construir_pesos(_modulo_601(), ANIO)


def _fila(df, cod, prod):
    sel = df[(df.cod_departamento == cod) & (df.producto == prod)]
    assert len(sel) == 1
    return sel.iloc[0]


class TestAgregacion:
    def test_filas_esperadas(self, canasta):
        # Lima: papa, pollo. Arequipa: limón. = 3 filas (ruido descartado).
        assert len(canasta) == 3
        assert set(zip(canasta.cod_departamento, canasta.producto, strict=True)) == {
            ("15", "papa"),
            ("15", "pollo"),
            ("04", "limon"),
        }

    def test_gasto_monetario_ponderado(self, canasta):
        # papa Lima: 100·10 + 200·20 + 40·20 = 5800
        assert _fila(canasta, "15", "papa").gasto_monetario_anual == pytest.approx(5800)

    def test_gasto_total_incluye_autoconsumo(self, canasta):
        # papa Lima total: (100)·10 + (200+50)·20 + (40)·20 = 6800 ≠ monetario.
        papa = _fila(canasta, "15", "papa")
        assert papa.gasto_total_anual == pytest.approx(6800)
        assert papa.gasto_total_anual > papa.gasto_monetario_anual

    def test_cantidad_kg_ponderada(self, canasta):
        # papa Lima kg: 50·10 + 80·20 + 10·20 = 2300
        assert _fila(canasta, "15", "papa").cantidad_kg_anual == pytest.approx(2300)

    def test_n_muestra_cuenta_hogares_no_lineas(self, canasta):
        # papa Lima: H1 y H2 → 2 hogares, aunque H2 tenga 2 presentaciones.
        assert _fila(canasta, "15", "papa").n_muestra == 2

    def test_hogares_expandidos(self, canasta):
        # papa Lima: factor de H1 (10) + H2 (20) = 30, sin duplicar por presentación.
        assert _fila(canasta, "15", "papa").hogares_expandidos == pytest.approx(30)

    def test_pesos_suman_uno_por_departamento(self, canasta):
        sumas = canasta.groupby("cod_departamento").peso_canasta.sum()
        assert sumas.loc["15"] == pytest.approx(1.0)
        assert sumas.loc["04"] == pytest.approx(1.0)

    def test_peso_proporcional_al_gasto(self, canasta):
        # peso papa Lima = 5800 / (5800 + 3000) = 0.6590...
        assert _fila(canasta, "15", "papa").peso_canasta == pytest.approx(5800 / 8800)

    def test_metadatos(self, canasta):
        papa = _fila(canasta, "15", "papa")
        assert papa.departamento == "Lima"
        assert papa.grupo_enaho == "05"
        assert papa.anio_enaho == ANIO
        assert "ENAHO 2023" in papa.fuente


class TestSuiteCanasta:
    def test_canasta_valida_pasa(self, canasta):
        # Pasa (los avisos de n_muestra<30 no bloquean: severidad advertencia).
        assert validar(canasta, SUITE_CANASTA).ok

    def test_pesos_rotos_fallan(self, canasta):
        roto = canasta.copy()
        roto.loc[roto.producto == "pollo", "peso_canasta"] = 0.99  # rompe Σ=1 en Lima
        reporte = validar(roto, SUITE_CANASTA)
        assert not reporte.ok
        assert any(e.expectativa == "pesos_suman_uno" for e in reporte.errores)

    def test_producto_invalido_falla(self, canasta):
        roto = canasta.copy()
        roto.loc[0, "producto"] = "quinua"
        assert not validar(roto, SUITE_CANASTA).ok

    def test_baja_confianza_es_advertencia(self, canasta):
        reporte = validar(canasta, SUITE_CANASTA)
        assert reporte.ok  # no bloquea
        assert any(a.expectativa == "soporte_muestral" for a in reporte.advertencias)


class TestVacio:
    def test_modulo_sin_mvp_devuelve_vacio(self):
        df = pd.DataFrame(
            [(1, 1, 1, "150101", 1804, 10, 0, 1, 5)],
            columns=[
                "conglome", "vivienda", "hogar", "ubigeo", "p601a",
                "i601c", "i601e", "i601b2", "factor07",
            ],
        )
        out = construir_pesos(df, ANIO)
        assert out.empty
        assert list(out.columns)  # mantiene el esquema de columnas

    def test_columnas_faltantes_lanza(self):
        with pytest.raises(ValueError, match="columnas requeridas"):
            construir_pesos(pd.DataFrame({"ubigeo": ["150101"]}), ANIO)
