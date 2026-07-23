"""Conexión a Postgres de la capa ML — a prueba del pooler de Supabase.

``SUPABASE_DB_URL`` apunta al **transaction pooler** (puerto 6543), que no
soporta *prepared statements*: los reusa entre transacciones y termina
respondiendo ``DuplicatePreparedStatement: prepared statement "_pg3_0" already
exists``. psycopg3 los usa por su cuenta a partir de la 5ª ejecución de la misma
consulta y en ``executemany``, así que la escritura de ``ml.*`` fallaba de forma
intermitente contra el pooler (verificado en la primera corrida de M4 en prod,
2026-07-22: ``run_entrenamiento`` pasó y ``run_anomalias`` abortó).

El resto del proyecto no se topa con esto porque escribe con ``COPY FROM STDIN``
(ver ``observatorio/carga``), que no prepara nada. Acá, en vez de reescribir la
persistencia, se desactiva la preparación con ``prepare_threshold=None``: psycopg
lo trata como "este usuario no quiere preparar" y manda siempre la consulta
extendida (ver ``psycopg/_preparing.py``). El costo es despreciable —una corrida
escribe unos miles de filas— y deja la capa funcionando por cualquiera de los dos
puertos, sin depender de qué URL traiga el secret.
"""

from __future__ import annotations

import os
from typing import Any

# Deshabilita el uso automático de prepared statements (None = nunca preparar).
PREPARE_THRESHOLD: int | None = None


def conectar(db_url: str | None = None, **kwargs: Any):
    """Abre una conexión a Postgres válida tanto por el pooler como por el directo.

    Toma la URL de ``db_url`` o, si no se pasa, de ``SUPABASE_DB_URL``. Los
    ``kwargs`` extra van tal cual a ``psycopg.connect``.
    """
    import psycopg

    url = db_url or os.environ["SUPABASE_DB_URL"]
    return psycopg.connect(url, prepare_threshold=PREPARE_THRESHOLD, **kwargs)
