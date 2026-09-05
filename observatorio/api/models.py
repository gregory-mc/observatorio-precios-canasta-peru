"""Modelos de respuesta de la API (issue #43)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class PrecioDiario(BaseModel):
    """Una fila de ``gold.fct_precio_diario`` (precio unificado por fuente/depto/día)."""

    fecha_captura: date
    fuente: str
    cod_departamento: str | None
    producto: str
    precio_prom: float | None
    precio_min: float | None
    precio_max: float | None
    n_obs: int


class CanastaItem(BaseModel):
    """Una fila de ``gold.canasta_consumo_dept`` (peso del producto en la canasta)."""

    anio_enaho: int
    cod_departamento: str
    departamento: str
    producto: str
    grupo_enaho: str
    peso_canasta: float
    gasto_total_anual: float | None
    cantidad_kg_anual: float | None


class _Pagina(BaseModel):
    """Sobre de paginación común a las respuestas de la API.

    ``total`` es cuántas filas matchean el filtro, no cuántas trae esta página:
    sin él, quien consume la API no puede distinguir "esto es todo" de "esta es
    la primera de N páginas" salvo por la heurística ``count == limit``.
    """

    total: int
    count: int
    limit: int
    offset: int


class RespuestaPrecios(_Pagina):
    results: list[PrecioDiario]


class RespuestaCanasta(_Pagina):
    results: list[CanastaItem]
