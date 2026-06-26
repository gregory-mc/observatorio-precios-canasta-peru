"""Motor de validación de calidad de datos — alternativa liviana a Great Expectations.

Define un puñado de *expectativas* declarativas (no-nulo, rango, dominio, clave
única, etc.) y un runner que las evalúa contra un ``pandas.DataFrame`` y devuelve
un reporte estructurado. Cero dependencias nuevas (solo pandas, ya base) y corre
en cualquier Python soportado por el repo.

Es el sustrato de la issue #18: las *suites por fuente* viven en ``suites.py`` y
se enganchan en la carga a bronze (``observatorio/carga/r2_a_supabase.py``) justo
antes del ``COPY``. Los mismos invariantes migran 1:1 a dbt tests en S6 (#26).

Severidad:
    * ``"error"``      → hace fallar el reporte (``Reporte.ok == False``). Aborta la carga.
    * ``"advertencia"`` → se registra pero no bloquea (p.ej. celdas de baja confianza
      muestral en la canasta, §7 de docs/canasta_consumo_dept.md: "no se borran; se reportan").

Uso:
    >>> from observatorio.validacion import SUITES, validar
    >>> reporte = validar(df, SUITES["sisap"])
    >>> reporte.ok
    True
    >>> print(reporte.resumen())
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import pandas as pd

Severidad = str  # "error" | "advertencia"

# Cuántos valores infractores de ejemplo se guardan por expectativa (para no
# volcar un dataset entero en el log).
MAX_EJEMPLOS = 5


# --------------------------------------------------------------------------- #
# Resultado y reporte
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Resultado:
    """Veredicto de evaluar una expectativa contra un DataFrame."""

    expectativa: str
    ok: bool
    severidad: Severidad
    n_fallos: int
    detalle: str
    columna: str | None = None
    ejemplos: tuple = ()

    def __str__(self) -> str:
        icono = "✅" if self.ok else ("❌" if self.severidad == "error" else "⚠️")
        col = f" [{self.columna}]" if self.columna else ""
        extra = ""
        if not self.ok:
            extra = f" — {self.n_fallos} fallo(s): {self.detalle}"
            if self.ejemplos:
                extra += f" (ej: {list(self.ejemplos)})"
        return f"{icono} {self.expectativa}{col}{extra}"


@dataclass(frozen=True)
class Reporte:
    """Conjunto de resultados de correr una suite sobre un DataFrame."""

    suite: str
    resultados: list[Resultado] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True si ninguna expectativa de severidad ``error`` falló."""
        return all(r.ok for r in self.resultados if r.severidad == "error")

    @property
    def errores(self) -> list[Resultado]:
        return [r for r in self.resultados if not r.ok and r.severidad == "error"]

    @property
    def advertencias(self) -> list[Resultado]:
        return [r for r in self.resultados if not r.ok and r.severidad == "advertencia"]

    def resumen(self) -> str:
        estado = "OK" if self.ok else "FALLÓ"
        cab = (
            f"Validación '{self.suite}': {estado} "
            f"({len(self.errores)} error(es), {len(self.advertencias)} advertencia(s), "
            f"{len(self.resultados)} chequeos)"
        )
        return "\n".join([cab, *(f"  {r}" for r in self.resultados)])


class ValidacionError(Exception):
    """Se lanza cuando un reporte con errores debe abortar el pipeline."""

    def __init__(self, reporte: Reporte):
        self.reporte = reporte
        super().__init__(f"Validación '{reporte.suite}' falló:\n{reporte.resumen()}")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mascara_nula(s: pd.Series) -> pd.Series:
    """Marca como nulo: NaN/None y, en columnas de texto, cadenas vacías o en blanco.

    El CSV crudo de bronze escribe los None de Python como cadena vacía, así que
    "" cuenta como ausente igual que NaN.
    """
    nula = s.isna()
    # En columnas de texto, "" o espacios también cuentan como ausente. Cubre tanto
    # el dtype ``object`` clásico como el ``string`` que pandas 3.0 usa por defecto.
    if not pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        vacio = s.astype("string").str.strip().eq("").fillna(False)
        nula = nula | vacio
    return nula


def _ejemplos(serie: pd.Series) -> tuple:
    return tuple(serie.head(MAX_EJEMPLOS).tolist())


# --------------------------------------------------------------------------- #
# Expectativas declarativas
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ColumnasPresentes:
    """Todas las columnas requeridas existen en el DataFrame."""

    columnas: Sequence[str]
    severidad: Severidad = "error"

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        faltantes = [c for c in self.columnas if c not in df.columns]
        detalle = "todas presentes"
        if faltantes:
            detalle = "columnas ausentes: " + ", ".join(faltantes)
        return Resultado(
            expectativa="columnas_presentes",
            ok=not faltantes,
            severidad=self.severidad,
            n_fallos=len(faltantes),
            detalle=detalle,
        )


@dataclass(frozen=True)
class MinFilas:
    """El DataFrame tiene al menos ``n`` filas (detecta cargas vacías)."""

    n: int = 1
    severidad: Severidad = "error"

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        ok = len(df) >= self.n
        return Resultado(
            expectativa="min_filas",
            ok=ok,
            severidad=self.severidad,
            n_fallos=0 if ok else 1,
            detalle=f"{len(df)} filas (mínimo esperado {self.n})",
        )


@dataclass(frozen=True)
class NoNulo:
    """La columna no tiene valores nulos/vacíos."""

    columna: str
    severidad: Severidad = "error"

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        if self.columna not in df.columns:
            return _columna_ausente("no_nulo", self.columna, self.severidad)
        nulos = _mascara_nula(df[self.columna])
        n = int(nulos.sum())
        return Resultado(
            expectativa="no_nulo",
            columna=self.columna,
            ok=n == 0,
            severidad=self.severidad,
            n_fallos=n,
            detalle="sin nulos" if n == 0 else f"{n} fila(s) con valor ausente",
        )


@dataclass(frozen=True)
class EnRango:
    """Los valores numéricos de la columna caen en [minimo, maximo].

    Coacciona a numérico (los valores no numéricos cuentan como infractores).
    Los nulos se ignoran si ``permite_nulo`` (bronze guarda lo crudo; el no-nulo
    se chequea aparte con ``NoNulo`` donde corresponda).
    """

    columna: str
    minimo: float | None = None
    maximo: float | None = None
    permite_nulo: bool = True
    severidad: Severidad = "error"

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        if self.columna not in df.columns:
            return _columna_ausente("en_rango", self.columna, self.severidad)
        original = df[self.columna]
        num = pd.to_numeric(original, errors="coerce")
        # No numérico = NaN tras coerción, pero NO era nulo originalmente → infractor.
        no_numerico = num.isna() & ~_mascara_nula(original)
        fuera = pd.Series(False, index=df.index)
        if self.minimo is not None:
            fuera = fuera | (num < self.minimo)
        if self.maximo is not None:
            fuera = fuera | (num > self.maximo)
        infractores = no_numerico | fuera.fillna(False)
        if not self.permite_nulo:
            infractores = infractores | _mascara_nula(original)
        n = int(infractores.sum())
        rango = f"[{self.minimo}, {self.maximo}]"
        return Resultado(
            expectativa="en_rango",
            columna=self.columna,
            ok=n == 0,
            severidad=self.severidad,
            n_fallos=n,
            detalle=f"en rango {rango}" if n == 0 else f"{n} valor(es) fuera de {rango}",
            ejemplos=_ejemplos(original[infractores]),
        )


@dataclass(frozen=True)
class EnConjunto:
    """Los valores de la columna pertenecen a un dominio cerrado."""

    columna: str
    valores: Iterable
    permite_nulo: bool = True
    severidad: Severidad = "error"

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        if self.columna not in df.columns:
            return _columna_ausente("en_conjunto", self.columna, self.severidad)
        permitidos = set(self.valores)
        col = df[self.columna]
        nula = _mascara_nula(col)
        fuera = ~col.isin(permitidos) & ~nula
        if not self.permite_nulo:
            fuera = fuera | nula
        n = int(fuera.sum())
        return Resultado(
            expectativa="en_conjunto",
            columna=self.columna,
            ok=n == 0,
            severidad=self.severidad,
            n_fallos=n,
            detalle="dominio respetado" if n == 0 else f"{n} valor(es) fuera del dominio",
            ejemplos=_ejemplos(col[fuera]),
        )


@dataclass(frozen=True)
class ClaveUnica:
    """La combinación de columnas no tiene duplicados (clave natural)."""

    columnas: Sequence[str]
    severidad: Severidad = "error"

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        faltantes = [c for c in self.columnas if c not in df.columns]
        if faltantes:
            return _columna_ausente("clave_unica", ", ".join(faltantes), self.severidad)
        cols = list(self.columnas)
        dup = df.duplicated(subset=cols, keep=False)
        n = int(dup.sum())
        ejemplos: tuple = ()
        if n:
            ejemplos = tuple(
                df.loc[dup, cols].drop_duplicates().head(MAX_EJEMPLOS).to_dict("records")
            )
        return Resultado(
            expectativa="clave_unica",
            columna="+".join(cols),
            ok=n == 0,
            severidad=self.severidad,
            n_fallos=n,
            detalle="sin duplicados" if n == 0 else f"{n} fila(s) con clave repetida",
            ejemplos=ejemplos,
        )


@dataclass(frozen=True)
class Predicado:
    """Escape hatch: una función ``df -> (ok, n_fallos, detalle, ejemplos)``.

    Para invariantes que no encajan en las expectativas estándar (p.ej. "los
    pesos suman 1.0 por departamento" en la canasta).
    """

    nombre: str
    fn: Callable[[pd.DataFrame], tuple[bool, int, str, tuple]]
    severidad: Severidad = "error"
    columna: str | None = None

    def evaluar(self, df: pd.DataFrame) -> Resultado:
        ok, n_fallos, detalle, ejemplos = self.fn(df)
        return Resultado(
            expectativa=self.nombre,
            columna=self.columna,
            ok=ok,
            severidad=self.severidad,
            n_fallos=n_fallos,
            detalle=detalle,
            ejemplos=tuple(ejemplos),
        )


def _columna_ausente(expectativa: str, columna: str, severidad: Severidad) -> Resultado:
    return Resultado(
        expectativa=expectativa,
        columna=columna,
        ok=False,
        severidad=severidad,
        n_fallos=1,
        detalle="la columna no existe en el DataFrame",
    )


# Una expectativa es cualquier objeto con ``.evaluar(df) -> Resultado``.
Expectativa = (
    ColumnasPresentes | MinFilas | NoNulo | EnRango | EnConjunto | ClaveUnica | Predicado
)


@dataclass(frozen=True)
class Suite:
    """Conjunto nombrado de expectativas para una fuente/tabla."""

    nombre: str
    expectativas: list[Expectativa]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def validar(df: pd.DataFrame, suite: Suite) -> Reporte:
    """Evalúa todas las expectativas de la suite sobre ``df`` y arma el reporte."""
    return Reporte(suite=suite.nombre, resultados=[e.evaluar(df) for e in suite.expectativas])


def validar_o_error(df: pd.DataFrame, suite: Suite) -> Reporte:
    """Como ``validar`` pero lanza ``ValidacionError`` si hay errores. Devuelve el
    reporte cuando pasa (puede traer advertencias)."""
    reporte = validar(df, suite)
    if not reporte.ok:
        raise ValidacionError(reporte)
    return reporte
