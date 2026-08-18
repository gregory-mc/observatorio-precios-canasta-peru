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
}


@pytest.fixture
def captura(monkeypatch):
    """Monkeypatchea db.consultar; guarda (sql, params) y devuelve filas fijadas."""
    estado: dict = {"rows": []}

    def fake(sql, params=()):
        estado["sql"] = sql
        estado["params"] = params
        return estado["rows"]

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
        captura["rows"] = []
        r = client.get(
            "/precios",
            params={"producto": "papa", "fuente": "marketplace",
                    "cod_departamento": "15", "desde": "2026-08-01",
                    "hasta": "2026-08-17", "limit": 10, "offset": 5},
        )
        assert r.status_code == 200
        sql, params = captura["sql"], captura["params"]
        assert "producto ILIKE %s" in sql
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
