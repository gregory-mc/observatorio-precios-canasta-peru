"""Backtesting batch: valida Prophet vs baselines y aterriza métricas — M4 (ml-4).

Carga las series de ``gold.fct_precio_diario`` (SISAP por defecto), corre el
walk-forward de cada modelo (Prophet, media móvil, naive) sobre los mismos
cortes, y escribe una fila de métricas por (serie, modelo) en
``ml.backtest_metricas``. Al final loguea el veredicto: en cuántas series Prophet
le gana al mejor baseline por MAPE.

Uso (requiere `pip install -e ".[ml]"` y SUPABASE_DB_URL):
    python -m observatorio.ml.run_backtesting
    python -m observatorio.ml.run_backtesting --fuente sisap_minorista --horizonte 7
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import config
from .backtesting import ResultadoBacktest, comparar_serie
from .datos import Serie, cargar_series
from .persistencia import escribir_backtest_metricas

log = logging.getLogger("ml.backtesting")
LIMA = timezone(timedelta(hours=-5))


def fecha_hoy() -> date:
    """Fecha actual en hora de Lima (UTC-5), igual criterio que el resto de la capa."""
    return datetime.now(LIMA).date()


def evaluar_todas(series: list[Serie], horizonte: int) -> pd.DataFrame:
    """Corre el backtest de cada serie y devuelve un DataFrame de métricas.

    Una fila por (serie, modelo). Las series sin cortes válidos (poca historia)
    aportan 0 filas. Se añade ``horizonte`` como columna para el contrato de
    persistencia.
    """
    resultados: list[ResultadoBacktest] = []
    for serie in series:
        resultados.extend(comparar_serie(serie, horizonte=horizonte))

    if not resultados:
        return pd.DataFrame()

    df = pd.DataFrame(r.__dict__ for r in resultados)
    df["horizonte"] = horizonte
    return df


def _loguear_veredicto(df: pd.DataFrame) -> None:
    """Loguea en cuántas series Prophet le gana al mejor baseline por MAPE."""
    clave = ["fuente", "cod_departamento", "producto"]
    ganador_prophet = 0
    total = 0
    for _, grupo in df.groupby(clave, dropna=False):
        mapes = grupo.set_index("modelo")["mape"]
        if "prophet" not in mapes.index:
            continue
        total += 1
        baselines = mapes.drop("prophet", errors="ignore")
        if baselines.empty or mapes["prophet"] <= baselines.min():
            ganador_prophet += 1
    if total:
        log.info(
            "🏆 Prophet le gana (o iguala) al mejor baseline en %d/%d series (MAPE)",
            ganador_prophet,
            total,
        )
    else:
        log.info("ℹ️  Ninguna serie con Prophet evaluable (historia insuficiente).")


def ejecutar(args: argparse.Namespace) -> int:
    fecha_corrida = date.fromisoformat(args.fecha_corrida) if args.fecha_corrida else fecha_hoy()
    fuentes = args.fuente or list(config.FUENTES_MODELADAS)

    log.info("🚀 Backtesting — corrida %s · fuentes: %s", fecha_corrida, ", ".join(fuentes))
    series = cargar_series(fuentes=fuentes, db_url=args.db_url)
    if not series:
        log.error("🚨 0 series cargadas — ¿está poblada gold.fct_precio_diario?")
        return 1

    metricas = evaluar_todas(series, horizonte=args.horizonte)
    if metricas.empty:
        log.error("🚨 0 series con historia suficiente para backtesting.")
        return 1

    _loguear_veredicto(metricas)
    n = escribir_backtest_metricas(metricas, fecha_corrida, db_url=args.db_url)
    log.info("💾 %d filas escritas en ml.backtest_metricas (corrida %s)", n, fecha_corrida)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Backtesting walk-forward (Prophet vs baseline)")
    ap.add_argument("--fuente", action="append", help="Fuente a evaluar (repetible).")
    ap.add_argument(
        "--fecha-corrida", help="Fecha de la corrida (YYYY-MM-DD). Default: hoy (Lima)."
    )
    ap.add_argument(
        "--horizonte",
        type=int,
        default=config.HORIZONTE_DIAS,
        help=f"Días pronosticados por fold (default: {config.HORIZONTE_DIAS}).",
    )
    ap.add_argument("--db-url", help="Connection string Postgres. Default: SUPABASE_DB_URL.")
    return ejecutar(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
