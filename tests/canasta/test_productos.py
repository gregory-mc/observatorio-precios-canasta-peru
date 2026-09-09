"""Tests del mapeo de códigos p601a → productos de la canasta (#19, ampliado en #155)."""

from observatorio.canasta.productos import (
    CANASTA_GRUPOS,
    EXCLUIDOS,
    GRUPO_A_PRODUCTO,
    MVP_GRUPOS,
    PRODUCTOS_MVP,
    es_agregado,
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
    def test_el_agregado_de_cada_grupo_NO_mapea(self):
        # Antes se asumía que XX00 era una línea de compra más y se sumaba junto
        # a las presentaciones. Verificado contra la ENAHO 2023: en 22,242 de
        # 22,242 hogares con arroz, XX00 es exactamente la suma de las
        # específicas — sumar los dos duplicaba todo. Ver #155.
        for grupo in CANASTA_GRUPOS.values():
            assert mapear_producto(int(grupo + "00")) is None

    def test_cada_grupo_mapea_por_sus_presentaciones(self):
        for producto, grupo in CANASTA_GRUPOS.items():
            assert mapear_producto(int(grupo + "01")) == producto

    def test_presentaciones_frescas(self):
        assert mapear_producto(501) == "papa"  # papa amarilla
        assert mapear_producto(701) == "huevo"  # huevo a granel
        assert mapear_producto(901) == "pollo"  # pollo eviscerado
        assert mapear_producto(3201) == "cebolla"
        assert mapear_producto(3301) == "tomate"
        assert mapear_producto(3801) == "limon"

    def test_productos_nuevos(self):
        assert mapear_producto(304) == "arroz"  # arroz extra a granel
        assert mapear_producto(801) == "carne_res"  # res bistec
        assert mapear_producto(2001) == "pescado"  # jurel
        assert mapear_producto(401) == "leche"  # leche evaporada
        assert mapear_producto(602) == "azucar"  # azúcar rubia
        assert mapear_producto(2303) == "aceite"  # aceite vegetal envasado
        assert mapear_producto(3101) == "menestras"  # lenteja

    def test_papa_seca_excluida(self):
        # 0507 cae en grupo 05 pero es procesado → no es papa fresca. La
        # exclusión recién funciona al no sumar el agregado: 0500 la contenía.
        assert mapear_producto("0507") is None

    def test_exclusiones_de_los_grupos_nuevos(self):
        assert mapear_producto("0406") is None  # leche de soya
        assert mapear_producto("0409") is None  # leche chocolatada
        assert mapear_producto("0603") is None  # endulzante stevia
        assert mapear_producto("2306") is None  # manteca de chancho
        assert mapear_producto("0809") is None  # cuy EN PIE (animal vivo)
        assert mapear_producto("0812") is None  # carne de mono

    def test_lo_que_si_entra_en_carnes_rojas(self):
        # Res y chancho son el grueso; cordero y alpaca son carne roja de
        # mercado. Lo que se excluye es el animal vivo y la carne de monte.
        for codigo in (801, 805, 807, 806, 808):
            assert mapear_producto(codigo) == "carne_res"

    def test_codigos_de_otros_grupos_no_mapean(self):
        assert mapear_producto(1804) is None  # harina (grupo 18)
        assert mapear_producto(3010) is None  # salsa de tomate (grupo 30)
        assert mapear_producto(1107) is None  # pollo en conserva (grupo 11)

    def test_invalido_es_none(self):
        assert mapear_producto(None) is None
        assert mapear_producto("xx") is None

    def test_coherencia_estructuras(self):
        assert set(PRODUCTOS_MVP) == set(MVP_GRUPOS)
        assert GRUPO_A_PRODUCTO == {g: p for p, g in CANASTA_GRUPOS.items()}
        assert MVP_GRUPOS is CANASTA_GRUPOS  # alias retrocompatible

    def test_la_canasta_tiene_13_productos(self):
        assert len(CANASTA_GRUPOS) == 13
        assert len(set(CANASTA_GRUPOS.values())) == 13  # un grupo por producto

    def test_ninguna_exclusion_es_un_agregado(self):
        # Excluir un XX00 sería redundante (ya se descarta) y confundiría.
        assert not [c for c in EXCLUIDOS if es_agregado(c)]

    def test_las_exclusiones_caen_en_grupos_de_la_canasta(self):
        # Una exclusión de un grupo ajeno no haría nada y sería letra muerta.
        grupos = set(CANASTA_GRUPOS.values())
        assert all(c[:2] in grupos for c in EXCLUIDOS)


class TestEsAgregado:
    def test_agregados(self):
        assert es_agregado("0300") and es_agregado("0900")

    def test_presentaciones(self):
        assert not es_agregado("0301") and not es_agregado("0907")
