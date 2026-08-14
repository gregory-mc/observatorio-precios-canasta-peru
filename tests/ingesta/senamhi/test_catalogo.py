"""Tests del catálogo de estaciones SENAMHI y su curación (issue #14).

No hacen red: usan un HTML de mapa sintético con ``var PruebaTest`` que cubre los
casos de curación (meteorológica vs hidrológica, fresca vs diferida, dentro vs
fuera de región) y una entrada con comillas simples para ejercitar el fallback de
parseo tolerante.
"""

from __future__ import annotations

import json

from observatorio.ingesta.senamhi import catalogo
from observatorio.ingesta.senamhi.models import Estacion


def _est(cod, ico, estado, lat, lon, *, cate="CO", nom="X", cod_old=""):
    return {
        "nom": nom, "cate": cate, "lat": lat, "lon": lon,
        "ico": ico, "cod": cod, "cod_old": cod_old, "estado": estado,
    }


# Estaciones de prueba (coordenadas reales aproximadas):
#  - 111111: meteorológica AUTOMATICA en Lima            -> se conserva
#  - 222222: HIDROLÓGICA en Lima                         -> se descarta (ico H)
#  - 333333: meteorológica DIFERIDO en Lima              -> se descarta (rezagada)
#  - 444444: meteorológica REAL en Ica                   -> se conserva
#  - 555555: meteorológica AUTOMATICA fuera de región    -> se descarta (bbox)
_VALIDAS = [
    _est("111111", "M", "AUTOMATICA", -12.07, -77.04, cate="EMA", nom="CAMPO DE MARTE"),
    _est("222222", "H", "REAL", -12.00, -76.90, cate="HLM", nom="PUENTE RIO"),
    _est("333333", "M", "DIFERIDO", -12.10, -77.00, nom="VIEJA LIMA"),
    _est("444444", "M", "REAL", -14.05, -75.73, cate="EMA", nom="SAN CAMILO"),
    _est("555555", "M", "AUTOMATICA", -3.78, -73.30, cate="EMA", nom="IQUITOS"),
]

# Entrada con comillas simples (JSON inválido) en Lima, M/REAL -> ejercita el
# fallback de parseo por regex de campo.
_RARA = (
    "{'nom':'RARO','cate':'CO','lat':-12.05,'lon':-77.02,"
    "'ico':'M','cod':'666666','cod_old':'','estado':'REAL'}"
)

_ARRAY = "[" + ",".join([*(json.dumps(e) for e in _VALIDAS), _RARA]) + "]"
_HTML_MAPA = f"<html><head><script>var PruebaTest = {_ARRAY};</script></head><body></body></html>"


class TestParseoCatalogo:
    def test_parsea_todas_las_estaciones(self):
        ests = catalogo.parsear_catalogo(_HTML_MAPA)
        assert len(ests) == 6
        assert all(isinstance(e, Estacion) for e in ests)

    def test_lat_lon_son_float(self):
        ests = {e.cod: e for e in catalogo.parsear_catalogo(_HTML_MAPA)}
        assert ests["111111"].lat == -12.07
        assert ests["111111"].lon == -77.04

    def test_fallback_parsea_entrada_con_comillas_simples(self):
        # La entrada 'raro' rompe json.loads (comillas simples) -> regex de campo.
        ests = {e.cod: e for e in catalogo.parsear_catalogo(_HTML_MAPA)}
        assert "666666" in ests
        assert ests["666666"].nombre == "RARO"
        assert ests["666666"].tipo == "M"

    def test_sin_array_lanza(self):
        import pytest

        with pytest.raises(ValueError):
            catalogo.parsear_catalogo("<html>sin catalogo</html>")


class TestCuracion:
    def test_conserva_solo_meteo_fresca_en_region(self):
        curadas = catalogo.curar(catalogo.parsear_catalogo(_HTML_MAPA))
        cods = {e.cod for e in curadas}
        # Conserva Lima automática (111111), Ica real (444444) y la 'raro' (666666).
        assert cods == {"111111", "444444", "666666"}

    def test_descarta_hidrologica(self):
        curadas = catalogo.curar(catalogo.parsear_catalogo(_HTML_MAPA))
        assert "222222" not in {e.cod for e in curadas}

    def test_descarta_diferida(self):
        curadas = catalogo.curar(catalogo.parsear_catalogo(_HTML_MAPA))
        assert "333333" not in {e.cod for e in curadas}

    def test_descarta_fuera_de_region(self):
        curadas = catalogo.curar(catalogo.parsear_catalogo(_HTML_MAPA))
        assert "555555" not in {e.cod for e in curadas}  # Iquitos, fuera de bbox

    def test_anota_region(self):
        curadas = {e.cod: e for e in catalogo.curar(catalogo.parsear_catalogo(_HTML_MAPA))}
        assert curadas["111111"].region == "lima"
        assert curadas["444444"].region == "ica"


class TestRegionProductora:
    def test_lima_dentro(self):
        assert catalogo.region_productora(-12.07, -77.04) == "lima"

    def test_ica_dentro(self):
        assert catalogo.region_productora(-14.05, -75.73) == "ica"

    def test_fuera_de_todo(self):
        assert catalogo.region_productora(-3.78, -73.30) is None  # Iquitos
