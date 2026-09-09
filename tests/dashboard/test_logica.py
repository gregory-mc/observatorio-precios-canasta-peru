"""Tests del núcleo del dashboard (#37): índice, variación y semáforo.

Sin streamlit y sin base: `logica.py` solo recibe y devuelve estructuras simples.
"""

from __future__ import annotations

import pytest

from observatorio.dashboard.logica import (
    AMBAR,
    NACIONAL,
    PROPIO,
    PROXY,
    ROJO,
    SIN_DATO,
    TODAS,
    UMBRAL_ALERTA,
    UMBRAL_ESTABLE,
    VERDE,
    clasificar,
    evaluar_semaforo,
    indice_canasta,
    mes_anterior,
    mes_legible,
    resolver_ambito,
)

_PESOS = {"papa": 0.5, "pollo": 0.5}


def _indice(precios_por_mes: dict[str, dict[str, float]]):
    return indice_canasta(precios_por_mes, _PESOS)


class TestMesAnterior:
    def test_mes_corriente(self):
        assert mes_anterior("2026-08") == "2026-07"

    def test_cruza_el_anio(self):
        assert mes_anterior("2026-01") == "2025-12"

    def test_conserva_el_cero_a_la_izquierda(self):
        assert mes_anterior("2026-10") == "2026-09"


class TestClasificar:
    @pytest.mark.parametrize("var", [-9.0, -0.5, 0.0, UMBRAL_ESTABLE - 0.1])
    def test_estable_o_bajando_es_verde(self, var):
        # Direccional a propósito: una baja fuerte no es una alarma para el consumidor.
        assert clasificar(var) == VERDE

    @pytest.mark.parametrize(
        "var", [UMBRAL_ESTABLE, (UMBRAL_ESTABLE + UMBRAL_ALERTA) / 2, UMBRAL_ALERTA - 0.1]
    )
    def test_suba_moderada_es_ambar(self, var):
        assert clasificar(var) == AMBAR

    @pytest.mark.parametrize("var", [UMBRAL_ALERTA, UMBRAL_ALERTA + 5])
    def test_alza_fuerte_es_roja(self, var):
        assert clasificar(var) == ROJO

    def test_los_bordes_caen_del_lado_mas_severo(self):
        assert clasificar(UMBRAL_ESTABLE) == AMBAR
        assert clasificar(UMBRAL_ALERTA) == ROJO

    def test_sin_variacion_no_hay_veredicto(self):
        assert clasificar(None) == SIN_DATO


class TestSemaforo:
    def test_los_umbrales_conservan_su_significado_estadistico(self):
        # Verde = mes típico, rojo = quintil extremo. Si alguien mueve los
        # umbrales sin recalibrar, esto no lo detecta — pero sí detecta que se
        # inviertan o se vuelvan absurdos.
        assert 0 < UMBRAL_ESTABLE < UMBRAL_ALERTA < 20

    def test_compara_el_ultimo_mes_cerrado(self):
        idx = _indice(
            {
                "2026-06": {"papa": 2.0, "pollo": 10.0},
                "2026-07": {"papa": 2.0, "pollo": 10.0},
                "2026-08": {"papa": 2.2, "pollo": 11.0},  # +10 %
            }
        )
        sem = evaluar_semaforo(idx, mes_actual="2026-09")
        assert (sem.mes, sem.mes_previo) == ("2026-08", "2026-07")
        assert sem.variacion == pytest.approx(10.0)
        assert sem.nivel == ROJO

    def test_descarta_el_mes_en_curso_por_parcial(self):
        # Septiembre existe pero corre: su promedio son unos pocos días y su
        # variación sería un artefacto, no una señal.
        idx = _indice(
            {
                "2026-07": {"papa": 2.0, "pollo": 10.0},
                "2026-08": {"papa": 2.0, "pollo": 10.0},
                "2026-09": {"papa": 9.0, "pollo": 40.0},
            }
        )
        sem = evaluar_semaforo(idx, mes_actual="2026-09")
        assert sem.mes == "2026-08"
        assert sem.variacion == pytest.approx(0.0)
        assert sem.nivel == VERDE

    def test_un_hueco_de_datos_no_se_reporta_como_variacion_mensual(self):
        # El caso real de SISAP: no hay 2026-01 a 2026-05. Comparar junio contra
        # diciembre y llamarlo "mensual" sería mentir; se declara sin dato.
        idx = _indice(
            {
                "2025-12": {"papa": 2.0, "pollo": 10.0},
                "2026-06": {"papa": 3.0, "pollo": 15.0},  # +50 % en seis meses
            }
        )
        sem = evaluar_semaforo(idx, mes_actual="2026-07")
        assert sem.nivel == SIN_DATO
        assert sem.variacion is None
        assert sem.mes == "2026-06" and sem.mes_previo == "2026-05"
        assert "2026-05" in sem.motivo

    def test_sin_meses_cerrados_no_inventa_veredicto(self):
        idx = _indice({"2026-09": {"papa": 2.0, "pollo": 10.0}})
        sem = evaluar_semaforo(idx, mes_actual="2026-09")
        assert sem.nivel == SIN_DATO and sem.mes is None

    def test_indice_vacio(self):
        sem = evaluar_semaforo([], mes_actual="2026-09")
        assert sem.nivel == SIN_DATO

    def test_pondera_por_la_canasta_y_no_por_el_promedio_simple(self):
        # papa 90 % / pollo 10 %: una suba del 10 % en la papa pesa mucho más que
        # la misma suba en el pollo. Un promedio simple daría lo mismo en los dos.
        precios = {
            "2026-07": {"papa": 2.0, "pollo": 10.0},
            "2026-08": {"papa": 2.2, "pollo": 10.0},
        }
        sesgado = indice_canasta(precios, {"papa": 0.9, "pollo": 0.1})
        assert evaluar_semaforo(sesgado, mes_actual="2026-09").variacion == pytest.approx(9.0)

        precios_pollo = {
            "2026-07": {"papa": 2.0, "pollo": 10.0},
            "2026-08": {"papa": 2.0, "pollo": 11.0},
        }
        otro = indice_canasta(precios_pollo, {"papa": 0.9, "pollo": 0.1})
        assert evaluar_semaforo(otro, mes_actual="2026-09").variacion == pytest.approx(1.0)


class TestResolverAmbito:
    """Con qué precios se valoriza la canasta de un departamento sin precios propios."""

    _NOMBRES = {"15": "Lima", "01": "Amazonas"}

    def test_depto_con_precios_propios_los_usa_y_no_aclara_nada(self):
        amb = resolver_ambito("15", deptos_con_precio={"15"}, tiene_nacional=False)
        assert (amb.clave, amb.tipo, amb.nota) == ("15", PROPIO, None)

    def test_fuente_nacional_cae_a_los_precios_nacionales(self):
        # marketplace guarda cod_departamento en NULL: no desagrega.
        amb = resolver_ambito("15", deptos_con_precio=set(), tiene_nacional=True)
        assert (amb.clave, amb.tipo) == ("nacional", NACIONAL)
        assert amb.nota

    def test_sin_precios_propios_ni_nacionales_usa_los_que_haya(self):
        # El caso real de Amazonas en SISAP: la fuente solo cubre Lima. Antes esto
        # pedía precios "nacionales", que en SISAP no existen, y la página decía
        # "no hay datos" escondiendo que la canasta del departamento sí existe.
        amb = resolver_ambito(
            "01", deptos_con_precio={"15"}, tiene_nacional=False, nombres=self._NOMBRES
        )
        assert (amb.clave, amb.tipo) == (TODAS, PROXY)
        assert "Lima" in amb.nota

    def test_la_nota_nombra_los_deptos_disponibles(self):
        amb = resolver_ambito(
            "01", deptos_con_precio={"15", "04"}, tiene_nacional=False,
            nombres={"15": "Lima", "04": "Arequipa"},
        )
        assert "Arequipa" in amb.nota and "Lima" in amb.nota

    def test_sin_ninguna_cobertura_lo_dice_en_vez_de_romper(self):
        amb = resolver_ambito("01", deptos_con_precio=set(), tiene_nacional=False)
        assert amb.tipo == PROXY and "ninguno" in amb.nota


class TestMesLegible:
    """Los códigos ISO de mes son de la base, no del lector."""

    def test_formato_castellano(self):
        assert mes_legible("2026-08") == "agosto de 2026"

    def test_enero_y_diciembre(self):
        assert mes_legible("2026-01") == "enero de 2026"
        assert mes_legible("2025-12") == "diciembre de 2025"

    def test_sin_mes(self):
        assert mes_legible(None) == "—"
        assert mes_legible("") == "—"

    def test_valor_raro_se_devuelve_tal_cual_en_vez_de_romper(self):
        assert mes_legible("no-es-un-mes") == "no-es-un-mes"
        assert mes_legible("2026-13") == "2026-13"
