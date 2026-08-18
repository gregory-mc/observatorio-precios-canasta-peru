"""Ingesta diaria de clima a bronze vía R2 (Open-Meteo) — issue #14.

Baja el clima diario (precipitación + temp máx/mín) de las localidades curadas
(una por/para cada región productora de la canasta) y escribe una fila por
localidad para la **fecha objetivo** (hoy en hora Lima por defecto). Open-Meteo
entrega una ventana reciente, así que ``--fecha`` permite backfill corto.

Salida: CSV ``clima/{fecha}_clima.csv`` (una fila por localidad), subido a R2. La
carga a bronze la hace ``observatorio.carga.r2_a_supabase --fuente clima``.

Open-Meteo es un servicio global sin geo-bloqueo → corre en el runner estándar de
GitHub (no requiere self-hosted, a diferencia de SISAP/OSINERGMIN).
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

from .cliente import descargar
from .config import LOCALIDADES
from .models import MedicionClima
from .parser import parsear

log = logging.getLogger("clima")
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


def ejecutar_ingesta_diaria(args: argparse.Namespace) -> int:
    if os.getenv("SIMULAR_FALLO", "false").lower() == "true":
        log.error("🧪 SIMULAR_FALLO=true — forzando fallo intencional para prueba de alertas.")
        return 1

    fecha = args.fecha or fecha_hoy()
    log.info("🚀 Iniciando Pipeline Bronze - Clima (Open-Meteo)")
    log.info("🗺️  %d localidades — objetivo %s", len(LOCALIDADES), fecha)

    try:
        respuesta = descargar(LOCALIDADES)
    except Exception as e:  # noqa: BLE001
        log.error("🚨 Error consultando Open-Meteo: %s", e)
        return 1

    filas = parsear(respuesta, LOCALIDADES, fecha)
    log.info("🏁 %d/%d localidades con dato para %s", len(filas), len(LOCALIDADES), fecha)

    if not filas:
        log.error("🚨 0 localidades con dato para %s — ¿fecha fuera de ventana o caída?", fecha)
        return 1

    base = Path(args.salida) / "clima"
    base.mkdir(parents=True, exist_ok=True)
    nombre_csv = f"{fecha}_clima.csv"
    ruta_csv = base / nombre_csv
    escribir_csv(filas, ruta_csv)
    log.info("💾 CSV: %s (%d filas)", ruta_csv, len(filas))

    subir_a_r2(ruta_csv, f"clima/{nombre_csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Ingesta de clima diario (Open-Meteo).")
    ap.add_argument("--salida", default="data/bronze", help="Carpeta de salida local.")
    ap.add_argument(
        "--fecha",
        help="Fecha YYYY-MM-DD a capturar (default: hoy en hora Lima). Admite backfill corto.",
    )
    args = ap.parse_args(argv)

    if args.fecha:
        try:
            date.fromisoformat(args.fecha)
        except ValueError:
            ap.error(f"--fecha inválida: {args.fecha!r} (formato esperado YYYY-MM-DD)")

    return ejecutar_ingesta_diaria(args)


if __name__ == "__main__":
    sys.exit(main())
