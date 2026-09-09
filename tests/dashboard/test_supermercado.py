"""Tests del núcleo de la sección de supermercado (#152).

Lo que se prueba acá es la decisión metodológica: comparar cada producto contra
sí mismo, y reportar el desglose en vez de un único número — porque en el retail
la mayoría de los precios no se mueve y un promedio de 0 % esconde el movimiento
real.
"""

from __future__ import annotations

import pytest

from observatorio.dashboard.logica import (
    cambios_por_categoria,
    comparar_matcheado,
    descuento_pct,
    fecha_menos,
)


class TestCompararMatcheado:
    def test_todos_suben_lo_mismo(self):
        antes = {"a": 10.0, "b": 20.0, "c": 30.0}
        ahora = {"a": 11.0, "b": 22.0, "c": 33.0}
        n, subieron, bajaron, sin_cambio, media = comparar_matcheado(antes, ahora)
        assert (n, subieron, bajaron, sin_cambio) == (3, 3, 0, 0)
        assert media == pytest.approx(10.0)

    def test_un_producto_nuevo_y_caro_no_cuenta_como_inflacion(self):
        # LA trampa que este cálculo evita: el precio promedio del catálogo pasa
        # de 15 a 338 porque entró un producto carísimo, pero NINGÚN precio
        # cambió. La variación real es 0 %.
        antes = {"a": 10.0, "b": 20.0}
        ahora = {"a": 10.0, "b": 20.0, "premium": 985.0}
        n, subieron, bajaron, sin_cambio, media = comparar_matcheado(antes, ahora)
        assert n == 2 and sin_cambio == 2  # el nuevo queda fuera
        assert media == pytest.approx(0.0)

    def test_un_producto_barato_que_sale_del_catalogo_tampoco(self):
        antes = {"a": 10.0, "b": 20.0, "oferton": 1.0}
        ahora = {"a": 10.0, "b": 20.0}
        n, _, _, sin_cambio, media = comparar_matcheado(antes, ahora)
        assert n == 2 and sin_cambio == 2 and media == pytest.approx(0.0)

    def test_el_desglose_es_lo_informativo_cuando_el_neto_es_cero(self):
        # Caso real del retail: uno sube 10 %, otro baja 10 %, dos quedan igual.
        # El neto es ~0 % pero decir solo "0 %" ocultaría que la mitad se movió.
        antes = {"a": 10.0, "b": 10.0, "c": 10.0, "d": 10.0}
        ahora = {"a": 11.0, "b": 9.0, "c": 10.0, "d": 10.0}
        n, subieron, bajaron, sin_cambio, media = comparar_matcheado(antes, ahora)
        assert (n, subieron, bajaron, sin_cambio) == (4, 1, 1, 2)
        assert media == pytest.approx(0.0)

    def test_los_movimientos_minimos_no_cuentan_como_cambio(self):
        # Los precios se promedian sobre una semana: un día de oferta deja una
        # diferencia de decimales que no es un cambio de precio.
        antes = {"a": 10.0}
        ahora = {"a": 10.02}  # +0.2 %, por debajo del umbral de 0.5 %
        n, subieron, bajaron, sin_cambio, _ = comparar_matcheado(antes, ahora)
        assert (n, subieron, bajaron, sin_cambio) == (1, 0, 0, 1)

    def test_el_umbral_es_configurable(self):
        antes, ahora = {"a": 10.0}, {"a": 10.02}
        _, subieron, _, _, _ = comparar_matcheado(antes, ahora, umbral=0.001)
        assert subieron == 1

    def test_bajas_de_precio(self):
        antes = {"a": 10.0, "b": 10.0}
        ahora = {"a": 9.0, "b": 9.0}
        _, subieron, bajaron, _, media = comparar_matcheado(antes, ahora)
        assert (subieron, bajaron) == (0, 2)
        assert media == pytest.approx(-10.0)

    def test_sin_productos_en_comun(self):
        assert comparar_matcheado({"a": 10.0}, {"b": 10.0}) is None

    def test_diccionarios_vacios(self):
        assert comparar_matcheado({}, {}) is None

    def test_ignora_precios_no_positivos(self):
        # Un precio 0 haría una división por cero: se descarta la fila.
        antes = {"a": 0.0, "b": 10.0}
        ahora = {"a": 5.0, "b": 11.0}
        n, subieron, _, _, media = comparar_matcheado(antes, ahora)
        assert n == 1 and subieron == 1 and media == pytest.approx(10.0)


class TestCambiosPorCategoria:
    def _muchos(self, base: float, factor: float, n: int = 25):
        antes = {f"sku{i}": base for i in range(n)}
        ahora = {f"sku{i}": base * factor for i in range(n)}
        return antes, ahora

    def test_ordena_de_la_que_mas_subio_a_la_que_menos(self):
        a1, h1 = self._muchos(10.0, 1.05)
        a2, h2 = self._muchos(20.0, 1.20)
        a3, h3 = self._muchos(5.0, 0.90)
        res = cambios_por_categoria(
            {"Lácteos": a1, "Abarrotes": a2, "Frutas": a3},
            {"Lácteos": h1, "Abarrotes": h2, "Frutas": h3},
            {"Lácteos": 12.0, "Abarrotes": 15.0, "Frutas": 9.0},
        )
        assert [c.categoria for c in res] == ["Abarrotes", "Lácteos", "Frutas"]
        assert res[0].variacion_media == pytest.approx(20.0)
        assert res[-1].variacion_media == pytest.approx(-10.0)

    def test_porcentajes_del_desglose(self):
        antes = {f"sku{i}": 10.0 for i in range(20)}
        ahora = {**antes, "sku0": 12.0, "sku1": 12.0, "sku2": 8.0}
        res = cambios_por_categoria({"X": antes}, {"X": ahora}, {})
        assert res[0].pct_subieron == pytest.approx(10.0)  # 2 de 20
        assert res[0].pct_bajaron == pytest.approx(5.0)  # 1 de 20

    def test_descarta_las_categorias_con_muy_pocos_productos(self):
        # Panadería y Pastelería tiene 10 SKUs en la fuente real: con esa
        # cantidad el número salta por ruido.
        chica_antes, chica_ahora = self._muchos(10.0, 2.0, n=5)
        grande_antes, grande_ahora = self._muchos(10.0, 1.05, n=25)
        res = cambios_por_categoria(
            {"Panadería": chica_antes, "Abarrotes": grande_antes},
            {"Panadería": chica_ahora, "Abarrotes": grande_ahora},
            {},
        )
        assert [c.categoria for c in res] == ["Abarrotes"]

    def test_el_minimo_es_configurable(self):
        antes, ahora = self._muchos(10.0, 1.10, n=5)
        res = cambios_por_categoria({"X": antes}, {"X": ahora}, {}, minimo_productos=3)
        assert len(res) == 1 and res[0].n_productos == 5

    def test_arrastra_el_precio_tipico_para_dar_contexto(self):
        antes, ahora = self._muchos(10.0, 1.10)
        res = cambios_por_categoria({"X": antes}, {"X": ahora}, {"X": 7.5})
        assert res[0].precio_tipico == 7.5

    def test_categoria_ausente_en_la_ventana_actual_se_omite(self):
        antes, _ = self._muchos(10.0, 1.10)
        assert cambios_por_categoria({"X": antes}, {}, {}) == []

    def test_porcentajes_con_cero_productos_no_dividen_por_cero(self):
        from observatorio.dashboard.logica import CambioCategoria

        vacia = CambioCategoria("X", 0, 0, 0, 0, 0.0, 0.0)
        assert vacia.pct_subieron == 0.0 and vacia.pct_bajaron == 0.0


class TestDescuento:
    def test_descuento_normal(self):
        assert descuento_pct(75.0, 100.0) == pytest.approx(25.0)

    def test_sin_descuento_devuelve_none(self):
        assert descuento_pct(100.0, 100.0) is None

    def test_precio_mayor_que_lista_no_es_descuento(self):
        assert descuento_pct(120.0, 100.0) is None

    def test_lista_invalida(self):
        assert descuento_pct(50.0, 0.0) is None
        assert descuento_pct(50.0, -1.0) is None


class TestFechaMenos:
    def test_resta_dias(self):
        assert fecha_menos("2026-09-08", 30) == "2026-08-09"

    def test_cruza_el_anio(self):
        assert fecha_menos("2026-01-05", 10) == "2025-12-26"

    def test_cero_dias(self):
        assert fecha_menos("2026-09-08", 0) == "2026-09-08"
