"""Carga de la capa Bronze: descarga los CSV crudos desde Cloudflare R2 y los
inserta en Supabase Postgres (schema ``bronze``).

Cierra el ``TODO(S2)`` del pipeline: R2 (archivos crudos) → ``bronze.*`` en Postgres.
A partir de ahí dbt construye las capas silver/gold.

Las dos fuentes de ingesta (ver ``observatorio/ingesta/``) escriben en R2 con estas
claves; este módulo las mapea a sus tablas bronze:

    marketplace/<fecha>.csv                  → bronze.marketplace_precios
    sisap/<fecha>_sisap_lima_minorista.csv   → bronze.sisap_precios
    sisap/<fecha>_sisap_lima_mayorista.csv   → bronze.sisap_precios

La carga es **idempotente por fecha**: re-correr el mismo día borra las filas de
esa fecha (y tipo de mercado, en SISAP) antes de reinsertarlas — igual que el
scraper sobreescribe el CSV del día en R2. El DELETE + COPY van en una sola
transacción por archivo, así que un fallo a mitad no deja la tabla a medias.

Variables de entorno requeridas:
    R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
    SUPABASE_DB_URL  → connection string Postgres del pooler de Supabase, p.ej.
                       postgresql://postgres.<ref>:<pwd>@<host>:6543/postgres?sslmode=require

Uso (desde la raíz del repo):
    python -m observatorio.carga.r2_a_supabase                      # ambas fuentes, hoy (Lima)
    python -m observatorio.carga.r2_a_supabase --fuente marketplace
    python -m observatorio.carga.r2_a_supabase --fecha 2026-06-01
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("carga")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> str:
    """Fecha actual en hora de Lima (UTC-5), igual criterio que los scrapers."""
    return datetime.now(LIMA).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Conversores celda CSV (str) → tipo Postgres.
# El CSV lo escribe csv.DictWriter desde dataclasses.asdict, así que un None de
# Python llega como cadena vacía: aquí se revierte a NULL.
# --------------------------------------------------------------------------- #
def _texto(v: str | None) -> str | None:
    return v if v else None


def _float(v: str | None) -> float | None:
    return float(v) if v else None


def _int(v: str | None) -> int | None:
    return int(v) if v else None


def _bool(v: str | None) -> bool | None:
    if not v:
        return None
    return v.strip().lower() == "true"


def _fecha(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


CONVERSORES = {"text": _texto, "float": _float, "int": _int, "bool": _bool, "date": _fecha}
SQL_TIPOS = {
    "text": "text",
    "float": "double precision",
    "int": "integer",
    "bool": "boolean",
    "date": "date",
}


# --------------------------------------------------------------------------- #
# Esquema de cada fuente: columnas (orden = orden del CSV) con su tipo, la tabla
# destino y el constructor de "tareas" de carga (una por archivo en R2).
# Cada tarea es (clave_r2, where_idempotencia, params_where).
# --------------------------------------------------------------------------- #
COLUMNAS_MARKETPLACE = [
    ("fecha_captura", "date"),
    ("fuente", "text"),
    ("product_id", "text"),
    ("sku_id", "text"),
    ("nombre", "text"),
    ("marca", "text"),
    ("categoria", "text"),
    ("categoria_raiz", "text"),
    ("ean", "text"),
    ("unidad_medida", "text"),
    ("multiplicador_unidad", "float"),
    ("precio", "float"),
    ("precio_lista", "float"),
    ("disponible", "bool"),
    ("cantidad_disponible", "int"),
    ("vendedor", "text"),
    ("url", "text"),
    ("consulta", "text"),
]

COLUMNAS_SISAP = [
    ("fecha_captura", "date"),
    ("fuente", "text"),
    ("region", "text"),
    ("tipo_mercado", "text"),
    ("producto", "text"),
    ("unidad_medida", "text"),
    ("equiv_kg_lt", "float"),
    ("precio_prom", "float"),
]

FUENTES = {
    "marketplace": {
        "tabla": "marketplace_precios",
        "columnas": COLUMNAS_MARKETPLACE,
        "tareas": lambda fecha: [
            (f"marketplace/{fecha}.csv", "fecha_captura = %s", (fecha,)),
        ],
    },
    "sisap": {
        "tabla": "sisap_precios",
        "columnas": COLUMNAS_SISAP,
        "tareas": lambda fecha: [
            (
                f"sisap/{fecha}_sisap_lima_{tipo}.csv",
                "fecha_captura = %s AND tipo_mercado = %s",
                (fecha, tipo),
            )
            for tipo in ("minorista", "mayorista")
        ],
    },
}


def ddl_tabla(tabla: str, columnas: list[tuple[str, str]]) -> str:
    """Genera el CREATE TABLE IF NOT EXISTS a partir del esquema de columnas.

    Mantiene una sola fuente de verdad: las mismas columnas se usan para el DDL
    y para el COPY, así no hay drift entre la tabla y la inserción.
    """
    lineas = [f"    {nombre} {SQL_TIPOS[tipo]}" for nombre, tipo in columnas]
    lineas.append("    ingested_at timestamptz NOT NULL DEFAULT now()")
    cuerpo = ",\n".join(lineas)
    return f"CREATE TABLE IF NOT EXISTS bronze.{tabla} (\n{cuerpo}\n);"


# --------------------------------------------------------------------------- #
# Clientes externos
# --------------------------------------------------------------------------- #
def cliente_r2():
    """Cliente boto3 S3-compatible apuntando a Cloudflare R2."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def descargar_csv(s3, bucket: str, clave: str) -> str | None:
    """Devuelve el contenido del objeto en R2, o None si la clave no existe."""
    try:
        obj = s3.get_object(Bucket=bucket, Key=clave)
    except s3.exceptions.NoSuchKey:
        return None
    return obj["Body"].read().decode("utf-8")


def cargar_csv(
    conn,
    *,
    tabla: str,
    columnas: list[tuple[str, str]],
    contenido: str,
    where: str,
    where_params: tuple,
) -> int:
    """Borra las filas previas de la partición y hace COPY de las nuevas.

    DELETE + COPY van en la misma transacción (un commit al final): si algo
    falla, la tabla queda como estaba. Devuelve el número de filas insertadas.
    """
    nombres = [c for c, _ in columnas]
    convs = [CONVERSORES[t] for _, t in columnas]

    reader = csv.DictReader(io.StringIO(contenido))
    faltantes = set(nombres) - set(reader.fieldnames or [])
    if faltantes:
        raise ValueError(f"El CSV no trae las columnas esperadas para {tabla}: {sorted(faltantes)}")

    cols_sql = ", ".join(nombres)
    filas = 0
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM bronze.{tabla} WHERE {where}", where_params)
        with cur.copy(f"COPY bronze.{tabla} ({cols_sql}) FROM STDIN") as copy:
            for fila in reader:
                copy.write_row([conv(fila.get(nombre)) for nombre, conv in zip(nombres, convs)])
                filas += 1
    conn.commit()
    return filas


def ejecutar(fuentes: list[str], fecha: str) -> int:
    """Orquesta la carga de las fuentes pedidas. Devuelve exit code (0 OK, 1 fallo)."""
    import psycopg

    bucket = os.environ["R2_BUCKET"]
    s3 = cliente_r2()

    total_filas = 0
    archivos_ok = 0
    fallos: list[str] = []

    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        # 1. Asegurar schema + tablas (idempotente).
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
            for nombre_fuente in fuentes:
                spec = FUENTES[nombre_fuente]
                cur.execute(ddl_tabla(spec["tabla"], spec["columnas"]))
        conn.commit()

        # 2. Por cada archivo de cada fuente: descargar de R2 y cargar a bronze.
        for nombre_fuente in fuentes:
            spec = FUENTES[nombre_fuente]
            tareas = spec["tareas"](fecha)
            cargados_fuente = 0

            for clave, where, where_params in tareas:
                log.info("⬇️  Descargando de R2: %s", clave)
                contenido = descargar_csv(s3, bucket, clave)
                if contenido is None:
                    log.warning("   ⚠️  No existe en R2: %s — se omite.", clave)
                    continue
                try:
                    filas = cargar_csv(
                        conn,
                        tabla=spec["tabla"],
                        columnas=spec["columnas"],
                        contenido=contenido,
                        where=where,
                        where_params=where_params,
                    )
                except Exception as e:  # noqa: BLE001 — registramos y seguimos con el resto
                    conn.rollback()
                    log.error("   ❌ Error cargando %s → bronze.%s: %s", clave, spec["tabla"], e)
                    fallos.append(clave)
                    continue

                log.info("   ✅ %d filas → bronze.%s", filas, spec["tabla"])
                total_filas += filas
                archivos_ok += 1
                cargados_fuente += 1

            # marketplace siempre produce un archivo; SISAP puede faltar un mercado
            # un día puntual, pero que NINGÚN archivo de la fuente cargue es un fallo.
            if cargados_fuente == 0:
                fallos.append(f"{nombre_fuente} (sin archivos cargados para {fecha})")

    log.info("🏁 Carga finalizada: %d archivos, %d filas en total.", archivos_ok, total_filas)
    if fallos:
        log.error("🚨 Fallos: %s", ", ".join(fallos))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Modo de prueba: fuerza fallo intencional para verificar la alerta (igual que los scrapers).
    if os.getenv("SIMULAR_FALLO", "false").lower() == "true":
        log.error("🧪 SIMULAR_FALLO=true — forzando fallo intencional para prueba de alertas.")
        return 1

    ap = argparse.ArgumentParser(description="Carga CSV crudos de R2 → Supabase Postgres (bronze).")
    ap.add_argument(
        "--fuente",
        choices=[*FUENTES, "ambas"],
        default="ambas",
        help="Fuente a cargar (default: ambas).",
    )
    ap.add_argument(
        "--fecha",
        default=fecha_hoy(),
        help="Fecha YYYY-MM-DD a cargar (default: hoy en hora Lima).",
    )
    args = ap.parse_args(argv)

    try:
        date.fromisoformat(args.fecha)
    except ValueError:
        ap.error(f"--fecha inválida: {args.fecha!r} (formato esperado YYYY-MM-DD)")

    fuentes = list(FUENTES) if args.fuente == "ambas" else [args.fuente]
    log.info("📦 Cargando fuentes %s para la fecha %s", fuentes, args.fecha)
    return ejecutar(fuentes, args.fecha)


if __name__ == "__main__":
    sys.exit(main())
