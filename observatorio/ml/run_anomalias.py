"""Detección batch de anomalías de precio → ml.anomalias_raw — M4 (ml-5).

Carga las series de ``gold.fct_precio_diario`` (SISAP por defecto), marca en cada
una los días con residuo normalizado > ``config.UMBRAL_SIGMA`` (ver
``anomalias.py``) y aterriza los días anómalos en ``ml.anomalias_raw``,
idempotente por corrida. A partir de esa tabla dbt construye ``gold.fct_anomalias``.

Uso (requiere `pip install -e ".[ml]"` y SUPABASE_DB_URL):
    python -m observatorio.ml.run_anomalias
    python -m observatorio.ml.run_anomalias --fuente sisap_minorista --sigma 3.0
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import config
from .anomalias import METODO, detectar_anomalias_serie
from .datos import Serie, cargar_series
from .persistencia import escribir_anomalias

log = logging.getLogger("ml.anomalias")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> date:
    """Fecha actual en hora de Lima (UTC-5), igual criterio que el resto de la capa."""
    return datetime.now(LIMA).date()


def detectar_todas(series: list[Serie], umbral: float) -> pd.DataFrame:
    """Detecta anomalías en cada serie y devuelve un DataFrame con la identidad.

    Una fila por día anómalo, con ``fuente``, ``cod_departamento``, ``producto``,
    ``metodo`` y ``umbral_sigma`` adjuntos. Series sin anomalías aportan 0 filas.
    """
    marcos: list[pd.DataFrame] = []
    for serie in series:
        anom = detectar_anomalias_serie(serie, umbral=umbral)
        if anom.empty:
            continue
        marcos.append(
            anom.assign(
                fuente=serie.fuente,
                cod_departamento=serie.cod_departamento,
                producto=serie.producto,
                metodo=METODO,
                umbral_sigma=umbral,
            )
        )

    if not marcos:
        return pd.DataFrame()
    return pd.concat(marcos, ignore_index=True)


def ejecutar(args: argparse.Namespace) -> int:
    fecha_corrida = date.fromisoformat(args.fecha_corrida) if args.fecha_corrida else fecha_hoy()
    fuentes = args.fuente or list(config.FUENTES_MODELADAS)

    log.info(
        "🚀 Detección de anomalías — corrida %s · fuentes: %s · umbral %.1fσ",
        fecha_corrida,
        ", ".join(fuentes),
        args.sigma,
    )
    series = cargar_series(fuentes=fuentes, db_url=args.db_url)
    if not series:
        log.error("🚨 0 series cargadas — ¿está poblada gold.fct_precio_diario?")
        return 1

    anomalias = detectar_todas(series, umbral=args.sigma)
    if anomalias.empty:
        log.info("✅ 0 anomalías detectadas; nada que escribir para la corrida.")
        return 0

    n = escribir_anomalias(anomalias, fecha_corrida, db_url=args.db_url)
    log.info("💾 %d anomalías escritas en ml.anomalias_raw (corrida %s)", n, fecha_corrida)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Detección de anomalías de precio (residuo > Nσ)")
    ap.add_argument("--fuente", action="append", help="Fuente a evaluar (repetible).")
    ap.add_argument(
        "--fecha-corrida", help="Fecha de la corrida (YYYY-MM-DD). Default: hoy (Lima)."
    )
    ap.add_argument(
        "--sigma",
        type=float,
        default=config.UMBRAL_SIGMA,
        help=f"Umbral de σ para marcar anomalía (default: {config.UMBRAL_SIGMA}).",
    )
    ap.add_argument("--db-url", help="Connection string Postgres. Default: SUPABASE_DB_URL.")
    return ejecutar(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
