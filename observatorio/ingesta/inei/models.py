"""Esquema de una fila del IPC del INEI (una por mes de la serie)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IpcInei:
    """Un valor mensual del Índice de Precios al Consumidor de Lima Metropolitana.

    Fuente: INEI, archivo `n01_indice-precios_al_consumidor-lm_<mes><yy>.xlsx`,
    hoja con la serie reexpresada en base Dic 2021 = 100 (continua desde 1994).

    Las variaciones (`var_*`) pueden ser None: el INEI las deja en blanco ("-")
    para el primer año de la serie, donde no hay mes previo con que comparar.
    La normalización y el recorte temporal (p. ej. últimos 5 años) es trabajo de
    la capa silver (dbt); bronze guarda la serie cruda completa.
    """

    fuente: str  # "inei_ipc"
    ambito: str  # "Lima Metropolitana"
    base: str  # "Dic2021"
    periodo: str  # "YYYY-MM"
    anio: int
    mes: int  # 1..12
    indice: float  # índice del mes
    var_mensual: float | None  # variación % respecto al mes anterior
    var_acumulada: float | None  # variación % acumulada en el año
    var_anual: float | None  # variación % respecto al mismo mes del año anterior
