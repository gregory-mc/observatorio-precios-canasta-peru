"""Tests de la validación de solidez interna de la canasta (issue #20, opción B).

Corren sin red ni base: alimentan las funciones puras del módulo
``canasta_vs_ipc`` con estructuras sintéticas y verifican el veredicto de solidez
(pesos que suman 1, cobertura estable, precios plausibles, continuidad) y que el
contraste con el IPC sea meramente descriptivo (no gatilla el veredicto).
"""

from observatorio.validacion.canasta_vs_ipc import (
    RANGO_PLAUSIBLE_DEFAULT,
    RANGOS_PLAUSIBLES_SOLKG,
    comparar,
    construir_indice,
    evaluar_solidez,
    rango_plausible,
)

# Canasta MVP mínima: 3 productos con pesos que suman 1, 3 meses completos.
PESOS_OK = {"papa": 0.5, "pollo": 0.3, "tomate": 0.2}
PRECIOS_OK = {
    "2024-01": {"papa": 3.5, "pollo": 10.0, "tomate": 4.0},
    "2024-02": {"papa": 3.8, "pollo": 9.5, "tomate": 4.5},
    "2024-03": {"papa": 3.2, "pollo": 11.0, "tomate": 3.8},
}


def _indice(precios=PRECIOS_OK, pesos=PESOS_OK):
    return construir_indice(precios, pesos)


class TestEvaluarSolidez:
    def test_canasta_sana_es_solida(self):
        sol = evaluar_solidez(PRECIOS_OK, PESOS_OK, _indice())
        assert sol["veredicto"] == "CANASTA SÓLIDA"
        checks = sol["checks"]
        assert checks["pesos_suman_1"]["ok"]
        assert checks["cobertura"]["ok"]
        assert checks["precios_plausibles"]["ok"]
        assert checks["serie_continua"]["ok"]

    def test_pesos_no_suman_uno_falla(self):
        pesos = {"papa": 0.5, "pollo": 0.3, "tomate": 0.1}  # Σ = 0.9
        sol = evaluar_solidez(PRECIOS_OK, pesos, _indice(pesos=pesos))
        assert not sol["checks"]["pesos_suman_1"]["ok"]
        assert sol["veredicto"] == "REVISAR"

    def test_cobertura_incompleta_falla(self):
        # tomate ausente en 2 de 3 meses → cobertura 1/3 < 0.9.
        precios = {
            "2024-01": {"papa": 3.5, "pollo": 10.0, "tomate": 4.0},
            "2024-02": {"papa": 3.8, "pollo": 9.5},
            "2024-03": {"papa": 3.2, "pollo": 11.0},
        }
        sol = evaluar_solidez(precios, PESOS_OK, construir_indice(precios, PESOS_OK))
        assert not sol["checks"]["cobertura"]["ok"]
        assert sol["veredicto"] == "REVISAR"

    def test_precio_absurdo_falla(self):
        # pollo a S/ 5000/kg = error de unidad → fuera de rango.
        precios = {m: dict(v) for m, v in PRECIOS_OK.items()}
        precios["2024-02"]["pollo"] = 5000.0
        sol = evaluar_solidez(precios, PESOS_OK, construir_indice(precios, PESOS_OK))
        assert not sol["checks"]["precios_plausibles"]["ok"]
        assert sol["checks"]["precios_plausibles"]["fuera_rango"]
        assert sol["veredicto"] == "REVISAR"

    def test_precio_moderadamente_absurdo_falla_por_rango_por_producto(self):
        # papa a S/ 45/kg (≈10× lo normal): dentro del viejo blanket 0.1–100 pero
        # fuera del rango propio de la papa (#102 propuesta 1). Debe fallar.
        assert rango_plausible("papa")[1] < 45.0 < RANGO_PLAUSIBLE_DEFAULT[1]
        precios = {m: dict(v) for m, v in PRECIOS_OK.items()}
        precios["2024-02"]["papa"] = 45.0
        sol = evaluar_solidez(precios, PESOS_OK, construir_indice(precios, PESOS_OK))
        assert not sol["checks"]["precios_plausibles"]["ok"]
        assert sol["veredicto"] == "REVISAR"

    def test_pico_de_escasez_del_limon_sigue_plausible(self):
        # el limón trepa a S/ 18/kg en desabastecimientos: volatilidad real, no error.
        precios = {
            "2024-01": {"papa": 3.5, "pollo": 10.0, "limon": 4.0},
            "2024-02": {"papa": 3.8, "pollo": 9.5, "limon": 18.0},
            "2024-03": {"papa": 3.2, "pollo": 11.0, "limon": 6.0},
        }
        pesos = {"papa": 0.5, "pollo": 0.3, "limon": 0.2}
        sol = evaluar_solidez(precios, pesos, construir_indice(precios, pesos))
        assert sol["checks"]["precios_plausibles"]["ok"]
        assert sol["veredicto"] == "CANASTA SÓLIDA"

    def test_cada_producto_mvp_tiene_rango_propio(self):
        # los 6 slugs del MVP deben tener un rango calibrado (no caer al fallback).
        assert set(RANGOS_PLAUSIBLES_SOLKG) == {
            "papa", "cebolla", "huevo", "pollo", "tomate", "limon"
        }
        for lo, hi in RANGOS_PLAUSIBLES_SOLKG.values():
            assert 0 < lo < hi

    def test_hueco_es_aviso_no_falla(self):
        # salta de enero a marzo (falta febrero): continuidad falla pero sigue SÓLIDA.
        precios = {
            "2024-01": {"papa": 3.5, "pollo": 10.0, "tomate": 4.0},
            "2024-03": {"papa": 3.2, "pollo": 11.0, "tomate": 3.8},
        }
        sol = evaluar_solidez(precios, PESOS_OK, construir_indice(precios, PESOS_OK))
        assert not sol["checks"]["serie_continua"]["ok"]
        assert sol["checks"]["serie_continua"]["huecos"] == ["2024-02"]
        assert sol["veredicto"] == "CANASTA SÓLIDA"  # el hueco no bloquea


class TestContrasteIpcEsDescriptivo:
    def test_comparar_no_emite_veredicto(self):
        # El contraste con el IPC ya no produce un pass/fail: solo estadísticos.
        indice = _indice()
        ipc = {"2024-02": 0.5, "2024-03": 0.3}
        res = comparar(indice, ipc)
        assert "veredicto" not in res
        assert set(res) >= {"correlacion", "tracking_error", "meses_comunes", "suficiente"}
