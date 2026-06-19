# observatorio/ingesta/sisap/run_ingesta_sisap.py

import csv
import os
import sys
import time
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from observatorio.comun.calendario import es_dia_habil_peru
from observatorio.ingesta.sisap.config import PRODUCTOS_CANASTA_BASICA
from observatorio.ingesta.sisap.models import PrecioSisap
from observatorio.ingesta.sisap.parser import parsear_html

URL_SISAP = "http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar"

# Reintentos a nivel de aplicación cuando SISAP responde 200 pero sin datos aún.
# MIDAGRI a veces publica tarde; esperamos hasta 2 veces antes de declarar fallo.
_REINTENTOS_VACIO = 2
_PAUSA_REINTENTO_S = 600  # 10 minutos
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",  # noqa: E501
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.8",
}

# (tipo_mercado, variable SISAP)
TIPOS_MERCADO = [
    ("minorista", "min_precio_prom"),
    ("mayorista", "may_precio_prom"),
]


def configurar_sesion_resiliente() -> requests.Session:
    """Sesión HTTP con reintentos automáticos ante errores 5xx del servidor estatal."""
    session = requests.Session()
    estrategia = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(max_retries=estrategia)
    session.mount("http://", adaptador)
    session.mount("https://", adaptador)
    return session


def escribir_csv(filas: list[PrecioSisap], ruta: Path) -> None:
    """Escribe la lista de PrecioSisap como CSV con encabezado."""
    columnas = [f.name for f in fields(PrecioSisap)]
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columnas)
        writer.writeheader()
        for fila in filas:
            writer.writerow(asdict(fila))


def _solicitar_filas(
    cliente: requests.Session,
    mix_params: list,
    *,
    fecha: str,
    tipo_mercado: str,
) -> list[PrecioSisap] | None:
    """Solicita datos al SISAP y parsea la respuesta.

    Reintenta hasta _REINTENTOS_VACIO veces (con pausa) si la tabla viene vacía
    — MIDAGRI a veces publica con retraso. Retorna None si hay error de red.
    """
    for intento in range(_REINTENTOS_VACIO + 1):
        try:
            response = cliente.get(URL_SISAP, params=mix_params, headers=HEADERS, timeout=(15, 45))
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"🚨 Error de conexión en {tipo_mercado}: {e}")
            return None

        filas = parsear_html(response.text, fecha_captura=fecha, tipo_mercado=tipo_mercado)
        if filas:
            return filas

        if intento < _REINTENTOS_VACIO:
            mins = _PAUSA_REINTENTO_S // 60
            print(
                f"⏳ {tipo_mercado}: tabla vacía — esperando {mins} min antes de reintentar"
                f" ({intento + 1}/{_REINTENTOS_VACIO})..."
            )
            time.sleep(_PAUSA_REINTENTO_S)

    return []


def subir_a_r2(ruta_local: Path, clave_r2: str) -> None:
    """Sube un archivo a Cloudflare R2 via boto3 (S3-compatible).

    Si las variables de entorno R2_* no están configuradas (desarrollo local),
    omite la subida con un aviso sin fallar.
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


def ejecutar_ingesta_diaria() -> None:
    # Modo de prueba: fuerza fallo intencional para verificar que la alerta funciona
    if os.getenv("SIMULAR_FALLO", "false").lower() == "true":
        print("🧪 SIMULAR_FALLO=true — forzando fallo intencional para prueba de alertas.")
        sys.exit(1)

    # Sincronización horaria con Perú (UTC-5)
    hora_peru = datetime.utcnow() - timedelta(hours=5)
    str_fecha = hora_peru.strftime("%d/%m/%Y")
    str_archivo = hora_peru.strftime("%Y-%m-%d")
    str_desde = hora_peru.replace(day=1).strftime("%d/%m/%Y")
    str_hasta = str_fecha

    # Salida temprana si MIDAGRI no publica hoy (fin de semana o feriado peruano)
    if not es_dia_habil_peru(hora_peru.date()):
        nombre_dia = hora_peru.strftime("%A %d/%m/%Y")
        print(f"📅 {nombre_dia} — día no hábil, SISAP no publica. Saltando sin error.")
        sys.exit(0)

    print("🚀 Iniciando Pipeline Bronze - SISAP (minorista + mayorista)")
    print(f"📅 Fecha objetivo Perú: {str_fecha}")
    print(f"📊 Parámetros: Desde {str_desde} hasta {str_hasta}")
    print(f"📦 {len(PRODUCTOS_CANASTA_BASICA)} productos por request")

    # Carpeta de salida local
    base = Path(__file__).parent / "output_bronze_sisap"
    base.mkdir(parents=True, exist_ok=True)

    payload_productos = [("productos[]", pid) for pid in PRODUCTOS_CANASTA_BASICA]
    cliente = configurar_sesion_resiliente()
    total_exitosos = 0
    mercados_con_error: list[str] = []  # error de red/HTTP → fallo real
    mercados_vacios: list[str] = []     # tabla vacía → ausencia legítima (cadencia de la fuente)

    for tipo_mercado, variable in TIPOS_MERCADO:
        print(f"\n📡 Solicitando precios {tipo_mercado.upper()}...")

        params = {
            "region": "150000",
            "variables[]": variable,
            "fecha": str_fecha,
            "desde": str_desde,
            "hasta": str_hasta,
            "anios[]": hora_peru.strftime("%Y"),
            "meses[]": hora_peru.strftime("%m"),
            "periodicidad": "dia",
            "__ajax_carga_final": "consulta",
            "ajax": "true",
        }
        mix_params = list(params.items()) + payload_productos

        filas = _solicitar_filas(
            cliente, mix_params, fecha=str_archivo, tipo_mercado=tipo_mercado
        )
        filas_con_precio = [f for f in filas if f.precio_prom is not None] if filas else []

        if filas is None:
            # Error de red irrecuperable → fallo real
            mercados_con_error.append(tipo_mercado)
            continue

        if not filas:
            # Tabla vacía: MIDAGRI publica el minorista de forma interdiaria, así que
            # la ausencia de datos no es un fallo si el otro mercado sí cargó. Se trata
            # como warning; la decisión de alertar se toma al final del pipeline.
            print(
                f"⚠️  Tabla vacía en {tipo_mercado}"
                f" — sin datos tras {_REINTENTOS_VACIO} reintentos."
            )
            mercados_vacios.append(tipo_mercado)
            continue

        # Data quality: tabla con filas pero ningún precio disponible
        if not filas_con_precio:
            print(
                f"⚠️  {tipo_mercado.capitalize()}: tabla con {len(filas)} filas"
                " pero 0 precios disponibles."
            )

        # Escribir CSV
        nombre_csv = f"{str_archivo}_sisap_lima_{tipo_mercado}.csv"
        ruta_csv = base / nombre_csv
        escribir_csv(filas, ruta_csv)

        print(
            f"✅ {tipo_mercado.capitalize()}:"
            f" {len(filas_con_precio)}/{len(filas)} productos con precio"
        )
        print(f"💾 CSV: {nombre_csv}")

        # Data Quality preview
        print(f"🔍 Muestra {tipo_mercado}:")
        for fila in [f for f in filas if f.precio_prom is not None][:3]:
            print(f"  -> 📦 {fila.producto:<40} | 💰 S/. {fila.precio_prom}")

        # Subir CSV a R2
        subir_a_r2(ruta_csv, f"sisap/{nombre_csv}")

        total_exitosos += 1

    total_mercados = len(TIPOS_MERCADO)
    print(f"\n🏁 Pipeline finalizado: {total_exitosos}/{total_mercados} requests exitosos.")

    if mercados_vacios:
        print(
            f"ℹ️  Mercados sin datos hoy (cadencia de la fuente): {', '.join(mercados_vacios)}"
        )

    # Alertar solo ante un fallo real: error de red en algún mercado, o ningún
    # mercado con datos (probable caída de la fuente). Un mercado vacío mientras
    # el otro carga es normal — el minorista del SISAP se publica interdiario.
    if mercados_con_error:
        print(f"🚨 Mercados con error de red: {', '.join(mercados_con_error)}")
        print("   → Verificar disponibilidad del SISAP o conexión del runner.")
        sys.exit(1)

    if total_exitosos == 0:
        print("🚨 Ningún mercado devolvió datos — probable caída de la fuente.")
        print("   → Verificar disponibilidad del SISAP.")
        sys.exit(1)


if __name__ == "__main__":
    ejecutar_ingesta_diaria()
