"""Acceso de solo-lectura a la capa gold de Supabase para la API (issue #43).

Se consulta por SQL directo (psycopg) y no por el cliente supabase-py: PostgREST
solo expone el schema ``public`` por defecto, y los marts viven en ``gold``.
Reutiliza el conector a prueba del pooler de ``observatorio.ml.conexion`` (ver su
docstring: desactiva prepared statements, necesario contra el pooler 6543).

``consultar`` es el único punto de contacto con la base — los endpoints arman el
SQL con parámetros y lo llaman. Aislarlo así lo hace trivial de monkeypatchear en
los tests (sin base real).
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from observatorio.ml.conexion import conectar


def consultar(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Ejecuta un SELECT y devuelve las filas como lista de dicts."""
    with conectar(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
