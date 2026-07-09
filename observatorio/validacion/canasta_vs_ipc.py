"""Validación de la metodología de la canasta contra el IPC del INEI — issue #20.

Construye un índice de precios propio ponderado por los pesos de
`gold.canasta_consumo_dept` (derivados de la ENAHO) sobre las series de precios
de `gold.fct_precio_diario`, y lo compara contra la serie oficial del IPC de
Lima Metropolitana (`silver.stg_ipc_inei`). Si nuestro índice sigue al IPC
oficial (correlación alta, tracking error bajo) en su variación mensual, la
metodología de la canasta queda validada.

**Diseño de la comparación** (ver docs/validacion_canasta_vs_ipc.md para el
detalle y los caveats):

  1. Precio mensual por producto MVP: promedio de las presentaciones de cada
     producto (mapeo `MAPEO_PRECIO_MVP`) sobre los días del mes, para una fuente
     y un departamento dados (default: `sisap_minorista`, Lima = dep 15, que es
     el ámbito del IPC disponible).
  2. Índice tipo Laspeyres de base fija: `I_t = 100 · Σ w_p · (P_{p,t}/P_{p,0})`,
     con `w_p` los pesos de la canasta del departamento, renormalizados sobre los
     productos con precio disponible (Σ w = 1). Base = primer mes con datos.
  3. Variación mensual propia `var% = I_t/I_{t-1} − 1` vs `var_mensual` del IPC.
  4. Métricas sobre los meses en común: correlación de Pearson, tracking error
     (desvío de las diferencias) y diferencia absoluta media.

El script es un **reporte**: nunca escribe a la base. Si todavía no hay meses en
común entre nuestros precios y el IPC publicado (situación al 2026-07: precios
jun–jul 2026 vs IPC ≤ may 2026), imprime el estado "PENDIENTE por datos" con la
señal descriptiva disponible, sin fallar.

Uso:
    python -m observatorio.validacion.canasta_vs_ipc                 # Lima, sisap_minorista
    python -m observatorio.validacion.canasta_vs_ipc --dep 04        # Arequipa
    python -m observatorio.validacion.canasta_vs_ipc --fuente marketplace --dep nacional

Requiere `SUPABASE_DB_URL` en el entorno o en `.env` (se carga con dotenv).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

log = logging.getLogger("canasta_vs_ipc")

# Mapeo de los nombres crudos de producto en gold.fct_precio_diario a los 6 slugs
# del MVP. Cada slug lista patrones SQL ILIKE; se promedian todas las
# presentaciones que matcheen. Los patrones evitan falsos positivos conocidos
# ('Papa %' con espacio excluye "Papaya"; 'Carne de pollo%' excluye otras carnes).
MAPEO_PRECIO_MVP: dict[str, tuple[str, ...]] = {
    "papa": ("Papa %",),
    "pollo": ("Carne de pollo%",),
    "huevo": ("Huevos%",),
    "cebolla": ("Cebolla%",),
    "tomate": ("Tomate%",),
    "limon": ("Limon%", "Limón%"),
}

# Umbrales de suficiencia de datos.
MIN_MESES_INDICE = 2  # hacen falta ≥2 meses para 1 punto de variación mensual.
MIN_OVERLAP = 3  # ≥3 meses en común para una correlación con sentido.

# Umbrales del veredicto (sobre los meses en común, cuando los haya).
CORR_MINIMA = 0.6  # correlación de Pearson mínima para "sigue al IPC".
TRACKING_MAX = 1.5  # tracking error (pp) máximo tolerado.


# --------------------------------------------------------------------------- #
# Núcleo puro (testeable sin base): índice y métricas sobre estructuras simples
# --------------------------------------------------------------------------- #
def construir_indice(
    precios_mensuales: dict[str, dict[str, float]], pesos: dict[str, float]
) -> list[tuple[str, float, float | None]]:
    """Construye el índice mensual ponderado por canasta (Laspeyres base fija).

    `precios_mensuales`: {mes 'YYYY-MM' → {slug → precio_promedio}}.
    `pesos`: {slug → peso_canasta} (no necesariamente suman 1 sobre los slugs
    con precio; se renormalizan aquí sobre los productos presentes en la base).

    Devuelve una lista ordenada de (mes, indice, var_mensual_pct) con
    var_mensual_pct None en el primer mes. Índice base = 100 en el primer mes.
    """
    meses = sorted(precios_mensuales)
    if not meses:
        return []

    base = precios_mensuales[meses[0]]
    # Solo productos con precio en la base Y con peso conocido pueden indexarse.
    productos = [p for p in base if p in pesos and base.get(p)]
    total_peso = sum(pesos[p] for p in productos)
    if not productos or total_peso <= 0:
        return []
    w = {p: pesos[p] / total_peso for p in productos}  # renormalizado, Σ = 1.

    salida: list[tuple[str, float, float | None]] = []
    indice_prev: float | None = None
    for mes in meses:
        pm = precios_mensuales[mes]
        # Índice solo sobre productos con precio ese mes (renormaliza el peso).
        disp = [p for p in productos if pm.get(p)]
        w_mes = sum(w[p] for p in disp)
        if not disp or w_mes <= 0:
            continue
        indice = 100.0 * sum((w[p] / w_mes) * (pm[p] / base[p]) for p in disp)
        var = None if indice_prev is None else (indice / indice_prev - 1.0) * 100.0
        salida.append((mes, indice, var))
        indice_prev = indice
    return salida


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def comparar(
    indice: list[tuple[str, float, float | None]],
    ipc_var: dict[str, float],
) -> dict:
    """Compara la variación mensual propia vs la del IPC en los meses en común.

    `indice`: salida de construir_indice. `ipc_var`: {mes 'YYYY-MM' → var_mensual}.
    Devuelve un dict con los pares comparados y las métricas (o razones de por qué
    no se pudieron calcular).
    """
    nuestros = {mes: var for mes, _, var in indice if var is not None}
    comunes = sorted(set(nuestros) & set(ipc_var))
    pares = [(m, nuestros[m], ipc_var[m]) for m in comunes]

    res: dict = {
        "meses_indice": [m for m, _, _ in indice],
        "meses_con_variacion": sorted(nuestros),
        "meses_ipc": sorted(ipc_var),
        "meses_comunes": comunes,
        "pares": pares,
        "correlacion": None,
        "tracking_error": None,
        "dif_abs_media": None,
        "suficiente": False,
        "veredicto": None,
    }
    if len(pares) >= MIN_OVERLAP:
        difs = [n - i for _, n, i in pares]
        media = sum(difs) / len(difs)
        res["dif_abs_media"] = sum(abs(d) for d in difs) / len(difs)
        res["tracking_error"] = (sum((d - media) ** 2 for d in difs) / len(difs)) ** 0.5
        res["correlacion"] = _pearson([n for _, n, _ in pares], [i for _, _, i in pares])
        res["suficiente"] = True
        corr = res["correlacion"]
        te = res["tracking_error"]
        ok = (corr is not None and corr >= CORR_MINIMA) and (te is not None and te <= TRACKING_MAX)
        res["veredicto"] = "VALIDADA" if ok else "NO CONCLUYENTE"
    return res


# --------------------------------------------------------------------------- #
# IO: lectura de la base (no escribe nada)
# --------------------------------------------------------------------------- #
def _sql_case_slug() -> str:
    """CASE que mapea fct_precio_diario.producto → slug MVP (o NULL)."""
    ramas = []
    for slug, patrones in MAPEO_PRECIO_MVP.items():
        cond = " or ".join("producto ilike %s" for _ in patrones)
        ramas.append(f"when {cond} then '{slug}'")
    return "case " + " ".join(ramas) + " else null end"


def cargar(conn, *, fuente: str, cod_dep: str, anio_canasta: int | None):
    """Lee de la base los precios mensuales por producto, los pesos y el IPC."""
    with conn.cursor() as cur:
        # 1. Precios mensuales por producto MVP.
        params: list = []
        for patrones in MAPEO_PRECIO_MVP.values():
            params.extend(patrones)
        filtro_dep = (
            "cod_departamento = %s" if cod_dep != "nacional" else "cod_departamento is null"
        )
        dep_params = [cod_dep] if cod_dep != "nacional" else []
        cur.execute(
            f"""
            with etiquetado as (
                select to_char(fecha_captura, 'YYYY-MM') as mes,
                       {_sql_case_slug()} as slug,
                       precio_prom
                from gold.fct_precio_diario
                where fuente = %s and {filtro_dep}
            )
            select mes, slug, avg(precio_prom)
            from etiquetado
            where slug is not null
            group by mes, slug
            order by mes, slug
            """,
            [*params, fuente, *dep_params],
        )
        precios: dict[str, dict[str, float]] = {}
        for mes, slug, precio in cur.fetchall():
            precios.setdefault(mes, {})[slug] = float(precio)

        # 2. Pesos de la canasta del departamento (último anio_enaho si no se fija).
        cur.execute(
            """
            select producto, peso_canasta
            from gold.canasta_consumo_dept
            where cod_departamento = %s
              and (%s::int is null or anio_enaho = %s::int)
              and anio_enaho = (
                  select max(anio_enaho) from gold.canasta_consumo_dept
                  where cod_departamento = %s
                    and (%s::int is null or anio_enaho = %s::int))
            """,
            [
                cod_dep if cod_dep != "nacional" else "15",
                anio_canasta,
                anio_canasta,
                cod_dep if cod_dep != "nacional" else "15",
                anio_canasta,
                anio_canasta,
            ],
        )
        pesos = {prod: float(w) for prod, w in cur.fetchall()}

        # 3. IPC mensual (var_mensual por mes).
        cur.execute("select to_char(fecha_mes, 'YYYY-MM'), var_mensual from silver.stg_ipc_inei")
        ipc_var = {mes: float(v) for mes, v in cur.fetchall() if v is not None}

    return precios, pesos, ipc_var


# --------------------------------------------------------------------------- #
# Reporte
# --------------------------------------------------------------------------- #
def _reporte(
    res: dict, precios: dict, pesos: dict, indice: list, *, fuente: str, cod_dep: str
) -> None:
    print("\n" + "=" * 70)
    print(f"  VALIDACIÓN CANASTA vs IPC — fuente={fuente}  dep={cod_dep}")
    print("=" * 70)

    print(f"\nProductos con peso de canasta: {sorted(pesos)}")
    print(f"Meses con precios: {res['meses_indice'] or '(ninguno)'}")
    print("\nÍndice propio (base 100 = primer mes):")
    for mes, ind, var in indice:
        vtxt = "  —" if var is None else f"{var:+6.2f}%"
        print(f"   {mes}   índice={ind:7.2f}   varMoM={vtxt}")

    print(
        f"\nMeses de IPC publicados: {res['meses_ipc'][:3]} … {res['meses_ipc'][-3:]}"
        if len(res["meses_ipc"]) > 6
        else f"\nMeses de IPC publicados: {res['meses_ipc']}"
    )
    print(f"Meses en común (para comparar): {res['meses_comunes'] or '(ninguno)'}")

    if res["suficiente"]:
        print("\n--- MÉTRICAS (meses en común) ---")
        for mes, n, i in res["pares"]:
            print(f"   {mes}   propia={n:+6.2f}%   IPC={i:+6.2f}%   dif={n - i:+6.2f}pp")
        print(f"\n   correlación Pearson : {res['correlacion']:.3f}  (mín {CORR_MINIMA})")
        print(f"   tracking error      : {res['tracking_error']:.3f} pp  (máx {TRACKING_MAX})")
        print(f"   dif. absoluta media : {res['dif_abs_media']:.3f} pp")
        print(f"\n   VEREDICTO: {res['veredicto']}")
    else:
        print("\n--- ESTADO: PENDIENTE POR DATOS ---")
        n_var = len(res["meses_con_variacion"])
        if n_var < 1:
            n_precios = len(res["meses_indice"])
            print(
                f"   No hay ni un punto de variación mensual propia "
                f"(se necesitan ≥{MIN_MESES_INDICE} meses de precios; hay {n_precios})."
            )
        elif not res["meses_comunes"]:
            print(
                "   No hay solape temporal: nuestros precios y el IPC publicado no "
                "comparten ningún mes."
            )
            ult_ipc = res["meses_ipc"][-1] if res["meses_ipc"] else "—"
            print(f"     · meses con variación propia : {res['meses_con_variacion']}")
            print(f"     · último mes de IPC publicado: {ult_ipc}")
        else:
            print(
                f"   Solo {len(res['meses_comunes'])} mes(es) en común; se necesitan "
                f"≥{MIN_OVERLAP} para una correlación con sentido."
            )
        # Señal descriptiva (NO es la validación): variación propia disponible.
        if res["meses_con_variacion"]:
            ult = res["meses_con_variacion"][-1]
            propia = next(v for m, _, v in indice if m == ult)
            print(
                f"\n   Señal descriptiva (no comparable aún): variación propia "
                f"{ult} = {propia:+.2f}% ; IPC de referencia (otro mes) ≈ "
                f"{res['meses_ipc'][-1] if res['meses_ipc'] else '—'}."
            )
        print("\n   → Rehacer cuando el INEI publique un mes que solape con los precios.")
    print("=" * 70 + "\n")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Valida la canasta contra el IPC del INEI (#20).")
    ap.add_argument(
        "--fuente",
        default="sisap_minorista",
        help="Fuente de fct_precio_diario (default sisap_minorista).",
    )
    ap.add_argument(
        "--dep",
        default="15",
        help="Código de departamento (default 15=Lima) o 'nacional' (cod_dep NULL).",
    )
    ap.add_argument(
        "--anio-canasta",
        type=int,
        default=None,
        help="Año ENAHO de la canasta (default: el más reciente cargado).",
    )
    args = ap.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("SUPABASE_DB_URL"):
        log.error("Falta SUPABASE_DB_URL (en el entorno o en .env).")
        return 2

    import psycopg

    with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=20) as conn:
        precios, pesos, ipc_var = cargar(
            conn, fuente=args.fuente, cod_dep=args.dep, anio_canasta=args.anio_canasta
        )

    if not pesos:
        log.error(
            "Sin pesos de canasta para dep=%s. ¿Cargaste gold.canasta_consumo_dept?", args.dep
        )
        return 3

    indice = construir_indice(precios, pesos)
    res = comparar(indice, ipc_var)
    _reporte(res, precios, pesos, indice, fuente=args.fuente, cod_dep=args.dep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
