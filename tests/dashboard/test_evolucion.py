"""Tests del núcleo de la página de evolución (#38): ventanas, huecos, pronóstico."""

from __future__ import annotations

from datetime import date

from observatorio.dashboard.logica import (
    DIAS_HUECO,
    VENTANAS,
    desde_ventana,
    insertar_huecos,
    proxima_prediccion,
)


class TestVentanas:
    def test_resta_los_dias_de_la_etiqueta(self):
        assert desde_ventana("Últimos 90 días", date(2026, 9, 5)) == date(2026, 6, 7)

    def test_todo_el_historico_no_pone_corte(self):
        assert desde_ventana("Todo el histórico", date(2026, 9, 5)) is None

    def test_etiqueta_desconocida_no_corta(self):
        assert desde_ventana("inventada", date(2026, 9, 5)) is None

    def test_todas_las_ventanas_del_selector_resuelven(self):
        hoy = date(2026, 9, 5)
        for etiqueta in VENTANAS:
            desde = desde_ventana(etiqueta, hoy)
            assert desde is None or desde < hoy


class TestInsertarHuecos:
    def test_serie_continua_no_se_toca(self):
        serie = [(date(2026, 9, d), 2.0) for d in (1, 2, 3)]
        assert insertar_huecos(serie) == serie

    def test_la_cadencia_normal_de_sisap_no_es_hueco(self):
        # Fin de semana largo: 4 días sin dato es cómo publica la fuente.
        serie = [(date(2026, 9, 4), 2.0), (date(2026, 9, 8), 2.1)]
        assert insertar_huecos(serie) == serie

    def test_un_hueco_real_corta_la_linea(self):
        # El caso de SISAP: de 2025-12 salta a 2026-06. Unir esos dos puntos con
        # una recta aparentaría cinco meses de dato interpolado.
        serie = [(date(2025, 12, 28), 2.0), (date(2026, 6, 2), 3.0)]
        salida = insertar_huecos(serie)
        assert len(salida) == 3
        assert salida[1] == (date(2025, 12, 29), None)
        assert salida[0] == serie[0] and salida[2] == serie[1]

    def test_varios_huecos(self):
        serie = [
            (date(2026, 1, 1), 1.0),
            (date(2026, 3, 1), 2.0),
            (date(2026, 3, 2), 2.1),
            (date(2026, 6, 1), 3.0),
        ]
        nulos = [f for f, v in insertar_huecos(serie) if v is None]
        assert len(nulos) == 2

    def test_ordena_antes_de_evaluar(self):
        serie = [(date(2026, 9, 3), 3.0), (date(2026, 9, 1), 1.0), (date(2026, 9, 2), 2.0)]
        assert [v for _, v in insertar_huecos(serie)] == [1.0, 2.0, 3.0]

    def test_serie_vacia(self):
        assert insertar_huecos([]) == []

    def test_un_solo_punto(self):
        assert insertar_huecos([(date(2026, 9, 1), 2.0)]) == [(date(2026, 9, 1), 2.0)]

    def test_el_umbral_es_configurable(self):
        serie = [(date(2026, 9, 1), 1.0), (date(2026, 9, 6), 2.0)]  # 5 días
        assert insertar_huecos(serie, dias_hueco=3) != serie
        assert insertar_huecos(serie, dias_hueco=DIAS_HUECO) == serie


class TestProximaPrediccion:
    _PREDS = [
        (date(2026, 8, 29), 2.0, 1.9, 2.1),
        (date(2026, 9, 6), 2.2, 2.0, 2.4),
        (date(2026, 9, 11), 2.3, 2.0, 2.6),
    ]

    def test_toma_el_primer_punto_futuro(self):
        prox = proxima_prediccion(self._PREDS, hoy=date(2026, 9, 5))
        assert prox.fecha == date(2026, 9, 6)
        assert (prox.valor, prox.inferior, prox.superior) == (2.2, 2.0, 2.4)

    def test_ignora_los_puntos_ya_vencidos(self):
        # Las corridas son semanales con horizonte de 14 días: una corrida vieja
        # trae puntos pasados, y mostrarlos como "lo que viene" sería engañoso.
        prox = proxima_prediccion(self._PREDS, hoy=date(2026, 9, 10))
        assert prox.fecha == date(2026, 9, 11)

    def test_horizonte_agotado_no_devuelve_nada(self):
        assert proxima_prediccion(self._PREDS, hoy=date(2026, 9, 30)) is None

    def test_hoy_no_cuenta_como_futuro(self):
        prox = proxima_prediccion(self._PREDS, hoy=date(2026, 9, 6))
        assert prox.fecha == date(2026, 9, 11)

    def test_sin_predicciones(self):
        assert proxima_prediccion([], hoy=date(2026, 9, 5)) is None

    def test_no_asume_que_vienen_ordenadas(self):
        prox = proxima_prediccion(list(reversed(self._PREDS)), hoy=date(2026, 9, 5))
        assert prox.fecha == date(2026, 9, 6)
