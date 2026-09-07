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


# --------------------------------------------------------------------------- #
# Evolución temporal (#38)
# --------------------------------------------------------------------------- #
# `fct_predicciones` y `fct_anomalias` ya vienen reducidas al slug MVP por el
# macro dbt `slug_producto_mvp`, así que acá no hace falta mapear: se filtra por
# `producto` directo. Para la serie observada, que sale de `fct_precio_diario`
# (nombres crudos), se sigue usando el CASE de `validacion`.


@st.cache_data(ttl=_TTL)
def productos_con_prediccion(fuente: str) -> list[str]:
    """Slugs con pronóstico en la última corrida de esa fuente."""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select distinct producto from gold.fct_predicciones
            where fuente = %s
              and fecha_corrida = (select max(fecha_corrida) from gold.fct_predicciones)
            order by producto
            """,
            [fuente],
        )
        return [p for (p,) in cur.fetchall()]


@st.cache_data(ttl=_TTL, show_spinner="Cargando serie…")
def serie_precio(fuente: str, ambito: str, slug: str, desde: str | None) -> list[tuple]:
    """[(fecha, precio promedio del día)] de un producto MVP."""
    load_dotenv()
    filtro, extra = _filtro_ambito(ambito)
    corte = "and fecha_captura >= %s" if desde else ""
    corte_param = [desde] if desde else []
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            with etiquetado as (
                select fecha_captura, {_sql_case_slug()} as slug, precio_prom
                from gold.fct_precio_diario
                where fuente = %s and {filtro} and precio_prom is not null {corte}
            )
            select fecha_captura, avg(precio_prom)
            from etiquetado where slug = %s
            group by fecha_captura order by fecha_captura
            """,
            [*_patrones_slug(), fuente, *extra, *corte_param, slug],
        )
        return [(fecha, float(precio)) for fecha, precio in cur.fetchall()]


@st.cache_data(ttl=_TTL)
def predicciones(fuente: str, slug: str) -> tuple[list[tuple], str | None, str | None]:
    """([(fecha, pred, inf, sup)], modelo, fecha_corrida) de la última corrida."""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select fecha_pred, precio_pred, precio_pred_inf, precio_pred_sup,
                   modelo, fecha_corrida
            from gold.fct_predicciones
            where fuente = %s and producto = %s
              and fecha_corrida = (select max(fecha_corrida) from gold.fct_predicciones)
            order by fecha_pred
            """,
            [fuente, slug],
        )
        filas = cur.fetchall()
    if not filas:
        return [], None, None
    puntos = [(f, float(v), float(i), float(s)) for f, v, i, s, _, _ in filas]
    return puntos, filas[0][4], filas[0][5].isoformat()


@st.cache_data(ttl=_TTL)
def anomalias(fuente: str, slug: str, desde: str | None) -> list[tuple]:
    """[(fecha, precio observado, esperado, z)] detectadas en la última corrida."""
    load_dotenv()
    corte = "and fecha >= %s" if desde else ""
    corte_param = [desde] if desde else []
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            select fecha, precio_prom, esperado_prom, z_abs_max
            from gold.fct_anomalias
            where fuente = %s and producto = %s {corte}
              and fecha_corrida = (select max(fecha_corrida) from gold.fct_anomalias)
            order by fecha
            """,
            [fuente, slug, *corte_param],
        )
        return [(f, float(p), float(e), float(z)) for f, p, e, z in cur.fetchall()]


# --------------------------------------------------------------------------- #
# Mapa por departamento (#39)
# --------------------------------------------------------------------------- #
# Los límites departamentales se traen en runtime y NO se vendorean: el archivo
# está bajo MPL-2.0 y este repo es MIT, así que distribuirlo arrastraría la
# obligación de licencia por un mapa que el PLAN marca como recortable. Trae
# `FIRST_IDDP`, que es el mismo código de departamento que usa la canasta, así
# que el join no depende de matchear nombres.
GEOJSON_URL = (
    "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/"
    "peru_departamental_simple.geojson"
)
GEOJSON_CLAVE = "properties.FIRST_IDDP"
GEOJSON_ATRIBUCION = (
    "Límites: [juaneladio/peru-geojson]"
    "(https://github.com/juaneladio/peru-geojson) (MPL-2.0)"
)


@st.cache_data(ttl=_TTL)
def pesos_por_departamento() -> dict[str, dict[str, float]]:
    """{cod_departamento → {slug → peso}} del año ENAHO más reciente."""
    load_dotenv()
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select cod_departamento, producto, peso_canasta
            from gold.canasta_consumo_dept
            where anio_enaho = (select max(anio_enaho) from gold.canasta_consumo_dept)
            """
        )
        salida: dict[str, dict[str, float]] = {}
        for cod, producto, peso in cur.fetchall():
            salida.setdefault(cod, {})[producto] = float(peso)
    return salida


@st.cache_data(ttl=86400, show_spinner="Cargando límites departamentales…")
def geojson_departamentos() -> dict | None:
    """Límites de los 25 departamentos, o None si la descarga falla.

    Devolver None en vez de propagar el error permite que la página degrade a una
    tabla ordenada — que es lo que el PLAN sugiere como sustituto del mapa — en
    lugar de quedar rota por una dependencia externa.
    """
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(GEOJSON_URL, timeout=20) as respuesta:
            return json.loads(respuesta.read())
    except Exception:  # noqa: BLE001 — cualquier fallo de red/parseo degrada a tabla
        return None
