"""Backfill histórico de precios SISAP (MIDAGRI) a ``bronze.sisap_precios`` — issue #16.

A diferencia del scraper diario (``run_ingesta_sisap.py``, que trae el día de hoy),
esto recorre un **rango de fechas pasadas** y carga directo a bronze por psycopg
(``DELETE`` + ``COPY`` por ``(fecha_captura, tipo_mercado)``, idempotente). Es un
one-shot administrativo, análogo a la descarga histórica del INEI (#12): no tiene
cron y se corre a demanda.

**Por qué día por día.** El portal SISAP no permite agregación mensual
(``periodicidad=mes`` siempre expira con "servidor sobrecargado") y cada request
en ``periodicidad=dia`` devuelve **un solo día** (la fecha ``hasta``). Así que el
histórico se arma consultando fechas individuales. Para no golpear de más la
infraestructura estatal (lenta e intermitente) se puede **muestrear** un
subconjunto de días por mes con ``--dias`` en vez de todos.

Reutiliza el parser, el modelo ``PrecioSisap`` y el esquema de columnas de la
carga, así que las filas que aterrizan son idénticas a las del pipeline diario
(``unidad_medida`` / ``equiv_kg_lt`` pueden venir vacíos, igual que en el diario).

Uso (desde la raíz del repo, requiere ``SUPABASE_DB_URL``)::

    # Rango completo, minorista + mayorista, todos los días:
    python -m observatorio.ingesta.sisap.backfill_historico --desde 2024-01-01 --hasta 2025-12-31

    # Muestreando 6 días/mes, sólo minorista, subconjunto de productos:
    python -m observatorio.ingesta.sisap.backfill_historico \\
        --desde 2025-01-01 --hasta 2025-12-31 \\
        --dias 4,9,14,19,24,28 --tipos minorista --productos 0104,1101,1105,0212,0228,0611

    # Sin escribir a la base (sólo reporta cobertura):
    python -m observatorio.ingesta.sisap.backfill_historico \\
        --desde 2025-01-01 --hasta 2025-01-31 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta

import requests

from observatorio.carga.r2_a_supabase import COLUMNAS_SISAP, ddl_tabla
from observatorio.ingesta.sisap.config import PRODUCTOS_CANASTA_BASICA
from observatorio.ingesta.sisap.models import PrecioSisap
from observatorio.ingesta.sisap.parser import parsear_html
from observatorio.ingesta.sisap.run_ingesta_sisap import (
    HEADERS,
    TIPOS_MERCADO,
    URL_SISAP,
    configurar_sesion_resiliente,
)

log = logging.getLogger("backfill_sisap")

# Reintentos por día ante error de red / respuesta vacía transitoria. El histórico
# es tolerante a huecos: un día sin publicación es ausencia legítima, no un fallo.
_REINTENTOS = 1
_PAUSA_ENTRE_REQUESTS_S = 0.5


def iterar_fechas(desde: date, hasta: date, dias: list[int] | None):
    """Genera las fechas del rango [desde, hasta]. Si ``dias`` está dado, sólo
    emite esos días-del-mes (muestreo); si no, todos los días."""
    d = desde
    while d <= hasta:
        if dias is None or d.day in dias:
            yield d
        d += timedelta(days=1)


def _variable_de(tipo_mercado: str) -> str:
    """Devuelve la variable SISAP (``min_precio_prom`` / ``may_precio_prom``)."""
    for tipo, variable in TIPOS_MERCADO:
        if tipo == tipo_mercado:
            return variable
    raise ValueError(f"tipo_mercado desconocido: {tipo_mercado}")


def pedir_dia(
    sesion: requests.Session,
    fecha: date,
    tipo_mercado: str,
    productos: list[str],
) -> list[PrecioSisap]:
    """Consulta el SISAP para una fecha y tipo de mercado; devuelve las filas
    parseadas (``[]`` si el día no tiene publicación o hay error transitorio)."""
    f = fecha.strftime("%d/%m/%Y")
    params = {
        "region": "150000",
        "variables[]": _variable_de(tipo_mercado),
        "fecha": f,
        "desde": fecha.replace(day=1).strftime("%d/%m/%Y"),
        "hasta": f,
        "anios[]": fecha.strftime("%Y"),
        "meses[]": fecha.strftime("%m"),
        "periodicidad": "dia",
        "__ajax_carga_final": "consulta",
        "ajax": "true",
    }
    mix = list(params.items()) + [("productos[]", pid) for pid in productos]
    for intento in range(_REINTENTOS + 1):
        try:
            resp = sesion.get(URL_SISAP, params=mix, headers=HEADERS, timeout=(10, 25))
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            if intento < _REINTENTOS:
                time.sleep(1)
            continue
        if "mensajeDeError" in resp.text:
            return []
        filas = parsear_html(
            resp.text, fecha_captura=fecha.strftime("%Y-%m-%d"), tipo_mercado=tipo_mercado
        )
        return [f for f in filas if f.precio_prom is not None and f.precio_prom > 0]
    return []


def cargar_bronze(conn, filas: list[PrecioSisap]) -> int:
    """Carga filas a ``bronze.sisap_precios`` de forma idempotente: por cada
    ``(fecha_captura, tipo_mercado)`` presente, borra lo previo y hace COPY.
    Todo en una transacción. Devuelve el número de filas insertadas."""
    if not filas:
        return 0
    cols = [c for c, _ in COLUMNAS_SISAP]
    claves = sorted({(f.fecha_captura, f.tipo_mercado) for f in filas})
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
        cur.execute(ddl_tabla("sisap_precios", COLUMNAS_SISAP))
        for fecha, tipo in claves:
            cur.execute(
                "DELETE FROM bronze.sisap_precios WHERE fecha_captura = %s AND tipo_mercado = %s",
                (fecha, tipo),
            )
        with cur.copy(f"COPY bronze.sisap_precios ({', '.join(cols)}) FROM STDIN") as copy:
            for f in filas:
                copy.write_row([getattr(f, c) for c in cols])
    conn.commit()
    return len(filas)


def ejecutar(
    conn,
    *,
    desde: date,
    hasta: date,
    dias: list[int] | None,
    tipos: list[str],
    productos: list[str],
    dry_run: bool,
) -> int:
    """Recorre el rango scrapeando y cargando mes a mes. Devuelve filas totales."""
    sesion = configurar_sesion_resiliente()
    total = 0
    fechas = list(iterar_fechas(desde, hasta, dias))
    log.info(
        "Backfill SISAP %s → %s | %d fechas | tipos=%s | %d productos%s",
        desde, hasta, len(fechas), tipos, len(productos), " (DRY-RUN)" if dry_run else "",
    )
    for fecha in fechas:
        lote: list[PrecioSisap] = []
        marcas = []
        for tipo in tipos:
            filas = pedir_dia(sesion, fecha, tipo, productos)
            lote.extend(filas)
            marcas.append(f"{tipo}:{len(filas)}")
            time.sleep(_PAUSA_ENTRE_REQUESTS_S)
        if lote and not dry_run:
            cargar_bronze(conn, lote)
        total += len(lote)
        log.info("  %s  %s", fecha, " ".join(marcas))
    destino = "descubiertas (dry-run)" if dry_run else "cargadas a bronze"
    log.info("Backfill terminado: %d filas %s.", total, destino)
    return total


def _parse_fecha(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Backfill histórico de precios SISAP a bronze (#16).")
    ap.add_argument("--desde", required=True, type=_parse_fecha, help="Fecha inicial YYYY-MM-DD.")
    ap.add_argument("--hasta", required=True, type=_parse_fecha, help="Fecha final YYYY-MM-DD.")
    ap.add_argument(
        "--dias",
        default=None,
        help="Días-del-mes a muestrear, coma-separados (p.ej. 4,9,14,19,24,28). "
        "Si se omite, se recorren todos los días del rango.",
    )
    ap.add_argument(
        "--tipos",
        default="minorista,mayorista",
        help="Tipos de mercado, coma-separados (minorista,mayorista). Default: ambos.",
    )
    ap.add_argument(
        "--productos",
        default=None,
        help="IDs de producto SISAP coma-separados. Default: toda la canasta básica.",
    )
    ap.add_argument("--dry-run", action="store_true", help="No escribe a bronze; sólo reporta.")
    args = ap.parse_args(argv)

    dias = [int(x) for x in args.dias.split(",")] if args.dias else None
    tipos = [t.strip() for t in args.tipos.split(",") if t.strip()]
    productos = (
        [p.strip() for p in args.productos.split(",") if p.strip()]
        if args.productos
        else list(PRODUCTOS_CANASTA_BASICA)
    )

    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("SUPABASE_DB_URL"):
        log.error("Falta SUPABASE_DB_URL (en el entorno o en .env).")
        return 2

    import psycopg

    with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=20) as conn:
        ejecutar(
            conn,
            desde=args.desde,
            hasta=args.hasta,
            dias=dias,
            tipos=tipos,
            productos=productos,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
