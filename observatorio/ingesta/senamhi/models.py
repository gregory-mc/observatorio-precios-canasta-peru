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


@dataclass(slots=True)
class MedicionClima:
    """Una medición diaria de una estación (precipitación + temperatura).

    Grano bronze = **una estación × un día**. La fecha es la de la observación
    (no la de la corrida). Los tres valores pueden ser None: SENAMHI reporta el
    día en curso incompleto, y muchas estaciones de precipitación no miden
    temperatura. Los campos de estación (nombre, lat/lon, región…) los completa
    el parser desde la ``Estacion`` del catálogo curado.
    """

    fecha_captura: str  # YYYY-MM-DD de la observación
    fuente: str  # "senamhi"
    cod_estacion: str
    nombre: str
    categoria: str
    estado: str
    latitud: float
    longitud: float
    region: str
    precip_mm: float | None  # precipitación acumulada del día (mm)
    temp_max_c: float | None  # temperatura máxima (°C)
    temp_min_c: float | None  # temperatura mínima (°C)
