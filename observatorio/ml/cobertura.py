"""Control de cobertura del batch: qué se esperaba modelar vs qué se modeló.

La capa ML es resiliente a propósito —una serie caída no tumba la corrida, igual
criterio que los scrapers— pero esa resiliencia no tenía techo: el 2026-07-22
fallaron **las 15 series de Prophet** por un problema de entorno y el batch
terminó con exit 0 y "2072 filas escritas", puras de baseline. En un workflow eso
es un run verde con datos a medias, que nadie mira.

Este módulo pone el techo. Compara, por modelo, las series que se esperaba
producir contra las que realmente salieron, y decide si la corrida es aceptable:

* **Pérdida total de un modelo** (se esperaban N>0 series y salieron 0): falla.
  Es el caso del 2026-07-22 y no puede ser nunca un fallo legítimo — si Prophet
  no le sirve a ninguna serie, es el entorno o el código, no los datos.
* **Pérdida global por encima de ``UMBRAL_FALLO_TOLERADO``**: falla. Red de
  seguridad para la degradación difusa (muchas series caídas, ninguna categoría
  al 100%).
* **Cualquier otra pérdida**: pasa, pero se loguea como WARNING con el desglose.

Las funciones son puras (dicts → veredicto); los runners solo loguean y traducen
el veredicto a exit code.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

# Proporción de series perdidas que la corrida tolera antes de fallar.
UMBRAL_FALLO_TOLERADO: float = 0.30


@dataclass(frozen=True)
class Veredicto:
    """Resultado de comparar la cobertura esperada con la obtenida."""

    esperado: dict[str, int]
    obtenido: dict[str, int]
    modelos_perdidos: tuple[str, ...]
    umbral: float

    @property
    def n_esperado(self) -> int:
        return sum(self.esperado.values())

    @property
    def n_obtenido(self) -> int:
        return sum(self.obtenido.values())

    @property
    def n_perdido(self) -> int:
        return max(self.n_esperado - self.n_obtenido, 0)

    @property
    def tasa_fallo(self) -> float:
        """Proporción de series esperadas que no se produjeron (0.0 si no se esperaba nada)."""
        return self.n_perdido / self.n_esperado if self.n_esperado else 0.0

    @property
    def ok(self) -> bool:
        """True si la corrida es aceptable (ningún modelo perdido y bajo el umbral)."""
        return not self.modelos_perdidos and self.tasa_fallo <= self.umbral

    def desglose(self) -> str:
        """Línea legible con el conteo por modelo, p. ej. ``prophet 0/15 · media_movil 148/148``."""
        modelos = sorted(set(self.esperado) | set(self.obtenido))
        return " · ".join(
            f"{m} {self.obtenido.get(m, 0)}/{self.esperado.get(m, 0)}" for m in modelos
        )


def evaluar_cobertura(
    esperado: Mapping[str, int],
    obtenido: Mapping[str, int],
    umbral: float = UMBRAL_FALLO_TOLERADO,
) -> Veredicto:
    """Compara lo esperado con lo obtenido por modelo y emite el veredicto.

    ``esperado`` y ``obtenido`` cuentan **series** (no filas) por nombre de
    modelo. Un modelo se considera perdido si se esperaban series suyas y no
    salió ninguna.

    >>> v = evaluar_cobertura({"prophet": 15, "media_movil": 148}, {"media_movil": 148})
    >>> v.modelos_perdidos, v.ok
    (('prophet',), False)
    >>> evaluar_cobertura({"media_movil": 10}, {"media_movil": 10}).ok
    True
    """
    perdidos = tuple(
        modelo
        for modelo, n in sorted(esperado.items())
        if n > 0 and obtenido.get(modelo, 0) == 0
    )
    return Veredicto(
        esperado=dict(esperado),
        obtenido=dict(obtenido),
        modelos_perdidos=perdidos,
        umbral=umbral,
    )


def reportar(veredicto: Veredicto, log: logging.Logger) -> int:
    """Loguea el desglose de cobertura y devuelve el exit code (0 OK, 1 fallo).

    Se loguea **siempre**, también cuando todo sale bien: el conteo real por
    modelo es lo que habría hecho visible el fallo del 2026-07-22 de un vistazo.
    """
    log.info("📊 Cobertura por modelo (series obtenidas/esperadas): %s", veredicto.desglose())

    if veredicto.modelos_perdidos:
        log.error(
            "🚨 Se perdió el 100%% de las series de: %s. La corrida se marca como fallida.",
            ", ".join(veredicto.modelos_perdidos),
        )
        return 1

    if veredicto.tasa_fallo > veredicto.umbral:
        log.error(
            "🚨 %d/%d series perdidas (%.0f%%), por encima del %.0f%% tolerado.",
            veredicto.n_perdido,
            veredicto.n_esperado,
            veredicto.tasa_fallo * 100,
            veredicto.umbral * 100,
        )
        return 1

    if veredicto.n_perdido:
        log.warning(
            "⚠️  %d/%d series perdidas (%.0f%%), dentro de lo tolerado.",
            veredicto.n_perdido,
            veredicto.n_esperado,
            veredicto.tasa_fallo * 100,
        )
    return 0
