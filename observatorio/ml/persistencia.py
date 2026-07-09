"""Escritura de la salida cruda del modelado a Postgres (schema ``ml``).

Aterriza los pronósticos en ``ml.predicciones_raw`` siguiendo el mismo contrato
que la capa de carga: **idempotente por corrida** (DELETE de las filas de esa
``fecha_corrida`` y luego insert, todo en una transacción, así un fallo a mitad
no deja la tabla a medias). El schema/tabla se autocrean (CREATE ... IF NOT
EXISTS); el DDL de referencia vive en ``sql/ml_schema.sql``.

``_filas_para_insertar`` es una función pura (DataFrame → tuplas) testeable sin
DB; ``escribir_predicciones`` es el envoltorio que abre la conexión y escribe.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd

# Orden de columnas del insert; debe calzar con ml.predicciones_raw.
_COLS_INSERT = (
    "fecha_corrida",
    "fuente",
    "cod_departamento",
    "producto",
    "fecha_pred",
    "yhat",
    "yhat_lower",
    "yhat_upper",
    "modelo",
    "n_obs_entrenamiento",
)

DDL = """
create schema if not exists ml;

create table if not exists ml.predicciones_raw (
    fecha_corrida         date              not null,
    fuente                text              not null,
    cod_departamento      char(2),
    producto              text              not null,
    fecha_pred            date              not null,
    yhat                  double precision  not null,
    yhat_lower            double precision,
    yhat_upper            double precision,
    modelo                text              not null,
    n_obs_entrenamiento   integer           not null,
    computed_at           timestamptz       not null default now(),
    primary key (fecha_corrida, fuente, cod_departamento, producto, fecha_pred)
);
"""


def _celda(valor: object) -> object:
    """Normaliza un valor de pandas a un tipo que psycopg acepta (NA/NaN → None)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor is pd.NA:
        return None
    if pd.isna(valor):
        return None
    return valor


def _filas_para_insertar(df: pd.DataFrame, fecha_corrida: date) -> list[tuple]:
    """Convierte el DataFrame de pronósticos en tuplas listas para el insert.

    El DataFrame debe traer la identidad de la serie ya adjunta (fuente,
    cod_departamento, producto) más las columnas de pronóstico. Añade
    ``fecha_corrida`` y ordena/normaliza las columnas según ``_COLS_INSERT``.
    Los nulos de banda (baseline) salen como ``None``; ``fecha_pred`` como
    ``date`` de Python.

    >>> import pandas as pd
    >>> from datetime import date
    >>> df = pd.DataFrame({
    ...     "fuente": ["sisap_minorista"], "cod_departamento": ["15"],
    ...     "producto": ["PAPA"], "fecha_pred": pd.to_datetime(["2026-02-01"]),
    ...     "yhat": [2.5], "yhat_lower": [pd.NA], "yhat_upper": [pd.NA],
    ...     "modelo": ["media_movil"], "n_obs_entrenamiento": [10],
    ... })
    >>> filas = _filas_para_insertar(df, date(2026, 1, 31))
    >>> filas[0][:5]
    (datetime.date(2026, 1, 31), 'sisap_minorista', '15', 'PAPA', datetime.date(2026, 2, 1))
    >>> print(filas[0][6])  # yhat_lower NA → None
    None
    """
    trabajo = df.copy()
    trabajo["fecha_corrida"] = fecha_corrida
    trabajo["fecha_pred"] = pd.to_datetime(trabajo["fecha_pred"]).dt.date

    filas: list[tuple] = []
    for registro in trabajo[list(_COLS_INSERT)].itertuples(index=False, name=None):
        filas.append(tuple(_celda(v) for v in registro))
    return filas


def escribir_predicciones(
    df: pd.DataFrame,
    fecha_corrida: date,
    db_url: str | None = None,
) -> int:
    """Escribe los pronósticos en ``ml.predicciones_raw``, idempotente por corrida.

    Borra las filas de ``fecha_corrida`` e inserta las nuevas en una sola
    transacción. Devuelve el número de filas insertadas. Conexión desde
    ``db_url`` o ``SUPABASE_DB_URL``.
    """
    if df.empty:
        return 0

    import psycopg

    url = db_url or os.environ["SUPABASE_DB_URL"]
    filas = _filas_para_insertar(df, fecha_corrida)
    placeholders = ", ".join(["%s"] * len(_COLS_INSERT))
    insert = (
        f"insert into ml.predicciones_raw ({', '.join(_COLS_INSERT)}) "
        f"values ({placeholders})"
    )

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute(
                "delete from ml.predicciones_raw where fecha_corrida = %s",
                (fecha_corrida,),
            )
            cur.executemany(insert, filas)
        conn.commit()
    return len(filas)
