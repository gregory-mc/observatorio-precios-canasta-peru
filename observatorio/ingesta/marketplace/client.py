"""Cliente del catálogo de Marketplace (VTEX), endpoint legacy Catalog System:

    /api/catalog_system/pub/products/search

Filtra por categoría (``fq=C:<ruta/de/ids>``), por productId(s) (``fq``) o por
texto (``ft``). Pagina con ``_from``/``_to`` (tope ~2500). No requiere auth.

El scraper navega categorías (ver categorias.py); ``ft`` queda para uso ad-hoc.
Detalles del por qué de este endpoint y no otros (verificados en mayo 2026):
  - Una categoría con >2500 SKUs no se pagina entera: se baja por subcategorías
    con la ruta de IDs (``fq=C:431/432``). De eso se encarga categorias.py.
  - El ``ft`` debe ser **una sola palabra** (con espacios el WAF da 400
    "Scripts are not allowed!").
  - El endpoint moderno *Intelligent Search* **regionaliza**: sin región fijada
    devuelve 0 para frescos (cebolla, huevos). El legacy sí los trae.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE = "https://www.plazavea.com.pe/api/catalog_system/pub/products/search"
PAGE_SIZE = 50  # máximo que VTEX devuelve por página
MAX_OFFSET = 2500  # tope de la búsqueda paginada legacy

HEADERS = {
    "User-Agent": "observatorio-precios-canasta-peru/0.1 (ingesta diaria; contacto: repo GitHub)",
    "Accept": "application/json",
}


class VtexError(RuntimeError):
    """Fallo no recuperable al consultar la API de VTEX."""


def _request_json(
    session: requests.Session,
    url: str,
    params: dict,
    *,
    timeout: int = 30,
    intentos: int = 3,
) -> list:
    """GET con reintentos (backoff exponencial en 429/5xx). Acepta 200 y 206."""
    for intento in range(1, intentos + 1):
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            if intento == intentos:
                raise VtexError(f"fallo de red en {url}: {exc}") from exc
            time.sleep(2**intento)
            continue

        if resp.status_code in (200, 206):
            return resp.json()
        if resp.status_code == 429 or resp.status_code >= 500:
            espera = 2**intento
            log.warning(
                "VTEX %s en %s — reintento %d/%d en %ss",
                resp.status_code,
                url,
                intento,
                intentos,
                espera,
            )
            time.sleep(espera)
            continue
        raise VtexError(f"HTTP {resp.status_code} en {url}: {resp.text[:200]}")

    raise VtexError(f"agotados {intentos} intentos en {url}")


def contar(session: requests.Session, fq: str, *, timeout: int = 20) -> int:
    """Total de SKUs de un filtro, leído del header ``resources: 0-0/<total>``.
    Hace un solo request liviano (``_to=0``)."""
    resp = session.get(BASE, params={"fq": fq, "_from": 0, "_to": 0}, timeout=timeout)
    return int(resp.headers.get("resources", "0-0/0").split("/")[-1])


def buscar(
    session: requests.Session,
    *,
    ft: str | None = None,
    path: str = "",
    fq: list[str] | None = None,
    limite: int | None = None,
    pausa: float = 0.4,
) -> list[dict]:
    """Pagina una consulta hasta agotarla (o hasta ``limite``).

    - ``ft``: término de búsqueda de **una sola palabra** (sin espacios).
    - ``path``: ruta de categoría VTEX, ej. ``"Abarrotes/Arroz"``.
    - ``fq``: filtros, ej. ``["productId:101190089"]``.
    """
    if ft and " " in ft.strip():
        raise VtexError(f"ft debe ser una sola palabra (sin espacios): {ft!r}")

    productos: list[dict] = []
    desde = 0
    while desde < MAX_OFFSET:
        params: dict[str, object] = {"_from": desde, "_to": desde + PAGE_SIZE - 1}
        if ft:
            params["ft"] = ft
        if fq:
            params["fq"] = fq
        url = f"{BASE}/{path}".rstrip("/")
        pagina = _request_json(session, url, params)
        if not pagina:
            break
        productos.extend(pagina)
        if limite and len(productos) >= limite:
            return productos[:limite]
        if len(pagina) < PAGE_SIZE:
            break
        desde += PAGE_SIZE
        time.sleep(pausa)  # cortesía con el servidor
    return productos
