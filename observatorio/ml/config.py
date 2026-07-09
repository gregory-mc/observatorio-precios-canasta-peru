"""Constantes de la capa de modelado (ML) — Milestone M4.

Acá viven solo los parámetros estables del modelado. Las decisiones detrás de
cada valor (documentadas en el plan M4):

  * **Fuentes modeladas (MVP): SISAP minorista/mayorista.** Es la única fuente
    con backfill histórico suficiente para entrenar un modelo temporal. Marketplace
    y OSINERGMIN tienen historia corta todavía y quedan fuera del MVP de ML.
  * **Umbral de historia.** Una serie solo se modela con Prophet si supera
    ``MIN_OBSERVACIONES`` puntos repartidos en al menos ``MIN_SPAN_DIAS`` días de
    calendario. Debajo de eso el forecast no es fiable y la serie cae al baseline.
    (Las fuentes publican de forma esparsa, así que se exige span además de conteo.)
  * **Detección de anomalías: residuo normalizado > 2.5σ**, como fija el PLAN.
"""

from __future__ import annotations

# --- Fuentes de precios que la capa ML modela en el MVP ------------------------
# Deben existir como valores de `fuente` en gold.fct_precio_diario.
FUENTES_MODELADAS: tuple[str, ...] = ("sisap_minorista", "sisap_mayorista")

# --- Umbral de historia para modelar con Prophet -------------------------------
# Series por debajo de ESTOS mínimos caen al baseline (ver baseline.py).
MIN_OBSERVACIONES: int = 60  # nº de días observados en la serie
MIN_SPAN_DIAS: int = 90  # días de calendario entre la 1ª y la última observación

# --- Pronóstico ----------------------------------------------------------------
HORIZONTE_DIAS: int = 14  # días hacia adelante a predecir

# --- Baseline (referencia para el backtesting) ---------------------------------
VENTANA_MEDIA_MOVIL_DIAS: int = 7  # ventana de calendario de la media móvil naive

# --- Detección de anomalías ----------------------------------------------------
UMBRAL_SIGMA: float = 2.5  # |residuo normalizado| por encima del cual es anomalía
