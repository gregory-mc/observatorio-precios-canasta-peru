"""Tests de la API REST (issue #43).

Sin base: monkeypatchean ``observatorio.api.db.consultar`` para capturar el SQL y
los parámetros que arma cada endpoint y devolver filas canned. Verifican el
armado del WHERE/params por filtro, la forma de la respuesta y la validación.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from observatorio.api import db  # noqa: E402
from observatorio.api.main import crear_app  # noqa: E402

_FILA_PRECIO = {
    "fecha_captura": "2026-08-17",
    "fuente": "sisap_minorista",
    "cod_departamento": "15",
    "producto": "papa blanca",
    "precio_prom": 2.5,
    "precio_min": 2.0,
    "precio_max": 3.0,
    "n_obs": 4,
    "_total": 1,
}
_FILA_CANASTA = {
    "anio_enaho": 2023,
    "cod_departamento": "15",
    "departamento": "Lima",
    "producto": "papa",
    "grupo_enaho": "01",
    "peso_canasta": 0.12,
    "gasto_total_anual": 480.0,
    "cantidad_kg_anual": 90.0,
    "_total": 1,
}


@pytest.fixture
def captura(monkeypatch):
    """Monkeypatchea db.consultar; guarda (sql, params) y devuelve filas fijadas."""
    estado: dict = {"rows": []}

    def fake(sql, params=()):
        estado.setdefault("sqls", []).append(sql)
        estado["sql"] = sql
        estado["params"] = params
        return [dict(fila) for fila in estado["rows"]]

    monkeypatch.setattr(db, "consultar", fake)
    return estado


@pytest.fixture
def client():
    return TestClient(crear_app())


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


class TestPrecios:
    def test_sin_filtros(self, client, captura):
        captura["rows"] = [_FILA_PRECIO]
        r = client.get("/precios")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["producto"] == "papa blanca"
        # Sin filtros no hay WHERE; params solo trae limit y offset (defaults).
        assert "WHERE" not in captura["sql"]
        assert captura["params"] == (500, 0)

    def test_filtros_arman_where_y_params(self, client, captura):
        # Con offset>0 y cero filas, _pagina dispara un COUNT(*) extra que
        # pisaría lo capturado; se devuelve una fila para quedarse en una query.
        captura["rows"] = [_FILA_PRECIO]
        r = client.get(
            "/precios",
            params={"producto": "papa", "fuente": "marketplace",
                    "cod_departamento": "15", "desde": "2026-08-01",
                    "hasta": "2026-08-17", "limit": 10, "offset": 5},
        )
        assert r.status_code == 200
        sql, params = captura["sql"], captura["params"]
        assert r"producto ILIKE %s ESCAPE '\'" in sql
        assert "fuente = %s" in sql
        assert "cod_departamento = %s" in sql
        assert "fecha_captura >= %s" in sql and "fecha_captura <= %s" in sql
        # Orden: filtros en orden de aparición + limit + offset al final.
        # FastAPI parsea desde/hasta a date (psycopg los adapta a DATE).
        assert params == ("%papa%", "marketplace", "15", date(2026, 8, 1), date(2026, 8, 17), 10, 5)

    def test_lee_de_fct_precio_diario(self, client, captura):
        captura["rows"] = []
        client.get("/precios")
        assert "gold.fct_precio_diario" in captura["sql"]

    def test_limit_fuera_de_rango_es_422(self, client, captura):
        assert client.get("/precios", params={"limit": 99999}).status_code == 422


class TestCanasta:
    def test_shape_y_tabla(self, client, captura):
        captura["rows"] = [_FILA_CANASTA]
        r = client.get("/canasta")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["peso_canasta"] == 0.12
        assert "gold.canasta_consumo_dept" in captura["sql"]

    def test_filtros(self, client, captura):
        captura["rows"] = []
        client.get("/canasta", params={"cod_departamento": "15", "producto": "papa", "anio": 2023})
        sql, params = captura["sql"], captura["params"]
        assert "cod_departamento = %s" in sql and "anio_enaho = %s" in sql
        assert params == ("15", "%papa%", 2023, 500, 0)


BARRA = chr(92)


class TestPaginacion:
    """`total` vs `count`: sin el total, quien pagina no sabe cuándo terminó."""

    def test_total_sale_del_count_over_y_no_se_filtra_a_results(self, client, captura):
        captura["rows"] = [dict(_FILA_PRECIO, _total=1337)]
        body = client.get("/precios", params={"limit": 1}).json()
        assert body["total"] == 1337        # cuántas matchean el filtro
        assert body["count"] == 1           # cuántas trae esta página
        assert body["limit"] == 1 and body["offset"] == 0
        assert "_total" not in body["results"][0]

    def test_sql_pide_el_total_en_el_mismo_viaje(self, client, captura):
        captura["rows"] = [_FILA_PRECIO]
        client.get("/precios")
        assert "COUNT(*) OVER () AS _total" in captura["sql"]
        assert len(captura["sqls"]) == 1    # una sola query, no dos

    def test_pagina_vacia_pasado_el_final_pide_el_total_aparte(self, client, captura):
        captura["rows"] = []
        body = client.get("/precios", params={"offset": 10_000}).json()
        assert body["count"] == 0
        # Sin filas de donde leer el window function, sale un COUNT(*) suelto.
        assert len(captura["sqls"]) == 2
        assert captura["sqls"][1].startswith("SELECT COUNT(*) AS _total")

    def test_sin_resultados_desde_el_arranque_no_gasta_una_segunda_query(self, client, captura):
        captura["rows"] = []
        body = client.get("/precios").json()
        assert body["total"] == 0 and body["count"] == 0
        assert len(captura["sqls"]) == 1


class TestOrdenTotal:
    """Con empates en el ORDER BY, LIMIT/OFFSET puede duplicar y saltear filas."""

    def test_precios_ordena_por_todo_el_grano(self, client, captura):
        captura["rows"] = []
        client.get("/precios")
        orden = captura["sql"].split("ORDER BY ")[1]
        for col in ("fecha_captura", "fuente", "producto", "cod_departamento"):
            assert col in orden

    def test_canasta_ordena_por_toda_la_pk(self, client, captura):
        captura["rows"] = []
        client.get("/canasta")
        orden = captura["sql"].split("ORDER BY ")[1]
        for col in ("anio_enaho", "cod_departamento", "producto"):
            assert col in orden


class TestComodinesILike:
    """La entrada del usuario es texto literal, no un patrón LIKE."""

    def test_porcentaje_no_convierte_el_filtro_en_no_op(self, client, captura):
        captura["rows"] = []
        client.get("/precios", params={"producto": "%"})
        # El patrón busca un '%' literal; sin escapar sería '%%%' = matchea todo.
        assert captura["params"][0] == "%" + BARRA + "%" + "%"

    def test_guion_bajo_se_escapa(self, client, captura):
        captura["rows"] = []
        client.get("/canasta", params={"producto": "a_b"})
        assert captura["params"][0] == "%a" + BARRA + "_b%"

    def test_texto_normal_queda_igual(self, client, captura):
        captura["rows"] = []
        client.get("/precios", params={"producto": "papa"})
        assert captura["params"][0] == "%papa%"


class TestAnio:
    def test_anio_cero_es_422_y_no_saltea_el_filtro(self, client, captura):
        captura["rows"] = []
        # Antes: `if anio:` lo tomaba como falsy y devolvía TODOS los años.
        assert client.get("/canasta", params={"anio": 0}).status_code == 422

    def test_anio_valido_filtra(self, client, captura):
        captura["rows"] = []
        client.get("/canasta", params={"anio": 2023})
        assert "anio_enaho = %s" in captura["sql"]
        assert 2023 in captura["params"]
