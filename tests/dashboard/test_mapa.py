"""Tests del núcleo del mapa (#39): semáforo y peso por departamento."""

from __future__ import annotations

import pytest

from observatorio.dashboard.logica import (
    AMBAR,
    ROJO,
    SIN_DATO,
    peso_por_departamento,
    semaforo_por_departamento,
)

# Mismos precios para todos los departamentos: es la situación real (solo Lima
# tiene precios propios). Papa +20 %, pollo estable.
_PRECIOS = {
    "2026-07": {"papa": 2.0, "pollo": 10.0},
    "2026-08": {"papa": 2.4, "pollo": 10.0},
}
_PESOS = {
    "15": {"papa": 0.2, "pollo": 0.8},  # Lima: come mucho pollo
    "01": {"papa": 0.8, "pollo": 0.2},  # Amazonas: come mucha papa
    "04": {"papa": 0.5, "pollo": 0.5},
}


class TestSemaforoPorDepartamento:
    def test_la_composicion_es_lo_que_diferencia_a_los_departamentos(self):
        # Con los MISMOS precios, el departamento que consume más papa sufre más
        # la suba de la papa. Eso es exactamente lo que el mapa muestra —
        # estructura de consumo, no diferencias de precio.
        sems = semaforo_por_departamento(_PRECIOS, _PESOS, mes_actual="2026-09")
        assert sems["01"].variacion == pytest.approx(16.0)  # 0.8 × 20 %
        assert sems["04"].variacion == pytest.approx(10.0)  # 0.5 × 20 %
        assert sems["15"].variacion == pytest.approx(4.0)  # 0.2 × 20 %

    def test_clasifica_cada_departamento_por_su_cuenta(self):
        # Los mismos precios dan tres veredictos distintos según la canasta local.
        sems = semaforo_por_departamento(_PRECIOS, _PESOS, mes_actual="2026-09")
        assert sems["01"].nivel == ROJO  # 16 % ≥ 7.5
        assert sems["04"].nivel == ROJO  # 10 % ≥ 7.5
        assert sems["15"].nivel == AMBAR  # 4 %: entre 3 y 7.5

    def test_cubre_los_departamentos_con_pesos(self):
        sems = semaforo_por_departamento(_PRECIOS, _PESOS, mes_actual="2026-09")
        assert set(sems) == {"15", "01", "04"}

    def test_departamento_sin_pesos_se_omite(self):
        sems = semaforo_por_departamento(_PRECIOS, {**_PESOS, "99": {}}, mes_actual="2026-09")
        assert "99" not in sems

    def test_hereda_el_cuidado_de_los_huecos(self):
        # Meses no consecutivos: no hay variación mensual y el mapa se queda sin
        # valores en vez de pintar un salto de seis meses como si fuera mensual.
        precios = {
            "2025-12": {"papa": 2.0, "pollo": 10.0},
            "2026-06": {"papa": 3.0, "pollo": 15.0},
        }
        sems = semaforo_por_departamento(precios, _PESOS, mes_actual="2026-07")
        assert all(s.nivel == SIN_DATO for s in sems.values())
        assert all(s.variacion is None for s in sems.values())

    def test_sin_precios_no_rompe(self):
        sems = semaforo_por_departamento({}, _PESOS, mes_actual="2026-09")
        assert all(s.nivel == SIN_DATO for s in sems.values())


class TestPesoPorDepartamento:
    def test_devuelve_porcentajes(self):
        assert peso_por_departamento(_PESOS, "papa") == {"15": 20.0, "01": 80.0, "04": 50.0}

    def test_omite_los_departamentos_sin_ese_producto(self):
        pesos = {**_PESOS, "05": {"pollo": 1.0}}
        assert "05" not in peso_por_departamento(pesos, "papa")

    def test_producto_inexistente_da_vacio(self):
        assert peso_por_departamento(_PESOS, "quinua") == {}
