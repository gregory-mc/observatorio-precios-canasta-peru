"""Tests del parser de la serie diaria SENAMHI (issue #14, paso 2).

Sin red: construyen HTML sintético con la misma forma Highcharts que devuelve
``map_red_graf.php`` (xAxis.categories + series precip/tmax/tmin) y verifican el
alineamiento por fecha, el manejo de ``null``, el descarte de días vacíos y las
estaciones sin temperatura.
"""

from __future__ import annotations

from observatorio.ingesta.senamhi.models import Estacion
from observatorio.ingesta.senamhi.parser import parsear_serie

# Nombre de la serie de precipitación tal cual viene (ó escapada ó).
_PRECIP = r"Precipitación"

_EST = Estacion(
    cod="105053", cod_old="", nombre="SALLIQUE", categoria="CO", tipo="M",
    estado="REAL", lat=-5.64, lon=-79.35, region="piura_lambayeque",
)


def _html(categories, series):
    """Arma un HTML Highcharts mínimo con categories + series {name, data}."""
    cats = "categories: [" + ",".join(f"'{c}'" for c in categories) + ",]"
    bloques = []
    for name, data in series:
        arr = ",".join("null" if v is None else str(v) for v in data)
        bloques.append("{ name: '" + name + "', type: 'column', data: [" + arr + ",] }")
    return "<script>xAxis: [{" + cats + "}], series: [" + ",".join(bloques) + "]</script>"


class TestParsearSerie:
    def test_alinea_fecha_con_las_tres_variables(self):
        html = _html(
            ["2026-08-01", "2026-08-02", "2026-08-03"],
            [
                (_PRECIP, [0.0, None, 2.5]),
                ("Temp. max", [29.8, None, None]),
                ("Temp. min", [15.4, None, 12.0]),
            ],
        )
        filas = parsear_serie(html, _EST)
        # date2 (2026-08-02) es todo-null -> se descarta; quedan 2 filas.
        assert [f.fecha_captura for f in filas] == ["2026-08-01", "2026-08-03"]
        f0, f1 = filas
        assert (f0.precip_mm, f0.temp_max_c, f0.temp_min_c) == (0.0, 29.8, 15.4)
        assert (f1.precip_mm, f1.temp_max_c, f1.temp_min_c) == (2.5, None, 12.0)

    def test_completa_metadata_de_estacion(self):
        html = _html(["2026-08-01"], [(_PRECIP, [1.0])])
        f = parsear_serie(html, _EST)[0]
        assert f.cod_estacion == "105053"
        assert f.nombre == "SALLIQUE"
        assert f.region == "piura_lambayeque"
        assert f.latitud == -5.64
        assert f.fuente == "senamhi"

    def test_estacion_sin_temperatura(self):
        # Estación pluviométrica: solo serie de precipitación.
        html = _html(["2026-08-01", "2026-08-02"], [(_PRECIP, [0.0, 3.2])])
        filas = parsear_serie(html, _EST)
        assert len(filas) == 2
        assert all(f.temp_max_c is None and f.temp_min_c is None for f in filas)
        assert [f.precip_mm for f in filas] == [0.0, 3.2]

    def test_descarta_dias_totalmente_vacios(self):
        html = _html(
            ["2026-08-01", "2026-08-02"],
            [(_PRECIP, [None, 1.0]), ("Temp. max", [None, 2.0]), ("Temp. min", [None, 3.0])],
        )
        filas = parsear_serie(html, _EST)
        assert [f.fecha_captura for f in filas] == ["2026-08-02"]

    def test_data_mas_corta_que_categories_no_rompe(self):
        # Defensivo: si una serie trae menos puntos, se rellena con None.
        html = _html(
            ["2026-08-01", "2026-08-02", "2026-08-03"],
            [(_PRECIP, [1.0, 2.0, 3.0]), ("Temp. min", [10.0])],
        )
        filas = parsear_serie(html, _EST)
        assert len(filas) == 3
        assert filas[0].temp_min_c == 10.0
        assert filas[2].temp_min_c is None

    def test_sin_categories_devuelve_vacio(self):
        assert parsear_serie("<script>sin datos</script>", _EST) == []
