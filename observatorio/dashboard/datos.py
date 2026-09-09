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

# Cómo se llaman las fuentes en pantalla. Los nombres internos
# (`sisap_minorista`) son de la base, no del lector: SISAP es el sistema de
# precios de MIDAGRI y "marketplace" es el catálogo retail de Plaza Vea.
NOMBRES_FUENTE = {
    "sisap_minorista": "Mercados de barrio (Lima)",
    "sisap_mayorista": "Mercados mayoristas (Lima)",
    "marketplace": "Supermercado (Plaza Vea)",
}


def nombre_fuente(clave: str) -> str:
    """Nombre legible de una fuente de precios."""
    return NOMBRES_FUENTE.get(clave, clave)

_TTL = 3600  # los pipelines corren 1×/día: cachear una hora no atrasa nada.


def _patrones_slug() -> list[str]:
    """Parámetros del CASE de slugs, en el orden que espera `_sql_case_slug()`."""
    return [pat for patrones in MAPEO_PRECIO_MVP.values() for pat in patrones]


def url_conexion() -> str | None:
    """Connection string de Supabase, de donde sea que esté configurada.

    Dos entornos, dos mecanismos:

    - **Local**: `SUPABASE_DB_URL` en el entorno o en `.env` (mismo secret que
      usa la carga).
    - **Streamlit Community Cloud**: `st.secrets`, que es donde se pegan los
      secrets en la UI del deploy.

    Se leen los dos en vez de confiar en que Streamlit espeje los secrets a
    variables de entorno, para que la app no dependa de ese detalle.
    """
    load_dotenv()
    desde_entorno = os.getenv("SUPABASE_DB_URL")
    if desde_entorno:
        return desde_entorno
    try:
        return st.secrets["SUPABASE_DB_URL"]
    except Exception:  # noqa: BLE001 — sin secrets.toml, st.secrets levanta
        return None


def hay_conexion() -> bool:
    """¿Hay credencial configurada? Permite un mensaje claro y no un stack."""
    return bool(url_conexion())


def _conectar(**kwargs):
    """`conectar` con la URL ya resuelta (entorno o st.secrets)."""
    return conectar(url_conexion(), **kwargs)


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
    filtro, extra = _filtro_ambito(ambito)
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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
    filtro, extra = _filtro_ambito(ambito)
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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
    filtro, extra = _filtro_ambito(ambito)
    corte = "and fecha_captura >= %s" if desde else ""
    corte_param = [desde] if desde else []
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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
    corte = "and fecha >= %s" if desde else ""
    corte_param = [desde] if desde else []
    with _conectar() as conn, conn.cursor() as cur:
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
    with _conectar() as conn, conn.cursor() as cur:
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


# --------------------------------------------------------------------------- #
# Supermercado (#152)
# --------------------------------------------------------------------------- #
# Esta sección lee `silver.stg_marketplace_precios` y no `gold`, porque
# `gold.fct_precio_diario` no modela el catálogo retail: unifica fuentes y se
# queda con producto/precio, sin marca ni categoría. Si la sección se consolida,
# el paso natural es un mart de gold para el catálogo de supermercado.
_TABLA_SUPER = "silver.stg_marketplace_precios"

# El scraper baja el catálogo completo de "Mercado Saludable", que incluye
# rubros que no son comida: 215 SKUs de vitaminas, 140 de cosmética y 23 de
# cuidado personal, sobre ~6,900 del día. Se excluyen acá porque esto es un
# observatorio de precios de ALIMENTOS — sin el filtro, la mejor oferta del día
# era un acondicionador para el cabello. El resto de las 9 categorías raíz es
# comida.
SUBCATEGORIAS_NO_ALIMENTO = (
    "Mercado Saludable/Vitaminas y Suplementos Orgánicos",
    "Mercado Saludable/Cosmética Natural",
    "Mercado Saludable/Cuidado Personal Sostenible",
)


# Ventana para "lo vigente". No se lee un solo día porque el scraper entrega
# días parciales sin fallar: el 2026-09-08 trajo 10 SKUs de Panadería cuando los
# seis días anteriores tenían ~970, y el 2026-09-01 se trajo la mitad de
# Abarrotes. Tomando el último registro de cada SKU dentro de una ventana, un día
# incompleto deja de esconder productos.
VENTANA_VIGENTE = 7


def _solo_alimentos() -> tuple[str, list[str]]:
    """(condición SQL, params) que deja fuera lo que no es comida."""
    condicion = " and ".join(["categoria not like %s || '%%'"] * len(SUBCATEGORIAS_NO_ALIMENTO))
    return f"({condicion})", list(SUBCATEGORIAS_NO_ALIMENTO)


def patron_literal(texto: str) -> str:
    """Patrón ILIKE que trata la entrada como texto y no como comodines.

    Sin escapar, buscar `%` devuelve el catálogo entero: el filtro se vuelve un
    no-op silencioso. Mismo cuidado que en la API (#144).
    """
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


@st.cache_data(ttl=_TTL)
def rango_fechas_super() -> tuple[str | None, str | None]:
    """(primera, última) fecha con datos de supermercado."""
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(f"select min(fecha_captura), max(fecha_captura) from {_TABLA_SUPER}")
        desde, hasta = cur.fetchone()
    return (desde.isoformat() if desde else None, hasta.isoformat() if hasta else None)


@st.cache_data(ttl=_TTL)
def categorias_super(hasta: str) -> list[str]:
    """Categorías raíz con alimentos vigentes, de más a menos productos."""
    alimentos, params_alimentos = _solo_alimentos()
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            with vigente as (
                select distinct on (sku_id) sku_id, categoria_raiz
                from {_TABLA_SUPER}
                where fecha_captura > %s::date - {VENTANA_VIGENTE}
                  and fecha_captura <= %s::date
                  and categoria_raiz is not null and {alimentos}
                order by sku_id, fecha_captura desc
            )
            select categoria_raiz, count(*) n from vigente group by 1 order by n desc
            """,
            [hasta, hasta, *params_alimentos],
        )
        return [c for c, _ in cur.fetchall()]


@st.cache_data(ttl=_TTL, show_spinner="Comparando precios…")
def precios_por_categoria(hasta: str, dias_ventana: int) -> dict[str, dict[str, float]]:
    """{categoría → {sku_id → precio promedio}} en la ventana que termina en `hasta`.

    Promedia varios días en vez de tomar una fecha suelta: no todos los SKUs
    aparecen todos los días y una fecha puntual dejaría afuera a los que
    faltaron por casualidad.
    """
    alimentos, params_alimentos = _solo_alimentos()
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            select categoria_raiz, sku_id, avg(precio)
            from {_TABLA_SUPER}
            where fecha_captura > %s::date - %s and fecha_captura <= %s::date
              and precio > 0 and categoria_raiz is not null
              and {alimentos}
            group by 1, 2
            """,
            [hasta, dias_ventana, hasta, *params_alimentos],
        )
        salida: dict[str, dict[str, float]] = {}
        for categoria, sku, precio in cur.fetchall():
            salida.setdefault(categoria, {})[sku] = float(precio)
    return salida


@st.cache_data(ttl=_TTL)
def precio_tipico_por_categoria(hasta: str) -> dict[str, float]:
    """{categoría → precio mediano vigente}, para dar contexto a la variación."""
    alimentos, params_alimentos = _solo_alimentos()
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            with vigente as (
                select distinct on (sku_id) sku_id, categoria_raiz, precio
                from {_TABLA_SUPER}
                where fecha_captura > %s::date - {VENTANA_VIGENTE}
                  and fecha_captura <= %s::date
                  and precio > 0 and categoria_raiz is not null and {alimentos}
                order by sku_id, fecha_captura desc
            )
            select categoria_raiz, percentile_cont(0.5) within group (order by precio)
            from vigente group by 1
            """,
            [hasta, hasta, *params_alimentos],
        )
        return {c: float(pr) for c, pr in cur.fetchall()}


@st.cache_data(ttl=_TTL, show_spinner="Buscando…")
def buscar_super(texto: str, hasta: str, limite: int = 40) -> list[dict]:
    """Alimentos vigentes cuyo nombre contiene `texto`, con su precio más reciente.

    Se busca en una ventana de 7 días y se toma el último registro de cada
    SKU, no el día suelto más reciente: el scraper entrega días parciales sin
    fallar, y leer una sola fecha esconde productos (ver `VENTANA_VIGENTE`).

    No se busca en todo el histórico por costo: `bronze.marketplace_precios` no
    tiene ningún índice, y sobre las 777k filas completas la consulta se pasa del
    `statement_timeout` de 2 minutos. Con la ventana, ~1.8 s.
    """
    alimentos, params_alimentos = _solo_alimentos()
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(
            rf"""
            select distinct on (sku_id)
                   sku_id, nombre, marca, categoria, precio, precio_lista,
                   disponible, url, fecha_captura
            from {_TABLA_SUPER}
            where fecha_captura > %s::date - {VENTANA_VIGENTE}
              and fecha_captura <= %s::date
              and nombre ilike %s escape ''
              and precio > 0
              and {alimentos}
            order by sku_id, fecha_captura desc
            limit %s
            """,
            [hasta, hasta, patron_literal(texto), *params_alimentos, limite],
        )
        columnas = [d[0] for d in cur.description]
        filas = [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]
    # `distinct on` obliga a ordenar por sku_id; el orden útil se aplica acá.
    return sorted(filas, key=lambda f: (not f["disponible"], f["nombre"]))


@st.cache_data(ttl=_TTL)
def serie_sku(sku_id: str) -> list[tuple]:
    """[(fecha, precio, precio_lista)] de un SKU, día por día."""
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            select fecha_captura, avg(precio), avg(precio_lista)
            from {_TABLA_SUPER}
            where sku_id = %s and precio > 0
            group by fecha_captura order by fecha_captura
            """,
            [sku_id],
        )
        return [
            (fecha, float(precio), float(lista) if lista is not None else None)
            for fecha, precio, lista in cur.fetchall()
        ]


@st.cache_data(ttl=_TTL)
def ofertas_super(
    categoria: str | None, solo_disponibles: bool, hasta: str, limite: int = 30
) -> list[dict]:
    """Mayores descuentos vigentes, sobre el último precio conocido de cada SKU."""
    alimentos, params_alimentos = _solo_alimentos()
    filtros, params = [], [hasta, hasta, *params_alimentos]
    if categoria:
        filtros.append("categoria_raiz = %s")
        params.append(categoria)
    if solo_disponibles:
        filtros.append("disponible")
    condicion = (" where " + " and ".join(filtros)) if filtros else ""
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            with vigente as (
                select distinct on (sku_id)
                       sku_id, nombre, marca, categoria_raiz, precio, precio_lista,
                       url, disponible, fecha_captura
                from {_TABLA_SUPER}
                where fecha_captura > %s::date - {VENTANA_VIGENTE}
                  and fecha_captura <= %s::date
                  and precio_lista > 0 and precio < precio_lista and {alimentos}
                order by sku_id, fecha_captura desc
            )
            select nombre, marca, categoria_raiz, precio, precio_lista, url, disponible
            from vigente{condicion}
            order by (1 - precio / precio_lista) desc
            limit %s
            """,
            [*params, limite],
        )
        columnas = [d[0] for d in cur.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cur.fetchall()]
