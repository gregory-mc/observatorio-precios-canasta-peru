"""API REST del Observatorio de Precios (issue #43).

Expone la capa gold de Supabase en modo solo-lectura. Scaffold con dos endpoints:

    GET /precios   → gold.fct_precio_diario  (precio unificado por fuente/depto/día)
    GET /canasta   → gold.canasta_consumo_dept (pesos de la canasta por depto)

Correr en local:  uvicorn observatorio.api.main:app --reload
Requiere ``SUPABASE_DB_URL`` (mismo secret que la carga). El SQL se arma siempre
con parámetros (nunca interpolando la entrada del usuario).
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, Query

from . import db
from .models import RespuestaCanasta, RespuestaPrecios

_COLS_PRECIOS = (
    "fecha_captura, fuente, cod_departamento, producto, "
    "precio_prom, precio_min, precio_max, n_obs"
)
_COLS_CANASTA = (
    "anio_enaho, cod_departamento, departamento, producto, grupo_enaho, "
    "peso_canasta, gasto_total_anual, cantidad_kg_anual"
)

# Orden TOTAL en ambos endpoints: si el ORDER BY no desempata por completo,
# Postgres puede devolver las filas empatadas en distinto orden entre la query
# de offset=0 y la de offset=500, duplicando unas y salteando otras. Por eso el
# orden incluye todas las columnas del grano/PK.
#   fct_precio_diario   grano: (fecha_captura, fuente, cod_departamento, producto)
#   canasta_consumo_dept  PK:  (anio_enaho, cod_departamento, producto)
_ORDEN_PRECIOS = "fecha_captura DESC, fuente, producto, cod_departamento"
_ORDEN_CANASTA = "anio_enaho DESC, cod_departamento, peso_canasta DESC, producto"

# Alias de la columna con el total; se saca de las filas antes de responder.
_TOTAL = "_total"


def _patron_ilike(texto: str) -> str:
    """Arma el patrón de un ILIKE tratando la entrada como texto literal.

    Sin esto, ``?producto=%`` genera el patrón ``%%%`` y el filtro matchea todo
    en vez de buscar un producto llamado ``%`` — o sea, el filtro se vuelve un
    no-op silencioso. Igual con ``_``, que en LIKE es "un carácter cualquiera".
    """
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def _pagina(
    *,
    cols: str,
    tabla: str,
    where: list[str],
    params: list,
    orden: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Devuelve (filas de la página, total que matchea el filtro).

    ``COUNT(*) OVER ()`` calcula el total sobre el mismo scan que la página: no
    hace falta una segunda query, que además hoy significaría una segunda
    conexión (cada ``db.consultar`` abre la suya).
    """
    clausula = ("WHERE " + " AND ".join(where)) if where else ""
    sql = (
        f"SELECT {cols}, COUNT(*) OVER () AS {_TOTAL} FROM {tabla} {clausula} "
        f"ORDER BY {orden} LIMIT %s OFFSET %s"
    )
    filas = db.consultar(sql, (*params, limit, offset))

    if filas:
        total = filas[0][_TOTAL]
        for fila in filas:
            fila.pop(_TOTAL, None)
        return filas, total

    if offset == 0:
        return [], 0

    # Página vacía por caer más allá del final: la window function no devolvió
    # ninguna fila de donde leer el total, así que se pide aparte.
    solo_total = db.consultar(f"SELECT COUNT(*) AS {_TOTAL} FROM {tabla} {clausula}", tuple(params))
    return [], (solo_total[0][_TOTAL] if solo_total else 0)


def crear_app() -> FastAPI:
    app = FastAPI(
        title="Observatorio de Precios — API",
        version="0.1.0",
        description="API de precios de alimentos y canasta básica en Perú (capa gold).",
    )

    @app.get("/health", tags=["infra"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/precios", response_model=RespuestaPrecios, tags=["precios"])
    def precios(
        producto: str | None = Query(None, description="Coincidencia parcial (ILIKE)."),
        fuente: str | None = Query(None, description="p.ej. sisap_minorista, marketplace."),
        cod_departamento: str | None = Query(None, min_length=2, max_length=2),
        desde: date | None = Query(None, description="fecha_captura >= desde."),
        hasta: date | None = Query(None, description="fecha_captura <= hasta."),
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ) -> RespuestaPrecios:
        where: list[str] = []
        params: list = []
        if producto:
            where.append(r"producto ILIKE %s ESCAPE '\'")
            params.append(_patron_ilike(producto))
        if fuente:
            where.append("fuente = %s")
            params.append(fuente)
        if cod_departamento:
            where.append("cod_departamento = %s")
            params.append(cod_departamento)
        if desde:
            where.append("fecha_captura >= %s")
            params.append(desde)
        if hasta:
            where.append("fecha_captura <= %s")
            params.append(hasta)

        filas, total = _pagina(
            cols=_COLS_PRECIOS,
            tabla="gold.fct_precio_diario",
            where=where,
            params=params,
            orden=_ORDEN_PRECIOS,
            limit=limit,
            offset=offset,
        )
        return RespuestaPrecios(
            total=total, count=len(filas), limit=limit, offset=offset, results=filas
        )

    @app.get("/canasta", response_model=RespuestaCanasta, tags=["canasta"])
    def canasta(
        cod_departamento: str | None = Query(None, min_length=2, max_length=2),
        producto: str | None = Query(None, description="Coincidencia parcial (ILIKE)."),
        anio: int | None = Query(None, ge=2000, le=2100, description="Año ENAHO de la canasta."),
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ) -> RespuestaCanasta:
        where: list[str] = []
        params: list = []
        if cod_departamento:
            where.append("cod_departamento = %s")
            params.append(cod_departamento)
        if producto:
            where.append(r"producto ILIKE %s ESCAPE '\'")
            params.append(_patron_ilike(producto))
        # `is not None` y no truthiness: con `if anio:` el año 0 saltea el filtro
        # y devuelve TODOS los años mientras el que llama cree que filtró.
        if anio is not None:
            where.append("anio_enaho = %s")
            params.append(anio)

        filas, total = _pagina(
            cols=_COLS_CANASTA,
            tabla="gold.canasta_consumo_dept",
            where=where,
            params=params,
            orden=_ORDEN_CANASTA,
            limit=limit,
            offset=offset,
        )
        return RespuestaCanasta(
            total=total, count=len(filas), limit=limit, offset=offset, results=filas
        )

    return app


app = crear_app()
