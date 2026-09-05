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
            where.append("producto ILIKE %s")
            params.append(f"%{producto}%")
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

        clausula = ("WHERE " + " AND ".join(where)) if where else ""
        sql = (
            f"SELECT {_COLS_PRECIOS} FROM gold.fct_precio_diario {clausula} "
            "ORDER BY fecha_captura DESC, fuente, producto LIMIT %s OFFSET %s"
        )
        filas = db.consultar(sql, (*params, limit, offset))
        return RespuestaPrecios(count=len(filas), results=filas)

    @app.get("/canasta", response_model=RespuestaCanasta, tags=["canasta"])
    def canasta(
        cod_departamento: str | None = Query(None, min_length=2, max_length=2),
        producto: str | None = Query(None, description="Coincidencia parcial (ILIKE)."),
        anio: int | None = Query(None, description="Año ENAHO de la canasta."),
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ) -> RespuestaCanasta:
        where: list[str] = []
        params: list = []
        if cod_departamento:
            where.append("cod_departamento = %s")
            params.append(cod_departamento)
        if producto:
            where.append("producto ILIKE %s")
            params.append(f"%{producto}%")
        if anio:
            where.append("anio_enaho = %s")
            params.append(anio)

        clausula = ("WHERE " + " AND ".join(where)) if where else ""
        sql = (
            f"SELECT {_COLS_CANASTA} FROM gold.canasta_consumo_dept {clausula} "
            "ORDER BY cod_departamento, peso_canasta DESC LIMIT %s OFFSET %s"
        )
        filas = db.consultar(sql, (*params, limit, offset))
        return RespuestaCanasta(count=len(filas), results=filas)

    return app


app = crear_app()
