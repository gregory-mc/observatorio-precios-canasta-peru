"""Tests de la conexión de la capa ML (sin DB).

Cubren la regresión que rompió la primera corrida de M4 en prod (2026-07-22):
la escritura usa ``executemany`` y, si la conexión permite prepared statements,
el transaction pooler de Supabase responde ``DuplicatePreparedStatement``.
"""

from datetime import date

import pandas as pd
import psycopg
import pytest

from observatorio.ml import datos, persistencia
from observatorio.ml.conexion import conectar


class _CursorFalso:
    def __init__(self, registro: list[tuple[str, object]]):
        self._registro = registro
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, consulta, params=None):
        self._registro.append(("execute", consulta))

    def executemany(self, consulta, filas):
        self._registro.append(("executemany", consulta))

    def fetchall(self):
        return []


class _ConexionFalsa:
    """Conexión mínima: registra lo que se ejecuta y no toca ninguna DB."""

    def __init__(self, registro: list[tuple[str, object]]):
        self._registro = registro

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return _CursorFalso(self._registro)

    def commit(self):
        self._registro.append(("commit", None))


def test_conectar_desactiva_los_prepared_statements(monkeypatch):
    capturado = {}

    def _connect_falso(url, **kwargs):
        capturado["url"] = url
        capturado["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(psycopg, "connect", _connect_falso)

    conectar("postgresql://usuario:clave@pooler:6543/postgres")

    # None = "nunca preparar" para psycopg (ver psycopg/_preparing.py).
    assert capturado["kwargs"]["prepare_threshold"] is None
    assert capturado["url"].endswith(":6543/postgres")


def test_conectar_toma_la_url_del_entorno_si_no_se_pasa(monkeypatch):
    capturado = {}
    monkeypatch.setattr(psycopg, "connect", lambda url, **kw: capturado.setdefault("url", url))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://del-entorno/postgres")

    conectar()

    assert capturado["url"] == "postgresql://del-entorno/postgres"


def test_conectar_propaga_kwargs_extra(monkeypatch):
    capturado = {}
    monkeypatch.setattr(psycopg, "connect", lambda url, **kw: capturado.update(kw))

    conectar("postgresql://x/postgres", connect_timeout=20)

    assert capturado["connect_timeout"] == 20
    assert capturado["prepare_threshold"] is None


@pytest.mark.parametrize("modulo", [persistencia, datos])
def test_la_capa_ml_no_abre_conexiones_por_su_cuenta(modulo):
    """Ni la lectura ni la escritura deben llamar a psycopg.connect directamente.

    Es la guarda de la regresión: cualquier conexión nueva tiene que pasar por
    ``conexion.conectar``, que es quien desactiva los prepared statements.
    """
    fuente = (modulo.__file__ or "").replace("\\", "/")
    with open(fuente, encoding="utf-8") as fh:
        codigo = fh.read()
    assert "psycopg.connect(" not in codigo
    assert "conectar(" in codigo


def test_escribir_predicciones_usa_conectar(monkeypatch):
    registro: list[tuple[str, object]] = []
    monkeypatch.setattr(persistencia, "conectar", lambda db_url: _ConexionFalsa(registro))

    df = pd.DataFrame(
        {
            "fuente": ["sisap_minorista"],
            "cod_departamento": ["15"],
            "producto": ["PAPA"],
            "fecha_pred": pd.to_datetime(["2026-02-01"]),
            "yhat": [2.5],
            "yhat_lower": [2.0],
            "yhat_upper": [3.0],
            "modelo": ["prophet"],
            "n_obs_entrenamiento": [120],
        }
    )
    n = persistencia.escribir_predicciones(df, date(2026, 1, 31))

    assert n == 1
    acciones = [a for a, _ in registro]
    assert "executemany" in acciones  # el insert que el pooler no soporta preparado
    assert acciones[-1] == "commit"
