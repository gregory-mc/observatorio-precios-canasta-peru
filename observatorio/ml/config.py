"""Constantes de la capa de modelado (ML) — Milestone M4.

Aquí viven solo los parámetros estables del modelado. Las decisiones detrás de
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

# --- Modelo que se sirve en producción -----------------------------------------
# Prophet quedó DESCARTADO para el MVP con evidencia (backtesting del 2026-07-24
# sobre las 157 series que pasan el umbral): pierde contra el naive en las dos
# fuentes —mayorista 8.45% vs 4.05%, minorista 4.48% vs 1.58% de MAPE mediano— y
# gana en apenas el 6–9% de las series. Más historia lo empeora: la familia más
# densa (mayorista, 181 obs) es donde peor queda, porque el problema es la
# estructura de huecos (mediano 5 días, agujeros de hasta 378) y no el conteo.
# Se deja detrás de un flag en vez de borrarlo: el backtesting lo sigue midiendo
# en cada corrida, así que si alguna vez entra una fuente de muestreo regular el
# veredicto se puede revisar con datos. Ver docs/ml.md.
USAR_PROPHET: bool = False

# Baseline que se sirve cuando Prophet está apagado o la serie es corta.
# "naive" (repetir el último precio) le gana a "media_movil" en las dos fuentes.
MODELO_SERVIDO: str = "naive"

# --- Umbral de historia para modelar con Prophet -------------------------------
# Series por debajo de ESTOS mínimos caen al baseline (ver baseline.py).
MIN_OBSERVACIONES: int = 60  # nº de días observados en la serie
MIN_SPAN_DIAS: int = 90  # días de calendario entre la 1ª y la última observación

# --- Pronóstico ----------------------------------------------------------------
HORIZONTE_DIAS: int = 14  # días hacia adelante a predecir

# --- Baseline (referencia para el backtesting) ---------------------------------
VENTANA_MEDIA_MOVIL_DIAS: int = 7  # ventana de calendario de la media móvil naive

# --- Bandas de incertidumbre del baseline --------------------------------------
# Los baselines no traen bandas propias, así que se estiman de la volatilidad
# histórica de la serie (ver baseline.volatilidad_diaria). Ancho del intervalo
# igual al default de Prophet (80%) para no cambiar la lectura del dashboard al
# apagar Prophet.
NIVEL_BANDA: float = 0.80

# --- Backtesting walk-forward --------------------------------------------------
# Nº de cortes temporales (folds) y paso en días de calendario entre cortes. Con
# el default se evalúan 5 ventanas separadas una semana; el corte más reciente
# deja HORIZONTE_DIAS de observaciones reales por delante para comparar.
N_FOLDS_BACKTEST: int = 5
PASO_BACKTEST_DIAS: int = 7

# --- Detección de anomalías ----------------------------------------------------
UMBRAL_SIGMA: float = 2.5  # |residuo normalizado| por encima del cual es anomalía
