"""Convierte el Excel del IPC del INEI a filas IpcInei (una por mes).

El archivo trae dos hojas (`Base Dic2021` y `Base 2009`) con el mismo layout:

    fila 1-2 → títulos
    fila 4   → encabezados (Año | Mes | Índice | Mensual | Acumulada | Anual)
    fila 5+  → datos, un mes por fila

Particularidades del archivo que este parser maneja:
  * El "Año" sólo aparece en la fila de Enero de cada bloque (celdas combinadas);
    el resto de meses lo heredan → se arrastra hacia abajo (forward-fill).
  * El INEI escribe "Setiembre" (no "Septiembre"); se aceptan ambas grafías.
  * Las variaciones ausentes vienen como "-" → se convierten a None.
  * Los encabezados llegan con mojibake (latin-1), por eso se parsea por
    POSICIÓN de columna, no por nombre.
"""

from __future__ import annotations

import io

import openpyxl

from .models import IpcInei

MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "setiembre": 9,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _mes_num(valor: object) -> int | None:
    """Número de mes (1..12) a partir del nombre en español, o None si no aplica."""
    if not isinstance(valor, str):
        return None
    return MESES.get(valor.strip().lower())


def _float_o_none(valor: object) -> float | None:
    """Convierte celda a float. None/"-"/vacío → None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto or texto == "-":
        return None
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return None


def parsear_ipc(
    contenido: bytes,
    *,
    hoja: str = "Base Dic2021",
    base: str = "Dic2021",
    ambito: str = "Lima Metropolitana",
    fuente: str = "inei_ipc",
) -> list[IpcInei]:
    """Parsea el Excel del IPC y devuelve la serie mensual como lista de IpcInei.

    Lee una sola hoja (por defecto la base vigente Dic 2021, que ya contiene la
    serie continua reexpresada desde 1994 — sin necesidad de empalmar bases).
    Filas sin año vigente, sin mes válido o sin índice numérico se descartan.
    """
    wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    ws = wb[hoja]

    filas: list[IpcInei] = []
    anio_actual: int | None = None

    for fila in ws.iter_rows(values_only=True):
        c_anio = fila[0] if len(fila) > 0 else None
        c_mes = fila[1] if len(fila) > 1 else None
        mes_num = _mes_num(c_mes)

        # El año sólo aparece en la fila de Enero; se arrastra al resto del bloque.
        # Sólo lo tomamos cuando viene acompañado de un mes válido (descarta títulos).
        if isinstance(c_anio, (int, float)) and 1900 < int(c_anio) < 2100 and mes_num is not None:
            anio_actual = int(c_anio)

        if anio_actual is None or mes_num is None:
            continue

        indice = _float_o_none(fila[2] if len(fila) > 2 else None)
        if indice is None:
            continue

        filas.append(
            IpcInei(
                fuente=fuente,
                ambito=ambito,
                base=base,
                periodo=f"{anio_actual:04d}-{mes_num:02d}",
                anio=anio_actual,
                mes=mes_num,
                indice=indice,
                var_mensual=_float_o_none(fila[3] if len(fila) > 3 else None),
                var_acumulada=_float_o_none(fila[4] if len(fila) > 4 else None),
                var_anual=_float_o_none(fila[5] if len(fila) > 5 else None),
            )
        )

    return filas
