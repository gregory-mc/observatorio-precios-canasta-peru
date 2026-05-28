"""Scraper diario del catálogo de alimentos de Marketplace (API VTEX, Marketplace).

Navega las categorías de alimento (ver categorias.py) y baja todos los SKUs con
su precio, unidad y categoría. NO cruza con la canasta SISAP: ese join es trabajo
de la capa silver/dbt, usando observatorio/ingesta/canasta_productos.json.

Uso (desde la raíz del repo; sin instalar el paquete, de ahí el PYTHONPATH=.):
    PYTHONPATH=. python3 -m observatorio.ingesta.marketplace.scrape
    PYTHONPATH=. python3 -m observatorio.ingesta.marketplace.scrape --salida data/bronze

Por corrida escribe dos artefactos (idempotentes por fecha — re-correr el mismo
día sobreescribe):
  - <salida>/marketplace/raw/<fecha>.json  -> productos crudos (bronze inmutable)
  - <salida>/marketplace/<fecha>.csv       -> filas aplanadas (una por SKU)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .categorias import categorias_a_navegar
from .client import HEADERS, buscar
from .models import ProductoPrecio
from .parser import aplanar
from .relevancia import es_alimento

log = logging.getLogger("marketplace")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> str:
    return datetime.now(LIMA).strftime("%Y-%m-%d")


def recolectar(
    session: requests.Session,
    *,
    fecha: str,
    limite: int | None = None,
) -> tuple[list[dict], list[ProductoPrecio]]:
    """Navega las categorías de alimento y devuelve (productos crudos, filas).

    Deduplica productos por productId (uno puede caer en varias categorías).
    """
    objetivos = categorias_a_navegar(session)
    log.info("categorías a navegar: %d", len(objetivos))

    crudos: list[dict] = []
    filas: list[ProductoPrecio] = []
    vistos: set[str] = set()
    for fq, etiqueta in objetivos:
        productos = buscar(session, fq=[fq], limite=limite)
        nuevos = 0
        for p in productos:
            pid = str(p.get("productId", ""))
            if pid in vistos:
                continue
            vistos.add(pid)
            crudos.append(p)  # raw (bronze) conserva todo
            # el CSV aplanado se queda solo con alimentos; el raw mantiene todo
            filas.extend(
                f
                for f in aplanar(p, fecha_captura=fecha, consulta=etiqueta)
                if es_alimento(f.categoria)
            )
            nuevos += 1
        log.info("%s -> %d productos (%d nuevos)", etiqueta, len(productos), nuevos)
    return crudos, filas


def escribir(crudos: list[dict], filas: list[ProductoPrecio], salida: Path, *, fecha: str) -> None:
    base = salida / "marketplace"
    (base / "raw").mkdir(parents=True, exist_ok=True)

    (base / "raw" / f"{fecha}.json").write_text(
        json.dumps(crudos, ensure_ascii=False), encoding="utf-8"
    )

    csv_path = base / f"{fecha}.csv"
    columnas = [f.name for f in fields(ProductoPrecio)]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columnas)
        writer.writeheader()
        for fila in filas:
            writer.writerow(asdict(fila))
    log.info("escrito %s (%d filas) + raw/%s.json", csv_path, len(filas), fecha)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Scraper del catálogo de alimentos de Marketplace")
    ap.add_argument("--salida", type=Path, default=Path("data/bronze"))
    ap.add_argument("--limite", type=int, default=None, help="Máx SKUs por categoría (debug).")
    args = ap.parse_args(argv)

    fecha = fecha_hoy()
    with requests.Session() as session:
        session.headers.update(HEADERS)
        crudos, filas = recolectar(session, fecha=fecha, limite=args.limite)

    if not filas:
        log.error("0 filas recolectadas — posible cambio/bloqueo de la API. Falla intencional.")
        return 1

    escribir(crudos, filas, args.salida, fecha=fecha)
    log.info("OK: %d productos, %d filas SKU", len(crudos), len(filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
