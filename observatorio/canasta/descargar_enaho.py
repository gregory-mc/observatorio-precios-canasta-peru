"""Descarga los microdatos de la ENAHO necesarios para la canasta (issue #19).

Extrae a un CLI la lógica de descarga que vivía solo en el notebook
`notebooks/01_enaho_exploracion.ipynb` (celda 4), para poder bajar los `.dta`
sin abrir Jupyter. Baja el Módulo 07 (Gastos en Alimentos y Bebidas → archivo
`...-601.dta`, central para los pesos) y el 34 (Sumaria).

**Requiere IP peruana**: el portal del INEI geo-bloquea a los runners de GitHub,
no a una máquina en Perú (ver docs/enaho.md).

Uso:
    # Año soportado por enahodata v0.0.3 (hasta 2023):
    python -m observatorio.canasta.descargar_enaho --anio 2023

    # Año más reciente (2024/2025): aportar el "código INEI" del año.
    # Se obtiene en https://proyectos.inei.gob.pe/microdatos/ → ENAHO
    # Metodología ACTUALIZADA → año → Módulo 07; la URL de descarga trae
    # `.../STATA/<CODIGO>-Modulo07.zip`. Referencia: 2021→759, 2022→784, 2023→906.
    python -m observatorio.canasta.descargar_enaho --anio 2024 --codigo 934

Al terminar imprime la ruta del `.dta` del 601, lista para pasársela a
`observatorio.canasta.construir_canasta --dta ...`.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Códigos de módulo en el sistema de microdatos del INEI (NO es el "601"):
#   07 = Gastos en Alimentos y Bebidas  → archivo ...-601.dta
#   34 = Sumaria (variables calculadas por hogar)
MOD_ALIMENTOS = "07"
MOD_SUMARIA = "34"


def descargar(anio: int, *, codigo: int | None, dir_data: Path) -> Path:
    """Descarga los módulos 07 y 34 de la ENAHO `anio` a `dir_data`.

    Devuelve la ruta al `.dta` del Módulo 601 (módulo 07). Idempotente: si ya
    hay un `*601*.dta` bajo `dir_data`, no vuelve a descargar.
    """
    from enahodata import enahodata

    # enahodata v0.0.3 solo conoce años hasta 2023 en su tabla interna
    # (YEAR_MAP). Para 2024/2025 hay que inyectar el código INEI del año.
    _ed = importlib.import_module("enahodata.enahodata")
    if codigo is not None:
        _ed.YEAR_MAP[str(anio)] = {"codigo": codigo, "year": anio}
    if str(anio) not in _ed.YEAR_MAP:
        raise SystemExit(
            f"❌ El año {anio} no está en enahodata. Pasá su código INEI con "
            f"--codigo (ver el docstring) o usá un año soportado: "
            f"{sorted(_ed.YEAR_MAP)}."
        )

    dir_data.mkdir(parents=True, exist_ok=True)

    if list(dir_data.rglob("*601*.dta")):
        print(f"↩️  Ya existe un *601*.dta bajo {dir_data} — no se descarga de nuevo.")
    else:
        print(f"⬇️  Descargando ENAHO {anio} módulos {MOD_ALIMENTOS}+{MOD_SUMARIA} → {dir_data}")
        enahodata(
            modulos=[MOD_ALIMENTOS, MOD_SUMARIA],
            anios=[str(anio)],
            descomprimir=True,
            only_dta=True,
            overwrite=False,
            output_dir=str(dir_data),
            panel=False,
        )

    encontrados = sorted(dir_data.rglob("*601*.dta"))
    if not encontrados:
        raise SystemExit(
            f"❌ No se encontró ningún *601*.dta bajo {dir_data} tras la descarga. "
            "¿Terminó bien? ¿Es correcto el año/código?"
        )
    return encontrados[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Descarga los .dta de la ENAHO para construir la canasta (#19)."
    )
    ap.add_argument("--anio", type=int, default=2023, help="Año de la ENAHO (default 2023).")
    ap.add_argument(
        "--codigo",
        type=int,
        default=None,
        help="Código INEI del año (solo para 2024/2025, que enahodata no conoce).",
    )
    ap.add_argument(
        "--dir",
        dest="dir_data",
        default="data/enaho",
        help="Carpeta destino (default data/enaho, gitignored).",
    )
    args = ap.parse_args(argv)

    ruta_601 = descargar(args.anio, codigo=args.codigo, dir_data=Path(args.dir_data))
    print(f"\n✅ Módulo 601 listo: {ruta_601}")
    print("\nSiguiente paso — construir y cargar la canasta a gold:")
    print(
        f"    set -a; source .env; set +a\n"
        f"    python -m observatorio.canasta.construir_canasta "
        f"--anio {args.anio} --dta {ruta_601}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
