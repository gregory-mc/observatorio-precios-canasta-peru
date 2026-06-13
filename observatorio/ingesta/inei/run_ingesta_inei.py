"""Descarga histórica del IPC del INEI (script one-shot — issue #12).

A diferencia de los scrapers diarios (SISAP, Marketplace), esto se corre a
demanda: baja la serie mensual completa del Índice de Precios al Consumidor de
Lima Metropolitana (base Dic 2021 = 100, continua desde 1994), la guarda como
un único CSV histórico y lo sube a R2. La carga a bronze la hace después
``observatorio.carga.r2_a_supabase --fuente inei`` (reemplazo total de la tabla).

El INEI publica el archivo con un nombre que cambia cada mes
(`n01_..._lm_<mes><yy>.xlsx`) y con prefijo variable, así que la URL NO se
hardcodea: se descubre leyendo la página índice de precios.

Uso (desde la raíz del repo):
    python -m observatorio.ingesta.inei.run_ingesta_inei
"""

from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import asdict, fields
from pathlib import Path

import requests
import urllib3

from observatorio.ingesta.inei.models import IpcInei
from observatorio.ingesta.inei.parser import parsear_ipc

URL_INDICE = "https://www.inei.gob.pe/estadisticas/indice-tematico/price-indexes/"
HOST = "https://www.inei.gob.pe"
CLAVE_R2 = "inei/ipc_historico.csv"

# El portal del INEI presenta una cadena de certificados incompleta; la
# verificación TLS falla aunque el host es correcto. Se desactiva a propósito
# (sólo se descargan archivos públicos) y se silencia el aviso ruidoso.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Captura el .xlsx del IPC de Lima Metropolitana, sea cual sea el prefijo
# (`01_`, `n01_`, ...) y el sufijo de mes (`ene26`, `may26`, ...).
PATRON_ARCHIVO = re.compile(
    r"/media/[^\"']*?indice-precios_al_consumidor-lm_[a-z]{3}\d{2}\.xlsx",
    re.IGNORECASE,
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def descubrir_url_xlsx(sesion: requests.Session) -> str:
    """Lee la página índice y devuelve la URL absoluta del Excel del IPC vigente."""
    resp = sesion.get(URL_INDICE, headers=HEADERS, timeout=(15, 45), verify=False)
    resp.raise_for_status()
    match = PATRON_ARCHIVO.search(resp.text)
    if not match:
        raise RuntimeError(
            "No se encontró el enlace al Excel del IPC en la página índice del INEI; "
            "¿cambió el formato de la página?"
        )
    return HOST + match.group(0)


def descargar_xlsx(sesion: requests.Session, url: str) -> bytes:
    """Descarga el Excel y devuelve su contenido en bytes."""
    resp = sesion.get(url, headers=HEADERS, timeout=(15, 60), verify=False)
    resp.raise_for_status()
    return resp.content


def validar_cobertura(filas: list[IpcInei]) -> list[str]:
    """Valida que la serie mensual sea contigua, sin huecos ni meses duplicados.

    Devuelve la lista de periodos faltantes (vacía si la cobertura es completa).
    Imprime un reporte legible. Los duplicados se consideran fallo de parseo.
    """
    periodos = [f.periodo for f in filas]
    if not periodos:
        print("🚨 Cobertura: la serie vino vacía.")
        return ["<serie vacía>"]

    def ym(p: str) -> int:
        anio, mes = p.split("-")
        return int(anio) * 12 + int(mes) - 1

    presentes = sorted(periodos)
    duplicados = sorted({p for p in presentes if presentes.count(p) > 1})
    inicio, fin = ym(presentes[0]), ym(presentes[-1])
    esperados = set(range(inicio, fin + 1))
    faltantes_ym = sorted(esperados - {ym(p) for p in presentes})
    faltantes = [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in faltantes_ym]

    print(
        f"📈 Cobertura: {len(set(presentes))} meses, "
        f"{presentes[0]} → {presentes[-1]} "
        f"({len(esperados)} esperados)."
    )
    if duplicados:
        print(f"🚨 Periodos duplicados: {', '.join(duplicados)}")
    if faltantes:
        print(f"🚨 Periodos faltantes ({len(faltantes)}): {', '.join(faltantes)}")
    if not duplicados and not faltantes:
        print("✅ Serie contigua, sin huecos.")

    return faltantes + duplicados


def escribir_csv(filas: list[IpcInei], ruta: Path) -> None:
    """Escribe la serie como CSV con encabezado (mismo formato que los scrapers)."""
    columnas = [f.name for f in fields(IpcInei)]
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columnas)
        writer.writeheader()
        for fila in filas:
            writer.writerow(asdict(fila))


def subir_a_r2(ruta_local: Path, clave_r2: str) -> None:
    """Sube un archivo a Cloudflare R2 vía boto3 (S3-compatible).

    Si las variables R2_* no están configuradas (desarrollo local), omite la
    subida con un aviso sin fallar — igual que el scraper de SISAP.
    """
    endpoint = os.getenv("R2_ENDPOINT")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
    bucket = os.getenv("R2_BUCKET")

    if not all([endpoint, access_key, secret_key, bucket]):
        print("⚠️  R2 no configurado — se omite la subida a la nube (desarrollo local).")
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
    print(f"☁️  Subido a R2: {clave_r2}")


def ejecutar() -> int:
    print("🚀 Descarga histórica IPC — INEI (Lima Metropolitana, base Dic 2021)")

    sesion = requests.Session()
    url_xlsx = descubrir_url_xlsx(sesion)
    print(f"🔗 Excel vigente: {url_xlsx}")

    contenido = descargar_xlsx(sesion, url_xlsx)
    print(f"⬇️  Descargado: {len(contenido):,} bytes")

    filas = parsear_ipc(contenido)
    print(f"📊 Parseadas {len(filas)} filas (meses).")
    for f in filas[-3:]:
        print(f"  -> 📅 {f.periodo} | índice {f.indice:.2f} | anual {f.var_anual}")

    problemas = validar_cobertura(filas)

    base = Path(__file__).parent / "output_bronze_inei"
    base.mkdir(parents=True, exist_ok=True)
    ruta_csv = base / "ipc_historico.csv"
    escribir_csv(filas, ruta_csv)
    print(f"💾 CSV: {ruta_csv.name}")

    subir_a_r2(ruta_csv, CLAVE_R2)

    if problemas:
        print("🚨 Cobertura incompleta — revisar parser o archivo del INEI.")
        return 1
    print("🏁 Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(ejecutar())
