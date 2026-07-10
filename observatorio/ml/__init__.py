"""Capa de modelado (ML) del Observatorio de Precios — Milestone M4.

Consume la historia conformada de ``gold.fct_precio_diario`` (una fila por día
observado y serie) y produce, respetando el medallion, su salida CRUDA en el
schema ``ml`` de Postgres (``ml.predicciones_raw``, ``ml.backtest_metricas``,
``ml.anomalias_raw``). A partir de esas tablas dbt construye los marts gold
(``fct_predicciones``, ``fct_anomalias``) — igual que ``observatorio.carga``
aterriza bronze y dbt construye silver/gold. La capa Python nunca escribe gold.

Una **serie** es la unidad de modelado: el eje temporal de precio de un
``(fuente, cod_departamento, producto)``. Ver ``datos.Serie``.

Módulos:
    config          Constantes de modelado (horizonte, umbral σ, mínimo de historia).
    datos           Carga de series desde ``gold.fct_precio_diario``.
    baseline        Pronósticos de referencia (naive, media móvil).
    prophet_modelo  Pronóstico por serie: Prophet si hay historia, baseline si no.
    backtesting     Walk-forward + MAPE/RMSE (valida Prophet vs baseline).
    anomalias       Detección de anomalías (residuo normalizado > Nσ).
    persistencia    Escritura de las tablas crudas del schema ``ml``.
"""

from __future__ import annotations
