"""Dimensión de departamentos — ubigeo ↔ nombre ↔ región SISAP (issue #19).

Los pesos de `canasta_consumo_dept` se llavean por **código de departamento**
(2 primeros dígitos del ubigeo, `'01'`..`'25'`), pero las tablas de precios usan
**nombres de región** (`bronze.sisap_precios.region`). Para calcular el costo de
la canasta hace falta puentear ambos mundos; eso es esta dimensión (docs/
canasta_consumo_dept.md §5).

Los 25 códigos y nombres son **canónicos del INEI** (24 departamentos + Provincia
Constitucional del Callao). Ojo con los que confunden: **Lima = `15`**,
**Callao = `07`**.

⚠️ `region_sisap` es **best-effort**: por defecto = el nombre del departamento, que
es el caso común. Los valores reales del SISAP deben reconciliarse contra
`SELECT DISTINCT region FROM bronze.sisap_precios` antes del join definitivo de #19
(p.ej. acentos, "Lima Metropolitana" vs "Lima", mayúsculas). Ver REGION_SISAP_OVERRIDE.
"""

from __future__ import annotations

import pandas as pd

# código (2 díg. del ubigeo) → nombre oficial del departamento (INEI).
DEPARTAMENTOS: dict[str, str] = {
    "01": "Amazonas",
    "02": "Áncash",
    "03": "Apurímac",
    "04": "Arequipa",
    "05": "Ayacucho",
    "06": "Cajamarca",
    "07": "Callao",  # Provincia Constitucional del Callao
    "08": "Cusco",
    "09": "Huancavelica",
    "10": "Huánuco",
    "11": "Ica",
    "12": "Junín",
    "13": "La Libertad",
    "14": "Lambayeque",
    "15": "Lima",
    "16": "Loreto",
    "17": "Madre de Dios",
    "18": "Moquegua",
    "19": "Pasco",
    "20": "Piura",
    "21": "Puno",
    "22": "San Martín",
    "23": "Tacna",
    "24": "Tumbes",
    "25": "Ucayali",
}

# Excepciones donde el nombre de la región en SISAP NO coincide con el del
# departamento. Rellenar a medida que se reconcilie con los valores reales de
# bronze.sisap_precios.region (de momento vacío; placeholder explícito).
REGION_SISAP_OVERRIDE: dict[str, str] = {}

# Códigos válidos (para el dominio de validación de la canasta).
CODIGOS_DEPARTAMENTO: tuple[str, ...] = tuple(DEPARTAMENTOS)


def nombre_departamento(cod: str) -> str | None:
    return DEPARTAMENTOS.get(cod)


def region_sisap(cod: str) -> str | None:
    """Nombre de región SISAP para un código de departamento (best-effort)."""
    if cod not in DEPARTAMENTOS:
        return None
    return REGION_SISAP_OVERRIDE.get(cod, DEPARTAMENTOS[cod])


def dim_departamento_df() -> pd.DataFrame:
    """DataFrame de la dimensión: una fila por departamento (25 filas)."""
    return pd.DataFrame(
        {
            "cod_departamento": list(DEPARTAMENTOS),
            "departamento": list(DEPARTAMENTOS.values()),
            "region_sisap": [region_sisap(c) for c in DEPARTAMENTOS],
        }
    )


DDL = """
CREATE SCHEMA IF NOT EXISTS gold;
CREATE TABLE IF NOT EXISTS gold.dim_departamento (
    cod_departamento  char(2)  NOT NULL,
    departamento      text     NOT NULL,
    region_sisap      text,
    PRIMARY KEY (cod_departamento)
);
"""


def cargar(conn) -> int:
    """Reemplaza el contenido de gold.dim_departamento (idempotente). Devuelve filas."""
    import io

    df = dim_departamento_df()
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("DELETE FROM gold.dim_departamento")
        buffer = io.StringIO()
        df.to_csv(buffer, index=False, header=False)
        buffer.seek(0)
        with cur.copy(
            "COPY gold.dim_departamento (cod_departamento, departamento, region_sisap) "
            "FROM STDIN WITH (FORMAT csv)"
        ) as copy:
            copy.write(buffer.read())
    conn.commit()
    return len(df)


def main(argv: list[str] | None = None) -> int:
    """CLI: carga la dimensión a gold (requiere SUPABASE_DB_URL)."""
    import logging
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import psycopg

    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        filas = cargar(conn)
    logging.getLogger("canasta").info("✅ %d filas en gold.dim_departamento", filas)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
