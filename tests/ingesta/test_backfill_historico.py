"""Tests del backfill histórico de SISAP (#16): iteración de fechas, mapeo de
variable de mercado, parseo de un día (con fixture) y carga idempotente a bronze
(con conexión falsa, sin base)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from observatorio.carga.r2_a_supabase import COLUMNAS_SISAP
from observatorio.ingesta.sisap.backfill_historico import (
    _variable_de,
    cargar_bronze,
    iterar_fechas,
    pedir_dia,
)
from observatorio.ingesta.sisap.models import PrecioSisap

# ---------------------------------------------------------------------------
# iterar_fechas
# ---------------------------------------------------------------------------


class TestIterarFechas:
    def test_todos_los_dias_del_rango(self):
        fechas = list(iterar_fechas(date(2025, 1, 1), date(2025, 1, 4), None))
        assert fechas == [date(2025, 1, d) for d in (1, 2, 3, 4)]

    def test_muestreo_por_dia_del_mes(self):
        fechas = list(iterar_fechas(date(2025, 1, 1), date(2025, 2, 28), [4, 14]))
        assert fechas == [date(2025, 1, 4), date(2025, 1, 14), date(2025, 2, 4), date(2025, 2, 14)]

    def test_rango_de_un_solo_dia(self):
        uno = date(2024, 6, 10)
        assert list(iterar_fechas(uno, uno, None)) == [uno]

    def test_muestreo_sin_coincidencias_es_vacio(self):
        assert list(iterar_fechas(date(2025, 1, 1), date(2025, 1, 3), [20])) == []


# ---------------------------------------------------------------------------
# _variable_de
# ---------------------------------------------------------------------------


class TestVariableDe:
    def test_minorista(self):
        assert _variable_de("minorista") == "min_precio_prom"

    def test_mayorista(self):
        assert _variable_de("mayorista") == "may_precio_prom"

    def test_desconocido_falla(self):
        with pytest.raises(ValueError):
            _variable_de("informal")


# ---------------------------------------------------------------------------
# pedir_dia — parseo de un día usando el fixture HTML del scraper diario
# ---------------------------------------------------------------------------

FIXTURE = "sisap_lima_minorista_2026-05-15.html"


def _html_con_datos() -> str:
    ruta = Path(__file__).parent.parent / "fixtures" / "sisap" / FIXTURE
    return ruta.read_text(encoding="utf-8")


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


class TestPedirDia:
    def test_parsea_y_fija_fecha_y_tipo(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_html_con_datos())

        filas = pedir_dia(session, date(2024, 6, 10), "minorista", ["0104"])

        assert filas, "debería devolver filas del fixture"
        assert all(f.fecha_captura == "2024-06-10" for f in filas)
        assert all(f.tipo_mercado == "minorista" for f in filas)
        # sólo precios > 0 (se descartan las celdas vacías del HTML)
        assert all(f.precio_prom is not None and f.precio_prom > 0 for f in filas)

    def test_mensaje_de_error_devuelve_vacio(self):
        session = MagicMock()
        session.get.return_value = _mock_response("<p class=mensajeDeError>sobrecargado</p>")

        assert pedir_dia(session, date(2024, 6, 10), "minorista", ["0104"]) == []

    def test_error_de_red_devuelve_vacio(self):
        import requests

        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError("sin red")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("observatorio.ingesta.sisap.backfill_historico.time.sleep", lambda *_: None)
            assert pedir_dia(session, date(2024, 6, 10), "minorista", ["0104"]) == []


# ---------------------------------------------------------------------------
# cargar_bronze — idempotencia y orden de columnas, con conexión falsa
# ---------------------------------------------------------------------------


class _FakeCopy:
    def __init__(self):
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write_row(self, row):
        self.rows.append(row)


class _FakeCursor:
    def __init__(self):
        self.ejecutadas = []
        self.copy_obj = _FakeCopy()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.ejecutadas.append((sql, params))

    def copy(self, sql):
        self.ejecutadas.append((sql, None))
        return self.copy_obj


class _FakeConn:
    def __init__(self):
        self.cur = _FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


def _fila(fecha, producto, precio, tipo="minorista"):
    return PrecioSisap(
        fecha_captura=fecha, fuente="sisap_midagri", region="Lima", tipo_mercado=tipo,
        producto=producto, unidad_medida=None, equiv_kg_lt=None, precio_prom=precio,
    )


class TestCargarBronze:
    def test_lista_vacia_no_hace_nada(self):
        conn = _FakeConn()
        assert cargar_bronze(conn, []) == 0
        assert conn.commits == 0

    def test_borra_por_particion_y_copia_en_orden(self):
        conn = _FakeConn()
        filas = [
            _fila("2024-06-10", "Papa amarilla", 4.5),
            _fila("2024-06-10", "Cebolla cabeza roja", 3.0),
            _fila("2024-06-11", "Papa amarilla", 4.7),
        ]
        n = cargar_bronze(conn, filas)

        assert n == 3
        assert conn.commits == 1
        # un DELETE por cada (fecha, tipo) distinta → 2 particiones
        deletes = [e for e in conn.cur.ejecutadas if str(e[0]).startswith("DELETE")]
        assert len(deletes) == 2
        assert {d[1] for d in deletes} == {("2024-06-10", "minorista"), ("2024-06-11", "minorista")}
        # el COPY escribe en el orden exacto de COLUMNAS_SISAP
        cols = [c for c, _ in COLUMNAS_SISAP]
        assert conn.cur.copy_obj.rows[0] == [getattr(filas[0], c) for c in cols]
        assert len(conn.cur.copy_obj.rows) == 3
