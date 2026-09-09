"""Construcción de `gold.canasta_consumo_dept` desde la ENAHO — issue #19.

One-shot que lee el Módulo 601 (Gastos en Alimentos y Bebidas) de una ENAHO,
deriva el **peso de cada producto del MVP por departamento** ponderando por el
factor de expansión, y persiste el agregado a `gold.canasta_consumo_dept`.

Implementa el contrato de docs/canasta_consumo_dept.md (deliverable de #17). La
lógica de agregación (`construir_pesos`) es pura y testeable sin `.dta` ni base;
la lectura del `.dta` y la carga idempotente viven en las funciones de IO.

Metodología (resumen; ver el doc para el detalle de decisiones):
  1. Mapear `p601a` → producto MVP por grupo de 2 dígitos, excluyendo procesados.
  2. `cod_departamento` = 2 primeros dígitos del `ubigeo`.
  3. Agregar por `(anio_enaho, cod_departamento, producto)` ponderando por `factor07`.
  4. Normalizar el peso dentro del MVP (Σ pesos = 1.0 por departamento), base
     `i601c` (gasto monetario de compra).

Uso (desde IP peruana, con los `.dta` ya descargados por el notebook #13):
    python -m observatorio.canasta.construir_canasta --anio 2023 \\
        --dta data/enaho/enaho01-2023-601.dta --dry-run
    python -m observatorio.canasta.construir_canasta --anio 2023 \\
        --dta data/enaho/enaho01-2023-601.dta            # carga a gold

Variables de entorno (solo para la carga, no para --dry-run):
    SUPABASE_DB_URL  → connection string Postgres del pooler de Supabase.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys

import pandas as pd

from observatorio.canasta.dim_departamento import (
    CODIGOS_DEPARTAMENTO,
    nombre_departamento,
)
from observatorio.canasta.productos import (
    MVP_GRUPOS,
    PRODUCTOS_CANASTA,
    PRODUCTOS_MVP,
    mapear_producto,
)
from observatorio.validacion.runner import (
    ClaveUnica,
    ColumnasPresentes,
    EnConjunto,
    EnRango,
    MinFilas,
    NoNulo,
    Predicado,
    Suite,
    validar_o_error,
)

log = logging.getLogger("canasta")

# Columnas del Módulo 601 que necesitamos (nombres en minúscula, ver docs/enaho.md).
COL_HOGAR = ["conglome", "vivienda", "hogar"]
COL_REQUERIDAS = [
    *COL_HOGAR,
    "ubigeo",
    "p601a",
    "i601c",  # gasto monetario de compra (anualizado)
    "i601e",  # autoconsumo / obtenido sin compra (anualizado)
    "i601b2",  # kg comprados (anualizado)
    "factor07",  # factor de expansión anual
]

# Columnas de gold.canasta_consumo_dept en orden de COPY (computed_at usa DEFAULT).
COLUMNAS_GOLD = [
    "anio_enaho",
    "cod_departamento",
    "departamento",
    "producto",
    "grupo_enaho",
    "gasto_monetario_anual",
    "gasto_total_anual",
    "cantidad_kg_anual",
    "n_muestra",
    "hogares_expandidos",
    "peso_canasta",
    "fuente",
]

# Umbral de soporte muestral por debajo del cual una celda es de baja confianza
# (docs/canasta_consumo_dept.md §7): no se borra, se reporta como advertencia.
N_MUESTRA_MINIMA = 30

# Rango plausible de precio implícito (S/ por kg) para detectar errores de unidad.
PRECIO_IMPLICITO_MIN = 0.1
PRECIO_IMPLICITO_MAX = 100.0


# --------------------------------------------------------------------------- #
# Núcleo: agregación pura (testeable sin .dta ni base)
# --------------------------------------------------------------------------- #
def construir_pesos(
    df_601: pd.DataFrame, anio_enaho: int, *, fuente: str | None = None
) -> pd.DataFrame:
    """Agrega el Módulo 601 a pesos de canasta por departamento.

    Recibe un DataFrame con las columnas de ``COL_REQUERIDAS`` (minúscula) y
    devuelve uno con el esquema de ``gold.canasta_consumo_dept`` (sin ``computed_at``).
    No toca la base; es determinista y la unidad de los tests de #19.
    """
    faltantes = [c for c in COL_REQUERIDAS if c not in df_601.columns]
    if faltantes:
        raise ValueError(f"El módulo 601 no trae las columnas requeridas: {faltantes}")
    if fuente is None:
        fuente = f"ENAHO {anio_enaho} Mód.601 (INEI)"

    w = df_601.copy()

    # 1. Producto MVP por grupo (filtra no-MVP y procesados) y departamento.
    w["producto"] = w["p601a"].map(mapear_producto)
    w = w[w["producto"].notna()].copy()
    w["cod_departamento"] = (
        w["ubigeo"].map(_normalizar_ubigeo).astype("string").str.slice(0, 2)
    )
    w = w[w["cod_departamento"].isin(CODIGOS_DEPARTAMENTO)].copy()

    # 2. Numéricos. factor07 imprescindible: sin él la fila no expande.
    for c in ("i601c", "i601e", "i601b2", "factor07"):
        w[c] = pd.to_numeric(w[c], errors="coerce")
    w = w[w["factor07"] > 0].copy()
    for c in ("i601c", "i601e", "i601b2"):
        w[c] = w[c].fillna(0.0)

    if w.empty:
        return pd.DataFrame(columns=COLUMNAS_GOLD)

    # 3. Magnitudes ponderadas por factor07 (cada fila = una línea de compra).
    w["_gm"] = w["i601c"] * w["factor07"]
    w["_gt"] = (w["i601c"] + w["i601e"]) * w["factor07"]
    w["_ck"] = w["i601b2"] * w["factor07"]

    claves = ["cod_departamento", "producto"]
    agg = (
        w.groupby(claves, as_index=False)
        .agg(
            gasto_monetario_anual=("_gm", "sum"),
            gasto_total_anual=("_gt", "sum"),
            cantidad_kg_anual=("_ck", "sum"),
        )
    )

    # 4. Soporte muestral a nivel de HOGAR (no de línea de compra): un hogar con
    #    varias presentaciones del mismo producto cuenta una sola vez.
    w["_hogar_id"] = w[COL_HOGAR].astype("string").agg("|".join, axis=1)
    hogares = w.drop_duplicates([*claves, "_hogar_id"])
    soporte = (
        hogares.groupby(claves, as_index=False).agg(
            n_muestra=("_hogar_id", "size"),
            hogares_expandidos=("factor07", "sum"),
        )
    )
    agg = agg.merge(soporte, on=claves, how="left")

    # 5. Metadatos.
    agg["anio_enaho"] = anio_enaho
    agg["departamento"] = agg["cod_departamento"].map(nombre_departamento)
    agg["grupo_enaho"] = agg["producto"].map(MVP_GRUPOS)
    agg["fuente"] = fuente

    # 6. Normalizar el peso dentro del MVP por departamento (Σ = 1.0).
    total_dep = agg.groupby("cod_departamento")["gasto_monetario_anual"].transform("sum")
    agg["peso_canasta"] = (agg["gasto_monetario_anual"] / total_dep).where(total_dep > 0, 0.0)

    return (
        agg[COLUMNAS_GOLD]
        .sort_values(["cod_departamento", "producto"])
        .reset_index(drop=True)
    )


def _normalizar_ubigeo(ubigeo: object) -> str:
    """Lleva el ubigeo a string de 6 dígitos (puede venir como int/float)."""
    if isinstance(ubigeo, float) and not pd.isna(ubigeo):
        ubigeo = int(ubigeo)
    s = str(ubigeo).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6)


# --------------------------------------------------------------------------- #
# Suite de calidad de la canasta (§7 del diseño) — sobre el motor del #18.
# Vive aquí (no en validacion/suites.py) para no crear un ciclo de imports:
# validacion es el framework base, canasta lo consume.
# --------------------------------------------------------------------------- #
def _pesos_suman_uno(df: pd.DataFrame) -> tuple[bool, int, str, tuple]:
    sumas = df.groupby(["anio_enaho", "cod_departamento"])["peso_canasta"].sum()
    malos = sumas[(sumas - 1.0).abs() > 1e-6]
    detalle = "Σ pesos = 1.0 por departamento" if malos.empty else f"{len(malos)} depto(s) con Σ≠1"
    ejemplos = tuple(f"{k}={v:.6f}" for k, v in malos.head(5).items())
    return malos.empty, len(malos), detalle, ejemplos


def _baja_confianza_muestral(df: pd.DataFrame) -> tuple[bool, int, str, tuple]:
    bajos = df[pd.to_numeric(df["n_muestra"], errors="coerce") < N_MUESTRA_MINIMA]
    n = len(bajos)
    detalle = (
        "soporte muestral suficiente"
        if n == 0
        else f"{n} celda(s) con n_muestra<{N_MUESTRA_MINIMA}"
    )
    ejemplos = tuple(
        f"{r.cod_departamento}/{r.producto}:{r.n_muestra}" for r in bajos.head(5).itertuples()
    )
    return n == 0, n, detalle, ejemplos


def _precio_implicito_plausible(df: pd.DataFrame) -> tuple[bool, int, str, tuple]:
    kg = pd.to_numeric(df["cantidad_kg_anual"], errors="coerce")
    gm = pd.to_numeric(df["gasto_monetario_anual"], errors="coerce")
    precio = gm / kg.where(kg > 0)
    fuera = precio.notna() & (
        (precio < PRECIO_IMPLICITO_MIN) | (precio > PRECIO_IMPLICITO_MAX)
    )
    n = int(fuera.sum())
    rango = f"[{PRECIO_IMPLICITO_MIN}, {PRECIO_IMPLICITO_MAX}] S//kg"
    detalle = f"precio implícito en {rango}" if n == 0 else f"{n} celda(s) fuera de {rango}"
    return n == 0, n, detalle, tuple(round(p, 2) for p in precio[fuera].head(5))


SUITE_CANASTA = Suite(
    nombre="canasta_consumo_dept",
    expectativas=[
        ColumnasPresentes(COLUMNAS_GOLD),
        MinFilas(1),
        NoNulo("peso_canasta"),
        NoNulo("departamento"),
        NoNulo("grupo_enaho"),
        ClaveUnica(["anio_enaho", "cod_departamento", "producto"]),
        EnConjunto("producto", PRODUCTOS_MVP),
        EnConjunto("cod_departamento", CODIGOS_DEPARTAMENTO),
        EnRango("peso_canasta", minimo=0.0, maximo=1.0),
        EnRango("gasto_monetario_anual", minimo=0.0),
        EnRango("gasto_total_anual", minimo=0.0),
        EnRango("cantidad_kg_anual", minimo=0.0),
        Predicado("pesos_suman_uno", _pesos_suman_uno),
        # Calidad informativa: no bloquea la carga, se reporta (§7).
        Predicado("soporte_muestral", _baja_confianza_muestral, severidad="advertencia"),
        Predicado("precio_implicito", _precio_implicito_plausible, severidad="advertencia"),
    ],
)


# --------------------------------------------------------------------------- #
# IO: lectura del .dta y carga idempotente a gold
# --------------------------------------------------------------------------- #
def leer_modulo_601(ruta_dta: str) -> pd.DataFrame:
    """Lee el `.dta` del Módulo 601 y devuelve sus columnas en minúscula."""
    import pyreadstat  # import perezoso: solo hace falta para la carga real

    df, _meta = pyreadstat.read_dta(ruta_dta)
    df.columns = [c.lower() for c in df.columns]
    return df


def cargar_a_gold(conn, df_canasta: pd.DataFrame, anio_enaho: int) -> int:
    """Carga idempotente por año: DELETE WHERE anio_enaho + COPY, en una transacción."""
    with conn.cursor() as cur:
        cur.execute(_DDL_GOLD)
        cur.execute(
            "DELETE FROM gold.canasta_consumo_dept WHERE anio_enaho = %s", (anio_enaho,)
        )
        buffer = io.StringIO()
        df_canasta[COLUMNAS_GOLD].to_csv(buffer, index=False, header=False)
        buffer.seek(0)
        cols_sql = ", ".join(COLUMNAS_GOLD)
        with cur.copy(
            f"COPY gold.canasta_consumo_dept ({cols_sql}) FROM STDIN WITH (FORMAT csv)"
        ) as copy:
            copy.write(buffer.read())
    conn.commit()
    return len(df_canasta)


_DDL_GOLD = """
CREATE SCHEMA IF NOT EXISTS gold;
CREATE TABLE IF NOT EXISTS gold.canasta_consumo_dept (
    anio_enaho             smallint          NOT NULL,
    cod_departamento       char(2)           NOT NULL,
    departamento           text              NOT NULL,
    producto               text              NOT NULL,
    grupo_enaho            char(2)           NOT NULL,
    gasto_monetario_anual  double precision,
    gasto_total_anual      double precision,
    cantidad_kg_anual      double precision,
    n_muestra              integer,
    hogares_expandidos     double precision,
    peso_canasta           double precision  NOT NULL,
    fuente                 text              NOT NULL,
    computed_at            timestamptz       NOT NULL DEFAULT now(),
    PRIMARY KEY (anio_enaho, cod_departamento, producto)
);
"""


def ejecutar(anio: int, ruta_dta: str, *, dry_run: bool, salida: str | None) -> int:
    """Orquesta: leer .dta → construir pesos → validar → (dry-run | cargar a gold)."""
    log.info("📖 Leyendo módulo 601: %s", ruta_dta)
    df_601 = leer_modulo_601(ruta_dta)
    log.info("   %d filas crudas", len(df_601))

    df_canasta = construir_pesos(df_601, anio)
    log.info(
        "🧮 Canasta: %d filas (≤ 25 deptos × %d productos)",
        len(df_canasta),
        len(PRODUCTOS_CANASTA),
    )

    reporte = validar_o_error(df_canasta, SUITE_CANASTA)  # lanza si hay errores
    for adv in reporte.advertencias:
        log.warning("   ⚠️  %s", adv)

    if salida:
        df_canasta.to_csv(salida, index=False)
        log.info("💾 Escrito CSV: %s", salida)

    if dry_run:
        log.info("🚦 --dry-run: no se carga a gold.")
        return 0

    import psycopg  # import perezoso: --dry-run no necesita la base
    from dotenv import load_dotenv  # lee .env (SUPABASE_DB_URL), como el resto del pipeline

    load_dotenv()
    log.info("⬆️  Cargando a gold.canasta_consumo_dept (idempotente por año %d)…", anio)
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        filas = cargar_a_gold(conn, df_canasta, anio)
    log.info("✅ %d filas en gold.canasta_consumo_dept", filas)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(
        description="Construye gold.canasta_consumo_dept desde el Módulo 601 de la ENAHO."
    )
    ap.add_argument("--anio", type=int, required=True, help="Año de la ENAHO (p.ej. 2023).")
    ap.add_argument("--dta", required=True, help="Ruta al .dta del Módulo 601.")
    ap.add_argument(
        "--dry-run", action="store_true", help="Calcula y valida, pero no carga a la base."
    )
    ap.add_argument("--salida", help="(Opcional) Escribe el resultado a este CSV.")
    args = ap.parse_args(argv)
    return ejecutar(args.anio, args.dta, dry_run=args.dry_run, salida=args.salida)


if __name__ == "__main__":
    sys.exit(main())
