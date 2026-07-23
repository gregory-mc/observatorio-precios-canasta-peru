"""Carga de series de precio desde ``gold.fct_precio_diario`` — Milestone M4.

Una **serie** es el eje temporal de precio de un ``(fuente, cod_departamento,
producto)``: una fila por día observado, sin rellenar los días sin dato (las
fuentes publican de forma esparsa). Es la unidad que consumen el baseline y, más
adelante, Prophet.

El grano de ``fct_precio_diario`` conserva el nombre de producto tal como viene
de la fuente (no el slug del MVP); las series heredan ese nombre. La reducción a
los 6 slugs es trabajo de un mart posterior, no de esta capa.

``construir_series`` es una función pura sobre un DataFrame (testeable sin DB);
``cargar_series`` es el envoltorio que lee de Postgres y la invoca.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from . import config
from .conexion import conectar

# Columnas mínimas que una serie necesita de fct_precio_diario.
_COLUMNAS = ("fecha_captura", "fuente", "cod_departamento", "producto", "precio_prom")


@dataclass(frozen=True)
class Serie:
    """Serie temporal de precio de un ``(fuente, cod_departamento, producto)``.

    ``obs`` es un DataFrame ordenado por fecha con dos columnas en el naming que
    espera Prophet: ``ds`` (fecha, ``datetime64``) e ``y`` (precio, float). Una
    fila por día observado.
    """

    fuente: str
    cod_departamento: str | None
    producto: str
    obs: pd.DataFrame

    @property
    def clave(self) -> tuple[str, str | None, str]:
        """Identidad de la serie (su grano en fct_precio_diario)."""
        return (self.fuente, self.cod_departamento, self.producto)

    @property
    def n_obs(self) -> int:
        """Número de días observados."""
        return len(self.obs)

    @property
    def span_dias(self) -> int:
        """Días de calendario entre la primera y la última observación (0 si <2 obs)."""
        if self.n_obs < 2:
            return 0
        return int((self.obs["ds"].iloc[-1] - self.obs["ds"].iloc[0]).days)

    def es_modelable(
        self,
        min_obs: int = config.MIN_OBSERVACIONES,
        min_span: int = config.MIN_SPAN_DIAS,
    ) -> bool:
        """True si la serie tiene historia suficiente para Prophet.

        Debajo del umbral el forecast no es fiable y la serie debe caer al
        baseline (ver ``baseline.py``). Se exige span además de conteo porque las
        fuentes publican esparso: 60 puntos apretados en 2 semanas no son base
        para un modelo temporal.
        """
        return self.n_obs >= min_obs and self.span_dias >= min_span


def construir_series(df: pd.DataFrame) -> list[Serie]:
    """Parte un DataFrame de ``fct_precio_diario`` en una lista de ``Serie``.

    Espera las columnas de ``_COLUMNAS``. Agrupa por ``(fuente, cod_departamento,
    producto)`` — incluyendo grupos con ``cod_departamento`` nulo — y ordena cada
    serie por fecha. Devuelve la lista ordenada por clave para ser determinista.

    >>> import pandas as pd
    >>> df = pd.DataFrame({
    ...     "fecha_captura": ["2026-01-02", "2026-01-01"],
    ...     "fuente": ["sisap_minorista", "sisap_minorista"],
    ...     "cod_departamento": ["15", "15"],
    ...     "producto": ["PAPA BLANCA", "PAPA BLANCA"],
    ...     "precio_prom": [2.5, 2.4],
    ... })
    >>> series = construir_series(df)
    >>> len(series)
    1
    >>> list(series[0].obs["y"])  # reordenada por fecha
    [2.4, 2.5]
    """
    faltantes = [c for c in _COLUMNAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas en el DataFrame: {faltantes}")

    trabajo = df[list(_COLUMNAS)].copy()
    trabajo["fecha_captura"] = pd.to_datetime(trabajo["fecha_captura"])

    series: list[Serie] = []
    # dropna=False para no perder las series de ámbito nacional (cod_departamento null).
    agrupado = trabajo.groupby(
        ["fuente", "cod_departamento", "producto"], dropna=False
    )
    for (fuente, cod, producto), grupo in agrupado:
        obs = (
            grupo[["fecha_captura", "precio_prom"]]
            .rename(columns={"fecha_captura": "ds", "precio_prom": "y"})
            .sort_values("ds")
            .reset_index(drop=True)
        )
        obs["y"] = obs["y"].astype(float)
        cod_norm = None if pd.isna(cod) else str(cod)
        series.append(Serie(str(fuente), cod_norm, str(producto), obs))

    series.sort(key=lambda s: (s.fuente, s.cod_departamento or "", s.producto))
    return series


def cargar_series(
    fuentes: Iterable[str] = config.FUENTES_MODELADAS,
    db_url: str | None = None,
) -> list[Serie]:
    """Lee ``gold.fct_precio_diario`` de Postgres y devuelve las series.

    Filtra a las ``fuentes`` indicadas (por defecto, las del MVP de ML). La
    conexión se toma de ``db_url`` o, si no se pasa, de ``SUPABASE_DB_URL`` (el
    mismo connection string del pooler de Supabase que usa la capa de carga),
    vía ``conexion.conectar`` — sin prepared statements, que el pooler no admite.
    """
    fuentes = list(fuentes)
    consulta = (
        "select fecha_captura, fuente, cod_departamento, producto, precio_prom "
        "from gold.fct_precio_diario "
        "where fuente = any(%s)"
    )
    with conectar(db_url) as conn, conn.cursor() as cur:
        cur.execute(consulta, (fuentes,))
        filas = cur.fetchall()
        assert cur.description is not None  # siempre presente tras un SELECT
        columnas = [d.name for d in cur.description]

    df = pd.DataFrame(filas, columns=columnas)
    return construir_series(df)
