"""Tests del motor de validación y de las suites por fuente (issue #18).

Corren solo con pandas (sin red ni base): construyen DataFrames sintéticos y
verifican que cada expectativa y cada suite distingan datos buenos de corruptos.
"""

import pandas as pd
import pytest

from observatorio.validacion import (
    SUITES,
    ClaveUnica,
    ColumnasPresentes,
    EnConjunto,
    EnRango,
    MinFilas,
    NoNulo,
    Predicado,
    Suite,
    ValidacionError,
    validar,
    validar_o_error,
)


# --------------------------------------------------------------------------- #
# Expectativas individuales
# --------------------------------------------------------------------------- #
class TestColumnasPresentes:
    def test_todas_presentes(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        assert ColumnasPresentes(["a", "b"]).evaluar(df).ok

    def test_falta_columna(self):
        df = pd.DataFrame({"a": [1]})
        r = ColumnasPresentes(["a", "b"]).evaluar(df)
        assert not r.ok
        assert "b" in r.detalle


class TestMinFilas:
    def test_suficientes(self):
        assert MinFilas(1).evaluar(pd.DataFrame({"a": [1]})).ok

    def test_vacio_falla(self):
        assert not MinFilas(1).evaluar(pd.DataFrame({"a": []})).ok


class TestNoNulo:
    def test_sin_nulos(self):
        assert NoNulo("a").evaluar(pd.DataFrame({"a": [1, 2]})).ok

    def test_nan_es_nulo(self):
        r = NoNulo("a").evaluar(pd.DataFrame({"a": [1, None]}))
        assert not r.ok and r.n_fallos == 1

    def test_cadena_vacia_es_nulo(self):
        # El CSV crudo escribe los None como "" — deben contar como ausentes.
        r = NoNulo("a").evaluar(pd.DataFrame({"a": ["x", "", "  "]}))
        assert not r.ok and r.n_fallos == 2

    def test_columna_ausente_falla(self):
        assert not NoNulo("z").evaluar(pd.DataFrame({"a": [1]})).ok


class TestEnRango:
    def test_dentro(self):
        assert EnRango("p", minimo=0).evaluar(pd.DataFrame({"p": [0, 5, 10]})).ok

    def test_negativo_fuera(self):
        r = EnRango("p", minimo=0).evaluar(pd.DataFrame({"p": [-1, 2]}))
        assert not r.ok and r.n_fallos == 1

    def test_maximo(self):
        r = EnRango("p", maximo=100).evaluar(pd.DataFrame({"p": [50, 200]}))
        assert not r.ok and r.n_fallos == 1

    def test_strings_numericos_se_coaccionan(self):
        # bronze llega como texto del CSV: "0.5" es válido, "abc" no.
        assert EnRango("p", minimo=0).evaluar(pd.DataFrame({"p": ["0.5", "1.2"]})).ok
        r = EnRango("p", minimo=0).evaluar(pd.DataFrame({"p": ["abc", "1"]}))
        assert not r.ok and r.n_fallos == 1

    def test_nulos_se_ignoran_por_defecto(self):
        assert EnRango("p", minimo=0).evaluar(pd.DataFrame({"p": [None, "", 5]})).ok

    def test_nulos_fallan_si_no_permitidos(self):
        r = EnRango("p", minimo=0, permite_nulo=False).evaluar(pd.DataFrame({"p": [None, 5]}))
        assert not r.ok


class TestEnConjunto:
    def test_dominio_ok(self):
        e = EnConjunto("t", {"minorista", "mayorista"})
        assert e.evaluar(pd.DataFrame({"t": ["minorista", "mayorista"]})).ok

    def test_fuera_de_dominio(self):
        e = EnConjunto("t", {"minorista", "mayorista"})
        r = e.evaluar(pd.DataFrame({"t": ["minorista", "otro"]}))
        assert not r.ok and r.n_fallos == 1


class TestClaveUnica:
    def test_sin_duplicados(self):
        df = pd.DataFrame({"f": ["d1", "d1"], "k": ["a", "b"]})
        assert ClaveUnica(["f", "k"]).evaluar(df).ok

    def test_con_duplicados(self):
        df = pd.DataFrame({"f": ["d1", "d1"], "k": ["a", "a"]})
        r = ClaveUnica(["f", "k"]).evaluar(df)
        assert not r.ok and r.n_fallos == 2  # ambas filas del par duplicado


class TestPredicado:
    def test_ok_y_falla(self):
        suma_par = Predicado(
            "suma_par",
            lambda d: (d["x"].sum() % 2 == 0, 0, "suma par", ()),
        )
        assert suma_par.evaluar(pd.DataFrame({"x": [2, 4]})).ok
        assert not suma_par.evaluar(pd.DataFrame({"x": [1, 4]})).ok


# --------------------------------------------------------------------------- #
# Runner: severidad y aborto
# --------------------------------------------------------------------------- #
class TestRunnerSeveridad:
    def test_advertencia_no_hace_fallar(self):
        suite = Suite("s", [EnRango("p", maximo=10, severidad="advertencia")])
        reporte = validar(pd.DataFrame({"p": [999]}), suite)
        assert reporte.ok  # solo advertencia → reporte OK
        assert len(reporte.advertencias) == 1

    def test_error_hace_fallar(self):
        suite = Suite("s", [EnRango("p", minimo=0)])
        reporte = validar(pd.DataFrame({"p": [-1]}), suite)
        assert not reporte.ok
        assert len(reporte.errores) == 1

    def test_validar_o_error_lanza(self):
        suite = Suite("s", [NoNulo("a")])
        with pytest.raises(ValidacionError):
            validar_o_error(pd.DataFrame({"a": [None]}), suite)

    def test_validar_o_error_devuelve_reporte_si_pasa(self):
        suite = Suite("s", [NoNulo("a")])
        reporte = validar_o_error(pd.DataFrame({"a": [1]}), suite)
        assert reporte.ok


# --------------------------------------------------------------------------- #
# Suites reales por fuente
# --------------------------------------------------------------------------- #
def _sisap_ok() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha_captura": ["2026-06-26", "2026-06-26"],
            "region": ["Lima", "Lima"],
            "tipo_mercado": ["minorista", "minorista"],
            "producto": ["papa blanca", "limón"],
            "unidad_medida": ["kg", "kg"],
            "equiv_kg_lt": ["1.0", "1.0"],
            "precio_prom": ["2.50", "4.00"],
        }
    )


class TestSuitesPorFuente:
    def test_registro_cubre_fuentes_de_carga(self):
        # Las suites deben existir para las fuentes que el cargador conoce.
        assert {"marketplace", "sisap", "inei", "osinergmin"} <= set(SUITES)

    def test_sisap_valido_pasa(self):
        assert validar(_sisap_ok(), SUITES["sisap"]).ok

    def test_sisap_precio_negativo_falla(self):
        df = _sisap_ok()
        df.loc[0, "precio_prom"] = "-1"
        assert not validar(df, SUITES["sisap"]).ok

    def test_sisap_tipo_mercado_invalido_falla(self):
        df = _sisap_ok()
        df.loc[0, "tipo_mercado"] = "informal"
        assert not validar(df, SUITES["sisap"]).ok

    def test_sisap_clave_duplicada_falla(self):
        df = _sisap_ok()
        df.loc[1, "producto"] = "papa blanca"  # mismo (fecha, region, tipo, producto)
        assert not validar(df, SUITES["sisap"]).ok

    def test_inei_mes_fuera_de_rango_falla(self):
        df = pd.DataFrame(
            {
                "base": ["2021"],
                "periodo": ["2026-13"],
                "anio": ["2026"],
                "mes": ["13"],
                "indice": ["110.5"],
            }
        )
        assert not validar(df, SUITES["inei"]).ok

    def test_marketplace_precio_absurdo_es_advertencia(self):
        df = pd.DataFrame(
            {
                "fecha_captura": ["2026-06-26"],
                "sku_id": ["X1"],
                "precio": ["999999"],
                "precio_lista": ["999999"],
            }
        )
        reporte = validar(df, SUITES["marketplace"])
        assert reporte.ok  # precio absurdo solo advierte, no bloquea
        assert reporte.advertencias
