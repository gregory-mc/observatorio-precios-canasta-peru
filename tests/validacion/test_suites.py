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


def _osinergmin_ok() -> pd.DataFrame:
    # Dos grifos SIN codigo_osi (== "" en el CSV, como los entrega Facilito) que
    # venden el mismo producto: se distinguen por establecimiento + dirección.
    return pd.DataFrame(
        {
            "fecha_captura": ["2026-06-28", "2026-06-28"],
            "codigo_osi": ["", ""],
            "establecimiento": ["GRIFO A", "GRIFO B"],
            "direccion": ["AV. UNO 100", "AV. DOS 200"],
            "producto": ["Gasohol Regular", "Gasohol Regular"],
            "producto_codigo": ["126", "126"],
            "precio_soles_galon": ["15.80", "16.20"],
        }
    )


def _clima_ok() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha_captura": ["2026-08-14", "2026-08-14"],
            "cod_estacion": ["105053", "105056"],
            "precip_mm": ["0.0", "3.2"],
            "temp_max_c": ["29.8", "27.5"],
            "temp_min_c": ["15.4", "14.0"],
        }
    )


class TestSuitesPorFuente:
    def test_registro_cubre_fuentes_de_carga(self):
        # Las suites deben existir para las fuentes que el cargador conoce.
        assert {"marketplace", "sisap", "inei", "osinergmin", "clima"} <= set(SUITES)

    def test_clima_valido_pasa(self):
        assert validar(_clima_ok(), SUITES["clima"]).ok

    def test_clima_clave_duplicada_falla(self):
        df = _clima_ok()
        df.loc[1, "cod_estacion"] = "105053"  # misma (fecha, estación)
        assert not validar(df, SUITES["clima"]).ok

    def test_clima_precip_negativa_falla(self):
        df = _clima_ok()
        df.loc[0, "precip_mm"] = "-1"
        assert not validar(df, SUITES["clima"]).ok

    def test_clima_temp_absurda_falla(self):
        df = _clima_ok()
        df.loc[0, "temp_max_c"] = "999"  # fuera del rango físico
        assert not validar(df, SUITES["clima"]).ok

    def test_clima_precip_extrema_es_advertencia(self):
        df = _clima_ok()
        df.loc[0, "precip_mm"] = "800"  # > cota absurda, pero solo advierte
        reporte = validar(df, SUITES["clima"])
        assert reporte.ok
        assert reporte.advertencias

    def test_clima_temp_nula_permitida(self):
        # Estaciones pluviométricas no miden temperatura: null no debe fallar.
        df = _clima_ok()
        df.loc[0, "temp_max_c"] = ""
        df.loc[0, "temp_min_c"] = ""
        assert validar(df, SUITES["clima"]).ok

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

    def test_osinergmin_grifos_sin_codigo_osi_no_son_duplicados(self):
        # Regresión: varios grifos sin codigo_osi vendiendo el mismo producto NO
        # deben colapsar a la misma clave (antes fallaba la carga diaria).
        assert validar(_osinergmin_ok(), SUITES["osinergmin"]).ok

    def test_osinergmin_mismo_grifo_repetido_falla(self):
        # Duplicado real: mismo establecimiento + dirección + producto el mismo día.
        df = _osinergmin_ok()
        df.loc[1, "establecimiento"] = "GRIFO A"
        df.loc[1, "direccion"] = "AV. UNO 100"
        assert not validar(df, SUITES["osinergmin"]).ok

    def test_osinergmin_precio_negativo_falla(self):
        df = _osinergmin_ok()
        df.loc[0, "precio_soles_galon"] = "-1"
        assert not validar(df, SUITES["osinergmin"]).ok

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
