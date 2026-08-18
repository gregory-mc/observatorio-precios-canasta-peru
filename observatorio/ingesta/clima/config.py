"""Constantes de la ingesta de clima diario vía Open-Meteo (issue #14).

Se usa Open-Meteo en vez de SENAMHI: la fuente estatal geo-bloquea tanto los
runners de datacenter como la red del self-hosted (sin ruta hacia su host), así
que era inalcanzable desde toda máquina programable como runner. Open-Meteo es un
servicio global (CDN, sin auth, sin geo-bloqueo) que entrega clima diario por
coordenada — precipitación y temperatura máx/mín — que es justo lo que el
observatorio necesita para cruzar clima con precios por región productora.

El dato es **reanálisis/modelo por coordenada**, no observación de estación
oficial. Para correlacionar clima↔precios en las zonas productoras de la canasta
es más completo y estable que las estaciones intermitentes del SENAMHI.
"""

from __future__ import annotations

from dataclasses import dataclass

# Endpoint de pronóstico (incluye días pasados recientes vía `past_days` y el día
# en curso). Para backfill de fechas dentro de la ventana alcanza con ampliar
# `past_days`; fechas muy viejas requerirían el archive-api (posible follow-up).
URL_FORECAST = "https://api.open-meteo.com/v1/forecast"

# Variables diarias pedidas (Open-Meteo). Orden de mapeo en el parser.
VARIABLES_DIARIAS = ["precipitation_sum", "temperature_2m_max", "temperature_2m_min"]

# Zona horaria de las fechas devueltas (alinea con el resto del pipeline, hora Lima).
TIMEZONE = "America/Lima"

# Días hacia atrás a pedir en cada corrida. Cubre el día objetivo y deja margen
# para backfill corto / recuperación si el cron no corrió.
PAST_DAYS = 7

TIMEOUT = (15, 45)


@dataclass(slots=True, frozen=True)
class Localidad:
    """Un punto representativo de una región productora de la canasta."""

    nombre: str
    region: str
    lat: float
    lon: float


# Localidades curadas: puntos representativos de las regiones productoras de la
# canasta MVP (papa, limón, pollo, cebolla, huevo, tomate) + Lima como polo de
# consumo (cruza con los precios SISAP de Lima). Ampliable sin tocar el resto.
LOCALIDADES: list[Localidad] = [
    Localidad("Lima", "lima", -12.05, -77.04),  # consumo + avicultura costa central
    Localidad("Ica", "ica", -14.07, -75.73),  # cebolla, tomate, hortalizas
    Localidad("Arequipa", "arequipa", -16.41, -71.54),  # cebolla, ajo (valles)
    Localidad("Camana", "arequipa", -16.62, -72.71),  # valle costero de Arequipa
    Localidad("Trujillo", "la_libertad", -8.11, -79.03),  # hortalizas, avicultura
    Localidad("Piura", "piura_lambayeque", -5.19, -80.63),  # limón, cítricos norte
    Localidad("Chiclayo", "piura_lambayeque", -6.77, -79.84),  # norte agrícola
    Localidad("Huancayo", "sierra_central", -12.07, -75.21),  # papa sierra central
    Localidad("Huanuco", "sierra_central", -9.93, -76.24),  # papa
    Localidad("Puno", "altiplano", -15.84, -70.02),  # papa altiplano
    Localidad("Cusco", "altiplano", -13.53, -71.97),  # papa altiplano
]
