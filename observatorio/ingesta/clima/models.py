"""Modelo de una medición diaria de clima (Open-Meteo) — issue #14."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MedicionClima:
    """Clima diario de una localidad productora.

    Grano bronze = **una localidad × un día**. ``fecha_captura`` es la fecha de la
    observación (no la de la corrida). ``precip_mm`` puede ser 0 (válido); los
    valores pueden ser None si Open-Meteo no reporta la variable ese día.
    """

    fecha_captura: str  # YYYY-MM-DD (hora Lima)
    fuente: str  # "open-meteo"
    localidad: str
    region: str
    latitud: float
    longitud: float
    precip_mm: float | None  # precipitación acumulada del día (mm)
    temp_max_c: float | None  # temperatura máxima (°C)
    temp_min_c: float | None  # temperatura mínima (°C)
