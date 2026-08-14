"""Modelos del scraper de clima de SENAMHI (issue #14)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Estacion:
    """Una estación del catálogo de SENAMHI (``var PruebaTest`` del mapa).

    Los campos calcan las claves del catálogo. ``tipo`` viene del ``ico`` del
    catálogo ("M" meteorológica / "H" hidrológica) y ``estado`` indica la
    frescura del dato (AUTOMATICA/REAL = reciente, DIFERIDO = histórico rezagado).
    ``cod_old`` puede venir vacío. ``region`` la asigna la curación por
    bounding-box (``catalogo.curar``); es None para estaciones fuera de las
    regiones productoras de interés.
    """

    cod: str
    cod_old: str
    nombre: str
    categoria: str  # cate del catálogo (CO, EMA, PLU, ...)
    tipo: str  # ico: "M" | "H"
    estado: str  # AUTOMATICA | REAL | DIFERIDO
    lat: float
    lon: float
    region: str | None = None
