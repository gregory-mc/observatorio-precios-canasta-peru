"""Ingesta diaria Bronze - OSINERGMIN (precios de combustible, Facilito).

Recorre, con navegador headless (ver ``client.py``), el buscador de Estaciones de
Servicio de Facilito por (departamento × provincia × producto) y baja todos los
grifos con su precio. Escribe un CSV (una fila por grifo × producto) y lo respalda
en Cloudflare R2, de donde ``observatorio.carga.r2_a_supabase`` lo carga a
``bronze.osinergmin_precios``. La agregación a precio por departamento/distrito es
trabajo de la capa silver (dbt).

Idempotente por fecha: re-correr el mismo día sobreescribe el CSV en R2, y la
carga borra las filas de esa fecha antes de reinsertar.

Uso (desde la raíz del repo; requiere `pip install playwright` + `playwright install chromium`):
    PYTHONPATH=. python3 -m observatorio.ingesta.osinergmin.run_ingesta_osinergmin
    # un solo departamento (debug):           --departamento 240000
    # navegador visible + 1 provincia (debug): --headful --limite-provincias 1
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .client import RecaptchaRechazado, SesionFacilito
from .config import DEPARTAMENTOS, PRODUCTOS
from .models import PrecioCombustible
from .parser import parsear_html

log = logging.getLogger("osinergmin")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> str:
    """Fecha actual en hora de Lima (UTC-5), igual criterio que los demás scrapers."""
    return datetime.now(LIMA).strftime("%Y-%m-%d")


def escribir_csv(filas: list[PrecioCombustible], ruta: Path) -> None:
    """Escribe la lista de PrecioCombustible como CSV con encabezado."""
    columnas = [f.name for f in fields(PrecioCombustible)]
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columnas)
        writer.writeheader()
        for fila in filas:
            writer.writerow(asdict(fila))


def subir_a_r2(ruta_local: Path, clave_r2: str) -> None:
    """Sube un archivo a Cloudflare R2 via boto3 (S3-compatible).

    Si las variables R2_* no están configuradas (desarrollo local), omite la
    subida con un aviso sin fallar.
    """
    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    if not all([endpoint, access_key, secret_key, bucket]):
        log.warning("R2 no configurado — se omite la subida a la nube (desarrollo local).")
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


def recolectar(
    sesion: SesionFacilito,
    *,
    fecha: str,
    departamentos: dict[str, str],
    limite_provincias: int | None = None,
) -> tuple[list[PrecioCombustible], list[str]]:
    """Recorre departamento × provincia × producto y devuelve (filas, errores).

    Un fallo puntual (timeout, reCAPTCHA rechazado en una consulta) se registra y
    no aborta el recorrido: se sigue con el resto. Devuelve la lista de errores
    para que el orquestador decida si el run fue exitoso.
    """
    filas: list[PrecioCombustible] = []
    errores: list[str] = []

    for cod_dep, nombre_dep in departamentos.items():
        try:
            provincias = sesion.abrir_departamento(cod_dep)
        except RecaptchaRechazado:
            log.error("🚨 %s: reCAPTCHA rechazado al abrir el departamento.", nombre_dep)
            errores.append(f"{nombre_dep}: recaptcha")
            continue
        except Exception as e:  # noqa: BLE001 — un departamento caído no debe tumbar el run
            log.error("🚨 %s: error al abrir el departamento: %s", nombre_dep, e)
            errores.append(f"{nombre_dep}: {type(e).__name__}")
            continue

        if limite_provincias is not None:
            provincias = provincias[:limite_provincias]

        log.info("📍 %s: %d provincias", nombre_dep, len(provincias))
        filas_dep = 0
        for cod_prov, nombre_prov in provincias:
            for cod_prod, nombre_prod in PRODUCTOS.items():
                etiqueta = f"{nombre_dep}/{nombre_prov}/{nombre_prod}"
                try:
                    html = sesion.consultar(cod_prov, cod_prod)
                except Exception as e:  # noqa: BLE001
                    log.warning("  ⚠️  %s: %s", etiqueta, type(e).__name__)
                    errores.append(etiqueta)
                    continue
                nuevas = parsear_html(
                    html,
                    fecha_captura=fecha,
                    departamento=nombre_dep,
                    provincia=nombre_prov,
                    producto=nombre_prod,
                    producto_codigo=cod_prod,
                )
                filas.extend(nuevas)
                filas_dep += len(nuevas)
        log.info("  ✅ %s: %d filas", nombre_dep, filas_dep)

    return filas, errores


def ejecutar_ingesta_diaria(args: argparse.Namespace) -> int:
    # Modo de prueba: fuerza fallo intencional para verificar la alerta.
    if os.getenv("SIMULAR_FALLO", "false").lower() == "true":
        log.error("🧪 SIMULAR_FALLO=true — forzando fallo intencional para prueba de alertas.")
        return 1

    fecha = fecha_hoy()

    if args.departamento:
        if args.departamento not in DEPARTAMENTOS:
            log.error("Departamento desconocido: %s", args.departamento)
            return 1
        departamentos = {args.departamento: DEPARTAMENTOS[args.departamento]}
    else:
        departamentos = DEPARTAMENTOS

    log.info("🚀 Iniciando Pipeline Bronze - OSINERGMIN (Facilito)")
    log.info("📅 Fecha objetivo Perú: %s", fecha)
    log.info("🗺️  %d departamento(s) × %d producto(s)", len(departamentos), len(PRODUCTOS))

    with SesionFacilito(headless=not args.headful) as sesion:
        filas, errores = recolectar(
            sesion,
            fecha=fecha,
            departamentos=departamentos,
            limite_provincias=args.limite_provincias,
        )

    con_precio = [f for f in filas if f.precio_soles_galon is not None]
    log.info(
        "🏁 Recolección: %d filas (%d con precio), %d errores",
        len(filas),
        len(con_precio),
        len(errores),
    )

    if not filas:
        log.error("🚨 0 filas recolectadas — probable bloqueo de reCAPTCHA o caída de Facilito.")
        return 1

    # Salida local + CSV
    base = Path(args.salida) / "osinergmin"
    base.mkdir(parents=True, exist_ok=True)
    nombre_csv = f"{fecha}_osinergmin_combustibles.csv"
    ruta_csv = base / nombre_csv
    escribir_csv(filas, ruta_csv)
    log.info("💾 CSV: %s (%d filas)", ruta_csv, len(filas))

    # Muestra para data quality
    for fila in con_precio[:3]:
        log.info(
            "  -> ⛽ %s | %s | S/. %s",
            fila.producto,
            fila.establecimiento[:40],
            fila.precio_soles_galon,
        )

    subir_a_r2(ruta_csv, f"osinergmin/{nombre_csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="Scraper de precios de combustible (OSINERGMIN/Facilito)"
    )
    ap.add_argument(
        "--salida",
        default="data/bronze",
        help="Carpeta de salida local (default: data/bronze).",
    )
    ap.add_argument("--departamento", help="Código Facilito de un solo departamento (debug).")
    ap.add_argument(
        "--limite-provincias",
        type=int,
        default=None,
        help="Máx provincias por departamento (debug).",
    )
    ap.add_argument("--headful", action="store_true", help="Mostrar el navegador (debug).")
    args = ap.parse_args(argv)

    return ejecutar_ingesta_diaria(args)


if __name__ == "__main__":
    sys.exit(main())
