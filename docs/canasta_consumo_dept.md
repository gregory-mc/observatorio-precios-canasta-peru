# Diseño de la tabla `canasta_consumo_dept`

Especificación de la tabla que asigna, **por departamento**, el peso relativo de cada
producto del MVP dentro de la canasta de consumo de alimentos, derivado de los
microdatos de la **ENAHO** (INEI). Es el deliverable de la issue **#17** (diseño); la
construcción es **#19**.

> Insumo: [`docs/enaho.md`](enaho.md) (estructura de los microdatos, columnas y códigos
> de producto confirmados en ENAHO 2023) y el notebook
> [`notebooks/01_enaho_exploracion.ipynb`](../notebooks/01_enaho_exploracion.ipynb) (#13).

**Productos del MVP:** papa, limón, pollo, cebolla, huevo, tomate.

---

## 1. Para qué sirve

El observatorio rastrea **precios** por producto y departamento (SISAP minorista,
Marketplace retail). Para convertir esos precios en **un solo "costo de la canasta" por
departamento** necesitamos un peso por producto: cuánto pesa la papa vs. el pollo, etc.,
en el gasto real de los hogares de ese departamento.

`canasta_consumo_dept` es esa **tabla de pesos** (referencia/dimensión). No tiene fechas
de precio: es estructural, atada al **año de la ENAHO** usada, y se recalcula solo cuando
el INEI publica una ENAHO más reciente.

```
precios diarios (SISAP/Marketplace)  ×  pesos (canasta_consumo_dept)  =  costo canasta dept
        gold.fct_precio_diario                 gold.canasta_consumo_dept           (#19, dashboard)
```

---

## 2. Granularidad y clave

**Grain:** una fila por `(anio_enaho, cod_departamento, producto)` → **decisión #3 resuelta**.

- `anio_enaho` en la clave para que recargar con una ENAHO más nueva **no colisione** con
  la anterior (los pesos son propios de un año de encuesta).
- `cod_departamento` = los **2 primeros dígitos del `ubigeo`** (`'01'`..`'25'`: 24
  departamentos + Prov. Const. del Callao). Es el nivel de agregación que demostró el
  notebook (#13).

**PK:** `(anio_enaho, cod_departamento, producto)`.
**Filas esperadas:** ≤ 25 × 6 = **150** por año (menos si algún producto no aparece en un
departamento).

---

## 3. Esquema (DDL de referencia)

Capa **gold** (agregado de negocio derivado de microdatos). Mientras no exista el proyecto
dbt (S6), este DDL es el contrato; lo crea/puebla el one-shot de #19. En S6 se reescribe
como modelo dbt con el **mismo contrato** (ver §6).

```sql
CREATE SCHEMA IF NOT EXISTS gold;

-- Pesos de la canasta de alimentos del MVP por departamento, desde la ENAHO.
-- Una fila por (año de encuesta, departamento, producto). Tabla estructural,
-- sin fecha de precio: se recalcula al cambiar de año de ENAHO (#19).
CREATE TABLE IF NOT EXISTS gold.canasta_consumo_dept (
    anio_enaho             smallint          NOT NULL,  -- año de la ENAHO (p.ej. 2023)
    cod_departamento       char(2)           NOT NULL,  -- 2 díg. del ubigeo ('01'..'25')
    departamento           text              NOT NULL,  -- nombre (incl. Callao)
    producto               text              NOT NULL,  -- slug MVP: papa|limon|pollo|cebolla|huevo|tomate
    grupo_enaho            char(2)            NOT NULL,  -- grupo de 2 díg. de p601a (05,07,09,32,33,38)

    -- Agregados ponderados por factor07 (expandidos a población). Soles/kg ANUALES.
    gasto_monetario_anual  double precision,            -- Σ(i601c · factor07): solo COMPRA
    gasto_total_anual      double precision,            -- Σ((i601c + i601e) · factor07): compra + autoconsumo
    cantidad_kg_anual      double precision,            -- Σ(i601b2 · factor07): kg comprados

    -- Soporte muestral (para fiabilidad; ver §7).
    n_muestra              integer,                     -- nº de hogares en la muestra (SIN expandir)
    hogares_expandidos     double precision,            -- Σ(factor07): hogares representados

    -- Peso final usado por la canasta. Normalizado DENTRO del MVP por (anio, depto):
    -- Σ peso_canasta = 1.0 por cada (anio_enaho, cod_departamento). Base: gasto_monetario.
    peso_canasta           double precision  NOT NULL,

    fuente                 text              NOT NULL,  -- 'ENAHO <anio> Mód.601 (INEI)'
    computed_at            timestamptz       NOT NULL DEFAULT now(),

    PRIMARY KEY (anio_enaho, cod_departamento, producto)
);
```

### Por qué se guardan los tres agregados de gasto
`peso_canasta` se calcula por defecto con `gasto_monetario_anual`, pero la tabla **guarda
también** `gasto_total_anual` y `cantidad_kg_anual` para que #19 (o un análisis futuro)
pueda recalcular el peso con otra base **sin reprocesar los microdatos**, y para validar
precios implícitos (`gasto / kg ≈ precio observado`).

---

## 4. Metodología (cómo se llena) — decisiones #1 y #2 resueltas

Fuente única: **Módulo 601** (Gastos en Alimentos y Bebidas) de una ENAHO. Pasos:

1. **Filtrar productos del MVP por grupo de 2 dígitos** de `p601a` y **excluir procesados**
   (decisión #2 → *agregar por grupo excluyendo procesados*):

   | producto | grupo | excluir (procesados, ver `docs/enaho.md`) |
   |---|---|---|
   | papa | `05` | `0507` papa seca, `1804` harina de papa |
   | huevo | `07` | `1804/1805` harina de huevo, `1905` fideos al huevo, `0108/0109` pan de huevo |
   | pollo | `09` | grupo `10` menudencia, `1107`–`1109` conserva, embutidos de pollo |
   | cebolla | `32` | — |
   | tomate | `33` | grupo `30` (`3010`–`3024`) salsa/pasta de tomate |
   | limón | `38` | grupo `42` hoja para infusión, `3904`–`4116` limón dulce |

   Dentro del grupo se **suman todas las presentaciones frescas** (los `XX0n`). Cada fila
   del módulo es una línea de compra distinta, así que sumar los códigos no-excluidos del
   grupo no duplica (ver chequeo `XX00` vs `XX0n` en §7, a verificar en #19).

2. **Derivar `cod_departamento`** = `substr(ubigeo, 1, 2)`.

3. **Agregar por `(anio_enaho, cod_departamento, producto)` ponderando por `factor07`**
   (factor de expansión — *imprescindible*, nunca promediar en crudo):
   - `gasto_monetario_anual = Σ(i601c · factor07)`
   - `gasto_total_anual     = Σ((i601c + i601e) · factor07)`
   - `cantidad_kg_anual     = Σ(i601b2 · factor07)`
   - `n_muestra = COUNT(hogares)` ; `hogares_expandidos = Σ(factor07)`

4. **Normalizar dentro del MVP** por `(anio_enaho, cod_departamento)`:
   ```
   peso_canasta = gasto_monetario_anual / Σ_productos(gasto_monetario_anual)
   ```
   → los 6 pesos suman **1.0** por departamento.

### Decisión #1 — qué gasto usa el peso
Base por defecto: **`i601c` (gasto monetario de compra)**, porque es lo más alineado con
nuestro tracking de **precios de mercado** (SISAP/Marketplace): pesa lo que los hogares
efectivamente **compran**. El autoconsumo valorizado (`i601e`) **no** entra en el peso por
defecto, pero queda persistido en `gasto_total_anual` por si #19 quiere el "peso real en la
dieta" (relevante en departamentos rurales con mucho autoconsumo). Cambiar la base = un solo
`UPDATE peso_canasta`, sin tocar microdatos.

---

## 5. Dependencia para el join con precios (`dim_departamento`)

Los pesos se llavean por **ubigeo** (`'01'`..`'25'`), pero las tablas de precios usan
**nombres de región** (`bronze.sisap_precios.region`, categorías de Marketplace). Para
calcular el costo de la canasta (#19) hace falta un mapeo:

```
dim_departamento(cod_departamento, departamento, region_sisap, ...)
```

Ojo con los casos que confunden: **Lima** = ubigeo `15`, **Callao** = ubigeo `07`. Esta
dimensión es un **prerequisito chico de #19** (no de #17), pero se documenta acá porque
condiciona el diseño de la clave (se eligió ubigeo como llave canónica por ser estable).

---

## 6. Capa y materialización

- **Crudo ENAHO = bronze a nivel de archivo.** Los `.dta` (módulo 601) son inmutables por
  año y pesados; **no** se cargan fila por fila a Postgres (free-tier). Viven como archivo
  en `data/enaho/` (local) con respaldo opcional en R2 (`enaho/<anio>/`), igual que describe
  `docs/enaho.md`.
- **`canasta_consumo_dept` se computa en un one-shot** (Python `pyreadstat`/pandas o DuckDB
  sobre el `.dta`) que persiste **solo el agregado** a `gold.canasta_consumo_dept`. Es la
  tarea **#19**.
- **Idempotencia por año** (mismo patrón que `bronze.inei_ipc`):
  `DELETE FROM gold.canasta_consumo_dept WHERE anio_enaho = :anio;` y luego `COPY`, todo en
  una transacción. Re-correr un año lo reemplaza limpio.
- **En S6 (dbt, M3):** se reescribe como modelo dbt manteniendo este contrato. Si para
  entonces se decide **landear** el módulo 601 en `bronze.enaho_gasto_601`, el modelo es SQL
  puro; si no, queda como modelo Python/seed alimentado por el one-shot de #19.

---

## 7. Invariantes y tests de calidad (para GE en #5 / dbt en S6)

- **Suma de pesos:** `Σ peso_canasta = 1.0 ± 1e-6` por cada `(anio_enaho, cod_departamento)`.
- **Rango:** `peso_canasta ∈ [0, 1]`; `gasto_*_anual ≥ 0`.
- **Unicidad:** la PK `(anio_enaho, cod_departamento, producto)` sin duplicados.
- **Dominio:** `cod_departamento` ∈ los 25 códigos; `producto` ∈ los 6 slugs;
  `grupo_enaho` consistente con el producto.
- **Fiabilidad muestral:** marcar como baja confianza las celdas con `n_muestra < 30`
  (pocos hogares reportando ese producto en ese departamento → peso ruidoso). No se borran;
  se reportan.
- **Sanidad de precio implícito:** `gasto_monetario_anual / cantidad_kg_anual` debe caer en
  un rango plausible de S/ por kg comparado con SISAP/Marketplace (detecta errores de unidad).

---

## 8. Construcción (#19) — estado

Implementado en `observatorio/canasta/` (PR de #19):

- ✅ **One-shot** `construir_canasta.py`: lógica pura `construir_pesos(df_601, anio)` +
  lectura `.dta` (`pyreadstat`) + carga idempotente por año a `gold.canasta_consumo_dept`
  (`DELETE WHERE anio_enaho` + `COPY`). CLI con `--anio/--dta/--dry-run/--salida`.
- ✅ **Mapeo de productos** `productos.py`: por grupo de 2 dígitos de `p601a`, excluyendo
  procesados (única exclusión intra-grupo: papa seca `0507`; el resto cae en otros grupos).
- ✅ **`dim_departamento`** (`dim_departamento.py` + `sql/gold_schema.sql`): 25 deptos,
  ubigeo ↔ nombre. `region_sisap` es **best-effort** (= nombre del depto); falta reconciliar
  contra `SELECT DISTINCT region FROM bronze.sisap_precios` antes del join definitivo.
- ✅ **Tests §7** (`tests/canasta/`) con módulo 601 sintético (sin `.dta` ni base) + la
  **suite de calidad** `SUITE_CANASTA` (motor de #18): Σ pesos = 1.0, dominios, clave única,
  rangos; n_muestra<30 y precio implícito fuera de rango como **advertencias**.

### Decisión tomada: doble conteo `XX00` vs `XX0n`
Se sigue el supuesto del §4.1 (cada fila del módulo es una línea de compra distinta, así
que sumar todos los códigos no-excluidos del grupo **no** duplica) → se suman tanto el
agregado `XX00` como las presentaciones `XX0n`. La verificación empírica de co-ocurrencia
(un hogar reportando el mismo producto bajo `XX00` y `XX0n` en el mismo periodo) queda
pendiente de correr contra los microdatos reales; si apareciera, preferir el código específico.

### Genuinamente pendiente (no es código)
- Conseguir el **código INEI** de la ENAHO más reciente (2024/2025) para recargar con
  `--anio` y reemplazar 2023 (afecta los pesos; ver `docs/enaho.md` §"Año utilizado").
- Reconciliar `dim_departamento.region_sisap` con los valores reales de SISAP.
```
