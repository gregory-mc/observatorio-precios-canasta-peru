"""Validación de la metodología de la canasta — issue #20.

Construye un índice de precios propio ponderado por los pesos de
`gold.canasta_consumo_dept` (derivados de la ENAHO) sobre las series de precios
de `gold.fct_precio_diario`, valida su **solidez interna** y lo contrasta —de
forma descriptiva— contra el IPC oficial del INEI (`silver.stg_ipc_inei`).

**Enfoque de validación (opción B, decidido 2026-07-22).** Nuestro índice sigue
6 alimentos frescos (papa, pollo, huevo, cebolla, tomate, limón) que son de los
productos MÁS volátiles de cualquier canasta (±10% mes a mes). Ningún índice
oficial publicado mide ese mismo canasto: el IPC general y hasta el subíndice de
"Alimentos y Bebidas" del INEI/BCRP promedian cientos de productos, casi todos
estables (±1%). Verificado empíricamente (ver docs/validacion_canasta_vs_ipc.md):
correlacionar nuestro índice contra cualquier agregado oficial, sea mes a mes,
interanual o por tendencia, da NO CONCLUYENTE — no por un defecto nuestro, sino
porque compara canastos distintos por naturaleza. Por eso **la correlación con el
IPC NO es criterio de validación**; queda como contexto descriptivo.

La metodología se valida por la **solidez interna del índice** (``evaluar_solidez``),
que es lo que sí delataría una canasta rota:

  1. Pesos que suman 1 sobre los productos del MVP con precio.
  2. Cobertura de productos estable mes a mes (sin saltos por entradas/salidas).
  3. Precios en rango de sanidad (atrapa errores de unidad/parseo).
  4. Serie mensual sin huecos (aviso).

El índice se arma con un Laspeyres de base fija:
`I_t = 100 · Σ w_p · (P_{p,t}/P_{p,0})`, base = primer mes con datos. La
comparación descriptiva contra el IPC usa la variación mensual propia
(`var% = I_t/I_{t-1} − 1`) vs `var_mensual` del IPC en los meses en común.

El script es un **reporte**: nunca escribe a la base.

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

# Umbral de suficiencia para los estadísticos descriptivos del contraste con IPC.
MIN_OVERLAP = 3  # ≥3 meses en común para calcular correlación/tracking error.

# --- Criterios de SOLIDEZ INTERNA (el veredicto real, opción B) --------------- #
# Rango de sanidad para precios de alimentos frescos en S/ por kg. NO es un límite
# de negocio: es amplísimo a propósito. Solo atrapa errores de unidad/parseo (un
# fresco a S/ 500/kg es casi seguro basura); la volatilidad normal cae holgada.
RANGO_PLAUSIBLE_SOLKG = (0.1, 100.0)
# Fracción mínima de meses en que deben estar TODOS los productos con peso, para
# que la composición del índice sea estable (sin saltos por entradas/salidas).
COBERTURA_MINIMA = 0.9

# --- Estadísticos DESCRIPTIVOS del contraste con el IPC (NO son criterio) ----- #
# Se reportan como contexto; ver docstring: la canasta de frescos diverge del IPC
# agregado por naturaleza, así que estos números no aprueban ni reprueban nada.
CORR_REFERENCIA = 0.6  # referencia informativa de correlación.
TRACKING_REFERENCIA = 1.5  # referencia informativa de tracking error (pp).


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
    }
    if len(pares) >= MIN_OVERLAP:
        difs = [n - i for _, n, i in pares]
        media = sum(difs) / len(difs)
        res["dif_abs_media"] = sum(abs(d) for d in difs) / len(difs)
        res["tracking_error"] = (sum((d - media) ** 2 for d in difs) / len(difs)) ** 0.5
        res["correlacion"] = _pearson([n for _, n, _ in pares], [i for _, _, i in pares])
        res["suficiente"] = True
    return res


def evaluar_solidez(
    precios_mensuales: dict[str, dict[str, float]],
    pesos: dict[str, float],
    indice: list[tuple[str, float, float | None]],
) -> dict:
    """Valida la SOLIDEZ INTERNA del índice de canasta — el veredicto real (opción B).

    Nuestro índice sigue 6 alimentos frescos volátiles; NO es una réplica del IPC
    agregado, así que correlacionar contra el IPC no valida nada (ver docstring del
    módulo y docs/validacion_canasta_vs_ipc.md). En su lugar chequeamos que el
    índice sea internamente sano — los defectos que sí delatarían una canasta rota:

      * ``pesos_suman_1``   — los pesos del MVP suman 1.0 (± 1e-6).
      * ``cobertura``       — fracción de meses con TODOS los productos con peso
                              presentes ≥ COBERTURA_MINIMA (composición estable).
      * ``precios_plausibles`` — todo precio mensual dentro de RANGO_PLAUSIBLE_SOLKG.
      * ``serie_continua``  — sin huecos en el tramo mensual cubierto (solo aviso).

    Los tres primeros son el gate (``veredicto`` = "CANASTA SÓLIDA" / "REVISAR");
    la continuidad es informativa. Función pura: no lee la base.
    """
    productos_con_peso = [p for p, w in pesos.items() if w and w > 0]
    meses = sorted(precios_mensuales)

    suma_pesos = sum(pesos[p] for p in productos_con_peso)
    ok_pesos = abs(suma_pesos - 1.0) <= 1e-6

    if meses and productos_con_peso:
        completos = sum(
            1 for m in meses if all(precios_mensuales[m].get(p) for p in productos_con_peso)
        )
        cobertura = completos / len(meses)
    else:
        cobertura = 0.0
    ok_cobertura = cobertura >= COBERTURA_MINIMA

    lo, hi = RANGO_PLAUSIBLE_SOLKG
    fuera_rango = [
        (m, p, pr)
        for m in meses
        for p, pr in precios_mensuales[m].items()
        if pr is not None and not (lo <= pr <= hi)
    ]
    ok_precios = not fuera_rango

    def _ym(s: str) -> int:
        anio, mes = s.split("-")
        return int(anio) * 12 + int(mes) - 1

    huecos: list[str] = []
    if len(meses) >= 2:
        ini, fin = _ym(meses[0]), _ym(meses[-1])
        presentes = {_ym(m) for m in meses}
        huecos = [
            f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(ini, fin + 1) if n not in presentes
        ]

    solida = ok_pesos and ok_cobertura and ok_precios
    return {
        "n_meses": len(meses),
        "n_productos": len(productos_con_peso),
        "checks": {
            "pesos_suman_1": {"ok": ok_pesos, "suma": suma_pesos},
            "cobertura": {"ok": ok_cobertura, "fraccion": cobertura, "minima": COBERTURA_MINIMA},
            "precios_plausibles": {
                "ok": ok_precios,
                "fuera_rango": fuera_rango[:10],
                "rango": RANGO_PLAUSIBLE_SOLKG,
            },
            "serie_continua": {"ok": not huecos, "huecos": huecos},
        },
        "veredicto": "CANASTA SÓLIDA" if solida else "REVISAR",
    }


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
    res: dict, solidez: dict, precios: dict, pesos: dict, indice: list, *, fuente: str, cod_dep: str
) -> None:
    print("\n" + "=" * 70)
    print(f"  VALIDACIÓN CANASTA (solidez interna) — fuente={fuente}  dep={cod_dep}")
    print("=" * 70)

    print(f"\nProductos con peso de canasta: {sorted(pesos)}")
    print(f"Meses con precios: {res['meses_indice'] or '(ninguno)'}")
    print("\nÍndice propio (base 100 = primer mes):")
    for mes, ind, var in indice:
        vtxt = "  —" if var is None else f"{var:+6.2f}%"
        print(f"   {mes}   índice={ind:7.2f}   varMoM={vtxt}")

    # --- Veredicto REAL: solidez interna del índice ------------------------- #
    print("\n--- SOLIDEZ INTERNA (criterio de validación) ---")
    c = solidez["checks"]
    m = "✓" if c["pesos_suman_1"]["ok"] else "✗"
    print(f"   [{m}] pesos suman 1.0            (Σ = {c['pesos_suman_1']['suma']:.6f})")
    m = "✓" if c["cobertura"]["ok"] else "✗"
    print(
        f"   [{m}] cobertura de productos      "
        f"({c['cobertura']['fraccion']:.0%} de meses completos; mín {c['cobertura']['minima']:.0%})"
    )
    m = "✓" if c["precios_plausibles"]["ok"] else "✗"
    lo, hi = c["precios_plausibles"]["rango"]
    detalle = "" if c["precios_plausibles"]["ok"] else f" fuera: {c['precios_plausibles']['fuera_rango']}"
    print(f"   [{m}] precios plausibles         (rango S/{lo}-{hi}/kg){detalle}")
    m = "✓" if c["serie_continua"]["ok"] else "!"
    huecos = c["serie_continua"]["huecos"]
    print(f"   [{m}] serie continua             ({'sin huecos' if not huecos else 'huecos: ' + ', '.join(huecos)})  [aviso]")
    print(f"\n   VEREDICTO: {solidez['veredicto']}")

    # --- Contexto descriptivo: contraste con el IPC (NO es criterio) -------- #
    print("\n--- CONTEXTO: contraste con el IPC oficial (descriptivo, NO valida) ---")
    print(
        "   Nota: nuestra canasta son 6 frescos muy volátiles; el IPC agregado casi\n"
        "   no se mueve. Que diverjan es esperable y NO indica un defecto de método\n"
        "   (ver docs/validacion_canasta_vs_ipc.md)."
    )
    print(f"   Meses en común: {res['meses_comunes'] or '(ninguno)'}")
    if res["suficiente"]:
        print(
            f"   correlación Pearson : {res['correlacion']:.3f}  (referencia {CORR_REFERENCIA})"
        )
        print(
            f"   tracking error      : {res['tracking_error']:.3f} pp  "
            f"(referencia {TRACKING_REFERENCIA})"
        )
        print(f"   dif. absoluta media : {res['dif_abs_media']:.3f} pp")
    else:
        print("   (sin suficientes meses en común para estadísticos; solo contexto)")
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
    solidez = evaluar_solidez(precios, pesos, indice)
    _reporte(res, solidez, precios, pesos, indice, fuente=args.fuente, cod_dep=args.dep)
    # El veredicto real es la solidez interna; el contraste con el IPC no gatilla.
    return 0 if solidez["veredicto"] == "CANASTA SÓLIDA" else 4


if __name__ == "__main__":
    sys.exit(main())
