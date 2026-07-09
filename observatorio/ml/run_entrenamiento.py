"""Entrenamiento batch de pronósticos de precio — Milestone M4 (ml-3).

Lee las series de ``gold.fct_precio_diario`` (SISAP por defecto), pronostica cada
una —Prophet si tiene historia holgada, media móvil si no— y aterriza el
resultado en ``ml.predicciones_raw``, idempotente por corrida. A partir de esa
tabla dbt construye el mart ``gold.fct_predicciones`` (PR posterior).

Uso (desde la raíz del repo; requiere `pip install -e ".[ml]"` y SUPABASE_DB_URL):
    python -m observatorio.ml.run_entrenamiento
    python -m observatorio.ml.run_entrenamiento --fuente sisap_minorista
    python -m observatorio.ml.run_entrenamiento --fecha-corrida 2026-07-01 --horizonte 7
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import config
from .datos import Serie, cargar_series
from .persistencia import escribir_predicciones
from .prophet_modelo import pronosticar_serie

log = logging.getLogger("ml.entrenamiento")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> date:
    """Fecha actual en hora de Lima (UTC-5), igual criterio que los scrapers."""
    return datetime.now(LIMA).date()


def entrenar_todas(series: list[Serie], horizonte: int = config.HORIZONTE_DIAS) -> pd.DataFrame:
    """Pronostica cada serie y devuelve un único DataFrame con la identidad adjunta.

    Una serie que falle al pronosticar (p.ej. Prophet no converge) se registra y
    se omite, sin abortar el batch — igual criterio de resiliencia que los
    scrapers. El DataFrame resultante trae, además de las columnas de pronóstico,
    ``fuente``, ``cod_departamento`` y ``producto``.
    """
    marcos: list[pd.DataFrame] = []
    for serie in series:
        try:
            pred = pronosticar_serie(serie, horizonte)
        except Exception as e:  # noqa: BLE001 — una serie caída no tumba el batch
            log.warning("⚠️  %s: falló el pronóstico (%s)", serie.clave, type(e).__name__)
            continue
        pred = pred.assign(
            fuente=serie.fuente,
            cod_departamento=serie.cod_departamento,
            producto=serie.producto,
        )
        marcos.append(pred)

    if not marcos:
        return pd.DataFrame()
    return pd.concat(marcos, ignore_index=True)


def ejecutar(args: argparse.Namespace) -> int:
    fecha_corrida = (
        date.fromisoformat(args.fecha_corrida) if args.fecha_corrida else fecha_hoy()
    )
    fuentes = args.fuente or list(config.FUENTES_MODELADAS)

    log.info("🚀 Entrenamiento de pronósticos — corrida %s", fecha_corrida)
    log.info("📊 Fuentes: %s · horizonte: %dd", ", ".join(fuentes), args.horizonte)

    series = cargar_series(fuentes=fuentes, db_url=args.db_url)
    modelables = sum(s.es_modelable() for s in series)
    log.info("📈 %d series (%d modelables con Prophet, resto baseline)", len(series), modelables)

    if not series:
        log.error("🚨 0 series cargadas — ¿está poblada gold.fct_precio_diario?")
        return 1

    predicciones = entrenar_todas(series, horizonte=args.horizonte)
    if predicciones.empty:
        log.error("🚨 0 pronósticos generados.")
        return 1

    n = escribir_predicciones(predicciones, fecha_corrida, db_url=args.db_url)
    log.info("💾 %d filas escritas en ml.predicciones_raw (corrida %s)", n, fecha_corrida)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="Entrenamiento batch de pronósticos (Prophet/baseline)"
    )
    ap.add_argument(
        "--fuente",
        action="append",
        help="Fuente a modelar (repetible). Default: las de config.FUENTES_MODELADAS.",
    )
    ap.add_argument(
        "--fecha-corrida",
        help="Fecha de la corrida (YYYY-MM-DD). Default: hoy (Lima).",
    )
    ap.add_argument(
        "--horizonte",
        type=int,
        default=config.HORIZONTE_DIAS,
        help=f"Días a pronosticar (default: {config.HORIZONTE_DIAS}).",
    )
    ap.add_argument("--db-url", help="Connection string Postgres. Default: SUPABASE_DB_URL.")
    args = ap.parse_args(argv)

    return ejecutar(args)


if __name__ == "__main__":
    sys.exit(main())
