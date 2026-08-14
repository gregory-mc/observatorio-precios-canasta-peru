"""Catálogo de estaciones de SENAMHI y curación al subset de interés (issue #14).

El catálogo completo viene embebido en el HTML del mapa como ``var PruebaTest =
[ {...}, {...} ]`` (≈981 estaciones). Este módulo lo descarga, lo parsea a objetos
``Estacion`` y filtra el **subset curado**: estaciones meteorológicas, con dato
fresco, dentro de las regiones productoras de la canasta (ver ``config``).

El parseo es tolerante a propósito: el array es *casi* JSON (a veces una entrada
trae una comilla suelta o un valor sin comillas que rompe ``json.loads`` sobre el
array entero), así que se parsea objeto por objeto con fallback a regex de campo.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

import requests

from .config import (
    ESTADOS_FRESCOS,
    REGIONES_PRODUCTORAS,
    TIMEOUT,
    TIPO_METEOROLOGICA,
    URL_MAPA,
    USER_AGENT,
)
from .models import Estacion

log = logging.getLogger("senamhi.catalogo")

_RE_ARRAY = re.compile(r"var\s+PruebaTest\s*=\s*(\[.*?\])\s*;", re.S)
_RE_OBJETO = re.compile(r"\{[^{}]*\}")


def descargar_html_mapa(session: requests.Session | None = None) -> str:
    """Descarga el HTML del mapa (que embebe el catálogo).

    Usa ``verify=False`` por la cadena TLS incompleta del portal (mismo caso que
    INEI; ver docs/sources.md). Requiere IP peruana (geo-bloqueo de datacenter).
    """
    ses = session or requests.Session()
    # El portal presenta una cadena de certificados incompleta; silenciamos el
    # warning para no ensuciar los logs del cron (solo datos públicos).
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    resp = ses.get(URL_MAPA, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, verify=False)
    resp.raise_for_status()
    return resp.text


def _campo(objeto: str, clave: str) -> str:
    """Extrae el valor de ``clave`` de un objeto JS suelto (fallback sin JSON)."""
    m = re.search(rf"['\"]?{clave}['\"]?\s*:\s*['\"]?([^,'\"}}]*)", objeto)
    return m.group(1).strip() if m else ""


def _a_estacion(objeto: str) -> Estacion | None:
    """Convierte un objeto JS (``{...}``) del catálogo en ``Estacion``.

    Intenta ``json.loads`` (las claves vienen entrecomilladas) y cae a regex de
    campo si el objeto trae alguna irregularidad. Descarta objetos sin código o
    sin coordenadas numéricas.
    """
    datos: dict = {}
    try:
        datos = json.loads(objeto)
    except (json.JSONDecodeError, ValueError):
        datos = {}

    def val(clave: str) -> str:
        if datos:
            v = datos.get(clave, "")
            return "" if v is None else str(v).strip()
        return _campo(objeto, clave)

    cod = val("cod")
    if not cod:
        return None
    try:
        lat = float(val("lat"))
        lon = float(val("lon"))
    except ValueError:
        return None

    return Estacion(
        cod=cod,
        cod_old=val("cod_old"),
        nombre=val("nom"),
        categoria=val("cate"),
        tipo=val("ico"),
        estado=val("estado"),
        lat=lat,
        lon=lon,
    )


def parsear_catalogo(html: str) -> list[Estacion]:
    """Extrae y parsea el catálogo completo de estaciones del HTML del mapa."""
    m = _RE_ARRAY.search(html)
    if not m:
        raise ValueError("No se encontró 'var PruebaTest = [...]' en el HTML del mapa.")
    estaciones = [e for obj in _RE_OBJETO.findall(m.group(1)) if (e := _a_estacion(obj))]
    log.info("catálogo SENAMHI: %d estaciones parseadas", len(estaciones))
    return estaciones


def region_productora(lat: float, lon: float) -> str | None:
    """Devuelve el nombre de la primera región productora que contiene el punto."""
    for nombre, (lat_min, lat_max, lon_min, lon_max) in REGIONES_PRODUCTORAS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return nombre
    return None


def es_relevante(est: Estacion) -> bool:
    """Estación meteorológica con dato fresco (ignora hidrológicas y diferidas)."""
    return est.tipo == TIPO_METEOROLOGICA and est.estado in ESTADOS_FRESCOS


def curar(estaciones: list[Estacion]) -> list[Estacion]:
    """Filtra al subset curado y anota la ``region`` de cada estación.

    Se queda con estaciones meteorológicas, de dato fresco (AUTOMATICA/REAL) y
    dentro de alguna región productora de la canasta.
    """
    curadas: list[Estacion] = []
    for est in estaciones:
        if not es_relevante(est):
            continue
        region = region_productora(est.lat, est.lon)
        if region is None:
            continue
        curadas.append(replace(est, region=region))
    log.info("subset curado SENAMHI: %d de %d estaciones", len(curadas), len(estaciones))
    return curadas


def obtener_catalogo_curado(session: requests.Session | None = None) -> list[Estacion]:
    """Descarga, parsea y cura el catálogo en un solo paso."""
    return curar(parsear_catalogo(descargar_html_mapa(session)))


def main() -> int:
    """CLI de inspección: imprime el subset curado (para ops/review, no ingesta)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    curadas = obtener_catalogo_curado()
    from collections import Counter

    print(f"\nSubset curado: {len(curadas)} estaciones")
    print("por región:", dict(Counter(e.region for e in curadas)))
    print("por estado:", dict(Counter(e.estado for e in curadas)))
    for e in sorted(curadas, key=lambda x: (x.region or "", x.nombre)):
        print(f"  [{e.region:18}] {e.cod:10} {e.estado:10} {e.categoria:5} {e.nombre}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
