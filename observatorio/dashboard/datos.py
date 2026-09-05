"""Capa de acceso a datos del dashboard (#36).

**Es el único módulo que habla con la base.** Hoy consulta Supabase directo por
SQL: el dashboard no depende de que la API esté desplegada (#47). Cuando lo esté,
se reemplazan estas funciones por llamadas HTTP y ninguna página cambia.

El mapeo producto crudo → slug MVP y los rangos de precio plausible viven en
`observatorio.validacion.canasta_vs_ipc` y se reusan desde acá: son la misma
definición que valida la canasta en #20/#102, y duplicarlos sería crear una
segunda verdad.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from observatorio.ml.conexion import conectar
from observatorio.validacion.canasta_vs_ipc import MAPEO_PRECIO_MVP, _sql_case_slug

# Fuente por defecto: es el ámbito canónico de la canasta (precio minorista, el
# que cruza con los pesos ENAHO) y la única con los 6 productos del MVP cubiertos.
FUENTE_DEFECTO = "sisap_minorista"
FUENTES = ("sisap_minorista", "sisap_mayorista", "marketplace")

_TTL = 3600  # los pipelines corren 1×/día: cachear una hora no atrasa nada.


def _patrones_slug() -> list[str]:
    """Parámetros del CASE de slugs, en el orden que espera `_sql_case_slug()`."""
    return [pat for patrones in MAPEO_PRECIO_MVP.values() for pat in patrones]


def hay_conexion() -> bool:
    """¿Está configurado `SUPABASE_DB_URL`? Permite un mensaje claro y no un stack."""
    load_dotenv()
    return bool(os.getenv("SUPABASE_DB_URL"))


def _filtro_ambito(clave: str) -> tuple[str, list]:
    """(fragmento SQL, params) para el ámbito: un depto, 'nacional' o 'todas'."""
    if clave == "nacional":
        return "cod_departamento is null", []
    if clave == "todas":
        return "true", []
    return "cod_departamento = %s", [clave]


@st.cache_data(ttl=_TTL, show_spinner="Consultando precios…")
def precios_mensuales(fuente: str, ambito: str) -> dict[str, dict[str, float]]:
    """{mes 'YYYY-MM' → {slug → precio promedio}} para una fuente y ámbito.

    `ambito` es un `cod_departamento`, `'nacional'` (filas sin departamento, como
    marketplace) o `'todas'` (sin filtrar: los precios que la fuente tenga).
    """
    load_dotenv()
    filtro, extra = _filtro_ambito(ambito)
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            with etiquetado as (
                select to_char(fecha_captura, 'YYYY-MM') as mes,
                       {_sql_case_slug()} as slug,
                       precio_prom
                from gold.fct_precio_diario
                where fuente = %s and {filtro} and precio_prom is not null
            )
            select mes, slug, avg(precio_prom)
            from etiquetado
            where slug is not null
            group by mes, slug
            """,
            [*_patrones_slug(), fuente, *extra],
        )
        salida: dict[str, dict[str, float]] = {}
        for mes, slug, precio in cur.fetchall():
            salida.setdefault(mes, {})[slug] = float(precio)
    return salida


@st.cache_data(ttl=_TTL)
def pesos_canasta(cod_departamento: str) -> tuple[dict[str, float], int | None]:
    """({slug → peso}, año ENAHO) del departamento, para el año más reciente."""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select producto, peso_canasta, anio_enaho
            from gold.canasta_consumo_dept
            where cod_departamento = %s
              and anio_enaho = (select max(anio_enaho) from gold.canasta_consumo_dept)
            """,
            [cod_departamento],
        )
        filas = cur.fetchall()
    pesos = {producto: float(peso) for producto, peso, _ in filas}
    anio = int(filas[0][2]) if filas else None
    return pesos, anio


@st.cache_data(ttl=_TTL)
def departamentos() -> list[tuple[str, str]]:
    """[(cod_departamento, nombre)] de los 25 departamentos, alfabético."""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select distinct cod_departamento, departamento
            from gold.canasta_consumo_dept
            order by departamento
            """
        )
        return [(cod, nombre) for cod, nombre in cur.fetchall()]


@st.cache_data(ttl=_TTL)
def departamentos_con_precio_propio(fuente: str) -> set[str]:
    """Departamentos con precios propios en esa fuente (hoy: solo Lima en SISAP)."""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select distinct cod_departamento
            from gold.fct_precio_diario
            where fuente = %s and cod_departamento is not null
            """,
            [fuente],
        )
        return {cod for (cod,) in cur.fetchall()}


@st.cache_data(ttl=_TTL)
def precios_recientes(fuente: str, ambito: str) -> list[tuple[str, float, str]]:
    """[(slug, último precio S//kg, fecha)] por producto del MVP."""
    load_dotenv()
    filtro, extra = _filtro_ambito(ambito)
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            with etiquetado as (
                select {_sql_case_slug()} as slug, precio_prom, fecha_captura
                from gold.fct_precio_diario
                where fuente = %s and {filtro} and precio_prom is not null
            ), ultimo as (
                select slug, max(fecha_captura) as fecha
                from etiquetado where slug is not null group by slug
            )
            select u.slug, avg(e.precio_prom), u.fecha
            from ultimo u join etiquetado e on e.slug = u.slug and e.fecha_captura = u.fecha
            group by u.slug, u.fecha
            order by u.slug
            """,
            [*_patrones_slug(), fuente, *extra],
        )
        return [(slug, float(precio), fecha.isoformat()) for slug, precio, fecha in cur.fetchall()]


@st.cache_data(ttl=_TTL)
def tiene_precios_nacionales(fuente: str) -> bool:
    """¿La fuente guarda filas sin departamento (cobertura nacional)?"""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "select exists (select 1 from gold.fct_precio_diario "
            "where fuente = %s and cod_departamento is null)",
            [fuente],
        )
        return bool(cur.fetchone()[0])
