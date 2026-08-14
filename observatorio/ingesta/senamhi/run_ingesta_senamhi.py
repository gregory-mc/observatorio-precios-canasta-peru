"""Ingesta diaria de clima de SENAMHI a bronze vía R2 (issue #14, paso 3).

Orquesta el catálogo curado (paso 1) + el parser de series (paso 2): recorre las
estaciones meteorológicas frescas de las regiones productoras, baja la serie de
cada una, y escribe una fila por estación para la **fecha objetivo** (hoy en hora
Lima por defecto). El endpoint entrega una ventana de ~30 días, así que ``--fecha``
permite re-generar cualquier día de esa ventana (backfill corto).

Salida: CSV ``clima/{fecha}_senamhi.csv`` (una fila por estación con dato ese día),
subido a R2. La carga a bronze la hace ``observatorio.carga.r2_a_supabase --fuente
clima``.

Requiere IP peruana (geo-bloqueo de datacenter) → corre en el self-hosted runner.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import asdict, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from .catalogo import descargar_serie, obtener_catalogo_curado
from .config import USER_AGENT
from .models import MedicionClima
from .parser import parsear_serie

log = logging.getLogger("senamhi")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> str:
    """Fecha actual en hora de Lima (UTC-5), igual criterio que los demás scrapers."""
    return datetime.now(LIMA).strftime("%Y-%m-%d")


def escribir_csv(filas: list[MedicionClima], ruta: Path) -> None:
    """Escribe las mediciones como CSV con encabezado (orden = campos del modelo)."""
    columnas = [f.name for f in fields(MedicionClima)]
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columnas)
        writer.writeheader()
        for fila in filas:
            writer.writerow(asdict(fila))


def subir_a_r2(ruta_local: Path, clave_r2: str) -> None:
    """Sube un archivo a Cloudflare R2 (S3-compatible). Omite si R2 no está configurado."""
    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")
    if not all([endpoint, access_key, secret_key, bucket]):
        log.warning("⚠️  R2 no configurado — se omite la subida (desarrollo local).")
        return

    import boto3
    from botocore.config import Config

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    s3.upload_file(str(ruta_local), bucket, clave_r2, ExtraArgs={"ContentType": "text/csv"})
    log.info("☁️  Subido a R2: %s", clave_r2)


def recolectar(fecha: str, *, limite: int | None = None) -> tuple[list[MedicionClima], int]:
    """Baja y parsea la serie de cada estación curada; devuelve (filas del día, errores).

    Toma solo la fila cuya ``fecha_captura`` == ``fecha`` (una por estación). Un
    fallo puntual (timeout, HTTP) se registra y no aborta el barrido.
    """
    estaciones = obtener_catalogo_curado()
    if limite:
        estaciones = estaciones[:limite]
    log.info("🗺️  %d estaciones curadas — objetivo %s", len(estaciones), fecha)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    filas: list[MedicionClima] = []
    errores = 0
    for est in estaciones:
        try:
            html = descargar_serie(est, session)
            del_dia = [f for f in parsear_serie(html, est) if f.fecha_captura == fecha]
            filas.extend(del_dia)
        except Exception as e:  # noqa: BLE001 — un grifo caído no tumba el barrido
            errores += 1
            log.warning("   ⚠️  %s (%s): %s", est.cod, est.nombre[:30], e)
    return filas, errores


def ejecutar_ingesta_diaria(args: argparse.Namespace) -> int:
    if os.getenv("SIMULAR_FALLO", "false").lower() == "true":
        log.error("🧪 SIMULAR_FALLO=true — forzando fallo intencional para prueba de alertas.")
        return 1

    fecha = args.fecha or fecha_hoy()
    log.info("🚀 Iniciando Pipeline Bronze - SENAMHI (clima diario)")

    filas, errores = recolectar(fecha, limite=args.limite)
    con_temp = sum(1 for f in filas if f.temp_max_c is not None or f.temp_min_c is not None)
    log.info(
        "🏁 Recolección: %d estaciones con dato para %s (%d con temperatura), %d errores",
        len(filas),
        fecha,
        con_temp,
        errores,
    )

    if not filas:
        log.error("🚨 0 estaciones con dato para %s — ¿caída o geo-bloqueo?", fecha)
        return 1

    base = Path(args.salida) / "senamhi"
    base.mkdir(parents=True, exist_ok=True)
    nombre_csv = f"{fecha}_senamhi.csv"
    ruta_csv = base / nombre_csv
    escribir_csv(filas, ruta_csv)
    log.info("💾 CSV: %s (%d filas)", ruta_csv, len(filas))

    subir_a_r2(ruta_csv, f"clima/{nombre_csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Scraper de clima diario (SENAMHI).")
    ap.add_argument("--salida", default="data/bronze", help="Carpeta de salida local.")
    ap.add_argument(
        "--fecha",
        help=(
            "Fecha YYYY-MM-DD a capturar (default: hoy en hora Lima). SENAMHI expone "
            "una ventana de ~30 días, así que admite backfill dentro de ese rango."
        ),
    )
    ap.add_argument("--limite", type=int, default=None, help="Máx estaciones (debug).")
    args = ap.parse_args(argv)

    if args.fecha:
        try:
            date.fromisoformat(args.fecha)
        except ValueError:
            ap.error(f"--fecha inválida: {args.fecha!r} (formato esperado YYYY-MM-DD)")

    return ejecutar_ingesta_diaria(args)


if __name__ == "__main__":
    sys.exit(main())
