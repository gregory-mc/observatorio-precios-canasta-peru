"""Validación de calidad de datos del observatorio (issue #18).

Motor declarativo liviano (alternativa a Great Expectations, sin deps nuevas) +
suites por fuente. API pública:

    from observatorio.validacion import SUITES, validar, validar_o_error, ValidacionError
"""

from .runner import (
    ClaveUnica,
    ColumnasPresentes,
    EnConjunto,
    EnRango,
    Expectativa,
    MinFilas,
    NoNulo,
    Predicado,
    Reporte,
    Resultado,
    Suite,
    ValidacionError,
    validar,
    validar_o_error,
)
from .suites import SUITES

__all__ = [
    "SUITES",
    "Suite",
    "Expectativa",
    "Reporte",
    "Resultado",
    "ValidacionError",
    "validar",
    "validar_o_error",
    "ColumnasPresentes",
    "MinFilas",
    "NoNulo",
    "EnRango",
    "EnConjunto",
    "ClaveUnica",
    "Predicado",
]
