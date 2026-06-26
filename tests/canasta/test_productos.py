"""Tests del mapeo de códigos p601a → productos del MVP (issue #19)."""

from observatorio.canasta.productos import (
    GRUPO_A_PRODUCTO,
    MVP_GRUPOS,
    PRODUCTOS_MVP,
    mapear_producto,
    normalizar_codigo,
)


class TestNormalizarCodigo:
    def test_entero_se_rellena_a_4_digitos(self):
        assert normalizar_codigo(501) == "0501"
        assert normalizar_codigo(700) == "0700"

    def test_string_se_respeta(self):
        assert normalizar_codigo("3201") == "3201"
        assert normalizar_codigo("0507") == "0507"

    def test_float_se_trunca(self):
        assert normalizar_codigo(700.0) == "0700"

    def test_invalidos_son_none(self):
        assert normalizar_codigo(None) is None
        assert normalizar_codigo("abc") is None
        assert normalizar_codigo("") is None


class TestMapearProducto:
    def test_cada_grupo_mapea_a_su_producto(self):
        # El código agregado XX00 de cada grupo cae en su producto.
        for producto, grupo in MVP_GRUPOS.items():
            assert mapear_producto(int(grupo + "00")) == producto

    def test_presentaciones_frescas(self):
        assert mapear_producto(501) == "papa"  # papa amarilla
        assert mapear_producto(701) == "huevo"  # huevo a granel
        assert mapear_producto(901) == "pollo"  # pollo eviscerado
        assert mapear_producto(3201) == "cebolla"
        assert mapear_producto(3301) == "tomate"
        assert mapear_producto(3801) == "limon"

    def test_papa_seca_excluida(self):
        # 0507 cae en grupo 05 pero es procesado → no es papa fresca.
        assert mapear_producto("0507") is None

    def test_codigos_de_otros_grupos_no_mapean(self):
        assert mapear_producto(1804) is None  # harina (grupo 18)
        assert mapear_producto(3010) is None  # salsa de tomate (grupo 30)
        assert mapear_producto(1107) is None  # pollo en conserva (grupo 11)

    def test_invalido_es_none(self):
        assert mapear_producto(None) is None
        assert mapear_producto("xx") is None

    def test_coherencia_estructuras(self):
        assert set(PRODUCTOS_MVP) == set(MVP_GRUPOS)
        assert GRUPO_A_PRODUCTO == {g: p for p, g in MVP_GRUPOS.items()}
