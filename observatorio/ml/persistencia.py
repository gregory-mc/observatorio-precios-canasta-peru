"""Escritura de la salida cruda del modelado a Postgres (schema ``ml``).

Aterriza los pronósticos en ``ml.predicciones_raw`` siguiendo el mismo contrato
que la capa de carga: **idempotente por corrida** (DELETE de las filas de esa
``fecha_corrida`` y luego insert, todo en una transacción, así un fallo a mitad
no deja la tabla a medias). El schema/tabla se autocrean (CREATE ... IF NOT
EXISTS); el DDL de referencia vive en ``sql/ml_schema.sql``.

``_filas_para_insertar`` es una función pura (DataFrame → tuplas) testeable sin
DB; ``escribir_predicciones`` es el envoltorio que abre la conexión y escribe.

La conexión se abre siempre vía ``conexion.conectar``: el insert usa
``executemany`` y eso, contra el pooler de Supabase, exige desactivar los
prepared statements (ver ``conexion.py``).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from .conexion import conectar

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

    filas = _filas_para_insertar(df, fecha_corrida)
    placeholders = ", ".join(["%s"] * len(_COLS_INSERT))
    insert = f"insert into ml.predicciones_raw ({', '.join(_COLS_INSERT)}) values ({placeholders})"

    with conectar(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute(
                "delete from ml.predicciones_raw where fecha_corrida = %s",
                (fecha_corrida,),
            )
            cur.executemany(insert, filas)
        conn.commit()
    return len(filas)


# =============================================================================
# Backtesting y anomalías — mismo contrato idempotente por corrida.
# Las series de backtest/anomalías comparten el patrón de predicciones_raw; la
# escritura se generaliza en _escribir_por_corrida. El DDL de referencia vive en
# sql/ml_schema.sql y es idéntico al que se autocrea acá.
# =============================================================================

_COLS_BACKTEST = (
    "fecha_corrida",
    "fuente",
    "cod_departamento",
    "producto",
    "modelo",
    "n_folds",
    "n_puntos",
    "mape",
    "rmse",
    "horizonte",
)

DDL_BACKTEST = """
create schema if not exists ml;

create table if not exists ml.backtest_metricas (
    fecha_corrida     date              not null,
    fuente            text              not null,
    cod_departamento  char(2),
    producto          text              not null,
    modelo            text              not null,
    n_folds           integer           not null,
    n_puntos          integer           not null,
    mape              double precision  not null,
    rmse              double precision  not null,
    horizonte         integer           not null,
    computed_at       timestamptz       not null default now(),
    primary key (fecha_corrida, fuente, cod_departamento, producto, modelo)
);
"""

_COLS_ANOMALIAS = (
    "fecha_corrida",
    "fuente",
    "cod_departamento",
    "producto",
    "fecha",
    "precio",
    "esperado",
    "residuo",
    "z_score",
    "metodo",
    "umbral_sigma",
)

DDL_ANOMALIAS = """
create schema if not exists ml;

create table if not exists ml.anomalias_raw (
    fecha_corrida     date              not null,
    fuente            text              not null,
    cod_departamento  char(2),
    producto          text              not null,
    fecha             date              not null,
    precio            double precision  not null,
    esperado          double precision  not null,
    residuo           double precision  not null,
    z_score           double precision  not null,
    metodo            text              not null,
    umbral_sigma      double precision  not null,
    computed_at       timestamptz       not null default now(),
    primary key (fecha_corrida, fuente, cod_departamento, producto, fecha)
);
"""


def _escribir_por_corrida(
    df: pd.DataFrame,
    cols: tuple[str, ...],
    tabla: str,
    ddl: str,
    fecha_corrida: date,
    db_url: str | None,
    fecha_cols: tuple[str, ...] = (),
) -> int:
    """Escribe ``df`` en ``tabla`` (schema ml), idempotente por ``fecha_corrida``.

    Añade ``fecha_corrida``, convierte a ``date`` las columnas de ``fecha_cols`` y
    normaliza los nulos (``_celda``). Borra las filas de la corrida e inserta las
    nuevas en una transacción. ``tabla`` es una constante del módulo (no entrada
    de usuario), así que interpolarla en el SQL es seguro.
    """
    if df.empty:
        return 0

    trabajo = df.copy()
    trabajo["fecha_corrida"] = fecha_corrida
    for c in fecha_cols:
        trabajo[c] = pd.to_datetime(trabajo[c]).dt.date

    filas = [
        tuple(_celda(v) for v in registro)
        for registro in trabajo[list(cols)].itertuples(index=False, name=None)
    ]
    placeholders = ", ".join(["%s"] * len(cols))
    insert = f"insert into {tabla} ({', '.join(cols)}) values ({placeholders})"

    with conectar(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute(f"delete from {tabla} where fecha_corrida = %s", (fecha_corrida,))
            cur.executemany(insert, filas)
        conn.commit()
    return len(filas)


def escribir_backtest_metricas(
    df: pd.DataFrame, fecha_corrida: date, db_url: str | None = None
) -> int:
    """Escribe las métricas de backtest en ``ml.backtest_metricas``.

    ``df`` trae la identidad de la serie, ``modelo`` y las métricas
    (``n_folds, n_puntos, mape, rmse, horizonte``). Idempotente por corrida.
    """
    return _escribir_por_corrida(
        df, _COLS_BACKTEST, "ml.backtest_metricas", DDL_BACKTEST, fecha_corrida, db_url
    )


def escribir_anomalias(df: pd.DataFrame, fecha_corrida: date, db_url: str | None = None) -> int:
    """Escribe las anomalías detectadas en ``ml.anomalias_raw``.

    ``df`` trae la identidad de la serie, el día anómalo (``fecha``) y su
    puntuación (``precio, esperado, residuo, z_score, metodo, umbral_sigma``).
    Idempotente por corrida.
    """
    return _escribir_por_corrida(
        df,
        _COLS_ANOMALIAS,
        "ml.anomalias_raw",
        DDL_ANOMALIAS,
        fecha_corrida,
        db_url,
        fecha_cols=("fecha",),
    )
