"""Núcleo puro del dashboard: índice de canasta, variación y semáforo (#37).

Sin streamlit y sin base: todo entra como estructuras simples y sale como
estructuras simples, así que se testea sin levantar nada.

El índice lo construye `observatorio.validacion.canasta_vs_ipc.construir_indice`
(Laspeyres base fija, ya validado en #20) — acá no se reimplementa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from observatorio.validacion.canasta_vs_ipc import construir_indice

# --------------------------------------------------------------------------- #
# Umbrales del semáforo
# --------------------------------------------------------------------------- #
# Calibrados sobre la distribución real de |variación mensual| del índice de
# canasta de Lima (sisap_minorista, 27 variaciones entre 2024-01 y 2026-09):
# mediana 3.1 %, p80 ≈ 7.5 %. Elegir 2 % / 5 % "a ojo" habría pintado de rojo uno
# de cada tres meses en una canasta de frescos, que se mueve así por naturaleza
# (ver docs/validacion_canasta_vs_ipc.md: volatilidad RMS ±6 %), y un semáforo
# que está siempre en rojo no informa nada.
#
# Es direccional a propósito: al consumidor una BAJA fuerte no le es una alarma.
# Verde cubre "estable o bajando"; el número con signo se muestra igual.
UMBRAL_ESTABLE = 3.0  # < 3 % de suba: mes típico (la mitad de los meses)
UMBRAL_ALERTA = 7.5  # ≥ 7.5 % de suba: el quintil más extremo

VERDE, AMBAR, ROJO, SIN_DATO = "verde", "ambar", "rojo", "sin_dato"

_ETIQUETAS = {
    VERDE: "Estable",
    AMBAR: "Subiendo",
    ROJO: "Alza fuerte",
    SIN_DATO: "Sin dato suficiente",
}


@dataclass(frozen=True)
class Semaforo:
    """Veredicto del semáforo para un departamento."""

    nivel: str  # VERDE | AMBAR | ROJO | SIN_DATO
    etiqueta: str
    variacion: float | None  # % respecto del mes anterior, con signo
    mes: str | None  # 'YYYY-MM' evaluado
    mes_previo: str | None
    motivo: str | None = None  # por qué no hay veredicto, si nivel == SIN_DATO


# --------------------------------------------------------------------------- #
# Ámbito de precios: qué precios se usan para valorizar la canasta de un depto
# --------------------------------------------------------------------------- #
PROPIO, NACIONAL, PROXY = "propio", "nacional", "proxy"

# Clave que entiende la capa de datos para "todas las filas de esta fuente, sin
# filtrar por departamento".
TODAS = "todas"


@dataclass(frozen=True)
class Ambito:
    """Con qué precios se valoriza la canasta, y qué hay que aclararle al lector."""

    clave: str  # cod_departamento | 'nacional' | 'todas'
    tipo: str  # PROPIO | NACIONAL | PROXY
    nota: str | None = None


def resolver_ambito(
    cod_departamento: str,
    *,
    deptos_con_precio: set[str],
    tiene_nacional: bool,
    nombres: dict[str, str] | None = None,
) -> Ambito:
    """Elige los precios con que valorizar la canasta de un departamento.

    Hoy SISAP solo se scrapea para Lima y marketplace no tiene desagregación
    departamental (guarda `cod_departamento` en NULL). Así que para 24 de los 25
    departamentos no hay precios propios y hay que decir con qué se los sustituye,
    en vez de mostrar un número sin aclaración o un "sin datos" que esconde que la
    canasta sí existe.
    """
    if cod_departamento in deptos_con_precio:
        return Ambito(cod_departamento, PROPIO)

    if tiene_nacional:
        return Ambito(
            "nacional",
            NACIONAL,
            "Esta fuente no desagrega por departamento: se valoriza la canasta local "
            "con precios nacionales. Lo que distingue a un departamento de otro acá "
            "es *qué* consume, no *a qué precio*.",
        )

    nombres = nombres or {}
    disponibles = ", ".join(sorted(nombres.get(c, c) for c in deptos_con_precio)) or "ninguno"
    return Ambito(
        TODAS,
        PROXY,
        f"No hay precios propios de este departamento en esta fuente: se valoriza su "
        f"canasta con los precios disponibles ({disponibles}). La comparación entre "
        f"departamentos refleja diferencias de consumo, no de precio.",
    )


def mes_anterior(mes: str) -> str:
    """'2026-01' → '2025-12'."""
    anio, m = (int(x) for x in mes.split("-"))
    return f"{anio - 1}-12" if m == 1 else f"{anio}-{m - 1:02d}"


def clasificar(variacion: float | None) -> str:
    """Nivel del semáforo para una variación porcentual con signo."""
    if variacion is None:
        return SIN_DATO
    if variacion >= UMBRAL_ALERTA:
        return ROJO
    if variacion >= UMBRAL_ESTABLE:
        return AMBAR
    return VERDE


def indice_canasta(
    precios_mensuales: dict[str, dict[str, float]], pesos: dict[str, float]
) -> list[tuple[str, float, float | None]]:
    """Índice mensual (mes, índice base 100, var % contra la entrada anterior)."""
    return construir_indice(precios_mensuales, pesos)


def evaluar_semaforo(
    indice: list[tuple[str, float, float | None]], *, mes_actual: str
) -> Semaforo:
    """Compara el último mes COMPLETO contra el inmediato anterior.

    Dos cuidados que la variación que ya trae `construir_indice` no cubre:

    1. **El mes en curso se descarta.** Si hoy es 4 de septiembre, el promedio de
       septiembre son 4 días: su variación es un artefacto. Se evalúa el último
       mes cerrado.
    2. **Los meses tienen que ser consecutivos de calendario.** `construir_indice`
       calcula la variación contra la entrada anterior de la lista, que con un
       hueco de datos puede ser meses atrás — SISAP no tiene 2026-01 a 2026-05,
       así que ahí compararía junio contra diciembre y lo llamaría "mensual".
    """
    por_mes = {mes: idx for mes, idx, _ in indice}
    cerrados = [mes for mes in sorted(por_mes) if mes < mes_actual]
    if not cerrados:
        return Semaforo(SIN_DATO, _ETIQUETAS[SIN_DATO], None, None, None,
                        "todavía no hay ningún mes cerrado con datos")

    mes = cerrados[-1]
    previo = mes_anterior(mes)
    if previo not in por_mes:
        return Semaforo(SIN_DATO, _ETIQUETAS[SIN_DATO], None, mes, previo,
                        f"falta {previo}: sin dos meses consecutivos no hay variación mensual")

    variacion = (por_mes[mes] / por_mes[previo] - 1.0) * 100.0
    nivel = clasificar(variacion)
    return Semaforo(nivel, _ETIQUETAS[nivel], variacion, mes, previo)


# --------------------------------------------------------------------------- #
# Serie de evolución (#38)
# --------------------------------------------------------------------------- #
# Ventanas del selector: etiqueta → días hacia atrás (None = todo el histórico).
VENTANAS: dict[str, int | None] = {
    "Últimos 90 días": 90,
    "Últimos 180 días": 180,
    "Último año": 365,
    "Todo el histórico": None,
}

# SISAP publica en días hábiles y el minorista de forma interdiaria, así que 1–4
# días sin dato es cadencia normal, no un hueco. Por encima de esto sí lo es.
DIAS_HUECO = 10


def desde_ventana(etiqueta: str, hoy: date) -> date | None:
    """Fecha de inicio de la ventana elegida (None = sin límite)."""
    dias = VENTANAS.get(etiqueta)
    return None if dias is None else hoy - timedelta(days=dias)


def insertar_huecos(
    serie: list[tuple[date, float]], *, dias_hueco: int = DIAS_HUECO
) -> list[tuple[date, float | None]]:
    """Corta la línea donde falta dato, en vez de cruzarlo con un segmento recto.

    Un gráfico de líneas une dos puntos consecutivos aunque los separen meses: en
    el hueco de SISAP (2026-01 a 2026-05) dibujaría una recta que parece dato
    interpolado y no lo es. Intercalar un punto nulo hace que la línea se corte
    ahí (plotly con `connectgaps=False`) y el hueco se vea como lo que es.
    """
    if not serie:
        return []
    ordenada = sorted(serie)
    salida: list[tuple[date, float | None]] = [ordenada[0]]
    for (previa, _), (actual, valor) in zip(ordenada, ordenada[1:], strict=False):
        if (actual - previa).days > dias_hueco:
            salida.append((previa + timedelta(days=1), None))
        salida.append((actual, valor))
    return salida


@dataclass(frozen=True)
class Prediccion:
    """Punto pronosticado con su banda."""

    fecha: date
    valor: float
    inferior: float
    superior: float


def proxima_prediccion(
    predicciones: list[tuple[date, float, float, float]], *, hoy: date
) -> Prediccion | None:
    """Primer punto pronosticado que todavía está en el futuro.

    Las corridas son semanales con horizonte de 14 días, así que una corrida vieja
    trae puntos ya vencidos: mostrarlos como "lo que viene" sería engañoso.
    """
    futuros = sorted((f, v, inf, sup) for f, v, inf, sup in predicciones if f > hoy)
    if not futuros:
        return None
    fecha, valor, inferior, superior = futuros[0]
    return Prediccion(fecha, valor, inferior, superior)
