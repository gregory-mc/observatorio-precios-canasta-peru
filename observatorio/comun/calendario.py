"""Calendario laboral peruano, compartido por la ingesta y la carga.

Única fuente de verdad para "¿MIDAGRI publica este día?". La usan tanto el
scraper SISAP (para no consultar en días no hábiles) como la carga a bronze
(para no marcar como fallo la ausencia de datos SISAP en esos mismos días).
"""

from __future__ import annotations

from datetime import date


def es_dia_habil_peru(fecha: date) -> bool:
    """Retorna False si MIDAGRI no publica ese día (fin de semana o feriado peruano)."""
    # Import perezoso: quien solo importa el módulo no paga el costo de `holidays`.
    import holidays

    if fecha.weekday() >= 5:  # 5=sábado, 6=domingo
        return False
    return fecha not in holidays.PE(years=fecha.year)
