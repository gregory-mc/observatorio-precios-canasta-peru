"""Test de idempotencia de la carga a bronze (issue #21).

Hace **ejecutable** la garantía que hasta ahora solo estaba documentada: re-cargar
la misma partición (fecha, o fecha+tipo_mercado) produce el mismo conteo de filas,
no duplica. Se apoya en un doble `DELETE ... WHERE <particion>` + `COPY` dentro de
``cargar_csv``.

No toca una base real: usa una conexión psycopg *falsa* que mantiene la tabla en
memoria y honra el `DELETE ... WHERE` y el `COPY ... FROM STDIN` que emite el
cargador. Así el test corre en CI sin Postgres.
"""

from __future__ import annotations

import io
import re

from observatorio.carga.r2_a_supabase import FUENTES, cargar_csv

# --------------------------------------------------------------------------- #
# Conexión psycopg falsa: tabla en memoria (lista de dicts col->valor).
# --------------------------------------------------------------------------- #
_RE_DELETE = re.compile(r"DELETE FROM bronze\.(\w+) WHERE (.+)", re.S)
_RE_COPY = re.compile(r"COPY bronze\.(\w+) \(([^)]*)\) FROM STDIN")


def _fila_cumple(fila: dict, condicion: str, params: tuple) -> bool:
    """Evalúa el WHERE del cargador contra una fila en memoria.

    Solo cubre las formas que emite el cargador: ``TRUE`` (borra todo) y una
    conjunción de ``col = %s`` unidas por AND, en el orden de ``params``.
    """
    condicion = condicion.strip()
    if condicion == "TRUE":
        return True
    valores = iter(params)
    for termino in condicion.split(" AND "):
        col = termino.split("=")[0].strip()
        esperado = next(valores)
        if str(fila.get(col)) != str(esperado):
            return False
    return True


class _FakeCopy:
    def __init__(self, cursor: _FakeCursor, tabla: str, cols: list[str]):
        self._cursor = cursor
        self._tabla = tabla
        self._cols = cols

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write_row(self, valores):
        fila = dict(zip(self._cols, valores, strict=True))
        self._cursor.db.setdefault(self._tabla, []).append(fila)


class _FakeCursor:
    def __init__(self, db: dict):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str, params: tuple = ()):  # noqa: D401
        m = _RE_DELETE.match(sql.strip())
        if not m:
            return  # CREATE SCHEMA / CREATE TABLE, etc. — irrelevantes para el test
        tabla, condicion = m.group(1), m.group(2)
        filas = self.db.get(tabla, [])
        self.db[tabla] = [f for f in filas if not _fila_cumple(f, condicion, params)]

    def copy(self, sql: str):
        m = _RE_COPY.match(sql.strip())
        assert m, f"COPY inesperado: {sql!r}"
        cols = [c.strip() for c in m.group(2).split(",")]
        return _FakeCopy(self, m.group(1), cols)


class _FakeConn:
    def __init__(self):
        self.db: dict[str, list] = {}
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self.db)

    def commit(self):
        self.commits += 1


# --------------------------------------------------------------------------- #
# Helpers de datos
# --------------------------------------------------------------------------- #
_MUESTRA = {"date": "2026-06-12", "text": "x", "float": "1.5", "int": "1", "bool": "true"}


def _csv_sisap(fecha: str, tipo: str, n: int) -> str:
    """CSV válido para bronze.sisap_precios con ``n`` filas de una partición."""
    columnas = FUENTES["sisap"]["columnas"]
    nombres = [c for c, _ in columnas]
    fijos = {"fecha_captura": fecha, "tipo_mercado": tipo}
    buf = io.StringIO()
    buf.write(",".join(nombres) + "\n")
    for i in range(n):
        fila = []
        for nombre, tipo_col in columnas:
            if nombre in fijos:
                fila.append(fijos[nombre])
            elif nombre == "producto":
                fila.append(f"producto_{i}")  # distingue filas dentro de la partición
            else:
                fila.append(_MUESTRA[tipo_col])
        buf.write(",".join(fila) + "\n")
    return buf.getvalue()


def _cargar(conn, contenido, fecha, tipo):
    spec = FUENTES["sisap"]
    return cargar_csv(
        conn,
        tabla=spec["tabla"],
        columnas=spec["columnas"],
        contenido=contenido,
        where="fecha_captura = %s AND tipo_mercado = %s",
        where_params=(fecha, tipo),
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
class TestIdempotenciaCarga:
    def test_doble_carga_misma_particion_no_duplica(self):
        conn = _FakeConn()
        csv = _csv_sisap("2026-06-12", "minorista", n=3)

        n1 = _cargar(conn, csv, "2026-06-12", "minorista")
        n2 = _cargar(conn, csv, "2026-06-12", "minorista")

        assert n1 == n2 == 3
        # La garantía central: tras dos corridas, la tabla tiene 3 filas, no 6.
        assert len(conn.db["sisap_precios"]) == 3

    def test_recarga_reemplaza_no_acumula(self):
        conn = _FakeConn()
        _cargar(conn, _csv_sisap("2026-06-12", "minorista", n=5), "2026-06-12", "minorista")
        # Segunda corrida del mismo día con menos filas: debe quedar el nuevo conteo.
        _cargar(conn, _csv_sisap("2026-06-12", "minorista", n=2), "2026-06-12", "minorista")
        assert len(conn.db["sisap_precios"]) == 2

    def test_particiones_distintas_conviven(self):
        conn = _FakeConn()
        _cargar(conn, _csv_sisap("2026-06-12", "minorista", n=3), "2026-06-12", "minorista")
        _cargar(conn, _csv_sisap("2026-06-12", "mayorista", n=4), "2026-06-12", "mayorista")
        _cargar(conn, _csv_sisap("2026-06-13", "minorista", n=2), "2026-06-13", "minorista")
        # Re-cargar solo una partición no toca las otras.
        _cargar(conn, _csv_sisap("2026-06-12", "minorista", n=3), "2026-06-12", "minorista")
        assert len(conn.db["sisap_precios"]) == 3 + 4 + 2

    def test_cada_carga_hace_commit(self):
        conn = _FakeConn()
        _cargar(conn, _csv_sisap("2026-06-12", "minorista", n=1), "2026-06-12", "minorista")
        assert conn.commits == 1
